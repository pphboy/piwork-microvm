#!/usr/bin/env python3
"""Kill only the owned launcher; prove its orphan QEMU retains real disk locks."""
import argparse,fcntl,importlib.util,json,os,pathlib,signal,subprocess,time
root=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('guestctl',root/'scripts/guestctl.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
p=argparse.ArgumentParser();p.add_argument('--runtime',type=pathlib.Path,required=True);a=p.parse_args();info=json.loads(a.runtime.read_text())
out=pathlib.Path(os.environ['PIWORK_ACCEPTANCE_OUT']);qemu=info['pid']
status=pathlib.Path('/proc/'+str(qemu)+'/status').read_text();parent=int(next(l.split()[1] for l in status.splitlines() if l.startswith('PPid:')))
assert 'piwork-microvm' in pathlib.Path('/proc/'+str(parent)+'/cmdline').read_bytes().decode()
os.kill(parent,signal.SIGKILL)
time.sleep(.3)
os.kill(qemu,0)
alias=pathlib.Path(info['disk']).with_name('acceptance-alias.qcow2');os.link(info['disk'],alias)
try:
 for path in [pathlib.Path(info['data'])/'.lock',pathlib.Path(info['disk']),alias]:
  with path.open('r+b') as f:
   try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:continue
   raise AssertionError('Inherited QEMU writer protection was released: '+str(path))
 for unit in ['piwork.service','docker.service']:g.execute(info,['/bin/systemctl','stop',unit])
 g.execute(info,['/bin/sh','-c','sync && umount /var/lib/piwork/core && umount /var/lib/containerd && umount /mnt/state'])
 try:g.rpc(info['qmp'],'quit',qmp=True)
 except (BrokenPipeError,ValueError):pass
 for _ in range(100):
  if not pathlib.Path('/proc/'+str(qemu)).exists():break
  time.sleep(.1)
 for path in [pathlib.Path(info['data'])/'.lock',alias]:
  with path.open('r+b') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert (pathlib.Path(info['data'])/'unclean.json').exists(),'parent death must retain unconfirmed marker'
 (out/'orphan-result.json').write_text(json.dumps({'parentKilled':True,'qemuRetainedInstallationAndDiskAliasLocks':True,'supplementaryGuestSyncUnmount':True,'uncleanMarkerPreserved':True},indent=2)+'\n')
finally:alias.unlink(missing_ok=True)
print('PASS orphan QEMU inherited installation/disk/hard-link locks; released only after QEMU exit; abnormal marker retained')
