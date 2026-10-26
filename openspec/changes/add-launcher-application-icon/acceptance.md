# Launcher icon acceptance — 2026-10-26

## Scope and input identity

This verifies the launcher icon change against [locked inputs](evidence/locked-inputs.json) and the compiled body/source fingerprints in [build-inputs.json](evidence/build-inputs.json). The wrapper identifies itself as `0.0.0-dev.715a7d38f328`, independently of the bundled Piwork `0.0.14` (`3355a106766116a9d64b8492209a93218f3b4b21`). No release tag, remote push, registry push or publication was performed.

The pre-existing `dist` preparation contained Piwork 0.0.12 while `build.lock.json` already selected 0.0.14. Initial GUI packaging correctly rejected that mismatch. The user explicitly approved preparing the existing locked 0.0.14 inputs and rebuilding the affected Guest. `make guest` then completed, `scripts/piwork_release.py check` passed, and the cached Kernel and both QEMU components passed their input/output checks. All 167 installed Guest package license texts were retained, with zero missing texts. No user installation disk was modified.

The source clone used HTTPS without the machine's broken SSH URL rewrite. Docker's configured loopback proxy was unavailable; a temporary loopback-only CONNECT relay was used for the required public Docker registry traffic, then stopped. Docker configuration and existing containers were not changed or restarted.

Verification is input based. Final binaries and their checksums remain local build outputs in `dist/`; their bytes do not bind this evidence to a future release. Guest ext4 UUIDs are regenerated, so byte reproducibility is not claimed.

## Automated and build results

| Check | Result |
| --- | --- |
| `make test` | Passed: 141 Python script tests and all Go packages, including resource generation/linking tests |
| `node --test scripts/frontend_test.mjs` | Passed: 4 existing frontend regressions |
| `CGO_ENABLED=1 go test -tags 'desktop production webkit2_41' ./cmd/piwork-launcher` | Passed, including native window/header logo equality and retained GPU policy |
| `CGO_ENABLED=0 go build ... ./cmd/piwork-microvm` | Passed; CLI still needs no desktop toolchain |
| Native Windows resource tests | Passed with Go 1.25.5; ICO has 16/32/48/64/128/256 layers, transparency and group ID 3 |
| Two native Windows build entry points | Both bodies compiled; their icon resources verified against the PNG and their source fingerprints matched |
| Resource failure cleanup | Passed for an injected compiler failure and an existing resource ownership sentinel; no `.syso` or resource working directory remained |
| Changed source inputs | Logo, embedded frontend and resource recipes invalidate old GUI bodies; temporary resource removal does not |
| Final ELF and PE | Both packaged successfully with the current locked inputs; version, Trailer, manifest and payload hash verification passed |
| Final PE resource extraction | `go run ./tools/gui-resources -verify-exe dist/piwork-microvm-gui.exe` passed after bundle append |
| Standalone files | Both final GUI files were copied into directories without adjacent PNG/ICO files and opened successfully |

[tests.log](evidence/tests.log) contains the regular test output. Publication-related lines are test doubles from existing release tests, not real publication operations. [native-build-check.json](evidence/native-build-check.json) records the native cross-entry resource/fingerprint/cleanup checks.

Reproduction commands for the real-window probes:

```sh
python3 scripts/gui-icon-linux.py --exe dist/piwork-microvm-gui --root /path/to/new-isolated-directory
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/gui-icon-build-check.ps1 -Source C:\src\piwork-microvm -Version <wrapper-version> -Commit <source-commit>
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/gui-icon-windows.ps1 -Exe C:\path\piwork-microvm-gui.exe -Root C:\path\new-isolated-directory
```

## Real-window results

| Platform | Observed result | Evidence |
| --- | --- | --- |
| Native Windows 11 Home, WebView2 | Shell-associated EXE icon and actual `WM_GETICON` window handle both carry Piwork's logo. Header logo is visible. Header drag, minimize, restore and idle close passed. | [window record](evidence/windows-window.json), [header](evidence/windows-header.png), [shell icon](evidence/windows-shell-icon.png), [window icon](evidence/windows-window-icon.png) |
| Two Windows monitors | Both reported 96 DPI and 800×600 windows. Normal-scale screenshots passed. | [monitor 0](evidence/windows-monitor-0.png), [monitor 1](evidence/windows-monitor-1.png) |
| Linux, WSLg Weston/XWayland, GTK 3.24.49 | Native GTK window has a legacy `WM_HINTS` icon pixmap containing the local Piwork logo. This WM does not expose `_NET_WM_ICON`. Header and idle close passed at 800×600. | [window record](evidence/linux-window.json), [header](evidence/linux-header.png), [native icon](evidence/linux-native-icon.png) |

Both probes used isolated configuration, data and cache roots. Neither clicked Start nor launched a VM. Linux's installed icon represents the whole source PNG, including its original transparent canvas; the source image and provenance record were not changed.

## Unverified items and limits

- Linux header drag and minimize/restore are awaiting manual confirmation. Synthetic X11 and WSLg host pointer attempts did not establish these actions reliably; they are not reported as application failures or as passing checks. A separate isolated launcher window was opened for the user to inspect.
- Taskbar and Alt+Tab presentation was not visually confirmed. Native Windows shell/window icon extraction passed; it is not substituted for these separate shell-surface observations.
- Real high DPI display testing was unavailable: both current monitors reported 96 DPI. Multi-size resource validation is not described as a real high DPI pass.
- Wayland-native sessions and Linux desktop entry registration were not tested. Bare ELF file icons and automatic `.desktop`/shortcut installation are outside this change's scope.
- The approved 0.0.14 rebuild was packaging preparation. No VM boot, model request, business workload, original-disk recovery or complete release acceptance was performed by this icon change.

## Remaining acceptance

Task 3.2 remains open until the Linux header operations are confirmed, or the user explicitly approves recording that verification as deferred. All other implementation behavior is present. This change is not archived.
