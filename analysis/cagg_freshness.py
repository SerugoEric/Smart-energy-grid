"""Section 6.2: test freshness and delayed arrivals on a separate hypertable.

SCENARIO
    A test hypertable energy_test (event_time TIMESTAMPTZ, energy_kwh
    DOUBLE PRECISION) with an initially unpopulated hourly continuous
    aggregate energy_test_hourly of energy sum and row count. Real-time
    aggregation is disabled (timescaledb.materialized_only = true) and the
    automatic refresh policy is left off during the whole test.

    H        start of the most recent completed CAT hour
    old_hour H minus 48 hours

    Records are inserted as in the assignment timeline:
        old_hour + 10 min   1.0 kWh
        old_hour + 25 min   0.5 kWh
        H      + 10 min   2.0 kWh

STAGES
    A. After the 1.0 kWh insert, manually refresh only the older hour and
       query the aggregate: it must show 1 kWh, 1 row, with no H bucket.
    B. Insert 0.5 kWh and 2 kWh. Before any refresh, query the raw table and
       the aggregate. With materialized_only=TRUE the aggregate is unchanged
       (old hour 1 kWh/1 row, no H bucket) while the raw table already shows
       the new rows.
    C. Enable real-time aggregation (materialized_only=FALSE) and repeat the
       aggregate query: the stored older-hour bucket still shows 1 kWh/1 row
       and the current hour H now reads 2 kWh/1 row directly from the raw
       table.
    D. Manually refresh both complete hours and query again: older hour
       1.5 kWh / 2 rows, H 2 kWh / 1 row. The raw table after all inserts
       must agree.

    The program also reports which hours the Section 6.1 policy (3-day
    lookback, 1-hour end offset, 15-minute schedule) could refresh at this
    test time: the older hour (H-48h) is within the lookback and ends more
    than one hour before now, so it qualifies; hour H is the current,
    incomplete hour and its bucket end is only minutes in the future, so the
    end-offset rule keeps the policy away from it until it has fully closed.

HOW TO RUN
    From the project root:

        python analysis\\cagg_freshness.py
"""

import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

# Hourly buckets are aligned to CAT hours by giving time_bucket an origin on
# a whole CAT hour (2000-01-01 00:00:00+02), so bucket boundaries are CAT
# :00 in the wall clock the assignment uses.
HOUR_ORIGIN = "2000-01-01 00:00:00+02"


def truncate_hour(value):
    return value.replace(minute=0, second=0, microsecond=0)


def raw_rows(cursor, start, end):
    cursor.execute(
        """
        SELECT event_time, energy_kwh FROM energy_test
        WHERE event_time >= %s AND event_time < %s
        ORDER BY event_time
        """,
        (start, end),
    )
    return cursor.fetchall()


def agg_rows(cursor, view_name):
    cursor.execute(f"SELECT bucket, sum_energy_kwh, row_count FROM {view_name} "
                   "ORDER BY bucket")
    return cursor.fetchall()


def line(label, message=""):
    print(f"{label:<46}{message}")


def main() -> None:
    test_time = cat_now()
    current_hour = truncate_hour(test_time)
    h = current_hour - timedelta(hours=1)
    old_hour = h - timedelta(hours=48)

    inset_old_1 = old_hour + timedelta(minutes=10)
    inset_old_2 = old_hour + timedelta(minutes=25)
    inset_h = h + timedelta(minutes=10)

    print("=" * 78)
    print("Section 6.2  Freshness and delayed arrivals")
    print(f"Actual CAT test time {cat_text(test_time)}")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")
    print("TEST PARAMETERS")
    print(f"  H (start of most recent completed CAT hour) {cat_text(h)}")
    print(f"  Old hour (H minus 48 hours)                 {cat_text(old_hour)}")
    print(f"  Insert 1.0 kWh at                           {cat_text(inset_old_1)}")
    print(f"  Insert 0.5 kWh at                           {cat_text(inset_old_2)}")
    print(f"  Insert 2.0 kWh at                           {cat_text(inset_h)}")
    print("")

    connection = connect()
    cursor = connection.cursor()
    connection.autocommit = True

    # --- create the test table and aggregate ----------------------------
    print("SETUP")
    cursor.execute("DROP TABLE IF EXISTS energy_test CASCADE")
    cursor.execute(
        """
        CREATE TABLE energy_test (
            event_time TIMESTAMPTZ,
            energy_kwh  DOUBLE PRECISION
        )
        """
    )
    cursor.execute(
        """
        SELECT create_hypertable('energy_test', by_range('event_time'),
                                 create_default_indexes => FALSE,
                                 if_not_exists => TRUE)
        """
    )
    cursor.execute(
        """
        CREATE MATERIALIZED VIEW energy_test_hourly
        WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
        SELECT time_bucket(INTERVAL '1 hour', event_time,
                           TIMESTAMPTZ %s) AS bucket,
               sum(energy_kwh) AS sum_energy_kwh,
               count(*)        AS row_count
        FROM energy_test
        GROUP BY bucket
        WITH NO DATA
        """,
        (HOUR_ORIGIN,),
    )
    cursor.execute(
        """
        SELECT materialized_only
        FROM timescaledb_information.continuous_aggregates
        WHERE view_name = 'energy_test_hourly'
        """
    )
    print(f"  energy_test created; hourly cagg materialized_only="
          f"{cursor.fetchone()[0]}")
    print("  No refresh policy exists for the test cagg (left off)")
    print("")

    # --- stage A ---------------------------------------------------------
    print("STAGE A  insert 1.0 kWh, manually refresh the older hour only")
    cursor.execute(
        "INSERT INTO energy_test (event_time, energy_kwh) VALUES (%s, 1.0)",
        (inset_old_1,),
    )
    cursor.execute(
        """
        CALL refresh_continuous_aggregate('energy_test_hourly',
                                          %s, %s + INTERVAL '1 hour')
        """,
        (old_hour, old_hour),
    )
    print("  aggregate after refreshing only the older hour:")
    for bucket_row, energy, rows in agg_rows(cursor, "energy_test_hourly"):
        line("", f"    {cat_text(bucket_row)}  energy={energy:g} kWh  rows={rows}")
    print("")

    # --- stage B ---------------------------------------------------------
    print("STAGE B  insert 0.5 kWh and 2.0 kWh, NO refresh yet")
    cursor.execute(
        "INSERT INTO energy_test (event_time, energy_kwh) VALUES (%s, 0.5)",
        (inset_old_2,),
    )
    cursor.execute(
        "INSERT INTO energy_test (event_time, energy_kwh) VALUES (%s, 2.0)",
        (inset_h,),
    )
    print("  raw table now:")
    for t, energy in raw_rows(cursor, old_hour, h + timedelta(hours=1)):
        line("", f"    {cat_text(t)}  {energy:g} kWh")
    print("  aggregate (materialized_only=TRUE, before any refresh):")
    rows = agg_rows(cursor, "energy_test_hourly")
    if not rows:
        print("    (no buckets returned)")
    for bucket_row, energy, count in rows:
        line("", f"    {cat_text(bucket_row)}  energy={energy:g} kWh  rows={count}")
    print("")

    # --- stage C ---------------------------------------------------------
    print("STAGE C  enable real-time aggregation, still before any refresh")
    cursor.execute(
        """
        ALTER MATERIALIZED VIEW energy_test_hourly
        SET (timescaledb.materialized_only = false)
        """
    )
    print("  aggregate with real-time aggregation enabled:")
    rows = agg_rows(cursor, "energy_test_hourly")
    if not rows:
        print("    (no buckets returned)")
    for bucket_row, energy, count in rows:
        line("", f"    {cat_text(bucket_row)}  energy={energy:g} kWh  rows={count}")
    print("")

    # --- stage D ---------------------------------------------------------
    print("STAGE D  manually refresh both complete hours")
    cursor.execute(
        """
        CALL refresh_continuous_aggregate('energy_test_hourly',
                                          %s, %s + INTERVAL '1 hour')
        """,
        (old_hour, old_hour),
    )
    cursor.execute(
        """
        CALL refresh_continuous_aggregate('energy_test_hourly',
                                          %s, %s + INTERVAL '1 hour')
        """,
        (h, h),
    )
    print("  raw table after all inserts:")
    for t, energy in raw_rows(cursor, old_hour, h + timedelta(hours=1)):
        line("", f"    {cat_text(t)}  {energy:g} kWh")
    print("  aggregate after refreshing both hours:")
    for bucket_row, energy, count in agg_rows(cursor, "energy_test_hourly"):
        line("", f"    {cat_text(bucket_row)}  energy={energy:g} kWh  rows={count}")
    print("")

    # --- checks ---------------------------------------------------------
    cursor.execute(
        """
        SELECT sum(energy_kwh), count(*)
        FROM energy_test
        WHERE event_time >= %s AND event_time < %s + INTERVAL '1 hour'
        """,
        (old_hour, old_hour),
    )
    old_energy, old_rows = cursor.fetchone()
    cursor.execute(
        """
        SELECT sum(energy_kwh), count(*)
        FROM energy_test
        WHERE event_time >= %s AND event_time < %s + INTERVAL '1 hour'
        """,
        (h, h),
    )
    h_energy, h_rows = cursor.fetchone()
    print("CHECKS")
    print(f"  older hour raw: energy={float(old_energy):g} kWh rows={old_rows} "
          "(expect 1.5, 2)")
    print(f"  hour H raw:     energy={float(h_energy):g} kWh rows={h_rows} "
          "(expect 2, 1)")
    print("")

    # --- which hours could the 6.1 policy refresh at this test time ------
    print("SECTION 6.1 POLICY AT THIS TEST TIME (3-day lookback, "
          "1-hour end offset)")
    cutoff = test_time - timedelta(hours=1)
    line("  policy can refresh buckets ending at or before ", f"{cat_text(cutoff)}")
    line("  older hour %s" % cat_text(old_hour), ends_before_cutoff(older=old_hour, cutoff=cutoff))
    line("  hour H %s" % cat_text(h), ends_before_cutoff(older=h, cutoff=cutoff))
    print("")

    connection.close()
    print(f"Completed {cat_text()} CAT")


def ends_before_cutoff(older, cutoff):
    return "YES (ends before cutoff, within 3-day lookback)" \
        if older + timedelta(hours=1) <= cutoff else "no"


if __name__ == "__main__":
    run_with_log("cagg_freshness", main)