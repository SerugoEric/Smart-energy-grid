-- =====================================================================
-- Section 1.1, step 1: create the single assignment database.
-- =====================================================================
--
-- PURPOSE
--   Create one PostgreSQL database for the whole assignment, enable the
--   TimescaleDB extension inside it, and make CAT the default time zone for
--   every future connection to that database.
--
-- ENVIRONMENT
--   PostgreSQL 18.6 and TimescaleDB 2.30.2 run in a Docker container named
--   "timescaledb", published on host port 5433. The superuser is "auca".
--   The native Windows PostgreSQL 18 service is NOT used; connecting to it
--   would give the wrong server and the wrong time zone.
--
-- HOW TO RUN
--   From the project root:
--       docker exec -i timescaledb psql -U auca -d postgres -f - < sql\00_create_database.sql
--
--   Equivalent, if you prefer psql on the host:
--       psql -h localhost -p 5433 -U auca -d postgres -f sql/00_create_database.sql
--
--   This file uses the psql meta-command \gexec, so it must be run with the
--   psql client. A graphical tool such as pgAdmin cannot interpret it.
--
-- WHY \gexec
--   CREATE DATABASE cannot run inside a transaction block, and a DO $$ ... $$
--   block is a transaction block, so the usual "IF NOT EXISTS" trick fails with
--   "CREATE DATABASE cannot run inside a transaction block". Instead we SELECT
--   the command text conditionally and let \gexec execute the result. If the
--   database already exists, no command text is returned and nothing happens.
--   This script is safe to run more than once.

SELECT 'CREATE DATABASE smart_energy_grid'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'smart_energy_grid'
)
\gexec

-- Move into the new database. Everything below runs inside it.
\connect smart_energy_grid

-- ---------------------------------------------------------------------
-- TimescaleDB
-- ---------------------------------------------------------------------
-- Section 1.1 requires TimescaleDB 2.10 or later with a compatible PostgreSQL
-- version. The extension must be enabled inside the assignment database; it is
-- not global to the server, so a new database needs this statement too.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------------
-- Time zone
-- ---------------------------------------------------------------------
-- Section 1.1: "Set its session time zone to Africa/Kigali and align daily
-- buckets to CAT midnight."
--
-- ALTER DATABASE sets the default for every NEW session on this database, which
-- is what makes the setting stick for psql, Grafana and Python alike. The Python
-- helper common.db.connect() also sends SET TIME ZONE per session, so a session
-- is never wrong even if this default is missing.
--
-- Africa/Kigali is UTC+2 all year with no daylight saving, which is why daily
-- time_bucket calls land exactly on CAT midnight.
ALTER DATABASE smart_energy_grid SET timezone TO 'Africa/Kigali';

-- ---------------------------------------------------------------------
-- Reconnect, on purpose
-- ---------------------------------------------------------------------
-- \connect opens a brand new backend session. This line exists because of a real
-- mistake: on the first run of this script the evidence query below reported UTC
-- instead of Africa/Kigali.
--
-- The reason is that ALTER DATABASE ... SET only affects sessions that start
-- AFTER the command completes. The session that ran the ALTER, and the session
-- that ran the earlier \connect, both keep whatever time zone they had at
-- startup, which on this server is UTC from postgresql.conf. So we must open a
-- fresh session before asking what the time zone is.
--
-- The same trap applies to every program we write: settings that live in
-- postgresql.conf or in ALTER DATABASE are per-session at connect time, which
-- is why common.db.connect() re-sends SET TIME ZONE on every connection rather
-- than trusting the database default.
\connect smart_energy_grid

-- ---------------------------------------------------------------------
-- Evidence for the Section 1.1 screenshots
-- ---------------------------------------------------------------------
-- These statements are what you screenshot for 1.1, steps 3 and 5:
-- the connection, the enabled extension, and the session time zone.
--
-- Column naming matters here. now() returns a timestamptz rendered in the
-- SESSION time zone, so labelling it "cat" would be a lie whenever the session
-- zone is wrong. We therefore label it for what it is and convert explicitly
-- for the CAT value.

-- (1) Which database, which user, which time zone, and what time is it?
SELECT current_database()   AS connected_database,
       current_user         AS connected_user,
       current_setting('TimeZone')          AS session_timezone,
       now()                               AS server_time_in_session_timezone,
       now() AT TIME ZONE 'Africa/Kigali'  AS server_time_in_cat,
       pg_typeof(now())                    AS server_time_type,
       version()                           AS server_version_text;

-- (2) Is TimescaleDB enabled here, and which version is it?
--     A row here is the proof required by 1.1 screenshot 3.
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';

-- (3) Confirm the installed version is 2.10 or later, and see what the
--     extension offers. installed_version is the running version;
--     default_version is the newest version available to install.
SELECT default_version, installed_version
FROM pg_available_extensions
WHERE name = 'timescaledb';

-- (4) The required settings from Section 1.1.2, read exactly as written there.
SHOW shared_buffers;
SHOW work_mem;
SHOW max_parallel_workers_per_gather;
SHOW jit;