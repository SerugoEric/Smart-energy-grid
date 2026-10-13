"""Section 5.3: assess reporting quality.

PURPOSE
    1. Completeness for the whole network and each region over all 28 days.
       Planned reading count = registered meters * 28 days * 96 readings/day.
       Completeness = 100 * observed unique (meter_id, event_time) pairs /
       planned count.
    2. For readings whose event_time is 21 September, sum energy_kwh once
       using only arrivals with received_time at or before 00:00 on 22
       September and again using all arrivals. Report both totals, the
       difference in kWh and as a percentage of the final (all-arrival)
       total.

NOTES
    * A distinct (meter_id, event_time) group is exactly one observed unique
      reading; because we compare against the CLEANED table every observed
      pair appears exactly once.
    * Because the arrival is the same as event_time + 15 minutes when not
      delayed, the 00:00 cutoff on 22 September catches every normal arrival
      for 21 September but excludes readings delayed past midnight which are
      still the previous day's consumption.

HOW TO RUN
    From the project root:

        python analysis\\reporting_quality.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

DAYS = 28
SLOTS_PER_DAY = 96
PLANNED_PER_METER = DAYS * SLOTS_PER_DAY  # 2,688
DAY_21_START = "2026-09-21 00:00:00+02"
DAY_22_START = "2026-09-22 00:00:00+02"


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 5.3  Reporting quality")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")

    connection = connect()
    cursor = connection.cursor()

    # --- 1. Completeness -----------------------------------------------
    cursor.execute("SELECT count(*) FROM meters")
    registered = cursor.fetchone()[0]
    planned_network = registered * PLANNED_PER_METER
    print("COMPLETENESS OVER ALL 28 DAYS")
    print("-" * 70)
    print(f"  Registered meters             {registered:,}")
    print(f"  Planned readings per meter    {PLANNED_PER_METER:,}"
          f"  (28 days x 96)")
    print(f"  Planned network readings      {planned_network:,}")
    print("")

    cursor.execute(
        """
        SELECT count(*)  AS observed_network
        FROM (SELECT DISTINCT meter_id, event_time
              FROM energy_readings) d
        """
    )
    observed_network = cursor.fetchone()[0]
    completeness_network = 100.0 * observed_network / planned_network
    print("  Whole network")
    print(f"    observed unique pairs       {observed_network:,}")
    print(f"    completeness                {completeness_network:.4f}%")
    print("")

    cursor.execute(
        """
        SELECT m.region,
               count(DISTINCT (r.meter_id, r.event_time)) AS observed
        FROM energy_readings r
        JOIN meters m USING (meter_id)
        GROUP BY m.region
        ORDER BY split_part(m.region, ' ', 2)::int
        """
    )
    region_rows = cursor.fetchall()
    print("  By region")
    print(f"  {'Region':<12}{'Planned':>12}{'Observed':>12}"
          f"{'Completeness%':>16}")
    for region, observed in region_rows:
        planned = 400 * PLANNED_PER_METER
        completeness = 100.0 * observed / planned
        print(f"  {region:<12}{planned:>12,}{observed:>12,}"
              f"{completeness:>16.4f}")
    print("")

    # --- 2. Arrival-cutoff totals for 21 September ----------------------
    cursor.execute(
        """
        SELECT sum(energy_kwh) AS early_energy
        FROM energy_readings
        WHERE event_time >= %s::timestamptz
          AND event_time <  %s::timestamptz
          AND received_time <= %s::timestamptz
        """,
        (DAY_21_START, DAY_22_START, DAY_22_START),
    )
    early_energy = float(cursor.fetchone()[0])

    cursor.execute(
        """
        SELECT sum(energy_kwh) AS final_energy,
               count(*)        AS reading_count
        FROM energy_readings
        WHERE event_time >= %s::timestamptz
          AND event_time <  %s::timestamptz
        """,
        (DAY_21_START, DAY_22_START),
    )
    final_energy, reading_count = cursor.fetchone()
    final_energy = float(final_energy)

    difference = final_energy - early_energy
    percentage = 100.0 * difference / final_energy

    print("21 SEPTEMBER ENERGY, EARLY vs ALL ARRIVALS (kWh)")
    print("-" * 70)
    print(f"  readings with event_time on 21 September   {reading_count:,}")
    print(f"  energy using received_time <= 00:00 22 Sep {early_energy:,.3f} kWh")
    print(f"  energy using all arrivals                  {final_energy:,.3f} kWh")
    print(f"  difference (final - early)                 {difference:,.3f} kWh")
    print(f"  difference as % of final total             {percentage:.4f}%")
    print("")

    cursor.close()
    connection.close()

    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")


if __name__ == "__main__":
    run_with_log("reporting_quality", main)