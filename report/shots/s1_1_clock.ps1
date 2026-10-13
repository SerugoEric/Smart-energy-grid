# Section 1.1 screenshot: machine clock and time zone.
"System clock (CAT)   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
"UTC                  : $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss'))"
"Time zone id         : $((Get-TimeZone).Id)"
"UTC offset           : $((Get-TimeZone).BaseUtcOffset)"
""
"Windows Time service : $((Get-Service w32time).Status)"
w32tm /query /status
