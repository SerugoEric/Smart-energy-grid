# Section 1.1 — Environment details

Values measured by `python ingestion\capture_environment.py` on **6 October 2026**
(from `logs/environment_capture_2026-10-06_23-53-33.txt`) plus the storage-type and
clock checks listed below.

---

## 1.1.1 Services and database

Host is Windows. Both services run in Docker on the same machine.

| Item | Value |
|---|---|
| PostgreSQL container | `timescaledb`, image `timescale/timescaledb:latest-pg18` |
| PostgreSQL host port | `5433` (container port 5432) |
| PostgreSQL superuser | `auca` |
| EMQX container | `emqx`, image `emqx/emqx:latest`, version **6.3.1** |
| Native Windows PostgreSQL 18 service | exists but **not used** |
| Database name | `smart_energy_grid` |
| TimescaleDB extension enabled | yes — `timescaledb 2.30.2` |
| Session time zone | `Africa/Kigali` (confirmed in-session, `SHOW timezone`) |

> **Note for the report.** The native Windows PostgreSQL 18 service was
> deliberately not used, so a reader does not assume two installations
> contributed data.

---

## 1.1.2 Hardware, software versions and settings

### Machine

| Item | Value |
|---|---|
| Machine identifier | `DESKTOP-94DVA7R/AMD64` |
| CPU model (Win32_Processor) | **Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz** |
| Physical cores | **2** |
| Logical processors | **4** |
| Host installed RAM | **7.85 GB** |
| HostMemoryLoadPercent at capture | **95%** |
| Operating system and version | **Windows 10, version 10.0.19045, 64-bit** |
| Storage type | **SSD** — SanDisk SD8SN8U-256G-1006 (256 GB) |

### Software versions

| Component | Version |
|---|---|
| Python | **3.13.5** (`C:\Python313\python.exe`) |
| EMQX | **6.3.1** (from `emqx ctl status`) |
| PostgreSQL | **18.6** (`SELECT version()`) |
| TimescaleDB | **2.30.2** (installed and default) |

### Required PostgreSQL settings (Section 1.1.2)

Read with the exact `SHOW` commands the assignment names:

| Setting | Value |
|---|---|
| `shared_buffers` | **982856kB** |
| `work_mem` | **15357kB** |
| `max_parallel_workers_per_gather` | **2** |
| `jit` | **off** |

### Machine clock

`w32tm /query /status` reports that the Windows Time service is **stopped**, so no
NTP client is active. Measuring the offset directly against a live HTTP `Date`
header (google.com, 6 Oct 2026 21:55 UTC) put the system UTC **1 second behind**
network time. The clock is therefore effectively synchronised (within 1 s), which
satisfies Section 1.1.3 ("keep the machine clock synchronized") within the
measurement precision used throughout this report. All execution times are
recorded in CAT.

---

## 1.1.2 Execution environment statement

> PostgreSQL 18 and TimescaleDB 2.30.2 run in a Docker container named
> `timescaledb` on a Windows 10 host, published on host port 5433. The container
> declares **no CPU limit** (`HostConfig.NanoCpus` = 0) and **no memory limit**
> (`HostConfig.Memory` = 0), so Docker imposes no explicit per-container cap. The
> host has **4 logical processors (2 physical cores)** and **7.85 GB of RAM**.
>
> One constraint matters for the benchmarks: `docker stats` reports the
> `timescaledb` container against a **3.749 GiB** ceiling (Docker Desktop's WSL2
> virtual machine), and the host was at **95% memory load** when the environment
> was captured. Section 3.2.2 requires only the measured workload to run during
> timing, so these figures are the reason that requirement matters here.

Evidence, all from the capture log:

| Evidence | Source |
|---|---|
| Container image | `timescale/timescaledb:latest-pg18` |
| CPU limit | `NanoCpus` not limited; `CpuQuota` none; `CpusetCpus` not set |
| Memory limit | `Memory` 0 = unlimited |
| Live use at capture | `timescaledb` 82% CPU, 2.014 GiB / 3.749 GiB; `emqx` 0.65% CPU, 207.5 MiB |
| Volume mount | `timescaledb_data` → `/var/lib/postgresql` |
| PostgreSQL data directory | `/var/lib/postgresql/18/docker` (inside the container) |
| Database size after Section 2 | **4059 MB** |

---

## Disk space: the container figure is misleading

`docker exec timescaledb df -h` reports **947.3 GB available** on an `overlay`
filesystem. That is *not* real free space. It is inside Docker Desktop's WSL2
virtual disk, which is itself backed by the Windows C: drive.

The number that actually constrains us is the host's:

| Location | Total | Free |
|---|---|---|
| Host C: (holds the Docker virtual disk) | 237.86 GB | **13.90 GB** |
| Container overlay (not the real limit) | 1006.9 GB | 947.3 GB |

Three uncompressed copies of 10.6M rows already occupy about 4 GB, and the Section
4 compressed tables are kept on top. 13.90 GB is sufficient for the remaining
work, but the intermediate CSVs were deleted after Section 2.1 verification, which
Section 2.1.6 permits.

---

## Screenshots (take with taskbar + clock visible)

| # | Screenshot | What must be visible |
|---|---|---|
| 1 | Running broker | `docker ps`: `emqx` Up; or EMQX dashboard http://localhost:18083 |
| 2 | Connection to the assignment database | psql on port 5433 as `auca`, `current_database()` = `smart_energy_grid` |
| 3 | Enabled extension | `pg_extension` row: `timescaledb \| 2.30.2` |
| 4 | Session time zone | `SHOW timezone` = `Africa/Kigali` |
| 5 | Environment capture | capture script output: CPU, RAM, container limits, versions |
| 6 | CAT proof | `now()` shown in the session zone and in CAT simultaneously |
| 7 | Storage type | `Get-PhysicalDisk` = SSD (SanDisk SN8SN8U-256G-1006) |
| 8 | Clock | `w32tm /query /status` (stopped) + HTTP Date offset ≈ 0 s |

---

## Carried forward to later phases

1. **TimescaleDB 2.30.2** is past the 2.18 boundary where compression was renamed
   to **columnstore**. Section 4 must use the syntax this build accepts. The build
   exposes the settings `timescaledb.compress_orderby_default_function` and
   `timescaledb.compress_segmentby_default_function`, which are the modern names
   for the compression clause used by `ALTER TABLE ... SET (timescaledb.compress)`.

2. **2 physical cores / 7.85 GB RAM.** `max_parallel_workers_per_gather` = 2, so
   Section 3/4 timings are bounded by two parallel workers and will be noisier
   than on a server. Report median values, not minimums, and keep the machine
   otherwise idle.

3. **Chunk boundaries are UTC-day aligned, not CAT-midnight aligned.**
   TimescaleDB aligns time chunks to the Unix epoch, so a one-day chunk runs
   00:00–00:00 UTC = **02:00–02:00 CAT**. Section 1.1 requires daily *buckets* at
   CAT midnight, which is a different thing and is achieved in Section 6 with an
   explicit `time_bucket` origin of `2026-09-01 00:00:00+02`. The chunk ranges
   measured in Section 3.1 confirm this: first chunk starts `2026-08-31 02:00 +02`.