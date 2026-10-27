#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${PIWORK_QEMU_WINDOWS_CONTAINER:-}" != 1 ]]; then
  python3 scripts/windows-toolchain.py
  docker build -f guest/qemu/Dockerfile.windows -t piwork-microvm-qemu-windows-builder:local dist/windows-toolchain
  python3 scripts/windows-toolchain.py --check-builder
  exec docker run --rm --user "$(id -u):$(id -g)" -e PIWORK_QEMU_WINDOWS_CONTAINER=1 \
    -e PIWORK_BUILD_JOBS="${PIWORK_BUILD_JOBS:-8}" -v "$PWD:/project" -w /project \
    piwork-microvm-qemu-windows-builder:local bash scripts/qemu-windows.sh
fi
python3 - <<'PY'
import hashlib,json,pathlib
lock=json.loads(pathlib.Path('build.lock.json').read_text())
for patch in lock['qemu']['windowsPatches']:
    path=pathlib.Path(patch['file'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=patch['sha256']:
        raise SystemExit('QEMU Windows patch checksum mismatch: '+str(path))
PY
readarray -t qemu_input < <(python3 -c 'import json; d=json.load(open("build.lock.json"))["qemu"]; print(d["version"]); print(d["sha256"])')
qemu_version=${qemu_input[0]}
qemu_archive="dist/downloads/qemu-$qemu_version.tar.xz"
printf '%s  %s\n' "${qemu_input[1]}" "$qemu_archive" | sha256sum --check --strict
mkdir -p dist/qemu-source/windows dist/qemu-build-windows-patched dist/qemu-windows
qemu_source="$PWD/dist/qemu-source/windows/qemu-$qemu_version"
if [[ ! -f "$qemu_source/.piwork-source-complete" || ! -f "$qemu_source/configure" ]]; then
  rm -rf "$qemu_source"
  tar -xf "$qemu_archive" -C dist/qemu-source/windows
  touch "$qemu_source/.piwork-source-complete"
fi
for patch in guest/qemu/private-pipe.patch guest/qemu/pipe-poll.patch; do
  if git -C "$qemu_source" apply --check "$PWD/$patch" 2>/dev/null; then
    git -C "$qemu_source" apply "$PWD/$patch"
  else
    git -C "$qemu_source" apply --reverse --check "$PWD/$patch"
  fi
done
# These are the revisions declared by this QEMU release's own wrap files.
python3 - "$qemu_source" <<'PY'
import configparser,json,pathlib,sys
lock=json.loads(pathlib.Path('build.lock.json').read_text())['qemu']['libslirp']['windows']
wrap=configparser.ConfigParser(); wrap.read(pathlib.Path(sys.argv[1])/'subprojects/slirp.wrap')
if (wrap['wrap-git']['url'],wrap['wrap-git']['revision']) != (lock['url'],lock['revision']):
    raise SystemExit('libslirp lock differs from QEMU wrap')
PY
for dep in dtc slirp; do
  readarray -t dep_input < <(python3 -c 'import configparser,sys; c=configparser.ConfigParser(); c.read(sys.argv[1]); print(c["wrap-git"]["url"]); print(c["wrap-git"]["revision"])' "$qemu_source/subprojects/$dep.wrap")
  if [[ ! -d "$qemu_source/subprojects/$dep/.git" ]]; then
    git clone "${dep_input[0]}" "$qemu_source/subprojects/$dep"
    git -C "$qemu_source/subprojects/$dep" checkout --detach "${dep_input[1]}"
  fi
  [[ "$(git -C "$qemu_source/subprojects/$dep" rev-parse HEAD)" == "${dep_input[1]}" ]]
done
python3 scripts/libslirp-source.py windows --qemu-source "$qemu_source"
cd dist/qemu-build-windows-patched
"$qemu_source/configure" --target-list=x86_64-softmmu --cross-prefix=x86_64-w64-mingw32- \
  --without-default-features --enable-system --enable-whpx --disable-tcg \
  --enable-fdt=internal --enable-slirp --disable-user --disable-tools --disable-docs \
  --disable-guest-agent --disable-werror --disable-modules --enable-strip \
  --extra-cflags=-DFD_SETSIZE=1024 --with-pkgversion=Piwork-MicroVM --prefix=/opt/piwork-qemu
ninja -j"${PIWORK_BUILD_JOBS:-8}" qemu-system-x86_64.exe
python3 - <<'PY'
import json,pathlib
targets=json.loads(pathlib.Path('meson-info/intro-targets.json').read_text())
matches=[x for x in targets if x.get('name')=='slirp' and x.get('type')=='shared library']
expected=pathlib.Path.cwd()/'subprojects/slirp/libslirp-0.dll'
if len(matches)!=1 or [pathlib.Path(x).resolve() for x in matches[0]['filename']] != [expected.resolve()] or not expected.is_file():
    raise SystemExit('QEMU did not build the locked libslirp subproject')
PY
rm -f ../qemu-windows/qemu-system-x86_64.exe
cp qemu-system-x86_64.exe ../qemu-windows/
rm -f ../qemu-windows/build-packages.txt
cp /qemu-build-packages.txt ../qemu-windows/build-packages.txt
