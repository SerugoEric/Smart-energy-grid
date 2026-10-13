"""Audit that the Aggregate dashboard never reads energy_readings (FIX 2).

Parses the Aggregate panel SQL files and lists, per panel, the relations after
FROM/JOIN (ignoring local WITH CTE names). Fails if any panel references
energy_readings or uses an averaging function (averaging averages).

    python dashboards\\audit_aggregate_sources.py
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "dashboards"))

from dashboard_data import PANELS, sql_path, sql_text  # noqa: E402

FROM_JOIN = re.compile(r"(?i)\b(?:FROM|JOIN)\s+([a-zA-Z_][\w.]*)")
CTE_NAME = re.compile(r"(?is)(?:\bWITH|,)\s+([a-zA-Z_]\w*)\s*(?:\([^)]*\))?\s+AS\s*\(")
AVG = re.compile(r"(?i)\bavg\s*\(")

EXPECTED_PRIMARY = {
    "P1": "cagg_hour_region",
    "P2": "cagg_15min_region",
    "P3": "cagg_15min_region",
    "P4": "cagg_day_meter",
    "P5": "cagg_15min_region",
}


def strip_sql(sql: str) -> str:
    """Remove -- line comments and /* */ blocks so prose is not read as SQL."""
    stripped = re.sub(r"(?s)/\*.*?\*/", " ", sql)
    return re.sub(r"(?m)--[^\n]*", " ", stripped)


def relations(sql: str):
    stripped = strip_sql(sql)
    ctes = set(CTE_NAME.findall(stripped))
    found = [r for r in FROM_JOIN.findall(stripped) if r.lower() not in
             {c.lower() for c in ctes}]
    # de-duplicate, preserve order
    seen, ordered = set(), []
    for name in found:
        if name.lower() not in seen:
            seen.add(name.lower())
            ordered.append(name)
    return ordered, sorted(ctes)


def main():
    print("=" * 78)
    print("FIX 2  Aggregate dashboard source audit")
    print("=" * 78)
    print("")
    print(f"  {'Panel':<6}{'SQL file':<32}{'Relations used':<34}{'Result'}")
    print("  " + "-" * 74)

    ok = True
    for panel in PANELS:
        sql = sql_text("Aggregate", panel)
        rels, ctes = relations(sql)
        touches_raw = "energy_readings" in {r.lower() for r in rels} \
            or "energy_readings" in strip_sql(sql).lower()
        averages = bool(AVG.search(strip_sql(sql)))
        primary_ok = EXPECTED_PRIMARY[panel] in rels
        bad = touches_raw or averages or not primary_ok
        ok = ok and not bad
        result = "FAIL" if bad else "OK"
        detail = "; ".join(rels)
        if ctes:
            detail += f"  (CTEs: {', '.join(ctes)})"
        print(f"  {panel:<6}{sql_path('Aggregate', panel).name:<32}"
              f"{detail[:33]:<34}{result}")
        if bad:
            if touches_raw:
                print("    ! reads energy_readings")
            if averages:
                print("    ! uses an averaging function")
            if not primary_ok:
                print(f"    ! expected primary relation {EXPECTED_PRIMARY[panel]}")
    print("")
    print("  Allowed non-aggregate relation: meters (labels and registered counts).")
    print("")
    print("PASS - every Aggregate panel reads only the Section 6.1 aggregates "
          "(and meters); no energy_readings, no averaging of averages."
          if ok else "FAIL - see details above; fix the query, do not ignore it.")


if __name__ == "__main__":
    main()
