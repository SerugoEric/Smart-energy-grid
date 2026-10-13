-- Section 7.2 / 7.3  Panel P3 (Aggregate): network energy in the four seven-day
-- periods, kWh. Source: cagg_15min_region re-bucketed to CAT days, mapped onto
-- the four Section 5.1 periods (bucket origin 2026-09-01 00:00+02).
WITH periods(period, p_start, p_end, ord) AS (
    VALUES
      ('1-7 Sep',   TIMESTAMPTZ '2026-09-01 00:00:00+02', TIMESTAMPTZ '2026-09-08 00:00:00+02', 1),
      ('8-14 Sep',  TIMESTAMPTZ '2026-09-08 00:00:00+02', TIMESTAMPTZ '2026-09-15 00:00:00+02', 2),
      ('15-21 Sep', TIMESTAMPTZ '2026-09-15 00:00:00+02', TIMESTAMPTZ '2026-09-22 00:00:00+02', 3),
      ('22-28 Sep', TIMESTAMPTZ '2026-09-22 00:00:00+02', TIMESTAMPTZ '2026-09-29 00:00:00+02', 4)
),
daily AS (
    SELECT time_bucket(INTERVAL '1 day', bucket,
                       TIMESTAMPTZ '2026-09-01 00:00:00+02') AS d,
           sum(sum_energy_kwh)                               AS energy_kwh
    FROM cagg_15min_region
    WHERE bucket >= %(start)s::timestamptz
      AND bucket <  %(end)s::timestamptz
    GROUP BY 1
)
SELECT p.period          AS period,
       sum(daily.energy_kwh) AS energy_kwh
FROM periods p
JOIN daily
  ON daily.d >= GREATEST(p.p_start, %(start)s::timestamptz)
 AND daily.d <  LEAST(p.p_end,   %(end)s::timestamptz)
GROUP BY p.period, p.ord
ORDER BY p.ord;
