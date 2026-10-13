# Presentation & Demo Guide — Smart Energy Grid Analytics (Assignment I)

**Audience:** group colleagues / tutor. **Goal:** explain what was built, how it
was measured, and what we concluded — in about 15–20 minutes, plus a live demo.

Every number below is a **measured** result already recorded in the repo. The
`Source` column tells you the exact file to open if someone asks to see the
evidence. Nothing here is estimated.

---

## How to use this guide

- Each section is one slide. The **Say** block is a suggested script; the
  **Show** block is the file/chart to display.
- The **Demo plan** near the end is the live portion. Read it once beforehand.
- The **Q&A prep** lists the questions a tutor is most likely to ask, with the
  answers already in our data.
- Fill in the **Contributions** slide yourself before presenting (Section 9.3).

---

## Slide 1 — Title

**Say:** "This is our Smart Energy Grid Analytics project — a full big-data
pipeline over 4,000 smart meters, 28 days of 15-minute readings, about 10.7
million rows. We ingested it, cleaned it, benchmarked storage layouts, built
dashboards, and trained a demand forecast."

**Show:** `README.md` title block and the one-line description.

Key headline numbers to put on the slide:

| Metric | Value |
|---|---|
| Meters | 4,000 (Region 1–10, 400 each) |
| Period | 1–29 Sep 2026 (exclusive), CAT (UTC+2) |
| Planned readings | 10,752,000 |
| Emitted readings | 10,696,848 |
| Clean benchmark | 10,643,735 rows |
| Tech stack | PostgreSQL 18.6 + TimescaleDB 2.30.2 + EMQX 6.3.1 (Docker), Python 3.13, Dash/Plotly, scikit-learn |

---

## Slide 2 — The brief and our architecture

**Say:** "The assignment is an electricity utility scenario. We play data
analysts. The only supplied code is `smart_meter_simulator.py`, which we used
**unchanged**. Everything else — every line of ingestion, cleaning, SQL,
dashboards and modelling — is ours."

**Show:** a simple pipeline diagram you can draw live:

```
smart_meter_simulator.py  (supplied, unchanged)
        |
        +--> 1.3 MQTT pilot ---> EMQX ---> energy_live   (regular table)
        |
        +--> 2.1 full capture (direct Python -> DB) ---> energy_readings (hypertable, 1-day chunks)
                    |
        +--> 2.2 data quality ---> 2.3 cleaning (dedupe) ---> cleaned benchmark
                    |
        +--> 3. chunk intervals     (1 day / 3 h / 1 week)
        +--> 4. compression         (ORDER BY time / SEGMENT BY meter_id)
        +--> 5. utility analysis    (demand, regions, quality, anomalies)
        +--> 6. continuous aggregates
        +--> 7. dashboards          (Raw vs Aggregate)
        +--> 8. forecasting         (baseline vs gradient boosting)
```

**Say:** "The key architectural choice is that all storage experiments run on
the **same cleaned dataset**, so any performance difference is caused by the
layout, not by different data."

**Show:** `README.md` §2 execution order table.

---

## Slide 3 — Section 1.1: environment (why it matters)

**Say:** "The brief asks us to prove we know the machine, because the benchmarks
are only meaningful if we state the limits. This is a small machine: a 2-core,
7.85 GB Windows 10 host, memory already at ~95% load, running PostgreSQL and
EMQX in Docker Desktop."

| Item | Value |
|---|---|
| CPU | Intel Core i5-7200U, **2 physical / 4 logical cores** |
| RAM | 7.85 GB, ~95% load at capture |
| OS | Windows 10 build 10.0.19045, 64-bit |
| Storage | SSD (SanDisk 256 GB), 13.90 GB free on C: |
| PostgreSQL / TimescaleDB | 18.6 / 2.30.2 (container `timescaledb`, port 5433) |
| EMQX | 6.3.1 |
| `shared_buffers` / `work_mem` | 982856 kB / 15357 kB |
| `max_parallel_workers_per_gather` / `jit` | 2 / off |
| Session time zone | `Africa/Kigali` (CAT) |

**Say:** "Two honest caveats we recorded: the container has **no declared** CPU
or memory limit in Docker, but `docker stats` still caps it at ~3.75 GiB through
the WSL2 VM. And because the machine is small and busy, benchmark runs are
**noisy** — that is why every timing we quote is a **median of five runs**, never
a flattering minimum."

**Show:** `report/environment_details.md`, screenshots `1_1_*.png`.

**Source:** `logs/environment_capture_2026-10-06_23-53-33.txt`.

---

## Slide 4 — Section 1.2: database structures

**Say:** "Three tables. `energy_live` is a plain table for the pilot.
`energy_readings` is a TimescaleDB **hypertable** partitioned by `event_time`
with **one-day chunks**. `meters` holds the 4,000 metadata rows with a BIGINT
primary key."

Design decisions worth defending:

- **No unique constraint** on the reading tables at this stage — the assignment
  explicitly wants us to *count* duplicates before removing them, so a unique
  key would make those queries impossible.
- **BIGINT meter_id** — IDs go up to 1,000,003,999, which overflows `INTEGER`.
- **DOUBLE PRECISION** for the five measurement columns — the tolerances are
  ±0.001 kWh across 10.6M rows, too tight for `REAL`.
- **`create_default_indexes => FALSE`** so we can add *identical* explicit
  indexes on all three comparison tables later.

**Show:** `sql/01_schema.sql`, screenshot `1_2_columns.png` and `1_2_interval.png`.

**Fact:** `meters` has exactly 4,000 rows, 400 per region.

---

## Slide 5 — Section 1.3: MQTT pilot

**Say:** "Before the full run we proved the pipeline carries no loss. We
publish 2,000 readings via MQTT to EMQX, subscribe, and insert into
`energy_live`. All four counts the brief asks for agree at 2,000."

| Stage | Count |
|---|---|
| Dictionaries taken from `iter_readings()` | 2,000 |
| Broker acknowledged | 2,000 |
| Subscriber received | 2,000 |
| Rows in `energy_live` | 2,000 |
| Parse errors | 0 |

**Say:** "Zero loss at pilot scale means the publish/subscribe/insert path is
correct. The subscriber is slower than the publisher because each message costs
a JSON parse plus a database round trip — 2,000 individual inserts."

**Show:** screenshot `1_3_publisher.png`, `1_3_database.png`; log
`logs/pilot_counts.json`.

---

## Slide 6 — Section 2.1: full capture and load

**Say:** "We consumed the full stream with a **direct Python → database** route,
no intermediate CSV. That removes one full write-and-read cycle of a ~1 GB file.
We loaded **10,696,848 rows**, duplicates included, in **644.7 seconds** — about
16,500 rows per second."

| Item | Value |
|---|---|
| Dictionaries consumed | 10,696,848 |
| Rows committed | 10,696,848 |
| Generator `emitted_readings` | 10,696,848 |
| Total elapsed | 644.7 s |
| Distinct meters | 4,000 |
| Event range | 2026-09-01 00:00+02 → 2026-09-28 23:45+02 |

**Say:** "The proof that nothing was dropped is that all three counts —
consumed, committed, and the generator's own expectation — are identical."

**Show:** log `logs/readings_load_2026-10-06_16-03-13.txt`, screenshot `2_1_database.png`.

---

## Slide 7 — Section 2.2: data quality (the detective work)

**Say:** "This is where we found the dataset is not clean. Against the planned
grid of 4,000 meters × 28 days × 96 intervals = 10,752,000, we measured exactly
what the generator's own `dataset_info()` predicts — every difference is zero."

| Entry | Measured | Reference | Diff |
|---|---|---|---|
| emitted_readings | 10,696,848 | 10,696,848 | 0 |
| unique_readings | 10,643,735 | 10,643,735 | 0 |
| duplicate_readings | 53,113 | 53,113 | 0 |
| delayed_unique_readings | 213,090 | 213,090 | 0 |
| missing_readings | 108,265 | 108,265 | 0 |

Derived percentages:

| Missing | Duplicate | Delayed | Completeness |
|---|---|---|---|
| 1.0069% | 0.4990% | 2.0020% | **98.9931%** |

**Say:** "The nice insight is *why*. Delay is measured against the interval
**end**, not the start: normal arrival is event_time + 15 min. Delayed arrivals
land 30–180 min late, and the worst observed delay is exactly 180 minutes — which
matches the generator's `delay = 30 + int(random()*151)`. Missing readings are
spread evenly across all 4,000 meters (11 to 47 each), which is the signature of
independent random dropout, not a meter going offline."

**Show:** `logs/data_quality_2026-10-07_10-25-00_PRECLEAN.txt`,
screenshot `2_2_*` if present.

---

## Slide 8 — Section 2.3: cleaning

**Say:** "We removed the 53,113 duplicate copies. First we tested the prediction
that duplicate pairs are byte-identical — and indeed **zero conflicting values**
were found. That is exactly what the generator produces: a duplicate is
`record.copy()` with nothing written in between."

| Item | Before | After |
|---|---|---|
| Rows | 10,696,848 | 10,643,735 |
| Extra copies | 53,113 | 0 |
| Sum energy_kwh | 3,872,863.893 | 3,853,704.347 |
| Distinct meters | 4,000 | 4,000 |

**Say:** "One judgment call we want to highlight: **missing intervals are not
written as zero.** A gap means the meter never reported; a zero would be a
measurement of *no* consumption. Treating gaps as zero would pull every average
down and make completeness meaningless. We count only arrived intervals, and
keep the gaps visible against the planned count."

**Show:** `logs/clean_readings_2026-10-06_18-19-09.txt`, screenshot `2_3_cleaning.png`.

**Say:** "This 10,643,735-row cleaned table is the benchmark for everything
after this point."

---

## Slide 9 — Section 3: chunk interval comparison

**Say:** "Same rows, three different chunk layouts. We timed the same five
queries on each."

| Query | Workload | 1 day | 3 h | 1 week | Fastest |
|---|---|---|---|---|---|
| Q1 | avg power per CAT hour, 21 Sep | 383.6 | **192.2** | 205.2 | 3 h |
| Q2 | ten heaviest 15-min intervals | **630.9** | 864.0 | 1216.6 | 1 day |
| Q3 | total energy per meter | **3078.7** | 4691.9 | 3713.1 | 1 day |
| Q4 | one meter, one week | 6.2 | 8.5 | **2.8** | 1 week |
| Q5 | full scan | 1936.8 | **1931.7** | 2106.3 | tie |

*Median of 5 measured runs, milliseconds, warm cache. Client `smart-energy-grid`,
timer `time.perf_counter()`.*

**Say:** "No interval wins everything, and that is the point. A chunk boundary
costs per-chunk overhead but buys chunk exclusion. The one result with a
plan-backed explanation is Q1: the 1-day plan was the slow one because it was
the only plan that had to **read blocks from disk** — 620 buffer reads — while
the other two were fully served from cache."

**Judgement:** **one-day chunks** are the best general choice — they win the two
heaviest queries (Q3 by 1.5×, Q2 by 1.9×) and are never more than ~2× off the
best. 3-hour chunks pay 225 chunks of bookkeeping for two wins that don't matter.

**Show:** `benchmarks/chunk_timings.csv`, `logs/explain_chunk_configs.txt`,
screenshots `3_1_*`, `3_2_*`.

---

## Slide 10 — Section 4: compression strategies

**Say:** "Two compressed tables, both from the cleaned data, one-day chunks."

| Strategy | Ratio | Saved | Rows in compressed chunks |
|---|---|---|---|
| `ORDER BY time`, no segmentation | **3.080×** | 67.53% | 100% |
| `SEGMENT BY meter_id` | **2.694×** | 62.88% | 100% |

Storage: baseline `energy_readings` = 1351 MB; time-compressed = 438.7 MB;
meter-compressed = 501.6 MB.

Query performance:

| Query | ORDER BY time | SEGMENT BY meter_id | Winner |
|---|---|---|---|
| Q1 (time range, 24 rows) | **113.7** | 1348.4 | ORDER BY time (11.9×) |
| Q2 (10 rows) | 521.6 | **343.5** | SEGMENT |
| Q3 (per meter, 4000) | 1573.2 | **716.9** | SEGMENT (2.2×) |
| Q4 (one meter, 1 row) | 240.4 | **4.9** | SEGMENT (**49×**) |
| Q5 (full scan) | **1141.7** | 1187.0 | ORDER BY time (marginal) |

**Say:** "The story is segmentation. Grouping each meter's 672 rows into one
compressed batch lets a meter-filtered query skip whole batches — that is the
49× on Q4. The cost is the mirror image: a pure time-range query must touch every
meter segment, so Q1 is 11.9× slower. **So we recommend keeping both**: time-
ordered for reporting, meter-segmented for inspection. Together they are still
30.4% smaller than the single uncompressed baseline."

**Show:** `benchmarks/compressed_timings.csv`, `logs/explain_compressed.txt`,
screenshots `4_1_*` … `4_4_*`.

---

## Slide 11 — Section 5: utility data findings

**Say:** "Now the actual 'utility analyst' questions."

**Demand patterns (5.1):**
- Daily energy rises through each week and drops hard at weekends: 1 Sep
  141,195 kWh → 28 Sep 152,464 kWh; lowest 5–6 Sep ~111,700 kWh.
- Four weekly totals rise ~2.5% each week: 934,199 → 953,715 → 973,230 →
  992,560 kWh.
- **Peak 15-min demand: 28 Sep 13:00 CAT, 7,993.691 kW.**
- kW vs kWh: kW is instantaneous rate (the peak), kWh is energy over time (the
  daily totals).

**Regions & customer types (5.2):**
- Region 8 leads on kWh/meter (1,258.7) vs Region 4 (811.0) — a 55% spread.
- But it is a **mix difference, not efficiency**: industrial meters are 406 of
  4,000 meters (10.15%) yet draw 57.6% of all energy (5,469.6 kWh/meter).
  Region 8 just has more industrial meters registered.

**Reporting quality (5.3):**
- Network completeness 98.9931%, flat across regions (98.9693%–99.0129%).
- 21 September early (midnight cut) = 149,400.545 kWh vs all arrivals =
  149,552.723 kWh → **152.178 kWh (0.1018%) understated**. That is the cost of
  the 2% delayed arrivals, and the reason to hold the daily close open.

**Anomalies (5.4):**
- Rule: spike if `power > 2.0×` the meter's (CAT hour, weekday/weekend) median;
  drop if `< 0.1×`. Median over 28 days.
- Result: **40 / 40 injected events detected, 0 false flags** across 10.6M
  outside readings.
- Honest caveat: 473 readings flagged vs 474 inside event windows — one
  in-window reading missed, but every event still had a flag, so event-level
  detection is 40/40 and false flags stay 0.

**Show:** `analysis/output/5_1_daily_energy.png`,
`analysis/output/5_1_seven_day_periods.png`, `logs/demand_patterns_*`,
`logs/regions_*`, `logs/reporting_quality_*`, `logs/anomalies_*`.

---

## Slide 12 — Section 6: continuous aggregates

**Say:** "Three materialized views take the heavy lifting off the raw table."

| View | Grain | Stored | Initial refresh |
|---|---|---|---|
| `cagg_15min_region` | 15 min × region | 4.156 MB | 51.672 s |
| `cagg_hour_region` | 1 h × region | 1.234 MB | 31.222 s |
| `cagg_day_meter` | 1 day × meter | 12.570 MB | 16.150 s |
| **Total** | | **17.96 MB** | **99.044 s** |

**Say:** "That is 1.3% of the uncompressed 1,351 MB baseline, and it buys the
dashboard speed-up you'll see next."

**Freshness test (6.2)** — the subtle one. We inserted readings into an older
hour and the current hour and observed four stages:

| Stage | Older hour | Hour H |
|---|---|---|
| A. initial refresh of older hour | 1 kWh, 1 row | absent |
| B. two new inserts, no refresh, `materialized_only=TRUE` | 1 kWh | absent |
| C. real-time agg **on**, no refresh | 1 kWh | **2 kWh appears** |
| D. manual refresh both hours | **1.5 kWh, 2 rows** | 2 kWh, 1 row |

**Say:** "This separates three things people conflate: `materialized_only`
**hides** unrefreshed rows; real-time aggregation **surfaces** buckets no policy
has touched; and an explicit refresh is what **merges** a late arrival into an
already-materialized bucket. An absent bucket is not a zero reading."

**Show:** `logs/cagg_freshness_2026-10-07_01-22-45.txt`, screenshots `6_1_*`, `6_2_*`.

---

## Slide 13 — Section 7: dashboards (Raw vs Aggregate)

**Say:** "The brief says Grafana. Grafana is not installed on this machine, so
we built **two Dash/Plotly dashboards** with the identical five panels and
filters, differing only in data source, and documented the substitution."

**Say:** "First, 7.3: the two dashboards must return the same numbers."

| Panel | Rows | Max energy diff | Counts equal | Status |
|---|---|---|---|---|
| P1 Hourly regional energy | 1680 | 0.000000 | yes | PASS |
| P2 Daily network energy | 7 | 5e-09 | yes | PASS |
| P3 Seven-day period energy | 1 | 5e-09 | yes | PASS |
| P4 Selected meter daily | 7 | 0.000000 | yes | PASS |
| P5 Completeness by region | 10 | n/a | yes | PASS |

**Say:** "All within tolerance: ≤0.001 kWh and ≤0.000001 pp. The tiny P2/P3
differences are float summation order."

**Then 7.4, the performance payoff:**

| Metric | Raw (ms) | Aggregate (ms) | Speed-up |
|---|---|---|---|
| P1 | 1229.6 | 42.6 | 28.9× |
| P2 | 738.3 | 13.9 | 52.9× |
| P3 | 880.4 | 9.9 | 88.6× |
| P4 | 9.4 | 7.1 | 1.3× |
| P5 | 1282.9 | 13.7 | 93.7× |
| **Whole dashboard** | **5699.3** | **1272.6** | **4.5×** |

*Median of 10 measured refreshes per mode, after 1 warm-up, caching disabled,
jobs 1000–1004 paused, Chrome 154 via Playwright.*

**Say:** "The whole-dashboard gain (4.5×) is smaller than the per-panel SQL
gains (up to 94×) because the browser still has to render five Plotly panels.
And note P4: a single-meter point lookup already served by an index gains almost
nothing — **continuous aggregates are not a universal accelerator**. The
17.96 MB and 99 s of refresh are clearly worth it for whole-network reporting."

**Show:** `results/dashboard_match.csv`,
`results/dashboard_timings_summary.csv`, `docs/section7_summary.md`, running
dashboards.

---

## Slide 14 — Section 8: forecasting

**Say:** "Forecast hourly regional energy in kWh. We use a strict time split:
train 1–14 Sep, validate 15–21 Sep, test 22–28 Sep. Features are all available
before the 00:00 forecast origin: previous day's same hour (lag1d), 2 days back
(lag2d), previous-day mean, and calendar features. No within-day leakage."

**Baseline vs model (test set, 1,680 observations):**

| Method | MAE (kWh) | RMSE (kWh) |
|---|---|---|
| Previous-day baseline | 42.708 | 79.403 |
| Gradient boosting (GB-1) | **15.117** | **20.802** |
| Improvement | **64.6%** | 73.8% |

Model settings: 300 trees, learning rate 0.05, max depth 3, subsample 0.9.
Selected by lowest **validation** MAE (15.0907), then frozen and evaluated once
on test.

**Say:** "It is 2.83× better on MAE, every one of the ten regions improves
individually, and it cuts the peak-hour error on Region 1's busiest hour from
270.3 to 93.0 kWh — and peak error is what matters for dispatch. One condition
before going live: read the lags from the raw table or a real-time view, not
from a not-yet-refreshed `materialized_only` bucket, or you forecast from stale
data."

**Show:** `forecasting/output/8_4_forecast_comparison_Region_1.png`,
`forecasting/selected_model_config.json`, logs `8_1`–`8_4`.

---

## Slide 15 — Section 5.5: management recommendation

**Say:** "The one-page recommendation, backed by measured numbers."

1. **Operational:** hold the daily close open ~3 hours for delayed arrivals —
   the 21 Sep cut understates the day by 152.178 kWh (0.1018%). Run the anomaly
   detector unattended (40/40, 0 false flags). No region-specific ingestion
   problem (completeness flat at 98.99%).
2. **Storage & reporting:** one-day chunks; keep **both** compressed layouts
   (ORDER BY time for reporting, SEGMENT BY meter_id for inspection); run the
   three continuous aggregates on a 15-min schedule with a 3-day lookback and
   1-hour offset. Manually refresh a materialized bucket when a late reading
   arrives, because the policy is bounded by the database clock.
3. **Forecast:** use it — MAE 15.12 vs 42.71 kWh baseline (64.6% better) — with
   lags read from fresh data.

**Show:** `report/notes.md` → "Section 5.5 — Management recommendation".

---

## Slide 16 — Contributions (fill this in — Section 9.3)

Replace the placeholders before presenting:

| Name | Student ID | Contribution |
|---|---|---|
| `<name 1>` | `<id>` | e.g. ingestion + MQTT pilot |
| `<name 2>` | `<id>` | e.g. cleaning + chunk/compression benchmarks |
| `<name 3>` | `<id>` | e.g. dashboards + forecasting |

---

# Demo plan (live)

Total ~6–8 minutes if everything is already built. Pre-flight the day before.

## Pre-flight (do before the session)

```cmd
docker start timescaledb emqx
docker ps
python ingestion\capture_environment.py
```

Open in browser ahead of time: EMQX dashboard http://localhost:18083.

## Demo 1 — The database is real

```cmd
docker exec -it timescaledb psql -U auca -d smart_energy_grid
```
Then inside psql:
```sql
SELECT count(*) FROM meters;                          -- 4000
SELECT count(*) FROM energy_readings;                 -- 10,643,735
SELECT min(event_time), max(event_time) FROM energy_readings;
SELECT count(*) FROM timescaledb_information.chunks
  WHERE hypertable_name = 'energy_readings';          -- 29
SELECT view_name FROM timescaledb_information.continuous_aggregates;
\q
```

**Talking point:** "10.6 million rows, a hypertable with 29 daily chunks, three
continuous aggregates — all still browsable interactively."

## Demo 2 — The two dashboards

```cmd
REM terminal 1
python dashboards\raw_app.py
REM terminal 2
python dashboards\aggregate_app.py
```

Open http://127.0.0.1:8050 (Raw) and http://127.0.0.1:8051 (Aggregate). Click
**Refresh** on each and compare the time shown on screen.

**Talking point:** "Same five panels, same numbers, but the Aggregate dashboard
reflects off stored views — median 1,272 ms vs 5,699 ms."

## Demo 3 — The forecast plot

Open `forecasting/output/8_4_forecast_comparison_Region_1.png`.

**Talking point:** "Actual vs baseline vs model over the seven test days. The
model tracks the daily shape; the baseline is a day behind the trend."

## If asked to run something live (optional)

```cmd
python dashboards\verify_dashboards.py     REM prints the PASS table
python forecasting\03_evaluate_compare.py  REM prints MAE/RMSE comparison
```

---

# Q&A prep — likely tutor questions

**Q: Why not CSV for the full load?**
A: The brief allows either. Direct Python→DB removes one full write-and-read of
a ~1 GB file. We still recorded generation and load separately as evidence.

**Q: Your benchmarks are noisy — how do you trust them?**
A: We quote the **median of five** runs (and 10 for dashboards), state the
machine limits (2 cores, 95% memory), and keep only the measured workload
running. Where a difference is within noise (Q5) we say so instead of claiming
a winner.

**Q: Missing readings as zero would be simpler — why not?**
A: Zero is a measurement of no consumption; a gap is *no measurement*. Treating
gaps as zero biases every average down and makes completeness meaningless. Gaps
are kept visible against the planned count.

**Q: Grafana vs Dash?**
A: Grafana is not installed here. We built two Dash dashboards with identical
panels/filters and replaced the Grafana API timings with the dashboard's own
per-panel timings plus a Playwright-driven Chrome benchmark. Documented in
`docs/section7_summary.md`.

**Q: Is the forecast genuine — no leakage?**
A: Split is by target timestamp (no random shuffle). Every lag is available
before the 00:00 forecast origin; no within-day features. Preprocessing is fit on
training only and frozen before test.

**Q: Why keep both compressed tables?**
A: Each optimises a different access pattern — time-ordered wins time-range
reads, meter-segmented wins meter lookups (49× on Q4). Together they are still
30.4% smaller than the uncompressed baseline.

**Q: Where is the reproducible evidence?**
A: `logs/` (timestamped run transcripts), `benchmarks/*.csv` (raw timings),
`results/` (dashboard match/timings), `sql/` (numbered scripts),
`report/notes.md` (observations vs explanations kept separate).

---

# One-slide summary (if you only get 60 seconds)

We built a complete pipeline over **10.7M smart-meter readings**: ingested via
MQTT and direct load, found and cleaned **53,113 duplicates** to a benchmark of
**10,643,735 rows** at **98.99% completeness**. We benchmarked chunk intervals
and compression (**3.08× compression**, **4.5× faster dashboards** on continuous
aggregates), detected **40/40 injected anomalies with zero false flags**, and
forecast hourly regional demand with a model that is **64.6% better than the
previous-day baseline** (MAE 15.12 vs 42.71 kWh). Full evidence is in `logs/`,
`benchmarks/`, `results/`, and `report/notes.md`.
