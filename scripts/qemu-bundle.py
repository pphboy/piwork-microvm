#!/usr/bin/env python3
"""Freeze QEMU's dynamic dependency closure from the pinned build container."""
import hashlib, json, os, pathlib, re, shutil, subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run(*args,**kw):subprocess.run([str(a) for a in args],check=True,**kw)
def digest_file(path):
    with pathlib.Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
    os.chdir(ROOT)
    if os.environ.get('PIWORK_QEMU_CONTAINER')!='1':
        run('docker','run','--rm','--user',f'{os.getuid()}:{os.getgid()}',
            '-e','PIWORK_QEMU_CONTAINER=1','-v',f'{ROOT}:/project','-w','/project',
            'piwork-microvm-qemu-builder:local','python3','scripts/qemu-bundle.py')
        return
    out=ROOT/'dist/qemu';lib=out/'lib'
    if lib.exists():shutil.rmtree(lib)
    lib.mkdir()
    shutil.copyfile('/qemu-build-packages.txt',out/'build-packages.txt')
    binary=out/'qemu-system-x86_64'
    run('strip','--strip-unneeded',binary)
    patched=ROOT/'dist/libslirp-linux-install/lib/libslirp.so.0'
    source_record=ROOT/'dist/qemu-source/linux-libslirp/.piwork-source.json'
    if not patched.is_file() or not source_record.is_file():raise SystemExit('Missing patched Linux libslirp or its source record')
    env=os.environ.copy();env['LD_LIBRARY_PATH']=str(patched.parent)
    dependencies=subprocess.check_output(['ldd',binary],text=True,env=env)
    if 'not found' in dependencies:raise SystemExit('Incomplete QEMU dependency closure')
    files=set(re.findall(r'(?:=>\s+)?(/[^\s()]+)',dependencies))
    # glibc 2.36 integrates DNS/files NSS; include the compat modules too.
    files.update(str(p) for p in pathlib.Path('/lib/x86_64-linux-gnu').glob('libnss_*.so.2') if p.name in ('libnss_files.so.2','libnss_dns.so.2'))
    records=[];packages=set()
    for f in sorted(files):
        source=pathlib.Path(f)
        dest=out/source.name if source.name=='ld-linux-x86-64.so.2' else lib/source.name
        dest.unlink(missing_ok=True)
        shutil.copyfile(source,dest);dest.chmod(0o755 if dest.parent==out else 0o644)
        if source.name=='libslirp.so.0':
            if source.resolve()!=patched.resolve() or digest_file(dest)!=digest_file(patched):raise SystemExit('QEMU resolved an unexpected libslirp')
            ownership='libslirp0:amd64 (patched source)'
            version=json.loads(source_record.read_text())['input']['version']
            packages.add('libslirp0')
        else:
            ownership=None
            for candidate in [f,str(source.resolve()),'/usr'+f if f.startswith('/lib') else f.removeprefix('/usr')]:
                result=subprocess.run(['dpkg-query','-S',candidate],capture_output=True,text=True)
                if result.returncode==0:ownership=result.stdout.splitlines()[0].split(': /')[0];break
            if ownership is None:raise SystemExit('Unidentified runtime library package: '+f)
            package=ownership.split(':')[0];packages.add(package)
            version=subprocess.check_output(['dpkg-query','-W','-f=${Version}',ownership],text=True)
        records.append({'source':f,'file':str(dest.relative_to(ROOT/'dist')),'package':ownership,'version':version,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
    licenses=out/'licenses'
    if licenses.exists():shutil.rmtree(licenses)
    licenses.mkdir()
    source=ROOT/'dist/qemu-source/pristine'/('qemu-'+json.loads((ROOT/'build.lock.json').read_text())['qemu']['version'])
    for p in source.glob('COPYING*'):shutil.copyfile(p,licenses/p.name)
    shutil.copyfile(ROOT/'dist/qemu-source/linux-libslirp/COPYRIGHT',licenses/'libslirp-COPYRIGHT')
    shutil.copyfile(source_record,out/'libslirp-source.json')
    for name in sorted(packages):
        p=pathlib.Path('/usr/share/doc')/name/'copyright'
        if p.exists():shutil.copyfile(p,licenses/(name+'.copyright'))
    (out/'dependencies.json').unlink(missing_ok=True)
    (out/'dependencies.json').write_text(json.dumps(records,indent=2)+'\n')
    run(out/'ld-linux-x86-64.so.2','--library-path',lib,binary,'--version')
if __name__=='__main__':main()
