-- Section 1.2 screenshot: chunk interval of the hypertable and the 4,000 rows.
\echo '=== Section 1.2 - hypertable chunk interval ==='
SELECT h.hypertable_name, d.primary_dimension, d.column_name, d.time_interval
FROM timescaledb_information.hypertables h
JOIN timescaledb_information.dimensions d
  ON d.hypertable_schema = h.hypertable_schema
 AND d.hypertable_name = h.hypertable_name
WHERE h.hypertable_name = 'energy_readings';

\echo '=== Section 1.2 - meters metadata row count ==='
SELECT count(*) AS meters_rows FROM meters;
