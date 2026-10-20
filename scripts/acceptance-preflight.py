#!/usr/bin/env python3
"""Real final-ELF negative cases, restricted to the stopped test installation."""
import hashlib,json,os,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parents[1];lock=json.loads((root/'build.lock.json').read_text());binary=root/'dist/piwork-microvm'
clean=pathlib.Path(os.environ.get('PIWORK_CLEAN_ROOT',root/'dist/clean-host/root'));out=pathlib.Path(os.environ.get('PIWORK_ACCEPTANCE_OUT',root/'dist/acceptance'))
installation=clean/'state/Installation';assert not (installation/'runtime.json').exists(),'Stop acceptance VM first'
results=[]
def expect(name,command,text):
 r=subprocess.run([str(x) for x in command],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
 assert r.returncode!=0 and text in r.stdout,(name,r.stdout)
 results.append({'case':name,'exit':r.returncode,'message':r.stdout.strip()})
for name,extra in [('missing-kvm',[]),('kvm-permission',['--device','/dev/kvm','--user','65534:65534'])]:
 expect(name,['docker','run','--rm','--network','none','-v',str(binary)+':/demo:ro',*extra,lock['guestBaseImage'],'/demo'],'KVM unavailable or permission denied')
for port in [17891,17871]:
 program="import socket,subprocess,sys;s=socket.socket();s.bind(('127.0.0.1',"+str(port)+"));s.listen();r=subprocess.run(['/demo','--no-open'],capture_output=True,text=True,timeout=15);sys.stdout.write(r.stdout+r.stderr);sys.exit(r.returncode)"
 expect('occupied-port-'+str(port),['docker','run','--rm','--network','none','--device','/dev/kvm','-v',str(binary)+':/demo:ro','--entrypoint','/usr/bin/python3','piwork-microvm-rootfs:local','-c',program],'127.0.0.1:'+str(port)+' is occupied')
def command():
 return ['docker','run','--rm','--network','none','--pid=host','--device','/dev/kvm:/clean/dev/kvm','-e','PIWORK_TEST_UID='+str(os.getuid()),'-e','PIWORK_TEST_GID='+str(os.getgid()),'-e','PIWORK_TEST_KVM_GROUP='+str(os.stat('/dev/kvm').st_gid),'-v',str(clean)+':/clean','-v','/proc:/clean/proc:ro','-v',str(binary)+':/clean/piwork-microvm:ro','-v',str(root/'dist/acceptance-chroot')+':/acceptance-chroot:ro','--entrypoint','/acceptance-chroot',lock['dockerImage'],'--data-dir','/state/Installation','--no-open']
disk=installation/'disks/state.qcow2';saved=disk.with_suffix('.acceptance-saved');assert not saved.exists()
with disk.open('rb') as f:before=hashlib.file_digest(f,'sha256').hexdigest()
disk.rename(saved)
try:
 expect('existing-disk-missing',command(),'existing persistent disk is missing')
 disk.write_bytes(b'invalid disk; never overwrite');bad=disk.read_bytes()
 expect('existing-disk-corrupt',command(),'persistent qcow2 header/size is invalid');assert disk.read_bytes()==bad
finally:
 disk.unlink(missing_ok=True);saved.rename(disk)
with disk.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==before
(out/'preflight-failures.json').write_text(json.dumps(results,indent=2)+'\n')
print('PASS missing/inaccessible KVM, UI/Core port conflicts, missing/corrupt disk and exact original disk preservation')
