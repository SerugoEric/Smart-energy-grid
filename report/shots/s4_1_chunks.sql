-- Section 4.1 screenshot: which chunks are compressed, in each configuration.
\echo '=== 4.1  compressed chunk coverage ==='
SELECT hypertable_name,
       count(*)                                          AS total_chunks,
       count(*) FILTER (WHERE is_compressed)             AS compressed_chunks,
       count(*) FILTER (WHERE NOT is_compressed)         AS uncompressed_chunks
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
GROUP BY hypertable_name
ORDER BY hypertable_name;

\echo '=== 4.1  first and last compressed chunk per configuration ==='
SELECT hypertable_name,
       min(chunk_name) FILTER (WHERE is_compressed) AS first_compressed_chunk,
       max(chunk_name) FILTER (WHERE is_compressed) AS last_compressed_chunk
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
GROUP BY hypertable_name
ORDER BY hypertable_name;
