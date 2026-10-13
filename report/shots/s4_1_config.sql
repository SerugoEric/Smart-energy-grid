-- Section 4.1 screenshot: the two compression configurations and their policies.
\echo '=== 4.1  compression settings of the two configurations ==='
SELECT hypertable_name,
       attname,
       segmentby_column_index,
       orderby_column_index,
       orderby_asc,
       orderby_nullsfirst
FROM timescaledb_information.compression_settings
ORDER BY hypertable_name, coalesce(segmentby_column_index, 99),
         coalesce(orderby_column_index, 99);

\echo '=== 4.1  background policies (compression and refresh) ==='
SELECT job_id, proc_name, scheduled, schedule_interval, hypertable_name
FROM timescaledb_information.jobs
ORDER BY job_id;
