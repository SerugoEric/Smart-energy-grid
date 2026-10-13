-- Section 1.1 screenshot: the TimescaleDB extension is enabled.
\echo '=== Section 1.1 - enabled extension ==='
SELECT extname AS extension, extversion AS installed_version
FROM pg_extension
ORDER BY extname;
SELECT name AS extension, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'timescaledb';
