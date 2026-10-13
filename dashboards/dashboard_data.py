"""Shared data layer for the Raw and Aggregate dashboards (Sections 7.1-7.4).

SINGLE SOURCE OF TRUTH
    Every panel query lives in its own file:
        sql/dashboards/raw/p1_hourly_regional_energy.sql   ... p5_...
        sql/dashboards/aggregate/p1_hourly_regional_energy.sql ... p5_...
    The Dash dashboards, verify_dashboards.py and benchmark_dashboards.py all
    load the same files, so the SQL that is measured is byte-for-byte the SQL
    the dashboards issue. Query parameters are named psycopg2 placeholders:
        %(start)s, %(end)s   selected whole-CAT-day range, end exclusive
        %(meter)s            the meter-history selector (P4 only)

TWO FLAVOURS
    run_raw(...)   reads energy_readings directly and joins meters where a
                   region label is needed (Section 7.1).
    run_agg(...)   reads the Section 6.1 continuous aggregates only; meters is
                   queried for labels and registered counts (Section 7.2).
                   Buckets are combined by summing stored sums/counts.

Each flavour executes one SQL statement per panel and returns the rows plus the
query duration in milliseconds, measured with time.perf_counter around the
statement. Figures are built by the caller, so the timing harness can time the
query separately from rendering.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.db import connect  # noqa: E402

ORIGIN = "2026-09-01 00:00:00+02"

# The four seven-day periods of Section 5.1, aligned to CAT midnight.
SEVEN_DAY_PERIODS = [
    ("1-7 Sep",   "2026-09-01 00:00:00+02", "2026-09-08 00:00:00+02"),
    ("8-14 Sep",  "2026-09-08 00:00:00+02", "2026-09-15 00:00:00+02"),
    ("15-21 Sep", "2026-09-15 00:00:00+02", "2026-09-22 00:00:00+02"),
    ("22-28 Sep", "2026-09-22 00:00:00+02", "2026-09-29 00:00:00+02"),
]

PANELS = ["P1", "P2", "P3", "P4", "P5"]

PANEL_TITLES = {
    "P1": "Hourly regional energy",
    "P2": "Daily network energy",
    "P3": "Network energy in seven-day periods",
    "P4": "Daily energy of selected meter",
    "P5": "Completeness by region",
}

PANEL_FILES = {
    "P1": "p1_hourly_regional_energy.sql",
    "P2": "p2_daily_network_energy.sql",
    "P3": "p3_seven_day_periods.sql",
    "P4": "p4_daily_meter_energy.sql",
    "P5": "p5_completeness_by_region.sql",
}

SQL_DIR = Path(PROJECT_ROOT) / "sql" / "dashboards"

# Which columns are integer counts rather than measurements.
COUNT_COLUMNS = {"registered", "observed", "planned", "reading_count"}


class Panel:
    def __init__(self, panel_id: str, query_ms: float, rows) -> None:
        self.panel_id = panel_id
        self.query_ms = query_ms
        self.rows = rows


def sql_path(mode: str, panel_id: str) -> Path:
    return SQL_DIR / mode.lower() / PANEL_FILES[panel_id]


def sql_text(mode: str, panel_id: str) -> str:
    """Return the exact SQL for a panel and mode (used by exports/docs)."""
    return sql_path(mode, panel_id).read_text(encoding="utf-8")


def _coerce(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if value is None:
            out[key] = None
        elif key in COUNT_COLUMNS:
            out[key] = int(value)
        elif key in ("energy_kwh", "completeness"):
            out[key] = float(value)
        else:
            out[key] = value
    return out


def _exec(cursor, mode: str, panel_id: str, params: dict):
    started = time.perf_counter()
    cursor.execute(sql_text(mode, panel_id), params)
    columns = [d[0] for d in cursor.description]
    rows = [_coerce(dict(zip(columns, r))) for r in cursor.fetchall()]
    return (time.perf_counter() - started) * 1000.0, rows


def _params(start, end, meter_id) -> dict:
    return {"start": start, "end": end, "meter": int(meter_id)}


def run_raw(start, end, meter_id) -> dict:
    connection = connect()
    cursor = connection.cursor()
    params = _params(start, end, meter_id)
    results = {}
    for panel_id in PANELS:
        ms, rows = _exec(cursor, "raw", panel_id, params)
        results[panel_id] = Panel(panel_id, ms, rows)
    cursor.close()
    connection.close()
    return results


def run_agg(start, end, meter_id) -> dict:
    connection = connect()
    cursor = connection.cursor()
    params = _params(start, end, meter_id)
    results = {}
    for panel_id in PANELS:
        ms, rows = _exec(cursor, "aggregate", panel_id, params)
        results[panel_id] = Panel(panel_id, ms, rows)
    cursor.close()
    connection.close()
    return results


def run_dashboard(mode: str, start, end, meter_id) -> dict:
    """Dispatch to the requested flavour; returns {panel_id: Panel}."""
    from datetime import datetime

    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.fromisoformat(end)
    return run_raw(start, end, meter_id) if mode == "Raw" \
        else run_agg(start, end, meter_id)
