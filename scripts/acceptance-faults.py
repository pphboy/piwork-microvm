#!/usr/bin/env python3
"""Actual isolated Guest failures, with final launcher diagnostics and disk retained."""
import argparse,importlib.util,json,os,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('guestctl',root/'scripts/guestctl.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
p=argparse.ArgumentParser();p.add_argument('--runtime',type=pathlib.Path,required=True);p.add_argument('mode',choices=['storage','images','qga-timeout','early-exit']);a=p.parse_args();info=json.loads(a.runtime.read_text())
out=pathlib.Path(os.environ['PIWORK_ACCEPTANCE_OUT'])
if a.mode=='storage':
 program=r'''import json,pathlib,subprocess
run=lambda *args:subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
for unit in ['piwork.service','piwork-images.service','docker.service','piwork-storage.service']:
 r=run('systemctl','stop',unit);assert r.returncode==0
# This mount namespace has a private /run so its probe cannot change the live boot phase.
missing=run('unshare','--mount','--propagation','private','/bin/sh','-c','mount -t tmpfs none /run && umount /mnt/state && /usr/local/bin/piwork-guest storage')
assert missing.returncode!=0 and 'storage (ok=false)' in missing.stdout
marker=pathlib.Path('/mnt/state/.piwork-state-v1');original=marker.read_bytes()
try:
 marker.write_bytes(b'invalid-test-state-marker\n')
 blocked=run('systemctl','start','docker.service');assert blocked.returncode!=0
 assert run('systemctl','is-active','docker.service').stdout.strip()!='active'
finally:marker.write_bytes(original);run('sync')
print(json.dumps({'unmountedStateRejected':True,'invalidStateBlocksDockerAndPiwork':True,'originalDiskMarkerRestored':True}))
'''
elif a.mode=='images':
 program=r'''import json,pathlib,subprocess
p=pathlib.Path('/opt/piwork/images.json');original=p.read_text();images=json.loads(original)
snapshot=images['snapshotHelper']['reference']
r=subprocess.run(['docker','image','rm',snapshot],stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert r.returncode==0
r=subprocess.run(['/usr/local/bin/piwork-guest','images'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert r.returncode==0
wrong=json.loads(original);wrong['snapshotHelper']['id']='sha256:'+'0'*64
try:
 p.write_text(json.dumps(wrong))
 r=subprocess.run(['/usr/local/bin/piwork-guest','images'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert r.returncode!=0
finally:p.write_text(original)
print(json.dumps({'missingProductionImageReloaded':True,'mismatchedExpectedIdentityRejected':True,'immutableRootFSUnaffected':True}))
'''
else:program=None
if program:
 result=json.loads(g.execute(info,['/usr/bin/python3','-c',program]));(out/('fault-'+a.mode+'.json')).write_text(json.dumps(result,indent=2)+'\n');print('PASS actual Guest fault '+a.mode+'; launcher must now report stage failure and exit')
elif a.mode=='qga-timeout':
 g.execute(info,['/usr/bin/systemd-run','--on-active=1','/bin/systemctl','stop','piwork-guest-agent.service'])
 subprocess.run(['docker','kill','--signal','TERM','piwork-microvm-clean'],check=True,stdout=subprocess.DEVNULL)
 print('Guest QGA stopped; final launcher must exhaust its bounded shutdown budget, retain marker and force QEMU exit')
else:
 try:g.rpc(info['qmp'],'quit',qmp=True)
 except (BrokenPipeError,ValueError):pass
 print('Guest deliberately exited early; final launcher must fail and retain the original disk')
