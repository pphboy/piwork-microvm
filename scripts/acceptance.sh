#!/usr/bin/env bash
# Real KVM, isolated minimal runtime, current original Piwork. No directory sharing.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x dist/piwork-microvm ]] || { echo 'Build piwork-microvm first.' >&2; exit 1; }
if docker inspect piwork-microvm-clean >/dev/null 2>&1; then echo 'Stop the owned acceptance VM first.' >&2; exit 1; fi
run_dir="${PIWORK_ACCEPTANCE_RUN:-$PWD/dist/acceptance-runs/disk-only-$(date -u +%Y%m%dT%H%M%S)-$$}"
export PIWORK_CLEAN_ROOT="$run_dir/host" PIWORK_ACCEPTANCE_OUT="$run_dir/evidence"
mkdir -p "$PIWORK_ACCEPTANCE_OUT"
chmod 700 "$run_dir" "$PIWORK_ACCEPTANCE_OUT"
node_path="${PIWORK_NODE_PATH:-$(node -p 'process.execPath')}"
playwright="${PIWORK_PLAYWRIGHT_MODULE:-$PWD/../piwork/node_modules/playwright/index.mjs}"
run_node() {
 docker exec piwork-microvm-clean chroot /host /usr/bin/setpriv --reuid "$(id -u)" --regid "$(id -g)" --groups "$(stat -c %g /dev/kvm)" \
 /usr/bin/env HOME="$HOME" PIWORK_ACCEPTANCE_OUT="$PIWORK_ACCEPTANCE_OUT" PIWORK_ACCEPTANCE_PORT="${PIWORK_ACCEPTANCE_PORT:-17891}" PIWORK_ACCEPTANCE_CORE_PORT="${PIWORK_ACCEPTANCE_CORE_PORT:-17871}" PIWORK_PLAYWRIGHT_MODULE="$playwright" \
 "$node_path" "$PWD/scripts/$1" "${@:2}"
}
boot_pid=''
cleanup(){ if [[ -n "$boot_pid" ]] && docker inspect piwork-microvm-clean >/dev/null 2>&1; then docker kill --signal TERM piwork-microvm-clean >/dev/null || true; wait "$boot_pid" || true; fi; }
trap cleanup EXIT INT TERM
start_vm(){
 local label="$1";shift
 bash scripts/boot-clean.sh --port "${PIWORK_ACCEPTANCE_PORT:-17891}" --core-port "${PIWORK_ACCEPTANCE_CORE_PORT:-17871}" "$@" > "$PIWORK_ACCEPTANCE_OUT/boot-$label.log" 2>&1 & boot_pid=$!
 python3 - "$PIWORK_CLEAN_ROOT/state/Installation/runtime.json" "$boot_pid" <<'PY'
import os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]);pid=int(sys.argv[2]);deadline=time.monotonic()+180
while time.monotonic()<deadline:
 if p.exists():break
 os.kill(pid,0);time.sleep(.2)
else:raise SystemExit('No runtime metadata; inspect boot log')
PY
 python3 scripts/clean-runtime.py
}
stop_vm(){ docker kill --signal TERM piwork-microvm-clean >/dev/null; wait "$boot_pid"; boot_pid=''; test ! -e "$PIWORK_CLEAN_ROOT/state/Installation/unclean.json"; }
runtime="$PIWORK_ACCEPTANCE_OUT/clean-runtime.json"
start_vm first
run_node acceptance-browser.mjs | tee "$PIWORK_ACCEPTANCE_OUT/browser.log"
run_node acceptance-storage.mjs
python3 scripts/acceptance-fixture.py --runtime "$runtime"
run_node acceptance-memory.mjs
run_node acceptance-grants.mjs
run_node acceptance-grants-browser.mjs
python3 scripts/acceptance-inspect.py --runtime "$runtime"
run_node acceptance-baseline.mjs
stop_vm
start_vm restart
run_node acceptance-baseline.mjs --verify
run_node acceptance-recovery-browser.mjs
python3 scripts/acceptance-inspect.py --runtime "$runtime"
stop_vm
python3 scripts/acceptance-cache.py clear
export PIWORK_ACCEPTANCE_PORT=80
start_vm empty-cache --port 80
run_node acceptance-baseline.mjs --verify
run_node acceptance-recovery-browser.mjs
python3 scripts/acceptance-inspect.py --runtime "$runtime"
stop_vm
python3 scripts/acceptance-preflight.py
printf 'Evidence: %s\n' "$PIWORK_ACCEPTANCE_OUT"
printf '%s\n' 'Read persistence-result.json for any original Piwork Session-history failure. A real external model call requires a supplied key.'
