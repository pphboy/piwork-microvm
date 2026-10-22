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
mkdir -p dist/downloads dist/qemu-source/pristine dist/qemu-build-native dist/qemu
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
cd dist/qemu-build-native
"$qemu_source/configure" --target-list=x86_64-softmmu --without-default-features \
  --enable-system --enable-kvm --enable-fdt --enable-slirp --disable-tcg \
  --disable-user --disable-tools --disable-docs --disable-guest-agent --disable-werror \
  --disable-modules --disable-download --enable-strip --prefix=/opt/piwork-qemu \
  --with-pkgversion=Piwork-MicroVM
ninja -j"${PIWORK_BUILD_JOBS:-8}" qemu-system-x86_64
rm -f ../qemu/qemu-system-x86_64
cp qemu-system-x86_64 ../qemu/qemu-system-x86_64
rm -f ../qemu/build-packages.txt
cp /qemu-build-packages.txt ../qemu/build-packages.txt
./qemu-system-x86_64 --version
