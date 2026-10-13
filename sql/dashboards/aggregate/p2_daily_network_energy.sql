-- Section 7.2 / 7.3  Panel P2 (Aggregate): daily network energy, kWh.
-- Source: cagg_15min_region re-bucketed to CAT days (origin 2026-09-01).
-- Sum stored energy sums; never average averages.
SELECT time_bucket(INTERVAL '1 day', bucket,
                   TIMESTAMPTZ '2026-09-01 00:00:00+02') AS bucket,
       sum(sum_energy_kwh)                               AS energy_kwh
FROM cagg_15min_region
WHERE bucket >= %(start)s::timestamptz
  AND bucket <  %(end)s::timestamptz
GROUP BY 1
ORDER BY 1;
