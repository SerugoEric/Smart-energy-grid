-- Section 7.1 / 7.3  Panel P4 (Raw): daily energy of the selected meter, kWh.
-- Source: energy_readings. The meter variable is used by this panel only.
SELECT time_bucket(INTERVAL '1 day', r.event_time,
                   TIMESTAMPTZ '2026-09-01 00:00:00+02') AS bucket,
       sum(r.energy_kwh)                               AS energy_kwh
FROM energy_readings r
WHERE r.meter_id = %(meter)s
  AND r.event_time >= %(start)s::timestamptz
  AND r.event_time <  %(end)s::timestamptz
GROUP BY bucket
ORDER BY bucket;
