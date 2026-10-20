#!/usr/bin/env bash
# Development only: leave an existing host Piwork on 7171 running untouched.
set -euo pipefail
cd "$(dirname "$0")/.."
launcher="$PWD/dist/piwork-microvm-dev"
mode="--assets '$PWD/dist/guest' --qemu '$PWD/dist/qemu/qemu-system-x86_64'"
if [[ "${PIWORK_USE_BUNDLE:-}" == 1 ]]; then launcher="$PWD/dist/piwork-microvm"; mode=""; fi
docker run --rm --name piwork-microvm-validation --pid=host \
  --device /dev/kvm:/host/dev/kvm -v /:/host:ro -v "$PWD:/host$PWD" \
  --tmpfs /host/tmp:mode=1777 --entrypoint /bin/sh \
  docker@sha256:2a232a42256f70d78e3cc5d2b5d6b3276710a0de0596c145f627ecfae90282ac \
  -c "exec chroot /host /usr/bin/setpriv --reuid $(id -u) --regid $(id -g) --groups $(stat -c %g /dev/kvm) /usr/bin/env HOME=/home/p XDG_DATA_HOME='$PWD/dist/isolated-state' XDG_CACHE_HOME='$PWD/dist/isolated-cache' '$launcher' $mode --no-open"
