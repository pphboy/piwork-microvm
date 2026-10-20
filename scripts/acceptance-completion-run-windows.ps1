# Run only against a dedicated, explicitly marked acceptance installation.
param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$Tools)
$ErrorActionPreference='Stop'
Set-Location $Root
if(-not (Get-Content (Join-Path $Root '.acceptance-owned.json') -Raw -Encoding UTF8 | ConvertFrom-Json).owned){throw 'Not an owned test root'}
$installation=Join-Path $Root '安装 数据'
$controller=Join-Path $Root 'acceptance-windows.exe'
$runner=Join-Path $Root 'scripts\acceptance-completion-windows.ps1'
$script:currentLabel=''
function Start-Owned([string]$Label){
 $script:currentLabel=$Label
 $log=Join-Path $Root ('evidence\boot-'+$Label+'.log')
 $launched=@(& $controller start $log (Join-Path $Root 'piwork-microvm.exe') --data-dir $installation --port 19180 --core-port 19181 --no-open)
 if($LASTEXITCODE -ne 0){throw 'Native final PE launch failed'}
 $launched | Set-Content -Encoding UTF8 (Join-Path $Root 'launcher.json')
 $deadline=[DateTime]::UtcNow.AddMinutes(5)
 while([DateTime]::UtcNow -lt $deadline){
  try{$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:19180/healthz' -TimeoutSec 3;if($r.StatusCode -eq 200){Write-Output ('STARTED '+$Label);return}}catch{}
  $lp=(Get-Content (Join-Path $Root 'launcher.json') -Raw -Encoding UTF8 | ConvertFrom-Json).pid
  if(-not (Get-Process -Id $lp -ErrorAction SilentlyContinue)){throw ('Launcher exited: '+$log)}
  Start-Sleep -Milliseconds 500
 }
 throw 'Final PE readiness timeout'
}
function Stop-Owned([string]$Label){
 $lp=(Get-Content (Join-Path $Root 'launcher.json') -Raw -Encoding UTF8 | ConvertFrom-Json).pid
 $proc=Get-Process -Id $lp;$null=$proc.Handle
 & $controller stop $lp
 if($LASTEXITCODE -ne 0 -or -not $proc.WaitForExit(150000)){throw 'Normal stop failed'}
 $log=Get-Content (Join-Path $Root ('evidence\boot-'+$script:currentLabel+'.log')) -Raw -Encoding UTF8
 if($proc.ExitCode -ne 0 -or (Test-Path (Join-Path $installation 'unclean.json')) -or (Test-Path (Join-Path $installation 'runtime.json')) -or -not $log.Contains('Guest stopped cleanly')){throw 'Normal shutdown was not confirmed'}
 @{exitCode=$proc.ExitCode;clean=$true;diskRetained=(Test-Path (Join-Path $installation 'disks\state.qcow2'));label=$script:currentLabel} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Root ('evidence\normal-stop-'+$Label+'.json'))
 Write-Output ('STOPPED CLEANLY '+$script:currentLabel)
}
function Check([string]$Phase,[string]$Label){
 & $runner -Root $Root -Tools $Tools -Phase $Phase -Label $Label
 if($LASTEXITCODE -ne 0){throw ('Failed phase '+$Label)}
 if($Phase -eq 'check' -or $Phase -eq 'restart'){
  Copy-Item (Join-Path $Root 'evidence\persistence-result.json') (Join-Path $Root ('evidence\persistence-'+$Label+'.json'))
  Copy-Item (Join-Path $Root 'evidence\recovery-browser-result.json') (Join-Path $Root ('evidence\service-'+$Label+'.json'))
 }
}
Start-Owned 'first'
Check 'first' 'first'
Stop-Owned 'first'
Check 'inspect' 'before-restart'
Start-Owned 'restart'
Check 'restart' 'restart'
Stop-Owned 'restart'
Check 'inspect' 'normal-restart'
foreach($mode in @('early-exit','shutdown-timeout','launcher-kill')){
 Start-Owned ('before-'+$mode)
 Check 'check' ('before-'+$mode)
 & (Join-Path $Root 'scripts\acceptance-exits-windows.ps1') -Root $Root -Mode $mode
 if($LASTEXITCODE -ne 0){throw ('Fault injection failed '+$mode)}
 Start-Owned ('after-'+$mode)
 Check 'check' ('after-'+$mode)
 Stop-Owned 'final'
 Check 'inspect' ('after-'+$mode)
}
Write-Output 'PASS final native Windows real-model/restart and all three fault/recovery cases'
