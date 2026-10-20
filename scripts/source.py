#!/usr/bin/env python3
"""Checkout the declared revision, never copy a caller's dirty working tree."""
import argparse, datetime, json, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'build.lock.json').read_text())

def source_path():
    return ROOT/'dist/source'/LOCK['piwork']['commit']/'piwork'

def verify(dest):
    if run('git', 'rev-parse', 'HEAD', cwd=dest) != LOCK['piwork']['commit']:
        raise SystemExit('Source HEAD differs from build.lock.json; choose a fresh output directory.')
    if run('git', 'status', '--porcelain', '--untracked-files=all', cwd=dest):
        raise SystemExit('Refusing modified Piwork source; no patches or untracked inputs are allowed.')
    if run('git', 'config', '--local', '--get', 'remote.origin.url', cwd=dest) != LOCK['piwork']['url']:
        raise SystemExit('Unexpected Piwork source origin.')
    return {'repository': LOCK['piwork']['url'], 'commit': LOCK['piwork']['commit'],
            'tree': run('git', 'rev-parse', 'HEAD^{tree}', cwd=dest),
            'resolvedAt': LOCK['piwork']['resolvedAt'], 'branch': LOCK['piwork']['branch'],
            'modified': False, 'patches': []}

def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', default=LOCK['piwork']['url'], help='optional clone mirror; official origin is retained')
    p.add_argument('--output', type=pathlib.Path)
    p.add_argument('--refresh-lock', action='store_true', help='explicitly resolve latest official default HEAD')
    p.add_argument('--check', action='store_true', help='verify existing input without fetching or writing')
    a = p.parse_args()
    if a.refresh_lock:
        if a.check:
            p.error('--check and --refresh-lock are mutually exclusive')
        remote = run('git', 'ls-remote', '--symref', LOCK['piwork']['url'], 'HEAD')
        branch = re.search(r'^ref: refs/heads/(.+)\s+HEAD$', remote, re.M)
        head = re.search(r'^([0-9a-f]{40})\s+HEAD$', remote, re.M)
        if not branch or not head:
            raise SystemExit('Cannot resolve the official default branch and full HEAD.')
        LOCK['piwork'].update(commit=head[1], branch=branch[1],
            resolvedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
        (ROOT/'build.lock.json').write_text(json.dumps(LOCK, indent=2)+'\n')
    dest = (a.output or source_path()).resolve()
    if a.check:
        print(json.dumps(verify(dest)))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    (ROOT/'dist/go.mod').write_text('module piwork-microvm-build-artifacts\n')
    revision = LOCK['piwork']['commit']
    if not (dest/'.git').exists():
        subprocess.run(['git', 'clone', '--no-checkout', '--', a.source, str(dest)], check=True)
        subprocess.run(['git', 'checkout', '--detach', revision], cwd=dest, check=True)
        subprocess.run(['git', 'remote', 'set-url', 'origin', LOCK['piwork']['url']], cwd=dest, check=True)
    metadata = verify(dest)
    (dest.parent/'source.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps(metadata))

if __name__ == '__main__':
    main()
