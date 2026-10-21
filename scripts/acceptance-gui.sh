#!/usr/bin/env bash
# Acceptance-only isolation harness for the Linux GUI.
# It refuses the user's default data/config/cache roots, creates a marked
# dedicated tree, checks the two host ports and, with --run, launches the final
# artifact with only XDG_* redirected. It never kills processes or writes outside
# the dedicated root.
set -euo pipefail
MODE=check
ROOT="${PIWORK_GUI_ACCEPT_ROOT:-/home/p/piwork-gui-acceptance}"
EXE="$(cd "$(dirname "$0")/.." && pwd)/dist/piwork-microvm-gui"
while [ $# -gt 0 ]; do
  case "$1" in
    --run) MODE=run ;;
    --root) ROOT="$2"; shift ;;
    --exe) EXE="$2"; shift ;;
    *) echo "usage: $0 [--run] [--root DIR] [--exe FILE]" >&2; exit 2 ;;
  esac
  shift
done
canon() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
ROOT="$(canon "$ROOT")"
EXE="$(canon "$EXE")"
HOME_REAL="$(canon "$HOME")"
default_data="$(canon "${XDG_DATA_HOME:-$HOME/.local/share}/piwork-microvm")"
default_cfg="$(canon "${XDG_CONFIG_HOME:-$HOME/.config}/piwork-microvm")"
default_cache="$(canon "${XDG_CACHE_HOME:-$HOME/.cache}/piwork-microvm")"
case "$ROOT" in
  /|"$HOME_REAL"|"$default_data"|"$default_data"/*|"$default_cfg"|"$default_cfg"/*|"$default_cache"|"$default_cache"/*)
    echo "refusing root that is or contains a user default: $ROOT" >&2; exit 1 ;;
esac
[ -f "$EXE" ] || { echo "missing GUI artifact: $EXE" >&2; exit 1; }
mkdir -p "$ROOT/config" "$ROOT/data" "$ROOT/cache" "$ROOT/tmp"
chmod 700 "$ROOT" "$ROOT/config" "$ROOT/data" "$ROOT/cache" "$ROOT/tmp"
marker="$ROOT/.piwork-gui-acceptance"
[ -f "$marker" ] || printf 'owner=%s\ncreated=%s\n' "$(id -un)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$marker"
python3 - "$ROOT" <<'PY'
import socket, sys
root = sys.argv[1]
for port in (17891, 17871):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
    except OSError as e:
        raise SystemExit(f"port {port} is already in use; refusing to disturb an existing service: {e}")
    finally:
        s.close()
print("ports free")
PY
default_install="${XDG_DATA_HOME:-$HOME/.local/share}/piwork-microvm/installation.json"
before=""
[ -f "$default_install" ] && before="$(sha256sum "$default_install" | awk '{print $1}')"
echo "root=$ROOT"
echo "exe=$EXE"
echo "default-installation-sha=$before"
echo "marker=$(cat "$marker" | tr '\n' ' ')"
if [ "$MODE" = check ]; then
  echo "check-only: no process was started and no default path was modified"
  exit 0
fi
XDG_CONFIG_HOME="$ROOT/config" XDG_DATA_HOME="$ROOT/data" XDG_CACHE_HOME="$ROOT/cache" \
  DISPLAY="${DISPLAY:-:0}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  "$EXE" > "$ROOT/gui.log" 2>&1 &
echo $! > "$ROOT/gui.pid"
echo "started pid=$(cat "$ROOT/gui.pid"); working tree unchanged by the harness"
