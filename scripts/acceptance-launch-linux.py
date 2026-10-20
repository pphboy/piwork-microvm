#!/usr/bin/env python3
"""Supervise the final ELF for acceptance and record its actual exit status."""
import argparse, hashlib, json, pathlib, subprocess, time
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--label',required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--core-port',type=int,required=True);a=p.parse_args()
root=a.root.resolve();assert json.loads((root/'.acceptance-owned.json').read_text())['owned']
assert a.label.replace('-','').isalnum()
binary=pathlib.Path(__file__).resolve().parents[1]/'dist/piwork-microvm'
out=root/'evidence';out.mkdir(exist_ok=True)
args=[str(binary),'--data-dir',str(root/'installation'),'--port',str(a.port),'--core-port',str(a.core_port),'--no-open']
start=time.time()
with (out/f'boot-{a.label}.log').open('wb') as log:
 child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
 (root/'launcher.json').write_text(json.dumps({'pid':child.pid,'args':args,'label':a.label}))
 print('Owned Linux launcher PID',child.pid,flush=True)
 code=child.wait()
with binary.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
record={'exitCode':code,'elapsedSeconds':round(time.time()-start,3),'binarySHA256':digest,'label':a.label}
(out/f'exit-{a.label}.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
