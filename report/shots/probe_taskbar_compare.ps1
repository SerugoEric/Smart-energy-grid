# Compare a GDI screen grab of the taskbar strip with PrintWindow of the same
# window, under identical conditions, to find out why the strip comes back blank.
param([string]$Out = "$env:TEMP\taskbar_screen.png")
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TB2 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
"@

function Census([System.Drawing.Bitmap]$b, [string]$label) {
    $counts = @{}
    for ($y = 0; $y -lt $b.Height; $y++) {
        for ($x = 0; $x -lt $b.Width; $x++) {
            $c = $b.GetPixel($x, $y)
            $k = "$($c.R),$($c.G),$($c.B)"
            if ($counts.ContainsKey($k)) { $counts[$k]++ } else { $counts[$k] = 1 }
        }
    }
    Write-Output "--- $label  ($($b.Width)x$($b.Height), $($counts.Count) colours)"
    $counts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 5 |
        ForEach-Object { Write-Output ("    {0}  {1}" -f $_.Key, $_.Value) }
}

$h = [TB2]::FindWindow("Shell_TrayWnd", $null)
$r = New-Object TB2+RECT
[TB2]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "Shell_TrayWnd RECT: $($r.Left),$($r.Top) - $($r.Right),$($r.Bottom)"

# 1. GDI screen grab of the strip
$strip = New-Object System.Drawing.Bitmap(($r.Right - $r.Left), ($r.Bottom - $r.Top))
$g = [System.Drawing.Graphics]::FromImage($strip)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $strip.Size)
$g.Dispose()
Census $strip "GDI CopyFromScreen of taskbar strip"
$strip.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$strip.Dispose()

# 2. PrintWindow of the same window
$pw = New-Object System.Drawing.Bitmap(($r.Right - $r.Left), ($r.Bottom - $r.Top))
$g2 = [System.Drawing.Graphics]::FromImage($pw)
$hdc = $g2.GetHdc()
$ok = [TB2]::PrintWindow($h, $hdc, 2)
$g2.ReleaseHdc($hdc)
$g2.Dispose()
Write-Output "PrintWindow returned $ok"
Census $pw "PrintWindow of taskbar"
$pw.Dispose()
