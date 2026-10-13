"""Section 7.4: measure dashboard performance (Raw vs Aggregate) in a browser.

TOOLING
    Playwright 1.63.0 drives a real Google Chrome browser (the same browser,
    machine and connection for both modes). Grafana is not installed, so the
    Grafana-only instructions (/api/ds/query timings, Grafana query caching)
    do not apply; the equivalent evidence is captured here.

PROTOCOL
    * Pause every assignment background job (compression policies 1000/1001 and
      the three continuous-aggregate refresh policies 1002-1004) with
      alter_job(job_id, scheduled => false) before timing, and resume them
      afterwards; print their enabled status.
    * Dashboard query-result caching is disabled: the Dash callbacks have no
      memoisation, so every Refresh re-executes all five panel SQL statements
      (evidence: the per-refresh server timings change from run to run). The
      browser context sends Cache-Control: no-cache and is otherwise fresh.
    * Section 7.3 filters and dates: [2026-09-22 .. 2026-09-29) exclusive,
      all regions, meter 1000000000. Raw is measured first, then Aggregate.
    * Per mode: 1 warm-up refresh, then 10 measured refreshes.
    * Per refresh, record each panel's query duration (server timings shown by
      the dashboard) and the elapsed milliseconds from clicking Refresh until
      all five panels have finished rendering, plus CAT start/end timestamps.

OUTPUTS
    results/dashboard_timings_raw_runs.csv   every run, both modes
    results/dashboard_timings_summary.csv    median/min/max per panel + whole
                                             dashboard, per mode
    results/cagg_storage_and_refresh.csv     live aggregate sizes + the recorded
                                             Section 6.1 initial refresh seconds
    logs/benchmark_dashboards_<CAT>.txt      full transcript
    logs/benchmark_raw_server.log, benchmark_aggregate_server.log

HOW TO RUN
    python dashboards\\benchmark_dashboards.py
"""

import csv
import re
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "dashboards"))

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

START = datetime.fromisoformat("2026-09-22T00:00:00+02:00")
END = datetime.fromisoformat("2026-09-29T00:00:00+02:00")
METER = 1000000000
PANELS = ["P1", "P2", "P3", "P4", "P5"]
MODES = ["Raw", "Aggregate"]
WARMUPS = 1
MEASURED_RUNS = 10

URLS = {"Raw": "http://127.0.0.1:8050", "Aggregate": "http://127.0.0.1:8051"}

# Recorded in logs/dashboard_benchmark_2026-10-07_01-31-51.txt (Section 6.1).
# These are the initial refresh durations; they are NOT re-measured here, so
# they are read back from the recorded log rather than invented.
REFRESH_LOG = PROJECT_ROOT / "logs" / "dashboard_benchmark_2026-10-07_01-31-51.txt"


def pause_jobs(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT job_id
            FROM timescaledb_information.jobs
            WHERE proc_name IN ('policy_compression', 'policy_compression_narrow',
                                'policy_refresh_continuous_aggregate',
                                'policy_continuous_aggregate',
                                'policy_materialize_continuous_aggregate')
            ORDER BY job_id
            """
        )
        job_ids = [row[0] for row in cursor.fetchall()]
        for job_id in job_ids:
            cursor.execute("SELECT alter_job(%s, scheduled => false)", (job_id,))
    connection.commit()
    return job_ids


def set_jobs(connection, job_ids, scheduled):
    with connection.cursor() as cursor:
        for job_id in job_ids:
            cursor.execute("SELECT alter_job(%s, scheduled => %s)",
                           (job_id, scheduled))
    connection.commit()


def jobs_status(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT job_id, proc_name, scheduled
            FROM timescaledb_information.jobs
            WHERE proc_name NOT LIKE 'policy_telemetry%'
              AND proc_name NOT LIKE 'policy_job_stat%'
            ORDER BY job_id
            """
        )
        return [(r[0], r[1], r[2]) for r in cursor.fetchall()]


def wait_port(host, port, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.5)
    raise RuntimeError(f"server on {host}:{port} did not start in {timeout}s")


def start_server(script, port, log_name):
    log_path = PROJECT_ROOT / "logs" / log_name
    handle = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(script)],
                            cwd=str(PROJECT_ROOT), stdout=handle,
                            stderr=subprocess.STDOUT)
    wait_port("127.0.0.1", port)
    return proc, handle


def parse_panel_ms(text):
    out = {}
    for match in re.finditer(r"(P\d|total_ms)\s+([0-9]+\.[0-9]+)\s*ms", text):
        out[match.group(1)] = float(match.group(2))
    return out


def live_cagg_storage(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH agg AS (
                SELECT view_name, materialization_hypertable_schema AS s,
                       materialization_hypertable_name AS h
                FROM timescaledb_information.continuous_aggregates
                WHERE view_name IN ('cagg_15min_region', 'cagg_hour_region',
                                    'cagg_day_meter')
            ),
            sizes AS (
                SELECT a.view_name,
                       sum(pg_relation_size(
                           format('%I.%I', c.chunk_schema, c.chunk_name)::regclass))
                           AS data_bytes,
                       sum(pg_indexes_size(
                           format('%I.%I', c.chunk_schema, c.chunk_name)::regclass))
                           AS index_bytes,
                       sum(pg_total_relation_size(
                           format('%I.%I', c.chunk_schema, c.chunk_name)::regclass))
                           AS total_bytes
                FROM agg a
                JOIN timescaledb_information.chunks c
                  ON c.hypertable_schema = a.s AND c.hypertable_name = a.h
                GROUP BY a.view_name
            )
            SELECT view_name, data_bytes, index_bytes, total_bytes
            FROM sizes ORDER BY view_name
            """
        )
        return {r[0]: {"data_bytes": int(r[1]), "index_bytes": int(r[2]),
                       "total_bytes": int(r[3])} for r in cursor.fetchall()}


def recorded_refresh_seconds():
    """Read the Section 6.1 initial refresh seconds from the recorded log."""
    values = {}
    if not REFRESH_LOG.exists():
        return values
    pattern = re.compile(r"(cagg_\w+)\s+([0-9.]+) MB stored\s+([0-9.]+) s")
    for line in REFRESH_LOG.read_text(encoding="utf-8").splitlines():
        match = pattern.search(line)
        if match:
            values[match.group(1)] = float(match.group(3))
    return values


def run_mode(page, mode, run_records, machine, browser_label):
    url = URLS[mode]
    page.goto(url, wait_until="load")
    page.wait_for_function(
        "() => { const el=document.querySelector('#timings');"
        "return el && el.innerText.includes('dashboard'); }",
        timeout=120000)
    # Guard: confirm the default filters are the Section 7.3 range.
    text = page.inner_text("#timings")
    assert "2026-09-22" in text and "2026-09-29" in text, \
        f"unexpected default range for {mode}: {text}"

    total = WARMUPS + MEASURED_RUNS
    for number in range(1, total + 1):
        phase = "warmup" if number <= WARMUPS else "measured"
        previous = page.inner_text("#timings")
        cat_start = cat_now()
        counter = time.perf_counter()
        page.click("#refresh")
        page.wait_for_function(
            """(old) => { const el=document.querySelector('#timings');
               return el && el.innerText !== old
                      && el.innerText.includes('span'); }""",
            arg=previous, timeout=180000)
        page.wait_for_function(
            "() => document.querySelectorAll('.js-plotly-plot').length >= 5",
            timeout=60000)
        page.wait_for_timeout(150)  # let the final plotly transition settle
        render_ms = (time.perf_counter() - counter) * 1000.0
        cat_end = cat_now()

        timings = parse_panel_ms(page.inner_text("#timings"))
        record = {
            "mode": mode,
            "phase": phase,
            "run_number": number if phase == "measured" else 0,
            "dashboard_render_ms": round(render_ms, 3),
            "server_total_ms": timings.get("total_ms"),
            "cat_start": cat_start.isoformat(timespec="milliseconds"),
            "cat_end": cat_end.isoformat(timespec="milliseconds"),
            "machine": machine,
            "browser": browser_label,
        }
        for panel in PANELS:
            record[f"{panel}_ms"] = timings.get(panel)
        run_records.append(record)
        tag = f"run {number:>2}" if phase == "measured" else "warm-up "
        print(f"    {tag}  render {render_ms:>10.3f} ms  "
              + "  ".join(f"{p}={timings.get(p, 0):.3f}" for p in PANELS))


def main():
    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    machine = machine_identifier()

    print("=" * 78)
    print("Section 7.4  Dashboard performance (Raw vs Aggregate), browser-driven")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine}")
    print("=" * 78)
    print("  Tool        Dash 4.4.1 served on 127.0.0.1, driven by Playwright")
    print("  Filters     [2026-09-22 .. 2026-09-29) exclusive, meter 1000000000")
    print(f"  Per mode    {WARMUPS} warm-up + {MEASURED_RUNS} measured refresh")
    print("  Cache label WARM CACHE (warm-up first, no server restart)")
    print("  Caching     disabled (Dash callbacks have no memoisation; every")
    print("              refresh re-runs all five panel queries)")
    print("")

    # --- pause background jobs -------------------------------------------
    connection = connect()
    paused = pause_jobs(connection)
    print(f"Paused {len(paused)} background jobs: "
          + ", ".join(str(j) for j in paused))
    print("")

    from playwright.sync_api import sync_playwright

    run_records = []
    browser_label = "unknown"
    browser_version = "unknown"
    servers = []
    try:
        raw_proc, raw_handle = start_server(
            PROJECT_ROOT / "dashboards" / "raw_app.py", 8050,
            "benchmark_raw_server.log")
        agg_proc, agg_handle = start_server(
            PROJECT_ROOT / "dashboards" / "aggregate_app.py", 8051,
            "benchmark_aggregate_server.log")
        servers = [(raw_proc, raw_handle), (agg_proc, agg_handle)]
        print("Both dashboards are up (Raw :8050, Aggregate :8051)")
        print("")

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="chrome",
                                                     headless=True)
                browser_label = "Google Chrome (Playwright channel=chrome)"
            except Exception:
                browser = playwright.chromium.launch(headless=True)
                browser_label = "Playwright Chromium"
            browser_version = browser.version
            context = browser.new_context()
            context.set_extra_http_headers(
                {"Cache-Control": "no-cache", "Pragma": "no-cache"})
            page = context.new_page()
            print(f"Browser {browser_label} version {browser_version}")
            print("")

            for mode in MODES:
                print(f"  --- mode {mode} ---")
                run_mode(page, mode, run_records, machine, browser_label)
                print("")
            context.close()
            browser.close()
    finally:
        for proc, handle in servers:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
            handle.close()

    # --- write raw runs CSV ----------------------------------------------
    fields = ["mode", "phase", "run_number", "dashboard_render_ms",
              "server_total_ms"] + [f"{p}_ms" for p in PANELS] + \
             ["cat_start", "cat_end", "machine", "browser"]
    runs_path = results_dir / "dashboard_timings_raw_runs.csv"
    with open(runs_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(run_records)

    # --- summary CSV ------------------------------------------------------
    summary_rows = []
    print("=" * 78)
    print("SUMMARY (milliseconds, warm-cache, median/min/max)")
    print("=" * 78)
    print(f"  {'Mode':<11}{'Metric':<10}{'Median':>11}{'Min':>11}{'Max':>11}")
    print("  " + "-" * 51)
    for mode in MODES:
        measured = [r for r in run_records
                    if r["mode"] == mode and r["phase"] == "measured"]
        metrics = {p: [r[f"{p}_ms"] for r in measured] for p in PANELS}
        metrics["dashboard"] = [r["dashboard_render_ms"] for r in measured]
        for metric in PANELS + ["dashboard"]:
            durations = metrics[metric]
            row = {
                "mode": mode,
                "metric": metric,
                "median_ms": round(statistics.median(durations), 3),
                "min_ms": round(min(durations), 3),
                "max_ms": round(max(durations), 3),
            }
            summary_rows.append(row)
            print(f"  {mode:<11}{metric:<10}{row['median_ms']:>11.3f}"
                  f"{row['min_ms']:>11.3f}{row['max_ms']:>11.3f}")
        print("")
    summary_path = results_dir / "dashboard_timings_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["mode", "metric", "median_ms",
                                                 "min_ms", "max_ms"])
        writer.writeheader()
        writer.writerows(summary_rows)

    # --- aggregate storage + recorded refresh cost -----------------------
    storage = live_cagg_storage(connection)
    refresh = recorded_refresh_seconds()
    storage_path = results_dir / "cagg_storage_and_refresh.csv"
    with open(storage_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["view_name", "data_bytes", "index_bytes",
                         "total_bytes", "total_mb", "recorded_initial_refresh_s",
                         "refresh_source"])
        for view in ("cagg_15min_region", "cagg_hour_region",
                     "cagg_day_meter"):
            info = storage.get(view, {})
            writer.writerow([
                view,
                info.get("data_bytes"), info.get("index_bytes"),
                info.get("total_bytes"),
                round(info.get("total_bytes", 0) / 1024 / 1024, 3),
                refresh.get(view),
                str(REFRESH_LOG) if view in refresh else "not recorded",
            ])
    print("SECTION 6.1 AGGREGATE STORAGE (live) AND RECORDED INITIAL REFRESH")
    print("-" * 60)
    total_mb = 0.0
    for view in ("cagg_15min_region", "cagg_hour_region", "cagg_day_meter"):
        info = storage.get(view, {})
        mb = info.get("total_bytes", 0) / 1024 / 1024
        total_mb += mb
        secs = refresh.get(view)
        secs_text = f"{secs:.3f} s" if secs is not None else "recorded value not found"
        print(f"  {view:<20}{mb:>9.3f} MB stored   {secs_text:>16}"
              f"  (from {REFRESH_LOG.name})")
    print(f"  {'TOTAL':<20}{total_mb:>9.3f} MB stored")
    if not refresh:
        print(f"  Initial refresh seconds not found in {REFRESH_LOG};")
        print("  find the recorded values in report/notes.md Phase 6.x.")
    print("")

    # --- resume jobs ------------------------------------------------------
    set_jobs(connection, paused, True)
    print("Resumed the paused jobs; current status:")
    for job_id, proc_name, scheduled in jobs_status(connection):
        print(f"  job {job_id:<5}{proc_name:<40}scheduled={scheduled}")
    connection.close()

    print("")
    print(f"Raw runs   -> {runs_path}")
    print(f"Summary    -> {summary_path}")
    print(f"Storage    -> {storage_path}")
    print(f"Browser    -> {browser_label} {browser_version}")
    print(f"Completed  {cat_text()} CAT")


if __name__ == "__main__":
    run_with_log("benchmark_dashboards", main)
