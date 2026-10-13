-- =====================================================================
-- Section 6.1: three continuous aggregate views over energy_readings.
-- =====================================================================
--
-- WHAT IS CREATED
--     1.  cagg_15min_region  15-minute CAT bucket + region
--     2.  cagg_hour_region   CAT hour + region
--     3.  cagg_day_meter     CAT day + meter_id
--
--     The two regional views inner-join energy_readings with meters on
--     meter_id; the meter view groups on meter_id alone. Each view stores
--     its bucket, its grouping key, sum(energy_kwh), sum(power_kw) and a
--     reading count. timescaledb.materialized_only is set TRUE on all three
--     so real-time aggregation is disabled and every query for Sections 7.2
--     reads stored aggregates only.
--
-- ORDER OF OPERATIONS (Section 6.1.3)
--     1. Create all three with WITH NO DATA (initially unpopulated).
--     2. Verify they are empty before refreshing.
--     3. Manually refresh the entire period 2026-09-01 00:00+02 to
--        2026-09-29 00:00+02. Each CALL is timed with \timing so the
--        refresh duration is captured in seconds.
--     4. Report materialized row counts and data/index sizes.
--     5. Only then add refresh policies: three-day lookback, one-hour end
--        offset, fifteen-minute schedule. The offsets are relative to the
--        database clock, so the policies did not populate the older
--        September data - the manual refresh already did.
--
-- TIME ALIGNMENT
--     Every time_bucket uses origin 2026-09-01 00:00:00+02, so buckets open
--     on CAT midnight / top of the CAT hour (the same convention as 5.1).
--
-- HOW TO RUN
--     type sql\10_continuous_aggregates.sql
--         | docker exec -i timescaledb psql -U auca -d smart_energy_grid
--
-- REPEATABILITY
--     Safe to re-run: each view/task is created if_not_exists.

\echo '=== 1. Create the three continuous aggregates (initially empty) ==='

CREATE MATERIALIZED VIEW cagg_15min_region
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket(INTERVAL '15 minutes', r.event_time,
                   TIMESTAMPTZ '2026-09-01 00:00:00+02') AS bucket,
       m.region                                        AS region,
       sum(r.energy_kwh)                               AS sum_energy_kwh,
       sum(r.power_kw)                                 AS sum_power_kw,
       count(*)                                        AS reading_count
FROM energy_readings r
JOIN meters m USING (meter_id)
GROUP BY bucket, m.region
WITH NO DATA;

CREATE MATERIALIZED VIEW cagg_hour_region
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket(INTERVAL '1 hour', r.event_time,
                   TIMESTAMPTZ '2026-09-01 00:00:00+02') AS bucket,
       m.region                                        AS region,
       sum(r.energy_kwh)                               AS sum_energy_kwh,
       sum(r.power_kw)                                 AS sum_power_kw,
       count(*)                                        AS reading_count
FROM energy_readings r
JOIN meters m USING (meter_id)
GROUP BY bucket, m.region
WITH NO DATA;

CREATE MATERIALIZED VIEW cagg_day_meter
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket(INTERVAL '1 day', r.event_time,
                   TIMESTAMPTZ '2026-09-01 00:00:00+02') AS bucket,
       r.meter_id                                      AS meter_id,
       sum(r.energy_kwh)                               AS sum_energy_kwh,
       sum(r.power_kw)                                 AS sum_power_kw,
       count(*)                                        AS reading_count
FROM energy_readings r
GROUP BY bucket, r.meter_id
WITH NO DATA;

\echo '=== 2. Materialized-only settings and initial (empty) state ==='
SELECT view_name, materialized_only
FROM timescaledb_information.continuous_aggregates
WHERE view_name IN ('cagg_15min_region', 'cagg_hour_region', 'cagg_day_meter')
ORDER BY view_name;

SELECT 'cagg_15min_region' AS view_name, count(*) AS rows FROM cagg_15min_region
UNION ALL
SELECT 'cagg_hour_region', count(*) FROM cagg_hour_region
UNION ALL
SELECT 'cagg_day_meter', count(*) FROM cagg_day_meter;

\echo ''
\echo '=== 3. Manual refresh of the entire period (timed) ==='
\timing on
CALL refresh_continuous_aggregate('cagg_15min_region',
    TIMESTAMPTZ '2026-09-01 00:00:00+02', TIMESTAMPTZ '2026-09-29 00:00:00+02');
CALL refresh_continuous_aggregate('cagg_hour_region',
    TIMESTAMPTZ '2026-09-01 00:00:00+02', TIMESTAMPTZ '2026-09-29 00:00:00+02');
CALL refresh_continuous_aggregate('cagg_day_meter',
    TIMESTAMPTZ '2026-09-01 00:00:00+02', TIMESTAMPTZ '2026-09-29 00:00:00+02');
\timing off

\echo ''
\echo '=== 4. Populated row counts and sample rows ==='
SELECT 'cagg_15min_region' AS view_name, count(*) AS rows FROM cagg_15min_region
UNION ALL
SELECT 'cagg_hour_region', count(*) FROM cagg_hour_region
UNION ALL
SELECT 'cagg_day_meter', count(*) FROM cagg_day_meter;

SELECT bucket, region, sum_energy_kwh, sum_power_kw, reading_count
FROM cagg_15min_region
ORDER BY bucket, region LIMIT 5;

SELECT bucket, region, sum_energy_kwh, sum_power_kw, reading_count
FROM cagg_hour_region
ORDER BY bucket, region LIMIT 5;

SELECT bucket, meter_id, sum_energy_kwh, sum_power_kw, reading_count
FROM cagg_day_meter
ORDER BY bucket, meter_id LIMIT 5;

\echo ''
\echo '=== 5. Materialized data and index sizes per aggregate ==='
WITH agg AS (
    SELECT view_name, materialization_hypertable_schema AS h_schema,
           materialization_hypertable_name AS h_name
    FROM timescaledb_information.continuous_aggregates
    WHERE view_name IN ('cagg_15min_region', 'cagg_hour_region', 'cagg_day_meter')
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
      ON c.hypertable_schema = a.h_schema AND c.hypertable_name = a.h_name
    GROUP BY a.view_name
)
SELECT view_name,
       pg_size_pretty(data_bytes)  AS data,
       pg_size_pretty(index_bytes) AS index,
       pg_size_pretty(total_bytes) AS total,
       round(total_bytes / 1024.0 / 1024.0, 3) AS total_mb
FROM sizes
ORDER BY view_name;

\echo ''
\echo '=== 6. Policies: 3-day lookback, 1-hour end offset, 15-minute schedule ==='
SELECT add_continuous_aggregate_policy('cagg_15min_region',
    start_offset => INTERVAL '3 days',  end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('cagg_hour_region',
    start_offset => INTERVAL '3 days',  end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('cagg_day_meter',
    start_offset => INTERVAL '3 days',  end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);

SELECT job_id, hypertable_name, schedule_interval, scheduled,
       config->>'start_offset' AS start_offset,
       config->>'end_offset'   AS end_offset
FROM timescaledb_information.jobs
WHERE proc_name IN ('policy_refresh_continuous_aggregate',
                    'policy_continuous_aggregate',
                    'policy_materialize_continuous_aggregate')
ORDER BY job_id;