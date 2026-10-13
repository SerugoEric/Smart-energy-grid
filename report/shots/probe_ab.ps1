# Decisive test: does opening a console window make the taskbar vanish from
# a GDI screen grab?  Measures the tray RECT and the strip census before,
# during and after a console window is on screen.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TB4 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
}
"@

function Strip {
    $h = [TB4]::FindWindow("Shell_TrayWnd", $null)
    $r = New-Object TB4+RECT
    [TB4]::GetWindowRect($h, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap(1280, 40)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, 680, 0, 0, $bmp.Size)
    $g.Dispose()
    $c = @{}
    for ($y = 0; $y -lt 40; $y++) { for ($x = 0; $x -lt 1280; $x++) {
        $p = $bmp.GetPixel($x, $y); $k = "$($p.R),$($p.G),$($p.B)"
        if ($c.ContainsKey($k)) { $c[$k]++ } else { $c[$k] = 1 } } }
    $bmp.Dispose()
    $distinct = $c.Count
    $top = ($c.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 3 |
            ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "  "
    Write-Output "  RECT=$($r.Left),$($r.Top),$($r.Right),$($r.Bottom)  colours=$distinct  | $top"
}

Write-Output "1) no console:"
Strip

$p = Start-Process -FilePath "$env:WINDIR\System32\cmd.exe" -ArgumentList "/k echo hello" -PassThru
Start-Sleep -Seconds 3
Write-Output "2) console open:"
Strip

Stop-Process -Id $p.Id -Force
Start-Sleep -Seconds 2
Write-Output "3) console closed:"
Strip
