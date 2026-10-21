# Native Windows desktop acceptance

Completed on native Windows 11 Home build 26200, WebView2 137.0.3296.93, WHPX,
Go 1.25.5, MinGW GCC 16.1.0 and Wails v2.17.0. WSL was used to submit test commands;
the GUI, browser, QEMU, paths, dialogs and VM acceleration ran natively on Windows.

The completion run used the final `dist/piwork-microvm-gui.exe` from
`C:\Users\p\piwork-gui-accept-win4\程序 目录`, with a different working directory
`temp` and data root `C:\Users\p\piwork-gui-accept-win4\数据 目录`.
Installation identity stayed `3d7c8bbeca64f3ea428b322cbf5ae1c7`. The historical default-directory gate used a preceding body. The delivered final EXE
was also rechecked in a fresh default-directory installation, as recorded below, in
addition to the Chinese/space installation and complete fault/business matrix.
Local delivery checksums are in `gui-windows-build.json`; input versions, rather than
artifact byte identity, define the build/verification scope.

## Native dialogs, interaction and layout (8.4 / 8.5)

- Fixed the folder picker's browsing root so the current directory is only an initial
  selection. Selected a sibling Chinese/space directory and persisted it; Cancel kept the
  previous selection. An occupied 17891 port produced the real error and left directory
  selection available. Selected the original root again, released the test listener and
  retried. Double Start produced one managed QEMU; double Stop produced one clean stop.
- Reopened the GUI: preferences selected the same root, the success marker matched its
  installation identity, and directory controls were hidden only after health succeeded.
- Fixed the native save filter's embedded NUL representation; native dialog tests passed.
  Exported `本次 日志.log` (33,523 bytes) and `全部 日志.zip` (20,567 bytes, two nonempty
  real log entries); reopened both. Cancel created no export. Existing redaction remains
  active; raw logs, credentials and native file-dialog listings are not committed.
- Real clipboard contained the exact WebUI URL and full absolute qcow2 path. The latter
  was ellipsized in the narrow row, with its complete value available through copy.
- Minimize reported native iconic state, then restored. A scoped header mouse sequence
  triggered Windows `EVENT_SYSTEM_MOVESIZESTART` for this exact Wails HWND; the test
  cancelled the native move loop afterward. The input thread's temporary button state
  was restored and detached. No global cursor movement or global input injection was used.
- More/Help/About opened and closed; SVGs and version/platform values displayed.
  Guide, GitHub and Discuss were clicked in the real GUI and their exact allowlisted URLs
  verified in Chrome's native address-bar accessibility value. Open Piwork opened
  `http://127.0.0.1:17891/login` after the upstream redirect.
- Reviewed native 800x600 captures of idle, actual starting, running, error, stopping,
  expanded logs/menu and Help/About. All required controls/icons were present and usable;
  expanded content scrolls, and the disk path truncates without widening the window.

## Original Piwork business and persistence (8.6)

- Started bundled QEMU with microvm/WHPX from the GUI. Native `/healthz` returned 200.
- Through the original UI, created the administrator, saved model/runtime configuration
  and reached production runtime readiness. The model key was synthetic; no paid provider
  inference was attempted or claimed.
- Created Work `work-38060a62-0f2c-473d-a6f0-8dc850e5d3ff` and its real Service.
  Files edit/upload/download/delete, Chinese names, binary hashes, authenticated HTTP,
  anonymous rejection, WebSocket echo, SSE and Work DNS/HTTPS passed.
- Stop button and running-window Close both prompted, waited for the existing ordered
  Guest shutdown and exited cleanly. Reopen/restart reused the original identity and
  business data; Service counter continued 1 -> 2.
- After all fault tests, the original login, Work, Service and files still worked; counter
  continued 2 -> 3. Core, Work, Memory and Service SQLite integrity checks all returned
  `ok`, backed by ext4. Docker data-root remained `/mnt/state/docker`.
- Database inspection after safe GUI closure used the exclusive supplementary native
  Guest inspection helper. Its ext4 unmount was confirmed. This is database evidence;
  GUI startup evidence comes from the preceding real GUI sessions.

## Actual lifecycle failures and recovery (8.7)

- Startup-close: clicked Start, Close and native Yes while starting. One clean shutdown
  completed; GUI exited, runtime metadata disappeared, no unclean marker remained.
- Guest early exit: terminated only the owned QEMU child. GUI stayed open with the real
  exit-status error, unclean marker remained, runtime metadata cleared and all installation,
  disk and case-alias locks became available. Retry recovered the original disk.
- Shutdown budget: suspended the real owned QEMU, clicked Stop and confirmed; sent two
  scoped close requests during stopping. The original 120-second budget expired after
  126.36 seconds including cleanup. QEMU exited, locks released, runtime cleared, unclean
  remained, GUI stayed open. It did not report a clean stop. The queued close required
  explicit acknowledgement of the unclean result; No kept the error screen open.
- Retried to health 200. Forcibly ended only this GUI process; its Windows Job ended its
  QEMU. Stale runtime metadata and unclean marker remained, locks became available.
  Reopened the final EXE, started the same installation and completed business recovery.
- Final normal Close waited for safe shutdown, cleared runtime/unclean and preserved the
  installation identity. No owned GUI/QEMU test process remains; test disks/data remain.

Structured evidence: `gui-windows-guest-exit-result.json`,
`gui-windows-timeout-result.json`, `gui-windows-forced-gui-result.json`,
`gui-windows-final-close-result.json`, `gui-windows-business-before.json`,
`gui-windows-business-after-faults.json`, `gui-windows-before-databases.json`,
`gui-windows-after-databases.json`. Native screenshots use `windows-complete-*.png`.

A transient 17871 forwarding conflict occurred while the isolated Linux test VM was
running concurrently through WSL localhost forwarding. Tests were serialized and the
native retry passed after that test VM stopped; no user's VM was stopped.

## Limits

One Windows host/build and one Linux WSLg/KVM environment were exercised. Other Windows
builds, Linux desktop environments and real AI provider/model sessions are not claimed.
No credentials, disks, generated binaries or raw unfiltered logs are included in Git.

## Final default-directory recheck

Ran the delivered final EXE again with a fresh redirected native LOCALAPPDATA/APPDATA
under `C:\Users\p\piwork-gui-accept-win5`. Start required no directory picker.
Its default `local\PiworkMicroVM` installation reached health 200 with native
QEMU microvm/WHPX; Open Piwork opened the upstream `/setup` page in Chrome.
Normal window Close + native Yes completed safely; GUI/QEMU exited and runtime/unclean
markers cleared. See `gui-windows-final-default.json` and
`screenshots/windows-final-default-{idle,running}.png`.

A test-only cache junction was initially rejected by the existing reparse-point guard.
Replaced only that owned junction with a regular copied cache directory and retried;
no product path-protection change or user-installation change was made.
