# Capture only the owned launcher and its system icons; never start its VM.
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$Root
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing, System.Windows.Forms, UIAutomationClient, UIAutomationTypes
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class IconProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr c);
    [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr w);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr w, out Rect r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr w);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr w, IntPtr process);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint from, uint to, bool attach);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr w, int x, int y, int width, int height, bool repaint);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr w, int mode);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr w);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr w, uint m, IntPtr a, IntPtr b);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr w, uint m, IntPtr a, IntPtr b);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
}
'@
[void][IconProbe]::SetProcessDpiAwarenessContext([IntPtr](-4))
$Root = [IO.Path]::GetFullPath($Root)
if (Test-Path -LiteralPath $Root) { throw 'Use a new isolated acceptance directory' }
foreach ($sub in @('local', 'roaming', 'temp', 'evidence')) {
    New-Item -ItemType Directory -Path (Join-Path $Root $sub) -Force | Out-Null
}
$env:LOCALAPPDATA = Join-Path $Root 'local'
$env:APPDATA = Join-Path $Root 'roaming'
$env:TEMP = Join-Path $Root 'temp'
$evidence = Join-Path $Root 'evidence'
$previousForeground = [IconProbe]::GetForegroundWindow()
$previousPointer = [Windows.Forms.Cursor]::Position
function Bounds([IntPtr]$window) {
    $r = New-Object IconProbe+Rect
    [void][IconProbe]::GetWindowRect($window, [ref]$r)
    return $r
}
function Foreground([IntPtr]$window) {
    $currentThread = [IconProbe]::GetCurrentThreadId()
    $foregroundThread = [IconProbe]::GetWindowThreadProcessId([IconProbe]::GetForegroundWindow(), [IntPtr]::Zero)
    $attached = $false
    if ($foregroundThread -ne $currentThread) {
        $attached = [IconProbe]::AttachThreadInput($currentThread, $foregroundThread, $true)
    }
    try {
        # An ALT key transition releases Windows' foreground activation lock.
        [IconProbe]::keybd_event(18,0,0,[UIntPtr]::Zero)
        [IconProbe]::keybd_event(18,0,2,[UIntPtr]::Zero)
        [void][IconProbe]::SetForegroundWindow($window)
        Start-Sleep -Milliseconds 100
    } finally {
        if ($attached) { [void][IconProbe]::AttachThreadInput($currentThread, $foregroundThread, $false) }
    }
}
function Capture($rectangle, [string]$path) {
    $width = [int]($rectangle.Right - $rectangle.Left)
    $height = [int]($rectangle.Bottom - $rectangle.Top)
    $bitmap = New-Object Drawing.Bitmap($width, $height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen([int]$rectangle.Left, [int]$rectangle.Top, 0, 0, $bitmap.Size)
        $bitmap.Save($path, [Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
function Click([int]$x, [int]$y) {
    [void][IconProbe]::SetCursorPos($x, $y)
    [IconProbe]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
    [IconProbe]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
    Start-Sleep -Milliseconds 500
}
$app = Start-Process -FilePath $Exe -PassThru
try {
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        Start-Sleep -Milliseconds 100
        $app.Refresh()
        if ($app.HasExited) { throw 'Launcher exited before showing a window' }
        if ($app.MainWindowHandle -ne [IntPtr]::Zero) { break }
    }
    $window = $app.MainWindowHandle
    if ($window -eq [IntPtr]::Zero) { throw 'No owned window appeared' }
    Start-Sleep -Seconds 2
    Foreground $window
    $shellIcon = [Drawing.Icon]::ExtractAssociatedIcon($Exe)
    try {
        $bitmap = $shellIcon.ToBitmap()
        try { $bitmap.Save((Join-Path $evidence 'windows-shell-icon.png')) } finally { $bitmap.Dispose() }
    } finally { $shellIcon.Dispose() }
    $icon = [IconProbe]::SendMessage($window, 127, [IntPtr]1, [IntPtr]::Zero)
    if ($icon -eq [IntPtr]::Zero) { $icon = [IconProbe]::SendMessage($window, 127, [IntPtr]0, [IntPtr]::Zero) }
    if ($icon -eq [IntPtr]::Zero) { throw 'Native window has no WM_GETICON handle' }
    $bitmap = [Drawing.Icon]::FromHandle($icon).ToBitmap()
    try { $bitmap.Save((Join-Path $evidence 'windows-window-icon.png')) } finally { $bitmap.Dispose() }
    $monitors = @()
    $index = 0
    foreach ($screen in [Windows.Forms.Screen]::AllScreens) {
        [void][IconProbe]::MoveWindow($window, $screen.Bounds.X+100, $screen.Bounds.Y+100, 800, 600, $true)
        Start-Sleep -Milliseconds 700
        $dpi = [IconProbe]::GetDpiForWindow($window)
        [void][IconProbe]::MoveWindow($window, $screen.Bounds.X+100, $screen.Bounds.Y+100, [int](800*$dpi/96), [int](600*$dpi/96), $true)
        Foreground $window
        Start-Sleep -Milliseconds 700
        $r = Bounds $window
        Capture $r (Join-Path $evidence "windows-monitor-$index.png")
        $monitors += [ordered]@{ dpi = $dpi; width = $r.Right-$r.Left; height = $r.Bottom-$r.Top }
        $index++
    }
    $r = Bounds $window
    $scale = [IconProbe]::GetDpiForWindow($window)/96
    if ([IconProbe]::GetForegroundWindow() -ne $window) { throw 'Refusing pointer input without owned foreground window' }
    # Actual pointer drag on the blank HTML header exercises Wails drag handling.
    [void][IconProbe]::SetCursorPos($r.Left+[int](450*$scale), $r.Top+[int](30*$scale))
    [IconProbe]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
    Start-Sleep -Milliseconds 150
    [void][IconProbe]::SetCursorPos($r.Left+[int](500*$scale), $r.Top+[int](60*$scale))
    Start-Sleep -Milliseconds 300
    [IconProbe]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
    Start-Sleep -Milliseconds 500
    $moved = Bounds $window
    $dragged = $moved.Left -ne $r.Left -or $moved.Top -ne $r.Top
    Click ($moved.Right-[int](67*$scale)) ($moved.Top+[int](30*$scale))
    $minimized = [IconProbe]::IsIconic($window)
    [void][IconProbe]::ShowWindow($window, 9)
    Foreground $window
    Start-Sleep -Milliseconds 500
    $r = Bounds $window
    Capture $r (Join-Path $evidence 'windows-header.png')
    Click ($r.Right-[int](33*$scale)) ($r.Top+[int](30*$scale))
    $closed = $app.WaitForExit(5000)
    if (-not $closed) { throw 'Header close did not close the idle launcher' }
    if (-not $dragged -or -not $minimized) { throw "Header control failure: drag=$dragged minimize=$minimized" }
    [ordered]@{
        executable = $Exe; nativeWindowIcon = $true; shellIconExtracted = $true
        monitors = $monitors; headerDrag = $dragged; headerMinimize = $minimized
        headerIdleClose = $closed; vmStarted = $false
        taskbarVisual = 'not yet captured'; altTabVisual = 'not yet captured'
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $evidence 'windows-window.json')
} finally {
    if (-not $app.HasExited) { [void][IconProbe]::PostMessage($app.MainWindowHandle,16,[IntPtr]::Zero,[IntPtr]::Zero) }
    [void][IconProbe]::SetCursorPos($previousPointer.X,$previousPointer.Y)
    [void][IconProbe]::SetForegroundWindow($previousForeground)
}
