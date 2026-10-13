"""Section 3.2: time the five SQL workloads on the three chunk configurations.

PURPOSE
    Run Q1 to Q5 against energy_readings (one day), energy_readings_3h
    (three hours) and energy_readings_week (one week), one warm-up followed by
    five measured executions per query and table, and report median, minimum
    and maximum durations in milliseconds together with the CAT start and end
    of every run.

MEASUREMENT RULES THE ASSIGNMENT LAYS DOWN (3.2.2 - 3.2.4)
    * One machine and one named client: every statement is sent on a single
      connection opened with application_name 'smart-energy-grid', so
      pg_stat_activity and EXPLAIN name the same client for every run.
    * Settings are never changed between configurations. The script does not
      issue any SET statement at all; the only session setting applied is the
      Africa/Kigali time zone from common.db.connect().
    * Runs are sequential. There is no concurrency in this program.
    * Statistics are current: ANALYZE runs once at the start, not between
      configurations.
    * Warm cache: the warm-up precedes the timed runs, PostgreSQL is not
      restarted and no cache is cleared between them. Results are labelled
      warm-cache in the report.
    * The clock starts when the statement is sent (execute()) and stops when
      the LAST row has been received (fetchall() returns), so client-side
      result handling is inside the measurement for every configuration
      equally.

WHY THE SAME TIMER FOR EVERY RUN
    psycopg2's cursor.execute() sends the statement, and fetchall() returns
    when the final row has arrived over the wire. Timing that pair measures
    submission to last row, which is what Section 3.2.3 asks for, and it is
    identical code for all three tables, so any difference between them comes
    from the server, not from the stopwatch.

INPUTS
    - the three hypertables from Section 3.1
    - config.py

OUTPUTS
    - one row per measured execution in benchmarks/chunk_timings.csv
    - a median/minimum/maximum summary printed and saved to
      logs/chunk_benchmark_<CAT timestamp>.txt
    - session seconds from the first warm-up submission to the last measured
      result, printed with the summary

HOW TO RUN
    From the project root:

        python benchmarks\\run_chunk_benchmarks.py

    Re-running appends a fresh run_id rather than overwriting earlier results.
"""

import csv
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text, CAT  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

TABLES = [
    ("energy_readings", "1 day"),
    ("energy_readings_3h", "3 hours"),
    ("energy_readings_week", "1 week"),
]

# Warm-up plus five measured executions, as Section 3.2.3 requires.
WARMUPS = 1
MEASURED_RUNS = 5

# --------------------------------------------------------------------------
# The five workloads. Each takes the source table as its only variable.
# --------------------------------------------------------------------------
QUERIES = {
    "Q1": """
        -- Q1: average power_kw per CAT hour on 21 September, all meters.
        -- CAT day boundaries come from the session time zone (Africa/Kigali),
        -- so the date literal needs no offset conversion.
        SELECT time_bucket(INTERVAL '1 hour', event_time) AS hour_start,
               avg(power_kw) AS average_power_kw
        FROM {table}
        WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02'
          AND event_time <  TIMESTAMPTZ '2026-09-22 00:00:00+02'
        GROUP BY hour_start
        ORDER BY hour_start
    """,
    "Q2": """
        -- Q2: the ten heaviest 15-minute intervals, 22 to 28 September.
        -- Ties are resolved by event_time ascending, and ORDER BY ... LIMIT
        -- keeps exactly ten rows even when a tie crosses tenth place.
        SELECT event_time, sum(power_kw) AS total_power_kw
        FROM {table}
        WHERE event_time >= TIMESTAMPTZ '2026-09-22 00:00:00+02'
          AND event_time <  TIMESTAMPTZ '2026-09-29 00:00:00+02'
        GROUP BY event_time
        ORDER BY total_power_kw DESC, event_time ASC
        LIMIT 10
    """,
    "Q3": """
        -- Q3: total energy per meter over the whole period.
        SELECT meter_id, sum(energy_kwh) AS total_energy_kwh
        FROM {table}
        GROUP BY meter_id
        ORDER BY meter_id
    """,
    "Q4": """
        -- Q4: energy, average power and peak power for one meter, 22-28 Sep.
        SELECT sum(energy_kwh)  AS total_energy_kwh,
               avg(power_kw)    AS average_power_kw,
               max(power_kw)    AS peak_power_kw
        FROM {table}
        WHERE meter_id = 1000000000
          AND event_time >= TIMESTAMPTZ '2026-09-22 00:00:00+02'
          AND event_time <  TIMESTAMPTZ '2026-09-29 00:00:00+02'
    """,
    "Q5": """
        -- Q5: full scan reporting row count, total energy and power
        -- average, minimum and maximum.
        SELECT count(*)          AS row_count,
               sum(energy_kwh)   AS total_energy_kwh,
               avg(power_kw)     AS average_power_kw,
               min(power_kw)     AS minimum_power_kw,
               max(power_kw)     AS maximum_power_kw
        FROM {table}
    """,
}


def run_once(cursor, sql: str) -> tuple[float, int]:
    """Execute sql and return (elapsed_ms, row_count).

    The timer brackets execute() and fetchall(), so it spans statement
    submission through arrival of the last row.
    """
    started = time.perf_counter()
    cursor.execute(sql)
    rows = cursor.fetchall()
    finished = time.perf_counter()
    return (finished - started) * 1000.0, len(rows)


def compare_results(expected: dict, actual: dict, tolerance: float) -> list[str]:
    """Return a list of human-readable mismatches between two result sets.

    Sections 3.1.3 and 3.2.1 require matching results across configurations
    with at most 0.001 of numeric rounding difference. Rows are matched by
    their key columns (everything except the measured aggregates), so a
    different physical order is not reported as a difference.
    """
    problems: list[str] = []

    if len(expected) != len(actual):
        return [
            f"row count differs: {len(expected)} vs {len(actual)}"
        ]

    for index, (left, right) in enumerate(zip(expected, actual)):
        if len(left) != len(right):
            problems.append(f"row {index}: column count differs")
            continue
        for position, (a, b) in enumerate(zip(left, right)):
            if isinstance(a, float) or isinstance(b, float):
                if a is None or b is None:
                    if a != b:
                        problems.append(f"row {index} col {position}: {a!r} vs {b!r}")
                    continue
                difference = abs(float(a) - float(b))
                if difference > tolerance:
                    problems.append(
                        f"row {index} col {position}: difference {difference:.6f} "
                        f"exceeds {tolerance}"
                    )
            elif a != b:
                problems.append(f"row {index} col {position}: {a!r} vs {b!r}")
    return problems


def main() -> None:
    run_id = cat_now().strftime("%Y-%m-%d_%H-%M-%S")
    machine = machine_identifier()

    print("=" * 78)
    print("Section 3.2  Chunk-interval timing comparison")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine}")
    print(f"Run id  {run_id}")
    print("=" * 78)
    print("")
    print("  Client          psycopg2 via benchmarks/run_chunk_benchmarks.py")
    print("  Timing tool     time.perf_counter() (monotonic, nanosecond clock)")
    print("  Timer bracket   cursor.execute() to fetchall() of the last row")
    print(f"  Per query/table {WARMUPS} warm-up + {MEASURED_RUNS} measured runs")
    print("  Cache label     WARM CACHE (warm-up precedes timing, no restart)")
    print("  Settings        unchanged; no SET statements are issued")
    print("")

    connection = connect(application_name="smart-energy-grid")
    connection.autocommit = True
    cursor = connection.cursor()

    # Section 3.2.1: current statistics before the first measured run.
    print("Updating table statistics with ANALYZE")
    for table_name, _ in TABLES:
        cursor.execute(f"ANALYZE {table_name}")
        print(f"  ANALYZE {table_name}")
    print("")

    # Correctness first: results must match before timing means anything.
    print("=" * 78)
    print("RESULT EQUIVALENCE CHECK (before timing)")
    print("=" * 78)
    reference_results: dict[str, list] = {}
    equivalence_ok = True
    for query_id, template in QUERIES.items():
        cursor.execute(template.format(table="energy_readings"))
        reference_results[query_id] = cursor.fetchall()
        for table_name, _ in TABLES[1:]:
            cursor.execute(template.format(table=table_name))
            problems = compare_results(
                reference_results[query_id], cursor.fetchall(), 0.001
            )
            if problems:
                equivalence_ok = False
                print(f"  {query_id} on {table_name}: {len(problems)} difference(s)")
                for problem in problems[:5]:
                    print(f"      {problem}")
            else:
                print(f"  {query_id} on {table_name}: matches energy_readings")
    print("")
    if not equivalence_ok:
        raise SystemExit(
            "Results differ between configurations by more than 0.001. "
            "Timing would be meaningless; fix the data first."
        )
    print("  All five queries return matching results on all three tables")
    print("  (numeric tolerance 0.001).")
    print("")

    # --- timing ------------------------------------------------------------
    print("=" * 78)
    print("MEASURED RUNS")
    print("=" * 78)

    records: list[dict] = []
    session_started_at: datetime | None = None
    session_finished_at: datetime | None = None

    csv_path = Path(PROJECT_ROOT) / "benchmarks" / "chunk_timings.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "run_id", "query_id", "table_name", "chunk_interval",
                "phase", "run_number", "duration_ms", "row_count",
                "cat_start", "cat_end", "machine",
            ],
        )
        if write_header:
            writer.writeheader()

        for query_id, template in QUERIES.items():
            print("")
            print(f"  {query_id}")
            for table_name, chunk_interval in TABLES:
                sql = template.format(table=table_name)

                for phase, count in (("warmup", WARMUPS),
                                     ("measured", MEASURED_RUNS)):
                    for number in range(1, count + 1):
                        start_cat = cat_now()
                        if session_started_at is None:
                            session_started_at = start_cat
                        duration_ms, row_count = run_once(cursor, sql)
                        end_cat = cat_now()
                        session_finished_at = end_cat

                        record = {
                            "run_id": run_id,
                            "query_id": query_id,
                            "table_name": table_name,
                            "chunk_interval": chunk_interval,
                            "phase": phase,
                            "run_number": number,
                            "duration_ms": f"{duration_ms:.3f}",
                            "row_count": row_count,
                            "cat_start": start_cat.isoformat(timespec="milliseconds"),
                            "cat_end": end_cat.isoformat(timespec="milliseconds"),
                            "machine": machine,
                        }
                        writer.writerow(record)
                        csv_file.flush()

                        if phase == "measured":
                            records.append(
                                {
                                    "query_id": query_id,
                                    "table_name": table_name,
                                    "duration_ms": duration_ms,
                                    "row_count": row_count,
                                    "cat_start": start_cat,
                                    "cat_end": end_cat,
                                }
                            )
                            print(
                                f"    {chunk_interval:<9} run {number} "
                                f"{duration_ms:>10.3f} ms  "
                                f"rows={row_count:<8} "
                                f"{start_cat.strftime('%H:%M:%S.%f')[:-3]} -> "
                                f"{end_cat.strftime('%H:%M:%S.%f')[:-3]}"
                            )
                        else:
                            print(
                                f"    {chunk_interval:<9} warm-up "
                                f"{duration_ms:>10.3f} ms  (not timed)"
                            )

    cursor.close()
    connection.close()

    # --- summary -----------------------------------------------------------
    print("")
    print("=" * 78)
    print("SUMMARY  (milliseconds, warm-cache, median of "
          f"{MEASURED_RUNS} measured runs)")
    print("=" * 78)
    header = (f"  {'Query':<6}{'Configuration':<22}"
              f"{'Median':>12}{'Min':>12}{'Max':>12}{'Rows':>10}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    summary_rows = []
    for query_id in QUERIES:
        for table_name, chunk_interval in TABLES:
            durations = [
                record["duration_ms"]
                for record in records
                if record["query_id"] == query_id
                and record["table_name"] == table_name
            ]
            row_count = next(
                record["row_count"]
                for record in records
                if record["query_id"] == query_id
                and record["table_name"] == table_name
            )
            median = statistics.median(durations)
            low = min(durations)
            high = max(durations)
            label = f"{table_name} ({chunk_interval})"
            print(f"  {query_id:<6}{label:<22}"
                  f"{median:>12.3f}{low:>12.3f}{high:>12.3f}{row_count:>10}")
            summary_rows.append(
                {
                    "query_id": query_id,
                    "table_name": table_name,
                    "chunk_interval": chunk_interval,
                    "median_ms": round(median, 3),
                    "min_ms": round(low, 3),
                    "max_ms": round(high, 3),
                    "row_count": row_count,
                }
            )
        # Fastest configuration for this workload, named explicitly.
        fastest = min(
            summary_rows,
            key=lambda row: row["median_ms"]
            if row["query_id"] == query_id else float("inf"),
        )
        print(f"         -> fastest for {query_id}: "
              f"{fastest['table_name']} ({fastest['chunk_interval']}) at "
              f"{fastest['median_ms']:.3f} ms")
        print("")

    # --- session seconds ---------------------------------------------------
    if session_started_at and session_finished_at:
        session_seconds = (
            session_finished_at - session_started_at
        ).total_seconds()
        print("=" * 78)
        print("SESSION TIMING")
        print("=" * 78)
        print(f"  first warm-up submitted   {session_started_at.isoformat(timespec='milliseconds')}")
        print(f"  last measured result      {session_finished_at.isoformat(timespec='milliseconds')}")
        print(f"  session seconds           {session_seconds:.3f}")
        print(f"  machine identifier        {machine}")
        print(f"  client / timing tool      smart-energy-grid / time.perf_counter()")

    print("")
    print(f"  Per-run records appended to {csv_path}")
    print("  Label these results WARM CACHE in the report.")


if __name__ == "__main__":
    run_with_log("chunk_benchmark", main)
