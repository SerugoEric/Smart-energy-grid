-- Section 1.1 screenshot: proof that the clock is read in CAT.
\echo '=== Section 1.1 - clock in CAT ==='
SELECT now()                         AS now_in_session_zone,
       now() AT TIME ZONE 'Africa/Kigali' AS now_in_cat,
       now() AT TIME ZONE 'UTC'           AS now_in_utc,
       current_setting('TimeZone')        AS session_time_zone;
