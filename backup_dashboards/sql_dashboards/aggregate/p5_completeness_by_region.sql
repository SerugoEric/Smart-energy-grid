-- Section 7.2 / 7.3  Panel P5 (Aggregate): completeness by region, percent.
-- observed = SUM(reading_count) from cagg_15min_region (sum stored counts,
--            never average averages).
-- planned  = registered meters in the region x 96 readings/day x days in range,
--            computed from the meters table and the selected CAT-day period.
WITH reg AS (
    SELECT region, count(*) AS registered
    FROM meters
    GROUP BY region
),
obs AS (
    SELECT region, sum(reading_count) AS observed
    FROM cagg_15min_region
    WHERE bucket >= %(start)s::timestamptz
      AND bucket <  %(end)s::timestamptz
    GROUP BY region
)
SELECT reg.region              AS region,
       reg.registered          AS registered,
       obs.observed            AS observed,
       reg.registered * 96
           * ((%(end)s::date - %(start)s::date))            AS planned,
       100.0 * obs.observed
           / (reg.registered * 96
              * ((%(end)s::date - %(start)s::date)))        AS completeness
FROM reg
JOIN obs USING (region)
ORDER BY split_part(reg.region, ' ', 2)::int;
