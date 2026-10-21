#!/usr/bin/env python3
"""Inspect the real VM and its port selection without printing credentials."""
import argparse,hashlib,json,os,pathlib,subprocess
import guestctl as g

root=pathlib.Path(__file__).resolve().parents[1]
out=pathlib.Path(os.environ['PIWORK_ACCEPTANCE_OUT'])
clean=pathlib.Path(os.environ['PIWORK_CLEAN_ROOT'])
core_port=int(os.environ.get('PIWORK_ACCEPTANCE_CORE_PORT',17871));port=int(os.environ['PIWORK_ACCEPTANCE_PORT']);origin='http://127.0.0.1'+('' if port==80 else f':{port}')
p=argparse.ArgumentParser();p.add_argument('--runtime',type=pathlib.Path,required=True);a=p.parse_args()
info=json.loads(a.runtime.read_text());pid=info['pid']
browser=json.loads((out/'browser-result.json').read_text())
if browser['origin']!=origin:
    recovered=json.loads((out/'recovery-browser-result.json').read_text());assert recovered['origin']==origin
kvm=g.rpc(info['qmp'],'query-kvm',qmp=True)
assert kvm['present'] and kvm['enabled']
assert g.rpc(info['qmp'],'qom-get',{'path':'/machine','property':'type'},qmp=True)=='microvm-machine'
assert g.rpc(info['qmp'],'query-pci',qmp=True)==[]
argv=pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
netdev=argv[argv.index('-netdev')+1];append=argv[argv.index('-append')+1]
assert f'hostfwd=tcp:127.0.0.1:{port}-:{port}' in netdev
assert netdev.count('hostfwd=tcp:')==2
assert f'hostfwd=tcp:127.0.0.1:{core_port}-:{core_port}' in netdev
assert f'piwork.host_port={port}' in append.split()
if port!=7171:assert 'hostfwd=tcp:127.0.0.1:7171-' not in netdev
inodes=set()
for fd in pathlib.Path(f'/proc/{pid}/fd').iterdir():
    try:target=fd.readlink().as_posix()
    except FileNotFoundError:continue
    if target.startswith('socket:['):inodes.add(target[8:-1])
listeners=[]
for line in pathlib.Path(f'/proc/{pid}/net/tcp').read_text().splitlines()[1:]:
    fields=line.split()
    if fields[3]=='0A' and fields[9] in inodes:
        addr,number=fields[1].split(':');listeners.append({'addressHex':addr,'port':int(number,16)})
assert sorted(x['port'] for x in listeners)==sorted([port,core_port])
assert all(x['addressHex']=='0100007F' for x in listeners)
libraries=sorted(set(line.split()[-1] for line in pathlib.Path(f'/proc/{pid}/maps').read_text().splitlines() if '.so' in line and line.split()[-1].startswith('/')))
assert libraries and all('/cache/piwork-microvm/bundles/' in lib and '/qemu/' in lib for lib in libraries)
program='''import json,pathlib
commands=[]
for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try:a=p.read_bytes().rstrip(b'\\0').decode().split('\\0')
 except (OSError,UnicodeError):continue
 if a and a[0]=='/usr/local/bin/piwork-core':commands.append(a)
print(json.dumps({'kernelCmdline':pathlib.Path('/proc/cmdline').read_text().strip(),'commands':commands}))
'''
guest=json.loads(g.execute(info,['/usr/bin/python3','-c',program]))
assert f'piwork.host_port={port}' in guest['kernelCmdline'].split()
assert len(guest['commands'])==1
command=guest['commands'][0]
assert command[command.index('--ui-port')+1]==str(port)
assert command[command.index('--core-port')+1]==str(core_port)
assert '--service-ports' not in command
assert '--public-origin' not in command
assert f'piwork.host_core_port={core_port}' in guest['kernelCmdline'].split()
inspection=json.loads(g.execute(info,['/usr/bin/python3','-c',(root/'fixtures/inspect.py').read_text(),browser['workId']]))
assert inspection['docker']['version']=='28.5.2' and inspection['docker']['driver']=='overlay2'
assert inspection['docker']['cgroupVersion']=='2'
assert inspection['containerd']['root']=='/mnt/state/docker/containerd/daemon'
assert inspection['containerd']['rootBacking']['fstype']=='ext4'
assert len(inspection['volumes'])==2 and all(v['Driver']=='local' for v in inspection['volumes'])
assert all(d['integrity']=='ok' and d['backing']['fstype']=='ext4' for d in inspection['databases'])
assert next(d['counter'] for d in inspection['databases'] if d['path'].endswith('/microvm.sqlite'))==browser['counterAfter']['value']
assert all(not c['ports'] for c in inspection['containers'])
if port!=8080:
    before=json.loads((out/'proof-8080.json').read_text())['inspection']
    assert sorted(v['Name'] for v in inspection['volumes'])==sorted(v['Name'] for v in before['volumes'])
logs=list((pathlib.Path(info['disk']).parent.parent/'logs').glob('*.log'))
latest=max(logs,key=lambda p:p.stat().st_mtime_ns).read_text(errors='replace')
assert 'Piwork is available: '+origin in latest and 'Piwork runtime is ready.' in latest
secrets=[json.loads((out/'credentials.json').read_text())['password'].encode(),b'microvm-acceptance-synthetic-not-a-real-key',b'#setup=']
journal=g.execute(info,['/bin/journalctl','--no-pager','-u','piwork.service','-u','docker.service'])
assert all(secret not in blob for blob in [journal,*[p.read_bytes() for p in logs]] for secret in secrets)
occupier=None
if port!=7171:
    occupier=subprocess.check_output(['docker','exec','piwork-microvm-clean','wget','-q','-O','-','http://127.0.0.1:7171/'],text=True).strip()
    assert occupier=='piwork-microvm controlled port-7171 listener'
# A second namespace has free ports; changing the entry port cannot bypass data locks.
image=json.loads((root/'build.lock.json').read_text())['dockerImage']
second=['docker','run','--rm','--network','none','--pid=host','--device','/dev/kvm:/clean/dev/kvm',
        '-e','PIWORK_TEST_UID='+str(os.getuid()),'-e','PIWORK_TEST_GID='+str(os.getgid()),
        '-e','PIWORK_TEST_KVM_GROUP='+str(os.stat('/dev/kvm').st_gid),'-v',str(clean)+':/clean',
        '-v','/proc:/clean/proc:ro','-v',str(root/'dist/acceptance-chroot')+':/acceptance-chroot:ro',
        '--entrypoint','/acceptance-chroot',image,'--data-dir','/state/Installation','--port','8082','--no-open']
blocked=subprocess.run(second,capture_output=True,text=True,timeout=90)
assert blocked.returncode!=0 and ('another instance owns' in blocked.stderr or 'already' in blocked.stderr or 'temporarily unavailable' in blocked.stderr)
with (root/'dist/piwork-microvm').open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
with (clean/'piwork-microvm').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest
if port!=8080:assert json.loads((out/'proof-8080.json').read_text())['binarySHA256']==digest
record={'binarySHA256':digest,'port':port,'origin':origin,'kvm':kvm,'machine':'microvm-machine','pci':[],
        'qemuArgv':argv,'listeners':listeners,'libraries':libraries,'guest':guest,'inspection':inspection,
        'controlled7171Listener':occupier,'differentPortSameDataLockRefused':True,
        'setupProofOrPasswordInLogs':False,'realProviderCall':'not verified; no supplied key'}
(out/f'proof-{port}.json').write_text(json.dumps(record,indent=2)+'\n')
print(f'PASS real KVM port {port}: two UI/Core loopback listeners, Guest origin/listener, ext4 data, private logs and unchanged data locks')
