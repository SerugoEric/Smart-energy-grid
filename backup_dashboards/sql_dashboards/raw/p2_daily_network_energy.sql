-- Section 7.1 / 7.3  Panel P2 (Raw): daily network energy, kWh.
-- Source: energy_readings. Daily buckets align to CAT midnight (origin 2026-09-01).
SELECT time_bucket(INTERVAL '1 day', r.event_time,
                   TIMESTAMPTZ '2026-09-01 00:00:00+02') AS bucket,
       sum(r.energy_kwh)                               AS energy_kwh
FROM energy_readings r
WHERE r.event_time >= %(start)s::timestamptz
  AND r.event_time <  %(end)s::timestamptz
GROUP BY bucket
ORDER BY bucket;
