#!/usr/bin/env python3
"""Verify and record reusable Kernel, QEMU and Guest build components.

A component is reused only when its own inputs are unchanged and every declared
output exists with the recorded size and digest. The record lives under the
ignored dist/ tree; a missing or incomplete record never counts as a hit.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
KINDS = ('kernel', 'qemu', 'qemu-windows', 'guest')
HIT, MISS = 0, 4

KERNEL_OUTPUTS = ('guest/kernel', 'guest/kernel.config')
GUEST_OUTPUTS = ('guest/rootfs.ext4', 'guest/initramfs', 'guest/state.qcow2',
                 'guest/qemu-data', 'guest/firmware.json', 'guest/guest-licenses')


class ComponentError(Exception):
    pass


def sha256_file(path):
    with pathlib.Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def file_identity(path):
    path = pathlib.Path(path)
    if not path.is_file():
        return None
    return {'sha256': sha256_file(path), 'size': path.stat().st_size}


def tree_identity(root, prefix=''):
    """Every regular file under one root, with path, size and digest."""
    root = pathlib.Path(root)
    records = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            key = prefix + path.relative_to(root).as_posix()
            records[key] = {'sha256': sha256_file(path), 'size': path.stat().st_size}
    return records


def hash_paths(paths, root=ROOT):
    records = {}
    for relative in paths:
        records[relative] = file_identity(pathlib.Path(root) / relative)
    return records


def output_identity(paths, root=ROOT):
    records = {}
    for relative in paths:
        target = pathlib.Path(root) / 'dist' / relative
        if target.is_dir():
            for key, value in tree_identity(target).items():
                records[relative + '/' + key] = value
        elif target.is_file():
            records[relative] = {'sha256': sha256_file(target), 'size': target.stat().st_size}
        else:
            records[relative] = None
    return records


def docker_image_id(name, runner=subprocess.run):
    result = runner(['docker', 'image', 'inspect', '--format', '{{.Id}}', name],
                    capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def piwork_identity(root=ROOT):
    """The application/image identity consumed by Guest assembly."""
    out = pathlib.Path(root) / 'dist/piwork'
    records = {}
    for name in ('bin/piwork-core', 'bin/piwork-cli', 'metadata.json', 'images.json'):
        records[name] = file_identity(out / name)
    records['guest/images.tar'] = file_identity(pathlib.Path(root) / 'dist/guest/images.tar')
    return records


def guest_source_identity(root=ROOT, runner=subprocess.run):
    """Hash only the packages the Guest agent actually imports."""
    root = pathlib.Path(root)
    listed = runner(['go', 'list', '-deps', '-f', '{{.Dir}}', './cmd/piwork-guest'],
                    cwd=root, capture_output=True, text=True)
    paths = set()
    if listed.returncode == 0:
        for line in listed.stdout.splitlines():
            directory = pathlib.Path(line.strip())
            try:
                directory.relative_to(root)
            except ValueError:
                continue
            if directory.is_dir():
                paths.update(path for path in directory.rglob('*.go'))
    else:
        # Without a usable Go toolchain, fall back to the conservative tree hash.
        for base in (root / 'cmd/piwork-guest', root / 'internal'):
            paths.update(base.rglob('*.go'))
    records = {}
    for path in sorted(paths):
        if path.is_file():
            records[path.relative_to(root).as_posix()] = file_identity(path)
    for name in ('go.mod', 'go.sum'):
        records[name] = file_identity(root / name)
    return records


def fingerprint(kind, lock, root=ROOT, runner=subprocess.run):
    """Inputs actually used by one component; unrelated lock entries stay out."""
    if kind == 'kernel':
        return {
            'kind': kind,
            'linux': lock['linux'],
            'system': {'dockerImage': lock['dockerImage'],
                       'guestBaseImage': lock['guestBaseImage'],
                       'debianSnapshot': lock['debianSnapshot']},
            'recipe': hash_paths(['scripts/kernel.sh', 'guest/Dockerfile.build'], root),
            'config': hash_paths(['guest/kernel/config.fragment'], root),
            'builderImage': docker_image_id('piwork-microvm-builder:local', runner=runner),
        }
    if kind == 'qemu':
        return {
            'kind': kind,
            'qemu': {'version': lock['qemu']['version'], 'url': lock['qemu']['url'],
                     'sha256': lock['qemu']['sha256']},
            'system': {'dockerImage': lock['dockerImage']},
            'recipe': hash_paths(['scripts/qemu.sh', 'scripts/qemu-bundle.py',
                                  'guest/Dockerfile.build', 'guest/qemu/Dockerfile'], root),
            'builderImage': docker_image_id('piwork-microvm-qemu-builder:local', runner=runner),
        }
    if kind == 'qemu-windows':
        return {
            'kind': kind,
            'qemu': {'version': lock['qemu']['version'], 'url': lock['qemu']['url'],
                     'sha256': lock['qemu']['sha256']},
            'patches': [{'file': patch['file'],
                         'sha256': file_identity(pathlib.Path(root) / patch['file'])['sha256']}
                        for patch in lock['qemu']['windowsPatches']],
            'toolchain': {'lock': lock['qemu']['windowsToolchain'],
                          'manifest': file_identity(pathlib.Path(root) /
                                                    lock['qemu']['windowsToolchain']['manifest'])},
            'recipe': hash_paths(['scripts/qemu-windows.sh', 'scripts/qemu-windows-bundle.py',
                                  'scripts/windows-toolchain.py',
                                  'guest/qemu/Dockerfile.windows'], root),
            'builderImage': docker_image_id('piwork-microvm-qemu-windows-builder:local',
                                            runner=runner),
        }
    if kind == 'guest':
        return {
            'kind': kind,
            'piwork': piwork_identity(root),
            'agent': guest_source_identity(root, runner=runner),
            'system': {'dockerImage': lock['dockerImage'],
                       'guestBaseImage': lock['guestBaseImage'],
                       'debianSnapshot': lock['debianSnapshot'],
                       'dockerVersion': lock['dockerVersion'],
                       'go': lock['go'],
                       'qemu': {'version': lock['qemu']['version'],
                                'url': lock['qemu']['url'],
                                'sha256': lock['qemu']['sha256']},
                       'qboot': lock['qboot']},
            'recipe': hash_paths(['scripts/rootfs.py', 'scripts/rootfs-assemble.sh',
                                  'scripts/guest-licenses.py', 'guest/rootfs/Dockerfile',
                                  'guest/initramfs/init'], root),
            'rootfsFiles': tree_identity(pathlib.Path(root) / 'guest/rootfs/files'),
        }
    raise ComponentError('unknown component: ' + kind)


def outputs_for(kind, root=ROOT):
    if kind == 'kernel':
        return output_identity(KERNEL_OUTPUTS, root)
    if kind == 'qemu':
        return tree_identity(pathlib.Path(root) / 'dist/qemu', 'qemu/')
    if kind == 'qemu-windows':
        return tree_identity(pathlib.Path(root) / 'dist/qemu-windows', 'qemu-windows/')
    if kind == 'guest':
        return output_identity(GUEST_OUTPUTS, root)
    raise ComponentError('unknown component: ' + kind)


def record_path(kind, root=ROOT):
    return pathlib.Path(root) / 'dist/build-current' / (kind + '.json')


def write_record(kind, lock, root=ROOT, runner=subprocess.run):
    outputs = outputs_for(kind, root)
    if not outputs or any(value is None for value in outputs.values()):
        raise ComponentError('%s has no complete output set to record' % kind)
    record = {'recordVersion': 1, 'kind': kind,
              'fingerprint': fingerprint(kind, lock, root, runner=runner),
              'outputs': outputs,
              'recordedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    target = record_path(kind, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=kind + '.', suffix='.part', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps(record, indent=2) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        pathlib.Path(temp).unlink(missing_ok=True)
    return record


def read_record(kind, root=ROOT):
    target = record_path(kind, root)
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text())
    except json.JSONDecodeError as err:
        raise ComponentError('cannot parse component record %s: %s' % (target, err))


def verify(kind, lock, root=ROOT, runner=subprocess.run, force=False):
    """Return (hit, reason). Corruption or missing outputs always means a miss."""
    if force:
        return False, 'full rebuild requested'
    record = read_record(kind, root)
    if record is None:
        return False, 'no component record'
    if record.get('kind') != kind:
        return False, 'component record belongs to another kind'
    current = fingerprint(kind, lock, root, runner=runner)
    if record.get('fingerprint') != current:
        return False, 'component inputs changed'
    recorded = record.get('outputs') or {}
    if not recorded:
        return False, 'component record declares no outputs'
    current = outputs_for(kind, root)
    if set(recorded) != set(current):
        missing = sorted(set(current) - set(recorded))
        extra = sorted(set(recorded) - set(current))
        return False, 'component output set changed (missing %s, extra %s)' % (missing[:3], extra[:3])
    for relative, expected in current.items():
        if expected is None:
            return False, 'declared output is absent now: ' + relative
        saved = recorded.get(relative) or {}
        if (saved.get('size'), saved.get('sha256')) != (expected['size'], expected['sha256']):
            return False, 'output size or digest differs: ' + relative
    return True, 'inputs and %d outputs verified' % len(recorded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check', help='exit 0 on a verified hit, 4 when a rebuild is needed')
    check.add_argument('--kind', required=True, choices=KINDS)
    check.add_argument('--force', action='store_true')
    check.add_argument('--root', default=str(ROOT))
    record = sub.add_parser('record', help='record inputs and output digests after a build')
    record.add_argument('--kind', required=True, choices=KINDS)
    record.add_argument('--root', default=str(ROOT))
    args = parser.parse_args()
    root = pathlib.Path(args.root)
    lock = json.loads((root / 'build.lock.json').read_text())
    started = time.monotonic()
    try:
        if args.command == 'check':
            hit, reason = verify(args.kind, lock, root=root, force=args.force)
            elapsed = time.monotonic() - started
            print('component %s: %s (%.2fs) - %s'
                  % (args.kind, 'HIT' if hit else 'MISS', elapsed, reason))
            sys.exit(HIT if hit else MISS)
        record_value = write_record(args.kind, lock, root=root)
        elapsed = time.monotonic() - started
        print('component %s: recorded %d outputs (%.2fs)'
              % (args.kind, len(record_value['outputs']), elapsed))
    except ComponentError as err:
        print('components: ' + str(err), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
