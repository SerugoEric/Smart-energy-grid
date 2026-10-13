# Capture one evidence screenshot for the report.
#
# The assignment requires every screenshot to show the executed command or
# action, its result, the taskbar and the clock. A full-screen capture of the
# interactive desktop includes the taskbar and the clock automatically, so this
# helper only has to make sure the command and its output are on screen first.
#
#   .\report\capture_screenshot.ps1 -Name 1_1_database `
#       -Command "docker exec -it timescaledb psql -U auca -d smart_energy_grid -c `"select current_database();`""
#
#   .\report\capture_screenshot.ps1 -Name dashboard_raw   # just capture now
#
# Parameters
#   Name             file name (without extension) written to report\screenshots\
#   Command          optional command line; opened in a visible cmd window
#   WorkingDirectory folder for the visible window, defaults to the project root
#   WaitSeconds      seconds to leave the window on screen before capturing
#   KeepWindow       leave the window open after the capture
#
# The window is closed by matching its process id, so no other window is
# touched.

param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [string]$Command = "",

    [string]$WorkingDirectory = "",

    [int]$WaitSeconds = 12,

    [int]$ConsoleLines = 32,

    [int]$ConsoleCols = 170,

    # Open a picture (chart) instead of a console window. Used for Sections
    # that must screenshot a generated chart together with the taskbar and
    # the clock, which a bare file copy of the PNG would not show.
    [string]$Image = "",

    # Bring this process name to the front just before the capture. Needed when
    # the command starts a browser: the evidence window itself would otherwise
    # sit on top of the dashboard and hide it.
    [string]$FrontProcess = "",

    # Only consider windows of $FrontProcess whose title contains this text.
    # Chrome restores the tabs of a session it had to kill, and the first
    # chrome.exe with a window is then usually that restored window rather than
    # the one carrying the page the screenshot is about.
    [string]$FrontTitle = "",

    # Only consider processes whose command line contains this text (for a
    # browser: the dedicated --user-data-dir profile of the instance under
    # test). More reliable than the title, which Chrome changes to
    # "Updating..." while a Dash callback is running.
    [string]$FrontMatch = "",

    # Minimise the evidence window just before the capture. More reliable than
    # activating another window: Windows can refuse a foreground change, but it
    # always honours a minimise, so the maximised browser behind is visible.
    [switch]$HideWindow,

    [switch]$KeepWindow
)

$ErrorActionPreference = "Stop"

# The desktop is 1920x1080 physical pixels behind 150% display scaling.
# PowerShell starts as a DPI-unaware process, so Win32 reports a virtualised
# 1280x720 desktop to it. CopyFromScreen still addresses physical pixels, so
# the frame grabbed only the top-left 1280x720 of the screen: the console
# window was scaled down to 1261x549 and the taskbar strip at y=1020 never
# entered the picture at all. Every screenshot taken that way is missing the
# taskbar and the clock the assignment asks for. Opting in to DPI awareness
# makes Screen.Bounds, GetWindowRect and CopyFromScreen agree on physical
# pixels, so the frame covers the whole 1920x1080 desktop including the bar.
Add-Type -Namespace Native -Name Dpi -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
"@
[void][Native.Dpi]::SetProcessDPIAware()

$projectRoot = Split-Path -Parent $PSScriptRoot
if ($WorkingDirectory -eq "") { $WorkingDirectory = $projectRoot }

$screenshotDir = Join-Path $projectRoot "report\screenshots"
if (-not (Test-Path $screenshotDir)) { New-Item -ItemType Directory -Path $screenshotDir | Out-Null }
$target = Join-Path $screenshotDir "$Name.png"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$process = $null
$imageProcess = $null
if ($Image -ne "") {
    $imageProcess = Start-Process -FilePath $Image -PassThru
    Start-Sleep -Seconds $WaitSeconds
}
if ($Command -ne "") {
    # mode con makes the window as tall as the screen allows. The command is
    # echoed again at the end so the window still shows WHAT was run after a
    # long output has scrolled the original prompt off the top; metacharacters
    # are caret-escaped so echo prints them instead of acting on them.
    $escaped = $Command -replace '([&|^<>])', '^$1'
    $launcher = "cd /d `"$WorkingDirectory`" && mode con lines=$ConsoleLines cols=$ConsoleCols && $Command && echo. && echo Executed: $escaped"
    $process = Start-Process -FilePath "cmd.exe" `
        -ArgumentList @("/k", $launcher) `
        -WorkingDirectory $WorkingDirectory `
        -PassThru
    Start-Sleep -Seconds $WaitSeconds
}

# Pin the window to the top-left corner in physical pixels. cmd lets its own
# cascade placement decide where the window opens, and that placement has been
# observed at x = 127 logical (190 physical), which pushes the right edge of a
# 170-column window past the right edge of the screen and silently clips the
# longest output lines. At 170 columns the window is 1892 x 824 physical, so
# (0,0) leaves the bottom 196 pixels and the whole taskbar strip visible.
if ($process) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class CaptureWin32 {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(
        IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool MoveWindow(
        IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}
"@
    $rect = New-Object CaptureWin32+RECT
    if ([CaptureWin32]::GetWindowRect($process.MainWindowHandle, [ref]$rect)) {
        $w = $rect.Right - $rect.Left
        $h = $rect.Bottom - $rect.Top
        $null = [CaptureWin32]::MoveWindow($process.MainWindowHandle, 0, 0, $w, $h, $true)
    }
}

# Bring the capture window to the front so nothing else covers the command.
if ($process) {
    Add-Type -AssemblyName Microsoft.VisualBasic
    try {
        [Microsoft.VisualBasic.Interaction]::AppActivate($process.Id) 2>$null | Out-Null
    } catch { }
    Start-Sleep -Seconds 1
}

# Minimise that window again when asked: the browser behind must be visible
# and a minimise always succeeds, unlike a foreground change.
if ($HideWindow -and $process) {
    if (-not ("Capture.W" -as [type])) {
        Add-Type -Namespace Capture -Name W -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
"@
    }
    [void][Capture.W]::ShowWindow($process.MainWindowHandle, 6)
    Start-Sleep -Seconds 1
}

# ... unless a browser (or any other program) was started and is the real
# subject of the screenshot. A maximised browser then covers the console
# window completely, so the panel the capture is meant to show is visible.
# Activation is retried until the window really is the foreground window,
# because other applications (a messaging app, the editor) may grab the
# foreground again while the wait runs and would otherwise be captured.
if ($FrontProcess -ne "") {
    Add-Type -AssemblyName Microsoft.VisualBasic
    if (-not ("Capture.Fg" -as [type])) {
        Add-Type -Namespace Capture -Name Fg -MemberDefinition @"
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
[DllImport("user32.dll")] public static extern bool SetWindowPos(
    IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
"@
    }
    # Force the window to the maximised state before it is activated. Chrome
    # opens a restored window when it is started from a hidden console, and a
    # restored window sits lower on the screen, which pushes the second row of
    # dashboard panels underneath the taskbar. SW_MAXIMIZE (3) plus a move to
    # (0,0) puts the page viewport back at the top of the screen.
    $subject = Get-Process -Name $FrontProcess -ErrorAction SilentlyContinue |
               Where-Object { $_.MainWindowHandle -ne 0 }
    if ($FrontTitle -ne "") {
        $subject = $subject |
                   Where-Object { $_.MainWindowTitle -like "*$FrontTitle*" }
    }
    if ($FrontMatch -ne "") {
        $ids = (Get-CimInstance Win32_Process -Filter "Name='$FrontProcess.exe'" |
                Where-Object { $_.CommandLine -like "*$FrontMatch*" } |
                Select-Object -ExpandProperty ProcessId)
        $subject = $subject | Where-Object { $ids -contains $_.Id }
    }
    foreach ($win in $subject) {
        try {
            [void][Capture.Fg]::ShowWindow($win.MainWindowHandle, 3)
            [void][Capture.Fg]::SetWindowPos($win.MainWindowHandle,
                [IntPtr]::Zero, 0, 0, 0, 0, 0x0013)  # NOMOVE|NOZORDER|NOACTIVATE
        } catch { }
    }
    if ($subject) { Start-Sleep -Seconds 2 }
    $activated = $false
    for ($try = 0; $try -lt 12 -and -not $activated; $try++) {
        $front = Get-Process -Name $FrontProcess -ErrorAction SilentlyContinue |
                 Where-Object { $_.MainWindowHandle -ne 0 }
        if ($FrontTitle -ne "") {
            $front = $front |
                     Where-Object { $_.MainWindowTitle -like "*$FrontTitle*" }
        }
        if ($FrontMatch -ne "") {
            $ids = (Get-CimInstance Win32_Process |
                    Where-Object { $_.Name -eq "$FrontProcess.exe" -and
                                   $_.CommandLine -like "*$FrontMatch*" } |
                    Select-Object -ExpandProperty ProcessId)
            $front = $front | Where-Object { $ids -contains $_.Id }
        }
        $front = $front | Select-Object -First 1
        if ($front) {
            try {
                [void][Capture.Fg]::SetForegroundWindow($front.MainWindowHandle)
            } catch { }
            try {
                [Microsoft.VisualBasic.Interaction]::AppActivate($front.Id) 2>$null | Out-Null
            } catch { }
            Start-Sleep -Milliseconds 800
            $activated = ([Capture.Fg]::GetForegroundWindow() -eq
                          $front.MainWindowHandle)
        } else {
            Start-Sleep -Seconds 1
        }
    }
    Start-Sleep -Seconds 2
}

try {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
} finally {
    # Always close the evidence window, even when the capture itself failed.
    # A window left behind at (0,0) hides the next screenshot completely.
    if ($process -and -not $KeepWindow) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    if ($imageProcess -and -not $KeepWindow) {
        Stop-Process -Id $imageProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Output $target
