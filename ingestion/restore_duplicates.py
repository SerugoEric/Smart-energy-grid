"""Restore the duplicate copies so Section 2.2 can be measured before cleaning.

PURPOSE
    Assignment 2.2.1 says "Query energy_readings before cleaning." That state no
    longer exists: ingestion/load_readings.py committed 10,696,848 rows and
    ingestion/clean_readings.py then deleted the 53,113 duplicate copies, so
    energy_readings now holds 10,643,735 unique rows and a pre-cleaning query
    would report zero duplicates.

    This program puts the identical copies back. It does not invent anything:
    it replays the unchanged smart_meter_simulator.iter_readings() stream, which
    yields record.copy() a second time immediately after the original whenever
    the duplicate flag fires (smart_meter_simulator.py lines 188-190), and keeps
    only that second copy. The copies inserted here are byte-identical to the
    ones cleaned_readings.py removed, so the restored table is exactly the state
    Section 2.1.2 left behind.

    After sql/05_data_quality.sql has been run against the restored table,
    ingestion/clean_readings.py is run again to return the table to its cleaned
    state. Nothing else in the project depends on the intermediate state: the
    refresh policies only cover the last three days (October), which contain no
    readings, and the compression policies act on energy_time_compressed and
    energy_meter_compressed, not on energy_readings.

INPUTS
    - smart_meter_simulator.dataset_info() and iter_readings()  (unchanged)
    - energy_readings already holding the 10,643,735 cleaned rows
    - config.py for the database connection

OUTPUTS
    - 53,113 byte-identical duplicate rows added back to energy_readings
    - a printed verification block: total rows, distinct pairs, energy sum
    - the same report in logs/restore_duplicates_<CAT timestamp>.txt

HOW TO RUN
    From the project root:

        python ingestion\\restore_duplicates.py

    Re-run safety: the program refuses to start when the duplicates are already
    present, so running it twice cannot insert 106,226 copies.
"""

import io
import sys
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import smart_meter_simulator  # noqa: E402 - the supplied file, imported unchanged

from common.cat_time import cat_text  # noqa: E402
from common.db import connect  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402
from load_readings import (  # noqa: E402 - the CSV format must stay identical
    COPY_STATEMENT,
    format_row,
)

# Rows per COPY batch. Same size as load_readings.py so the restored rows are
# written in the same shape the original load used.
BATCH_SIZE = 100_000

# How often to print progress, in source rows examined.
PROGRESS_EVERY = 2_000_000


def collect_copies() -> tuple[list[dict], int, int]:
    """Replay the stream and return (duplicate copies, examined, emitted).

    A duplicate is recognised as a reading whose (meter_id, event_time) pair is
    the same as the reading yielded immediately before it. That is exactly what
    smart_meter_simulator.py produces: the original is yielded, then the copy.
    Checking only the previous row keeps memory at one dictionary instead of a
    table of all 10.6 million pairs.
    """
    copies: list[dict] = []
    examined = 0
    emitted = 0
    previous_pair: tuple | None = None
    next_report = PROGRESS_EVERY
    started = time.monotonic()

    for reading in smart_meter_simulator.iter_readings():
        emitted += 1
        pair = (reading["meter_id"], reading["event_time"])
        if pair == previous_pair:
            copies.append(reading)
        previous_pair = pair
        examined += 1

        if examined >= next_report:
            elapsed = time.monotonic() - started
            rate = examined / elapsed if elapsed else 0
            print(
                f"  {examined:>12,} dictionaries examined   "
                f"{len(copies):>7,} copies found   "
                f"{elapsed:>7.1f} s   {rate:>8,.0f} rows/s",
                flush=True,
            )
            next_report += PROGRESS_EVERY

    return copies, examined, emitted


def run_restore() -> None:
    info = smart_meter_simulator.dataset_info()
    expected = info["expected_counts"]

    print("=" * 78)
    print("Section 2.2.1  Restore the duplicate copies for a pre-cleaning query")
    print(f"Started {cat_text()} CAT")
    print("=" * 78)
    print("")
    print("  Reason: the table was cleaned on 2026-10-06, but assignment 2.2.1")
    print("  asks for energy_readings BEFORE cleaning. The unchanged generator")
    print("  is replayed and only the second copy of each duplicated pair is")
    print("  re-inserted, which reproduces the pre-cleaning state exactly.")
    print("")

    connection = connect()
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM energy_readings")
        rows_before = cursor.fetchone()[0]
    connection.close()

    expected_emitted = expected["emitted_readings"]
    expected_unique = expected["unique_readings"]
    expected_duplicates = expected["duplicate_readings"]

    print(f"  energy_readings currently holds {rows_before:,} rows")
    if rows_before == expected_emitted:
        raise SystemExit(
            "The duplicate copies are already present, so there is nothing to "
            "restore.\nRun ingestion/clean_readings.py first if you want to "
            "start over from the cleaned state."
        )
    if rows_before != expected_unique:
        raise SystemExit(
            f"energy_readings holds {rows_before:,} rows, which is neither the "
            f"cleaned count ({expected_unique:,}) nor the emitted count "
            f"({expected_emitted:,}).\nRefusing to continue."
        )
    print("")

    print("  Replaying smart_meter_simulator.iter_readings() ...", flush=True)
    copies, examined, emitted = collect_copies()
    print("")
    print(f"  dictionaries examined       {examined:>12,}")
    print(f"  emitted_readings (expected) {emitted:>12,}")
    print(f"  duplicate copies found      {len(copies):>12,}")
    print(f"  unique pairs found          {examined - len(copies):>12,}")
    print("")

    if emitted != expected_emitted or len(copies) != expected_duplicates:
        raise SystemExit(
            "FAIL: the replay did not reproduce dataset_info().\n"
            f"  examined  {examined:,} vs emitted_readings {expected_emitted:,}\n"
            f"  copies    {len(copies):,} vs duplicate_readings {expected_duplicates:,}\n"
            "Nothing was written to the database."
        )
    print("  PASS: examined rows and copy count both match dataset_info().")
    print("")

    connection = connect()
    cursor = connection.cursor()
    buffer: list[str] = []
    copied_rows = 0
    started = time.monotonic()

    try:
        for reading in copies:
            buffer.append(format_row(reading))
            if len(buffer) >= BATCH_SIZE:
                cursor.copy_expert(COPY_STATEMENT, io.StringIO("\n".join(buffer)))
                copied_rows += len(buffer)
                buffer.clear()

        if buffer:
            cursor.copy_expert(COPY_STATEMENT, io.StringIO("\n".join(buffer)))
            copied_rows += len(buffer)
            buffer.clear()

        connection.commit()
        finished = time.monotonic()
    except BaseException:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

    print(f"  rows restored               {copied_rows:>12,}")
    print(f"  insert seconds              {finished - started:>12.1f}")
    print("")

    # --- verification ------------------------------------------------------
    check = connect()
    with check.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM energy_readings")
        total_rows = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT count(*)
              FROM (SELECT DISTINCT meter_id, event_time FROM energy_readings) AS pairs
            """
        )
        distinct_pairs = cursor.fetchone()[0]
        cursor.execute("SELECT sum(energy_kwh) FROM energy_readings")
        energy_sum = float(cursor.fetchone()[0])
        cursor.execute("SELECT count(DISTINCT meter_id) FROM energy_readings")
        meter_count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT count(*) FROM timescaledb_information.chunks "
            "WHERE hypertable_name = 'energy_readings'"
        )
        chunk_count = cursor.fetchone()[0]
    check.close()

    print("=" * 78)
    print("VERIFICATION")
    print("=" * 78)
    print(f"  energy_readings rows        {total_rows:>14,}")
    print(f"  expected emitted_readings   {expected_emitted:>14,}")
    print(f"  distinct (meter, event)     {distinct_pairs:>14,}")
    print(f"  expected unique_readings    {expected_unique:>14,}")
    print(f"  extra copies now present    {total_rows - distinct_pairs:>14,}")
    print(f"  expected duplicate_readings {expected_duplicates:>14,}")
    print(f"  distinct meters             {meter_count:>14,}")
    print(f"  chunks                      {chunk_count:>14,}")
    print(f"  sum(energy_kwh)             {energy_sum:>14.6f}")
    print("")

    # The cleaning log recorded 3,872,863.893179 kWh before the copies were
    # removed, so the restored sum must land back on that figure.
    reference_energy = 3_872_863.893179
    energy_diff = abs(energy_sum - reference_energy)

    checks = [
        ("rows equal emitted_readings", total_rows == expected_emitted),
        ("distinct pairs equal unique_readings", distinct_pairs == expected_unique),
        ("extra copies equal duplicate_readings",
         total_rows - distinct_pairs == expected_duplicates),
        ("meters equal 4,000", meter_count == 4000),
        ("energy sum matches the pre-cleaning value", energy_diff < 0.001),
    ]
    for label, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}: {label}")

    print("")
    if not all(passed for _, passed in checks):
        raise SystemExit("Restored table did not verify. Stop and investigate.")

    print("  energy_readings is now in its pre-cleaning state.")
    print("  Run sql/05_data_quality.sql next, then")
    print("  python ingestion\\clean_readings.py to return to the cleaned state.")


def main() -> None:
    run_restore()


if __name__ == "__main__":
    run_with_log("restore_duplicates", main)
