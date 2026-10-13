-- Section 2.3 screenshot: energy_readings BEFORE cleaning.
\echo '=== Section 2.3 - BEFORE cleaning ==='
SELECT count(*) AS rows_before,
       round(sum(energy_kwh)::numeric, 6) AS sum_energy_kwh_before,
       count(DISTINCT meter_id) AS meters
FROM energy_readings;
