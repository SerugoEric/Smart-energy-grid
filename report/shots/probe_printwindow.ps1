# Capture the taskbar two ways and report which one contains content.
param([string]$Out = "$env:TEMP\taskbar_printwindow.png")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class TB {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
"@
$h = [TB]::FindWindow("Shell_TrayWnd", $null)
$r = New-Object TB+RECT
[TB]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.Right - $r.Left
$ht = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
# PW_RENDERFULLCONTENT = 0x00000002
$ok = [TB]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "PrintWindow ok=$ok size=${w}x${ht} saved=$Out"

# colour census
$img = [System.Drawing.Bitmap]::FromFile($Out)
$counts = @{}
for ($y = 0; $y -lt $img.Height; $y += 2) {
    for ($x = 0; $x -lt $img.Width; $x += 2) {
        $c = $img.GetPixel($x, $y)
        $k = "$($c.R),$($c.G),$($c.B)"
        if ($counts.ContainsKey($k)) { $counts[$k]++ } else { $counts[$k] = 1 }
    }
}
$img.Dispose()
$counts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 10 |
    ForEach-Object { Write-Output ("  {0}  {1}" -f $_.Key, $_.Value) }
