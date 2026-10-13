# Section 1.1 screenshot: machine, container and service summary.
# The full version of these numbers is written by ingestion\capture_environment.py
# to logs\environment_capture_*.txt and pasted into report\environment_details.md;
# this compact form exists so the whole block fits on one screen.

$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor
$os = Get-CimInstance Win32_OperatingSystem

"Machine                : $env:COMPUTERNAME / $env:PROCESSOR_ARCHITECTURE"
"OS                     : $($os.Caption) $($os.Version) $($os.OSArchitecture)"
"CPU model              : $($cpu.Name)"
"Cores / logical        : $($cpu.NumberOfCores) physical, $($cpu.NumberOfLogicalProcessors) logical"
"Installed RAM          : $([math]::Round($cs.TotalPhysicalMemory/1GB, 2)) GB"
"Python                 : $(python --version 2>&1)"
"Time zone              : $((Get-TimeZone).Id)"
"Current time (CAT)     : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
""
"Container        Image                                     Status"
"timescaledb      $(docker inspect -f '{{.Config.Image}}' timescaledb)     $(docker inspect -f '{{.State.Status}}' timescaledb)"
"emqx             $(docker inspect -f '{{.Config.Image}}' emqx)   $(docker inspect -f '{{.State.Status}}' emqx)"
""
"PostgreSQL and TimescaleDB, read from the assignment database:"
docker exec timescaledb psql -U auca -d smart_energy_grid -c "select current_database() as database, current_setting('server_version') as postgresql, current_setting('TimeZone') as session_time_zone;"
