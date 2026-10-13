-- Section 1.3 screenshot: stored pilot rows and a sample.
\echo '=== Section 1.3 - rows stored in energy_live ==='
SELECT count(*)                  AS energy_live_rows,
       count(DISTINCT meter_id)  AS distinct_meters,
       min(event_time)           AS earliest_event_time,
       max(event_time)           AS latest_event_time
FROM energy_live;

\echo '=== Section 1.3 - five sample rows ==='
SELECT meter_id, event_time, received_time, power_kw, voltage_v,
       current_a, frequency_hz, energy_kwh
FROM energy_live
ORDER BY meter_id, event_time
LIMIT 5;
