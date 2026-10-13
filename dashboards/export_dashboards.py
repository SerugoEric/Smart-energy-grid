"""Export the Raw and Aggregate dashboard definitions to JSON (Section 7).

Dash has no native Grafana-style JSON export, so this writes a portable
definition: identity, filters, variables, time zone, default range, panel titles,
panel sources and the exact SQL of every panel (loaded from sql/dashboards/).
No connection strings, hosts, users or passwords are written.

    python dashboards\\export_dashboards.py

Outputs
    dashboards\\Raw.json
    dashboards\\Aggregate.json
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "dashboards"))

from dashboard_data import PANELS, PANEL_TITLES, sql_text  # noqa: E402

SOURCES = {
    "Raw": {
        "P1": "energy_readings JOIN meters",
        "P2": "energy_readings",
        "P3": "energy_readings",
        "P4": "energy_readings",
        "P5": "energy_readings JOIN meters (observed = count(*)); meters (planned)",
    },
    "Aggregate": {
        "P1": "cagg_hour_region",
        "P2": "cagg_15min_region (re-bucketed to CAT days)",
        "P3": "cagg_15min_region (re-bucketed to CAT days, mapped to periods)",
        "P4": "cagg_day_meter",
        "P5": "cagg_15min_region (SUM(reading_count)); meters (registered counts)",
    },
}

UNITS = {"P1": "kWh", "P2": "kWh", "P3": "kWh", "P4": "kWh", "P5": "percent"}


def dashboard_definition(mode: str) -> dict:
    return {
        "name": mode,
        "tool": "Dash (Plotly)",
        "note": "Dash has no Grafana JSON; this is the portable dashboard "
                "definition. Contains no connection secrets.",
        "timezone": "Africa/Kigali",
        "default_time_range": {
            "picker_start": "2026-09-22",
            "picker_end_inclusive": "2026-09-28",
            "query_start": "2026-09-22T00:00:00+02:00",
            "query_end_exclusive": "2026-09-29T00:00:00+02:00",
        },
        "variables": [
            {"name": "range", "type": "date_range_cat_days",
             "end_exclusive": True, "default": "2026-09-22 .. 2026-09-29"},
            {"name": "meter", "type": "dropdown", "default": 1000000000,
             "used_by": ["P4"]},
        ],
        "panels": [
            {
                "id": pid,
                "title": PANEL_TITLES[pid],
                "unit": UNITS[pid],
                "source": SOURCES[mode][pid],
                "sql": sql_text(mode, pid),
            }
            for pid in PANELS
        ],
    }


def main() -> None:
    for mode in ("Raw", "Aggregate"):
        target = PROJECT_ROOT / "dashboards" / f"{mode}.json"
        target.write_text(json.dumps(dashboard_definition(mode), indent=2),
                          encoding="utf-8")
        print(f"Wrote {target}")


if __name__ == "__main__":
    main()
