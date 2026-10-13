-- Section 3.2.1: update table statistics with ANALYZE after loading.
--
-- The benchmark harness already runs ANALYZE before every timed run, and those
-- runs are recorded in logs/chunk_benchmark_*.txt and
-- logs/compressed_benchmark_*.txt. This file repeats the same statements on
-- demand so the step can be shown on its own, and then reports the statistics
-- the planner actually reads.
--
-- pg_stat_user_tables is not used as evidence here: its counters live in
-- shared memory and are lost when the container restarts, so last_analyze can
-- read NULL even though ANALYZE ran. pg_class.reltuples and pg_stats are
-- written to the catalogs by ANALYZE and survive a restart.

\echo '=== Section 3.2.1  ANALYZE after loading ==='
SELECT now() AS started_at, current_setting('TimeZone') AS session_time_zone;

ANALYZE energy_readings;
ANALYZE energy_readings_3h;
ANALYZE energy_readings_week;
ANALYZE energy_time_compressed;
ANALYZE energy_meter_compressed;
ANALYZE meters;
ANALYZE energy_live;

\echo '=== planner statistics now present on every chunk ==='
WITH chunk_rows AS (
    SELECT h.hypertable_name, h.chunk_name, c.reltuples, c.relpages
    FROM timescaledb_information.chunks h
    JOIN pg_class c
      ON c.oid = format('%I.%I', h.chunk_schema, h.chunk_name)::regclass
),
chunk_stats AS (
    SELECT h.hypertable_name, h.chunk_name, count(*) AS columns_analysed
    FROM timescaledb_information.chunks h
    JOIN pg_stats s
      ON s.schemaname = h.chunk_schema AND s.tablename = h.chunk_name
    GROUP BY h.hypertable_name, h.chunk_name
)
SELECT r.hypertable_name                       AS hypertable,
       count(*)                                AS chunks,
       sum(r.reltuples)::bigint                AS estimated_rows,
       sum(r.relpages)                         AS estimated_pages,
       sum(COALESCE(s.columns_analysed, 0))     AS column_statistics,
       count(*) FILTER (WHERE s.columns_analysed > 0) AS chunks_with_stats
FROM chunk_rows r
LEFT JOIN chunk_stats s
       ON s.hypertable_name = r.hypertable_name
      AND s.chunk_name = r.chunk_name
GROUP BY r.hypertable_name
ORDER BY 1;

\echo '=== non-hypertable tables ==='
SELECT relname                          AS table_name,
       last_analyze                     AS last_analyze,
       n_live_tup                       AS live_tuples
FROM pg_stat_user_tables
WHERE relname IN ('meters', 'energy_live')
ORDER BY relname;

SELECT now() AS finished_at;
