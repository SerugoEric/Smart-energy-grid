# DPI-aware reveal test: park the cursor on the bottom edge, then census the
# taskbar strip.  SetCursorPos from a non-DPI-aware process is virtualised to
# logical pixels, so the process must opt in to physical coordinates first.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TB5 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@
[void][TB5]::SetProcessDPIAware()

function Census([string]$label) {
    $bmp = New-Object System.Drawing.Bitmap(1280, 40)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, 680, 0, 0, $bmp.Size)
    $g.Dispose()
    $c = @{}
    for ($y = 0; $y -lt 40; $y++) { for ($x = 0; $x -lt 1280; $x++) {
        $p = $bmp.GetPixel($x, $y); $k = "$($p.R),$($p.G),$($p.B)"
        if ($c.ContainsKey($k)) { $c[$k]++ } else { $c[$k] = 1 } } }
    $bmp.Dispose()
    $top = ($c.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 3 |
            ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "  "
    Write-Output "$label colours=$($c.Count) | $top"
}

$h = [TB5]::FindWindow("Shell_TrayWnd", $null)
$r = New-Object TB5+RECT
[TB5]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "RECT=$($r.Left),$($r.Top),$($r.Right),$($r.Bottom)"

Census "before:"
[TB5]::SetCursorPos(640, 719) | Out-Null
Start-Sleep -Milliseconds 1500
[TB5]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "RECT after hover=$($r.Left),$($r.Top),$($r.Right),$($r.Bottom)"
Census "after bottom-edge hover:"

[TB5]::SetCursorPos(640, 719) | Out-Null
Start-Sleep -Milliseconds 300
Census "second grab:"
