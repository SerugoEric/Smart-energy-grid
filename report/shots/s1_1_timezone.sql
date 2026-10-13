-- Section 1.1 screenshot: session time zone set to CAT.
\echo '=== Section 1.1 - session time zone ==='
SHOW timezone;
SELECT now()                         AS now_in_session_zone,
       now() AT TIME ZONE 'Africa/Kigali' AS now_in_cat,
       current_setting('TimeZone')   AS session_time_zone;
