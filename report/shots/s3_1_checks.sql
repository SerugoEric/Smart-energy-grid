-- Section 3.1 screenshot: row counts, date ranges and the matching-sum check.
\echo '=== 3.1  rows, meters and date range per configuration ==='
SELECT 'energy_readings' AS table_name, count(*) AS row_count,
       count(DISTINCT meter_id) AS meter_count,
       min(event_time) AS earliest, max(event_time) AS latest
FROM energy_readings
UNION ALL
SELECT 'energy_readings_3h', count(*), count(DISTINCT meter_id),
       min(event_time), max(event_time)
FROM energy_readings_3h
UNION ALL
SELECT 'energy_readings_week', count(*), count(DISTINCT meter_id),
       min(event_time), max(event_time)
FROM energy_readings_week
ORDER BY table_name;

\echo '=== 3.1  sums must agree with the one-day baseline (tolerance 0.001) ==='
WITH sums AS (
    SELECT 'energy_readings' AS table_name,
           sum(power_kw) AS sum_power_kw, sum(energy_kwh) AS sum_energy_kwh
    FROM energy_readings
    UNION ALL
    SELECT 'energy_readings_3h', sum(power_kw), sum(energy_kwh)
    FROM energy_readings_3h
    UNION ALL
    SELECT 'energy_readings_week', sum(power_kw), sum(energy_kwh)
    FROM energy_readings_week
), base AS (
    SELECT sum_power_kw, sum_energy_kwh FROM sums
    WHERE table_name = 'energy_readings'
)
SELECT s.table_name,
       round((s.sum_power_kw  - b.sum_power_kw)::numeric, 9)  AS power_difference,
       round((s.sum_energy_kwh - b.sum_energy_kwh)::numeric, 9) AS energy_difference,
       CASE WHEN abs(s.sum_power_kw - b.sum_power_kw) < 0.001
             AND abs(s.sum_energy_kwh - b.sum_energy_kwh) < 0.001
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM sums s, base b
ORDER BY s.table_name;
