# Diagnostic: list every visible top-level window with its physical pixel
# rectangle, so a screenshot that shows the wrong thing can be explained.
Add-Type -Namespace N -Name D -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
'@
[void][N.D]::SetProcessDPIAware()

Add-Type -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
public struct RECT { public int Left, Top, Right, Bottom; }
'@ -Name Win -Namespace W

Get-Process |
    Where-Object { $_.MainWindowHandle -ne 0 -and [W.Win]::IsWindowVisible($_.MainWindowHandle) } |
    ForEach-Object {
        $r = New-Object W.Win+RECT
        [void][W.Win]::GetWindowRect($_.MainWindowHandle, [ref]$r)
        "{0,-14} pid={1,-7} rect=({2},{3})-({4},{5})  {6}" -f `
            $_.ProcessName, $_.Id, $r.Left, $r.Top, $r.Right, $r.Bottom, `
            $_.MainWindowTitle.Substring(0, [Math]::Min(60, $_.MainWindowTitle.Length))
    }
