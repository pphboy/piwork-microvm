#!/usr/bin/env python3
"""Release identity, gate and publication for piwork-microvm.

Nothing here publishes unless an explicit publish command is given; the build
flow itself never pushes or releases. See design.md D1-D7.
"""
import argparse, datetime, gzip, hashlib, json, os, pathlib, shutil, subprocess, sys, tarfile
import bundle
import components
import piwork_release
from source import source_path, input_mode
ROOT=pathlib.Path(__file__).resolve().parents[1]
CHANGE=ROOT/'openspec/changes/import-official-piwork-binaries'
EVIDENCE=CHANGE/'evidence'
PLATFORMS=[('linux','piwork-microvm'),('windows','piwork-microvm.exe')]
ENTRIES=[('cli','linux'),('cli','windows'),('gui','linux'),('gui','windows')]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read_json(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write_json(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def utc_now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def built_input_mode():
    """Mode that actually produced dist/piwork, not merely the current lock."""
    marker=ROOT/'dist/piwork/build-mode.json'
    if marker.is_file():
        try:return read_json(marker).get('inputMode','source')
        except Exception:fail('dist/piwork/build-mode.json is unreadable')
    return input_mode(read_json(ROOT/'build.lock.json'))
def upstream_version():
    """Version declared by the pinned upstream input, not by this wrapper."""
    lock=read_json(ROOT/'build.lock.json')
    if input_mode(lock)=='official-release':
        return lock['piwork']['release']['metadata']['releaseVersion']
    pkg=source_path()/'package.json'
    return read_json(pkg).get('version','unknown') if pkg.exists() else 'unknown'
def locked_inputs():
    """Identity of the pinned build inputs; stable while build.lock.json is unchanged."""
    lock=read_json(ROOT/'build.lock.json')
    return {'buildLockSHA256':sha(ROOT/'build.lock.json'),
            'builtInputMode':built_input_mode(),
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
def artifact_name(entry,platform):
    return bundle.artifact_names(entry,platform)['artifact']
def artifact_path(entry,platform):
    return ROOT/'dist'/artifact_name(entry,platform)
def manifest_name(entry,platform):
    return bundle.artifact_names(entry,platform)['manifest']
def body_record(entry,platform):
    return read_json(bundle.body_record_path(entry,platform))
def artifacts():
    """Identity of the four artifacts built for this release; differs on every rebuild."""
    out=[]
    for entry,platform in ENTRIES:
        binary=artifact_path(entry,platform)
        if not binary.exists():continue
        manifest=ROOT/'dist'/manifest_name(entry,platform)
        raw=json.dumps(read_json(manifest),sort_keys=True,separators=(',',':')).encode()
        record=body_record(entry,platform)
        out.append({'entry':entry,'path':'dist/'+binary.name,'os':platform,'arch':'amd64',
                    'version':record['version'],'size':binary.stat().st_size,
                    'sha256':sha(binary),'manifestSha256':hashlib.sha256(raw).hexdigest()})
    return out

def input_fingerprint():
    """Canonical digest of every locked input identity, stable across rebuilds."""
    raw=json.dumps(locked_inputs(),sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()
def evidence_records(evidence):
    """Every JSON record that declares a scope; unrelated files are ignored."""
    records=[]
    if not pathlib.Path(evidence).is_dir():return records
    for path in sorted(pathlib.Path(evidence).rglob('*.json')):
        try:value=read_json(path)
        except Exception:continue
        if isinstance(value,dict) and value.get('scope'):
            value=dict(value);value['_path']=str(path);records.append(value)
    return records
def verification(evidence):
    """Scoped acceptance status; only a full input fingerprint match may upgrade a scope."""
    current=input_fingerprint()
    records=evidence_records(evidence)
    def matching(scope,platform=None):
        return [r for r in records if r.get('scope')==scope and r.get('status')=='passed'
                and r.get('inputFingerprint')==current
                and (platform is None or r.get('platform')==platform)]
    def scoped(scope,platform=None):
        hits=matching(scope,platform)
        if hits:
            return {'status':'verified','verifiedAt':max(r.get('checkedAt','') for r in hits),
                    'records':[r['_path'] for r in hits]}
        reason='no passing record with the current input fingerprint'
        if records:
            reason='recorded evidence lacks a matching input fingerprint, is incomplete, or covers other inputs'
        return {'status':'not-verified','reason':reason}
    upstream=[r for r in records if r.get('scope')=='upstream']
    return {'basis':'locked-inputs','inputFingerprint':current,
            'note':'Acceptance evidence covers the locked inputs, not these artifact bytes: the Guest ext4 rootfs is regenerated with fresh UUIDs on every build, so artifacts are not byte-reproducible. Verify downloads with the checksums in this manifest.',
            'scopes':{
                'build':{'platforms':{platform:scoped('build',platform) for platform,_ in PLATFORMS}},
                'integration':{'platforms':{platform:scoped('integration',platform) for platform,_ in PLATFORMS}},
                'realModel':{'platforms':{platform:scoped('real-model',platform) for platform,_ in PLATFORMS}},
                'upstream':{'status':'reported' if upstream else 'none',
                            'note':'Upstream verification is informational and never upgrades a MicroVM scope.',
                            'records':[r['_path'] for r in upstream]}}}

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

def guest_package_count():
    """Number of Debian packages in the Guest rootfs, read without mounting the image."""
    image=ROOT/'dist/guest/rootfs.ext4'
    debugfs=shutil.which('debugfs') or ('/usr/sbin/debugfs' if pathlib.Path('/usr/sbin/debugfs').exists() else None)
    if not image.exists() or not debugfs:return None
    try:r=subprocess.run([debugfs,'-R','cat /usr/share/piwork-guest-packages.txt',str(image)],capture_output=True,text=True,timeout=60)
    except (OSError,subprocess.SubprocessError):return None
    return len([line for line in r.stdout.splitlines() if line.strip()]) or None

def guest_licenses_archive(out):
    """Readable license texts, so readers need not download the ~400 MB artifact."""
    tree=ROOT/'dist/guest/guest-licenses'
    if not tree.is_dir():fail('guest license tree missing; run make guest before releasing')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|',format=tarfile.PAX_FORMAT) as tar:
        for p in sorted(tree.rglob('*')):
            if not p.is_file():continue
            info=tarfile.TarInfo('guest-licenses/'+p.relative_to(tree).as_posix())
            info.size=p.stat().st_size;info.mode=0o444;info.mtime=0;info.uid=info.gid=0
            with p.open('rb') as f:tar.addfile(info,f)
    return out
def piwork_licenses_archive(out):
    """Readable license texts for the imported binaries, Go modules and images."""
    tree=ROOT/'dist/piwork/upstream-release/licenses'
    if not tree.is_dir():fail('official license tree missing; run make piwork-check')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|',format=tarfile.PAX_FORMAT) as tar:
        for p in sorted(tree.rglob('*')):
            if not p.is_file():continue
            info=tarfile.TarInfo('piwork-licenses/'+p.relative_to(tree).as_posix())
            info.size=p.stat().st_size;info.mode=0o444;info.mtime=0;info.uid=info.gid=0
            with p.open('rb') as f:tar.addfile(info,f)
    return out
def official_license_gaps():
    try:
        index=read_json(ROOT/'dist/piwork/upstream-release/licenses/index.json')
    except Exception:
        return None
    modules=index.get('goModules',{}).get('absent',0)
    debian=sum(record.get('absentDebianLicenses',0) for record in index.get('images',{}).values())
    return modules,debian
def guest_license_summary():
    p=ROOT/'dist/guest/guest-licenses/index.json'
    return read_json(p) if p.exists() else None

def notes(version,evidence):
    m=manifest(version,evidence);inputs=m['inputs'];kernel=inputs['kernel'];qemu=inputs['qemu']
    lines=['# piwork-microvm v'+version,'',
           'Bundles original Piwork '+inputs['upstreamPiworkVersion']+' at commit '+inputs['piwork']['commit']+', unmodified.']
    release_input=inputs['piwork'].get('release')
    if inputs.get('builtInputMode')=='official-release' and release_input:
        lines+=['','Official release input: `'+release_input['tag']+'` (upstream Preview), actual build commit `'
                +inputs['piwork']['commit']+'`, publication commit `'+release_input['releaseCommit']+'`. Four asset sizes/SHA256 and three production image digests are recorded in the manifest.']
    lines+=['',
           '## Artifacts','','| File | Platform | Bytes | SHA256 |','| --- | --- | --- | --- |']
    for a in m['artifacts']:
        lines.append('| `'+asset_label(version,a['entry'],a['os'],a['path'])+'` | '+a.get('entry','cli')+' '+a['os']+'/'+a['arch']+' | '+str(a['size'])+' | `'+a['sha256']+'` |')
    lines+=['','Verify downloads with these checksums.','','## Verification','',m['verification']['note'],
            '','Input fingerprint: `'+m['verification']['inputFingerprint']+'`',
            '','| Scope | Platform | Status | Evidence |','| --- | --- | --- | --- |']
    for scope,group in m['verification']['scopes'].items():
        if scope=='upstream':
            lines.append('| upstream | - | '+group['status']+' | '+group['note']+' |')
            continue
        for platform,status in group['platforms'].items():
            detail=', '.join(status.get('records',[]))or status.get('reason','')
            lines.append('| '+scope+' | '+platform+' | '+status['status']+' | '+detail+' |')
    snapshot=inputs['toolchain']['debianSnapshot']
    count=guest_package_count()
    packages=(str(count)+' Debian packages') if count else 'Debian packages'
    licenses=guest_license_summary()
    if licenses and licenses.get('absent')==0:
        license_gap='all '+str(licenses.get('packages'))+' Guest packages have a text.'
    elif licenses:
        license_gap=str(licenses.get('absent'))+' of '+str(licenses.get('packages'))+' Guest packages have no extractable text; `index.json` lists them.'
    else:
        license_gap='the license index was not available when this manifest was generated.'
    gaps=official_license_gaps()
    official_gap=''
    if gaps is not None:
        modules,debian=gaps
        official_gap=(' The imported binaries/images index also records %d Go modules and %d Debian package texts without an extractable file; see `piwork-licenses.tar.gz`.'%(modules,debian))
    lines+=['','## Corresponding source','',
            'This release distributes binaries and a Guest image that include GPL and LGPL components. The written offer below covers every component listed here.','',
            '| Component | License | Source |','| --- | --- | --- |',
            '| Linux '+kernel['version']+', unmodified | GPL-2.0 | '+kernel['url']+', sha256 `'+kernel['sha256']+'` |',
            '| QEMU '+qemu['version']+', modified by '+str(len(qemu['windowsPatches']))+' patches | GPL-2.0 | '+qemu['url']+', sha256 `'+qemu['sha256']+'`, plus the attached `qemu-patches.tar.gz` |',
            '| qboot ROM | GPL-2.0 | `roms/qboot` in the QEMU source archive above, sha256 `'+inputs['qboot']['sha256']+'` |',
            '| libfdt / dtc, linked into QEMU | GPL-2+ | `dtc/` in the QEMU source archive above |',
            '| BusyBox, in the Guest initramfs and rootfs | GPL-2.0 | the `busybox-static` source package at Debian snapshot `'+snapshot+'` |',
            '| '+packages+' in the Guest rootfs | GPL and LGPL mix | source packages at Debian snapshot `'+snapshot+'`; the installed list is `usr/share/piwork-guest-packages.txt` inside `rootfs.ext4` |',
            '| MinGW-w64 runtime libraries in the Windows QEMU | GPL-3.0 with the GCC runtime exception, or LGPL | the source packages recorded in `provenance/windows-toolchain.lock.json` |',
            '| Production `piwork-agentd`, `piwork-file-helper` and `piwork-snapshot-helper` images, embedded in `images.tar` | Node.js MIT plus npm/Debian component licenses | built from the Piwork source at commit `'+inputs['piwork']['commit']+'`; readable texts in `piwork-licenses.tar.gz` and `provenance/piwork-upstream/licenses/images/` |',
            '| Node.js 24 runtime, npm and Yarn inside the Agent image | MIT and bundled package licenses | same image source above; texts in `piwork-licenses.tar.gz` |',
            '| Debian packages inside the production Agent image, including GCC runtime libraries | GPL/LGPL and other Debian licenses | exact installed versions and copyright/source notices in `piwork-licenses.tar.gz` (`images/agent/INDEX.json`); Debian sources at https://deb.debian.org/debian/pool/ and https://snapshot.debian.org/; covered by the written offer below |',
            '| Shared libraries shipped beside QEMU (`qemu/lib/*.so`, `*.dll`) | LGPL-2.1+, BSD or GPL-2+ | shipped with the artifact; source as listed above |','',
            'Written offer: the complete corresponding source for every GPL and LGPL component listed above is available on request for three years from this release date (GPL-2.0 section 3(b)).','',
            '## Known limitations','',
            '- License texts for the Guest rootfs packages and BusyBox ship at `provenance/guest-licenses/` inside the artifact and in `guest-licenses.tar.gz`, so they can be read without booting the VM; '+license_gap+' Kernel and QEMU license texts ship alongside in `provenance/` and `qemu/licenses/`.',
            '- Windows artifacts are unsigned, so SmartScreen may warn on first run. Windows requires WHPX and WebView2; Linux requires KVM and the documented GTK/WebKit runtime for the GUI.',
            '- Piwork 0.0.11 is an upstream Preview. This scoped integration does not verify real-model calls, a full failure matrix or general downgrade compatibility. Upgrade a stopped backup copy and retain the untouched backup.',
            '- Readable license texts for the imported binaries, Go modules and production images ship as `piwork-licenses.tar.gz` and under `provenance/piwork-upstream/licenses/`. '+('The index records every extraction gap.'+official_gap if official_gap else 'The index records every extraction gap.'),
            '- Acceptance evidence is recorded against the locked inputs, not against these artifact bytes; see Verification above.','']
    return '\n'.join(lines)

def cmd_manifest(args):
    out=pathlib.Path(args.out) if args.out else ROOT/'dist/release-manifest.json'
    write_json(out,manifest(args.version,pathlib.Path(args.evidence_dir)))
    print('Wrote',out)

def cmd_patches(args):
    files=patches(pathlib.Path(args.out))
    print('Wrote',args.out,'('+str(len(files))+' patches)')
def cmd_licenses(args):
    out=guest_licenses_archive(pathlib.Path(args.out))
    print('Wrote',out)
def cmd_notes(args):
    pathlib.Path(args.out).write_text(notes(args.version,pathlib.Path(args.evidence_dir)),encoding='utf-8')
    print('Wrote',args.out)

class Failure(Exception):pass
def fail(message):raise Failure(message)
def git_out(*args):
    r=subprocess.run(['git',*args],capture_output=True,text=True)
    return r.stdout.strip() if r.returncode==0 else None
def check_tree_clean():
    """Tracked and untracked changes both block a release: untracked Go files compile into artifacts."""
    if git_out('status','--porcelain'):fail('working tree has uncommitted or untracked changes')
def check_input_locked():
    """Source mode verifies the clean checkout; official mode verifies the import record."""
    if built_input_mode()=='official-release':
        try:piwork_release.check_prepared()
        except piwork_release.ReleaseError as err:fail('official input check failed: '+str(err))
        return
    r=subprocess.run(['python3',str(ROOT/'scripts/source.py'),'--check'],capture_output=True,text=True)
    if r.returncode!=0:fail('locked source check failed: '+(r.stderr.strip() or r.stdout.strip()))
def check_tag_absent(version):
    if git_out('rev-parse','--verify','--quiet','refs/tags/v'+version) is not None:fail('tag v'+version+' already exists')
def check_gh():
    if not shutil.which('gh'):fail('gh CLI is required to publish a release')
    if subprocess.run(['gh','auth','status'],capture_output=True).returncode!=0:fail('gh is not authenticated')
def check_head_pushed():
    """A tag must point at a commit the remote branch already contains."""
    head=git_out('rev-parse','HEAD');upstream=git_out('rev-parse','--abbrev-ref','--symbolic-full-name','@{upstream}')
    if not head or not upstream:fail('current branch has no upstream; push it before publishing')
    if subprocess.run(['git','merge-base','--is-ancestor',head,upstream],cwd=ROOT).returncode!=0:
        fail('HEAD is not contained in '+upstream+'; push the branch before publishing')
def preflight(version,require_gh,allow_existing_tag=False):
    """Gate steps 1-3. Everything here runs before any test, build or publish."""
    check_tree_clean();check_input_locked()
    if not allow_existing_tag:check_tag_absent(version)
    if require_gh:check_head_pushed();check_gh()

def run_tests():
    if subprocess.run(['go','test','./...'],cwd=ROOT).returncode!=0:fail('go test ./... failed')
    if subprocess.run(['python3','-m','unittest','discover','-s','scripts','-p','*_test.py'],
                      cwd=ROOT).returncode!=0:fail('Python script tests failed')
def artifact_bytes(path):
    """Return the launcher body bytes without reading the embedded payload."""
    info=bundle.read_trailer(path)
    with pathlib.Path(path).open('rb') as f:return f.read(info['offset'])
def verify_resources(entry,platform):
    """The embedded resource manifest must describe the current build inputs."""
    manifest=read_json(ROOT/'dist'/manifest_name(entry,platform))
    recorded={record['path']:record['sha256'] for record in manifest.get('files',[])}
    inputs=bundle.collect_inputs(entry,platform,ROOT/'dist')
    expected={}
    for name,source in inputs.items():
        if isinstance(source,tuple) and source[0]=='inline':
            expected[name]=hashlib.sha256(source[1]).hexdigest()
        else:expected[name]=sha(source)
    if recorded!=expected:
        missing=sorted(set(expected)-set(recorded));extra=sorted(set(recorded)-set(expected))
        changed=sorted(name for name in set(expected)&set(recorded) if expected[name]!=recorded[name])
        fail('resource manifest differs for %s/%s (missing %s, extra %s, changed %s)'
             %(entry,platform,missing[:3],extra[:3],changed[:3]))
def sha_region(path,offset,length):
    digest=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        f.seek(offset);remaining=length
        while remaining:
            chunk=f.read(min(1<<20,remaining))
            if not chunk:fail('artifact payload is truncated: '+str(path))
            digest.update(chunk);remaining-=len(chunk)
    return digest.hexdigest()
def verify_embedded(entry,platform,binary,info):
    """The trailer manifest and payload must equal the sidecar built from current inputs."""
    sidecar=read_json(ROOT/'dist'/manifest_name(entry,platform))
    if info['manifest']!=sidecar:fail('%s embedded manifest differs from %s'%(binary.name,manifest_name(entry,platform)))
    if info['length']!=sidecar.get('size') and sidecar.get('size') is not None:
        fail('%s payload length differs from the sidecar'%binary.name)
    if sha_region(binary,info['offset'],info['length'])!=info['manifest'].get('payloadSha256'):
        fail('%s embedded payload digest differs from its manifest'%binary.name)
def verify_artifact_version(version):
    """Every entry must carry this version, a matching body record and real resources."""
    for entry,platform in ENTRIES:
        binary=artifact_path(entry,platform)
        if not binary.exists():fail('missing artifact '+str(binary))
        try:info=bundle.read_trailer(binary)
        except (OSError,ValueError) as err:fail('%s trailer is invalid: %s'%(binary.name,err))
        try:record=body_record(entry,platform)
        except Exception as err:fail('%s build record is unreadable: %s'%(binary.name,err))
        if record.get('version')!=version:
            fail('%s build record reports %s, expected %s'%(binary.name,record.get('version'),version))
        identity={'version':version,'manifest':'v2','upstream':upstream_version(),
                  'commit':read_json(ROOT/'build.lock.json')['piwork']['commit']}
        try:
            bundle.verify_body_record(entry,platform,ROOT/'dist'/bundle.artifact_names(entry,platform)['body'],identity)
        except (SystemExit,OSError,ValueError) as err:
            fail('%s body identity is invalid: %s'%(binary.name,err))
        body=artifact_bytes(binary)
        digest=record.get('body') or {}
        if (digest.get('size'),digest.get('sha256'))!=(len(body),hashlib.sha256(body).hexdigest()):
            fail('%s body differs from its build record'%binary.name)
        if platform=='linux' or entry=='gui' and platform=='linux':
            r=subprocess.run([str(binary),'--version'],capture_output=True,text=True)
            if r.returncode!=0:fail('%s --version failed: %s'%(binary.name,r.stderr.strip() or r.returncode))
            if 'piwork-microvm '+version not in r.stdout:
                fail('%s reports "%s", expected version %s'%(binary.name,r.stdout.splitlines()[0] if r.stdout else '',version))
        elif version.encode() not in body:
            fail('%s has no embedded %s version string'%(binary.name,version))
        verify_embedded(entry,platform,binary,info)
        verify_resources(entry,platform)
def run_build(reuse,version):
    """Step 3. The version is an explicit build input, since the release tag does not exist yet.

    Reuse is explicit and non-default: it skips the build, not the gate's other checks.
    The Windows GUI body is native, so a fresh build prepares it only when it was
    already produced on Windows and recorded; all four artifacts are always verified.
    """
    if not reuse:
        env=os.environ.copy();env['PIWORK_RELEASE_VERSION']=version
        if subprocess.run(['make','piwork-microvm-all','piwork-microvm-gui'],cwd=ROOT,env=env).returncode!=0:fail('artifact build failed')
    lock=read_json(ROOT/'build.lock.json')
    for kind in components.KINDS:
        hit,reason=components.verify(kind,lock,root=ROOT)
        if not hit:fail('component %s cannot be reused (%s); rebuild it before releasing'%(kind,reason))
    missing=[artifact_name(entry,platform) for entry,platform in ENTRIES
             if not artifact_path(entry,platform).exists()]
    if missing:fail('missing artifacts, build before releasing: '+', '.join(missing))
    verify_artifact_version(version)

def cmd_preflight(args):
    preflight(args.version,args.require_gh)
    print('Preflight passed for v'+args.version)
def cmd_release(args):
    """Steps 1-5: gate, build, manifest and notes. Never tags, pushes or publishes."""
    preflight(args.version,False)
    print('Preflight passed for v'+args.version)
    run_tests();print('Tests passed')
    run_build(args.reuse_artifacts,args.version);print('Artifacts ready and report '+args.version)
    evidence=pathlib.Path(args.evidence_dir)
    manifest_out=pathlib.Path(args.out) if args.out else ROOT/'dist/release-manifest.json'
    manifest_value=manifest(args.version,evidence)
    write_json(manifest_out,manifest_value);print('Wrote',manifest_out)
    notes_out=pathlib.Path(args.notes_out) if args.notes_out else ROOT/'dist/release-notes.md'
    notes_text=notes(args.version,evidence)
    notes_out.write_text(notes_text,encoding='utf-8');print('Wrote',notes_out)
    patches_out=pathlib.Path(args.patches_out) if args.patches_out else ROOT/'dist/qemu-patches.tar.gz'
    patches(patches_out);print('Wrote',patches_out)
    licenses_out=ROOT/'dist/guest-licenses.tar.gz'
    guest_licenses_archive(licenses_out);print('Wrote',licenses_out)
    piwork_licenses_out=ROOT/'dist/piwork-licenses.tar.gz'
    piwork_licenses_archive(piwork_licenses_out);print('Wrote',piwork_licenses_out)
    assets=release_assets(args.version,manifest_out,patches_out,licenses_out,piwork_licenses_out)
    plan=freeze_plan(args.version,manifest_value,notes_text,assets)
    print('Froze release plan',plan_path(args.version),'with',len(plan['assets']),'assets')

def repo_slug():
    return git_out('remote','get-url','origin') or 'unknown'
def asset_label(version,entry,platform,name):
    base='piwork-microvm-gui' if entry=='gui' else 'piwork-microvm'
    return base+'-v'+version+'-'+platform+'-amd64'+('.exe' if name.endswith('.exe') else '')
def release_assets(version,manifest_path,patches_path,licenses_path,piwork_licenses_path=None):
    """Asset names carry the version and entry, so downloads stay distinguishable.

    gh uses the file name as the asset name and a `#label` only sets the display
    label, so the binaries are staged under their release names instead.
    """
    stage=ROOT/'dist/release-assets';stage.mkdir(parents=True,exist_ok=True)
    assets=[]
    for entry,platform in ENTRIES:
        binary=artifact_path(entry,platform)
        if not binary.exists():fail('missing artifact '+binary.name)
        label=asset_label(version,entry,platform,binary.name)
        staged=stage/label
        if staged.exists() or staged.is_symlink():staged.unlink()
        try:os.link(binary,staged)
        except OSError:shutil.copyfile(binary,staged)
        sums=stage/(label+'.sha256');sums.write_text(sha(binary)+'  '+label+'\n',encoding='utf-8')
        assets+=[(staged,label),(sums,label+'.sha256')]
    assets+=[(manifest_path,'release-manifest.json'),(patches_path,'qemu-patches.tar.gz'),(licenses_path,'guest-licenses.tar.gz')]
    if piwork_licenses_path is not None:assets.append((piwork_licenses_path,'piwork-licenses.tar.gz'))
    return assets

def plan_dir(version):
    return ROOT/'dist/release-plans'/('v'+version)
def plan_path(version):
    return plan_dir(version)/'plan.json'
def freeze_plan(version,manifest_value,notes_text,assets):
    """Freeze the exact version plan and asset bytes; later retries never regenerate it."""
    target=plan_dir(version)
    if plan_path(version).exists():
        fail('release plan for v'+version+' is already frozen; use a new version or remove it explicitly')
    target.mkdir(parents=True,exist_ok=True)
    entries=[]
    for path,label in assets:
        staged=target/label
        if staged.exists():staged.unlink()
        try:os.link(path,staged)
        except OSError:shutil.copyfile(path,staged)
        entries.append({'name':label,'size':staged.stat().st_size,'sha256':sha(staged)})
    (target/'notes.md').write_text(notes_text,encoding='utf-8')
    write_json(target/'release-manifest.json',manifest_value)
    plan={'planVersion':1,'version':version,'tag':'v'+version,
          'sourceCommit':git_out('rev-parse','HEAD'),
          'inputFingerprint':input_fingerprint(),'createdAt':utc_now(),
          'manifest':manifest_value,'notes':notes_text,'assets':entries}
    write_json(plan_path(version),plan)
    return plan
def load_plan(version):
    path=plan_path(version)
    if not path.exists():fail('no frozen release plan for v'+version+'; run make release first')
    return read_json(path)
def verify_plan(plan,version):
    """The frozen plan must still describe this version, commit and locked inputs."""
    if plan.get('planVersion')!=1:fail('unsupported release plan version')
    if plan.get('version')!=version or plan.get('tag')!='v'+version:fail('release plan is for another version')
    if plan.get('sourceCommit')!=git_out('rev-parse','HEAD'):fail('release plan targets another source commit')
    if plan.get('inputFingerprint')!=input_fingerprint():fail('release plan was frozen for other locked inputs')
    target=plan_dir(version)
    for asset in plan.get('assets',[]):
        path=target/asset['name']
        if not path.is_file():fail('frozen asset is missing: '+asset['name'])
        if path.stat().st_size!=asset['size']:fail('frozen asset size differs: '+asset['name'])
        if sha(path)!=asset['sha256']:fail('frozen asset digest differs: '+asset['name'])
    notes_path=target/'notes.md'
    if not notes_path.is_file():fail('frozen release notes are missing')
    if notes_path.read_text(encoding='utf-8')!=plan.get('notes'):
        fail('frozen release notes differ from the plan')
def remote_asset(assets,name):
    return next((a for a in assets if a.get('name')==name),None)
def asset_matches(remote,planned):
    return (remote.get('size')==planned['size'] and remote.get('digest')=='sha256:'+planned['sha256'])
def placeholder(remote):
    """Only an incomplete upload with no valid digest may be cleaned from our draft."""
    return remote.get('state')!='uploaded' and not remote.get('digest')
def verify_remote_assets(release_value,plan):
    assets=release_value.get('assets') or []
    missing=[];mismatched=[]
    for planned in plan['assets']:
        actual=remote_asset(assets,planned['name'])
        if actual is None:missing.append(planned['name'])
        elif not asset_matches(actual,planned):mismatched.append(planned['name'])
    if missing:mismatched=mismatched+['missing: '+name for name in missing]
    if mismatched:fail('remote assets are incomplete or differ: '+', '.join(mismatched))
def ensure_remote_tag(tag,commit):
    """Accept only the same annotated tag on the same commit; never move a tag."""
    lines=(git_out('ls-remote','--tags','origin','refs/tags/'+tag,'refs/tags/'+tag+'^{}') or '').splitlines()
    targets={}
    for line in lines:
        sha,_,ref=line.partition('\t');targets[ref.strip()]=sha.strip()
    remote=targets.get('refs/tags/'+tag+'^{}') or targets.get('refs/tags/'+tag)
    if remote is not None:
        if remote!=commit:fail('tag '+tag+' points at '+remote+', plan says '+commit)
        if 'refs/tags/'+tag+'^{}' not in targets:fail('remote tag '+tag+' is not annotated')
        return 'existing'
    local_type=git_out('cat-file','-t','refs/tags/'+tag)
    if local_type and local_type!='tag':fail('local tag '+tag+' exists but is not annotated')
    if local_type=='tag':
        if git_out('rev-parse','refs/tags/'+tag+'^{}')!=commit:fail('local tag '+tag+' points at another commit')
    else:
        subprocess.run(['git','tag','-a',tag,commit,'-m','piwork-microvm '+tag],cwd=ROOT,check=True)
    subprocess.run(['git','push','origin','refs/tags/'+tag],cwd=ROOT,check=True)
    return 'created'
class GitHubRelease:
    """Thin gh CLI wrapper; only the publish command writes remotely."""
    def __init__(self,runner=subprocess.run):
        self.runner=runner
        self.slug=None
    def _run(self,args,check=True):
        result=self.runner(['gh',*args],capture_output=True,text=True)
        if check and result.returncode!=0:
            fail('gh '+' '.join(args)+' failed: '+(result.stderr.strip() or result.stdout.strip()))
        return result
    def repo(self):
        if self.slug is None:
            self.slug=self._run(['repo','view','--json','nameWithOwner','--jq','.nameWithOwner']).stdout.strip()
        return self.slug
    def release(self,tag):
        result=self._run(['api','repos/'+self.repo()+'/releases/tags/'+tag],check=False)
        if result.returncode!=0:
            if 'HTTP 404' in (result.stderr or '') or 'Not Found' in (result.stderr or ''):return None
            fail('cannot read release '+tag+': '+result.stderr.strip())
        return json.loads(result.stdout)
    def create_draft(self,tag,title,notes_file):
        self._run(['release','create',tag,'--draft','--verify-tag','--title',title,'--notes-file',str(notes_file)])
    def upload(self,tag,path,name):
        self._run(['release','upload',tag,str(path)])
    def delete_asset(self,tag,name):
        self._run(['release','delete-asset',tag,name,'--yes'])
    def publish(self,tag):
        self._run(['release','edit',tag,'--draft=false','--verify-tag'])
def publish_plan(plan,version,remote,dry_run=False):
    """Upload the frozen assets, verify the remote bytes, and only then publish."""
    verify_plan(plan,version)
    target=plan_dir(version)
    if dry_run:
        print('Dry run: plan '+plan['tag']+' targets '+plan['sourceCommit'])
        for asset in plan['assets']:print('  asset: '+asset['name']+'  '+str(asset['size'])+'  '+asset['sha256'])
        print('Dry run: no tag created, nothing uploaded or published.')
        return {'status':'dry-run'}
    ensure_remote_tag(plan['tag'],plan['sourceCommit'])
    existing=remote.release(plan['tag'])
    if existing and not existing.get('draft'):
        verify_remote_assets(existing,plan)
        if (existing.get('body') or '').strip()!=plan['notes'].strip():
            fail('published release notes differ from the frozen plan; refusing to rewrite them')
        print('Already published '+plan['tag']+' with matching assets; nothing changed.')
        return {'status':'already-published'}
    if existing is None:
        remote.create_draft(plan['tag'],'piwork-microvm '+plan['tag'],target/'notes.md')
        existing=remote.release(plan['tag'])
    if existing is None:fail('draft release is not readable after creation')
    draft_body=(existing.get('body') or '').strip()
    if draft_body and draft_body!=plan['notes'].strip():
        fail('existing draft notes differ from the frozen plan; refusing to rewrite them')
    assets=existing.get('assets') or []
    for planned in plan['assets']:
        actual=remote_asset(assets,planned['name'])
        if actual is not None and asset_matches(actual,planned):continue
        if actual is not None:
            if not placeholder(actual):fail('remote asset '+planned['name']+' already exists with different content')
            remote.delete_asset(plan['tag'],planned['name'])
        remote.upload(plan['tag'],target/planned['name'],planned['name'])
    current=remote.release(plan['tag'])
    verify_remote_assets(current,plan)
    remote.publish(plan['tag'])
    final=remote.release(plan['tag'])
    if final is None or final.get('draft') is not False:fail('release did not become public')
    verify_remote_assets(final,plan)
    print('Published '+plan['tag'])
    return {'status':'published'}

def cmd_publish(args):
    """Steps 6-7: upload the frozen plan and publish. The only remote-writing command."""
    version=args.version;tag='v'+version
    preflight(version,True,allow_existing_tag=True);print('Preflight passed for '+tag)
    run_tests();print('Tests passed')
    run_build(True,version);print('Artifacts report '+version)
    plan=load_plan(version)
    verify_plan(plan,version)
    if args.dry_run:
        publish_plan(plan,version,GitHubRelease(),dry_run=True)
        print('  repository: '+repo_slug())
        return
    publish_plan(plan,version,GitHubRelease())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('manifest',help='write the release manifest')
    m.add_argument('--version',required=True);m.add_argument('--out');m.add_argument('--evidence-dir',default=str(EVIDENCE))
    m.set_defaults(func=cmd_manifest)
    pa=sub.add_parser('patches',help='write qemu-patches.tar.gz, the corresponding source for the modified GPL component')
    pa.add_argument('--out',default=str(ROOT/'dist/qemu-patches.tar.gz'))
    pa.set_defaults(func=cmd_patches)
    li=sub.add_parser('licenses',help='write guest-licenses.tar.gz, the readable license texts')
    li.add_argument('--out',default=str(ROOT/'dist/guest-licenses.tar.gz'))
    li.set_defaults(func=cmd_licenses)
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
