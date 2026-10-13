"""Section 4.1: copy cleaned data into the two compressed tables chunk by chunk.

PURPOSE
    Section 4.1.5 requires loading the cleaned energy_readings rows into
    energy_time_compressed and energy_meter_compressed ONE CHUNK AT A TIME,
    and after a chunk is fully loaded, manually compressing it if its end
    precedes the experiment cutoff (start of this run minus 48 hours).
    Loading and compression are timed SEPARATELY, as 4.1.5 and 4.2.3 ask.

    The chunk grid is the one-day grid already in materialised use by
    energy_readings. Every one of its 29 chunks ends before the cutoff (the
    data is all in September and the run happens in October), so every chunk
    is compressed in both tables. The comparison of "same chunk time ranges
    compressed in both new tables" is therefore exact.

WHY THE SOURCE RANGES DRIVE THE LOOP
    energy_readings already exists with 29 one-day chunks. Loading the same
    ranges into the new tables keeps the three tables on an identical chunk
    grid, which is what lets 4.1.7 verify that the same ranges are
    compressed in both new tables.

INPUTS
    - the two compressed hypertables from sql/08_compression_tables.sql
    - cleaned energy_readings from Section 2.3
    - config.py for the connection

OUTPUTS
    - a per-chunk loading time and a per-chunk compression time for both
      tables
    - the cutoff timestamp (start of run minus 48 hours)
    - a list of compressed chunks per table with their ranges
    - final verification: row counts, distinct meters, date ranges, sums
    - the same report in logs/compressed_load_<CAT timestamp>.txt
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

TARGETS = ["energy_time_compressed", "energy_meter_compressed"]


def plan_source_ranges(connection) -> list[tuple]:
    """Return [(range_start, range_end)] for every energy_readings chunk."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT range_start, range_end
            FROM timescaledb_information.chunks
            WHERE hypertable_name = 'energy_readings'
            ORDER BY range_start
            """
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]


def chunk_state(connection, hypertable: str) -> list[dict]:
    """Return a list of chunk dicts for one hypertable."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_schema, chunk_name, range_start, range_end, is_compressed
            FROM timescaledb_information.chunks
            WHERE hypertable_name = %s
            ORDER BY range_start
            """,
            (hypertable,),
        )
        rows = cursor.fetchall()
        columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def compress_eligible(connection, hypertable: str, cutoff,
                      compression_log: list[dict]) -> None:
    """Manually compress every chunk of hypertable whose end precedes cutoff."""
    chunks = chunk_state(connection, hypertable)
    for chunk in chunks:
        if chunk["is_compressed"]:
            continue
        if chunk["range_end"] <= cutoff:
            fully_qualified = f"{chunk['chunk_schema']}.{chunk['chunk_name']}"
            started = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute("SELECT compress_chunk(%s::regclass)", (fully_qualified,))
            elapsed = (time.perf_counter() - started) * 1000.0
            connection.commit()
            compression_log.append(
                {
                    "hypertable": hypertable,
                    "chunk": fully_qualified,
                    "range_start": chunk["range_start"].isoformat(timespec="seconds"),
                    "range_end": chunk["range_end"].isoformat(timespec="seconds"),
                    "elapsed_ms": round(elapsed, 3),
                }
            )
            print(
                f"      compressed {chunk['range_end'].strftime('%Y-%m-%d %H:%M')} "
                f"chunk {fully_qualified} in {elapsed:.3f} ms",
                flush=True,
            )


def row_count(connection, table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {table}")
        return cursor.fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy cleaned rows into the compressed hypertables chunk by chunk."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE both tables (and drop chunks) before loading.",
    )
    args = parser.parse_args()

    started_at = cat_now()
    cutoff = started_at - time_delta_days(2)

    print("=" * 78)
    print("Section 4.1  Chunk-by-chunk load and compression")
    print(f"Started {cat_text(started_at)} CAT")
    print(f"Machine {machine_identifier()}")
    print(f"Cutoff (start minus 48 h)  {cutoff.isoformat(timespec='seconds')}")
    print("=" * 78)
    print("")

    connection = connect()
    connection.autocommit = False

    if args.reset:
        for table in TARGETS:
            with connection.cursor() as cursor:
                cursor.execute(f"TRUNCATE {table}")
        connection.commit()
        print("  Both tables TRUNCATEd (--reset was given)")
        print("")

    for table in TARGETS:
        existing = row_count(connection, table)
        if existing:
            connection.close()
            raise SystemExit(
                f"{table} already holds {existing:,} rows. Re-run with --reset "
                "to reload from scratch."
            )

    # Chunk-by-chunk load per target; compression timed separately.
    overall_started = time.perf_counter()
    source_ranges = plan_source_ranges(connection)
    print(f"  Source chunk plan: {len(source_ranges)} one-day ranges "
          f"({source_ranges[0][0]} .. {source_ranges[-1][1]})")
    print("")

    all_load_logs: dict[str, list[dict]] = {t: [] for t in TARGETS}
    all_compression_logs: dict[str, list[dict]] = {t: [] for t in TARGETS}

    for table in TARGETS:
        print("-" * 78)
        print(f"LOADING + COMPRESSING {table}")
        print("-" * 78)
        load_started = time.perf_counter()
        for index, (range_start, range_end) in enumerate(source_ranges, 1):
            label = f"{range_start.strftime('%Y-%m-%d %H:%M')}"
            t0 = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {table}
                    SELECT * FROM energy_readings
                    WHERE event_time >= %s AND event_time < %s
                    """,
                    (range_start, range_end),
                )
                inserted = cursor.rowcount
            # One commit per chunk so a failed chunk never half-ships.
            connection.commit()
            load_elapsed = (time.perf_counter() - t0) * 1000.0
            all_load_logs[table].append(
                {
                    "chunk_index": index,
                    "range_start": range_start.isoformat(timespec="seconds"),
                    "range_end": range_end.isoformat(timespec="seconds"),
                    "rows": inserted,
                    "elapsed_ms": round(load_elapsed, 3),
                }
            )
            print(
                f"  chunk {index:>2}/{len(source_ranges)}  {label}  "
                f"{inserted:>9,} rows loaded in {load_elapsed:>10.3f} ms",
                flush=True,
            )
            # Compress this chunk now, separately timed, if it is eligible.
            compress_eligible(connection, table, cutoff, all_compression_logs[table])
        load_total_s = (time.perf_counter() - load_started)
        print(
            f"  TOTAL LOAD TIME for {table}: {load_total_s:.3f} s",
            flush=True,
        )
        print("")

    overall_elapsed = time.perf_counter() - overall_started
    connection.close()

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------
    check = connect()
    print("=" * 78)
    print("VERIFICATION (Section 4.1.7 / 3.1 data checks)")
    print("=" * 78)
    for table in TARGETS:
        with check.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT count(*) AS rows, count(DISTINCT meter_id) AS meters,
                       min(event_time) AS earliest, max(event_time) AS latest,
                       sum(power_kw) AS sp, sum(energy_kwh) AS se
                FROM {table}
                """
            )
            row = cursor.fetchone()
            print(f"  {table}")
            print(f"    rows={row[0]:>12,}  meters={row[1]:>6,}")
            print(f"    earliest={row[2]}  latest={row[3]}")
            print(
                f"    sum power_kw={row[4]:.6f}  sum energy_kwh={row[5]:.6f}"
            )
        chunks = chunk_state(check, table)
        compressed = [c for c in chunks if c["is_compressed"]]
        print(
            f"    chunks: {len(chunks)} total, {len(compressed)} compressed"
        )
        print("")

    # Compare the compressed range sets across the two tables.
    def compressed_ranges(connection, table: str) -> list[tuple]:
        chunks = chunk_state(connection, table)
        return [
            (c["range_start"], c["range_end"])
            for c in chunks
            if c["is_compressed"]
        ]

    time_ranges = compressed_ranges(check, TARGETS[0])
    meter_ranges = compressed_ranges(check, TARGETS[1])
    print(f"  Same compressed ranges in both tables: "
          f"{len(time_ranges)} / {len(meter_ranges)}",
          end=" ")
    print("PASS" if time_ranges == meter_ranges else "FAIL")

    # Compression cost summary (Section 4.2.3).
    print("")
    print("=" * 78)
    print("COMPRESSION COST (sum of measured chunk compression times)")
    print("=" * 78)
    for table in TARGETS:
        total_ms = sum(c["elapsed_ms"] for c in all_compression_logs[table])
        comp_chunks = len(all_compression_logs[table])
        first_compressed = all_compression_logs[table][0]
        last_compressed = all_compression_logs[table][-1]
        print("")
        print(f"  {table}")
        print(f"    chunks compressed        {comp_chunks}")
        print(f"    total compression time   {total_ms:,.3f} ms "
              f"({total_ms / 1000.0:.3f} s)")
        print(f"    time range of compressed chunks: "
              f"{first_compressed['range_start']} .. "
              f"{last_compressed['range_end']}")
    print("")
    print(f"  Overall elapsed for this run (load + compress): "
          f"{overall_elapsed:.3f} s")

    check.close()


def time_delta_days(days: float):
    from datetime import timedelta

    return timedelta(days=days)


if __name__ == "__main__":
    run_with_log("compressed_load", main)