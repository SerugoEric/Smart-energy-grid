-- Section 7.1 / 7.3  Panel P1 (Raw): hourly regional energy, kWh.
-- Source: energy_readings (cleaned, 10,643,735 rows) JOIN meters for the region.
-- Range is the selected whole-CAT-day window [start, end), end exclusive.
-- Bucket origin 2026-09-01 00:00+02 aligns CAT hours.
SELECT time_bucket(INTERVAL '1 hour', r.event_time,
                   TIMESTAMPTZ '2026-09-01 00:00:00+02') AS bucket,
       m.region                                        AS region,
       sum(r.energy_kwh)                               AS energy_kwh
FROM energy_readings r
JOIN meters m USING (meter_id)
WHERE r.event_time >= %(start)s::timestamptz
  AND r.event_time <  %(end)s::timestamptz
GROUP BY bucket, m.region
ORDER BY bucket, m.region;
