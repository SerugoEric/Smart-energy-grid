-- Section 4.4 screenshot: execution plan of Q1 on the time-compressed copy.
\echo '=== 4.4  EXPLAIN (ANALYZE, BUFFERS), energy_time_compressed ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT avg(power_kw) AS average_power_kw
FROM energy_time_compressed
WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02'
  AND event_time <  TIMESTAMPTZ '2026-09-21 01:00:00+02';
