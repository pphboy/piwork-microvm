#!/usr/bin/env python3
import argparse,hashlib,importlib.util,json,os,pathlib,sys
root=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('guestctl',root/'scripts/guestctl.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
p=argparse.ArgumentParser();p.add_argument('--runtime',type=pathlib.Path,required=True);p.add_argument('--recovery-only',action='store_true');a=p.parse_args()
info=json.loads(a.runtime.read_text());out=pathlib.Path(os.environ.get('PIWORK_ACCEPTANCE_OUT',root/'dist/acceptance'));work=json.loads((out/'browser-result.json').read_text())['workId']
result=json.loads(g.execute(info,['/usr/bin/python3','-c',(root/'fixtures/inspect.py').read_text(),work]))
assert result['docker']['version']=='28.5.2' and result['docker']['driver']=='overlay2'
assert result['containerd']['root']=='/mnt/state/docker/containerd/daemon' and result['containerd']['rootBacking']['fstype']=='ext4'
assert len(result['volumes'])==2 and all(v['Driver']=='local' for v in result['volumes'])
assert all(d['integrity']=='ok' and d['backing']['fstype']=='ext4' for d in result['databases'])
memory=next(d for d in result['databases'] if d['path'].endswith('/memory.sqlite'))
# The deterministic fixture explicitly commits Memory; a real file-tool prompt
# need not do so. Both paths still require the actual persistent Memory database.
if not os.environ.get('PIWORK_REAL_MODEL_FILE'):assert memory['head']>=1
assert next(d for d in result['databases'] if d['path'].endswith('/work.sqlite'))['sessions']>=1
assert all(not c['ports'] for c in result['containers'])
expected=json.loads((out/'browser-result.json').read_text())['counterAfter']['value']
assert next(d for d in result['databases'] if d['path'].endswith('/microvm.sqlite'))['counter']==expected,'Service SQLite counter persists exactly'
inspection=out/'guest-runtime-inspection.json'
if inspection.exists():
    before=json.loads(inspection.read_text())
    assert sorted(v['Name'] for v in before['volumes'])==sorted(v['Name'] for v in result['volumes']),'original named volume identities persist'
(out/'guest-runtime-inspection.json').write_text(json.dumps(result,indent=2)+'\n')
kvm=g.rpc(info['qmp'],'query-kvm',qmp=True);machine=g.rpc(info['qmp'],'qom-get',{'path':'/machine','property':'type'},qmp=True);pci=g.rpc(info['qmp'],'query-pci',qmp=True)
assert kvm['enabled'] and kvm['present'] and machine=='microvm-machine' and pci==[]
libraries=sorted(set(line.split()[-1] for line in pathlib.Path('/proc/'+str(info['pid'])+'/maps').read_text().splitlines() if '.so' in line and line.split()[-1].startswith('/')))
assert libraries and all('/piwork-microvm/bundles/' in lib and '/qemu/' in lib for lib in libraries),'QEMU must use its bundled runtime libraries'
with (root/'dist/piwork-microvm').open('rb') as f:elf_hash=hashlib.file_digest(f,'sha256').hexdigest()
inodes=set()
for fd in pathlib.Path('/proc/'+str(info['pid'])+'/fd').iterdir():
    try:target=fd.readlink().as_posix()
    except FileNotFoundError:continue
    if target.startswith('socket:['):inodes.add(target[8:-1])
listeners=[]
for line in pathlib.Path('/proc/'+str(info['pid'])+'/net/tcp').read_text().splitlines()[1:]:
    fields=line.split()
    if fields[3]=='0A' and fields[9] in inodes:
        addr,port=fields[1].split(':');listeners.append({'addressHex':addr,'port':int(port,16)})
port=int(os.environ.get('PIWORK_ACCEPTANCE_PORT',17891));core_port=int(os.environ.get('PIWORK_ACCEPTANCE_CORE_PORT',17871))
assert sorted(x['port'] for x in listeners)==sorted([port,core_port]) and all(x['addressHex']=='0100007F' for x in listeners),'exactly two UI/Core loopback forwarding listeners'
(out/'qemu-proof.json').write_text(json.dumps({'binarySHA256':elf_hash,'kvm':kvm,'machine':machine,'pci':pci,'libraries':libraries,'listeners':listeners},indent=2)+'\n')
clean=pathlib.Path(os.environ.get('PIWORK_CLEAN_ROOT',root/'dist/clean-host/root'))
with (root/'dist/piwork-microvm').open('rb') as f:f.seek(-32,2);cache_key=f.read(32).hex()
argv=pathlib.Path('/proc/'+str(info['pid'])+'/cmdline').read_bytes().decode().split('\0')
qemu_path=next(pathlib.Path(arg) for arg in argv if arg.endswith('/qemu/qemu-system-x86_64'))
cache=qemu_path.parent.parent
if not cache.exists():cache=clean/cache.as_posix().lstrip('/')
file=cache/'guest/rootfs.ext4';kernel=cache/'guest/kernel'
cache_record={'pid':info['pid'],'rootInode':file.stat().st_ino,'rootMtimeNS':file.stat().st_mtime_ns,'kernelSHA256':hashlib.sha256(kernel.read_bytes()).hexdigest()}
records=json.loads((out/'cache-runs.json').read_text()) if (out/'cache-runs.json').exists() else []
if not records or records[-1]['pid']!=info['pid']:records.append(cache_record)
(out/'cache-runs.json').write_text(json.dumps(records,indent=2)+'\n')
if a.recovery_only:
 print('PASS original ext4 volumes and Core/Work/Memory/Service database integrity and counter after fault recovery')
 raise SystemExit(0)
network=(root/'fixtures/network.py').read_text()
net=json.loads(g.execute(info,['/usr/bin/python3','-c',network]))
(out/'guest-network.json').write_text(json.dumps(net,indent=2)+'\n')
assert net['dns'] and net['https']==200 and net['unauthenticatedAIAPI']==401,net
probe=json.loads(g.execute(info,['/usr/bin/python3','-c',(root/'fixtures/storage-probe.py').read_text(),'/mnt/state/.acceptance-storage-probe']))
assert probe[0]['WAL']['passed'] and probe[0]['DELETE']['passed']
(out/'filesystem-probe.json').write_text(json.dumps(probe,indent=2)+'\n')
secrets=[json.loads((out/'credentials.json').read_text())['password'].encode(),b'microvm-acceptance-synthetic-not-a-real-key',b'synthetic-fixture-only-not-provider-key',b'#setup=']
if os.environ.get('PIWORK_REAL_MODEL_FILE'):secrets.append(json.loads(pathlib.Path(os.environ['PIWORK_REAL_MODEL_FILE']).read_text())['credential'].encode())
journal=g.execute(info,['/bin/journalctl','--no-pager','-u','piwork.service','-u','piwork-images.service','-u','docker.service'])
records[-1]['imageLoadInJournal']=b'piwork boot: loading-images' in journal or b'Loaded image:' in journal
(out/'cache-runs.json').write_text(json.dumps(records,indent=2)+'\n')
logs=[journal]
for cid in g.execute(info,['/usr/local/bin/docker','ps','-a','--filter','label=piwork.work_id='+work,'--format','{{.ID}}']).decode().splitlines():
    logs.append(g.execute(info,['/bin/sh','-c','exec /usr/local/bin/docker logs --tail 500 "$1" 2>&1','--',cid]))
clean_disk=pathlib.Path(info['disk']);logdir=clean_disk.parent.parent/'logs'
logs.extend(p.read_bytes() for p in logdir.glob('*.log'))
assert all(secret not in blob for blob in logs for secret in secrets),'a supplied synthetic secret reached diagnostic logs'
(out/'secret-scan.json').write_text(json.dumps({'logStreamsChecked':len(logs),'passwordOrSyntheticKeyLeaks':False,'realProviderKeyChecked':bool(os.environ.get('PIWORK_REAL_MODEL_FILE')),'setupProofInLogs':False},indent=2)+'\n')
print('PASS two original local volumes, all real Core/Work/Memory/Service databases on ext4 with integrity ok, Memory and Session durable, no Docker published Service ports')
print('PASS SQLite WAL/DELETE lock, transaction and sync probes on persistent ext4; no shared filesystem')
