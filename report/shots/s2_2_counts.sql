-- Section 2.2 screenshot: diagnostics on energy_readings BEFORE cleaning.
-- One pass only: the expensive distinct-pair count is materialised once and
-- the three result blocks read it back.
CREATE TEMP TABLE measured AS
SELECT count(*) AS total_rows,
       (SELECT count(*) FROM
            (SELECT DISTINCT meter_id, event_time FROM energy_readings) d
       ) AS unique_pairs,
       count(*) FILTER (WHERE received_time > event_time + INTERVAL '15 minutes')
           AS delayed_pairs,
       count(DISTINCT meter_id) AS meters
FROM energy_readings;

\echo '=== 2.2.1  base counts on the pre-cleaning table ==='
SELECT total_rows,
       unique_pairs,
       total_rows - unique_pairs AS extra_copies,
       delayed_pairs,
       meters
FROM measured;

\echo '=== 2.2.2  the four percentages ==='
SELECT round(100.0 * (10752000 - unique_pairs) / 10752000, 4) AS missing_pct,
       round(100.0 * (total_rows - unique_pairs) / unique_pairs, 4) AS duplicate_pct,
       round(100.0 * delayed_pairs / unique_pairs, 4) AS delayed_pct,
       round(100.0 * unique_pairs / 10752000, 4) AS completeness_pct
FROM measured;

\echo '=== 2.2.3  measured minus reference, and the two arithmetic checks ==='
SELECT total_rows   - 10696848 AS emitted_diff,
       unique_pairs - 10643735 AS unique_diff,
       (total_rows - unique_pairs) - 53113 AS duplicate_diff,
       delayed_pairs - 213090 AS delayed_diff,
       (10752000 - unique_pairs) - 108265 AS missing_diff,
       unique_pairs + (total_rows - unique_pairs) - 10696848 AS check_unique_plus_extra,
       10752000 - unique_pairs - 108265 AS check_planned_minus_unique
FROM measured;

DROP TABLE measured;
