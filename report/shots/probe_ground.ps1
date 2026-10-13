# Ground truth: physical screen size, physical console RECT, and a full
# physical-pixel capture for comparison with the report screenshots.
param(
    [int]$ConsoleLines = 32,
    [int]$ConsoleCols = 170,
    [string]$Out = "$env:TEMP\physical_full.png"
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TB7 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int hh, bool repaint);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
[void][TB7]::SetProcessDPIAware()

$sw = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
Write-Output "PrimaryScreen.Bounds (DPI-aware) = $($sw.Width) x $($sw.Height)"

$cmd = Join-Path $env:WINDIR 'System32\cmd.exe'
$p = Start-Process -FilePath $cmd -ArgumentList "/k mode con lines=$ConsoleLines cols=$ConsoleCols && echo hello" -PassThru
Start-Sleep -Seconds 4
$h = $p.MainWindowHandle
$r = New-Object TB7+RECT
[TB7]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "console physical RECT: $($r.Left),$($r.Top) - $($r.Right),$($r.Bottom)  size=$($r.Right - $r.Left) x $($r.Bottom - $r.Top)"
[TB7]::MoveWindow($h, 0, 0, ($r.Right - $r.Left), ($r.Bottom - $r.Top), $true) | Out-Null
[TB7]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Seconds 2
[TB7]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "console after move     : $($r.Left),$($r.Top) - $($r.Right),$($r.Bottom)  size=$($r.Right - $r.Left) x $($r.Bottom - $r.Top)"

$bmp = New-Object System.Drawing.Bitmap(1920, 1080)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved $Out"

Stop-Process -Id $p.Id -Force
