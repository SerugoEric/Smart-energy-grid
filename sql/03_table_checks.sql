-- =====================================================================
-- Section 2.1 step 5: size and content checks for energy_readings.
-- =====================================================================
--
-- WHY THE SIZES ARE SUMMED OVER CHUNKS
--     pg_relation_size('energy_readings') reports only the size of the
--     hypertable's EMPTY root table, which is why a naive call returns
--     "0 bytes" for a table whose data lives in 29 chunk relations.
--     hypertable_size() is the TimescaleDB helper that walks the chunks.
--     The data and index split below sums pg_relation_size (heap) and
--     pg_indexes_size (indexes) across the same chunk relations, so the
--     three numbers add up:
--         data + indexes = total
--
-- HOW TO RUN
--     type sql\03_table_checks.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

-- 1. Row count, distinct meters, date range.
SELECT count(*)                              AS row_count,
       count(DISTINCT meter_id)              AS distinct_meters,
       min(event_time)                       AS earliest_event,
       max(event_time)                       AS latest_event
FROM energy_readings;

-- 2. Chunk interval, chunk count and the actual time span covered.
SELECT dim.time_interval,
       count(*)                             AS chunk_count,
       min(c.range_start)                   AS first_chunk_start,
       max(c.range_end)                     AS last_chunk_end
FROM timescaledb_information.dimensions dim
JOIN timescaledb_information.chunks c
  ON c.hypertable_name = dim.hypertable_name
WHERE dim.hypertable_name = 'energy_readings'
GROUP BY dim.time_interval;

-- 3. Sizes: data, indexes and total, summed over every chunk.
SELECT pg_size_pretty(sum(pg_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass)))  AS table_data,
       pg_size_pretty(sum(pg_indexes_size(format('%I.%I', chunk_schema, chunk_name)::regclass)))   AS index_size,
       pg_size_pretty(sum(pg_total_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass))) AS total_size
FROM timescaledb_information.chunks
WHERE hypertable_name = 'energy_readings';

-- 4. Same three figures in bytes and MB, for the report table.
SELECT sum(pg_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass))          AS data_bytes,
       sum(pg_indexes_size(format('%I.%I', chunk_schema, chunk_name)::regclass))           AS index_bytes,
       sum(pg_total_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass))    AS total_bytes,
       round((sum(pg_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass)) / 1024.0 / 1024.0)::numeric, 1)  AS data_mb,
       round((sum(pg_indexes_size(format('%I.%I', chunk_schema, chunk_name)::regclass)) / 1024.0 / 1024.0)::numeric, 1)   AS index_mb,
       round((sum(pg_total_relation_size(format('%I.%I', chunk_schema, chunk_name)::regclass)) / 1024.0 / 1024.0)::numeric, 1) AS total_mb
FROM timescaledb_information.chunks
WHERE hypertable_name = 'energy_readings';

-- 5. Pilot table, for contrast.
SELECT count(*) AS pilot_rows FROM energy_live;
