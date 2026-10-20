# Native fault injection against an explicitly owned final-PE installation.
param(
 [Parameter(Mandatory=$true)][string]$Root,
 [Parameter(Mandatory=$true)][ValidateSet('early-exit','shutdown-timeout','launcher-kill')][string]$Mode
)
$ErrorActionPreference='Stop'
$owned=Get-Content (Join-Path $Root '.acceptance-owned.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if(-not $owned.owned){throw 'Not an owned acceptance installation'}
$installation=Join-Path $Root '安装 数据'
$runtime=Get-Content (Join-Path $installation 'runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$launch=Get-Content (Join-Path $Root 'launcher.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($runtime.data -ne $installation){throw 'Unexpected data directory'}
$controller=Join-Path $Root 'acceptance-windows.exe'
$parent=Get-Process -Id $launch.pid
$qemu=Get-Process -Id $runtime.pid
$null=$parent.Handle;$null=$qemu.Handle
$line=(Get-CimInstance Win32_Process -Filter ('ProcessId='+$runtime.pid)).CommandLine
if(-not $line.Contains($installation)){throw 'Unexpected QEMU writer'}
$metadata=Join-Path $installation 'installation.json'
$metadataHash=(Get-FileHash $metadata -Algorithm SHA256).Hash
$before=@(& $controller locks $installation)
if($LASTEXITCODE -ne 0 -or @($before | Where-Object {$_ -like '*: locked'}).Count -ne 3){throw 'Writer locks absent'}
$watch=[Diagnostics.Stopwatch]::StartNew()
if($Mode -eq 'early-exit'){$diagnostic=@(& $controller kill $runtime.pid)}
elseif($Mode -eq 'shutdown-timeout'){
 & $controller suspend $runtime.pid
 if($LASTEXITCODE -ne 0){throw 'Owned QEMU suspension failed'}
 $diagnostic=@(& $controller stop $launch.pid)
}else{$diagnostic=@(& $controller kill $launch.pid)}
if($LASTEXITCODE -ne 0){throw 'Native fault controller failed'}
if(-not $parent.WaitForExit(150000)){throw 'Launcher did not exit'}
if(-not $qemu.WaitForExit(15000)){throw 'Original QEMU writer survived'}
$watch.Stop()
if(-not (Test-Path (Join-Path $installation 'unclean.json'))){throw 'Missing abnormal shutdown marker'}
if((Get-FileHash $metadata -Algorithm SHA256).Hash -ne $metadataHash){throw 'Installation identity changed'}
if(-not (Test-Path $runtime.disk)){throw 'Original disk missing'}
$after=@(& $controller locks $installation)
if(@($after | Where-Object {$_ -like '*: available'}).Count -ne 3){throw 'Locks not released after all writers exited'}
if($Mode -eq 'shutdown-timeout' -and ($watch.Elapsed.TotalSeconds -lt 118 -or $watch.Elapsed.TotalSeconds -gt 145)){throw 'Real shutdown budget was not exercised'}
$record=[ordered]@{
 mode=$Mode;nativeWindows=$true;finalPE=$true
 binarySHA256=(Get-FileHash (Join-Path $Root 'piwork-microvm.exe') -Algorithm SHA256).Hash.ToLower()
 launcherExitCode=$parent.ExitCode;qemuExitCode=$qemu.ExitCode
 elapsedSeconds=[math]::Round($watch.Elapsed.TotalSeconds,3)
 writerLocksBefore=$before;writerLocksAfter=$after
 uncleanMarkerRetained=$true;installationMetadataUnchanged=$true;diskRetained=$true
 allOriginalWritersExited=$true;controllerDiagnostic=$diagnostic
}
$json=$record | ConvertTo-Json -Depth 5
$json | Set-Content -Encoding UTF8 (Join-Path $Root ('evidence\fault-'+$Mode+'.json'))
Write-Output $json
