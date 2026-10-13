-- =====================================================================
-- Section 1.2: create the three required database structures.
-- =====================================================================
--
-- WHAT THIS CREATES, AND WHY EACH CHOICE
--
-- 1. energy_live is a NORMAL TABLE, not a hypertable.
--    Section 1.3 uses it to hold the 2,000-reading MQTT pilot. That is a
--    tiny, short-lived, append-heavy set of rows that arrives in arrival order
--    rather than event order. A hypertable would add chunk management, ordering
--    rules and compression bookkeeping for no analytical benefit. The
--    assignment asks for a regular table here precisely so the pilot can be
--    dropped and recreated with TRUNCATE between attempts.
--
-- 2. energy_readings IS A HYPERTABLE partitioned by event_time.
--    It will hold 10,696,848 rows spanning 28 days. TimescaleDB splits it into
--    chunks, so most queries touch only the chunks their time filter selects.
--    That is what makes the Section 3 chunk-interval comparison meaningful:
--    without chunks there would be nothing to compare.
--
-- 3. event_time IS THE TIME COLUMN because it is the dimension we query on.
--    Section 1.3.5, 2.2, 3, 4 and 6 all group or filter by event_time. The
--    assignment also says to group by event_time rather than received_time
--    unless a step explicitly says otherwise. received_time is deliberately NOT
--    a partition column: the generator yields rows in event_time order while
--    arrival times are deliberately out of order, so received_time is unsuitable
--    for time partitioning.
--
-- 4. TIMESTAMPTZ, NOT TIMESTAMP, for both time columns.
--    TIMESTAMP with no zone stores a wall-clock reading with no offset, which is
--    ambiguous. TIMESTAMPTZ stores the instant in UTC and renders it in the
--    session time zone. The generator emits CAT ISO strings ending in +02:00, and
--    "now()" in Africa/Kigali is the same instant, so TIMESTAMPTZ accepts the
--    generator's text directly and converts it losslessly.
--
--    NOTE ON DAILY ALIGNMENT: a chunk boundary and a daily bucket are different
--    things. TimescaleDB aligns time chunks to the Unix epoch, so a one-day chunk
--    runs 00:00 to 00:00 UTC, which is 02:00 to 02:00 in CAT. The Section 6
--    daily continuous aggregate therefore uses an explicit origin of
--    2026-09-01 00:00:00+02 to align buckets to CAT midnight, as Section 1.1
--    requires. We are not claiming chunks are CAT-midnight aligned.
--
-- 5. DUPLICATES ARE ALLOWED AT THIS STAGE, so no primary key or unique index
--    exists on either reading table. Section 1.3.3 explicitly says to count
--    duplicate copies as separate messages and separate rows, and Section 2.2
--    counts "extra copies of observed pairs" before Section 2.3 removes them. A
--    unique constraint now would make the data-quality queries impossible to
--    run. It is also impossible: TimescaleDB cannot create a unique index that
--    does not include the partitioning column.
--
-- 6. meter_id IS BIGINT, not INTEGER.
--    PostgreSQL INTEGER tops out at 2,147,483,647. Our IDs run from 1,000,000,000
--    to 1,000,003,999, which overflows INTEGER immediately. BIGINT holds up to
--    about 9.2 x 10^18. Keeping meter_id one type across meters, energy_live and
--    energy_readings also means the Section 6 and 7 joins need no cast, and a
--    cast on a 10.6-million-row join is not free.
--
-- 7. DOUBLE PRECISION for the five measurements.
--    The generator produces non-integer values (voltage 226.0 to 234.0, frequency
--    near 50, power with six decimals). Section 3.1.3 permits at most 0.001
--    difference in the numeric sums, and Section 7.3 requires energy agreement
--    within 0.001 kWh, so REAL would be too coarse to stay inside those
--    tolerances across 10.6 million rows. DOUBLE PRECISION is also what
--    SUM() returns in PostgreSQL, so no type juggling is needed.
--
-- 8. ONE-DAY CHUNKS at this stage, as Section 1.2.1 requires.
--    Twenty-eight chunks will cover the dataset. Section 3 will build the
--    three-hour and one-week variants for comparison, but Section 1.2 specifies
--    one day for this table.
--
-- ON NOT NULL CONSTRAINTS
--    meters has no NOT NULL constraints beyond its primary key, because the
--    assignment lists the columns and their types without asking for
--    constraints. Adding constraints we were not asked for would silently
--    change the required schema. Section 5.2 needs to trust these values, and
--    the generator always supplies all five fields.
--
-- ON FOREIGN KEYS
--    energy_readings and energy_live have no foreign key to meters. The
--    assignment does not ask for one, and enforcing 10.6 million references would
--    slow the Section 2 bulk load for no analytical benefit. The Section 6 and 7
--    joins are written explicitly instead.
--
-- HOW TO RUN (Windows CMD)
--    type sql\01_schema.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid
--
-- HOW TO RUN (PowerShell)
--    type works in PowerShell too. Do NOT use "<" redirection: PowerShell 5.1
--    removed it, so that form fails with a parser error.
--
-- REPEATABILITY
--    Safe to run more than once. CREATE TABLE IF NOT EXISTS skips existing
--    tables, and create_hypertable is called with if_not_exists => TRUE.

-- ---------------------------------------------------------------------
-- TABLE 3 of 3: meters
-- ---------------------------------------------------------------------
-- Created first only for readability. There is no dependency between the three
-- tables, so the order is arbitrary.
CREATE TABLE IF NOT EXISTS meters (
    meter_id      BIGINT PRIMARY KEY,
    region        TEXT,
    customer_type TEXT,
    base_power_kw DOUBLE PRECISION,
    power_factor  DOUBLE PRECISION
);

-- ---------------------------------------------------------------------
-- TABLE 1 of 3: energy_live  (regular table, pilot destination)
-- ---------------------------------------------------------------------
-- Deliberately NOT a hypertable. See note 1 at the top of this file.
-- No primary key and no unique index, so duplicate readings are accepted.
CREATE TABLE IF NOT EXISTS energy_live (
    meter_id      BIGINT,
    event_time    TIMESTAMPTZ,
    received_time TIMESTAMPTZ,
    power_kw      DOUBLE PRECISION,
    voltage_v     DOUBLE PRECISION,
    current_a     DOUBLE PRECISION,
    frequency_hz  DOUBLE PRECISION,
    energy_kwh    DOUBLE PRECISION
);

-- ---------------------------------------------------------------------
-- TABLE 2 of 3: energy_readings  (hypertable, one-day chunks)
-- ---------------------------------------------------------------------
-- Identical eight columns to energy_live. Keeping the column list identical is
-- what lets Sections 3, 4 and 7 compare the tables fairly.
CREATE TABLE IF NOT EXISTS energy_readings (
    meter_id      BIGINT,
    event_time    TIMESTAMPTZ,
    received_time TIMESTAMPTZ,
    power_kw      DOUBLE PRECISION,
    voltage_v     DOUBLE PRECISION,
    current_a     DOUBLE PRECISION,
    frequency_hz  DOUBLE PRECISION,
    energy_kwh    DOUBLE PRECISION
);

-- Convert energy_readings into a hypertable.
--
-- WHY by_range(...) RATHER THAN THE OLDER create_hypertable('t','col') FORM
--     TimescaleDB 2.13 introduced a dimension-builder API. This server runs
--     2.30.2, so the newer form is the documented one and the older string form
--     is deprecated. by_range names the column and its chunk width explicitly.
--
-- WHY create_default_indexes => FALSE
--     By default create_hypertable builds an index on the partitioning column.
--     Section 3.1.2 requires all three tables to carry the SAME two indexes, on
--     event_time and on (meter_id, event_time), with identical methods and sort
--     orders. Suppressing the automatic index here means 03_indexes.sql creates
--     the same pair of explicitly named indexes on every table, so none of the
--     three can accidentally differ.
--
-- WHY chunk_time_interval IS NOT USED
--     That named parameter belongs to the older API. In the by_range form the
--     chunk width is the second argument of by_range itself.
--
-- WHY if_not_exists => TRUE
--     Makes this script safe to re-run: the second attempt returns a notice
--     instead of raising "table is already a hypertable".
SELECT create_hypertable(
           'energy_readings',
           by_range('event_time', INTERVAL '1 day'),
           create_default_indexes => FALSE,
           if_not_exists           => TRUE
       );

-- ---------------------------------------------------------------------
-- Sanity check built into the script
-- ---------------------------------------------------------------------
-- If the eight columns are ever edited by mistake, this fails loudly instead of
-- letting the error surface much later during a Section 2 load.
DO $$
DECLARE
    live_columns     INTEGER;
    readings_columns INTEGER;
BEGIN
    SELECT count(*) INTO live_columns
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'energy_live';

    SELECT count(*) INTO readings_columns
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'energy_readings';

    IF live_columns <> 8 OR readings_columns <> 8 THEN
        RAISE EXCEPTION
            'Expected 8 columns in both reading tables, found energy_live=% and energy_readings=%',
            live_columns, readings_columns;
    END IF;

    RAISE NOTICE 'Column count check passed: 8 columns in energy_live and energy_readings';
END
$$;