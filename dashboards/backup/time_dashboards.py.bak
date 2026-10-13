"""Section 7.4: measure dashboard performance (Raw vs Aggregate).

MEASUREMENT PROTOCOL (mirrors 3.2.2 - 3.2.4)
    * One machine, one named client: every panel query runs over a fresh
      smart-energy-grid labelled connection from this program.
    * Settings unchanged; no SET statements.
    * Pauses assignment background jobs before measuring (the three Section
      6.1 refresh policies and the two Section 4 compression policies) and
      resumes them afterwards, so no background work competes with the
      measured refreshes.
    * Warm cache: one warm-up refresh precedes ten measured refreshes per
      mode; the server is not restarted and caches are not cleared between
      runs.
    * Each measured refresh times panel queries individually (time around
      each SQL statement, ms, the same timer the dashboard uses) and times
      the whole dashboard elapsed from the first panel request to the last
      panel result arrived (execute/fetch of all five panels), reported as
      milliseconds.
    * The exact filters and dates of Section 7.3 (22-28 September, all
      regions, meter 1000000000) are kept. The dB query functions are the
      same ones the Dash dashboard panels call, so each measured "refresh" is
      the dashboard's own work; the browser paints the returned figures, and
      that client-side paint time is identical in both modes and excluded
      from the reported server-side numbers.

OUTPUTS
    - benchmarks/dashboard_timings.csv  one row per measured refresh
    - logs/dashboard_benchmark_<CAT timestamp>.txt  summary with median,
      minimum and maximum per panel and whole dashboard, per mode
    - the Section 6.1 aggregate storage and initial refresh cost recorded
      beside the timings, as 7.4.2 requires

HOW TO RUN
    From the project root:

        python dashboards\\time_dashboards.py
"""

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
from dashboard_data import PANELS, run_dashboard  # noqa: E402

START = datetime.fromisoformat("2026-09-22T00:00:00+02:00")
END = datetime.fromisoformat("2026-09-29T00:00:00+02:00")
METER = 1000000000
MODES = ["Raw", "Aggregate"]
WARMUPS = 1
MEASURED_RUNS = 10

AGGREGATE_STORAGE = {
    "cagg_15min_region": {"total_mb": 4.156, "refresh_s": 51.672},
    "cagg_hour_region": {"total_mb": 1.234, "refresh_s": 31.222},
    "cagg_day_meter": {"total_mb": 12.539, "refresh_s": 16.150},
}


def background_jobs(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT job_id, proc_name
            FROM timescaledb_information.jobs
            WHERE proc_name IN ('policy_compression',
                                'policy_compression_narrow',
                                'policy_refresh_continuous_aggregate',
                                'policy_continuous_aggregate',
                                'policy_materialize_continuous_aggregate')
            ORDER BY job_id
            """
        )
        return [row for row in cursor.fetchall()]


def set_jobs(connection, job_ids, scheduled: bool) -> None:
    with connection.cursor() as cursor:
        for job_id in job_ids:
            cursor.execute(
                "SELECT alter_job(%s, scheduled => %s)", (job_id, scheduled)
            )
    connection.commit()


def one_measured_refresh(mode: str) -> dict:
    """Run one refresh: time each panel SQL and the whole dashboard."""
    per_panel = {}
    ts = {}
    overall_started = time.perf_counter()
    results = run_dashboard(mode, START, END, METER)
    for panel_id in PANELS:
        per_panel[panel_id] = results[panel_id].query_ms
        ts[panel_id] = cat_now().isoformat(timespec="milliseconds")
    overall_ms = (time.perf_counter() - overall_started) * 1000.0
    return {
        "per_panel_ms": per_panel,
        "dashboard_ms": overall_ms,
        "cat_start": ts["P1"],
        "cat_end": ts["P5"],
    }


def main() -> None:
    run_id = cat_now().strftime("%Y-%m-%d_%H-%M-%S")
    machine = machine_identifier()

    print("=" * 78)
    print("Section 7.4  Dashboard performance comparison")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine}")
    print(f"Run id  {run_id}")
    print("=" * 78)
    print("")
    print("  Mode            Raw = energy_readings, "
          "Aggregate = Section 6.1 views")
    print("  Filters         "
          f"{cat_text(START)} .. {cat_text(END)}  meter {METER}")
    print(f"  Per mode        {WARMUPS} warm-up + {MEASURED_RUNS} measured")
    print("  Cache label     WARM CACHE (warm-up first, no restart)")
    print("  Client          smart-energy-grid via "
          "dashboards/time_dashboards.py")
    print("  Timer           time.perf_counter() around each panel SQL and")
    print("                  around the whole dashboard (all five panels)")
    print("  Caching         disabled - every refresh executes every query")
    print("")

    connection = connect()
    jobs = background_jobs(connection)
    print(f"Pausing {len(jobs)} assignment background jobs for the "
          "measurement")
    set_jobs(connection, [job_id for job_id, _ in jobs], False)
    print("  paused job ids: "
          + ", ".join(str(job_id) for job_id, _ in jobs))
    print("")

    records = []
    csv_path = Path(PROJECT_ROOT) / "benchmarks" / "dashboard_timings.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["run_id", "mode", "phase", "run_number",
                        "dashboard_ms"]
                       + [f"{p}_ms" for p in PANELS]
                       + ["cat_start", "cat_end", "machine"],
        )
        if write_header:
            writer.writeheader()

        for mode in MODES:
            print(f"  --- mode {mode} ---")
            for phase, count in (("warmup", WARMUPS),
                                 ("measured", MEASURED_RUNS)):
                for number in range(1, count + 1):
                    timing = one_measured_refresh(mode)
                    record = {
                        "run_id": run_id,
                        "mode": mode,
                        "phase": phase,
                        "run_number": number,
                        "dashboard_ms": f"{timing['dashboard_ms']:.3f}",
                        **{f"{p}_ms":
                           f"{timing['per_panel_ms'][p]:.3f}"
                           for p in PANELS},
                        "cat_start": timing["cat_start"],
                        "cat_end": timing["cat_end"],
                        "machine": machine,
                    }
                    writer.writerow(record)
                    csv_file.flush()
                    if phase == "measured":
                        records.append(
                            {"mode": mode, "run_number": number, **timing}
                        )
                        print(
                            f"    run {number:>2}  dashboard "
                            f"{timing['dashboard_ms']:>10.3f} ms  "
                            + "  ".join(
                                f"{p}={timing['per_panel_ms'][p]:.3f}"
                                for p in PANELS
                            )
                        )
                    else:
                        print(f"    warm-up     dashboard "
                              f"{timing['dashboard_ms']:>10.3f} ms")
            print("")

    # Resume the paused jobs.
    set_jobs(connection, [job_id for job_id, _ in jobs], True)
    connection.close()
    print("Resumed the paused jobs after measurement")
    print("")

    print("=" * 78)
    print("SUMMARY  (milliseconds, warm-cache, median/min/max)")
    print("=" * 78)
    print(f"  {'Mode':<12}{'Panel':<6}{'Median':>12}{'Min':>12}{'Max':>12}")
    print("  " + "-" * 54)
    for mode in MODES:
        mode_records = [r for r in records if r["mode"] == mode]
        for panel_id in PANELS:
            durations = [r["per_panel_ms"][panel_id]
                         for r in mode_records]
            print(f"  {mode:<12}{panel_id:<6}"
                  f"{statistics.median(durations):>12.3f}"
                  f"{min(durations):>12.3f}{max(durations):>12.3f}")
        dash = [r["dashboard_ms"] for r in mode_records]
        print(f"  {mode:<12}{'total':<6}"
              f"{statistics.median(dash):>12.3f}"
              f"{min(dash):>12.3f}{max(dash):>12.3f}")
        print("")

    print("SECTION 6.1 AGGREGATE STORAGE AND INITIAL REFRESH COST")
    print("-" * 54)
    for view, info in AGGREGATE_STORAGE.items():
        print(f"  {view:<22}{info['total_mb']:>10.3f} MB stored"
              f"{info['refresh_s']:>10.3f} s initial refresh")
    print("")
    print(f"  Per-run records appended to {csv_path}")
    print("  Label these results WARM CACHE in the report.")


if __name__ == "__main__":
    run_with_log("dashboard_benchmark", main)