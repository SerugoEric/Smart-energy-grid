-- Section 3.1 screenshot: indexes and storage per configuration.
\echo '=== 3.1  indexes (identical shape on all three tables) ==='
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY tablename, indexname;

\echo '=== 3.1  storage, summed over the chunk relations ==='
SELECT 'energy_readings' AS table_name,
       pg_size_pretty(sum(pg_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass))) AS data,
       pg_size_pretty(sum(pg_indexes_size(format('%I.%I', chunk_schema, chunk_name)::regclass))) AS indexes,
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
FROM timescaledb_information.chunks WHERE hypertable_name = 'energy_readings_week'
ORDER BY table_name;
