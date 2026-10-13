-- Section 3.2 screenshot: execution plan of the same statement on the one-week
-- chunk configuration, with actual timing and buffer statistics.
\echo '=== 3.2  EXPLAIN (ANALYZE, BUFFERS), energy_readings_week ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT avg(power_kw) AS average_power_kw
FROM energy_readings_week
WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02'
  AND event_time <  TIMESTAMPTZ '2026-09-21 01:00:00+02';
