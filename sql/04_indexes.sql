-- =====================================================================
-- Section 3.1 step 2: the matching pair of indexes, applied identically to
-- every hypertable compared in Sections 3 and 4.
-- =====================================================================
--
-- WHY THE SAME TWO INDEXES ON EVERY TABLE
--     Section 3.1.2 requires non-unique indexes on event_time and on
--     (meter_id, event_time), with identical methods and sort orders on all
--     three chunk configurations. If one table carried an extra index, or a
--     different sort order, any timing difference could be caused by the index
--     rather than by the chunk interval, and the comparison would be void.
--
-- WHY create_hypertable WAS CALLED WITH create_default_indexes => FALSE
--     Otherwise TimescaleDB would have added its own partitioning-column index
--     to energy_readings only, and the three tables would not have matched
--     from the start.
--
-- WHY BTREE AND ASCENDING
--     The default access method. Every workload in Section 3.2 filters or
--     groups on these columns in ascending time order, so a descending index
--     would serve none of them better and would make the comparison unfair.
--
-- INDEX NAMES
--     One shared naming scheme, <table>_et and <table>_mt, so a screenshot of
--     \d for each table shows the same pair without ambiguity.
--
-- WHY PLAIN CREATE INDEX RATHER THAN CONCURRENTLY
--     CONCURRENTLY cannot run inside a transaction block, and the DO block
--     that handles the optional tables is one. Nothing else writes while this
--     script runs, so the short exclusive lock costs nothing here.
--
-- HOW TO RUN (from the project root, in either shell)
--     type sql\04_indexes.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

-- ---------------------------------------------------------------------
-- The one-day table.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS energy_readings_et
    ON energy_readings (event_time);

CREATE INDEX IF NOT EXISTS energy_readings_mt
    ON energy_readings (meter_id, event_time);

-- ---------------------------------------------------------------------
-- The three-hour, one-week and compressed tables. They may not exist yet;
-- the DO block reports which ones were skipped instead of failing.
-- Plain CREATE INDEX is used inside the block because CONCURRENTLY cannot run
-- inside a transaction, and a DO block is always wrapped in one. Nothing else
-- writes to these tables while this script runs, so the brief lock is harmless.
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.energy_readings_3h') IS NOT NULL THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_readings_3h_et ON energy_readings_3h (event_time)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_readings_3h_mt ON energy_readings_3h (meter_id, event_time)';
    ELSE
        RAISE NOTICE 'energy_readings_3h does not exist yet, skipping';
    END IF;

    IF to_regclass('public.energy_readings_week') IS NOT NULL THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_readings_week_et ON energy_readings_week (event_time)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_readings_week_mt ON energy_readings_week (meter_id, event_time)';
    ELSE
        RAISE NOTICE 'energy_readings_week does not exist yet, skipping';
    END IF;

    IF to_regclass('public.energy_time_compressed') IS NOT NULL THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_time_compressed_et ON energy_time_compressed (event_time)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_time_compressed_mt ON energy_time_compressed (meter_id, event_time)';
    END IF;

    IF to_regclass('public.energy_meter_compressed') IS NOT NULL THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_meter_compressed_et ON energy_meter_compressed (event_time)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS energy_meter_compressed_mt ON energy_meter_compressed (meter_id, event_time)';
    END IF;
END
$$;

-- ---------------------------------------------------------------------
-- Verification: every reading table must show the same two index shapes.
-- ---------------------------------------------------------------------
SELECT c.relname AS table_name,
       i.relname AS index_name,
       pg_get_indexdef(ix.indexrelid) AS index_definition
FROM pg_index ix
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('energy_readings', 'energy_readings_3h', 'energy_readings_week',
                    'energy_time_compressed', 'energy_meter_compressed')
ORDER BY c.relname, i.relname;
