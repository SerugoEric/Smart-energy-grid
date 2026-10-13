# Physical-pixel probe of the real 1920x1080 taskbar.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TB6 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
[void][TB6]::SetProcessDPIAware()

$h = [TB6]::FindWindow("Shell_TrayWnd", $null)
$r = New-Object TB6+RECT
[TB6]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "physical tray RECT: $($r.Left),$($r.Top) - $($r.Right),$($r.Bottom)"

function Census([int]$y, [string]$label) {
    $bmp = New-Object System.Drawing.Bitmap(1920, 60)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, $y, 0, 0, $bmp.Size)
    $g.Dispose()
    $c = @{}
    for ($yy = 0; $yy -lt 60; $yy++) { for ($x = 0; $x -lt 1920; $x++) {
        $p = $bmp.GetPixel($x, $yy); $k = "$($p.R),$($p.G),$($p.B)"
        if ($c.ContainsKey($k)) { $c[$k]++ } else { $c[$k] = 1 } } }
    $bmp.Dispose()
    $top = ($c.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 4 |
            ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "  "
    Write-Output "$label colours=$($c.Count) | $top"
}

Census 1020 "no hover :"
[TB6]::SetCursorPos(960, 1079) | Out-Null
Start-Sleep -Milliseconds 1500
[TB6]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "after hover RECT: $($r.Left),$($r.Top) - $($r.Right),$($r.Bottom)"
Census 1020 "hovered  :"
