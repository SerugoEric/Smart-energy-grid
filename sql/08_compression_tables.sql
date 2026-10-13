-- =====================================================================
-- Section 4.1: the two compressed configurations.
-- =====================================================================
--
-- WHAT IS CREATED
--     energy_time_compressed   one-day chunks, compression ORDER BY
--                              event_time DESC, NO segmentation.
--     energy_meter_compressed  one-day chunks, compression ORDER BY
--                              event_time DESC, segmented by meter_id.
--
-- WHY ONE-DAY CHUNKS
--     1-day is the Section 3 baseline table (energy_readings) and the
--     interval the assignment has used since 1.2. Using it as the chosen
--     interval makes energy_readings the uncompressed baseline for the
--     4.2 storage ratio and the 4.3 per-query improvement, exactly as
--     Section 4.3.2 asks.
--
-- COMPRESSION ORDER AND SEGMENTATION
--     energy_time_compressed: event_time DESC, no segmentby. This is the
--     columnstore order a pure time-series table would use; every meter
--     appears in every compressed batch.
--     energy_meter_compressed: same ORDER BY event_time DESC but segment
--     by meter_id, so each meter's rows form their own segments. The
--     Section 4.4 question is whether meter segmentation accelerates the
--     single-meter workload (Q4) and hurts or helps the all-meter
--     workloads (Q1-Q3, Q5).
--
-- POLICIES
--     Each table gets a compression policy that compresses chunks whose
--     end is more than 48 hours old. Both policies are immediately
--     paused (scheduled => false) so background jobs cannot compress
--     chunks during the Section 4.3 measurements. Section 4.3.3 resumes
--     them afterwards.
--
-- HOW TO RUN
--     type sql\08_compression_tables.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid
--
-- REPEATABILITY
--     Safe to re-run if the tables exist: the script DROPs them first.
--     Section 4.1.6 requires keeping all five tables, so only re-run this
--     after a deliberate scratch reset.

\echo '=== 1. Drop any previous copies ==='
DROP TABLE IF EXISTS energy_time_compressed;
DROP TABLE IF EXISTS energy_meter_compressed;

\echo '=== 2. Create energy_time_compressed (1-day, order by event_time DESC) ==='

CREATE TABLE energy_time_compressed (
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
           'energy_time_compressed',
           by_range('event_time', INTERVAL '1 day'),
           create_default_indexes => FALSE,
           if_not_exists           => TRUE
       );

ALTER TABLE energy_time_compressed SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'event_time DESC'
);

\echo '=== 3. Create energy_meter_compressed (1-day, order by event_time DESC, segment by meter_id) ==='

CREATE TABLE energy_meter_compressed (
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
           'energy_meter_compressed',
           by_range('event_time', INTERVAL '1 day'),
           create_default_indexes => FALSE,
           if_not_exists           => TRUE
       );

ALTER TABLE energy_meter_compressed SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'event_time DESC',
    timescaledb.compress_segmentby = 'meter_id'
);

\echo '=== 4. Matching indexes (same pair as the Section 3 tables) ==='
CREATE INDEX energy_time_compressed_et ON energy_time_compressed (event_time);
CREATE INDEX energy_time_compressed_mt ON energy_time_compressed (meter_id, event_time);
CREATE INDEX energy_meter_compressed_et ON energy_meter_compressed (event_time);
CREATE INDEX energy_meter_compressed_mt ON energy_meter_compressed (meter_id, event_time);

\echo '=== 5. Compression settings as configured ==='
SELECT hypertable_name, attname, segmentby_column_index, orderby_column_index,
       orderby_asc
FROM timescaledb_information.compression_settings
WHERE hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
ORDER BY hypertable_name, attname;

\echo '=== 6. Compression policies added then paused ==='
SELECT add_compression_policy('energy_time_compressed', INTERVAL '48 hours', if_not_exists => TRUE);
SELECT add_compression_policy('energy_meter_compressed', INTERVAL '48 hours', if_not_exists => TRUE);

DO $$
DECLARE
    job_row record;
BEGIN
    -- Only the two compression policies are paused here. Default upkeep jobs
    -- (telemetry, job-stat retention) are left untouched.
    FOR job_row IN
        SELECT j.job_id, j.hypertable_name
        FROM timescaledb_information.jobs j
        WHERE j.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
        ORDER BY j.hypertable_name
    LOOP
        PERFORM alter_job(job_row.job_id, scheduled => false);
        RAISE NOTICE 'Paused job % on %', job_row.job_id, job_row.hypertable_name;
    END LOOP;
END
$$;

SELECT j.job_id, j.hypertable_name, j.schedule_interval,
       j.proc_name, j.scheduled
FROM timescaledb_information.jobs j
WHERE j.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
ORDER BY j.hypertable_name;

\echo '=== 7. Both tables are empty before loading ==='
SELECT 'energy_time_compressed' AS table_name, count(*) AS rows FROM energy_time_compressed
UNION ALL
SELECT 'energy_meter_compressed', count(*) FROM energy_meter_compressed;