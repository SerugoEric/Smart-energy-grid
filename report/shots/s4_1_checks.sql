-- Section 4.1 screenshot: the compressed copies still answer correctly.
\echo '=== 4.1  rows, range and energy sum in the compressed copies ==='
SELECT 'energy_time_compressed' AS table_name,
       count(*) AS row_count,
       count(DISTINCT meter_id) AS meter_count,
       min(event_time) AS earliest,
       max(event_time) AS latest,
       round(sum(energy_kwh)::numeric, 6) AS sum_energy_kwh
FROM energy_time_compressed
UNION ALL
SELECT 'energy_meter_compressed',
       count(*),
       count(DISTINCT meter_id),
       min(event_time),
       max(event_time),
       round(sum(energy_kwh)::numeric, 6)
FROM energy_meter_compressed
ORDER BY table_name;

\echo '=== 4.1  both copies must equal the cleaned one-day baseline ==='
SELECT 'energy_time_compressed' AS table_name,
       CASE WHEN count(*) = 10643735
             AND round(sum(energy_kwh)::numeric, 6) = 3853704.346816
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM energy_time_compressed;
