# Probe the launcher window geometry so the screenshot window is known to fit
# the 1280x720 screen. Prints the window RECT in physical pixels.
param(
    [int]$ConsoleLines = 32,
    [int]$ConsoleCols  = 170,
    [int]$WaitSeconds  = 2
)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Rect {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
}
"@
$cmd  = Join-Path $env:WINDIR 'System32\cmd.exe'
$args = "/k mode con lines=$ConsoleLines cols=$ConsoleCols"
$p = Start-Process -FilePath $cmd -ArgumentList $args -PassThru
Start-Sleep -Seconds $WaitSeconds
$h = $p.MainWindowHandle
$r = New-Object Win32Rect+RECT
[Win32Rect]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.Right - $r.Left
$hgt = $r.Bottom - $r.Top
Write-Output "mode con lines=$ConsoleLines cols=$ConsoleCols"
Write-Output "RECT Left=$($r.Left) Top=$($r.Top) Right=$($r.Right) Bottom=$($r.Bottom)"
Write-Output "Size ${w} x ${hgt}   screen 1280 x 720"
Write-Output "Fits: $([bool]($w -le 1280 -and $hgt -le 720 -and $r.Left -ge 0 -and $r.Top -ge 0))"
Stop-Process -Id $p.Id -Force
