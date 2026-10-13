-- =====================================================================
-- Section 3.1 steps 1-2: the three chunk-interval configurations.
-- =====================================================================
--
-- WHAT IS CREATED
--     energy_readings        one-day chunks     (exists, created in 01_schema)
--     energy_readings_3h     three-hour chunks
--     energy_readings_week   one-week chunks
--
--     All three carry the same eight columns, the same event_time partitioning
--     and, after 04_indexes.sql, the same two non-unique indexes.
--
-- WHY THE CHUNK WIDTHS ARE EXPRESSED AS INTERVALS
--     Three hours and one week are not whole numbers of microseconds that fit
--     an integer dimension, and the generator's period is 28 days, which divides
--     evenly by 1 day, 1 week but not by 3 hours into whole weeks only.
--     28 days = 224 three-hour chunks and = 4 one-week chunks, so both new
--     configurations produce whole chunks across the period.
--
-- WHY THE COPY IS DONE HERE RATHER THAN RE-GENERATING
--     Section 2.3 produced ONE cleaned dataset that every later experiment must
--     share. Reading energy_readings and inserting into the two new hypertables
--     guarantees byte-identical inputs; a second pass over the generator would
--     risk a different random stream if the generator's settings ever changed.
--
-- HOW TO RUN (from the project root, either shell)
--     type sql\06_chunk_tables.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid
--
-- REPEATABILITY
--     Safe to re-run: CREATE TABLE IF NOT EXISTS and DROP of the copies only.
--     The COPY steps TRUNCATE first, so a second run re-copies rather than
--     doubling the rows.

\echo '=== 1. Create the two additional hypertables ==='

CREATE TABLE IF NOT EXISTS energy_readings_3h (
    meter_id      BIGINT,
    event_time    TIMESTAMPTZ,
    received_time TIMESTAMPTZ,
    power_kw      DOUBLE PRECISION,
    voltage_v     DOUBLE PRECISION,
    current_a     DOUBLE PRECISION,
    frequency_hz  DOUBLE PRECISION,
    energy_kwh    DOUBLE PRECISION
);

SELECT create_hypertable(
           'energy_readings_3h',
           by_range('event_time', INTERVAL '3 hours'),
           create_default_indexes => FALSE,
           if_not_exists           => TRUE
       );

CREATE TABLE IF NOT EXISTS energy_readings_week (
    meter_id      BIGINT,
    event_time    TIMESTAMPTZ,
    received_time TIMESTAMPTZ,
    power_kw      DOUBLE PRECISION,
    voltage_v     DOUBLE PRECISION,
    current_a     DOUBLE PRECISION,
    frequency_hz  DOUBLE PRECISION,
    energy_kwh    DOUBLE PRECISION
);

SELECT create_hypertable(
           'energy_readings_week',
           by_range('event_time', INTERVAL '1 week'),
           create_default_indexes => FALSE,
           if_not_exists           => TRUE
       );

\echo '=== 2. Chunk intervals ==='
SELECT hypertable_name, column_name, time_interval
FROM timescaledb_information.dimensions
WHERE hypertable_name IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY hypertable_name;

\echo '=== 3. Copy the cleaned rows (TRUNCATE makes this re-runnable) ==='

TRUNCATE energy_readings_3h;
TRUNCATE energy_readings_week;

\timing on
INSERT INTO energy_readings_3h
    SELECT * FROM energy_readings;
INSERT INTO energy_readings_week
    SELECT * FROM energy_readings;
\timing off

SELECT 'energy_readings'       AS table_name, count(*) AS rows FROM energy_readings
UNION ALL
SELECT 'energy_readings_3h',   count(*) FROM energy_readings_3h
UNION ALL
SELECT 'energy_readings_week', count(*) FROM energy_readings_week;

-- Indexes are added by sql/04_indexes.sql. Run it next, then verify with
-- sql/07_chunk_verify.sql.
