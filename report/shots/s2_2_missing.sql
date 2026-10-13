-- Section 2.2 screenshot: the five meters with the most missing readings.
-- Independent of cleaning state: count(DISTINCT event_time) counts observed
-- pairs even while duplicate copies are still present. The observed pair count
-- is materialised once so it is not recomputed for the distribution block.
CREATE TEMP TABLE observed AS
SELECT meter_id, count(DISTINCT event_time) AS observed_pairs
FROM energy_readings
GROUP BY meter_id;

\echo '=== 2.2.3  five meters with the most missing readings ==='
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

\echo '=== 2.2.3  missing-reading distribution across all 4,000 meters ==='
SELECT min(28 * 96 - observed_pairs) AS fewest_missing,
       max(28 * 96 - observed_pairs) AS most_missing,
       round(avg(28 * 96 - observed_pairs), 2) AS average_missing,
       sum(28 * 96 - observed_pairs) AS total_missing,
       count(*) AS meters_with_any_missing,
       count(*) FILTER (WHERE observed_pairs < 28 * 96) AS meters_below_plan
FROM observed;

DROP TABLE observed;
