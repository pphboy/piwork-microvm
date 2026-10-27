#!/usr/bin/env bash
# Real KVM, one VM at a time; never touches an existing Host installation.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x dist/piwork-microvm ]] || { echo 'Build piwork-microvm first.' >&2; exit 1; }
if docker inspect piwork-microvm-clean >/dev/null 2>&1; then
  echo 'An owned acceptance VM already exists; stop it before another run.' >&2; exit 1
fi
run_dir="$PWD/dist/acceptance-runs/ports-$(date -u +%Y%m%dT%H%M%S)-$$"
export PIWORK_CLEAN_ROOT="$run_dir/host" PIWORK_ACCEPTANCE_OUT="$run_dir/evidence"
mkdir -p "$PIWORK_ACCEPTANCE_OUT"
chmod 700 "$run_dir" "$PIWORK_ACCEPTANCE_OUT"
node_path="${PIWORK_NODE_PATH:-$(node -p 'process.execPath')}"
playwright="${PIWORK_PLAYWRIGHT_MODULE:-$PWD/dist/source/piwork/node_modules/playwright/index.mjs}"
[[ -f "$playwright" ]] || playwright="$PWD/../piwork/node_modules/playwright/index.mjs"
[[ -f "$playwright" ]] || { echo 'Set PIWORK_PLAYWRIGHT_MODULE with Chromium installed.' >&2; exit 1; }
boot_pid=''
cleanup() {
  if [[ -n "$boot_pid" ]] && docker inspect piwork-microvm-clean >/dev/null 2>&1; then
    docker kill --signal TERM piwork-microvm-clean >/dev/null || true
    wait "$boot_pid" || true
  fi
}
trap cleanup EXIT INT TERM
run_node() {
  docker exec piwork-microvm-clean chroot /host /usr/bin/setpriv \
    --reuid "$(id -u)" --regid "$(id -g)" --groups "$(stat -c %g /dev/kvm)" \
    /usr/bin/env HOME="$HOME" PIWORK_ACCEPTANCE_OUT="$PIWORK_ACCEPTANCE_OUT" \
    PIWORK_ACCEPTANCE_PORT="$PIWORK_ACCEPTANCE_PORT" PIWORK_ACCEPTANCE_CORE_PORT="${PIWORK_ACCEPTANCE_CORE_PORT:-17871}" PIWORK_PLAYWRIGHT_MODULE="$playwright" \
    "$node_path" "$PWD/scripts/$1" "${@:2}"
}
runtime="$PIWORK_ACCEPTANCE_OUT/clean-runtime.json"
for selected_port in 8080 8081 17891 80; do
  export PIWORK_ACCEPTANCE_PORT="$selected_port" PIWORK_TEST_OCCUPY_DEFAULT=1
  launch_args=(--port "$selected_port")
  if [[ "$selected_port" = 17891 ]]; then
    launch_args=()
  fi
  echo "Starting real KVM acceptance at Host port $selected_port"
  bash scripts/boot-clean.sh "${launch_args[@]}" > "$PIWORK_ACCEPTANCE_OUT/boot-$selected_port.log" 2>&1 & boot_pid=$!
  python3 - "$PIWORK_CLEAN_ROOT" "$boot_pid" <<'PY'
import os,pathlib,sys,time
root=pathlib.Path(sys.argv[1]);pid=int(sys.argv[2]);deadline=time.monotonic()+180
while time.monotonic()<deadline:
    if (root/'state/Installation/runtime.json').exists():break
    os.kill(pid,0);time.sleep(.2)
else:raise SystemExit('Launcher did not publish runtime information')
PY
  python3 scripts/clean-runtime.py
  if [[ "$selected_port" != 8080 ]]; then run_node acceptance-baseline.mjs --verify; fi
  run_node acceptance-browser.mjs "$runtime" | tee "$PIWORK_ACCEPTANCE_OUT/browser-$selected_port.log"
  run_node acceptance-concurrency.mjs
  cp "$PIWORK_ACCEPTANCE_OUT/browser-result.json" "$PIWORK_ACCEPTANCE_OUT/browser-$selected_port.json"
  if [[ "$selected_port" = 8080 ]]; then
    run_node acceptance-storage.mjs
    python3 scripts/acceptance-fixture.py --runtime "$runtime"
    run_node acceptance-memory.mjs
  fi
  run_node acceptance-baseline.mjs
  cp "$PIWORK_ACCEPTANCE_OUT/persistence-baseline.json" "$PIWORK_ACCEPTANCE_OUT/baseline-$selected_port.json"
  python3 scripts/acceptance-ports-proof.py --runtime "$runtime"
  docker kill --signal TERM piwork-microvm-clean >/dev/null
  wait "$boot_pid"
  boot_pid=''
  rg -q 'Guest stopped cleanly' "$PIWORK_ACCEPTANCE_OUT/boot-$selected_port.log"
  echo "PASS Host port $selected_port browser/Work/Service and clean shutdown"
done
python3 scripts/acceptance-ports-preflight.py
echo "PASS port acceptance complete; evidence: $PIWORK_ACCEPTANCE_OUT"
