#!/usr/bin/env python3
"""Append a deterministic gzip/tar payload and checked index to the Go entry.

The CLI entry remains the default. The GUI entry uses a separately built Wails
body and separate payload/manifest/artifact names so it never replaces CLI files.
"""
import argparse, gzip, hashlib, json, os, pathlib, shutil, struct, subprocess, tarfile
from source import source_path, verify

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
                  'piwork-source.json': source_path().parent / 'source.json',
                  'piwork-metadata.json': out / 'piwork/metadata.json',
                  'piwork-images.json': out / 'piwork/images.json',
                  'piwork.LICENSE': source_path() / 'LICENSE',
                  'kernel.COPYING': out / 'kernel/pristine' / ('linux-' + json.loads((ROOT / 'build.lock.json').read_text())['linux']['version']) / 'COPYING',
                  'kernel.GPL-2.0': out / 'kernel/pristine' / ('linux-' + json.loads((ROOT / 'build.lock.json').read_text())['linux']['version']) / 'LICENSES/preferred/GPL-2.0',
                  'guest-firmware.json': out / 'guest/firmware.json'}
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
    else:
        body = pathlib.Path(a.body) if a.body else out / names['body']
        if not body.is_file():
            raise SystemExit(f'GUI body not found: {body}; run scripts/gui-build.py first')
        if not body_magic_ok(body, a.platform):
            raise SystemExit(f'GUI body does not match platform {a.platform}: {body}')
        inputs = collect_inputs(a.entry, a.platform, out)
        payload = out / names['payload']
        records = write_payload(inputs, payload)
        manifest = {'version': 2, 'os': a.platform, 'arch': 'amd64', 'payloadSha256': sha(payload), 'files': records}
        manifest_raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        (out / names['manifest']).write_bytes(manifest_raw + b'\n')
        identity = build_identity(out, manifest['version'])

    artifact = out / names['artifact']
    append_bundle(body, payload, manifest_raw, artifact)
    digest = sha(artifact)
    (out / names['sha256']).write_text(digest + '  ' + names['artifact'] + '\n')
    print(a.entry, a.platform + ':', artifact, 'bytes:', artifact.stat().st_size, 'SHA256:', digest, 'version:', identity['version'])


if __name__ == '__main__':
    main()
