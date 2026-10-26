# Focused native Windows integration check. Does not append a Guest or start a VM.
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Commit
)
$ErrorActionPreference = 'Stop'
Set-Location $Source
$env:PATH = (Join-Path (& go env GOROOT).Trim() 'bin') + ';' + $env:PATH
$global:PiworkIconRealGo = (Get-Command go).Source
$resource = Join-Path $Source 'cmd/piwork-launcher/rsrc_windows_amd64.syso'
if (Test-Path -LiteralPath $resource) { throw 'Resource already exists; refusing to disturb another build' }
$builder = Join-Path $Source 'scripts/gui-build-windows.ps1'
$body = Join-Path $Source 'dist/launcher-gui-windows.exe'
& $builder -Source $Source -Output $body -Version $Version -Commit $Commit
& go run ./tools/gui-resources -verify-exe $body
if ($LASTEXITCODE) { throw 'PowerShell body icon verification failed' }
$record = Get-Content dist/build-bodies/gui-windows.json -Raw | ConvertFrom-Json
$driver = @'
import importlib.util, os, pathlib, sys
root = pathlib.Path.cwd()
spec = importlib.util.spec_from_file_location('gui_build', root / 'scripts/gui-build.py')
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)
identity = gui.bundle.build_identity(root / 'dist', 2)
identity['version'] = sys.argv[1]
environment = os.environ.copy()
environment.update(CGO_ENABLED='1', GOTOOLCHAIN='local', GOOS='windows', GOARCH='amd64')
gui.build_body('windows', root / 'dist/launcher-python-windows.exe', identity, environment)
print('Python GUI body compiled; fingerprint=' + gui.bundle.source_fingerprint(entry='gui'))
'@
& python -c $driver $Version
if ($LASTEXITCODE) { throw 'Python GUI body build failed' }
& go run ./tools/gui-resources -verify-exe dist/launcher-python-windows.exe
if ($LASTEXITCODE) { throw 'Python body icon verification failed' }
$pythonRecord = Get-Content dist/build-bodies/gui-windows.json -Raw | ConvertFrom-Json
if ($record.sourceFingerprint -ne $pythonRecord.sourceFingerprint) { throw 'Python and PowerShell fingerprints differ' }
# Preserve the record belonging to the primary body used for final packaging.
$record | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 dist/build-bodies/gui-windows.json

function go {
    if ($args[0] -eq 'build') { throw 'Injected compiler failure for cleanup verification' }
    & $global:PiworkIconRealGo @args
}
$failed = $false
try { & $builder -Source $Source -Output $body -Version $Version -Commit $Commit } catch {
    if ($_ -notmatch 'Injected compiler failure') { throw }
    $failed = $true
} finally { Remove-Item Function:go; Remove-Variable PiworkIconRealGo -Scope Global }
if (-not $failed -or (Test-Path -LiteralPath $resource)) { throw 'Failed build leaked a resource' }

Set-Content -LiteralPath $resource -Value 'acceptance ownership sentinel' -Encoding ascii
try {
    $failed = $false
    try { & $builder -Source $Source -Output $body -Version $Version -Commit $Commit } catch {
        if ($_ -notmatch 'GUI resource generation failed') { throw }
        $failed = $true
    }
    if (-not $failed -or (Get-Content -LiteralPath $resource -Raw).Trim() -ne 'acceptance ownership sentinel') {
        throw 'Build overwrote or removed another owners resource'
    }
} finally { Remove-Item -LiteralPath $resource }
if (@(Get-ChildItem dist -Directory -Filter 'gui-resources-*').Count) { throw 'Leaked resource working directory' }
[ordered]@{
    powershellIconVerified = $true
    pythonIconVerified = $true
    sourceFingerprintsEqual = $true
    sourceFingerprint = $record.sourceFingerprint
    compilerFailureCleaned = $true
    existingResourcePreserved = $true
} | ConvertTo-Json | Set-Content -Encoding utf8 dist/icon-build-check.json
