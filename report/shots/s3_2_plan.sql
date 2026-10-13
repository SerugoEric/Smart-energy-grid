-- Section 3.2 screenshot: one execution plan with actual timing and buffers.
\echo '=== 3.2  EXPLAIN (ANALYZE, BUFFERS) on the one-day configuration ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT avg(power_kw) AS average_power_kw
FROM energy_readings
WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02'
  AND event_time <  TIMESTAMPTZ '2026-09-21 01:00:00+02';
