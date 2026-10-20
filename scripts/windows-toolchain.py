#!/usr/bin/env python3
"""Freeze/download exact cross-toolchain RPMs; never resolve packages at build time."""
import argparse,concurrent.futures,hashlib,json,pathlib,subprocess,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='registry.fedoraproject.org/fedora@sha256:291ed4c06d5435a92d05ad622c9717afde6911e96d335e02919336eed0c8ae03'
LOCK=ROOT/'guest/qemu/windows-toolchain.lock.json'
CACHE=ROOT/'dist/windows-toolchain/rpms'
def packages(image):
    rows=subprocess.check_output(['docker','run','--rm',image,'rpm','-qa','--qf','%{NAME}|%{VERSION}|%{RELEASE}|%{ARCH}|%{SOURCERPM}\n'],text=True)
    return {r.split('|')[0]:r.split('|') for r in rows.splitlines()}
def fetch(record,refresh):
    p=CACHE/record['file']
    if not p.exists():
        temp=p.with_suffix('.part')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(record['url'],timeout=60) as source,temp.open('wb') as out:
                    while data:=source.read(1<<20):out.write(data)
                temp.replace(p);break
            except Exception:
                temp.unlink(missing_ok=True)
                if attempt==2:raise
    with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    if refresh:record['sha256']=digest
    elif digest!=record['sha256']:raise RuntimeError('Toolchain RPM checksum mismatch: '+p.name)
    return record
def main():
    a=argparse.ArgumentParser();a.add_argument('--refresh',action='store_true');a.add_argument('--check-builder',action='store_true');o=a.parse_args()
    CACHE.mkdir(parents=True,exist_ok=True)
    if o.refresh:
        before=packages(BASE);after=packages('piwork-microvm-qemu-windows-builder:local');records=[]
        for name,fields in sorted(after.items()):
            if before.get(name)==fields:continue
            name,version,release,arch,source=fields
            source_name,source_version,source_release=source.removesuffix('.src.rpm').rsplit('-',2)
            filename=f'{name}-{version}-{release}.{arch}.rpm'
            records.append({'file':filename,'url':f'https://kojipkgs.fedoraproject.org/packages/{source_name}/{source_version}/{source_release}/{arch}/{filename}'})
        lock={'version':1,'base':BASE,'installedPackages':list(after.values()),'rpms':records}
    else:
        expected=json.loads((ROOT/'build.lock.json').read_text())['qemu']['windowsToolchain']
        if hashlib.sha256(LOCK.read_bytes()).hexdigest()!=expected['sha256']:
            raise SystemExit('Windows toolchain manifest checksum differs from build.lock.json')
        lock=json.loads(LOCK.read_text())
        if lock['base']!=expected['baseImage']:raise SystemExit('Windows toolchain base image differs from build.lock.json')
    if o.check_builder:
        actual=sorted(packages('piwork-microvm-qemu-windows-builder:local').values())
        if actual!=sorted(lock['installedPackages']):raise SystemExit('Windows builder package identity differs from the lock')
        print('Windows builder matches all fixed package identities');return
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records=list(pool.map(lambda r:fetch(r,o.refresh),lock['rpms']))
    if o.refresh:
        lock['rpms']=records;LOCK.write_text(json.dumps(lock,indent=2)+'\n')
        main_path=ROOT/'build.lock.json';main_lock=json.loads(main_path.read_text())
        main_lock['qemu']['windowsToolchain']={'manifest':str(LOCK.relative_to(ROOT)),'sha256':hashlib.sha256(LOCK.read_bytes()).hexdigest(),'baseImage':BASE}
        main_path.write_text(json.dumps(main_lock,indent=2)+'\n')
    print('Verified fixed Windows toolchain RPMs:',len(records))
if __name__=='__main__':main()
