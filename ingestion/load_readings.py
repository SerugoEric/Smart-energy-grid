"""Section 2.1: capture the complete stream and load it into energy_readings.

PURPOSE
    Consume the whole of smart_meter_simulator.iter_readings() — 10,696,848
    dictionaries expected — and load every row, duplicates included, into the
    empty energy_readings hypertable. The pilot rows stay untouched in
    energy_live.

WHY THE DIRECT-DATABASE ROUTE RATHER THAN CSV
    The assignment offers three routes: CSV for bulk loading, MQTT, or a direct
    database writer. This program takes the third. A 10.7-million-row CSV would
    be about 1.5 GB on disk and would then have to be read back for a COPY,
    doubling the I/O for no benefit, and this machine has 22 GB free. Writing
    straight to PostgreSQL keeps one pass over the data, and the COPY protocol
    is still used inside each batch, so rows travel to the server in the same
    compact binary-ish text form a bulk load would use.

    Section 2.1.4 asks for total elapsed seconds from starting generation to
    committing the final row, and load seconds from the first database write to
    the final commit. Both are measured below. On this route generation and
    loading overlap by design, so load seconds is a subset of total seconds.

INPUTS
    - smart_meter_simulator.dataset_info() and iter_readings()  (unchanged)
    - the empty energy_readings hypertable from sql/01_schema.sql
    - config.py for the database connection

OUTPUTS
    - every emitted row in energy_readings, including duplicate copies
    - progress lines every BATCH_SIZE rows
    - a final verification block: row count, distinct meters, earliest and
      latest event_time, comparison against expected_counts.emitted_readings
    - the same report in logs/readings_load_<CAT timestamp>.txt

HOW TO RUN
    From the project root, with energy_readings empty:

        python ingestion\\load_readings.py

    Re-run safety: the program refuses to start when energy_readings already
    holds rows, because a second pass would double every reading. Use --reset
    to TRUNCATE first.
"""

import argparse
import io
import sys
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

import smart_meter_simulator  # noqa: E402 - the supplied file, imported unchanged

from common.cat_time import cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

# Rows per COPY batch. 100,000 rows is roughly 12 MB of text: large enough that
# the per-batch overhead disappears, small enough that progress prints often
# and a failed batch costs little work.
BATCH_SIZE = 100_000

# How often to print progress, in rows.
PROGRESS_EVERY = 500_000

COLUMNS = [
    "meter_id",
    "event_time",
    "received_time",
    "power_kw",
    "voltage_v",
    "current_a",
    "frequency_hz",
    "energy_kwh",
]

COPY_STATEMENT = "COPY energy_readings ({}) FROM STDIN WITH (FORMAT csv)".format(
    ", ".join(COLUMNS)
)

# Floats are written with repr() so the value round-trips exactly. str() would
# be shorter but can lose the last digit on some values, and Section 3.1.3
# allows only 0.001 of difference in the sums.
def format_row(reading: dict) -> str:
    """Return one CSV line for a reading dictionary."""
    return (
        f"{reading['meter_id']},"
        f"{reading['event_time']},"
        f"{reading['received_time']},"
        f"{reading['power_kw']!r},"
        f"{reading['voltage_v']!r},"
        f"{reading['current_a']!r},"
        f"{reading['frequency_hz']!r},"
        f"{reading['energy_kwh']!r}"
    )


def current_row_count(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM energy_readings")
        return cursor.fetchone()[0]


def run_load(reset: bool) -> None:
    """Generate and load the complete dataset, then verify it."""
    info = smart_meter_simulator.dataset_info()
    expected = info["expected_counts"]
    planned = info["planned_readings"]

    print("=" * 78)
    print("Section 2.1  Capture and load the complete stream")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")
    print("  Route: direct database writer (COPY batches, no CSV file)")
    print("")
    print("  dataset_info() declares:")
    print(f"    planned_readings      {planned:>12,}")
    print(f"    emitted_readings      {expected['emitted_readings']:>12,}")
    print(f"    unique_readings       {expected['unique_readings']:>12,}")
    print(f"    duplicate_readings    {expected['duplicate_readings']:>12,}")
    print(f"    delayed_unique        {expected['delayed_unique_readings']:>12,}")
    print(f"    missing_readings      {expected['missing_readings']:>12,}")
    print("")

    connection = connect()
    existing = current_row_count(connection)
    print(f"  energy_readings currently holds {existing:,} rows")
    if existing:
        if not reset:
            connection.close()
            raise SystemExit(
                "energy_readings is not empty. A second load would duplicate "
                "every reading.\n"
                "Run with --reset to TRUNCATE it first."
            )
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE energy_readings")
        connection.commit()
        print("  TRUNCATEd because --reset was given")
    print("")

    # One transaction for the whole load: connect() already opens with
    # autocommit off, and a single commit at the end is what Section 2.1.4
    # means by "committing the final row". It also avoids paying for 107
    # commit fsyncs.
    cursor = connection.cursor()

    generated = 0
    copied_rows = 0
    buffer: list[str] = []
    first_write_at: float | None = None

    generation_started = time.monotonic()
    next_report = PROGRESS_EVERY

    try:
        for reading in smart_meter_simulator.iter_readings():
            buffer.append(format_row(reading))
            generated += 1

            if len(buffer) >= BATCH_SIZE:
                if first_write_at is None:
                    first_write_at = time.monotonic()
                cursor.copy_expert(COPY_STATEMENT,
                                   io.StringIO("\n".join(buffer)))
                copied_rows += len(buffer)
                buffer.clear()

            if generated >= next_report:
                elapsed = time.monotonic() - generation_started
                rate = generated / elapsed if elapsed else 0
                print(
                    f"  {generated:>12,} dictionaries   "
                    f"{copied_rows:>12,} rows copied   "
                    f"{elapsed:>8.1f} s   {rate:>8.0f} rows/s",
                    flush=True,
                )
                next_report += PROGRESS_EVERY

        if buffer:
            if first_write_at is None:
                first_write_at = time.monotonic()
            cursor.copy_expert(COPY_STATEMENT, io.StringIO("\n".join(buffer)))
            copied_rows += len(buffer)
            buffer.clear()

        connection.commit()
        final_commit_at = time.monotonic()
    except BaseException:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

    total_seconds = final_commit_at - generation_started
    load_seconds = final_commit_at - first_write_at if first_write_at else 0.0

    print("")
    print(f"  generation + load finished at {cat_text()} CAT")
    print(f"  dictionaries consumed         {generated:,}")
    print(f"  rows copied                   {copied_rows:,}")
    print(f"  total elapsed seconds         {total_seconds:.1f}")
    print(f"  load seconds (first write to final commit) {load_seconds:.1f}")
    print("")

    # --- verification ------------------------------------------------------
    check = connect()
    with check.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM energy_readings")
        row_count = cursor.fetchone()[0]
        cursor.execute("SELECT count(DISTINCT meter_id) FROM energy_readings")
        meter_count = cursor.fetchone()[0]
        cursor.execute("SELECT min(event_time), max(event_time) FROM energy_readings")
        first_event, last_event = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM energy_live")
        live_rows = cursor.fetchone()[0]
    check.close()

    expected_emitted = expected["emitted_readings"]

    print("=" * 78)
    print("DATABASE CHECKS")
    print("=" * 78)
    print(f"  energy_readings row count    {row_count:>12,}")
    print(f"  expected emitted_readings    {expected_emitted:>12,}")
    print(f"  dictionaries consumed        {generated:>12,}")
    print(f"  CSV data rows                {'n/a (direct route)':>12}")
    print(f"  distinct meters              {meter_count:>12,}")
    print(f"  earliest event_time          {first_event}")
    print(f"  latest    event_time         {last_event}")
    print(f"  energy_live rows (pilot)     {live_rows:>12,}  (left untouched)")
    print("")

    agree = row_count == expected_emitted == generated
    if agree and meter_count == 4000:
        print("  PASS: dictionaries, committed rows and expected emitted "
              "readings all agree.")
    else:
        print("  FAIL: the three counts do not agree. Difference sizes:")
        print(f"    expected - dictionaries = {expected_emitted - generated:,}")
        print(f"    expected - rows         = {expected_emitted - row_count:,}")
        print(f"    dictionaries - rows     = {generated - row_count:,}")

    # Chunk and size summary, useful for Section 3.1 later.
    check = connect()
    with check.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*) FROM timescaledb_information.chunks
            WHERE hypertable_name = 'energy_readings'
            """
        )
        chunk_count = cursor.fetchone()[0]
        # Sizes are summed over the CHUNK relations, not read from the
        # hypertable's root table. A TimescaleDB hypertable keeps no rows in
        # its root relation, so pg_relation_size('energy_readings') reports
        # "0 bytes" no matter how much data exists. timescaledb_information
        # .chunks gives the real chunk relations to measure.
        cursor.execute(
            """
            SELECT pg_size_pretty(sum(pg_total_relation_size(
                       format('%I.%I', chunk_schema, chunk_name)::regclass))),
                   pg_size_pretty(sum(pg_relation_size(
                       format('%I.%I', chunk_schema, chunk_name)::regclass))),
                   pg_size_pretty(sum(pg_indexes_size(
                       format('%I.%I', chunk_schema, chunk_name)::regclass)))
            FROM timescaledb_information.chunks
            WHERE hypertable_name = 'energy_readings'
            """
        )
        total_size, data_size, index_size = cursor.fetchone()
    check.close()

    print("")
    print(f"  chunks                       {chunk_count}")
    print(f"  table data size              {data_size}")
    print(f"  index size                   {index_size}")
    print(f"  total including chunks       {total_size}")
    print("")
    print("  Sizes are summed over chunk relations: a hypertable's root")
    print("  table is empty, so pg_total_relation_size('energy_readings')")
    print("  alone would report 0 bytes.")
    print("")
    print("  Confirm with:")
    print('    docker exec -it timescaledb psql -U auca -d smart_energy_grid \\')
    print('      -c "SELECT count(*) FROM energy_readings;"')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture the full generator stream into energy_readings."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE energy_readings before loading.",
    )
    arguments = parser.parse_args()
    run_load(reset=arguments.reset)


if __name__ == "__main__":
    run_with_log("readings_load", main)

