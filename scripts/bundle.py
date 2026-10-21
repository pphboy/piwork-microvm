#!/usr/bin/env python3
"""Append a deterministic gzip/tar payload and checked index to the Go ELF."""
import argparse, gzip, hashlib, json, os, pathlib, shutil, struct, subprocess, tarfile
from source import source_path,verify
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def git(*args):
    """Run git read-only; return stripped stdout, or None when unavailable."""
    try:return subprocess.run(['git',*args],capture_output=True,text=True,check=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError):return None
def release_version():
    """Version of the annotated tag exactly at HEAD, or None when HEAD is untagged."""
    name=git('describe','--tags','--exact-match','HEAD')
    if not name or git('cat-file','-t',name)!='tag':return None
    return name[1:] if name.startswith('v') else name
def build_identity(out,manifest_version):
    """Own version, upstream pin and bundle manifest version reported by --version.

    PIWORK_RELEASE_VERSION lets a release build state its version before the tag
    exists, so the artifact never ships a development version under a release tag.
    """
    explicit=os.environ.get('PIWORK_RELEASE_VERSION','').strip()
    return {'version':explicit or release_version() or '0.0.0-dev.'+(git('rev-parse','--short=12','HEAD') or 'unknown'),
            'upstream':json.loads((out/'piwork/metadata.json').read_text())['releaseVersion'],
            'commit':json.loads((ROOT/'build.lock.json').read_text())['piwork']['commit'],
            'manifest':'v'+str(manifest_version)}
def version_ldflags(identity):
    prefix='piwork-microvm/internal/launcher.'
    fields=[('buildVersion',identity['version']),('buildUpstreamVersion',identity['upstream']),
            ('buildUpstreamCommit',identity['commit']),('buildManifestVersion',identity['manifest'])]
    return ' '.join('-X '+prefix+name+'='+value for name,value in fields)
def main():
    p=argparse.ArgumentParser();p.add_argument('--platform',choices=['linux','windows'],default='linux');a=p.parse_args()
    os.chdir(ROOT);out=ROOT/'dist';verify(source_path())
    suffix='.exe' if a.platform=='windows' else ''
    artifact_name='piwork-microvm'+suffix
    qemu_dir=out/('qemu-windows' if a.platform=='windows' else 'qemu')
    inputs={}
    for name in ['kernel','kernel.config','initramfs','rootfs.ext4','state.qcow2','qemu-data/qboot.rom','qemu-data/linuxboot.bin','qemu-data/linuxboot_dma.bin']:
        inputs['guest/'+name]=out/'guest'/name
    for p in qemu_dir.rglob('*'):
        if p.is_file():inputs['qemu/'+p.relative_to(qemu_dir).as_posix()]=p
    provenance={'build.lock.json':ROOT/'build.lock.json','piwork-source.json':source_path().parent/'source.json',
                'piwork-metadata.json':out/'piwork/metadata.json','piwork-images.json':out/'piwork/images.json',
                'piwork.LICENSE':source_path()/'LICENSE','kernel.COPYING':out/'kernel/pristine'/('linux-'+json.loads((ROOT/'build.lock.json').read_text())['linux']['version'])/'COPYING',
                'kernel.GPL-2.0':out/'kernel/pristine'/('linux-'+json.loads((ROOT/'build.lock.json').read_text())['linux']['version'])/'LICENSES/preferred/GPL-2.0',
                'guest-firmware.json':out/'guest/firmware.json'}
    if a.platform=='windows':
        for p in sorted((ROOT/'guest/qemu').glob('*.patch')):provenance['qemu-'+p.name]=p
        provenance['windows-toolchain.lock.json']=ROOT/'guest/qemu/windows-toolchain.lock.json'
    for name,p in provenance.items():inputs['provenance/'+name]=p
    guest_licenses=out/'guest/guest-licenses'
    if not guest_licenses.is_dir():raise SystemExit('missing guest license tree; run make guest first')
    for p in guest_licenses.rglob('*'):
        if p.is_file():inputs['provenance/guest-licenses/'+p.relative_to(guest_licenses).as_posix()]=p
    goroot=pathlib.Path(subprocess.check_output(['go','env','GOROOT'],text=True).strip())
    inputs['provenance/licenses/Go-LICENSE']=goroot/'LICENSE'
    modules=json.loads(subprocess.check_output(['go','list','-m','-json','golang.org/x/sys'],text=True))
    inputs['provenance/licenses/x-sys-LICENSE']=pathlib.Path(modules['Dir'])/'LICENSE'
    if a.platform=='windows':
        modules=json.loads(subprocess.check_output(['go','list','-m','-json','github.com/Microsoft/go-winio'],text=True))
        inputs['provenance/licenses/go-winio-LICENSE']=pathlib.Path(modules['Dir'])/'LICENSE'
    payload=out/('payload-'+a.platform+'.tar.gz');records=[]
    print('Compressing immutable Guest/QEMU resources...',flush=True)
    with payload.open('wb') as f,gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0,compresslevel=3) as g,tarfile.open(fileobj=g,mode='w|',format=tarfile.PAX_FORMAT) as tar:
        for name,p in sorted(inputs.items()):
            executable=a.platform=='linux' and name in ['qemu/qemu-system-x86_64','qemu/ld-linux-x86-64.so.2']
            mode=0o555 if executable else 0o444
            record={'path':name,'size':p.stat().st_size,'mode':mode,'sha256':sha(p)};records.append(record)
            info=tarfile.TarInfo(name);info.size=record['size'];info.mode=mode;info.mtime=0;info.uid=info.gid=0
            with p.open('rb') as source:tar.addfile(info,source)
    manifest={'version':2,'os':a.platform,'arch':'amd64','payloadSha256':sha(payload),'files':records}
    raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    (out/('bundle-manifest-'+a.platform+'.json')).write_bytes(raw+b'\n')
    env=os.environ.copy();env.update(CGO_ENABLED='0',GOTOOLCHAIN='local',GOOS=a.platform,GOARCH='amd64')
    launcher=out/('launcher-'+a.platform+suffix)
    identity=build_identity(out,manifest['version'])
    subprocess.run(['go','build','-trimpath','-ldflags=-s -w '+version_ldflags(identity),'-o',launcher,'./cmd/piwork-microvm'],check=True,env=env)
    artifact=out/(artifact_name+'.part')
    with artifact.open('wb') as f:
        for p in [launcher,payload]:
            with p.open('rb') as source:shutil.copyfileobj(source,f,1024*1024)
        f.write(raw);f.write(b'PIWORK-BUNDLE-v1');f.write(struct.pack('<QQ',payload.stat().st_size,len(raw)));f.write(hashlib.sha256(raw).digest());f.flush();os.fsync(f.fileno())
    artifact.chmod(0o755);os.replace(artifact,out/artifact_name)
    digest=sha(out/artifact_name);(out/(artifact_name+'.sha256')).write_text(digest+'  '+artifact_name+'\n')
    print(a.platform+':',out/artifact_name,'bytes:',(out/artifact_name).stat().st_size,'SHA256:',digest,'version:',identity['version'])
if __name__=='__main__':main()
