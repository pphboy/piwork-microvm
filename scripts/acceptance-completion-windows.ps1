# Native orchestration for the final real-model/recovery acceptance.
param(
 [Parameter(Mandatory=$true)][string]$Root,
 [Parameter(Mandatory=$true)][string]$Tools,
 [Parameter(Mandatory=$true)][ValidateSet('first','restart','check','inspect')][string]$Phase,
 [string]$Label=$Phase,
 [int]$Port=19180,[int]$CorePort=19181
)
$ErrorActionPreference='Stop'
Set-Location $Root
if($Label -notmatch '^[a-z0-9-]+$'){throw 'Invalid label'}
if(-not (Get-Content (Join-Path $Root '.acceptance-owned.json') -Raw -Encoding UTF8 | ConvertFrom-Json).owned){throw 'Not an owned test root'}
$env:PIWORK_ACCEPTANCE_OUT=Join-Path $Root 'evidence'
$env:PIWORK_ACCEPTANCE_PORT=[string]$Port;$env:PIWORK_ACCEPTANCE_CORE_PORT=[string]$CorePort
$env:PIWORK_ACCEPTANCE_PHASE=$Label;$env:PIWORK_ACCEPTANCE_PLATFORM='native Windows Home WHPX'
$env:PIWORK_REAL_MODEL_FILE=Join-Path $Root 'model.private.json'
$env:PIWORK_PLAYWRIGHT_MODULE=Join-Path $Tools 'node_modules\playwright\index.mjs'
$env:PIWORK_BROWSER_PATH='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$node=Join-Path $Tools 'node.exe'
function Run-Step([string]$Name,[string]$Argument=''){
 $argsList=@((Join-Path $Root ('scripts\'+$Name)))
 if($Argument){$argsList+=$Argument}
 & $node @argsList
 if($LASTEXITCODE -ne 0){throw ('Acceptance failed: '+$Name+' '+$Argument)}
}
$installation=Join-Path $Root '安装 数据'
if($Phase -eq 'inspect'){
 if(Test-Path (Join-Path $installation 'runtime.json')){throw 'Stop final PE before supplementary inspection'}
 $proof=Get-Content (Join-Path $Root 'evidence\native-process-proof.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 $work=(Get-Content (Join-Path $Root 'evidence\browser-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json).workId
 $inspection=Join-Path $Root ('evidence\inspection-'+$Label)
 $config=@{Installation=$installation;Assets=(Join-Path (Split-Path (Split-Path $proof.qemuPath)) 'guest');QEMU=$proof.qemuPath;Out=$inspection;WorkID=$work;Port=$Port;CorePort=$CorePort;InspectionSource=(Join-Path $Root 'fixtures\inspect.py');SkipNetwork=$true}
 $configPath=Join-Path $Root 'inspection-config.json'
 $config | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $configPath
 # Go JSON decoder expects UTF-8 without BOM.
 [IO.File]::WriteAllText($configPath,($config | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
 $output=@(& (Join-Path $Root 'acceptance-guest-windows.exe') $configPath)
 if($LASTEXITCODE -ne 0 -or -not ($output -contains 'Supplementary Guest ext4 unmount confirmed: true')){throw 'Supplementary inspection did not stop cleanly'}
 $report=Get-Content (Join-Path $inspection 'guest-runtime-inspection.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 if(@($report.volumes).Count -ne 2 -or @($report.databases).Count -lt 4){throw 'Missing persistent volumes/databases'}
 foreach($db in $report.databases){if($db.integrity -ne 'ok' -or $db.backing.fstype -ne 'ext4'){throw 'Database integrity/backing failed'}}
 $counter=(Get-Content (Join-Path $Root 'evidence\browser-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json).counterAfter.value
 if(($report.databases | Where-Object {$_.path.EndsWith('/microvm.sqlite')}).counter -ne $counter){throw 'Service counter changed'}
 $baseline=Join-Path $Root 'evidence\inspection-before-restart\guest-runtime-inspection.json'
 if(Test-Path $baseline){
  $previous=Get-Content $baseline -Raw -Encoding UTF8 | ConvertFrom-Json
  if((@($previous.volumes.Name | Sort-Object) -join ',') -ne (@($report.volumes.Name | Sort-Object) -join ',')){throw 'Volume identities changed'}
 }
 $output | Set-Content -Encoding UTF8 (Join-Path $inspection 'controller.log')
 Write-Output ('PASS native Guest inspection '+$Label+': all databases integrity ok on ext4; original volumes and Service counter retained')
 exit 0
}
$runtime=Get-Content (Join-Path $installation 'runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$qemu=Get-Process -Id $runtime.pid
$process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$runtime.pid)
$proof=@{qemuPath=$qemu.Path;pid=$runtime.pid;commandLine=$process.CommandLine;modules=@($qemu.Modules | ForEach-Object {$_.FileName});binarySHA256=(Get-FileHash (Join-Path $Root 'piwork-microvm.exe') -Algorithm SHA256).Hash.ToLower();nativeWindows=$true;version=[Environment]::OSVersion.Version.ToString();data=$runtime.data}
if(-not $process.CommandLine.Contains('-accel whpx') -or -not $process.CommandLine.Contains('-M microvm')){throw 'Wrong QEMU backend'}
$proof | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Root 'evidence\native-process-proof.json')
if($Phase -eq 'first'){
 Run-Step 'acceptance-browser.mjs'
 Run-Step 'acceptance-storage.mjs'
 Run-Step 'acceptance-real-model.mjs' 'first'
 Run-Step 'acceptance-real-history-browser.mjs'
 Run-Step 'acceptance-baseline.mjs'
}else{
 Run-Step 'acceptance-baseline.mjs' '--verify'
 Run-Step 'acceptance-real-model.mjs' $Phase
 Run-Step 'acceptance-real-history-browser.mjs'
 Run-Step 'acceptance-recovery-browser.mjs'
}
