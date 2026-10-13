-- Section 6.2 screenshot: definitions of the separate test table and of the
-- hourly continuous aggregate built over it.
\echo '=== 6.2  TEST TABLE DEFINITION ==='
\d energy_test
\echo '=== 6.2  TEST AGGREGATE VIEW DEFINITION ==='
SELECT view_name, materialized_only, view_definition
FROM timescaledb_information.continuous_aggregates
WHERE view_name = 'energy_test_hourly';
