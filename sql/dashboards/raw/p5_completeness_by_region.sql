-- Section 7.1 / 7.3  Panel P5 (Raw): completeness by region, percent.
-- observed = count(*) of cleaned energy_readings rows per region (the cleaned
-- table holds one row per meter_id + event_time pair, so count(*) equals the
-- unique observed pair count).
-- planned  = registered meters in the region x 96 readings/day x days in range.
-- days     = calendar days between the CAT-midnight bounds, end exclusive.
WITH reg AS (
    SELECT region, count(*) AS registered
    FROM meters
    GROUP BY region
),
obs AS (
    SELECT m.region, count(*) AS observed
    FROM energy_readings r
    JOIN meters m USING (meter_id)
    WHERE r.event_time >= %(start)s::timestamptz
      AND r.event_time <  %(end)s::timestamptz
    GROUP BY m.region
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
