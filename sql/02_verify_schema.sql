-- =====================================================================
-- Section 1.2, step 5: verify the three structures.
-- =====================================================================
--
-- PURPOSE
--     Prove what Section 1.2 asks us to prove:
--       1. all three tables exist
--       2. the column names and types are exactly as specified
--       3. energy_readings really is a hypertable
--       4. its chunk interval is one day
--
-- HOW TO RUN (Windows CMD)
--     type sql\02_verify_schema.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid
--
-- WHY information_schema INSTEAD OF \d
--     \d is a psql meta-command and its layout is for humans. For evidence in a
--     report, information_schema gives named columns you can screenshot, and the
--     same queries work in any client. Use \d for interactive poking.

-- ---------------------------------------------------------------------
-- 1. All three tables exist
-- ---------------------------------------------------------------------
-- table_type will read BASE TABLE for all three. A hypertable still reports as a
-- base table in information_schema, because a hypertable is an ordinary
-- PostgreSQL table with extra internal state. That is why check 3 below is
-- needed as well.
SELECT table_name,
       table_type
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- ---------------------------------------------------------------------
-- 2. Column names and exact types
-- ---------------------------------------------------------------------
-- format_type() renders the real declared type, so BIGINT appears as bigint and
-- TIMESTAMPTZ as timestamp with time zone. Reading data_type instead would give
-- the more verbose "bigint"/"timestamp with time zone" mapping in a different
-- shape, which is easier to misread in a screenshot.
SELECT c.relname  AS table_name,
       a.attnum   AS position,
       a.attname  AS column_name,
       format_type(a.atttypid, a.atttypmod) AS column_type
FROM pg_attribute a
JOIN pg_class     c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('energy_live', 'energy_readings', 'meters')
  AND a.attnum > 0            -- skip system columns
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;

-- ---------------------------------------------------------------------
-- 2b. Both reading tables have exactly eight columns
-- ---------------------------------------------------------------------
-- The assignment is specific about the count, so assert it rather than trusting
-- the eye. Both rows must show 8.
SELECT table_name,
       count(*) AS column_count
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('energy_live', 'energy_readings')
GROUP BY table_name
ORDER BY table_name;

-- ---------------------------------------------------------------------
-- 3. energy_readings is a hypertable, and energy_live is NOT
-- ---------------------------------------------------------------------
-- The decisive test. One row for energy_readings and none for energy_live is the
-- required outcome. If energy_live also appeared here, Section 1.3's pilot table
-- would have been created as a hypertable by mistake.
SELECT hypertable_name,
       num_dimensions,
       num_chunks
FROM timescaledb_information.hypertables
WHERE hypertable_name IN ('energy_live', 'energy_readings')
ORDER BY hypertable_name;

-- The negative case, stated explicitly so the screenshot proves it.
SELECT 'energy_live is a hypertable' AS check,
       count(*)                    AS should_be_zero
FROM timescaledb_information.hypertables
WHERE hypertable_name = 'energy_live';

-- ---------------------------------------------------------------------
-- 4. The chunk interval is one day
-- ---------------------------------------------------------------------
-- time_interval is reported in microseconds by this catalog, so one day is
-- 86,400,000,000. See the check below, which prints the interval in days too.
SELECT hypertable_name,
       column_name,
       column_type,
       time_interval      AS chunk_interval_microseconds,
       integer_interval,
       time_interval / 86.4e9 AS chunk_interval_days
FROM timescaledb_information.dimensions
WHERE hypertable_name = 'energy_readings';

-- ---------------------------------------------------------------------
-- 5. Chunk count, and the chunks that exist so far
-- ---------------------------------------------------------------------
-- The table is empty, so there should be 0 chunks. Chunks are created on INSERT,
-- not at hypertable creation. That is expected and is not a failure.
SELECT count(*) AS chunk_count
FROM timescaledb_information.chunks
WHERE hypertable_name = 'energy_readings';

-- ---------------------------------------------------------------------
-- 6. Indexes on all three tables
-- ---------------------------------------------------------------------
-- meters must show its primary key. The two reading tables are expected to show
-- NO index yet: 01_schema.sql suppressed the automatic partitioning-column index
-- on purpose, and Section 3.1.2 adds the required matching pair to all three
-- tables in 03_indexes.sql.
SELECT tablename,
       indexname,
       indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('energy_live', 'energy_readings', 'meters')
ORDER BY tablename, indexname;

-- ---------------------------------------------------------------------
-- 7. Row counts and the session time zone
-- ---------------------------------------------------------------------
-- All three must read 0 before Section 1.2 step 4 loads the meters, and
-- session_timezone must be Africa/Kigali (Section 1.1).
SELECT 'energy_live'     AS table_name, count(*) AS row_count FROM energy_live
UNION ALL
SELECT 'energy_readings', count(*) FROM energy_readings
UNION ALL
SELECT 'meters',          count(*) FROM meters
ORDER BY table_name;

SELECT current_database()                 AS connected_database,
       current_user                       AS connected_user,
       current_setting('TimeZone')        AS session_timezone,
       version()                          AS postgres_version;

-- Time zone shown two ways, as in the Phase 1.1 evidence.
SELECT now()                              AS now_in_session_timezone,
       now() AT TIME ZONE 'Africa/Kigali' AS same_instant_in_cat;