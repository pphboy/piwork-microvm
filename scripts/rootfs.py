#!/usr/bin/env python3
import hashlib, json, os, pathlib, subprocess, tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run(*args,**kw): subprocess.run([str(a) for a in args],check=True,**kw)
def main():
    os.chdir(ROOT)
    out=ROOT/'dist';(out/'guest').mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(CGO_ENABLED='0',GOOS='linux',GOARCH='amd64')
    run('go','build','-trimpath','-ldflags=-s -w','-o',out/'piwork-guest','./cmd/piwork-guest',env=env)
    run('docker','build','-f','guest/rootfs/Dockerfile','-t','piwork-microvm-rootfs:local','.')
    container=subprocess.check_output(['docker','create','piwork-microvm-rootfs:local'],text=True).strip()
    try:
        for f in ['piwork-core','piwork-cli']:
            run('docker','cp',out/'piwork/bin'/f,f'{container}:/usr/local/bin/{f}')
        run('docker','cp',out/'piwork-guest',f'{container}:/usr/local/bin/piwork-guest')
        run('docker','cp',out/'piwork/images.json',f'{container}:/opt/piwork/images.json')
        run('docker','cp',out/'guest/images.tar',f'{container}:/opt/piwork/images.tar')
        run('docker','export','-o',out/'rootfs.tar',container)
    finally: run('docker','rm',container)
    run('docker','run','--rm','-v',f'{ROOT}:/project','-w','/project',
        'piwork-microvm-rootfs:local','bash','scripts/rootfs-assemble.sh',str(os.getuid()),str(os.getgid()))
    run('python3','scripts/guest-licenses.py')
    run('qemu-img','convert','-f','raw','-O','qcow2',out/'guest/state.raw',out/'guest/state.qcow2')
    (out/'guest/state.raw').unlink()
    run('qemu-img','check',out/'guest/state.qcow2')
    (out/'guest/qemu-data').mkdir(exist_ok=True)
    lock=json.loads((ROOT/'build.lock.json').read_text())
    archive=out/'downloads'/('qemu-'+lock['qemu']['version']+'.tar.xz')
    if not archive.exists():
        run('curl','--fail','--location','--retry','3','-o',str(archive)+'.part',lock['qemu']['url'])
        os.rename(str(archive)+'.part',archive)
    with archive.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=lock['qemu']['sha256']:raise SystemExit('QEMU archive checksum mismatch')
    with tarfile.open(archive) as t:
        firmware=t.extractfile('qemu-'+lock['qemu']['version']+'/pc-bios/qboot.rom').read()
    if hashlib.sha256(firmware).hexdigest()!=lock['qboot']['sha256']:raise SystemExit('qboot checksum mismatch')
    (out/'guest/qemu-data/qboot.rom').write_bytes(firmware)
    firmware_records={'qboot.rom':hashlib.sha256(firmware).hexdigest()}
    with tarfile.open(archive) as t:
        for name in ['linuxboot.bin','linuxboot_dma.bin']:
            data=t.extractfile('qemu-'+lock['qemu']['version']+'/pc-bios/'+name).read()
            (out/'guest/qemu-data'/name).write_bytes(data)
            firmware_records[name]=hashlib.sha256(data).hexdigest()
    (out/'guest/firmware.json').write_text(json.dumps(firmware_records,indent=2)+'\n')
    run('sha256sum',out/'guest/kernel',out/'guest/initramfs',out/'guest/rootfs.ext4',out/'guest/state.qcow2')
if __name__=='__main__': main()
