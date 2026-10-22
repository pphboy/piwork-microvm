#!/usr/bin/env python3
"""Checkout the declared revision, never copy a caller's dirty working tree."""
import argparse, datetime, json, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'build.lock.json').read_text())
INPUT_MODES = ('source', 'official-release')


class LockError(ValueError):
    """The build lock declares an unusable or contradictory input."""


def input_mode(lock=LOCK):
    """Return the selected Piwork input mode; pre-mode locks stay on source builds."""
    value = lock.get('piwork', {}).get('inputMode', 'source')
    if value not in INPUT_MODES:
        raise LockError('unknown piwork.inputMode %r; expected one of %s'
                        % (value, ', '.join(INPUT_MODES)))
    return value


def official_release(lock=LOCK):
    """Return the locked official release record, or fail when the mode is not selected."""
    if input_mode(lock) != 'official-release':
        raise LockError('piwork.release is only available with inputMode official-release')
    release = lock.get('piwork', {}).get('release')
    if not isinstance(release, dict):
        raise LockError('official-release input requires a piwork.release record')
    return release


def source_path(lock=LOCK):
    return ROOT / 'dist/source' / lock['piwork']['commit'] / 'piwork'


def verify(dest, lock=LOCK):
    if run('git', 'rev-parse', 'HEAD', cwd=dest) != lock['piwork']['commit']:
        raise SystemExit('Source HEAD differs from build.lock.json; choose a fresh output directory.')
    if run('git', 'status', '--porcelain', '--untracked-files=all', cwd=dest):
        raise SystemExit('Refusing modified Piwork source; no patches or untracked inputs are allowed.')
    if run('git', 'config', '--local', '--get', 'remote.origin.url', cwd=dest) != lock['piwork']['url']:
        raise SystemExit('Unexpected Piwork source origin.')
    return {'repository': lock['piwork']['url'], 'commit': lock['piwork']['commit'],
            'tree': run('git', 'rev-parse', 'HEAD^{tree}', cwd=dest),
            'resolvedAt': lock['piwork']['resolvedAt'], 'branch': lock['piwork']['branch'],
            'modified': False, 'patches': []}


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def refresh_lock(lock=LOCK, runner=run):
    """Move the source lock to the official default HEAD; official input stays pinned."""
    if input_mode(lock) != 'source':
        raise LockError('official-release input is updated explicitly with '
                        '`python3 scripts/piwork_release.py lock --tag <tag>`; source-refresh does not apply')
    url = lock['piwork']['url']
    remote = runner('git', 'ls-remote', '--symref', url, 'HEAD')
    branch = re.search(r'^ref: refs/heads/(.+)\s+HEAD$', remote, re.M)
    head = re.search(r'^([0-9a-f]{40})\s+HEAD$', remote, re.M)
    if not branch or not head:
        raise SystemExit('Cannot resolve the official default branch and full HEAD.')
    lock['piwork'].update(commit=head[1], branch=branch[1],
        resolvedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
    return lock


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', default=LOCK['piwork']['url'], help='optional clone mirror; official origin is retained')
    p.add_argument('--output', type=pathlib.Path)
    p.add_argument('--refresh-lock', action='store_true', help='explicitly resolve latest official default HEAD')
    p.add_argument('--check', action='store_true', help='verify existing input without fetching or writing')
    a = p.parse_args()
    try:
        mode = input_mode()
    except LockError as err:
        raise SystemExit(str(err))
    if a.refresh_lock:
        if a.check:
            p.error('--check and --refresh-lock are mutually exclusive')
        try:
            refresh_lock()
        except LockError as err:
            raise SystemExit(str(err))
        (ROOT / 'build.lock.json').write_text(json.dumps(LOCK, indent=2) + '\n')
    dest = (a.output or source_path()).resolve()
    if a.check:
        print(json.dumps(verify(dest)))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / 'dist/go.mod').write_text('module piwork-microvm-build-artifacts\n')
    revision = LOCK['piwork']['commit']
    if not (dest / '.git').exists():
        subprocess.run(['git', 'clone', '--no-checkout', '--', a.source, str(dest)], check=True)
        subprocess.run(['git', 'checkout', '--detach', revision], cwd=dest, check=True)
        subprocess.run(['git', 'remote', 'set-url', 'origin', LOCK['piwork']['url']], cwd=dest, check=True)
    metadata = verify(dest)
    metadata['inputMode'] = mode
    (dest.parent / 'source.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
