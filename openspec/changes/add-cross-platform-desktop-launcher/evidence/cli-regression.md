# CLI regression and GUI build identity

Both entries share `internal/launcher.Service.RunContext`. This summary keeps the CLI evidence
separate from GUI acceptance.

## Final artifacts

| Entry | Platform | File | SHA256 |
| --- | --- | --- | --- |
| CLI | Linux | `dist/piwork-microvm` | `474a28bb414505b7fc66db25a2ec94cdd992a8b7d6c97db638ee80d29cb1c801` |
| CLI | Windows | `dist/piwork-microvm.exe` | `16de438c1703cf21299e7df54b77bf028f495a9b018fa2577371248052724c1c` |
| GUI | Linux | `dist/piwork-microvm-gui` | `562063245df0b0ffe1a63c19b9ce20b0e5eb026f8e50ff03b90b1db2afb0b70e` |
| GUI | Windows | `dist/piwork-microvm-gui.exe` | `1a98e488c74c9a21a184e5f0af4658ae39cc664b614efe7462fe895dc041384b` |

The GUI files are not CLI release assets and were not tagged, pushed or published. The CLI
filenames and their `.sha256` sidecars are unchanged.

## Linux CLI

- `--help` exits 0 without data changes; `--version` reports `0.1.1`, upstream `0.0.9`
  (`a6c36da16ebcc0e96f0e34ef820d857f2bea4877`) and bundle manifest `v2`.
- Invalid port, equal ports and unknown arguments exit 1.
- An occupied port fails before KVM/data work and reports the exact address once on stderr.
- A corrupt persistent disk is rejected without changing its bytes (`user bytes` retained).
- A clean data root reached `/healthz` = 200 on ports 17991/17971, then SIGTERM produced one
  "Stopping..." line, "Guest stopped cleanly", no `unclean.json`, and no QEMU process.
- A second start on the same root reached health, retained installation ID
  `3d031aa712563f1b1026219a75f34135`, and stopped cleanly.

## Windows CLI

- `--version`, `--help` and invalid-port behavior match Linux; the final PE is Go 1.25.5.
- A clean data root reached `http://127.0.0.1:17992/healthz` = 200 under WHPX with the bundled
  Windows QEMU, then Ctrl+C produced the same single stopping line, clean Guest stop and no
  `unclean.json`.
- The native Windows platform tests (`platform.test.exe`) pass disk identity, inherited lock,
  child lock, Unicode private ACL and reparse/network rejection.

## Identity rules

- The GUI's About values and `--version` both come from the same injected
  `piwork-microvm/internal/launcher` fields; About does not parse CLI text.
- Wails v2.17.0, Go 1.25.5, UI source hashes, the upstream pin and the GUI license index are in
  `gui-linux-build.json`, `gui-windows-build.json` and the bundle manifest.
- Historical CLI acceptance attachments under `openspec/changes/archive/` were not modified;
  they keep their original input-level identities.
- GTK/WebKitGTK and WebView2 are GUI-only prerequisites. `go test ./...` and both CLI builds
  remain independent of desktop development libraries.
