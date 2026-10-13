"""Section 4.3: time Q1-Q5 against the two compressed configurations.

PURPOSE
    Re-run the five Section 3 workloads (same queries, same time
    parameters) against the two compressed tables created in 4.1:
        energy_time_compressed   (one-day chunks, order by event_time DESC)
        energy_meter_compressed  (one-day chunks, order by event_time DESC,
                                  segment by meter_id)
    with the same client, the same warm-up + five-runs protocol and the same
    warm-cache conditions as Section 3.2, so the compressed numbers sit on
    exactly the same footing as the 3.2 table and 4.3.2 can compute
    per-query improvement against the energy_readings baseline.

MEASUREMENT RULES (inherited from 3.2.2 - 3.2.4)
    * One machine, one named client (application_name 'smart-energy-grid'),
      sequential runs, no SET statements, one ANALYZE pass before timing,
      warm cache (warm-up first, no restart in between).
    * The timer brackets cursor.execute() + fetchall() exactly as 3.2 did.
    * The compression policies were already paused in sql/08 and are NOT
      resumed here; measurement happens with no background compression, and
      Section 4.4.3 resumes the policies after the timeline is complete.

EQUIVALENCE
    Before timing, every query's result on each compressed table is compared
    with the uncompressed energy_readings result (same one-day chunk grid,
    same rows) at numeric tolerance 0.001. Any mismatch stops the run, since
    timing different data would be meaningless.

INPUTS
    - the two fully compressed hypertables from Section 4.1
    - energy_readings (uncompressed baseline) for the equivalence check
    - config.py

OUTPUTS
    - benchmarks/compressed_timings.csv  one row per measured execution
    - logs/compressed_benchmark_<CAT timestamp>.txt
      median/min/max summary plus session seconds
    - logs/explain_compressed.txt when --plans is given
      EXPLAIN (ANALYZE, BUFFERS) of Q1, Q2 and Q4 on both compressed tables,
      captured AFTER the timed runs so timing is not polluted

HOW TO RUN
    From the project root:

        python benchmarks\\run_compressed_benchmarks.py [--plans]
"""

import argparse
import csv
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

BASELINE = "energy_readings"
TABLES = [
    ("energy_time_compressed", "compress orderby time"),
    ("energy_meter_compressed", "compress segment meter"),
]

WARMUPS = 1
MEASURED_RUNS = 5

# The five workloads are byte-for-byte identical to Section 3.2.
QUERIES = {
    "Q1": """
        SELECT time_bucket(INTERVAL '1 hour', event_time) AS hour_start,
               avg(power_kw) AS average_power_kw
        FROM {table}
        WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02'
          AND event_time <  TIMESTAMPTZ '2026-09-22 00:00:00+02'
        GROUP BY hour_start
        ORDER BY hour_start
    """,
    "Q2": """
        SELECT event_time, sum(power_kw) AS total_power_kw
        FROM {table}
        WHERE event_time >= TIMESTAMPTZ '2026-09-22 00:00:00+02'
          AND event_time <  TIMESTAMPTZ '2026-09-29 00:00:00+02'
        GROUP BY event_time
        ORDER BY total_power_kw DESC, event_time ASC
        LIMIT 10
    """,
    "Q3": """
        SELECT meter_id, sum(energy_kwh) AS total_energy_kwh
        FROM {table}
        GROUP BY meter_id
        ORDER BY meter_id
    """,
    "Q4": """
        SELECT sum(energy_kwh)  AS total_energy_kwh,
               avg(power_kw)    AS average_power_kw,
               max(power_kw)    AS peak_power_kw
        FROM {table}
        WHERE meter_id = 1000000000
          AND event_time >= TIMESTAMPTZ '2026-09-22 00:00:00+02'
          AND event_time <  TIMESTAMPTZ '2026-09-29 00:00:00+02'
    """,
    "Q5": """
        SELECT count(*)          AS row_count,
               sum(energy_kwh)   AS total_energy_kwh,
               avg(power_kw)     AS average_power_kw,
               min(power_kw)     AS minimum_power_kw,
               max(power_kw)     AS maximum_power_kw
        FROM {table}
    """,
}


def run_once(cursor, sql: str) -> tuple[float, int]:
    started = time.perf_counter()
    cursor.execute(sql)
    rows = cursor.fetchall()
    finished = time.perf_counter()
    return (finished - started) * 1000.0, len(rows)


def compare_results(expected: list, actual: list, tolerance: float) -> list[str]:
    problems: list[str] = []
    if len(expected) != len(actual):
        return [f"row count differs: {len(expected)} vs {len(actual)}"]
    for index, (left, right) in enumerate(zip(expected, actual)):
        for position, (a, b) in enumerate(zip(left, right)):
            if isinstance(a, float) or isinstance(b, float):
                if a is None or b is None:
                    if a != b:
                        problems.append(f"row {index} col {position}: {a!r} vs {b!r}")
                    continue
                if abs(float(a) - float(b)) > tolerance:
                    problems.append(
                        f"row {index} col {position}: diff "
                        f"{abs(float(a) - float(b)):.6f} exceeds {tolerance}"
                    )
            elif a != b:
                problems.append(f"row {index} col {position}: {a!r} vs {b!r}")
    return problems


def capture_plans(connection, output_path: Path) -> None:
    """EXPLAIN (ANALYZE, BUFFERS, SETTINGS) of Q1/Q2/Q4 after the timing."""
    plans_to_capture = ["Q1", "Q2", "Q4"]
    print("Capturing EXPLAIN ANALYZE plans (after timing, not polluting it)")
    cursor = connection.cursor()
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"Section 4.3 EXPLAIN ANALYZE captured {cat_text()} CAT\n")
        out.write(f"Machine {machine_identifier()}\n")
        out.write("=" * 78 + "\n")
        for table_name, _label in TABLES:
            for query_id in plans_to_capture:
                sql = QUERIES[query_id].format(table=table_name)
                cursor.execute(
                    f"EXPLAIN (ANALYZE, BUFFERS, SETTINGS) {sql}"
                )
                out.write(f"\n{query_id} on {table_name}\n")
                out.write("-" * 78 + "\n")
                for (line,) in cursor.fetchall():
                    out.write(line + "\n")
        out.write("=" * 78 + "\n")
    cursor.close()
    print(f"  plans written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", action="store_true",
                        help="capture EXPLAIN ANALYZE after the timed runs")
    args = parser.parse_args()

    run_id = cat_now().strftime("%Y-%m-%d_%H-%M-%S")
    machine = machine_identifier()

    print("=" * 78)
    print("Section 4.3  Timing the five workloads on compressed tables")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine}")
    print(f"Run id  {run_id}")
    print("=" * 78)
    print("")
    print("  Client          psycopg2 via benchmarks/run_compressed_benchmarks.py")
    print("  Timing tool     time.perf_counter() (monotonic, nanosecond clock)")
    print("  Timer bracket   cursor.execute() to fetchall() of the last row")
    print(f"  Per query/table {WARMUPS} warm-up + {MEASURED_RUNS} measured runs")
    print("  Cache label     WARM CACHE (warm-up precedes timing, no restart)")
    print("  Settings        unchanged; no SET statements are issued")
    print("  Compression     policies still paused, no background compression")
    print("")

    connection = connect(application_name="smart-energy-grid")
    connection.autocommit = True
    cursor = connection.cursor()

    print("Updating table statistics with ANALYZE")
    for table_name, _ in TABLES + [("energy_readings", "baseline")]:
        cursor.execute(f"ANALYZE {table_name}")
        print(f"  ANALYZE {table_name}")
    print("")

    print("=" * 78)
    print("RESULT EQUIVALENCE CHECK (vs uncompressed energy_readings)")
    print("=" * 78)
    reference_results: dict[str, list] = {}
    equivalence_ok = True
    for query_id, template in QUERIES.items():
        cursor.execute(template.format(table=BASELINE))
        reference_results[query_id] = cursor.fetchall()
        for table_name, _label in TABLES:
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
                print(f"  {query_id} on {table_name}: matches {BASELINE}")
    print("")
    if not equivalence_ok:
        raise SystemExit(
            "Results differ from energy_readings by more than 0.001. "
            "Timing would be meaningless; fix the data first."
        )
    print("  All five queries return matching results on both compressed")
    print("  tables (numeric tolerance 0.001).")
    print("")

    print("=" * 78)
    print("MEASURED RUNS")
    print("=" * 78)

    records: list[dict] = []
    session_started_at: datetime | None = None
    session_finished_at: datetime | None = None

    csv_path = Path(PROJECT_ROOT) / "benchmarks" / "compressed_timings.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "run_id", "query_id", "table_name", "configuration",
                "phase", "run_number", "duration_ms", "row_count",
                "cat_start", "cat_end", "machine",
            ],
        )
        if write_header:
            writer.writeheader()

        for query_id, template in QUERIES.items():
            print("")
            print(f"  {query_id}")
            for table_name, configuration in TABLES:
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
                            "configuration": configuration,
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
                                f"    {configuration:<22} run {number} "
                                f"{duration_ms:>10.3f} ms  "
                                f"rows={row_count:<8} "
                                f"{start_cat.strftime('%H:%M:%S.%f')[:-3]} -> "
                                f"{end_cat.strftime('%H:%M:%S.%f')[:-3]}"
                            )
                        else:
                            print(
                                f"    {configuration:<22} warm-up "
                                f"{duration_ms:>10.3f} ms  (not timed)"
                            )

    cursor.close()

    if args.plans:
        capture_plans(connection, Path(PROJECT_ROOT) / "logs" / "explain_compressed.txt")
    connection.close()

    print("")
    print("=" * 78)
    print("SUMMARY  (milliseconds, warm-cache, median of "
          f"{MEASURED_RUNS} measured runs)")
    print("=" * 78)
    header = (f"  {'Query':<6}{'Configuration':<24}"
              f"{'Median':>12}{'Min':>12}{'Max':>12}{'Rows':>10}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for query_id in QUERIES:
        for table_name, configuration in TABLES:
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
            label = configuration
            print(f"  {query_id:<6}{label:<24}"
                  f"{median:>12.3f}{low:>12.3f}{high:>12.3f}{row_count:>10}")

    print("")
    print(f"  Per-run records appended to {csv_path}")
    print("  Label these results WARM CACHE in the report.")


if __name__ == "__main__":
    run_with_log("compressed_benchmark", main)