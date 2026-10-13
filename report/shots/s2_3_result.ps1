# Section 2.3 screenshot: the before/after/verification blocks of the cleaning log.
$projectRoot = Split-Path -Parent $PSScriptRoot
$latest = Get-ChildItem (Join-Path $projectRoot 'logs\clean_readings_*.txt') |
          Sort-Object Name | Select-Object -Last 1

"Log: $($latest.Name)"
Select-String -Path $latest.FullName -Pattern `
    '^(BEFORE CLEANING|AFTER CLEANING|VERIFICATION|  rows |  distinct pairs|  summed energy_kwh|  extra copies deleted|  energy removed|  final row count|  expected unique_readings|  duplicate pairs remaining|  distinct meters|  PASS:|  duplicated pairs found|    identical across all six|    conflicting |  No conflicting)' |
    ForEach-Object { $_.Line }
