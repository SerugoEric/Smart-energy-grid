# Print part of a run log so it can be screenshotted.
#
#   show_log_block.ps1 -File <path relative to project root> -Start <marker>
#                       [-Lines N] [-Pattern <regex>]
#
# Prints from the first line containing -Start, then either -Lines lines or
# every line matching -Pattern. One of the two is usually needed: a full
# benchmark summary is longer than a screenshot window can show.
#
# Underscores in -Start stand for spaces (cmd.exe drops quotes around a
# command tail like this, so a marker cannot contain a literal space).

param(
    [Parameter(Mandatory = $true)][string]$File,
    [Parameter(Mandatory = $true)][string]$Start,
    [int]$Lines = 0,
    [string]$Pattern = "",
    # -Summary keeps only the SUMMARY heading, the column heading and the
    # Q1-Q5 rows, because a full benchmark summary is taller than a screenshot
    # window. A switch rather than a -Pattern value so the command line stays
    # free of the | and ^ characters cmd.exe would have to escape.
    [switch]$Summary
)

# Shots scripts live in report\shots, so the project root is two levels up.
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$full = Join-Path $projectRoot $File
if (-not (Test-Path $full)) { Write-Output "not found: $File"; exit 1 }

$Start = $Start.Replace('_', ' ')
$hit = Select-String -Path $full -Pattern ([regex]::Escape($Start)) |
       Select-Object -First 1
if (-not $hit) { Write-Output "marker '$Start' not found in $File"; exit 1 }

Write-Output "Log: $File   (marker at line $($hit.LineNumber))"
$block = Get-Content $full |
         Select-Object -Skip ($hit.LineNumber - 1) |
         Select-Object -First $(if ($Lines -gt 0) { $Lines } else { 100000 })

if ($Summary) { $Pattern = 'SUMMARY|Configuration|Q[1-5] ' }

if ($Pattern -ne "") {
    $block = $block | Where-Object { $_ -match $Pattern }
}

$block
