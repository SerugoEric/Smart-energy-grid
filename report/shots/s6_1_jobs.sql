-- Section 6.1 screenshot: background job status of every scheduled policy job.
\echo '=== 6.1  BACKGROUND JOB STATUS (all policy jobs) ==='
SELECT j.job_id, j.proc_name, j.scheduled, s.last_run_status,
       s.total_runs, s.total_successes, s.total_failures
FROM timescaledb_information.jobs j
LEFT JOIN timescaledb_information.job_stats s ON s.job_id = j.job_id
WHERE j.proc_name LIKE 'policy_%'
ORDER BY j.job_id;
