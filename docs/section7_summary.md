# Section 7 — Dashboards (Raw vs Aggregate)

All numbers in this file come from executed queries/runs recorded on
2026-10-11 CAT. Nothing is estimated.

## 0. Environment and tooling (discovered, not assumed)

| Item | Value |
|---|---|
| Dashboard tool | **Dash 4.4.1 / Plotly 6.7.0** (served locally) |
| Browser used for timing | Google Chrome **154.0.8037.99**, driven by **Playwright 1.63.0** |
| Database | PostgreSQL 18 + TimescaleDB 2.30.2, container `timescaledb`, `localhost:5433`, db `smart_energy_grid` |
| Data | `energy_readings` = 10,643,735 rows / 4,000 meters; `meters` = 4,000; `energy_live` = 0 |
| Aggregates (materialized_only = TRUE) | `cagg_15min_region`, `cagg_hour_region`, `cagg_day_meter` |
| Time zone | Africa/Kigali (CAT, UTC+02:00); day buckets aligned to CAT midnight |

**Deviation from the brief (Grafana):** the brief is written for Grafana, but
Grafana is **not installed** on this machine and the dashboards are Dash. Per
the "if a requirement cannot be met as written, stop and explain" rule, the
Grafana-only instructions were replaced with equivalent Dash/Playwright evidence:

* Grafana API / provisioning files → the Dash source and `dashboards/Raw.json`,
  `dashboards/Aggregate.json` (portable dashboard definitions; no secrets).
* Grafana `/api/ds/query` panel timings → the dashboard's own per-panel query
  timings (printed on-screen and parsed from the running page).
* Grafana query-result caching → Dash has no memoisation, so every Refresh
  re-executes all five panel queries (proved by per-run timing variance).

## 1. Gap analysis (audit before changes)

The pre-change work was a **single** Dash app (`dashboards/app.py`) with a
Raw/Aggregate **radio button**, plus `dashboard_data.py`, `time_dashboards.py`
(server-side SQL timing) and `verify_dashboards.py`. Backed up to
`dashboards/backup/` (`legacy_combined_dashboard.json`, `*.py.bak`).

| # | Requirement | Was | Now |
|---|---|---|---|
| 1 | Two dashboards named exactly `Raw` and `Aggregate` | one app + mode radio | `raw_app.py` (:8050) and `aggregate_app.py` (:8051), titles "Raw"/"Aggregate" |
| 2 | JSON exports `Raw.json` / `Aggregate.json` | absent | `dashboards/export_dashboards.py` → both files |
| 3 | Backup before changes | absent | `dashboards/backup/` (JSON + `.py.bak`) |
| 4 | One `.sql` per panel | SQL inline in Python | `sql/dashboards/{raw,aggregate}/p1..p5*.sql`, loaded by `dashboard_data.py` |
| 5 | 7.3 result file | `dashboards/panel_data_*.csv` | `results/dashboard_match.csv` + PASS/FAIL |
| 6 | Raw P5 observed = `count(*)` | `count(DISTINCT (meter_id,event_time))` | `count(*)` (cleaned table is already one row per pair) |
| 7 | 7.4 browser benchmark | server-side SQL only | `benchmark_dashboards.py` (Playwright → real Chrome) |
| 8 | Storage/refresh pulled, not hard-coded | hard-coded Python dict | live sizes via SQL; refresh seconds read from the recorded Section 6 log |
| 9 | `docs/section7_summary.md` | absent | this file |
| 10 | README commands | absent | added in `README.md` §7 |

## 2. Panels and their exact source per mode

| Panel | Title | Unit | Raw source | Aggregate source |
|---|---|---|---|---|
| P1 | Hourly regional energy | kWh | `energy_readings JOIN meters` | `cagg_hour_region` |
| P2 | Daily network energy | kWh | `energy_readings` | `cagg_15min_region` re-bucketed to CAT days |
| P3 | Seven-day period energy (1/8/15/22 Sep) | kWh | `energy_readings` | `cagg_15min_region` re-bucketed, mapped to periods |
| P4 | Daily energy of selected meter | kWh | `energy_readings` (`meter` filter) | `cagg_day_meter` |
| P5 | Completeness by region | percent | `energy_readings JOIN meters`, observed = `count(*)` | `cagg_15min_region` `SUM(reading_count)` + `meters` registered counts |

Every panel is limited to the selected range with
`event_time >= start AND event_time < end` (end exclusive); Aggregate uses the
bucket equivalent. Filters identical in both; meter selector used only by P4;
default range `[2026-09-22 .. 2026-09-29)` and default meter `1000000000`.

## 3. Section 7.3 — matching results (`results/dashboard_match.csv`)

Range `[2026-09-22 00:00 +02 .. 2026-09-29 00:00 +02)` exclusive, all regions,
meter `1000000000`. Command: `python dashboards\verify_dashboards.py`.

| Panel | Rows (Raw=Agg) | Keys identical | Counts identical | Max abs energy diff (kWh) | Max abs completeness diff (pp) | Status |
|---|---|---|---|---|---|---|
| P1 | 1680 | yes | yes | 0.000000 | 0.000000 | PASS |
| P2 | 7 | yes | yes | 0.000000005 | 0.000000 | PASS |
| P3 | 1 | yes | yes | 0.000000004 | 0.000000 | PASS |
| P4 | 7 | yes | yes | 0.000000 | 0.000000 | PASS |
| P5 | 10 | yes | yes | n/a | 0.000000 | PASS |

**PASS** — all energy differences ≤ 0.001 kWh and all completeness differences
≤ 0.000001 pp (before rounding). Differences on P2/P3 are at the 1e-9 float
summation level.

## 4. Section 7.4 — timing (`results/dashboard_timings_summary.csv`)

Command: `python dashboards\benchmark_dashboards.py`. Warm cache, 1 warm-up +
10 measured refreshes per mode, Raw then Aggregate, jobs 1000–1004 paused.
Per-panel = dashboard query duration; **dashboard** = elapsed from clicking
Refresh until all five panels finished rendering in the browser.

| Mode | Metric | Median (ms) | Min (ms) | Max (ms) |
|---|---|---|---|---|
| Raw | P1 | 1229.568 | 950.793 | 2185.830 |
| Raw | P2 | 738.258 | 445.858 | 1181.862 |
| Raw | P3 | 880.359 | 483.674 | 1366.080 |
| Raw | P4 | 9.401 | 7.038 | 18.440 |
| Raw | P5 | 1282.902 | 799.795 | 2049.342 |
| Raw | **dashboard** | **5699.258** | **4022.079** | **7912.199** |
| Aggregate | P1 | 42.591 | 25.860 | 64.763 |
| Aggregate | P2 | 13.945 | 9.608 | 28.567 |
| Aggregate | P3 | 9.932 | 6.526 | 37.291 |
| Aggregate | P4 | 7.138 | 5.318 | 20.432 |
| Aggregate | P5 | 13.686 | 7.816 | 36.404 |
| Aggregate | **dashboard** | **1272.613** | **986.660** | **1581.248** |

Improvement = `100 × (Raw median − Aggregate median) / Raw median`:

| Metric | Speed-up | Improvement |
|---|---|---|
| P1 | 28.9× | 96.5% |
| P2 | 52.9× | 98.1% |
| P3 | 88.6× | 98.9% |
| P4 | 1.3× | 24.1% |
| P5 | 93.7× | 98.9% |
| **Whole dashboard** | **4.5×** | **77.7%** |

### Aggregate storage and initial refresh cost (Section 6.1)

| View | Stored (live) | Recorded initial refresh |
|---|---|---|
| `cagg_15min_region` | 4.156 MB | 51.672 s |
| `cagg_hour_region` | 1.234 MB | 31.222 s |
| `cagg_day_meter` | 12.570 MB | 16.150 s |
| **Total** | **17.961 MB** | **99.044 s** |

Sizes queried live (`results/cagg_storage_and_refresh.csv`). The refresh
seconds are **not** re-measured here; they were read from the already-recorded
Section 6 log `logs/dashboard_benchmark_2026-10-07_01-31-51.txt` (also in
`report/notes.md` Phase 6.x) so no number is invented. Re-running the initial
refresh is deliberately avoided because it would re-materialise the aggregates.

## 5. Does the speed-up justify the extra storage and refresh work?

Measured, the Aggregate dashboard returns the same five panels with the same
keys and reading counts and reduces the whole-dashboard refresh from a median of
**5699.258 ms to 1272.613 ms (4.5×, 77.7% faster)**; every one of the five
panels is equal or faster, the largest being P5 (1282.902 → 13.686 ms, 93.7×).
The price is **17.961 MB** of stored aggregates (about 1.3% of the 1351 MB
uncompressed `energy_readings`) plus a **one-off 99.044 s** initial refresh,
after which the 15-minute refresh policy keeps them current. On this 2-core,
8 GB machine the raw scan per refresh also competes for CPU with any concurrent
workload, so the aggregate path is the better default for interactive use. The
gain is real but **not free**: the whole-dashboard figure (4.5×) is smaller than
the per-panel SQL gains (up to 94×) because the browser must still render five
Plotly panels, and P4 (a single-meter point lookup already served by an index)
gains only 24% — continuous aggregates are not a universal accelerator. Provided
the three refresh policies are enabled and the retention/lookback windows are
respected, the storage and one-off refresh cost are clearly justified by the
removal of the 4–8 s raw scan from every dashboard refresh. The honest caveat is
that if only a single meter is ever queried, the aggregate adds storage and
refresh work for almost no benefit; the recommendation assumes whole-network
reporting, which is the dashboard's actual use.

## 6. Screenshots you must take (each with command/action, result, taskbar, clock)

1. Running **Raw** dashboard (`http://127.0.0.1:8050`) with all five panels.
2. Running **Aggregate** dashboard (`http://127.0.0.1:8051`) with all five panels.
3. Panel query definitions: `sql/dashboards/raw/*.sql` and `/aggregate/*.sql`
   (and/or `dashboards/Raw.json` / `Aggregate.json`).
4. Paired numerical checks for all five panels — `results/dashboard_match.csv`
   and the PASS table printed by `verify_dashboards.py`.
5. Completed timing results — `results/dashboard_timings_summary.csv` and the
   transcript `logs/benchmark_dashboards_2026-10-11_09-57-17.txt`.
6. Resumed-jobs status — the "Resumed the paused jobs" block at the end of the
   benchmark transcript (jobs 1000–1004 `scheduled=True`).

## 7. Reproduce

```
python dashboards\raw_app.py                     REM Raw dashboard  :8050
python dashboards\aggregate_app.py               REM Aggregate      :8051
python dashboards\export_dashboards.py           REM Raw.json / Aggregate.json
python dashboards\verify_dashboards.py           REM -> results/dashboard_match.csv
python dashboards\benchmark_dashboards.py        REM -> results/dashboard_timings_*.csv
```
