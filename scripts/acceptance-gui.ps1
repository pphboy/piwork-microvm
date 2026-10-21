# Acceptance-only isolation harness for the Windows GUI.
# Refuses the user's default data/config roots, creates a marked dedicated tree,
# checks the two host ports and optionally launches the final PE with redirected
# LOCALAPPDATA/APPDATA/TEMP. It never kills existing processes.
param(
    [string]$Root = 'C:\Users\p\piwork-gui-acceptance',
    [string]$Exe = 'C:\Users\p\piwork-gui-accept-win\piwork-microvm-gui.exe',
    [switch]$Run
)
$ErrorActionPreference = 'Stop'
function Full([string]$p) { [System.IO.Path]::GetFullPath($p).TrimEnd('\') }
$Root = Full $Root
$Exe = Full $Exe
$defaults = @(
    (Full (Join-Path $env:LOCALAPPDATA 'PiworkMicroVM')),
    (Full (Join-Path $env:APPDATA 'piwork-microvm'))
)
foreach ($d in $defaults) {
    if ($Root -eq $d -or $Root.StartsWith($d + '\')) { throw "refusing root that is or contains a user default: $Root" }
}
if (-not (Test-Path -LiteralPath $Exe)) { throw "missing GUI artifact: $Exe" }
foreach ($sub in @('local', 'roaming', 'temp')) {
    New-Item -ItemType Directory -Force (Join-Path $Root $sub) | Out-Null
}
$marker = Join-Path $Root '.piwork-gui-acceptance'
if (-not (Test-Path -LiteralPath $marker)) {
    Set-Content -LiteralPath $marker -Value @("owner=$env:USERNAME", "created=$([DateTime]::UtcNow.ToString('o'))") -Encoding ASCII
}
foreach ($port in @(17891, 17871)) {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() } catch { throw "port $port is already in use; refusing to disturb an existing service" } finally { $listener.Stop() }
}
$defaultInstall = Join-Path $env:LOCALAPPDATA 'PiworkMicroVM\installation.json'
$before = if (Test-Path -LiteralPath $defaultInstall) { (Get-FileHash -LiteralPath $defaultInstall -Algorithm SHA256).Hash.ToLower() } else { 'absent' }
Write-Output "root=$Root"
Write-Output "exe=$Exe"
Write-Output "default-installation-sha=$before"
Write-Output "marker=$(Get-Content -LiteralPath $marker | Out-String)"
if (-not $Run) {
    Write-Output 'check-only: no process was started and no default path was modified'
    exit 0
}
$env:LOCALAPPDATA = Join-Path $Root 'local'
$env:APPDATA = Join-Path $Root 'roaming'
$env:TEMP = Join-Path $Root 'temp'
$p = Start-Process -FilePath $Exe -WorkingDirectory (Join-Path $Root 'temp') -PassThru
Set-Content -LiteralPath (Join-Path $Root 'gui.pid') -Value $p.Id -Encoding ASCII
Write-Output "started pid=$($p.Id)"
