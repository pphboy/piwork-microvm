#!/usr/bin/env bash
# Dependency-isolation acceptance on this Host's real KVM; not a second Host.
set -euo pipefail
cd "$(dirname "$0")/.."
clean_root="${PIWORK_CLEAN_ROOT:-$PWD/dist/clean-host/root}"
mkdir -p "$clean_root"/{dev,proc,tmp,run,etc,home/demo,state,cache}
chmod 700 "$clean_root"/{home/demo,state,cache}
cp dist/piwork-microvm "$clean_root/piwork-microvm"
go build -trimpath -o dist/acceptance-chroot ./cmd/acceptance-chroot
install_mount=()
if [[ -n "${PIWORK_TEST_INSTALL_SOURCE:-}" ]]; then
  mkdir -p "$clean_root/state/Installation"
  install_mount=(-v "$PIWORK_TEST_INSTALL_SOURCE:/clean/state/Installation")
fi
docker run --rm --name piwork-microvm-clean --pid=host \
 -e PIWORK_TEST_OCCUPY_DEFAULT="${PIWORK_TEST_OCCUPY_DEFAULT:-0}" \
 -e PIWORK_TEST_PROJECT="$PWD" \
 -e PIWORK_TEST_UID="$(id -u)" -e PIWORK_TEST_GID="$(id -g)" -e PIWORK_TEST_KVM_GROUP="$(stat -c %g /dev/kvm)" \
 --device /dev/kvm:/clean/dev/kvm --device /dev/null:/clean/dev/null \
 --device /dev/urandom:/clean/dev/urandom --device /dev/random:/clean/dev/random --device /dev/zero:/clean/dev/zero \
 -v "$clean_root:/clean" -v /proc:/clean/proc:ro \
 "${install_mount[@]}" \
 -v /:/host:ro -v "$PWD:/host$PWD" --tmpfs /host/tmp:mode=1777 \
 -v "$PWD/dist/acceptance-chroot:/acceptance-chroot:ro" --entrypoint /bin/sh \
 docker@sha256:2a232a42256f70d78e3cc5d2b5d6b3276710a0de0596c145f627ecfae90282ac \
 -c 'cp /etc/resolv.conf /clean/etc/resolv.conf
 if [ "$PIWORK_TEST_OCCUPY_DEFAULT" = 1 ]; then
   chroot /host /usr/bin/python3 "$PIWORK_TEST_PROJECT/fixtures/port-listener.py" &
   for attempt in $(seq 1 50); do
     wget -q -O /dev/null http://127.0.0.1:7171/ 2>/dev/null && break
     sleep 0.1
   done
   wget -q -O /dev/null http://127.0.0.1:7171/ || exit 1
 fi
 /acceptance-chroot --data-dir /state/Installation --no-open "$@" & launcher_pid=$!
 trap '\''kill -TERM "$launcher_pid" 2>/dev/null || true; wait "$launcher_pid"; exit $? '\'' INT TERM
 wait "$launcher_pid"; result=$?
 if [ "$result" -eq 137 ]; then
   echo "Acceptance harness retains the orphan QEMU for the exclusive-lock test."
   while true; do sleep 1; done
 fi
 exit "$result"' sh "$@"
