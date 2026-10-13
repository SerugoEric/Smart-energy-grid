-- =====================================================================
-- Section 4.2: storage and compression-cost measurements.
-- =====================================================================
--
-- IMPORTANT NOTE ON HOW TIMESCALEDB STORES COMPRESSED CHUNKS
--     Since TimescaleDB 2.11 the compressed copy of a chunk lives in a
--     SEPARATE relation, "<chunk_name>_compressed", and the original chunk
--     relation is left (almost) empty. A naive pg_total_relation_size(...)
--     over the chunk alone therefore reports ~0 for a compressed table,
--     which is misleading. The queries below therefore sum:
--         chunk relation  +  chunk "_compressed" relation
--     for every chunk of every table, which reproduces the true footprint
--     for both compressed tables and reduces to the plain chunk size for
--     the uncompressed baseline (energy_readings, no "_compressed" tables).
--
-- Row coverage: the compressed chunk relations carry "_ts_meta_count", the
-- row count of each compressed batch, so a sum over those gives the exact
-- number of rows held in compressed chunks without decompressing anything.
--
-- HOW TO RUN
--     type sql\09_compression_storage.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

\echo '=== 0. Helper: row count stored inside each compressed chunk ==='
CREATE OR REPLACE FUNCTION _report_compressed_row_counts()
RETURNS TABLE(hypertable_name text, rows_in_compressed_chunks bigint)
AS $$
DECLARE
    rec record;
    total bigint;
BEGIN
    FOR rec IN
        SELECT h.hypertable_name, h.chunk_name
        FROM timescaledb_information.chunks h
        WHERE h.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
          AND h.is_compressed
    LOOP
        EXECUTE format(
            'SELECT sum(_ts_meta_count) FROM %I.%I',
            '_timescaledb_internal', rec.chunk_name || '_compressed'
        ) INTO total;
        hypertable_name := rec.hypertable_name;
        rows_in_compressed_chunks := total;
        RETURN NEXT;
    END LOOP;
END
$$ LANGUAGE plpgsql;

\echo '=== 1. True size components per table (chunk + its _compressed relation) ==='
WITH chunk_sizes AS (
    SELECT h.hypertable_name,
           h.chunk_name,
           format('%I.%I', h.chunk_schema, h.chunk_name)::regclass
               AS chunk_rel,
           to_regclass(format('%I.%I', h.chunk_schema,
                              h.chunk_name || '_compressed'))
               AS comp_rel
    FROM timescaledb_information.chunks h
    WHERE h.hypertable_name IN ('energy_readings', 'energy_time_compressed',
                                'energy_meter_compressed')
),
sizes AS (
    SELECT hypertable_name,
           sum(pg_relation_size(chunk_rel)
               + COALESCE(pg_relation_size(comp_rel), 0)) AS data_bytes,
           sum(pg_indexes_size(chunk_rel)
               + COALESCE(pg_indexes_size(comp_rel), 0)) AS index_bytes,
           sum(pg_total_relation_size(chunk_rel)
               + COALESCE(pg_total_relation_size(comp_rel), 0)) AS total_bytes
    FROM chunk_sizes
    GROUP BY hypertable_name
)
SELECT hypertable_name,
       pg_size_pretty(data_bytes)                                       AS data,
       pg_size_pretty(index_bytes)                                      AS index,
       pg_size_pretty(total_bytes)                                      AS total,
       round(data_bytes / 1024.0 / 1024.0, 1)                           AS data_mb,
       round(index_bytes / 1024.0 / 1024.0, 1)                          AS index_mb,
       round(total_bytes / 1024.0 / 1024.0, 2)                          AS total_mb
FROM sizes
ORDER BY hypertable_name;

\echo '=== 2. Chunk coverage and rows held in compressed chunks ==='
WITH coverage AS (
    SELECT h.hypertable_name,
           count(*)                                                       AS total_chunks,
           count(*) FILTER (WHERE h.is_compressed)                        AS compressed_chunks
    FROM timescaledb_information.chunks h
    WHERE h.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
    GROUP BY h.hypertable_name
),
compressed_rows AS (
    SELECT hypertable_name, sum(rows_in_compressed_chunks) AS rows_in_compressed
    FROM _report_compressed_row_counts()
    GROUP BY hypertable_name
),
table_rows AS (
    SELECT 'energy_time_compressed' AS hypertable_name, count(*) AS total_rows
    FROM energy_time_compressed
    UNION ALL
    SELECT 'energy_meter_compressed', count(*) FROM energy_meter_compressed
)
SELECT co.hypertable_name,
       co.compressed_chunks || ' of ' || co.total_chunks                  AS chunk_coverage,
       cr.rows_in_compressed,
       tr.total_rows,
       round(100.0 * cr.rows_in_compressed / tr.total_rows, 4)            AS rows_in_compressed_pct
FROM coverage co
JOIN compressed_rows cr USING (hypertable_name)
JOIN table_rows tr USING (hypertable_name)
ORDER BY co.hypertable_name;

\echo '=== 3. Compression ratio, percentage saved and coverage summary ==='
WITH baseline AS (
    SELECT sum(pg_total_relation_size(
               format('%I.%I', c.chunk_schema, c.chunk_name)::regclass)) AS size_bytes
    FROM timescaledb_information.chunks c
    WHERE c.hypertable_name = 'energy_readings'
),
chunk_sizes AS (
    SELECT h.hypertable_name,
           h.chunk_name,
           format('%I.%I', h.chunk_schema, h.chunk_name)::regclass AS chunk_rel,
           to_regclass(format('%I.%I', h.chunk_schema,
                              h.chunk_name || '_compressed')) AS comp_rel
    FROM timescaledb_information.chunks h
    WHERE h.hypertable_name IN ('energy_time_compressed', 'energy_meter_compressed')
),
computed AS (
    SELECT hypertable_name,
           sum(pg_total_relation_size(chunk_rel)
               + COALESCE(pg_total_relation_size(comp_rel), 0)) AS size_bytes,
           count(*) AS total_chunks,
           count(*) FILTER (WHERE comp_rel IS NOT NULL) AS compressed_chunks
    FROM chunk_sizes
    GROUP BY hypertable_name
)
SELECT c.hypertable_name,
       b.size_bytes                                                     AS baseline_bytes,
       c.size_bytes                                                     AS compressed_bytes,
       round(b.size_bytes::numeric / c.size_bytes::numeric, 3)          AS compression_ratio,
       round(100.0 * (b.size_bytes - c.size_bytes) / b.size_bytes, 2)   AS percent_saved,
       c.compressed_chunks || ' of ' || c.total_chunks                  AS chunk_coverage
FROM computed c, baseline b
ORDER BY c.hypertable_name;