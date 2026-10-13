-- Section 2.3 screenshot: energy_readings AFTER cleaning.
\echo '=== Section 2.3 - AFTER cleaning ==='
SELECT count(*) AS rows_after,
       round(sum(energy_kwh)::numeric, 6) AS sum_energy_kwh_after,
       count(DISTINCT meter_id) AS meters
FROM energy_readings;

\echo '=== duplicate pairs remaining (must be 0) ==='
SELECT count(*) - (SELECT count(*) FROM
       (SELECT DISTINCT meter_id, event_time FROM energy_readings) d)
       AS extra_copies
FROM energy_readings;
