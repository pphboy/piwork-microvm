#!/usr/bin/env python3
"""Build the native Wails body for the GUI entry, then append the bundle.

The GUI body is built with its own CGO/tag configuration. It never changes the
CLI's CGO_ENABLED=0 build. Windows builds must run on native Windows because
the Wails desktop toolchain is not cross-compiled from WSL.
"""
import argparse, json, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import bundle  # noqa: E402

WAILS_VERSION = 'v2.17.0'


def run(cmd, **kwargs):
    print('+', ' '.join(str(x) for x in cmd), flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def check_tool():
    """Fail early when the pinned Wails CLI is not the one in this module."""
    try:
        out = subprocess.check_output(['go', 'tool', 'wails', 'version'], text=True, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as err:
        output = getattr(err, 'output', '') or ''
        raise SystemExit(f'Wails CLI is unavailable; run: go get -tool github.com/wailsapp/wails/v2/cmd/wails@{WAILS_VERSION}\n{output}')
    first = next((line.strip() for line in out.splitlines() if line.strip().startswith('v')), '')
    if first != WAILS_VERSION:
        raise SystemExit(f'Wails CLI version is {first or "unknown"}, want {WAILS_VERSION}')


def check_linux_build_deps():
    for module, package in [('gtk+-3.0', 'libgtk-3-dev'), ('webkit2gtk-4.1', 'libwebkit2gtk-4.1-dev')]:
        if subprocess.run(['pkg-config', '--exists', module]).returncode != 0:
            raise SystemExit(f'missing desktop build dependency {module}; install {package} and pkg-config')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--platform', choices=['linux', 'windows'], default='linux' if sys.platform.startswith('linux') else 'windows')
    p.add_argument('--skip-tool-check', action='store_true')
    a = p.parse_args()
    if a.platform == 'windows' and not sys.platform.startswith('win'):
        raise SystemExit('the Windows GUI must be built on native Windows with the pinned Wails/Go/MinGW toolchain')
    if a.platform == 'linux' and not sys.platform.startswith('linux'):
        raise SystemExit('the Linux GUI must be built on Linux')
    os.chdir(ROOT)
    if not a.skip_tool_check:
        check_tool()
    if a.platform == 'linux':
        check_linux_build_deps()

    out = ROOT / 'dist'
    if not (out / 'piwork/metadata.json').is_file():
        raise SystemExit('missing dist/piwork/metadata.json; run make piwork first')
    names = bundle.artifact_names('gui', a.platform)
    body = out / names['body']
    identity = bundle.build_identity(out, 2)
    env = os.environ.copy()
    env.update(CGO_ENABLED='1', GOTOOLCHAIN='local', GOOS=a.platform, GOARCH='amd64')
    flags = '-s -w ' + bundle.version_ldflags(identity)
    tags = 'desktop production'
    if a.platform == 'linux':
        tags += ' webkit2_41'
    else:
        flags = '-s -w -H windowsgui ' + bundle.version_ldflags(identity)
    run(['go', 'build', '-trimpath', '-tags', tags, '-ldflags', flags, '-o', str(body), './cmd/piwork-launcher'], env=env)
    if not body.is_file() or not bundle.body_magic_ok(body, a.platform):
        raise SystemExit(f'GUI body has an unexpected format: {body}')
    run([sys.executable, str(ROOT / 'scripts/bundle.py'), '--entry', 'gui', '--platform', a.platform, '--body', str(body)])
    artifact = out / names['artifact']
    print('GUI body:', body, 'bytes:', body.stat().st_size)
    print('GUI artifact:', artifact, 'bytes:', artifact.stat().st_size)
    try:
        if a.platform == 'linux':
            deps = subprocess.check_output(['ldd', str(artifact)], text=True, stderr=subprocess.STDOUT)
            desktop = [line.strip() for line in deps.splitlines() if any(x in line for x in ('gtk-3', 'webkit2gtk', 'javascriptcoregtk'))]
            print('desktop libraries:', *desktop, sep='\n  ')
    except (OSError, subprocess.CalledProcessError):
        pass
    print('built with Wails', WAILS_VERSION, 'identity', json.dumps(identity, sort_keys=True))


if __name__ == '__main__':
    main()
