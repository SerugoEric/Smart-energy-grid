# Where is the taskbar? Prints the RECT of Shell_TrayWnd and the work area.
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class TrayProbe {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassName(IntPtr h, StringBuilder sb, int n);
    [DllImport("user32.dll")]
    public static extern bool SystemParametersInfo(uint uiAction, uint uiParam, ref RECT pvParam, uint fWinIni);
}
"@
$h = [TrayProbe]::FindWindow("Shell_TrayWnd", $null)
if ($h -eq [IntPtr]::Zero) { Write-Output "Shell_TrayWnd NOT FOUND (taskbar hidden or absent)"; exit }
$r = New-Object TrayProbe+RECT
[TrayProbe]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "Shell_TrayWnd RECT: Left=$($r.Left) Top=$($r.Top) Right=$($r.Right) Bottom=$($r.Bottom)"
$wa = New-Object TrayProbe+RECT
# SPI_GETWORKAREA = 0x0030
[TrayProbe]::SystemParametersInfo(0x0030, 0, [ref]$wa, 0) | Out-Null
Write-Output "Work area: Left=$($wa.Left) Top=$($wa.Top) Right=$($wa.Right) Bottom=$($wa.Bottom)"
Write-Output "Visible: $([bool]($r.Top -lt 720 -and $r.Bottom -gt $r.Top))"
