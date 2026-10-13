-- Section 7.2 / 7.3  Panel P4 (Aggregate): daily energy of the selected meter.
-- Source: cagg_day_meter continuous aggregate (CAT-day x meter_id).
SELECT bucket,
       sum_energy_kwh AS energy_kwh
FROM cagg_day_meter
WHERE meter_id = %(meter)s
  AND bucket >= %(start)s::timestamptz
  AND bucket <  %(end)s::timestamptz
ORDER BY bucket;
