"""Section 5.2: compare regions and customer types.

PURPOSE
    Join cleaned readings to the meters metadata and, over all 28 days,
    compare energy totals separately by region and by customer type. Each
    total is divided by that group's registered meter count to obtain energy
    per meter. The report interprets which differences remain after
    normalization.

REGION SORTING
    Region labels are "Region 1" ... "Region 10"; alphabetical order would
    place Region 10 before Region 2, so the queries order by the numeric
    part of the label.

HOW TO RUN
    From the project root:

        python analysis\\regions.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402


def report_grouped(connection, group_column: str, headline: str) -> None:
    order = {
        "region": "split_part(region, ' ', 2)::int",
        "customer_type": "customer_type",
    }[group_column]
    sql = f"""
        SELECT {group_column} AS group_name,
               count(DISTINCT m.meter_id)                  AS meter_count,
               sum(r.energy_kwh)                           AS total_kwh,
               sum(r.energy_kwh) / count(DISTINCT m.meter_id) AS per_meter_kwh
        FROM meters m
        LEFT JOIN energy_readings r USING (meter_id)
        GROUP BY {group_column}
        ORDER BY {order}
    """
    print(headline)
    print("-" * 60)
    print(f"  {'Group':<18}{'Meters':>8}{'Total kWh':>18}"
          f"{'Per meter kWh':>16}")
    with connection.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
    for name, meters, total, per_meter in rows:
        print(f"  {name:<18}{meters:>8}{float(total):>18,.3f}"
              f"{float(per_meter):>16,.4f}")
    print("")


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 5.2  Regions and customer types")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")

    connection = connect()

    print("REGISTERED METER COUNTS (from meters table, sanity check)")
    print("-" * 60)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT region, count(*) AS meters
            FROM meters GROUP BY region
            ORDER BY split_part(region, ' ', 2)::int
            """
        )
        for region, meters in cursor.fetchall():
            print(f"  {region:<18}{meters:>8}")
        cursor.execute(
            """
            SELECT customer_type, count(*) AS meters
            FROM meters GROUP BY customer_type ORDER BY customer_type
            """
        )
        print("")
        for kind, meters in cursor.fetchall():
            print(f"  {kind:<18}{meters:>8}")
    print("")

    report_grouped(connection, "region",
                   "ENERGY BY REGION OVER ALL 28 DAYS")
    report_grouped(connection, "customer_type",
                   "ENERGY BY CUSTOMER TYPE OVER ALL 28 DAYS")

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM meters")
        registered = cursor.fetchone()[0]
    print(f"Registered meters total: {registered:,}")

    print("")
    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")
    connection.close()


if __name__ == "__main__":
    run_with_log("regions", main)