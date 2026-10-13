"""Section 7.3: verify the Raw and Aggregate dashboards return matching results.

PROCEDURE
    Both modes run the Section 7.3 filter exactly:
        00:00 on 22 September through 00:00 on 29 September (exclusive),
        all regions, meter 1000000000 for the meter-history panel.
    The panel queries are the same files the dashboards execute
    (sql/dashboards/raw and sql/dashboards/aggregate), loaded through
    dashboard_data.py, so this compares the dashboards' own SQL.

COMPARISON (per panel, matched by key)
    P1 key (bucket, region), P2 key (bucket), P3 key (period), P4 key (bucket),
    P5 key (region) with observed reading counts and completeness.
    Requirements:
        identical keys and identical reading counts (P5 observed),
        energy differences  <= 0.001 kWh,
        completeness differences <= 0.000001 percentage points (before rounding).

OUTPUT
    results/dashboard_match.csv   one row per panel with the comparison result
    a PASS/FAIL table on stdout

HOW TO RUN
    python dashboards\\verify_dashboards.py
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "dashboards"))

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402
from dashboard_data import PANELS, run_raw, run_agg  # noqa: E402

START = datetime.fromisoformat("2026-09-22T00:00:00+02:00")
END = datetime.fromisoformat("2026-09-29T00:00:00+02:00")
METER = 1000000000

ENERGY_TOLERANCE = 0.001
COMPLETENESS_TOLERANCE = 0.000001

KEYS = {
    "P1": ("bucket", "region"),
    "P2": ("bucket",),
    "P3": ("period",),
    "P4": ("bucket",),
    "P5": ("region",),
}


def compare(panel_id: str, left: list, right: list) -> dict:
    keys = KEYS[panel_id]
    left_by_key = {tuple(r[k] for k in keys): r for r in left}
    right_by_key = {tuple(r[k] for k in keys): r for r in right}

    keys_identical = set(left_by_key) == set(right_by_key)
    counts_identical = True
    max_energy = 0.0
    max_completeness = 0.0

    if panel_id == "P5":
        for key in set(left_by_key) & set(right_by_key):
            if left_by_key[key]["observed"] != right_by_key[key]["observed"]:
                counts_identical = False
            max_completeness = max(
                max_completeness,
                abs(left_by_key[key]["completeness"]
                    - right_by_key[key]["completeness"]))
        energy_ok = keys_identical
    else:
        for key in set(left_by_key) & set(right_by_key):
            max_energy = max(max_energy,
                             abs(left_by_key[key]["energy_kwh"]
                                 - right_by_key[key]["energy_kwh"]))
        energy_ok = keys_identical and max_energy <= ENERGY_TOLERANCE

    completeness_ok = max_completeness <= COMPLETENESS_TOLERANCE
    status = "PASS" if (energy_ok and counts_identical and completeness_ok) \
        else "FAIL"

    return {
        "panel": panel_id,
        "rows_raw": len(left),
        "rows_aggregate": len(right),
        "keys_identical": keys_identical,
        "counts_identical": counts_identical,
        "max_abs_energy_diff_kwh": round(max_energy, 9),
        "max_abs_completeness_diff_pct": round(max_completeness, 12),
        "status": status,
    }


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 7.3  Verify Raw and Aggregate dashboards match")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print(f"Range [{START} .. {END}) exclusive, all regions, meter {METER}")
    print("")

    raw = run_raw(START, END, METER)
    agg = run_agg(START, END, METER)

    rows = [compare(p, raw[p].rows, agg[p].rows) for p in PANELS]

    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "dashboard_match.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"  {'Panel':<6}{'Rows':>7}{'Keys':>8}{'Counts':>8}"
          f"{'Max dE kWh':>14}{'Max dComp pp':>15}{'':>8}")
    print("  " + "-" * 66)
    for r in rows:
        print(f"  {r['panel']:<6}{r['rows_raw']:>7}"
              f"{str(r['keys_identical']):>8}{str(r['counts_identical']):>8}"
              f"{r['max_abs_energy_diff_kwh']:>14.6f}"
              f"{r['max_abs_completeness_diff_pct']:>15.9f}"
              f"{r['status']:>8}")
    print("")
    overall = all(r["status"] == "PASS" for r in rows)
    print("PASS - both dashboards match within tolerances" if overall
          else "FAIL - differences found; fix the query, not the tolerance")
    print(f"Results written to {csv_path}")
    print(f"Completed {cat_text()} CAT  "
          f"({(cat_now() - started).total_seconds():.3f} s)")


if __name__ == "__main__":
    run_with_log("verify_dashboards", main)
