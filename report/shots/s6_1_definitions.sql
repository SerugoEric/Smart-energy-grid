-- Section 6.1 screenshot: definitions of every continuous aggregate view.
\echo '=== 6.1  ALL CONTINUOUS AGGREGATE VIEW DEFINITIONS ==='
SELECT view_name, view_definition
FROM timescaledb_information.continuous_aggregates
WHERE view_name IN ('cagg_15min_region', 'cagg_hour_region', 'cagg_day_meter')
ORDER BY view_name;
