#!/usr/bin/env python3
"""Prepare the locked, patched libslirp source for each QEMU platform."""
import argparse
import configparser
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def digest(path):
    with pathlib.Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_patches(config, root=ROOT):
    result = []
    for item in config['patches']:
        path = pathlib.Path(root) / item['file']
        if not path.is_file() or digest(path) != item['sha256']:
            raise ValueError('libslirp patch checksum mismatch: ' + str(path))
        result.append(path.resolve())
    if not result:
        raise ValueError('libslirp patch list is empty')
    return result


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def prepare_windows(qemu_source, config, root=ROOT):
    qemu_source = pathlib.Path(qemu_source)
    wrap = configparser.ConfigParser()
    if not wrap.read(qemu_source / 'subprojects/slirp.wrap'):
        raise ValueError('missing QEMU libslirp wrap')
    if (wrap['wrap-git']['url'], wrap['wrap-git']['revision']) != (config['url'], config['revision']):
        raise ValueError('libslirp lock differs from QEMU wrap')
    source = qemu_source / 'subprojects/slirp'
    if run('git', 'rev-parse', 'HEAD', cwd=source) != config['revision']:
        raise ValueError('libslirp checkout revision differs from lock')
    patches = checked_patches(config, root)
    # Compute the precise expected file independently of the working tree.
    # A reverse-apply check alone would accept unrelated edits in the same file.
    original = subprocess.check_output(['git', 'show', 'HEAD:src/socket.c'], cwd=source)
    with tempfile.TemporaryDirectory(prefix='piwork-slirp-check-') as tmp:
        temp = pathlib.Path(tmp)
        (temp / 'src').mkdir()
        (temp / 'src/socket.c').write_bytes(original)
        for patch in patches:
            run('git', 'apply', '--check', str(patch), cwd=temp)
            run('git', 'apply', str(patch), cwd=temp)
        expected = (temp / 'src/socket.c').read_bytes()
    status = run('git', 'status', '--porcelain', '--untracked-files=all', cwd=source)
    if not status:
        for patch in patches:
            run('git', 'apply', '--check', str(patch), cwd=source)
            run('git', 'apply', str(patch), cwd=source)
        status = run('git', 'status', '--porcelain', '--untracked-files=all', cwd=source)
    if status != 'M src/socket.c' or (source / 'src/socket.c').read_bytes() != expected:
        raise ValueError('libslirp checkout has unexpected modifications')
    return source


def tree_digest(root):
    root = pathlib.Path(root)
    h = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if relative == '.piwork-source.json':
            continue
        if path.is_symlink():
            h.update(('L ' + relative + '\0' + os.readlink(path) + '\n').encode())
        elif path.is_file():
            h.update(('F ' + relative + '\0' + digest(path) + '\n').encode())
    return h.hexdigest()


def fetch_locked(config, downloads):
    downloads = pathlib.Path(downloads)
    downloads.mkdir(parents=True, exist_ok=True)
    for item in config['files']:
        name = item['file']
        if pathlib.PurePath(name).name != name:
            raise ValueError('invalid libslirp source filename')
        path = downloads / name
        if not path.exists():
            partial = path.with_suffix(path.suffix + '.part')
            try:
                with urllib.request.urlopen(config['sourceBase'] + name, timeout=60) as response, partial.open('wb') as out:
                    shutil.copyfileobj(response, out)
                if digest(partial) != item['sha256']:
                    raise ValueError('libslirp source checksum mismatch: ' + name)
                os.replace(partial, path)
            finally:
                partial.unlink(missing_ok=True)
        if not path.is_file() or digest(path) != item['sha256']:
            raise ValueError('libslirp source checksum mismatch: ' + name)
    return downloads


def prepare_linux(config, root=ROOT):
    root = pathlib.Path(root)
    patches = checked_patches(config, root)
    downloads = fetch_locked(config, root / 'dist/downloads/libslirp')
    parent = root / 'dist/qemu-source'
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / 'linux-libslirp'
    if destination.exists():
        marker = destination / '.piwork-source.json'
        if not marker.is_file():
            raise ValueError('existing Linux libslirp source has no verified identity')
        old = json.loads(marker.read_text())
        if old.get('treeSha256') != tree_digest(destination):
            raise ValueError('existing Linux libslirp source has unexpected modifications')
        if (old.get('format') == 2 and old.get('input') == config and
                b'listen(s, (flags & SS_HOSTFWD) ? 128 : 1)' in (destination / 'src/socket.c').read_bytes()):
            return destination
    with tempfile.TemporaryDirectory(prefix='libslirp-', dir=parent) as tmp:
        extracted = pathlib.Path(tmp) / 'source'
        dsc = next((downloads / item['file'] for item in config['files'] if item['file'].endswith('.dsc')), None)
        if dsc is None:
            raise ValueError('missing locked Debian source descriptor')
        run('dpkg-source', '-x', str(dsc), str(extracted))
        before = (extracted / 'src/socket.c').read_bytes()
        for patch in patches:
            # This generated directory sits under our Git worktree. `git apply`
            # silently skips paths outside its current worktree prefix there.
            run('patch', '--dry-run', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch), cwd=extracted)
            run('patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch), cwd=extracted)
        after = (extracted / 'src/socket.c').read_bytes()
        if before == after or b'listen(s, (flags & SS_HOSTFWD) ? 128 : 1)' not in after:
            raise ValueError('Linux libslirp forwarding patch did not change the listener')
        (extracted / '.piwork-source.json').write_text(json.dumps({'format': 2, 'input': config, 'treeSha256': tree_digest(extracted)}, indent=2) + '\n')
        if destination.exists():
            shutil.rmtree(destination)  # Only our previously verified generated source.
        os.replace(extracted, destination)
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('platform', choices=['windows', 'linux'])
    parser.add_argument('--qemu-source', type=pathlib.Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'build.lock.json').read_text())['qemu']['libslirp']
    try:
        if args.platform == 'windows':
            if args.qemu_source is None:
                parser.error('--qemu-source is required for Windows')
            source = prepare_windows(args.qemu_source, lock['windows'])
        else:
            source = prepare_linux(lock['linux'])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit('libslirp source preparation failed: ' + str(error)) from error
    print(source)


if __name__ == '__main__':
    main()
