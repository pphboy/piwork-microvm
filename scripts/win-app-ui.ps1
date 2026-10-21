# Acceptance-only Windows UI driver. It posts mouse messages to the Launcher's
# WebView2 child window and captures that window only, so concurrent desktop
# use and other windows are never targeted.
param(
    [Parameter(Mandatory = $true)][ValidateSet('click', 'capture', 'windows')][string]$Action,
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [int]$X = 0,
    [int]$Y = 0,
    [string]$Out = '',
    [int64]$WindowHandle = 0
)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class AppUi {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr h);
  [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr h, IntPtr dc);
  [DllImport("gdi32.dll")] public static extern IntPtr CreateCompatibleDC(IntPtr dc);
  [DllImport("gdi32.dll")] public static extern IntPtr CreateCompatibleBitmap(IntPtr dc, int w, int h);
  [DllImport("gdi32.dll")] public static extern IntPtr SelectObject(IntPtr dc, IntPtr obj);
  [DllImport("gdi32.dll")] public static extern bool DeleteObject(IntPtr obj);
  [DllImport("gdi32.dll")] public static extern bool DeleteDC(IntPtr dc);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,Rt,B; }
}
'@
$proc = Get-Process -Id $ProcessId -ErrorAction Stop
$top = $proc.MainWindowHandle
if ($WindowHandle) {
    if ($Action -ne 'capture') { throw 'explicit window handle is capture-only' }
    $owner = [uint32]0
    [AppUi]::GetWindowThreadProcessId([IntPtr]$WindowHandle, [ref]$owner) | Out-Null
    if ($owner -ne $ProcessId) { throw 'capture window belongs to another process' }
    $top = [IntPtr]$WindowHandle
}
if ($top -eq [IntPtr]::Zero) { throw 'launcher window is not available' }
$render = [IntPtr]::Zero
$callback = [AppUi+EnumProc]{
    param($h, $l)
    $name = New-Object System.Text.StringBuilder 256
    [AppUi]::GetClassName($h, $name, 256) | Out-Null
    if ($name.ToString() -eq 'Chrome_RenderWidgetHostHWND') { $script:render = $h }
    return $true
}
[AppUi]::EnumChildWindows($top, $callback, [IntPtr]::Zero) | Out-Null
if ($render -eq [IntPtr]::Zero -and $Action -ne 'capture') { throw 'WebView2 render child was not found' }

if ($Action -eq 'click') {
    [AppUi]::SetForegroundWindow($top) | Out-Null
    $lp = [IntPtr](($Y -shl 16) -bor ($X -band 0xffff))
    [AppUi]::PostMessage($render, 0x0200, [IntPtr]::Zero, $lp) | Out-Null
    Start-Sleep -Milliseconds 80
    [AppUi]::PostMessage($render, 0x0201, [IntPtr]1, $lp) | Out-Null
    Start-Sleep -Milliseconds 80
    [AppUi]::PostMessage($render, 0x0202, [IntPtr]::Zero, $lp) | Out-Null
    Write-Output "clicked $X,$Y"
    exit 0
}
if ($Action -eq 'windows') {
    Write-Output "top=$top render=$render"
    exit 0
}
if (-not $Out) { throw 'capture requires -Out' }
$rect = New-Object AppUi+RECT
[AppUi]::GetWindowRect($top, [ref]$rect) | Out-Null
$w = $rect.Rt - $rect.L
$h = $rect.B - $rect.T
if ($w -le 0 -or $h -le 0) { throw "window size is invalid: ${w}x${h}" }
$screen = [AppUi]::GetDC([IntPtr]::Zero)
$mem = [AppUi]::CreateCompatibleDC($screen)
$bmp = [AppUi]::CreateCompatibleBitmap($screen, $w, $h)
$old = [AppUi]::SelectObject($mem, $bmp)
$ok = [AppUi]::PrintWindow($top, $mem, 2)
[AppUi]::SelectObject($mem, $old) | Out-Null
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromHbitmap($bmp)
$image.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$image.Dispose()
[AppUi]::DeleteObject($bmp) | Out-Null
[AppUi]::DeleteDC($mem) | Out-Null
[AppUi]::ReleaseDC([IntPtr]::Zero, $screen) | Out-Null
Write-Output "captured=$ok size=${w}x${h} out=$Out"
