-- Section 6.1 screenshot: refresh policy settings for every continuous aggregate
-- plus the materialization mode of each view.
\echo '=== 6.1  CONTINUOUS AGGREGATE REFRESH POLICY SETTINGS ==='
SELECT job_id, proc_name, scheduled, config
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_refresh_continuous_aggregate'
ORDER BY job_id;
\echo '=== MATERIALIZATION MODE OF EACH VIEW ==='
SELECT view_name, materialized_only
FROM timescaledb_information.continuous_aggregates
WHERE view_name LIKE 'cagg_%'
ORDER BY view_name;
