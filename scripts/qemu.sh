#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${PIWORK_QEMU_CONTAINER:-}" != 1 ]]; then
  docker build -f guest/Dockerfile.build -t piwork-microvm-builder:local .
  docker build -f guest/qemu/Dockerfile -t piwork-microvm-qemu-builder:local .
  exec docker run --rm --user "$(id -u):$(id -g)" -e PIWORK_QEMU_CONTAINER=1 \
    -e PIWORK_BUILD_JOBS="${PIWORK_BUILD_JOBS:-8}" -v "$PWD:/project" -w /project piwork-microvm-qemu-builder:local bash scripts/qemu.sh
fi
readarray -t qemu_input < <(python3 -c 'import json;d=json.load(open("build.lock.json"))["qemu"];print(d["version"]);print(d["url"]);print(d["sha256"])')
qemu_version=${qemu_input[0]}
qemu_archive="dist/downloads/qemu-$qemu_version.tar.xz"
mkdir -p dist/downloads dist/qemu-source/pristine dist/qemu-build-native-patched dist/qemu
if [[ ! -f "$qemu_archive" ]]; then
  curl --fail --location --retry 3 --output "$qemu_archive.part" "${qemu_input[1]}"
  mv "$qemu_archive.part" "$qemu_archive"
fi
printf '%s  %s\n' "${qemu_input[2]}" "$qemu_archive" | sha256sum --check --strict
qemu_source="$PWD/dist/qemu-source/pristine/qemu-$qemu_version"
if [[ ! -f "$qemu_source/.piwork-source-complete" || ! -f "$qemu_source/configure" ]]; then
  rm -rf "$qemu_source"
  tar -xf "$qemu_archive" -C dist/qemu-source/pristine
  touch "$qemu_source/.piwork-source-complete"
fi
python3 scripts/libslirp-source.py linux
slirp_build="$PWD/dist/libslirp-linux-build"
slirp_install="$PWD/dist/libslirp-linux-install"
if [[ -f "$slirp_build/build.ninja" ]]; then
  meson setup --reconfigure --prefix "$slirp_install" --libdir lib --buildtype release "$slirp_build" "$PWD/dist/qemu-source/linux-libslirp"
else
  meson setup --prefix "$slirp_install" --libdir lib --buildtype release "$slirp_build" "$PWD/dist/qemu-source/linux-libslirp"
fi
ninja -C "$slirp_build" -j"${PIWORK_BUILD_JOBS:-8}" install
export PKG_CONFIG_PATH="$slirp_install/lib/pkgconfig"
export LD_LIBRARY_PATH="$slirp_install/lib"
cd dist/qemu-build-native-patched
"$qemu_source/configure" --target-list=x86_64-softmmu --without-default-features \
  --enable-system --enable-kvm --enable-fdt --enable-slirp --disable-tcg \
  --disable-user --disable-tools --disable-docs --disable-guest-agent --disable-werror \
  --disable-modules --disable-download --enable-strip --prefix=/opt/piwork-qemu \
  --with-pkgversion=Piwork-MicroVM
ninja -j"${PIWORK_BUILD_JOBS:-8}" qemu-system-x86_64
python3 - <<'PY'
import json,pathlib
dependencies=json.loads(pathlib.Path('meson-info/intro-dependencies.json').read_text())
slirp=[x for x in dependencies if x.get('name')=='slirp']
expected=(pathlib.Path('../libslirp-linux-install/lib/libslirp.so')).resolve()
if len(slirp)!=1 or expected not in [pathlib.Path(x).resolve() for x in slirp[0].get('link_args',[]) if x.startswith('/')]:
    raise SystemExit('QEMU did not link the patched Debian libslirp')
PY
rm -f ../qemu/qemu-system-x86_64
cp qemu-system-x86_64 ../qemu/qemu-system-x86_64
rm -f ../qemu/build-packages.txt
cp /qemu-build-packages.txt ../qemu/build-packages.txt
./qemu-system-x86_64 --version
