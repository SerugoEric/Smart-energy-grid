# With a console already open: reveal the taskbar by hovering the bottom edge,
# then grab the strip. Also prints StuckRects3 so auto-hide can be read.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TB3 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X, Y; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
$h = [TB3]::FindWindow("Shell_TrayWnd", $null)
$r = New-Object TB3+RECT
[TB3]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "before hover: RECT=$($r.Left),$($r.Top),$($r.Right),$($r.Bottom) visible=$([TB3]::IsWindowVisible($h))"

[TB3]::SetCursorPos(640, 719) | Out-Null
Start-Sleep -Milliseconds 1200
[TB3]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "after hover : RECT=$($r.Left),$($r.Top),$($r.Right),$($r.Bottom)"

$strip = New-Object System.Drawing.Bitmap(1280, 40)
$g = [System.Drawing.Graphics]::FromImage($strip)
$g.CopyFromScreen(0, $r.Top, 0, 0, $strip.Size)
$g.Dispose()
$counts = @{}
for ($y = 0; $y -lt $strip.Height; $y++) {
    for ($x = 0; $x -lt $strip.Width; $x++) {
        $c = $strip.GetPixel($x, $y)
        $k = "$($c.R),$($c.G),$($c.B)"
        if ($counts.ContainsKey($k)) { $counts[$k]++ } else { $counts[$k] = 1 }
    }
}
$strip.Dispose()
Write-Output "strip at Top=$($r.Top):"
$counts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 8 |
    ForEach-Object { Write-Output ("    {0}  {1}" -f $_.Key, $_.Value) }

$bytes = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StuckRects3').Settings
Write-Output ("StuckRects3 SETTINGS: " + (($bytes | ForEach-Object { $_.ToString('X2') }) -join ' '))
