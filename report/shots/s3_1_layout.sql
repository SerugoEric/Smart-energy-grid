-- Section 3.1 screenshot: chunk interval, chunk count and chunk date ranges.
\echo '=== 3.1  chunk interval and chunk count ==='
SELECT d.hypertable_name,
       d.time_interval,
       (SELECT count(*) FROM timescaledb_information.chunks c
         WHERE c.hypertable_name = d.hypertable_name) AS chunk_count
FROM timescaledb_information.dimensions d
WHERE d.hypertable_name IN
      ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
ORDER BY d.time_interval;

\echo '=== 3.1  date range covered by the chunks ==='
SELECT hypertable_name,
       min(range_start) AS first_chunk_start,
       max(range_end)   AS last_chunk_end
FROM timescaledb_information.chunks
WHERE hypertable_name IN
      ('energy_readings', 'energy_readings_3h', 'energy_readings_week')
GROUP BY hypertable_name
ORDER BY hypertable_name;
