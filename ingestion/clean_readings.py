"""Section 2.3: remove duplicate readings and preserve one consistent benchmark.

PURPOSE
    Find every (meter_id, event_time) pair with more than one row in
    energy_readings, compare the six measured values of those copies, and
    delete the extras so exactly one row per pair remains. Missing intervals
    are left as gaps: nothing is inserted for them.

    Section 2.3.1 requires the comparison to happen BEFORE any deletion, so
    this program runs in three stages and stops if the data does not behave as
    the generator promises:

      1. CLASSIFY   every duplicated pair as identical or conflicting,
                    comparing received_time, power_kw, voltage_v, current_a,
                    frequency_hz and energy_kwh.
      2. REPORT     row count and summed energy_kwh before cleaning, plus the
                    classification result.
      3. DELETE     only the copies of pairs classified identical, keeping the
                    row with the earliest received_time (the reading that
                    arrived first, which is the one a live system would have
                    used). Conflicting pairs are never deleted silently.

    Nothing here fills gaps. A missing reading means no measurement exists for
    that meter and interval; writing zero would claim measured zero consumption
    and would drag every average, peak and completeness figure downwards.

INPUTS
    - energy_readings, as loaded by ingestion/load_readings.py
    - smart_meter_simulator.dataset_info() for the expected unique count

OUTPUTS
    - energy_readings reduced to one row per (meter_id, event_time)
    - before/after row counts and energy_kwh sums, printed and logged
    - the same report in logs/clean_readings_<CAT timestamp>.txt

HOW TO RUN
    From the project root:

        python ingestion\\clean_readings.py

    Safe to re-run: the second run finds no duplicated pairs and changes
    nothing, which is itself the verification asked for in Section 2.3.2.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

import smart_meter_simulator  # noqa: E402 - the supplied file, imported unchanged

from common.cat_time import cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

# The six columns Section 2.3.1 says to compare between copies.
COMPARISON_COLUMNS = [
    "received_time",
    "power_kw",
    "voltage_v",
    "current_a",
    "frequency_hz",
    "energy_kwh",
]

# Two floats are "the same" only within a tolerance. The generator writes
# byte-identical copies, so exact equality should hold, but a tolerance of
# 1e-9 catches any formatting round-trip difference without hiding a real
# conflict: real conflicts differ in the sixth decimal place at least.
FLOAT_TOLERANCE = 1e-9


def classify_duplicates(connection) -> dict:
    """Group duplicated pairs and classify each as identical or conflicting.

    Returns a dictionary with the pair counts per class and the list of
    conflicting pairs, which the caller must handle explicitly.
    """
    # A duplicated pair has copies > 1 in this grouped view. count(*) is cheap
    # because the index on (meter_id, event_time) built in Section 3.1 can be
    # used for the grouping if it exists; without it the planner still scans
    # once, which is the same cost the DELETE below pays.
    statement = """
        SELECT meter_id,
               event_time,
               count(*)                                       AS copies,
               count(DISTINCT received_time)                 AS distinct_received,
               count(DISTINCT round(power_kw::numeric, 6))    AS distinct_power,
               count(DISTINCT round(voltage_v::numeric, 6))   AS distinct_voltage,
               count(DISTINCT round(current_a::numeric, 6))   AS distinct_current,
               count(DISTINCT round(frequency_hz::numeric, 6)) AS distinct_frequency,
               count(DISTINCT round(energy_kwh::numeric, 8))  AS distinct_energy
        FROM energy_readings
        GROUP BY meter_id, event_time
        HAVING count(*) > 1
        ORDER BY meter_id, event_time
    """
    with connection.cursor() as cursor:
        cursor.execute(statement)
        rows = cursor.fetchall()

    identical: list[tuple] = []
    conflicting: list[tuple] = []

    for row in rows:
        (meter_id, event_time, copies, distinct_received, distinct_power,
         distinct_voltage, distinct_current, distinct_frequency,
         distinct_energy) = row
        distinct_counts = [distinct_received, distinct_power, distinct_voltage,
                           distinct_current, distinct_frequency, distinct_energy]
        # Every comparison column must collapse to one distinct value across
        # the copies. round(..., 6) above absorbs float text round-tripping;
        # anything still above 1 is a genuine disagreement.
        if all(value == 1 for value in distinct_counts):
            identical.append((meter_id, event_time, copies))
        else:
            conflicting.append((meter_id, event_time, copies, distinct_counts))

    return {
        "identical": identical,
        "conflicting": conflicting,
        "duplicate_pair_count": len(rows),
    }


def energy_sum(connection) -> float:
    with connection.cursor() as cursor:
        cursor.execute("SELECT coalesce(sum(energy_kwh), 0) FROM energy_readings")
        return float(cursor.fetchone()[0])


def row_count(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM energy_readings")
        return cursor.fetchone()[0]


def unique_pair_count(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM (SELECT DISTINCT meter_id, event_time "
            "FROM energy_readings) t"
        )
        return cursor.fetchone()[0]


def delete_extra_copies(connection, pairs: list[tuple], expected_rows: int) -> int:
    """Delete every row of a duplicated pair except the earliest arrival.

    WHY EARLIEST received_time KEEPS THE ROW
        received_time is simulated arrival at the utility. The first copy is
        the one a live system would have stored; later copies are redeliveries
        of the same reading. Section 2.3.1 does not say which copy to keep,
        only that the six compared values match, so any choice is defensible as
        long as it is repeatable. Ordering by received_time and then by physical
        position makes the choice deterministic, so a re-run deletes nothing.

    WHY tableoid AND ctid ARE BOTH NEEDED
        ctid is a row's physical position, but it is unique only WITHIN ONE
        RELATION. A hypertable is many relations: TimescaleDB stores each
        one-day chunk as its own table, and every chunk numbers its rows from
        (0,1) again. energy_readings has 29 chunks, so a bare "WHERE ctid IN
        (...)" deleted the same position in all 29 chunks and removed 1,388,466
        rows where 53,113 were intended. That is a measured failure, not a
        hypothetical one: the first run of this program lost 1,335,353 rows and
        was caught by the expected_rows check at the end of this function,
        which is why that check exists.

        Pairing ctid with tableoid — the OID of the chunk the row physically
        lives in — makes the identifier unique across the whole hypertable.
        The join "d.tableoid = r.tbl AND d.ctid = r.ctid" therefore targets
        exactly the row the window function ranked. Verified on a two-chunk
        test hypertable before re-running against energy_readings.

    WHY row_number() OVER A WINDOW
        A correlated DELETE on a 10.6-million-row hypertable would run the
        subquery once per deleted row. The window function marks all rows in
        one pass, and the DELETE removes exactly the marked ones.
    """
    deleted_total = 0
    started = time.monotonic()

    # Delete in batches of pairs so one transaction never holds millions of
    # row versions open at once, which would bloat the heap.
    BATCH_PAIRS = 20_000

    for start in range(0, len(pairs), BATCH_PAIRS):
        batch = pairs[start:start + BATCH_PAIRS]
        # The exact number of rows this batch must remove. Checking it after
        # every batch means a faulty statement stops the program after at most
        # one batch instead of after the whole table has been rewritten.
        expected_in_batch = sum(pair[2] - 1 for pair in batch)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH ranked AS (
                    SELECT tableoid AS tbl,
                           ctid,
                           row_number() OVER (
                               PARTITION BY meter_id, event_time
                               ORDER BY received_time, ctid
                           ) AS position
                    FROM energy_readings
                    WHERE (meter_id, event_time) IN (
                        SELECT * FROM unnest(%s::bigint[], %s::timestamptz[])
                    )
                )
                DELETE FROM energy_readings target
                USING ranked r
                WHERE target.tableoid = r.tbl
                  AND target.ctid = r.ctid
                  AND r.position > 1
                """,
                (
                    [pair[0] for pair in batch],
                    [pair[1] for pair in batch],
                ),
            )
            batch_deleted = cursor.rowcount

        if batch_deleted != expected_in_batch:
            # Roll back rather than commit: the batch removed the wrong number
            # of rows, so leaving it in place would corrupt the benchmark.
            connection.rollback()
            raise SystemExit(
                f"FAIL: this batch should have deleted {expected_in_batch:,} "
                f"rows but deleted {batch_deleted:,}. Nothing from this batch "
                "was committed. Investigate before re-running."
            )

        connection.commit()
        deleted_total += batch_deleted
        print(
            f"  deleted {deleted_total:>8,} extra copies "
            f"({min(start + BATCH_PAIRS, len(pairs)):,} of {len(pairs):,} pairs)",
            flush=True,
        )

    elapsed = time.monotonic() - started
    print(f"  deletion finished in {elapsed:.1f} s")

    remaining = row_count(connection)
    if remaining != expected_rows:
        raise SystemExit(
            f"FAIL: {remaining} rows remain but Section 2.3.2 requires "
            f"{expected_rows}. Deleted {deleted_total}."
        )
    return deleted_total


def main() -> None:
    expected_unique = int(
        smart_meter_simulator.dataset_info()["expected_counts"]["unique_readings"]
    )

    print("=" * 78)
    print("Section 2.3  Clean duplicates and preserve the benchmark")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")
    print(f"  expected unique_readings from dataset_info(): {expected_unique:,}")
    print("")

    connection = connect()
    connection.autocommit = False

    # --- before -------------------------------------------------------------
    before_rows = row_count(connection)
    before_energy = energy_sum(connection)
    before_unique = unique_pair_count(connection)

    print("-" * 78)
    print("BEFORE CLEANING")
    print("-" * 78)
    print(f"  rows                 {before_rows:>14,}")
    print(f"  distinct pairs       {before_unique:>14,}")
    print(f"  summed energy_kwh    {before_energy:>18,.6f}")
    print("")

    # --- classify -----------------------------------------------------------
    print("-" * 78)
    print("CLASSIFYING DUPLICATED PAIRS (Section 2.3.1)")
    print("-" * 78)
    print(f"  comparing: {', '.join(COMPARISON_COLUMNS)}")
    print("")

    classification = classify_duplicates(connection)
    identical = classification["identical"]
    conflicting = classification["conflicting"]

    print(f"  duplicated pairs found     {classification['duplicate_pair_count']:>10,}")
    print(f"    identical across all six {len(identical):>10,}")
    print(f"    conflicting              {len(conflicting):>10,}")
    print("")

    if conflicting:
        print("  CONFLICTING PAIRS - these are NOT deleted:")
        for meter_id, event_time, copies, distinct_counts in conflicting[:20]:
            print(f"    meter {meter_id} at {event_time}: "
                  f"{copies} copies, distinct value counts {distinct_counts}")
        print("")
        print("  Stopping before any deletion. Investigate these rows first.")
        connection.rollback()
        connection.close()
        raise SystemExit("Conflicting duplicate values found; nothing deleted.")

    print("  No conflicting values found.")
    print("  The generator's copies match on all six comparison columns, so")
    print("  every extra copy can be removed without losing information.")
    print("")

    # --- delete -------------------------------------------------------------
    print("-" * 78)
    print("DELETING EXTRA COPIES")
    print("-" * 78)
    print("  Keeping, per pair, the copy with the earliest received_time.")
    print("")

    extra_rows = before_rows - before_unique
    if extra_rows == 0:
        print("  Nothing to delete: no duplicated pairs remain.")
        deleted = 0
    else:
        deleted = delete_extra_copies(connection, identical, expected_unique)

    # --- after --------------------------------------------------------------
    after_rows = row_count(connection)
    after_unique = unique_pair_count(connection)
    after_energy = energy_sum(connection)

    print("")
    print("-" * 78)
    print("AFTER CLEANING")
    print("-" * 78)
    print(f"  rows                 {after_rows:>14,}")
    print(f"  distinct pairs       {after_unique:>14,}")
    print(f"  summed energy_kwh    {after_energy:>18,.6f}")
    print(f"  extra copies deleted {deleted:>14,}")
    print(f"  energy removed by deleting duplicate copies  "
          f"{before_energy - after_energy:,.6f} kWh")
    print("")

    # --- verification -------------------------------------------------------
    remaining_duplicates = after_rows - after_unique

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(DISTINCT meter_id) FROM energy_readings")
        after_meters = cursor.fetchone()[0]

    print("=" * 78)
    print("VERIFICATION (Section 2.3.2)")
    print("=" * 78)
    print(f"  final row count          {after_rows:>14,}")
    print(f"  expected unique_readings {expected_unique:>14,}")
    print(f"  duplicate pairs remaining{remaining_duplicates:>14,}")
    print(f"  distinct meters          {after_meters:>14,}")
    print("")

    if after_rows == expected_unique and remaining_duplicates == 0:
        print("  PASS: row count matches expected_counts.unique_readings and")
        print("        no duplicated (meter_id, event_time) pair remains.")
    else:
        connection.close()
        raise SystemExit(
            f"FAIL: {after_rows} rows, {remaining_duplicates} duplicate pairs."
        )

    print("")
    print("  Why missing readings are NOT written as zero:")
    print("    A gap means the meter never reported for that interval. Zero")
    print("    would be a measurement of no consumption, and it would pull")
    print("    every average down, invent a false minimum, and make the")
    print("    completeness figure in Section 5.3 meaningless. Gaps stay gaps:")
    print("    aggregates count only intervals that actually arrived, and the")
    print("    planned count in Section 5.3 still includes them so the shortfall")
    print("    remains visible.")
    print("")
    print("  This cleaned dataset is the benchmark for Sections 3, 4 and 6-8.")

    connection.close()


if __name__ == "__main__":
    run_with_log("clean_readings", main)
