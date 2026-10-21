# Build the native Windows Wails body. This script must run on Windows.
# It is the native half of scripts/gui-build.py; bundle.py appends the payload.
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string]$Version
)
$ErrorActionPreference = 'Stop'
Set-Location $Source
$goVersion = (& go env GOVERSION).Trim()
if ($goVersion -ne 'go1.25.5') { throw "Go $goVersion found; exactly go1.25.5 is required" }
$wailsOut = & go tool wails version 2>$null
if ($LASTEXITCODE -ne 0) { throw "go tool wails version failed" }
$wails = (($wailsOut | Select-String -Pattern '^v[0-9]' | Select-Object -First 1) -as [string]).Trim()
if ($wails -ne 'v2.17.0') { throw "Wails $wails found; v2.17.0 is required" }
$lock = Get-Content build.lock.json -Raw | ConvertFrom-Json
$meta = Get-Content dist/piwork/metadata.json -Raw | ConvertFrom-Json
$flags = @(
    '-s', '-w', '-H', 'windowsgui',
    '-X', "piwork-microvm/internal/launcher.buildVersion=$Version",
    '-X', "piwork-microvm/internal/launcher.buildUpstreamVersion=$($meta.releaseVersion)",
    '-X', "piwork-microvm/internal/launcher.buildUpstreamCommit=$($lock.piwork.commit)",
    '-X', 'piwork-microvm/internal/launcher.buildManifestVersion=v2'
) -join ' '
$env:CGO_ENABLED = '1'
$env:GOTOOLCHAIN = 'go1.25.5'
$env:GOOS = 'windows'
$env:GOARCH = 'amd64'
& go build -trimpath -buildvcs=false -tags 'desktop production' -ldflags $flags -o $Output ./cmd/piwork-launcher
if ($LASTEXITCODE -ne 0) { throw "go build failed with exit $LASTEXITCODE" }
$hash = (Get-FileHash $Output -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $Output).Length
Write-Output "windows GUI body: $Output bytes=$size sha256=$hash"
