-- Section 7.2 / 7.3  Panel P1 (Aggregate): hourly regional energy, kWh.
-- Source: cagg_hour_region continuous aggregate (already CAT-hour x region).
-- No measurement query may touch energy_readings.
SELECT bucket,
       region,
       sum(sum_energy_kwh) AS energy_kwh
FROM cagg_hour_region
WHERE bucket >= %(start)s::timestamptz
  AND bucket <  %(end)s::timestamptz
GROUP BY bucket, region
ORDER BY bucket, region;
