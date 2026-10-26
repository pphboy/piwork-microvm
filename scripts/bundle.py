#!/usr/bin/env python3
"""Append a deterministic gzip/tar payload and checked index to the Go entry.

The CLI entry remains the default. The GUI entry uses a separately built Wails
body and separate payload/manifest/artifact names so it never replaces CLI files.
"""
import argparse, gzip, hashlib, json, os, pathlib, shutil, struct, subprocess, tarfile
import piwork_release
from source import source_path, verify, input_mode

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAGIC = b'PIWORK-BUNDLE-v1'
TRAILER_SIZE = 64


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def git(*args):
    """Run git read-only; return stripped stdout, or None when unavailable."""
    try:
        return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def release_version():
    """Version of the annotated tag exactly at HEAD, or None when HEAD is untagged."""
    name = git('describe', '--tags', '--exact-match', 'HEAD')
    if not name or git('cat-file', '-t', name) != 'tag':
        return None
    return name[1:] if name.startswith('v') else name


def built_input_mode(out=None, lock=None):
    """The mode that actually produced dist/piwork, not merely the current lock."""
    lock = lock or json.loads((ROOT / 'build.lock.json').read_text())
    marker = pathlib.Path(out or (ROOT / 'dist')) / 'piwork/build-mode.json'
    if marker.is_file():
        try:
            return json.loads(marker.read_text(encoding='utf-8-sig')).get('inputMode', 'source')
        except json.JSONDecodeError:
            raise SystemExit('dist/piwork/build-mode.json is unreadable')
    return input_mode(lock)


def input_fingerprint(lock=None):
    """Stable fingerprint of the locked inputs a body was built against.

    The native Windows script builds the same field list, so a body cannot be
    packaged after the lock changed.
    """
    lock = lock or json.loads((ROOT / 'build.lock.json').read_text())
    piwork = lock['piwork']
    release = piwork.get('release') or {}
    assets = release.get('assets') or {}
    fields = [piwork.get('inputMode', 'source'), piwork.get('commit', ''),
              release.get('tag', ''), release.get('releaseCommit', '')]
    for key in ('archive', 'releaseBuild', 'releaseManifest', 'sha256sums'):
        fields.append((assets.get(key) or {}).get('sha256', ''))
    fields += [lock.get('go', ''), lock.get('linux', {}).get('sha256', ''),
               lock.get('qemu', {}).get('sha256', ''), lock.get('guestBaseImage', ''),
               lock.get('dockerImage', ''), lock.get('debianSnapshot', '')]
    return hashlib.sha256('\n'.join(fields).encode()).hexdigest()


def source_fingerprint(root=None, entry='cli'):
    """Digest body inputs, including embedded GUI files and resource recipes."""
    root = pathlib.Path(root or ROOT)
    skip = {'.git', 'dist', 'openspec', 'node_modules'}
    files = [path for path in root.rglob('*.go')
             if not (set(path.relative_to(root).parts) & skip)]
    files += [root / 'go.mod', root / 'go.sum']
    files = [path for path in files if path.is_file()]
    if entry == 'gui':
        frontend = root / 'cmd/piwork-launcher/frontend'
        required = ['cmd/piwork-launcher/frontend/assets/piwork-logo.png',
                    'cmd/piwork-launcher/frontend/index.html',
                    'cmd/piwork-launcher/ui-sources.json',
                    'tools/gui-resources/main.go',
                    'scripts/gui-build.py', 'scripts/gui-build-windows.ps1']
        for relative in required:
            if not (root / relative).is_file():
                raise SystemExit(f'missing GUI body input: {relative}')
        files += [path for path in frontend.rglob('*') if path.is_file()]
        files += [root / relative for relative in required]
    digest = hashlib.sha256()
    for path in sorted(set(files), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode() + b'\0' + sha(path).encode() + b'\n')
    return digest.hexdigest()


def body_record_path(entry, platform):
    return ROOT / 'dist/build-bodies' / (entry + '-' + platform + '.json')


def write_body_record(entry, platform, body, identity):
    """Bind a built launcher body to its version, upstream identity and inputs."""
    body = pathlib.Path(body)
    lock = json.loads((ROOT / 'build.lock.json').read_text())
    release = lock['piwork'].get('release') or {}
    record = {'recordVersion': 1, 'entry': entry, 'platform': platform, 'arch': 'amd64',
              'version': identity['version'], 'manifest': identity['manifest'],
              'sourceCommit': git('rev-parse', 'HEAD'),
              'sourceFingerprint': source_fingerprint(entry=entry),
              'upstream': {'mode': built_input_mode(), 'version': identity['upstream'],
                           'buildCommit': identity['commit'],
                           'releaseCommit': release.get('releaseCommit')},
              'inputFingerprint': input_fingerprint(lock),
              'body': {'path': body.name, 'size': body.stat().st_size, 'sha256': sha(body)}}
    target = body_record_path(entry, platform)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + '\n')
    return record


def verify_body_record(entry, platform, body, identity):
    """Reject stale, foreign or unrecorded bodies before packaging them."""
    target = body_record_path(entry, platform)
    if not target.is_file():
        raise SystemExit(f'missing build record for {entry}/{platform}; rebuild the body')
    record = json.loads(target.read_text(encoding='utf-8-sig'))
    if (record.get('entry'), record.get('platform'), record.get('arch')) != (entry, platform, 'amd64'):
        raise SystemExit(f'build record does not belong to {entry}/{platform}')
    for field in ('version', 'manifest'):
        if record.get(field) != identity[field]:
            raise SystemExit(f'{entry}/{platform} body was built with {field} '
                             f'{record.get(field)!r}, expected {identity[field]!r}')
    upstream = record.get('upstream') or {}
    lock = json.loads((ROOT / 'build.lock.json').read_text())
    release = lock['piwork'].get('release') or {}
    expected_upstream = {'mode': built_input_mode(), 'version': identity['upstream'],
                         'buildCommit': identity['commit'],
                         'releaseCommit': release.get('releaseCommit')}
    if upstream != expected_upstream:
        raise SystemExit(f'{entry}/{platform} body upstream identity does not match the lock')
    if record.get('inputFingerprint') != input_fingerprint(lock):
        raise SystemExit(f'{entry}/{platform} body was built from other locked inputs')
    if record.get('sourceFingerprint') != source_fingerprint(entry=entry):
        raise SystemExit(f'{entry}/{platform} body was built from other Go sources or body inputs; rebuild the body')
    body = pathlib.Path(body)
    digest = record.get('body') or {}
    if (digest.get('size'), digest.get('sha256')) != (body.stat().st_size, sha(body)):
        raise SystemExit(f'{entry}/{platform} body bytes differ from its build record')
    return record


def build_identity(out, manifest_version):
    """Own version, upstream pin and bundle manifest version reported by --version.

    PIWORK_RELEASE_VERSION lets a release build state its version before the tag
    exists, so the artifact never ships a development version under a release tag.
    """
    explicit = os.environ.get('PIWORK_RELEASE_VERSION', '').strip()
    return {'version': explicit or release_version() or '0.0.0-dev.' + (git('rev-parse', '--short=12', 'HEAD') or 'unknown'),
            'upstream': json.loads((out / 'piwork/metadata.json').read_text())['releaseVersion'],
            'commit': json.loads((ROOT / 'build.lock.json').read_text())['piwork']['commit'],
            'manifest': 'v' + str(manifest_version)}


def version_ldflags(identity):
    prefix = 'piwork-microvm/internal/launcher.'
    fields = [('buildVersion', identity['version']), ('buildUpstreamVersion', identity['upstream']),
              ('buildUpstreamCommit', identity['commit']), ('buildManifestVersion', identity['manifest'])]
    return ' '.join('-X ' + prefix + name + '=' + value for name, value in fields)


def artifact_names(entry, platform):
    """Return every per-entry file name so CLI and GUI builds cannot overwrite each other."""
    suffix = '.exe' if platform == 'windows' else ''
    if entry == 'gui':
        return {'body': f'launcher-gui-{platform}{suffix}',
                'payload': f'payload-gui-{platform}.tar.gz',
                'manifest': f'bundle-manifest-gui-{platform}.json',
                'artifact': f'piwork-microvm-gui{suffix}',
                'sha256': f'piwork-microvm-gui{suffix}.sha256'}
    if entry == 'cli':
        return {'body': f'launcher-{platform}{suffix}',
                'payload': f'payload-{platform}.tar.gz',
                'manifest': f'bundle-manifest-{platform}.json',
                'artifact': f'piwork-microvm{suffix}',
                'sha256': f'piwork-microvm{suffix}.sha256'}
    raise ValueError(f'unsupported entry: {entry}')


def trailer(payload_size, manifest_raw):
    """Build the fixed 64-byte trailer read by internal/bundle."""
    return (MAGIC
            + struct.pack('<QQ', payload_size, len(manifest_raw))
            + hashlib.sha256(manifest_raw).digest())


def read_trailer(path):
    """Read and verify the appended manifest for tests and build checks."""
    path = pathlib.Path(path)
    size = path.stat().st_size
    if size < TRAILER_SIZE:
        raise ValueError('file is smaller than the bundle trailer')
    with path.open('rb') as f:
        f.seek(size - TRAILER_SIZE)
        t = f.read(TRAILER_SIZE)
        if t[:16] != MAGIC:
            raise ValueError('bundle trailer magic is invalid')
        length, mlen = struct.unpack('<QQ', t[16:32])
        if length == 0 or mlen == 0 or length + mlen + TRAILER_SIZE > size:
            raise ValueError('bundle trailer lengths are invalid')
        f.seek(size - TRAILER_SIZE - mlen)
        raw = f.read(mlen)
        if hashlib.sha256(raw).digest() != t[32:]:
            raise ValueError('bundle manifest checksum mismatch')
        return {'offset': size - TRAILER_SIZE - mlen - length,
                'length': length,
                'manifest_length': mlen,
                'manifest': json.loads(raw)}


def body_magic_ok(path, platform):
    """Reject an obviously wrong body before appending a platform payload."""
    with path.open('rb') as f:
        head = f.read(4)
    if platform == 'linux':
        return head == b'\x7fELF'
    return head[:2] == b'MZ'


def append_bundle(body, payload, manifest_raw, target):
    """Write body + payload + manifest + trailer atomically and verify it."""
    target = pathlib.Path(target)
    part = target.with_name(target.name + '.part')
    with part.open('wb') as f:
        for p in [body, payload]:
            with p.open('rb') as source:
                shutil.copyfileobj(source, f, 1024 * 1024)
        f.write(manifest_raw)
        f.write(trailer(payload.stat().st_size, manifest_raw))
        f.flush()
        os.fsync(f.fileno())
    part.chmod(0o755)
    os.replace(part, target)
    check = read_trailer(target)
    if check['length'] != payload.stat().st_size:
        raise SystemExit('appended payload length does not match')
    return check


def module_license(directory):
    for name in ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING', 'COPYING.md', 'NOTICE']:
        p = pathlib.Path(directory) / name
        if p.is_file():
            return p
    return None


def gui_licenses():
    """Collect readable license texts for the Wails module graph.

    The index records a missing text instead of dropping the package, so a
    shipped GUI always says which third-party components it contains.
    """
    raw = subprocess.check_output(['go', 'list', '-m', '-json', 'all'], text=True)
    decoder = json.JSONDecoder()
    modules, offset = [], 0
    while offset < len(raw):
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset >= len(raw):
            break
        value, offset = decoder.raw_decode(raw, offset)
        modules.append(value)
    files, index = {}, []
    for module in sorted(modules, key=lambda m: m.get('Path', '')):
        path = module.get('Path', '')
        if module.get('Main') or not path:
            continue
        directory = module.get('Dir', '')
        slug = path.replace('/', '_').replace('@', '_')
        found = module_license(directory) if directory else None
        if found:
            files[f'provenance/gui-licenses/{slug}-LICENSE'] = found
            index.append({'module': path, 'version': module.get('Version', ''), 'license': f'{slug}-LICENSE'})
        else:
            index.append({'module': path, 'version': module.get('Version', ''), 'license': None})
    return files, index


def collect_inputs(entry, platform, out):
    """Collect immutable resources, provenance and licenses shared by both entries."""
    qemu_dir = out / ('qemu-windows' if platform == 'windows' else 'qemu')
    inputs = {}
    for name in ['kernel', 'kernel.config', 'initramfs', 'rootfs.ext4', 'state.qcow2', 'qemu-data/qboot.rom', 'qemu-data/linuxboot.bin', 'qemu-data/linuxboot_dma.bin']:
        inputs['guest/' + name] = out / 'guest' / name
    for p in qemu_dir.rglob('*'):
        if p.is_file():
            inputs['qemu/' + p.relative_to(qemu_dir).as_posix()] = p
    provenance = {'build.lock.json': ROOT / 'build.lock.json',
                  'piwork-metadata.json': out / 'piwork/metadata.json',
                  'piwork-images.json': out / 'piwork/images.json',
                  'kernel.COPYING': out / 'kernel/pristine' / ('linux-' + json.loads((ROOT / 'build.lock.json').read_text())['linux']['version']) / 'COPYING',
                  'kernel.GPL-2.0': out / 'kernel/pristine' / ('linux-' + json.loads((ROOT / 'build.lock.json').read_text())['linux']['version']) / 'LICENSES/preferred/GPL-2.0',
                  'guest-firmware.json': out / 'guest/firmware.json'}
    source_json = source_path().parent / 'source.json'
    if source_json.is_file():
        provenance['piwork-source.json'] = source_json
    if built_input_mode(out) == 'official-release':
        # The official input, its program/image identity and readable license
        # texts travel with every artifact; no source checkout is required.
        provenance['piwork-import.json'] = out / 'piwork/import.json'
        upstream = out / 'piwork/upstream-release'
        if not upstream.is_dir():
            raise SystemExit('missing official import tree; run make piwork first')
        for p in upstream.rglob('*'):
            if p.is_file():
                inputs['provenance/piwork-upstream/' + p.relative_to(upstream).as_posix()] = p
    else:
        provenance['piwork.LICENSE'] = source_path() / 'LICENSE'
    if platform == 'windows':
        for p in sorted((ROOT / 'guest/qemu').glob('*.patch')):
            provenance['qemu-' + p.name] = p
        provenance['windows-toolchain.lock.json'] = ROOT / 'guest/qemu/windows-toolchain.lock.json'
    for name, p in provenance.items():
        inputs['provenance/' + name] = p
    guest_licenses = out / 'guest/guest-licenses'
    if not guest_licenses.is_dir():
        raise SystemExit('missing guest license tree; run make guest first')
    for p in guest_licenses.rglob('*'):
        if p.is_file():
            inputs['provenance/guest-licenses/' + p.relative_to(guest_licenses).as_posix()] = p
    goroot = pathlib.Path(subprocess.check_output(['go', 'env', 'GOROOT'], text=True).strip())
    inputs['provenance/licenses/Go-LICENSE'] = goroot / 'LICENSE'
    modules = json.loads(subprocess.check_output(['go', 'list', '-m', '-json', 'golang.org/x/sys'], text=True))
    inputs['provenance/licenses/x-sys-LICENSE'] = pathlib.Path(modules['Dir']) / 'LICENSE'
    if platform == 'windows':
        modules = json.loads(subprocess.check_output(['go', 'list', '-m', '-json', 'github.com/Microsoft/go-winio'], text=True))
        inputs['provenance/licenses/go-winio-LICENSE'] = pathlib.Path(modules['Dir']) / 'LICENSE'
    if entry == 'gui':
        extra, index = gui_licenses()
        inputs.update(extra)
        inputs['provenance/gui-licenses/INDEX.json'] = ('inline', json.dumps(index, indent=2, sort_keys=True).encode())
        ui = ROOT / 'cmd/piwork-launcher/ui-sources.json'
        if not ui.is_file():
            raise SystemExit('missing GUI UI source record')
        inputs['provenance/piwork-ui-sources.json'] = ui
    return inputs


def write_payload(inputs, payload):
    records = []
    payload.parent.mkdir(parents=True, exist_ok=True)
    print('Compressing immutable Guest/QEMU resources...', flush=True)
    with payload.open('wb') as f, gzip.GzipFile(fileobj=f, mode='wb', filename='', mtime=0, compresslevel=3) as g, tarfile.open(fileobj=g, mode='w|', format=tarfile.PAX_FORMAT) as tar:
        for name, source in sorted(inputs.items()):
            if isinstance(source, tuple) and source[0] == 'inline':
                data = source[1]
                digest = hashlib.sha256(data).hexdigest()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o444
                info.mtime = 0
                info.uid = info.gid = 0
                records.append({'path': name, 'size': len(data), 'mode': 0o444, 'sha256': digest})
                import io
                tar.addfile(info, io.BytesIO(data))
                continue
            p = pathlib.Path(source)
            if not p.is_file():
                raise SystemExit(f'missing payload input: {p}')
            executable = name in ['qemu/qemu-system-x86_64', 'qemu/ld-linux-x86-64.so.2']
            mode = 0o555 if executable else 0o444
            record = {'path': name, 'size': p.stat().st_size, 'mode': mode, 'sha256': sha(p)}
            records.append(record)
            info = tarfile.TarInfo(name)
            info.size = record['size']
            info.mode = mode
            info.mtime = 0
            info.uid = info.gid = 0
            with p.open('rb') as source_file:
                tar.addfile(info, source_file)
    return records


def build_cli_body(out, platform, identity, body_name):
    env = os.environ.copy()
    env.update(CGO_ENABLED='0', GOTOOLCHAIN='local', GOOS=platform, GOARCH='amd64')
    launcher = out / body_name
    subprocess.run(['go', 'build', '-trimpath', '-ldflags=-s -w ' + version_ldflags(identity),
                    '-o', launcher, './cmd/piwork-microvm'], check=True, env=env)
    return launcher


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--platform', choices=['linux', 'windows'], default='linux')
    p.add_argument('--entry', choices=['cli', 'gui'], default='cli')
    p.add_argument('--body', help='prebuilt GUI body (dist/launcher-gui-<platform>)')
    a = p.parse_args()
    os.chdir(ROOT)
    out = ROOT / 'dist'
    if built_input_mode(out) == 'official-release':
        piwork_release.check_prepared()
    else:
        verify(source_path())
    names = artifact_names(a.entry, a.platform)

    if a.entry == 'cli':
        inputs = collect_inputs(a.entry, a.platform, out)
        payload = out / names['payload']
        records = write_payload(inputs, payload)
        manifest = {'version': 2, 'os': a.platform, 'arch': 'amd64', 'payloadSha256': sha(payload), 'files': records}
        manifest_raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        (out / names['manifest']).write_bytes(manifest_raw + b'\n')
        identity = build_identity(out, manifest['version'])
        body = build_cli_body(out, a.platform, identity, names['body'])
        write_body_record('cli', a.platform, body, identity)
    else:
        body = pathlib.Path(a.body) if a.body else out / names['body']
        if not body.is_file():
            raise SystemExit(f'GUI body not found: {body}; run scripts/gui-build.py first')
        if not body_magic_ok(body, a.platform):
            raise SystemExit(f'GUI body does not match platform {a.platform}: {body}')
        identity = build_identity(out, 2)
        verify_body_record('gui', a.platform, body, identity)
        inputs = collect_inputs(a.entry, a.platform, out)
        payload = out / names['payload']
        records = write_payload(inputs, payload)
        manifest = {'version': 2, 'os': a.platform, 'arch': 'amd64', 'payloadSha256': sha(payload), 'files': records}
        manifest_raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        (out / names['manifest']).write_bytes(manifest_raw + b'\n')

    artifact = out / names['artifact']
    append_bundle(body, payload, manifest_raw, artifact)
    digest = sha(artifact)
    (out / names['sha256']).write_text(digest + '  ' + names['artifact'] + '\n')
    print(a.entry, a.platform + ':', artifact, 'bytes:', artifact.stat().st_size, 'SHA256:', digest, 'version:', identity['version'])


if __name__ == '__main__':
    main()
