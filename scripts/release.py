#!/usr/bin/env python3
"""Release identity, gate and publication for piwork-microvm.

Nothing here publishes unless an explicit publish command is given; the build
flow itself never pushes or releases. See design.md D1-D7.
"""
import argparse, datetime, gzip, hashlib, json, pathlib, shutil, subprocess, sys, tarfile
from source import source_path
ROOT=pathlib.Path(__file__).resolve().parents[1]
CHANGE=ROOT/'openspec/changes/support-windows-and-disk-only-storage'
EVIDENCE=CHANGE/'evidence/completion'
PLATFORMS=[('linux','piwork-microvm'),('windows','piwork-microvm.exe')]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read_json(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write_json(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def utc_now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def upstream_version():
    """Version declared by the pinned upstream source, not by this wrapper."""
    pkg=source_path()/'package.json'
    return read_json(pkg).get('version','unknown') if pkg.exists() else 'unknown'
def locked_inputs():
    """Identity of the pinned build inputs; stable while build.lock.json is unchanged."""
    lock=read_json(ROOT/'build.lock.json')
    return {'buildLockSHA256':sha(ROOT/'build.lock.json'),
            'piwork':lock['piwork'],
            'upstreamPiworkVersion':upstream_version(),
            'kernel':{'version':lock['linux']['version'],'url':lock['linux']['url'],'sha256':lock['linux']['sha256']},
            'qemu':{'version':lock['qemu']['version'],'url':lock['qemu']['url'],'sha256':lock['qemu']['sha256'],
                    'windowsPatches':lock['qemu']['windowsPatches']},
            'qboot':lock['qboot'],
            'toolchain':{'go':lock['go'],'dockerVersion':lock['dockerVersion'],'nodeImage':lock['nodeImage'],
                         'dockerImage':lock['dockerImage'],'goImage':lock['goImage'],
                         'guestBaseImage':lock['guestBaseImage'],'debianSnapshot':lock['debianSnapshot'],
                         'windowsToolchain':lock['qemu']['windowsToolchain']}}
def artifacts():
    """Identity of the artifacts built for this release; differs on every rebuild."""
    out=[]
    for platform,name in PLATFORMS:
        binary=ROOT/'dist'/name
        if not binary.exists():continue
        manifest=ROOT/'dist'/('bundle-manifest-'+platform+'.json')
        raw=json.dumps(read_json(manifest),sort_keys=True,separators=(',',':')).encode()
        out.append({'path':'dist/'+name,'os':platform,'arch':'amd64','size':binary.stat().st_size,
                    'sha256':sha(binary),'manifestSha256':hashlib.sha256(raw).hexdigest()})
    return out

def platform_verification(evidence,platform):
    """Acceptance status for one platform. Evidence is keyed to the locked inputs, never to these bytes."""
    first=evidence/platform/'real-model-first.json';restart=evidence/platform/'real-model-restart.json'
    if not (first.exists() and restart.exists()):
        return {'status':'not-verified','reason':'no real-provider acceptance evidence recorded for the locked inputs'}
    a=read_json(first);b=read_json(restart)
    if not (a.get('realProvider') and b.get('continuedAfterRestart')):
        return {'status':'not-verified','reason':'recorded acceptance evidence is incomplete for the locked inputs'}
    return {'status':'verified','verifiedAt':a.get('checkedAt'),'evidence':str((evidence/platform).relative_to(ROOT))}
def verification(evidence):
    return {'basis':'locked-inputs',
            'note':'Acceptance evidence covers the locked inputs, not these artifact bytes: the Guest ext4 rootfs is regenerated with fresh UUIDs on every build, so artifacts are not byte-reproducible. Verify downloads with the checksums in this manifest.',
            'platforms':{platform:platform_verification(evidence,platform) for platform,_ in PLATFORMS}}

def manifest(version,evidence):
    return {'manifestVersion':1,
            'release':{'version':version,'tag':'v'+version,'createdAt':utc_now()},
            'inputs':locked_inputs(),
            'artifacts':artifacts(),
            'verification':verification(evidence)}

def patches(out):
    """The QEMU patches are the only modification to a GPL component, so they are corresponding source."""
    files=sorted((ROOT/'guest/qemu').glob('*.patch'))
    if not files:fail('no QEMU patches found')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|',format=tarfile.PAX_FORMAT) as tar:
        for p in files:
            info=tarfile.TarInfo(p.name);info.size=p.stat().st_size;info.mode=0o644;info.mtime=0;info.uid=info.gid=0
            with p.open('rb') as f:tar.addfile(info,f)
    return files

def notes(version,evidence):
    m=manifest(version,evidence);inputs=m['inputs'];kernel=inputs['kernel'];qemu=inputs['qemu']
    lines=['# piwork-microvm v'+version,'',
           'Bundles original Piwork '+inputs['upstreamPiworkVersion']+' at commit '+inputs['piwork']['commit']+', unmodified.','',
           '## Artifacts','','| File | Platform | Bytes | SHA256 |','| --- | --- | --- | --- |']
    for a in m['artifacts']:
        lines.append('| `'+pathlib.Path(a['path']).name+'` | '+a['os']+'/'+a['arch']+' | '+str(a['size'])+' | `'+a['sha256']+'` |')
    lines+=['','Verify downloads with these checksums.','',
            '## Verification','',m['verification']['note'],'','| Platform | Status | Evidence |','| --- | --- | --- |']
    for platform,status in m['verification']['platforms'].items():
        lines.append('| '+platform+' | '+status['status']+' | '+status.get('evidence',status.get('reason',''))+' |')
    lines+=['','## Corresponding source','',
            'This release distributes binaries that include GPL-2.0 components. Their corresponding source is:','',
            '- Linux '+kernel['version']+', unmodified: '+kernel['url']+', sha256 `'+kernel['sha256']+'`.',
            '- QEMU '+qemu['version']+', modified by '+str(len(qemu['windowsPatches']))+' patches: '+qemu['url']+', sha256 `'+qemu['sha256']+'`, plus the attached `qemu-patches.tar.gz`.',
            '- qboot ROM, '+inputs['qboot']['file']+', sha256 `'+inputs['qboot']['sha256']+'`.','',
            'Written offer: the corresponding source for the GPL components above is available on request for three years from this release date (GPL-2.0 section 3(b)).','',
            '## Known limitations','',
            '- Guest rootfs distribution-package licenses are not bundled; the artifact carries the package manifest only. This is a known gap for public redistribution.',
            '- Windows artifacts are unsigned, so SmartScreen may warn on first run.',
            '- Acceptance evidence is recorded against the locked inputs, not against these artifact bytes; see Verification above.','']
    return '\n'.join(lines)

def cmd_manifest(args):
    out=pathlib.Path(args.out) if args.out else ROOT/'dist/release-manifest.json'
    write_json(out,manifest(args.version,pathlib.Path(args.evidence_dir)))
    print('Wrote',out)

def cmd_patches(args):
    files=patches(pathlib.Path(args.out))
    print('Wrote',args.out,'('+str(len(files))+' patches)')
def cmd_notes(args):
    pathlib.Path(args.out).write_text(notes(args.version,pathlib.Path(args.evidence_dir)),encoding='utf-8')
    print('Wrote',args.out)

class Failure(Exception):pass
def fail(message):raise Failure(message)
def git_out(*args):
    r=subprocess.run(['git',*args],capture_output=True,text=True)
    return r.stdout.strip() if r.returncode==0 else None
def check_tree_clean():
    """Tracked changes only: untracked scratch files must not block a release."""
    if git_out('status','--porcelain','--untracked-files=no'):fail('working tree has uncommitted changes')
def check_source_locked():
    r=subprocess.run(['python3',str(ROOT/'scripts/source.py'),'--check'],capture_output=True,text=True)
    if r.returncode!=0:fail('locked source check failed: '+(r.stderr.strip() or r.stdout.strip()))
def check_tag_absent(version):
    if git_out('rev-parse','--verify','--quiet','refs/tags/v'+version) is not None:fail('tag v'+version+' already exists')
def check_gh():
    if not shutil.which('gh'):fail('gh CLI is required to publish a release')
    if subprocess.run(['gh','auth','status'],capture_output=True).returncode!=0:fail('gh is not authenticated')
def preflight(version,require_gh):
    """Gate steps 1-3. Everything here runs before any test, build or publish."""
    check_tree_clean();check_source_locked();check_tag_absent(version)
    if require_gh:check_gh()

def run_tests():
    if subprocess.run(['go','test','./...'],cwd=ROOT).returncode!=0:fail('go test ./... failed')
def run_build(reuse):
    """Step 3. Reuse is explicit and non-default: it skips the build, not the gate's other checks."""
    if reuse:
        missing=[name for _,name in PLATFORMS if not (ROOT/'dist'/name).exists()]
        if missing:fail('--reuse-artifacts but missing: '+', '.join(missing))
        return
    if subprocess.run(['make','piwork-microvm-all'],cwd=ROOT).returncode!=0:fail('artifact build failed')

def cmd_preflight(args):
    preflight(args.version,args.require_gh)
    print('Preflight passed for v'+args.version)
def cmd_release(args):
    """Steps 1-5: gate, build, manifest and notes. Never tags, pushes or publishes."""
    preflight(args.version,False)
    print('Preflight passed for v'+args.version)
    run_tests();print('Tests passed')
    run_build(args.reuse_artifacts);print('Artifacts ready')
    evidence=pathlib.Path(args.evidence_dir)
    manifest_out=pathlib.Path(args.out) if args.out else ROOT/'dist/release-manifest.json'
    write_json(manifest_out,manifest(args.version,evidence));print('Wrote',manifest_out)
    notes_out=pathlib.Path(args.notes_out) if args.notes_out else ROOT/'dist/release-notes.md'
    notes_out.write_text(notes(args.version,evidence),encoding='utf-8');print('Wrote',notes_out)
    patches_out=pathlib.Path(args.patches_out) if args.patches_out else ROOT/'dist/qemu-patches.tar.gz'
    patches(patches_out);print('Wrote',patches_out)

def repo_slug():
    return git_out('remote','get-url','origin') or 'unknown'
def release_assets(version,manifest_path,patches_path):
    """D4: asset names carry the version, so downloads stay distinguishable across releases."""
    stage=ROOT/'dist/release-assets';stage.mkdir(parents=True,exist_ok=True)
    assets=[]
    for platform,name in PLATFORMS:
        binary=ROOT/'dist'/name
        if not binary.exists():fail('missing artifact '+name)
        label='piwork-microvm-v'+version+'-'+platform+'-amd64'+('.exe' if name.endswith('.exe') else '')
        sums=stage/(label+'.sha256');sums.write_text(sha(binary)+'  '+label+'\n',encoding='utf-8')
        assets+=[(binary,label),(sums,label+'.sha256')]
    return assets+[(manifest_path,'release-manifest.json'),(patches_path,'qemu-patches.tar.gz')]

def cmd_publish(args):
    """Steps 6-7: tag and GitHub Release. The only command here that writes remotely."""
    version=args.version;tag='v'+version
    preflight(version,True);print('Preflight passed for '+tag)
    missing=[name for _,name in PLATFORMS if not (ROOT/'dist'/name).exists()]
    if missing:fail('missing artifacts, build before publishing: '+', '.join(missing))
    evidence=pathlib.Path(args.evidence_dir)
    manifest_out=pathlib.Path(args.manifest_out) if args.manifest_out else ROOT/'dist/release-manifest.json'
    notes_out=pathlib.Path(args.notes_out) if args.notes_out else ROOT/'dist/release-notes.md'
    patches_out=pathlib.Path(args.patches_out) if args.patches_out else ROOT/'dist/qemu-patches.tar.gz'
    write_json(manifest_out,manifest(version,evidence));print('Wrote',manifest_out)
    notes_out.write_text(notes(version,evidence),encoding='utf-8');print('Wrote',notes_out)
    patches(patches_out);print('Wrote',patches_out)
    assets=release_assets(version,manifest_out,patches_out)
    if args.dry_run:
        print('Dry run: no tag created, nothing pushed and no release published.')
        print('  repository: '+repo_slug())
        print('  tag: '+tag)
        for path,label in assets:print('  asset: '+label+'  <- '+str(path.relative_to(ROOT)))
        return
    subprocess.run(['git','tag','-a',tag,'-m','piwork-microvm '+tag],cwd=ROOT,check=True)
    subprocess.run(['git','push','origin',tag],cwd=ROOT,check=True)
    command=['gh','release','create',tag,'--verify-tag','--title','piwork-microvm '+tag,'--notes-file',str(notes_out)]
    command+=[str(path)+'#'+label for path,label in assets]
    subprocess.run(command,cwd=ROOT,check=True)
    print('Published '+tag)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('manifest',help='write the release manifest')
    m.add_argument('--version',required=True);m.add_argument('--out');m.add_argument('--evidence-dir',default=str(EVIDENCE))
    m.set_defaults(func=cmd_manifest)
    pa=sub.add_parser('patches',help='write qemu-patches.tar.gz, the corresponding source for the modified GPL component')
    pa.add_argument('--out',default=str(ROOT/'dist/qemu-patches.tar.gz'))
    pa.set_defaults(func=cmd_patches)
    n=sub.add_parser('notes',help='write the release notes')
    n.add_argument('--version',required=True);n.add_argument('--out',default=str(ROOT/'dist/release-notes.md'))
    n.add_argument('--evidence-dir',default=str(EVIDENCE))
    n.set_defaults(func=cmd_notes)
    f=sub.add_parser('preflight',help='run the release gate checks')
    f.add_argument('--version',required=True);f.add_argument('--require-gh',action='store_true')
    f.set_defaults(func=cmd_preflight)
    r=sub.add_parser('release',help='preflight, test, build, manifest and notes; never tags or publishes')
    r.add_argument('--version',required=True);r.add_argument('--out');r.add_argument('--evidence-dir',default=str(EVIDENCE))
    r.add_argument('--notes-out');r.add_argument('--patches-out')
    r.add_argument('--reuse-artifacts',action='store_true',help='skip the build step; artifacts must already exist')
    r.set_defaults(func=cmd_release)
    b=sub.add_parser('publish',help='tag and create the public GitHub Release')
    b.add_argument('--version',required=True);b.add_argument('--evidence-dir',default=str(EVIDENCE))
    b.add_argument('--manifest-out');b.add_argument('--notes-out');b.add_argument('--patches-out')
    b.add_argument('--dry-run',action='store_true',help='print the tag and asset list without creating anything')
    b.set_defaults(func=cmd_publish)
    args=p.parse_args()
    try:args.func(args)
    except Failure as e:print('release: '+str(e),file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
