-- Section 1.2 screenshot: column names and types of the three reading tables.
\echo '=== Section 1.2 - columns and PostgreSQL types ==='
SELECT table_name, ordinal_position, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name IN ('energy_live', 'energy_readings', 'meters')
ORDER BY table_name, ordinal_position;
