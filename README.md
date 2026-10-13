# Smart Energy Grid Analytics — Assignment I

PostgreSQL + TimescaleDB + EMQX pipeline over 4,000 smart meters, covering
15-minute readings from 00:00 on 1 September 2026 to 00:00 on 29 September 2026
(exclusive). All dates and times are **CAT (Africa/Kigali, UTC+2)**.

The only supplied code is `smart_meter_simulator.py`, which is used **unchanged**.

---

## 0. How this project is hosted

Everything runs in Docker on a Windows host:

| Service | Where | How to reach it |
|---|---|---|
| PostgreSQL 18.6 + TimescaleDB 2.30.2 | container `timescaledb` | `localhost:5433` |
| EMQX 6.3.1 | container `emqx` | `localhost:1883` (MQTT), `localhost:18083` (dashboard) |
| Superuser | — | `auca` |

> **A native Windows PostgreSQL 18 service also exists on this machine and is NOT
> used.** Connecting to it would silently give you the wrong server and the wrong
> time zone. If a `psql` command fails to connect, check you are on port **5433**
> as user **auca**, not the Windows service on 5432.

Because the database is containerised, two things follow for the rest of the
project:

- The PostgreSQL **data directory is a path inside the container**. Only the
  container can report free space for it.
- All `psql` work is either `docker exec … psql` or a host `psql` pointed at
  `localhost:5433`.

---

## 1. Before you start

### 1.1 Python packages

```powershell
pip install psycopg2-binary paho-mqtt pandas numpy matplotlib scikit-learn tzdata
```

`tzdata` is not optional on Windows. Python's `zoneinfo` reads the IANA time zone
database, which Windows does not ship, so without this package
`ZoneInfo("Africa/Kigali")` raises `ZoneInfoNotFoundError` and every CAT timestamp
in the project breaks.

### 1.2 Your private settings file

The repository ships `config.example.py` with placeholders only. Copy it and fill
in your values:

```powershell
Copy-Item config.example.py config.py
notepad config.py
```

`config.py` is listed in `.gitignore` and must never be committed — Section 9.2
submits this repository, and a committed password would leak.

> If your `config.py` already holds a real password, **edit it by hand** instead of
> overwriting it. The three values that must match this machine are:
> `DB_PORT = "5433"`, `DB_USER = "auca"`, `DB_NAME = "smart_energy_grid"`.

Any setting can also be overridden per command, which is useful for testing against
a scratch database:

```powershell
$env:DB_NAME = "smart_energy_grid_test"
python ingestion\capture_environment.py
```

---

## 2. Execution order

Run the phases in order. Each depends on the state the previous one leaves behind,
and the report must follow subsection order (Section 9.1).

| Phase | Subsection | Status |
|---|---|---|
| 1.1 | Confirm the environment | done — `logs/environment_capture_2026-10-06_23-53-33.txt`, `report/environment_details.md` |
| 1.2 | Create the database structures | done — `sql\01_schema.sql`, `ingestion\load_meters.py`, 4,000 meters |
| 1.3 | Capture and publish a pilot stream | done — 2,000/2,000/2,000/2,000, `logs/pilot_counts.json` |
| 2.1 | Capture and load the complete stream | done — 10,696,848 rows in 644.7 s, `logs/readings_load_2026-10-06_16-03-13.txt` |
| 2.2 | Investigate data quality | done — `sql\05_data_quality.sql`, `logs/data_quality_*.txt` |
| 2.3 | Clean and preserve a consistent benchmark | done — 10,643,735 rows, 53,113 duplicates removed |
| 3.x | Compare chunk intervals | done — `benchmarks/chunk_timings.csv`, `logs/explain_chunk_configs.txt` |
| 4.x | Compare compression strategies | done — 3.080× / 2.694× ratios, `benchmarks/compressed_timings.csv` |
| 5.1–5.4 | Investigate the utility data | done — `logs/demand_patterns_*`, `regions_*`, `reporting_quality_*`, `anomalies_*` |
| 6.x | Continuous aggregates | done — 3 views, 17.929 MB, `logs/cagg_freshness_*` |
| 7.x | Dashboards | done — two Dash dashboards `Raw`/`Aggregate`; 7.3 PASS, 7.4 Raw 5699.258 ms → Aggregate 1272.613 ms median; `results/`, `docs/section7_summary.md` |
| 8.x | Forecast the next day | done — test MAE 15.116640 vs baseline 42.708281 (64.60% better) |
| 5.5 | Management recommendation (last) | written — `report/notes.md`, Section 5.5 |

Report material lives in `report/notes.md` (paste-ready paragraphs per phase)
and `report/environment_details.md` (Section 1.1 evidence).

---

## 3. Phase 1.1 — Confirm the environment

### 3.1 Confirm the containers are up

```powershell
docker ps
```

You need `timescaledb` and `emqx` both showing **Up**. Start them if needed:

```powershell
docker start timescaledb emqx
```

### 3.2 Create the database

One database is used for everything in the assignment.

```powershell
Get-Content sql\00_create_database.sql -Raw | docker exec -i timescaledb psql -U auca -d postgres -f -
```

> **Why not `… -f - < sql\file.sql`?** Input redirection with `<` is a `cmd` and
> bash feature. **PowerShell 5.1 removed it**, so that command fails with a
> parser error. `Get-Content -Raw |` is the PowerShell equivalent and works
> because `-Raw` keeps the file's newlines intact.
>
> Alternatively, using `psql` from the host:
> ```powershell
> psql -h localhost -p 5433 -U auca -d postgres -f sql/00_create_database.sql
> ```

The script is safe to run more than once: it creates `smart_energy_grid` only if
absent, enables the `timescaledb` extension, sets the database default time zone to
`Africa/Kigali`, and then reconnects so the evidence queries run in a session that
actually has that time zone.

### 3.3 Confirm the broker

Open <http://localhost:18083>. On EMQX 6 the dashboard may print a generated
password at first start — check with:

```powershell
docker logs emqx | Select-String -Pattern "password|admin" | Select-Object -First 10
```

### 3.4 Capture the evidence

```powershell
python ingestion\capture_environment.py
```

It prints and logs the host CPU model and core count from `Win32_Processor`, host
RAM via `GlobalMemoryStatusEx`, the Docker CPU and memory limits from
`docker inspect` plus live `docker stats`, free space inside the database
container, and the Python / PostgreSQL / TimescaleDB / EMQX versions with the four
required PostgreSQL settings.

### 3.5 Fill in the report

Copy the values into `report/environment_details.md` and add the screenshots.

---

## 3.6 Phase 1.2 — Create the structures and load the meters

```cmd
REM 1. Create the three tables and convert energy_readings to a hypertable
type sql\01_schema.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

REM 2. Verify tables, columns, hypertable status and the one-day chunk interval
type sql\02_verify_schema.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

REM 3. Load the 4,000 meter metadata rows from the unchanged generator
python ingestion\load_meters.py

REM 4. Confirm the row count
docker exec -it timescaledb psql -U auca -d smart_energy_grid -c "SELECT count(*) FROM meters;"
```

`python ingestion\load_meters.py` refuses to run when `meters` is not empty,
because the `meter_id` primary key would reject the duplicates. Use `--reset` to
reload from scratch:

```cmd
python ingestion\load_meters.py --reset
```

---

## 4. Useful commands for later phases

```cmd
REM Interactive psql against the assignment database
docker exec -it timescaledb psql -U auca -d smart_energy_grid

REM Run one SQL file (type works in both CMD and PowerShell)
type sql\03_indexes.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

REM Watch container health and resource use
docker stats --no-stream

REM Free space where the tables actually live
docker exec timescaledb df -h /var/lib/postgresql/data
```

> **Run SQL files with `type … | docker exec -i …`, not `<`.** The `<` form works
> in CMD but **PowerShell 5.1 removed input redirection**, so it fails there with
> a parser error. `type` is the one form that works in both shells.

---

## 5. Repository layout

```
smart_meter_simulator.py     Supplied generator. Never modified.
config.example.py            Placeholders only. Copy to config.py and edit.
config.py                    Your real settings. Git-ignored, never committed.
common/                      Shared helpers: CAT time, database connection.
ingestion/                   Environment capture, meters loader, MQTT pilot,
                             full capture.
cleaning/                    Data quality queries and the deduplication program.
benchmarks/                  Chunk comparison timing harness and its results.
analysis/                    Section 5 scripts, including anomaly detection.
dashboards/                  Raw and Aggregate dashboard definitions and queries.
forecasting/                 Dataset preparation, baseline, model, evaluation.
sql/                         Numbered SQL files, schema through aggregates.
report/                      notes.md, environment_details.md, write-up material.
logs/                        Run logs. Git-ignored except the folder itself.
data/                        Generated CSVs and the dataset. Git-ignored.
```

The generated dataset and intermediate CSVs stay out of Git, as Section 9.2
requires. They are reproduced by the programs in `ingestion/`, so a fresh clone can
rebuild them from the unchanged generator.

---

## 6. Troubleshooting

**`Could not load the Africa/Kigali time zone`** — run `pip install tzdata`.

**`config.py was not found`** — `Copy-Item config.example.py config.py`, then edit.

**`could not translate host name` or connection refused** — you are probably on the
native Windows PostgreSQL service. Use port **5433** and user **auca**.

**`Permission denied` running `SHOW` or creating hypertables** — connect as `auca`,
which is the superuser. TimescaleDB DDL requires superuser privileges.

**PowerShell syntax error on `<`** — PowerShell 5.1 has no input redirection. Pipe
with `Get-Content … -Raw |` instead.

**`emqx ctl status` fails inside the container** — try
`docker logs emqx | Select-Object -First 20`; the version appears in the startup
banner.

**TimescaleDB version below 2.10** — Section 1.1 requires 2.10 or later, and the
Section 4 compression syntax depends on the version.

---

## 7. Phase 7.x — Dashboards (Raw vs Aggregate)

The dashboards are **Dash (Plotly)**, not Grafana. Two separate servers share the
same five panels, filters and default range; only the data source differs. All
panel SQL lives in `sql/dashboards/{raw,aggregate}/` and is loaded by
`dashboards/dashboard_data.py`, so the dashboards, verifier and benchmark run
identical SQL.

```powershell
# Run the two dashboards (separate terminals)
python dashboards\raw_app.py          # Raw        http://127.0.0.1:8050
python dashboards\aggregate_app.py    # Aggregate  http://127.0.0.1:8051

# Export portable dashboard definitions (no secrets)
python dashboards\export_dashboards.py     # -> dashboards\Raw.json, Aggregate.json
```

### 7.3 Verify matching results

```powershell
python dashboards\verify_dashboards.py     # -> results\dashboard_match.csv (PASS/FAIL)
```

Range `[2026-09-22 .. 2026-09-29)` exclusive, all regions, meter `1000000000`.
Requires identical keys, identical P5 reading counts, energy difference
≤ 0.001 kWh and completeness difference ≤ 0.000001 pp.

### 7.4 Measure performance (browser)

```powershell
python dashboards\benchmark_dashboards.py
```

Starts both dashboards, pauses background jobs 1000–1004, drives **Google Chrome**
through **Playwright** (1 warm-up + 10 measured refreshes per mode), then resumes
the jobs. Outputs: `results\dashboard_timings_raw_runs.csv`,
`results\dashboard_timings_summary.csv`, `results\cagg_storage_and_refresh.csv`.
The background jobs can also be paused/resumed by hand:

```sql
SELECT job_id, proc_name, scheduled FROM timescaledb_information.jobs ORDER BY job_id;
SELECT alter_job(1000, scheduled => false);   -- repeat for 1001..1004, then => true
```

See `docs/section7_summary.md` for the gap analysis, source table, match table,
timing table, the storage/refresh tradeoff paragraph and the screenshot checklist.

> **Grafana note.** The brief is written for Grafana. Grafana is not installed
> here; the dashboards are Dash and the browser benchmark uses Playwright. The
> Grafana API, `/api/ds/query` timings and Grafana query-caching steps are
> replaced by the dashboard's own panel timings and a Playwright-driven Chrome
> run."# Smart-energy-grid" 
