-- =====================================================================
-- Section 2.2: data-quality diagnostics on energy_readings, BEFORE cleaning.
-- =====================================================================
--
-- WHY A TEMP TABLE
--     Every question below needs the same pair-level aggregate: one row per
--     (meter_id, event_time) with its earliest received_time. Computing that
--     once and storing it in a temp table turns six separate 10.7-million-row
--     grouping passes into one. Without it, each \echo step re-groups the whole
--     hypertable and the script takes many minutes instead of seconds.
--
--     TEMP is session-scoped, so it disappears when psql exits and leaves
--     nothing behind in the assignment database.
--
-- THE SIX COUNTS, AND HOW EACH ONE IS DEFINED
--
--   planned_readings        10,752,000
--       4,000 meters x 28 days x 96 intervals. Fixed by the generator's
--       settings; not measured from the table.
--
--   unique_readings         observed DISTINCT (meter_id, event_time) pairs.
--   duplicate_readings      total rows minus unique pairs: the extra copies.
--   missing_readings        planned minus unique: grid pairs never generated.
--   delayed_unique_readings unique pairs arriving later than the interval end
--                           (event_time + 15 minutes). Normal arrival IS
--                           event_time + 15 minutes, so the test is
--                           received_time > event_time + 15 minutes.
--                           The assignment bounds delayed arrivals at 30 to
--                           180 minutes after event_time; arrivals between 15
--                           and 30 minutes are reported separately as well,
--                           and the measured answer is expected to be zero.
--
-- PERCENTAGES (Section 2.2.2)
--   missing%     = 100 * missing / planned
--   duplicate%   = 100 * extra copies / unique pairs
--   delayed%     = 100 * delayed unique / unique pairs
--   completeness = 100 * unique pairs / planned
--
-- THE TWO ARITHMETIC CHECKS (Section 2.2.3)
--   unique + extra copies  = emitted rows
--   planned - unique       = missing readings
--
-- HOW TO RUN
--     type sql\05_data_quality.sql | docker exec -i timescaledb psql -U auca -d smart_energy_grid

\echo '=== 0. Build the pair-level temp table (one pass over the hypertable) ==='

CREATE TEMP TABLE pair_stats AS
SELECT meter_id,
       event_time,
       min(received_time)                          AS first_received,
       count(*)                                    AS copies
FROM energy_readings
GROUP BY meter_id, event_time;

ANALYZE pair_stats;

SELECT count(*) AS unique_pairs,
       sum(copies) - count(*)                      AS extra_copies,
       count(DISTINCT meter_id)                    AS distinct_meters,
       min(event_time)                             AS earliest_event,
       max(event_time)                             AS latest_event
FROM pair_stats;

\echo '=== 1. Base counts from the table ==='
SELECT (SELECT count(*) FROM energy_readings)      AS total_rows,
       (SELECT count(*) FROM pair_stats)           AS unique_pairs,
       (SELECT sum(copies) - count(*) FROM pair_stats) AS extra_copies,
       (SELECT count(DISTINCT meter_id) FROM pair_stats) AS distinct_meters,
       (SELECT min(event_time) FROM pair_stats)    AS earliest_event,
       (SELECT max(event_time) FROM pair_stats)    AS latest_event;

\echo '=== 2. Arrival timing of the unique pairs ==='
SELECT count(*)                                                     AS unique_pairs,
       count(*) FILTER (WHERE first_received <= event_time + INTERVAL '15 minutes')
                                                                     AS on_time,
       count(*) FILTER (WHERE first_received >  event_time + INTERVAL '15 minutes')
                                                                     AS later_than_interval_end,
       count(*) FILTER (WHERE first_received >= event_time + INTERVAL '30 minutes'
                     AND first_received <= event_time + INTERVAL '180 minutes')
                                                                     AS delayed_30_to_180,
       count(*) FILTER (WHERE first_received >  event_time + INTERVAL '180 minutes')
                                                                     AS later_than_180_minutes,
       count(*) FILTER (WHERE first_received >  event_time + INTERVAL '15 minutes'
                     AND first_received <  event_time + INTERVAL '30 minutes')
                                                                     AS between_15_and_30,
       max(first_received - event_time)                             AS worst_delay
FROM pair_stats;

\echo '=== 3. The reference counts from dataset_info() ==='
SELECT 10752000 AS planned_readings,
       10696848 AS emitted_readings,
       10643735 AS unique_readings,
       53113    AS duplicate_readings,
       213090   AS delayed_unique_readings,
       108265   AS missing_readings;

\echo '=== 4. Measured values next to the reference ==='
WITH measured AS (
    SELECT (SELECT count(*) FROM energy_readings) AS total_rows,
           (SELECT count(*) FROM pair_stats)      AS unique_pairs,
           (SELECT sum(copies) - count(*) FROM pair_stats) AS extra_copies,
           (SELECT count(*) FROM pair_stats
             WHERE first_received > event_time + INTERVAL '15 minutes') AS delayed_pairs
)
SELECT m.total_rows,
       10696848                                       AS ref_emitted,
       10696848 - m.total_rows                        AS emitted_difference,
       m.unique_pairs,
       10643735                                       AS ref_unique,
       10643735 - m.unique_pairs                      AS unique_difference,
       m.extra_copies,
       53113                                          AS ref_duplicates,
       53113 - m.extra_copies                         AS duplicate_difference,
       m.delayed_pairs,
       213090                                         AS ref_delayed,
       213090 - m.delayed_pairs                       AS delayed_difference,
       10752000 - m.unique_pairs                      AS measured_missing,
       108265                                         AS ref_missing,
       108265 - (10752000 - m.unique_pairs)           AS missing_difference
FROM measured m;

\echo '=== 5. Arithmetic checks (both must be zero) ==='
SELECT ((SELECT count(*) FROM pair_stats)
        + (SELECT sum(copies) - count(*) FROM pair_stats))
       - 10696848                                     AS unique_plus_extra_minus_emitted,
       (10752000 - (SELECT count(*) FROM pair_stats))
       - 108265                                       AS planned_minus_unique_minus_missing;

\echo '=== 6. The four percentages (Section 2.2.2) ==='
SELECT round(100.0 * (10752000 - (SELECT count(*) FROM pair_stats)) / 10752000, 4)
                                                                     AS missing_pct,
       round(100.0 * (SELECT sum(copies) - count(*) FROM pair_stats)
                 / (SELECT count(*) FROM pair_stats), 4)             AS duplicate_pct,
       round(100.0 * (SELECT count(*) FROM pair_stats
                        WHERE first_received > event_time + INTERVAL '15 minutes')
                 / (SELECT count(*) FROM pair_stats), 4)             AS delayed_pct,
       round(100.0 * (SELECT count(*) FROM pair_stats) / 10752000, 4) AS completeness_pct;

\echo '=== 7. The five meters with the most missing readings ==='
-- Each meter is planned to have 28 x 96 = 2,688 readings, so missing readings
-- per meter = 2,688 minus the distinct pairs observed for that meter. Building
-- the full 10,752,000-row grid and anti-joining it would produce the same
-- answer for far more work, so the arithmetic form is used instead.
WITH observed AS (
    SELECT meter_id, count(*) AS observed_pairs
    FROM pair_stats
    GROUP BY meter_id
)
SELECT o.meter_id,
       mt.region,
       mt.customer_type,
       o.observed_pairs,
       (28 * 96)                   AS planned_pairs_per_meter,
       (28 * 96) - o.observed_pairs AS missing_readings
FROM observed o
JOIN meters mt ON mt.meter_id = o.meter_id
ORDER BY missing_readings DESC, o.meter_id
LIMIT 5;

\echo '=== 8. Missing-reading distribution across all 4,000 meters ==='
WITH observed AS (
    SELECT meter_id, count(*) AS observed_pairs
    FROM pair_stats
    GROUP BY meter_id
)
SELECT min(28 * 96 - observed_pairs)                AS fewest_missing,
       max(28 * 96 - observed_pairs)                AS most_missing,
       round(avg(28 * 96 - observed_pairs), 2)      AS average_missing,
       sum(28 * 96 - observed_pairs)                AS total_missing,
       count(*)                                     AS meters_with_any_missing,
       count(*) FILTER (WHERE observed_pairs < 28 * 96) AS meters_below_plan
FROM observed;

DROP TABLE pair_stats;
