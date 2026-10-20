#!/usr/bin/env python3
"""Fault injection against an explicitly owned final-ELF installation only."""
import argparse, importlib.util, json, os, pathlib, signal, subprocess, time
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('mode',choices=['early-exit','shutdown-timeout','launcher-kill']);a=p.parse_args()
root=a.root.resolve();assert json.loads((root/'.acceptance-owned.json').read_text())['owned']
installation=root/'installation';out=root/'evidence'
run=json.loads((installation/'runtime.json').read_text());launcher=json.loads((root/'launcher.json').read_text())
assert pathlib.Path(run['data']).resolve()==installation
assert str(installation).encode() in pathlib.Path(f'/proc/{launcher["pid"]}/cmdline').read_bytes()
s=importlib.util.spec_from_file_location('g',pathlib.Path(__file__).with_name('guestctl.py'));g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
g.execute(run,['/bin/sync'])
metadata=(installation/'installation.json').read_bytes()
def alive(pid):
 try:return pathlib.Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1][0]!='Z'
 except FileNotFoundError:return False
def until(fn,seconds):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if fn():return
  time.sleep(.2)
 raise AssertionError('Timed out waiting for owned test process')
record={'mode':a.mode,'qemuPID':run['pid'],'launcherPID':launcher['pid'],'finalELF':True}
start=time.monotonic()
if a.mode=='shutdown-timeout':
 os.kill(run['pid'],signal.SIGSTOP)
 os.kill(launcher['pid'],signal.SIGTERM)
elif a.mode=='early-exit':
 g.rpc(run['qmp'],'quit',qmp=True)
else:
 os.kill(launcher['pid'],signal.SIGKILL)
 until(lambda:not alive(launcher['pid']),10)
 assert alive(run['pid'])
 binary=pathlib.Path(__file__).resolve().parents[1]/'dist/piwork-microvm'
 second=subprocess.run([str(binary),'--data-dir',str(installation),'--port','18082','--core-port','18083','--no-open'],capture_output=True,text=True,timeout=45)
 assert second.returncode!=0 and 'another instance owns this installation or disk' in second.stderr.lower(),second.stderr
 record['orphanWriterRejectedSecondLauncher']=True
 record['secondLauncherDiagnostic']=second.stderr.strip()
 g.rpc(run['qmp'],'quit',qmp=True)
until(lambda:not alive(launcher['pid']) and not alive(run['pid']),145)
record['elapsedSeconds']=round(time.monotonic()-start,3)
assert (installation/'unclean.json').exists()
assert (installation/'installation.json').read_bytes()==metadata
assert pathlib.Path(run['disk']).stat().st_size>0
log=(out/f'boot-{launcher["label"]}.log').read_text(errors='replace')
if a.mode=='shutdown-timeout':
 assert 118<=record['elapsedSeconds']<=145
 assert 'shutdown timed out' in log and 'unclean shutdown' in log
if a.mode=='early-exit':assert 'Guest exited unexpectedly' in log
record.update(uncleanMarkerRetained=True,installationMetadataUnchanged=True,diskRetained=True,allOriginalWritersExited=True)
(out/f'fault-{a.mode}.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
