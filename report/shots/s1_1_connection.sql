-- Section 1.1 screenshot: connection to the assignment database.
\echo '=== Section 1.1 - connection to the assignment database ==='
\conninfo
SELECT current_database()  AS database,
       current_user        AS role,
       current_setting('server_version') AS server_version,
       current_setting('TimeZone')       AS session_time_zone;
