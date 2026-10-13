"""Section 5.1: identify demand patterns.

PURPOSE
    1. Plot total network energy per CAT day and totals for the four
       seven-day periods beginning 1, 8, 15 and 22 September. Consumption
       totals are sums of energy_kwh.
    2. Find the three highest 15-minute network demand intervals across all
       28 days by summing power_kw across meters at each event_time, and
       report their times and kW values. (kW - kWh interpretation is written
       up in the report.)

HOW DAYS ARE ALIGNED
    The session is set to Africa/Kigali (UTC+2) by common.db.connect(), and
    every time_bucket call passes the explicit origin
    2026-09-01 00:00:00+02, so 1-day and 7-day buckets start on CAT
    midnight (the same convention as Section 6.1).

CHART OUTPUT
    PNG files are written to analysis/output/. The printed summary is saved
    to logs/demand_patterns_<CAT timestamp>.txt by run_with_log.

HOW TO RUN
    From the project root:

        python analysis\\demand_patterns.py
"""

import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

ORIGIN = "2026-09-01 00:00:00+02"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
PERIOD_STARTS = [
    "2026-09-01 00:00:00+02",
    "2026-09-08 00:00:00+02",
    "2026-09-15 00:00:00+02",
    "2026-09-22 00:00:00+02",
]


def plot_daily(days: list, totals_kwh: list) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(days, totals_kwh, width=0.7, color="#1f77b4")
    ax.set_title("Total network energy per CAT day, September 2026")
    ax.set_xlabel("CAT day")
    ax.set_ylabel("Energy [kWh]")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    path = OUTPUT_DIR / "5_1_daily_energy.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_periods(labels: list, totals_kwh: list) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, totals_kwh, width=0.55, color="#2ca02c")
    for x, value in enumerate(totals_kwh):
        ax.text(x, value, f"{value:,.0f}", ha="center", va="bottom")
    ax.set_title("Total network energy per seven-day period, September 2026")
    ax.set_ylabel("Energy [kWh]")
    fig.tight_layout()
    path = OUTPUT_DIR / "5_1_seven_day_periods.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def query_daily_totals(connection) -> tuple[list[datetime], list[float]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT time_bucket(INTERVAL '1 day', event_time,
                               TIMESTAMPTZ %s) AS day,
                   sum(energy_kwh) AS total_kwh
            FROM energy_readings
            GROUP BY day
            ORDER BY day
            """,
            (ORIGIN,),
        )
        rows = cursor.fetchall()
    days = [row[0] for row in rows]
    totals = [float(row[1]) for row in rows]
    return days, totals


def query_period_totals(connection) -> list[float]:
    totals = []
    with connection.cursor() as cursor:
        for start in PERIOD_STARTS:
            cursor.execute(
                """
                SELECT sum(energy_kwh)
                FROM energy_readings
                WHERE event_time >= %s::timestamptz
                  AND event_time <  %s::timestamptz + INTERVAL '7 days'
                """,
                (start, start),
            )
            totals.append(float(cursor.fetchone()[0]))
    return totals


def query_peak_intervals(connection) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_time, sum(power_kw) AS demand_kw
            FROM energy_readings
            GROUP BY event_time
            ORDER BY demand_kw DESC, event_time
            LIMIT 3
            """
        )
        return [(row[0], float(row[1])) for row in cursor.fetchall()]


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 5.1  Demand patterns")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")

    connection = connect()

    days, totals = query_daily_totals(connection)
    print("DAILY TOTAL NETWORK ENERGY (kWh per CAT day)")
    print("-" * 40)
    for day, total in zip(days, totals):
        print(f"  {day.strftime('%Y-%m-%d')}  {total:,.3f}")
    print(f"  sum of daily buckets     {sum(totals):,.3f}")
    print("")

    period_totals = query_period_totals(connection)
    labels = ["1-7 Sep", "8-14 Sep", "15-21 Sep", "22-28 Sep"]
    print("SEVEN-DAY PERIOD TOTALS (kWh)")
    print("-" * 40)
    for label, total in zip(labels, period_totals):
        print(f"  {label}  {total:,.3f}")
    print(f"  sum of the four periods  {sum(period_totals):,.3f}")
    print("")

    peaks = query_peak_intervals(connection)
    print("THREE HIGHEST 15-MINUTE NETWORK DEMAND INTERVALS (kW)")
    print("-" * 60)
    for rank, (when, demand) in enumerate(peaks, 1):
        print(f"  #{rank}  {when.strftime('%Y-%m-%d %H:%M')} CAT  "
              f"{demand:,.3f} kW")
    print("")

    daily_path = plot_daily(days, totals)
    periods_path = plot_periods(labels, period_totals)
    print(f"Charts written to {daily_path}")
    print(f"                  {periods_path}")
    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")

    connection.close()


if __name__ == "__main__":
    run_with_log("demand_patterns", main)