#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${PIWORK_KERNEL_CONTAINER:-}" != 1 ]]; then
  docker build -f guest/Dockerfile.build -t piwork-microvm-builder:local .
  exec docker run --rm --user "$(id -u):$(id -g)" -e PIWORK_KERNEL_CONTAINER=1 \
    -e PIWORK_BUILD_JOBS="${PIWORK_BUILD_JOBS:-8}" -v "$PWD:/project" -w /project piwork-microvm-builder:local bash scripts/kernel.sh
fi
readarray -t kernel_input < <(python3 -c 'import json; d=json.load(open("build.lock.json"))["linux"]; print(d["version"]); print(d["url"]); print(d["sha256"])')
kernel_version=${kernel_input[0]}
kernel_archive="dist/downloads/linux-$kernel_version.tar.xz"
mkdir -p dist/downloads dist/kernel/pristine dist/guest
if [[ ! -f "$kernel_archive" ]]; then
  curl --fail --location --retry 3 --output "$kernel_archive.part" "${kernel_input[1]}"
  mv "$kernel_archive.part" "$kernel_archive"
fi
printf '%s  %s\n' "${kernel_input[2]}" "$kernel_archive" | sha256sum --check --strict
if [[ ! -d "dist/kernel/pristine/linux-$kernel_version" ]]; then
  tar -xf "$kernel_archive" -C dist/kernel/pristine
fi
kernel_source="$PWD/dist/kernel/pristine/linux-$kernel_version"
make -C "$kernel_source" x86_64_defconfig
"$kernel_source/scripts/kconfig/merge_config.sh" -m -O "$kernel_source" "$kernel_source/.config" guest/kernel/config.fragment
make -C "$kernel_source" olddefconfig
make -C "$kernel_source" -j"${PIWORK_BUILD_JOBS:-8}" bzImage
cp "$kernel_source/arch/x86/boot/bzImage" dist/guest/kernel
cp "$kernel_source/.config" dist/guest/kernel.config
sha256sum dist/guest/kernel
