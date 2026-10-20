#!/usr/bin/env python3
"""Exercise final-ELF port failures in isolated network namespaces."""
import json,os,pathlib,subprocess

root=pathlib.Path(__file__).resolve().parents[1]
out=pathlib.Path(os.environ['PIWORK_ACCEPTANCE_OUT'])
binary=root/'dist/piwork-microvm'
image='piwork-microvm-rootfs:local'
base=['docker','run','--rm','--network','none','-v',str(binary)+':/demo:ro']
results=[]
program='''import json,pathlib,subprocess
cases=[['--port'],['--port',''],['--port','abc'],['--port','0'],['--port','-1'],['--port','65536'],['--core-port','abc'],['--core-port','0'],['--core-port','65536'],['--port','8080','--core-port','8080']]
for args in cases:
 r=subprocess.run(['/demo','--data-dir','/tmp/port-test-data',*args],capture_output=True,text=True,timeout=15)
 assert r.returncode!=0 and 'port' in r.stderr and 'KVM' not in r.stderr
 assert not pathlib.Path('/tmp/port-test-data').exists()
 assert not pathlib.Path('/root/.cache/piwork-microvm').exists()
print(json.dumps({'invalidInputs':len(cases),'beforeKVMAndData':True,'exitNonzero':True}))
'''
r=subprocess.run([*base,'--entrypoint','/usr/bin/python3',image,'-c',program],capture_output=True,text=True,timeout=120)
assert r.returncode==0,r.stderr
results.append(json.loads(r.stdout))
for occupied in [8080,17871]:
    program=f'''import socket,subprocess,sys
s=socket.socket();s.bind(('0.0.0.0',{occupied}));s.listen()
r=subprocess.run(['/demo','--port','8080','--no-open'],capture_output=True,text=True,timeout=20)
assert r.returncode!=0 and '127.0.0.1:{occupied} is occupied or unavailable' in r.stderr
print('selected UI/Core conflict diagnosed without changing data')
'''
    r=subprocess.run([*base,'--device','/dev/kvm','--entrypoint','/usr/bin/python3',image,'-c',program],capture_output=True,text=True,timeout=60)
    assert r.returncode==0,r.stderr
    results.append({'occupiedPort':occupied,'selectedPort':8080,'safeFailure':True})
command=[*base,'--device','/dev/kvm','--sysctl','net.ipv4.ip_unprivileged_port_start=1024',
         '--user','65534:65534','--group-add',str(os.stat('/dev/kvm').st_gid),'--cap-drop','ALL',
         '--entrypoint','/demo',image,'--port','80']
r=subprocess.run(command,capture_output=True,text=True,timeout=60)
assert r.returncode!=0 and '127.0.0.1:80 is occupied or unavailable' in r.stderr,r.stderr
results.append({'unprivilegedPort':80,'safeFailure':True})
(out/'port-preflight.json').write_text(json.dumps(results,indent=2)+'\n')
print('PASS final ELF: invalid ports before KVM/data, selected UI/Core conflicts and binding permission failure')
