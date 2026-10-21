# GUI acceptance

## Scoped bilingual follow-up — 2026-10-22

This is the apply result for the scope approved in `abd1444`, including the Header
translation in `c37c3bc`. Independent OpenSpec verify has **not** been rerun; the original
C1/W1–W5 findings remain in `verification.md` for the coordinator's separate verify step.
The historical business/fault matrix below keeps its original identities and is not
claimed as a new run.

Locked inputs are unchanged: Piwork **0.0.9**, commit
`a6c36da16ebcc0e96f0e34ef820d857f2bea4877`; Guest kernel 6.6.159; QEMU 10.0.8;
Go 1.25.5; Wails v2.17.0. Verification is against those inputs and the recorded native
runs. These SHA256 values identify the local files actually used, not byte-reproducible
builds, a release, or the later upstream-upgrade integration:

| Local artifact | Embedded wrapper version | File SHA256 |
| --- | --- | --- |
| `dist/piwork-microvm-gui` | `0.0.0-dev.c37c3bc2b354` | `eaec888dde0da7fdb246b4a001e634490f1f1b03a6945ba114e03f53592dfbba` |
| `dist/piwork-microvm-gui.exe` | `0.0.0-dev.c37c3bc` | `1ec3282e093ac91873ddee4b998aea92399ab3c17d085c20b2326d4c6fb36050` |

The bodies were built with their native CGO configurations, then appended using the
existing `bundle.append_bundle` path. The last body-only rebuild reused the immutable
payload only after its SHA256 matched the existing manifest. Both final files were
actually opened and launched their own Guest. Linux reused the verified cache
`5f08f0bba1abf7558e485cad30d378fd280bc1b37e8f903e8df2995c144a8c65`
(312 files); native Windows extracted
`3cb36683b202df17a7282673b9925f0b76403d0273f2469dbe8ccc3e03a3b6ca`
(337 files). Windows PE subsystem is 2 (GUI). CLI files were not replaced.

### Fixes and focused regressions

- C1: process ownership survives delayed control connection and cancellation; clean and
  unclean Stop results, held lock and initialization errors are covered by launcher tests.
  These are lifecycle regressions, not a claim of a new real delayed-pipe fault replay.
- W1: nonempty Guest errors race with Stop in 1,500 iterations under the race detector;
  wrapped cancellation without confirmed clean shutdown cannot grant a normal close.
- W2: controller-wide revision plus frontend checks reject old sessions, late snapshots
  and late log replies. Tests execute the production JS in a small DOM fixture; the native
  screenshots below separately prove actual GUI behavior.
- W3: full-file export equality covers more than 5,000 lines, 256 KiB and a 10 KiB line;
  real GUI exports below use the actual ordinary-size sessions, not synthetic GUI logs.
- W4: a normal writable 0755 Linux destination works without chmod; Windows normal
  writable destination also works.
- W5: an isolated RLIMIT_FSIZE subprocess causes a real partial write; a closed temporary
  descriptor exercises the actual file Sync error. Both preserve the previous target.
- Language: missing/legacy preference defaults to English despite Chinese locale;
  save failure and concurrent directory/health writes retain the correct choice and data.
  Catalogs, native prompt text and frontend state preservation have focused regressions.
- A real missing Linux browser association exposed a failed-helper reporting issue.
  `d4958f8` waits for helper results and tries the next helper; a failing executable / working
  fallback test covers it. The owned Linux test config then associated HTTP with real
  installed Chromium. This changes only the acceptance tree, not the user's browser defaults.

Commands passed: `go test ./...`; `go test -race ./internal/launcher ./internal/desktop`;
`node --test scripts/frontend_test.mjs` (4); Python script tests (6); native Windows
`go test ./internal/desktop ./internal/platform ./internal/launcher` and tagged native
Wails/dialog tests; Linux tagged Wails/browser test; CGO=0 CLI builds and help/version smoke.
Windows's symlink subtest alone was skipped for the user's missing symlink privilege
(error 1314); the Linux symlink check passed. No platform permissions were weakened.

### Actual native GUI results

| Check | Linux | Native Windows |
| --- | --- | --- |
| Owned installation | `/home/p/piwork-gui-bilingual/data/piwork-microvm` | `C:\Users\p\piwork-gui-bilingual\local\PiworkMicroVM` |
| Installation identity retained | `8a3addf66e832ef795ac5293cf1c3866` | `64a1638b38e5a3a5604defdeff621f55` |
| Native desktop / acceleration | WSLg, GTK3/WebKitGTK 4.1; actual `microvm` / `kvm,kernel-irqchip=on`, CPU host | WebView2; native QEMU `microvm` / WHPX; PIDs 94160 then 75524, parents 94548 then 42204 |
| English default / saved switch | Chinese LANGUAGE environment, English first; English and Chinese restored across reopen | Chinese Windows, final EXE with no preference opens English; Chinese restored across reopen |
| Header / layout | `MicroVM 启动器` in Chinese, original English label; accepted 800×600 layout retained | Same, reviewed native screenshots |
| Health and browser | Health 200; real configured system-browser handler opened original `/setup` | Health 200; system browser address verified exactly as original `/setup` |
| Clipboard | Actual WebUI URL and absolute qcow2 path matched | Both values matched native clipboard |
| Current / all export | Final current 33,159 bytes matched the session prefix; final ZIP contained 3 actual logs | Current 30,590 bytes equaled full live session; first ZIP 1 log, restart ZIP 2 logs / 61,183 source bytes |
| Failure export | Real owned port conflict before VM log creation saved through existing current-log action | Real owned port conflict saved through same action (190 bytes) |
| Save / Cancel | Native English/Chinese titles; 0755 Downloads unchanged; Cancel created no file | Native English/Chinese titles; ordinary writable folder; Cancel file count unchanged |
| Safe stop / reuse | Native confirmation, stopping state, clean result; original ext4 `/mnt/state/gui-acceptance.txt` recovered after restart | Native Stop confirmation, clean result; same disk and administrator recovered after GUI reopen/restart; running-window close also completed cleanly |

The first Linux marker probe used `/var/lib/piwork`, which is temporary outside its `core`
bind mount. That failed probe is not counted as persistence proof. The accepted test wrote
and recovered the marker on the actual ext4 state mount `/mnt/state`.
Windows administrator creation/login and recovery used the original Piwork browser forms
as supplementary browser checks against the GUI-started WHPX Guest; they are not substituted
for native Wails window checks. No model was configured or called.

Current native screenshots are `evidence/screenshots/bilingual-linux-*` and
`bilingual-windows-*` (idle/reopen, real starting, running, real error, stopping,
Help/About and translated Header). Earlier screenshots retain their earlier filenames
and artifact identities. Linux's default/early error probes before the final Header-only
rebuild are supplementary; current screenshots show the final body.

WSL/Windows loopback mirroring temporarily retained the default ports after a Linux test
VM stopped. Native bind probes and the real error screen exposed it; tests waited until
ports were free and retried. No user VM or network service was killed to clear ports.
The user's Linux CLI on port 8080 (PID 977959) was preserved, and its installation metadata
SHA256 remained `f0feacbcf69b24bb7067aa3efb1185090e62de78db5989606defe9d2d20f4ce4`.

### Boundaries

No real AI inference, new OS-version matrix, full old business/fault-matrix replay or
upstream upgrade is claimed. Early OS-loader/Wails-init diagnostics are explicitly outside
this scoped change. Displayed startup errors use existing logs/current export; there is no
new diagnostic directory, package/menu, upload service or automatic transmission.
Test data is retained; only owned test processes are cleaned up. No push, release, archive
or independent verify was performed.

---

## Historical GUI acceptance — original pre-verification record

Everything below retains its original test scope and file identities. The historical
39-task completion claim predates the independent C1/W1–W5 verification and must not be
read as verification of the corrected bilingual files above.

Status: **The planned desktop Launcher acceptance is complete on the two tested hosts.**
All 39 tasks are checked. This record distinguishes native GUI/VM checks, browser business
checks and supplementary database inspection. Real AI inference is not claimed.

Local deliverables (checksums identify these files for transfer; verification scope is the
locked inputs and actual recorded runs, not a claim of byte-reproducible Guest builds):

```text
c35509372bf95dd3b5436c1fd7d4eb199a0daa27c7ed8a51691420641a9f4cc3  dist/piwork-microvm-gui
07fac85ea893f6003d2d4b4fa687a508f0aea8dc8e72de8c3c331af235ea1e81  dist/piwork-microvm-gui.exe
```

Wrapper version 0.1.1; upstream Piwork 0.0.9 at
`a6c36da16ebcc0e96f0e34ef820d857f2bea4877`; Wails v2.17.0; Go 1.25.5.
CLI artifacts and their historical acceptance records remain separate. No tag, push or
Release was made.

## Native desktop and single-file checks

| Check | Linux | Windows | Evidence |
| --- | --- | --- | --- |
| Native final single-file GUI | ELF, WebKitGTK 4.1 | PE Windows GUI subsystem, WebView2 | `evidence/gui-linux-build.json`, `gui-windows-build.json` |
| Own appended bundle | manifest v2; 312 files | manifest v2; 337 files | build records, real cache extraction/reuse |
| Real acceleration / machine | KVM / microvm | WHPX / microvm | `evidence/gui-runs.json` |
| First open / default directory | Start without picker, health 200 | Start without picker, health 200 | default-run screenshots and run records |
| Chinese/space executable, data and different cwd | pass | pass | `gui-runs.json`, native completion reports |
| Picker, Cancel, persistence, failure/change/retry | pass | pass; native root/initial-selection fix | `gui-linux-complete.md`, `gui-windows-complete.md` |
| Repeated Start / Stop | one managed VM / shutdown | one managed VM / shutdown | completion reports |
| WebUI action and default browser | real health gates entry | real health gates entry; native Chrome URL checked | completion reports |
| Clipboard URL / full qcow2 path | pass | pass | completion reports |
| Minimize / header drag / menu / Help / About | pass | pass; native drag-start event observed | completion reports |
| Guide / GitHub / Discuss | expected allowlisted destinations | exact Chrome address-bar values checked | completion reports |
| Real logs / current + all export / Cancel | pass | pass; native UTF-16 filter fix | `gui-export-linux.txt`, Windows completion report |
| 800x600 five states, long path, logs and modals | screenshots reviewed | screenshots reviewed | `evidence/screenshots/linux-final-*.png`, `windows-complete-*.png` |
| CLI compatibility | original CLI build/lifecycle and tests pass | original CLI build/lifecycle and tests pass | `evidence/cli-regression.md`, `windows-platform-tests.txt` |

Windows export results: current log 33,523 bytes; all-logs ZIP 20,567 bytes with two
nonempty real entries. Linux current export had 425 sanitized lines; all-logs ZIP contained
three real logs. Cancel created no file. Native dialog directory listings and raw logs
are retained only in isolated test directories, not in Git.

## Real GUI-started Piwork and persistence

The original upstream QuickStart/admin/model/runtime flow ran in the system browser or
browser test tool against the actual GUI-started Guest. No host Core or mock VM was used.
The model credential was synthetic and no model request was sent.

| Check | Linux | Windows |
| --- | --- | --- |
| Original onboarding, production runtime readiness | pass | pass |
| Production Work creation and recovery | same Work recovered | same Work recovered |
| Files edit/upload/download/delete, Chinese + binary bytes | pass, hashes match | pass, hashes match |
| Real Service HTTP + authorization | pass | pass |
| Service WebSocket echo + SSE | pass | pass |
| Work DNS / HTTPS / AI API reachability | pass | pass |
| Stop button and running-window Close | confirmed ordered clean Guest shutdown | confirmed ordered clean Guest shutdown |
| Persistent Service SQLite counter | 1 -> 2, then 2 -> 3 with final delivered ELF | 1 -> 2 across restart, 2 -> 3 after faults |
| Core / Work / Memory / Service integrity | four `ok`, ext4 | four `ok`, ext4 |

Docker uses overlay2, cgroup v2 and data-root `/mnt/state/docker`. User/runtime data stays
inside the host's `disks/state.qcow2`; it is not exposed as a host directory.

The final Linux delivery recheck had one transient outbound network-probe failure;
a separate authenticated retry passed (DNS, HTTPS 200, AI API 401). Both the initial
attempt and successful retry are retained in `evidence/gui-linux-final-*.json`.

Full reports: [Linux](evidence/gui-linux-complete.md),
[Windows](evidence/gui-windows-complete.md). Structured business and database results are
`evidence/gui-{linux,windows}-business-*.json` and `gui-*-databases.json`. Credentials and
VM disks remain outside Git.

## Real failure and recovery checks

| Case | Linux | Windows |
| --- | --- | --- |
| Close while starting | confirmed clean stop | confirmed clean stop |
| Repeated close while shutting down | one shutdown; no early exit | two close requests; no early exit |
| Guest early exit | real error + unclean; original disk recovers | real exit-status error + unclean; original disk recovers |
| Full 120-second shutdown budget | ~128 s including cleanup | 126.36 s including cleanup |
| Forced GUI termination | orphan writer retains locks; second writer refused; recover after writer exit | Windows Job ends QEMU; stale runtime + unclean; locks released; reopen recovers |
| Final clean close after recovery | runtime/unclean cleared; identity retained | runtime/unclean cleared; identity retained; ext4 unmount confirmed |

Fault tests targeted marked test roots and owned process IDs only. A temporary cross-test
17871 forwarding conflict through WSL disappeared after serializing the Linux/Windows VM
tests. The user's separate Linux CLI instance on port 8080 was left running. Test processes
were stopped; test data was retained. Default installation metadata checksums are unchanged.

## Environment and limits

- Linux: WSLg, `DISPLAY=:0`, `/dev/kvm`, GTK 3.24.49, WebKitGTK 4.1 2.50.4.
  This is a real Linux GUI and KVM test, not evidence for every Linux desktop distribution.
- Windows: native Windows 11 Home build 26200, WebView2 137.0.3296.93 and WHPX. Product
  execution needs no WSL. Other Windows builds/machines were not tested.
- Linux GUI still requires the documented GTK/WebKitGTK system runtimes; Windows requires
  WebView2 and enabled WHPX. These are GUI/virtualization prerequisites, not CLI build
  dependencies or runtime downloads of QEMU/Guest resources.
- No real AI provider key was supplied for these GUI completion runs. Real inference,
  provider-specific behavior and AI conversation-history recovery remain **not verified**;
  network reachability, persisted model configuration, Work/Files/Services are verified.
- Scoped AT-SPI/HWND/UIA and temporary test helpers were used for desktop interactions;
  Playwright/Edge were test tools only. No global input injection was used in completion.

## Build and verification

```sh
# Linux final single file; GUI CGO configuration is isolated from the CLI
python3 scripts/gui-build.py --platform linux

# Native Windows body, then common trailer/payload append from the build workspace
powershell -ExecutionPolicy Bypass -File scripts/gui-build-windows.ps1 \
  -Source <windows-local-source> -Output <body.exe> -Version 0.1.1
python3 scripts/bundle.py --entry gui --platform windows --body <body.exe>
```

Make targets are `piwork-microvm-gui`, `piwork-microvm-gui-windows` and
`piwork-microvm-gui-all`; original CLI targets remain available.

Final verification covers `go test ./...`, race checks for launcher/desktop, six Python
script tests, native Windows desktop dialog tests, both final trailer/payload checksums,
`git diff --check` and strict OpenSpec validation. See `evidence/final-verification.txt`.
