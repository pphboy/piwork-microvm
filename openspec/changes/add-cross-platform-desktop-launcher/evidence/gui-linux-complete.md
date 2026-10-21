# Linux desktop acceptance (complete for this host)

This supplements `acceptance.md`. All checks used the final Linux artifact
`562063245df0b0ffe1a63c19b9ce20b0e5eb026f8e50ff03b90b1db2afb0b70e`, an isolated
XDG tree, KVM, and AT-SPI/window-message input. No global pointer input was used after the
shared-desktop incident.

## 8.4 directory, failure/retry and concurrency

- Native GTK picker selected `数据 目录` from the default root.
- Empty selected directory tightened from 0755 to 0700; only that directory changed.
- Preferences persisted the Chinese/space path; Cancel left it unchanged.
- Start reached `/healthz` 200; clean stop; success marker bound to installation ID
  `75be751e97f8da82488fe62f33ea21c6`; reopen hid the directory section.
- Occupied `127.0.0.1:17891`, then Start: error screen with the exact port error and
  `重试启动` / `更改`.
- Changed to `数据 目录2` through the picker (mode 0700), released the port, clicked retry:
  `/healthz` 200; installation ID `dcabe38638764f873dec2192e49b2ea2`.
- Double Start on idle: one managed QEMU for the selected installation (the user's separate
  CLI VM on port 8080 was not touched).
- Double Stop: first action accepted, second action rejected; one clean shutdown, no
  `unclean.json`.

## 8.5 interactions and layout

- Clipboard: `复制 WebUI 地址` -> `http://127.0.0.1:17891`; `复制数据镜像路径` -> the
  selected installation's `disks/state.qcow2`.
- Minimize: native window reports iconic; restore works.
- Title drag: real header drag moved the final window by 80x50; buttons did not drag.
- More menu: guide/GitHub/Discuss opened the exact allowlisted URLs; Help and About modals
  opened and closed in-window.
- Logs expanded; current `.log` and all-logs `.zip` saved through native dialogs; Cancel
  created no file; both sanitized.
- Final screenshots: `linux-final-idle.png`, `linux-final-starting.png`,
  `linux-final-running2.png`, `linux-final-stopping.png`; real error capture in
  `linux-orphan-lock-error.png`; Chinese path is visible in the running capture.

## 8.6 onboarding, business data and database integrity

- Playwright (test tool) against the GUI-started Piwork at `127.0.0.1:17891` created
  administrator `acceptance-linux`; the original `/setup` page was used.
- Login succeeded and reached `/admin/setup`; after a VM restart the same login succeeded.
- QGA read `core.sqlite` plus `core.sqlite-wal`:
  - `PRAGMA integrity_check` = `ok`.
  - 42 tables; `users` contains `acceptance-linux` / `admin` / enabled; one login session.
- Stop button: clean stop, no `unclean.json`.
- Running-window close: native confirmation, clean stop, no `unclean.json`.
- Reopen original disk: same installation ID (`dcabe386...`), preferences and admin data
  retained; no early exit or false "stopped".

## 8.7 edge lifecycle

- Startup close: Start then window close; confirmation; clean Guest stop after ~8 s; no
  `unclean.json`.
- Repeated close: two close requests produced one confirmation and one clean stop.
- Guest early exit: killed the QEMU child; GUI showed the real error, `unclean.json` remained;
  closing the error window was confirmed; next Start recovered, admin login worked, clean stop
  removed `unclean.json`.
- Forced GUI termination: orphan QEMU kept the host ports; Start failed with the exact occupied
  port error; after ending the orphan, retry recovered, admin login worked, clean stop.
- Shutdown budget exhaustion: SIGSTOP the QEMU child, close window, confirm; the real
  120-second budget expired at ~128 s, the GUI reported the unclean timeout, `unclean.json`
  remained; next Start recovered, admin login worked, clean stop removed it.


## Full GUI-started business acceptance (2026-10-22 completion)

A second marked test root, `/home/p/piwork-gui-complete`, used the same final ELF,
real WSLg/WebKitGTK window and KVM. Its default XDG data root was
`data/piwork-microvm`, installation ID `25a12249a5bb853883e6dc7358ba0ec3`.
The earlier directory/interaction/fault tests above retain their own installation IDs.

- Clicked Start in the native window; `/healthz` and production runtime readiness passed.
- Used upstream QuickStart to create the administrator, save model configuration and prepare
  the production runtime. The credential was synthetic; no model was called.
- Created production Work `work-b7b73a99-441d-4d2e-bb2b-e70c826411b8` and Service
  `service-36d0d350-bb87-46ca-a8c0-ba1443722eae`.
- Used the original Files UI to edit, upload/download Chinese text and binary bytes and
  delete a file; hashes matched. Authorized Service HTTP, WebSocket echo and SSE passed;
  anonymous Service access was rejected. Work DNS, HTTPS and AI API reachability passed.
- The native Stop button confirmed and completed a clean shutdown; clicked Start again in
  the GUI. The same administrator, configuration, Work, Service and file data returned.
  Service SQLite counter continued from 1 to 2, rather than starting a new database.
- Core, Work, Memory and Service SQLite `PRAGMA integrity_check` all returned `ok`;
  all four were backed by ext4 on the persistent state disk. Docker used overlay2/cgroup v2
  with data-root `/mnt/state/docker`.
- Closed the running window and accepted the native confirmation. It waited for
  `Guest stopped cleanly. All user data retained.`; GUI/QEMU exited, runtime metadata
  disappeared, and `unclean.json` was absent. Test data was retained.

Structured evidence: `gui-linux-business-before.json`,
`gui-linux-business-after-restart.json`, `gui-linux-databases.json`.
Real-provider inference and AI conversation history are not claimed by these tests.

## Final delivered Linux artifact recheck

The final local ELF was rebuilt after the original acceptance copy. Its transfer checksum
is `c35509372bf95dd3b5436c1fd7d4eb199a0daa27c7ed8a51691420641a9f4cc3`.
Copied that actual delivery file to the same Chinese/space executable path and launched
the existing isolated `piwork-gui-complete` installation in a real WebKitGTK window.
Its own trailer located successfully, bundled microvm/KVM reached health 200, and
Start/Open/Close were invoked through AT-SPI. Reviewed the real 800x600 running capture
`screenshots/linux-delivery-final-running.png`.

The original administrator, Work and Service recovered. The browser rechecked production
runtime readiness, Files edits/Chinese and binary transfers/deletion, Service authorization,
HTTP/WebSocket/SSE and persistent counter `2 -> 3`. The outbound network endpoint returned
503 once; a separate authenticated browser-session retry returned DNS success, HTTPS 200
and AI API 401 (reachable, no model call). The initial attempt is retained honestly in
`gui-linux-final-business-attempt.json`; the successful retry is in
`gui-linux-final-network-recheck.json`. This was a transient outbound probe failure,
not a GUI or data-recovery failure. Final safe Close completed and cleared runtime/unclean.
