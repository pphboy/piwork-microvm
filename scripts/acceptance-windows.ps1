# Native test entry point. Copy the repository scripts/fixtures, dist metadata,
# test helpers, final PE and native Node/Playwright into a Windows-local test tree.
# Product launch itself never requires these test tools.
param(
 [Parameter(Mandatory=$true)][string]$Root,
 [int]$Port=8080,
 [int]$CorePort=17871,
 [ValidateSet('first','recovery','failures')][string]$Phase='first',
 [string]$Browser='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
)
$ErrorActionPreference='Stop'
$env:PIWORK_ACCEPTANCE_OUT=Join-Path $Root 'evidence'
$env:PIWORK_ACCEPTANCE_PORT=[string]$Port
$env:PIWORK_ACCEPTANCE_CORE_PORT=[string]$CorePort
$env:PIWORK_ACCEPTANCE_PLATFORM='native Windows WHPX Guest'
$env:PIWORK_BROWSER_PATH=$Browser
$env:PIWORK_PLAYWRIGHT_MODULE=Join-Path $Root 'tools\node_modules\playwright\index.mjs'
$env:PIWORK_WINDOWS_ACCEPTANCE_ROOT=$Root
$node=Join-Path $Root 'tools\node.exe'
$steps=@()
if($Phase -eq 'first'){$steps=@('acceptance-browser.mjs','acceptance-storage.mjs','acceptance-grants.mjs','acceptance-grants-browser.mjs')}
if($Phase -eq 'recovery'){$steps=@('acceptance-baseline.mjs','acceptance-recovery-browser.mjs')}
if($Phase -eq 'failures'){$steps=@('acceptance-windows-failures.mjs')}
foreach($step in $steps){
 $arguments=@((Join-Path $Root ('scripts\'+$step)))
 if($Phase -eq 'recovery' -and $step -eq 'acceptance-baseline.mjs'){$arguments+='--verify'}
 & $node @arguments
 if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
}
