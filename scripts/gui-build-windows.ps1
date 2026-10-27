# Build the native Windows Wails body. This script must run on Windows.
# It is the native half of scripts/gui-build.py; bundle.py appends the payload.
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Commit
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
$resource = Join-Path $Source 'cmd/piwork-launcher/rsrc_windows_amd64.syso'
$resourceDir = Join-Path $Source ('dist/gui-resources-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $resourceDir | Out-Null
$ownsResource = $false
try {
    & go run ./tools/gui-resources -ico (Join-Path $resourceDir 'icon.ico') -syso $resource
    if ($LASTEXITCODE -ne 0) { throw "GUI resource generation failed with exit $LASTEXITCODE" }
    $ownsResource = $true
    & go build -trimpath -buildvcs=false -tags 'desktop production' -ldflags $flags -o $Output ./cmd/piwork-launcher
    if ($LASTEXITCODE -ne 0) { throw "go build failed with exit $LASTEXITCODE" }
} finally {
    if ($ownsResource) { Remove-Item -LiteralPath $resource -ErrorAction Stop }
    Remove-Item -LiteralPath $resourceDir -Recurse -Force
}
$hash = (Get-FileHash $Output -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $Output).Length

# The record binds this body to the exact lock; bundle.py refuses a stale body.
$modePath = Join-Path $Source 'dist/piwork/build-mode.json'
$mode = if (Test-Path -LiteralPath $modePath) {
    [string](Get-Content -LiteralPath $modePath -Raw | ConvertFrom-Json).inputMode
} elseif ($lock.piwork.inputMode) { [string]$lock.piwork.inputMode } else { 'source' }
$release = $lock.piwork.release
$assets = if ($release) { $release.assets } else { $null }
$releaseCommit = if ($release) { [string]$release.releaseCommit } else { $null }
$tag = if ($release) { [string]$release.tag } else { '' }
function LockField($value) { if ($null -eq $value) { '' } else { [string]$value } }
$fields = @(
    (LockField $mode), (LockField $lock.piwork.commit), (LockField $tag), (LockField $releaseCommit),
    (LockField $assets.archive.sha256), (LockField $assets.releaseBuild.sha256),
    (LockField $assets.releaseManifest.sha256), (LockField $assets.sha256sums.sha256),
    (LockField $lock.go), (LockField $lock.linux.sha256), (LockField $lock.qemu.sha256),
    (LockField $lock.guestBaseImage), (LockField $lock.dockerImage), (LockField $lock.debianSnapshot)
)
foreach ($patch in $lock.qemu.windowsPatches) { $fields += (LockField $patch.file); $fields += (LockField $patch.sha256) }
$slirp = $lock.qemu.libslirp
$fields += (LockField $slirp.windows.url); $fields += (LockField $slirp.windows.revision)
foreach ($patch in $slirp.windows.patches) { $fields += (LockField $patch.file); $fields += (LockField $patch.sha256) }
$fields += (LockField $slirp.linux.version); $fields += (LockField $slirp.linux.sourceBase)
foreach ($item in @($slirp.linux.files) + @($slirp.linux.patches)) { $fields += (LockField $item.file); $fields += (LockField $item.sha256) }
$fields = $fields -join "`n"
$sha = [Security.Cryptography.SHA256]::Create()
$fingerprint = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($fields))) -replace '-', '').ToLower()
$dist = Join-Path $Source 'dist'
$distFull = [IO.Path]::GetFullPath($dist)
$outputFull = [IO.Path]::GetFullPath($Output)
if ($outputFull.StartsWith($distFull, [StringComparison]::OrdinalIgnoreCase)) {
    $bodyPath = $outputFull.Substring($distFull.Length).TrimStart('\')
} else {
    $bodyPath = [IO.Path]::GetFileName($Output)
}
$goFiles = @(Get-ChildItem -LiteralPath $Source -Recurse -Filter *.go | Where-Object {
    $_.FullName -notmatch '\\(dist|openspec|node_modules|\.git)\\'
}) + @((Get-Item -LiteralPath (Join-Path $Source 'go.mod')), (Get-Item -LiteralPath (Join-Path $Source 'go.sum')))
$guiInputs = @(
    'cmd/piwork-launcher/frontend/assets/piwork-logo.png',
    'cmd/piwork-launcher/frontend/index.html',
    'cmd/piwork-launcher/ui-sources.json',
    'tools/gui-resources/main.go',
    'scripts/gui-build.py', 'scripts/gui-build-windows.ps1'
)
$goFiles += @($guiInputs | ForEach-Object { Get-Item -LiteralPath (Join-Path $Source $_) -ErrorAction Stop })
$goFiles += @(Get-ChildItem -LiteralPath (Join-Path $Source 'cmd/piwork-launcher/frontend') -Recurse -File)
$goFiles = @($goFiles | Sort-Object -Property FullName -Unique)
$sourceFull = (Resolve-Path -LiteralPath $Source).ProviderPath.TrimEnd('\')
$sourceParts = $goFiles | ForEach-Object {
    $relative = $_.FullName.Substring($sourceFull.Length).TrimStart('\').Replace('\', '/')
    $fileHash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
    [ordered]@{ rel = $relative; hash = $fileHash }
} | Sort-Object {[BitConverter]::ToString([Text.Encoding]::UTF8.GetBytes($_.rel)).Replace('-', '')}
$sourceText = ($sourceParts | ForEach-Object { $_.rel + "`0" + $_.hash + "`n" }) -join ''
$sourceFingerprint = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($sourceText))) -replace '-', '').ToLower()
$record = [ordered]@{
    recordVersion = 1
    entry = 'gui'
    platform = 'windows'
    arch = 'amd64'
    version = $Version
    manifest = 'v2'
    sourceCommit = $Commit
    sourceFingerprint = $sourceFingerprint
    upstream = [ordered]@{
        mode = $mode
        version = [string]$meta.releaseVersion
        buildCommit = [string]$lock.piwork.commit
        releaseCommit = $releaseCommit
    }
    inputFingerprint = $fingerprint
    body = [ordered]@{ path = $bodyPath; size = $size; sha256 = $hash }
}
$recordDir = Join-Path $dist 'build-bodies'
New-Item -ItemType Directory -Force -Path $recordDir | Out-Null
$record | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $recordDir 'gui-windows.json')
Write-Output "windows GUI body: $Output bytes=$size sha256=$hash fingerprint=$fingerprint source=$sourceFingerprint"
