-- Section 6.1 screenshot: sample populated rows from every continuous aggregate.
\echo '=== 6.1  SAMPLE ROWS, cagg_15min_region ==='
SELECT * FROM cagg_15min_region ORDER BY bucket LIMIT 3;
\echo '=== SAMPLE ROWS, cagg_hour_region ==='
SELECT * FROM cagg_hour_region ORDER BY bucket LIMIT 3;
\echo '=== SAMPLE ROWS, cagg_day_meter ==='
SELECT * FROM cagg_day_meter ORDER BY bucket LIMIT 3;
