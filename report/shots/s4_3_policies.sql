-- Section 4.3 screenshot: compression policies resumed after measurement.
\echo '=== Section 4.3 - compression policy jobs enabled after measurement ==='
SELECT j.job_id,
       j.hypertable_name,
       j.proc_name,
       j.scheduled AS enabled,
       j.config
FROM timescaledb_information.jobs j
WHERE j.proc_name = 'policy_compression'
ORDER BY j.job_id;

\echo '=== compressed chunks currently held by each strategy ==='
SELECT h.hypertable_name,
       count(*) FILTER (WHERE c.is_compressed) AS compressed_chunks,
       count(*) AS total_chunks
FROM timescaledb_information.chunks c
JOIN timescaledb_information.hypertables h
  ON h.hypertable_schema = c.hypertable_schema
 AND h.hypertable_name = c.hypertable_name
WHERE h.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
GROUP BY h.hypertable_name
ORDER BY h.hypertable_name;
