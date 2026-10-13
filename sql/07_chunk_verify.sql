-- =====================================================================
-- Section 3.1 steps 2-3: verify the three configurations match.
-- =====================================================================
--
-- WHAT MUST BE TRUE (Section 3.1.3)
--     10,643,735 rows and 4,000 meters in EACH table.
--     Identical earliest and latest event_time in all three.
--     sum(power_kw) and sum(energy_kwh) agreeing to within 0.001.
--
-- WHY THE TOLERANCE EXISTS
--     DOUBLE PRECISION addition is not associative, and a different physical
--     row order (which the three chunk layouts produce) changes the order the
--     additions happen in. The last bits of the sum can therefore differ even
--     though every stored value is identical. 0.001 is the tolerance the
--     assignment allows; anything larger would mean real data differences.
--
-- HOW TO RUN
--     type sql\07_chunk_verify.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

\echo '=== 1. Chunk interval and chunk count per table ==='
SELECT d.hypertable_name,
       d.time_interval,
       (SELECT count(*) FROM timescaledb_information.chunks c
         WHERE c.hypertable_name = d.hypertable_name) AS chunk_count
FROM timescaledb_information.dimensions d
WHERE d.hypertable_name IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY d.time_interval;

\echo '=== 2. Date range covered by the chunks themselves ==='
SELECT hypertable_name,
       min(range_start) AS first_chunk_start,
       max(range_end)   AS last_chunk_end
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
GROUP BY hypertable_name
ORDER BY hypertable_name;

\echo '=== 3. Row counts, meters and date range per table ==='
SELECT 'energy_readings'       AS table_name, count(*) AS row_count,
       count(DISTINCT meter_id) AS meter_count,
       min(event_time)          AS earliest,
       max(event_time)          AS latest
FROM energy_readings
UNION ALL
SELECT 'energy_readings_3h', count(*), count(DISTINCT meter_id),
       min(event_time), max(event_time)
FROM energy_readings_3h
UNION ALL
SELECT 'energy_readings_week', count(*), count(DISTINCT meter_id),
       min(event_time), max(event_time)
FROM energy_readings_week
ORDER BY table_name;

\echo '=== 4. Numeric sums per table ==='
SELECT 'energy_readings'       AS table_name,
       sum(power_kw)  AS sum_power_kw,
       sum(energy_kwh) AS sum_energy_kwh
FROM energy_readings
UNION ALL
SELECT 'energy_readings_3h', sum(power_kw), sum(energy_kwh)
FROM energy_readings_3h
UNION ALL
SELECT 'energy_readings_week', sum(power_kw), sum(energy_kwh)
FROM energy_readings_week
ORDER BY table_name;

\echo '=== 5. Differences against the one-day baseline (must be < 0.001) ==='
WITH baseline AS (
    SELECT sum(power_kw) AS p, sum(energy_kwh) AS e FROM energy_readings
)
SELECT 'energy_readings_3h' AS compared,
       abs(s.sum_power_kw - b.p)  AS power_difference,
       abs(s.sum_energy_kwh - b.e) AS energy_difference,
       CASE WHEN abs(s.sum_power_kw - b.p)  < 0.001
             AND abs(s.sum_energy_kwh - b.e) < 0.001
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM (SELECT sum(power_kw) AS sum_power_kw, sum(energy_kwh) AS sum_energy_kwh
      FROM energy_readings_3h) s, baseline b
UNION ALL
SELECT 'energy_readings_week',
       abs(s.sum_power_kw - b.p),
       abs(s.sum_energy_kwh - b.e),
       CASE WHEN abs(s.sum_power_kw - b.p)  < 0.001
             AND abs(s.sum_energy_kwh - b.e) < 0.001
            THEN 'PASS' ELSE 'FAIL' END
FROM (SELECT sum(power_kw) AS sum_power_kw, sum(energy_kwh) AS sum_energy_kwh
      FROM energy_readings_week) s, baseline b;

\echo '=== 6. Indexes on each table (must be identical in shape) ==='
SELECT c.relname AS table_name,
       i.relname AS index_name,
       pg_get_indexdef(ix.indexrelid) AS index_definition
FROM pg_index ix
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY c.relname, i.relname;

\echo '=== 7. Storage per configuration ==='
SELECT 'energy_readings' AS table_name,
       pg_size_pretty(sum(pg_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass)))  AS data,
       pg_size_pretty(sum(pg_indexes_size(format('%I.%I', chunk_schema, chunk_name)::regclass)))   AS indexes,
       pg_size_pretty(sum(pg_total_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass))) AS total
FROM timescaledb_information.chunks WHERE hypertable_name = 'energy_readings'
UNION ALL
SELECT 'energy_readings_3h',
       pg_size_pretty(sum(pg_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass))),
       pg_size_pretty(sum(pg_indexes_size(format('%I.%I', chunk_schema, chunk_name)::regclass))),
       pg_size_pretty(sum(pg_total_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass)))
FROM timescaledb_information.chunks WHERE hypertable_name = 'energy_readings_3h'
UNION ALL
SELECT 'energy_readings_week',
       pg_size_pretty(sum(pg_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass))),
       pg_size_pretty(sum(pg_indexes_size(format('%I.%I', chunk_schema, chunk_name)::regclass))),
       pg_size_pretty(sum(pg_total_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass)))
FROM timescaledb_information.chunks WHERE hypertable_name = 'energy_readings_week';

\echo '=== 8. Statistics are current (Section 3.2.1 requires ANALYZE) ==='
\echo 'pg_stat_user_tables is not used here: its counters live in shared memory'
\echo 'and are lost when the container restarts, so last_analyze can read NULL'
\echo 'even though ANALYZE ran. pg_class.reltuples and pg_stats are written to'
\echo 'the catalogs by ANALYZE and do survive a restart, and the planner reads'
\echo 'those. The ANALYZE commands themselves are recorded in the benchmark logs'
\echo '  logs/chunk_benchmark_2026-10-07_00-09-03.txt lines 15-18'
\echo '  logs/compressed_benchmark_2026-10-07_00-50-20.txt lines 16-19'
WITH chunk_rows AS (
    SELECT h.hypertable_name, h.chunk_name, c.reltuples
    FROM timescaledb_information.chunks h
    JOIN pg_class c
      ON c.oid = format('%I.%I', h.chunk_schema, h.chunk_name)::regclass
    WHERE h.hypertable_name IN
          ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
),
chunk_stats AS (
    SELECT h.hypertable_name, h.chunk_name, count(*) AS columns_analysed
    FROM timescaledb_information.chunks h
    JOIN pg_stats s
      ON s.schemaname = h.chunk_schema AND s.tablename = h.chunk_name
    WHERE h.hypertable_name IN
          ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
    GROUP BY h.hypertable_name, h.chunk_name
)
SELECT r.hypertable_name,
       count(*)                                        AS chunks,
       sum(r.reltuples)::bigint                        AS planner_row_estimate,
       sum(COALESCE(s.columns_analysed, 0))            AS column_statistics,
       count(*) FILTER (WHERE s.columns_analysed > 0)  AS chunks_with_stats
FROM chunk_rows r
LEFT JOIN chunk_stats s
       ON s.hypertable_name = r.hypertable_name
      AND s.chunk_name = r.chunk_name
GROUP BY r.hypertable_name
ORDER BY 1;

\echo '--- last_analyze as reported for the hypertable root relations ---'
SELECT relname, last_analyze, n_live_tup
FROM pg_stat_user_tables
WHERE relname IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY relname;
