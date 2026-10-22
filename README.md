# Piwork MicroVM

[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE) ![Platforms](https://img.shields.io/badge/platforms-Linux%20x86--64%20%7C%20Windows%2011%20x86--64-blue) [![Upstream Piwork](https://img.shields.io/badge/upstream%20Piwork-0.0.12-informational)](build.lock.json)

[简体中文](README.zh-CN.md)

Run original Piwork inside one QEMU `microvm` Linux Guest with VirtIO-MMIO, delivered as one
self-contained executable per platform: Linux x86-64/KVM and native Windows 11 Home
x86-64/WHPX, from 21H2. The Windows runtime uses no WSL, Docker Desktop or Hyper-V Manager.

Support status is tracked by
[tasks.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/tasks.md) for the completed
change. That file, not this README, is the source of truth for current support.

## Contents

- [What this is](#what-this-is)
- [Quick start](#quick-start)
- [Desktop launcher (GUI)](#desktop-launcher-gui)
- [Command-line reference](#command-line-reference)
- [Networking and access](#networking-and-access)
- [Installation data and persistence](#installation-data-and-persistence)
- [Lifecycle, shutdown and disk safety](#lifecycle-shutdown-and-disk-safety)
- [Logs and diagnostics](#logs-and-diagnostics)
- [Resource cache](#resource-cache)
- [Build from source](#build-from-source)
- [Releases](#releases)
- [Acceptance and evidence](#acceptance-and-evidence)
- [Scope and limitations](#scope-and-limitations)
- [License](#license)
- [Related documents](#related-documents)

## What this is

Piwork MicroVM boots unmodified upstream Piwork inside a single QEMU `microvm` Guest using
VirtIO-MMIO. Each platform gets one self-contained executable, a Linux ELF or a Windows PE,
carrying the kernel, QEMU, Guest rootfs and container images with it. On launch the executable
extracts those bundled resources into a user cache and boots the Guest; launching never builds
or downloads the Guest. No Piwork patches are applied, and Server, WebUI and the production
Agent/Helpers share the upstream release identity.

## Quick start

### Requirements

- Copy the artifact matching your platform, together with its `.sha256` sidecar.
- **Linux**: the current user needs read/write access to `/dev/kvm`.
- **Windows**: firmware virtualization and **Windows Hypervisor Platform** must be enabled,
  including any restart the system requires.
- No additional driver, host QEMU, Docker or language toolchain is needed.
- Hardware acceleration is mandatory. A missing accelerator is an error, with no machine/TCG
  fallback.
- At least **4 GiB free** is required in the installation root, plus **1 GiB** reserved for
  resource extraction. Leaving more room for Work growth is a recommendation, not a
  requirement.
- Defaults are 2 vCPU / 4096 MiB; adjust with `--cpus` / `--memory`.

### Run

```sh
./piwork-microvm
./piwork-microvm --data-dir /absolute/path/to/installation --port 8080
./piwork-microvm --data-dir /another/installation --port 8020 --core-port 8021
./piwork-microvm --help
```

```powershell
.\piwork-microvm.exe
.\piwork-microvm.exe --data-dir 'D:\Piwork Data' --port 8080
.\piwork-microvm.exe --data-dir 'D:\Another Piwork' --port 8030 --core-port 8031
.\piwork-microvm.exe --help
```

### First launch

The launcher reports the installation root, persistent disk and log path, then reports Guest
progress until Piwork is reachable:

```
Installation: /home/user/.local/share/piwork-microvm
Persistent state: /home/user/.local/share/piwork-microvm/disks/state.qcow2
Log: /home/user/.local/share/piwork-microvm/logs/20261021T074600.123456789.log
Piwork is available: http://127.0.0.1:17891
Core API: http://127.0.0.1:17871
```

The access address is opened in a browser unless `--no-open` is given; on Linux this only
happens when `DISPLAY` or `WAYLAND_DISPLAY` is set. Original Piwork 0.0.12 creates the first
administrator directly in the browser, after which normal login and QuickStart apply.

## Desktop launcher (GUI)

The optional desktop entry is a separate Wails v2.17.0 application. It is built and shipped
locally as its own single file; it does not replace, rename or add desktop dependencies to the
CLI artifacts.

### Requirements

- **Windows 11**: the Microsoft Edge WebView2 Runtime (present by default on current Windows
  11) and WHPX, with the same firmware-virtualization prerequisites as the CLI.
- **Linux**: GTK 3 and WebKitGTK 4.1 runtime libraries (for example `libgtk-3-0` and
  `libwebkit2gtk-4.1-0`), plus a system browser launcher: `xdg-open`, `gio open`,
  `gnome-open`, `kde-open` or `sensible-browser`. If none exists, the launcher reports an
  error instead of silently doing nothing.
- The same `/dev/kvm` or WHPX, free-space, port and data-lock rules as the CLI. No host QEMU,
  Docker, Node, NPM or Vite is used at run time or to build the static frontend.
- These desktop libraries and runtimes apply **only** to the GUI. The CLI remains a
  `CGO_ENABLED=0` binary with no desktop dependency.

### Run

Double-click `piwork-microvm-gui` (`piwork-microvm-gui.exe` on Windows). The first window uses
English regardless of the OS language, uses the platform default data root and offers an
optional native "Change" directory action. Click
"Start Piwork" once; the launcher shows the real phase, and "Open Piwork" becomes available
only after this VM's `/healthz` returns HTTP 200. The original Piwork page still owns first-run
administrator creation, model/API key and Runtime configuration.

- The data root is the complete installation root (metadata, `disks/state.qcow2`, logs). The
  default is `%LOCALAPPDATA%\PiworkMicroVM` on Windows and
  `$XDG_DATA_HOME/piwork-microvm` (or `~/.local/share/piwork-microvm`) on Linux.
- **Language:** More → English / 简体中文 switches immediately and saves the choice. No
  language prompt or separate settings page is required; older preferences without a
  language field also default to English. Changing language does not restart the VM or
  alter its data directory. The Guide link opens the matching English or Chinese README.
- Preferences are stored separately in `%APPDATA%\piwork-microvm\launcher.json` on Windows and
  `$XDG_CONFIG_HOME/piwork-microvm/launcher.json` (or `~/.config/...`) on Linux. WebView data
  stays in its own per-user location, never inside the installation root.
- The success marker is written only after a real health check and a matching installation
  identity. Copying the disk template alone, or a failed start, does not mark setup complete.
- Clicking stop or closing a running window asks for native confirmation, then performs the
  same ordered Guest stop and disk sync as the CLI. Repeated clicks reuse the existing stop.
  An unconfirmed shutdown stays visible as an error instead of being hidden by an automatic
  close.
- The bottom log panel shows the current session; reopening shows the most recent historical
  log when no new one exists. "Export current log" writes a sanitized `.log`, and "Export all
  logs" writes a sanitized `.zip` of the selected installation only, through the native save
  dialog. These contain original technical text; application labels and dialog titles use
  your chosen language. OS-owned buttons and file lists follow the OS language.

## Command-line reference

| Option | Default | Valid values | Purpose |
| --- | --- | --- | --- |
| `--data-dir DIR` | OS default root | any path | Complete installation root (metadata, disks, logs) |
| `--port PORT` | `17891` | 1-65535, except 7172 | Host browser UI/ControlPlane port |
| `--core-port PORT` | `17871` | 1-65535, except 7172 | Host Core API port for CLI/backend clients |
| `--cpus N` | `2` | 1-64 | Virtual CPUs |
| `--memory MiB` | `4096` | 1024-262144 | Guest memory in MiB |
| `--no-open` | off | - | Do not open the access address in a browser |
| `--startup-timeout D` | `15m` | > 0 | How long to wait for the Guest to become ready |
| `--help`, `-h` | - | - | Show help without touching virtualization or data |

- `--port` and `--core-port` must differ, and both must be in 1-65535 except 7172 (internal Agent RPC).
  The reserved port is rejected before virtualization or data access.
- Positional arguments are rejected.
- Exit code is `0` on success and for `--help`; any failure exits `1` and prints
  `piwork-microvm: <error>` on stderr.
- Development only: `--assets DIR` and `--qemu PATH` must be given together to use an
  explicitly selected external QEMU. This is not part of the normal user flow.

## Networking and access

Only two Host ports are forwarded, and every Host listener is bound to `127.0.0.1`:

| Option | Host default | Guest port | Purpose |
| --- | --- | --- | --- |
| `--port` | 17891 | selected `--port` | Browser UI, login, administration, QuickStart and Service Proxy |
| `--core-port` | 17871 | selected `--core-port` | Core API for CLI/backend clients |

Guest listeners, QEMU targets and internal Core clients follow the selected UI/Core ports;
no reverse proxy or relaxed Host/Origin/CSRF check is added. The browser origin follows `--port`, and HTTP port 80 omits `:80`. A port conflict fails with
an explicit error naming the occupied address, without stopping other programs. Services are
reached through the upstream UI's same-origin `/services/` path; the launcher itself only
forwards the two ports above. The old 64-port pool is neither reserved nor forwarded.

To run Windows and Linux instances concurrently, use independent installations and different
UI/Core ports. A single data disk always has only one VM writer. After changing the port of
the same stopped installation, sign in again and reopen Services.

## Installation data and persistence

`--data-dir` is the **complete installation root**:

| OS | Default root |
| --- | --- |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/piwork-microvm` |
| Windows | `%LOCALAPPDATA%\PiworkMicroVM` |

| Path | Contents |
| --- | --- |
| `.lock` | Installation lock, so two processes never share one root |
| `installation.json` | Installation identity and initialization state |
| `disks/state.qcow2` | Guest ext4: all business and persistent container data |
| `logs/` | Filtered startup and Guest diagnostics |
| `unclean.json` | Present only while the previous shutdown is unconfirmed |
| `runtime.json` | Transient runtime details for the running instance |

The qcow2 has 64 GiB logical capacity, grows with allocation and has no external backing file.
`/mnt/state/core` backs `/var/lib/piwork/core`. Docker uses `/mnt/state/docker`, including
managed containerd and local named volumes; `/var/lib/containerd` is also bound to the disk.
Accounts, model configuration, Work private/workspace/history/Memory and declared persistent
Service data live there. RootFS is read-only with a temporary overlay.

Use the existing **Piwork Files** upload/download. Files stay in the ordinary Work workspace
volume, inside the disk. No Host directory sharing, mapped drive, SMB, FUSE or file
synchronization is included.

## Lifecycle, shutdown and disk safety

For an upgrade rehearsal, first confirm a dedicated old test installation is stopped, then
copy its `installation.json` and `disks/state.qcow2` together to a separate installation root.
Start only the copy, verify its identity and data, stop safely and reopen that same copy.
Do not test on a user disk or initialize a replacement if compatibility checks fail. Rollback
uses the untouched stopped backup; reading an upgraded copy with an older Core is not promised.

Keep the launcher in the foreground. Press **Ctrl+C** and wait for confirmed clean Guest
shutdown, which prints `Guest stopped cleanly. All user data retained.` Shutdown has a
120-second budget; if it expires, the launcher forces QEMU to exit and reports an unclean
shutdown. Closing the window, OS shutdown deadlines or force termination can prevent confirmed
shutdown; the `unclean.json` marker (containing `{"shutdown":"unconfirmed"}`) is then left in
the installation root and re-reported on the next launch.

To back up:

1. Stop the launcher cleanly and wait for the confirmation message.
2. Back up `installation.json` and `disks/state.qcow2` together.
3. Never mount a running disk, and never treat a live copy as a consistent backup.

The launcher refuses to destroy data:

- A missing or inaccessible existing disk is never replaced with an empty one.
- Invalid `installation.json` is refused rather than overwritten.
- An unknown nonempty installation root is not claimed:
  `installation root contains unknown data; choose an empty directory (nothing was overwritten)`.

## Logs and diagnostics

Each run writes `<data-dir>/logs/<UTC timestamp>.log` with mode 0600. Only lines containing
`qemu-system-x86_64` are echoed to the console; the full QEMU argv JSON goes to the log file
only.

"Filtered" is an enforced mechanism, not an aspiration. The launcher replaces any line matching
`#setup=`, `authorization:`, `bearer `, `api_key`, `apikey`, `password`, `token` or `credential`
with `sensitive diagnostic omitted`, on both the QEMU and the Guest Piwork output paths. API
keys, passwords and tokens are therefore kept out of ordinary logs.

For a running Guest, open Piwork and sign in as administrator. In the Desktop account menu,
choose its single **Export logs** action. Wait for collection/packing, then save the browser ZIP
download on Host. Open `manifest.json` to check Core and your Work/Service sources and any gaps;
a partial archive does not prove all history was retained. Download started does not prove it
was saved. These business logs are separate from Launcher runtime logs.

For GUI failures, choose **View logs**, then **Export current log**. When a real VM
session file exists, this exports its complete sanitized contents at export start, including
lines outside the bounded display. Before a session file exists, a displayed startup error
can be saved through the same action. **Export all logs** includes only real log files from
the selected installation. Without matching real content, the corresponding action is disabled.

Exports accept an ordinary writable Downloads/Desktop directory without changing that
directory's permissions. Cancelling writes nothing. Write, sync or replacement errors are
reported; incomplete output does not replace an existing file. Current limits are 64 MiB per
source file and 256 MiB total for all logs; an oversized export fails rather than silently
truncating it. Save the file and send it to the maintainer yourself: there is no upload service.

If no window opens, use the system error to check WebView2 (Windows) or GTK/WebKitGTK and the
desktop session (Linux). On Linux, starting `./piwork-microvm-gui` from a terminal exposes
loader/Wails errors; on Windows check the OS error dialog and the installed WebView2 Runtime.
Failures before OS loading/Wails initialization do not promise an application diagnostic
file. The launcher has no separate early-diagnostics directory or export package.

## Resource cache

Bundled resources are extracted lazily on launch into
`<UserCacheDir>/piwork-microvm/bundles/<sha256-of-manifest>/`, and a valid cache is reused
instead of being re-extracted. Concurrent extraction is serialized, and extraction needs the
payload size plus a 1 GiB reserve to be free.

Deleting the cache after a clean stop is safe: the executable extracts it again, and the
installation is untouched.

## Build from source

### Host prerequisites

Docker Engine, **exactly Go 1.25.5** (the build hard-fails on any other `go env GOVERSION`),
Git, Python 3, Make, Bash, curl, qemu-img and internet access. Node is **not** a host
prerequisite; it is supplied by a container. Only Go has an enforced version check.

The default `official-release` input imports Piwork's published Linux binaries and pulls
its production images by digest; it does not run upstream npm, Go or image source builds.
It still needs Go 1.25.5 (to read module identity and module license texts), Docker and
network access on the first preparation. The explicitly selected `source` input compiles
the locked commit as before.

### GUI build prerequisites

GUI builds are separate from the CLI build and must use the pinned Wails CLI:

- Go 1.25.5 and the Wails CLI pinned in this module (`go tool wails version` must print
  `v2.17.0`).
- **Linux**: GCC, pkg-config, `libgtk-3-dev` and `libwebkit2gtk-4.1-dev`; build the Linux GUI
  on Linux.
- **Windows**: native Windows 11, Go 1.25.5, MinGW-w64 GCC on `PATH`, and the WebView2 runtime.
  Build the Windows GUI on native Windows; WSL, cross-compiled Linux results or a Linux GUI
  are not accepted as Windows evidence.
- Node/NPM is **not** required: the frontend is static and embedded with `go:embed`.

### Container-supplied components

| Component | Version |
| --- | --- |
| Linux kernel | 6.6.159 |
| QEMU | 10.0.8, with two Windows patches |
| Windows QEMU toolchain | MinGW on Fedora 43 |
| Node | 24 |
| Guest Docker | 28.5.2 |

Official-input builds pull the pinned Agent, file-helper and snapshot-helper images by
registry digest and embed them into the Guest archive. The finished artifact loads them
offline; users do not need Host Docker or network access.

### Make targets

| Target | What it does | Needs |
| --- | --- | --- |
| `source` | Clone and pin the locked upstream checkout | network, git |
| `source-refresh` | Source mode only: re-resolve the official default-branch HEAD and rewrite `build.lock.json` | network, git |
| `source-check` | Verify the existing clean, locked checkout without fetching | - |
| `piwork` | Prepare the locked input (official import by default) | Docker, Go 1.25.5, network |
| `piwork-lock` | Explicitly replace the official release input; requires `TAG`, for example `TAG=v0.0.12` | network, git |
| `piwork-check` | Verify the prepared official input and its output digests without writing or fetching | Python 3 |
| `piwork-source` | Explicitly compile the locked commit instead of importing the official release | Docker, Go 1.25.5 |
| `kernel` | Build the Guest kernel | Docker |
| `guest` | Assemble the Guest rootfs, initramfs and state disk | `piwork`, `kernel` |
| `qemu` | Build and bundle the Linux QEMU | Docker |
| `qemu-windows` | Build and bundle the Windows QEMU | Docker |
| `piwork-microvm` | Produce the Linux artifact | `guest`, `qemu` |
| `piwork-microvm-windows` | Produce the Windows artifact | `guest`, `qemu-windows` |
| `piwork-microvm-all` | Produce both platform artifacts | both of the above |
| `piwork-microvm-gui` | Produce the Linux GUI artifact | `guest`, `qemu`, GUI build prerequisites |
| `piwork-microvm-gui-windows` | Produce the Windows GUI artifact | `guest`, `qemu-windows`, native Windows GUI prerequisites |
| `piwork-microvm-gui-all` | Produce both GUI artifacts | both GUI targets |
| `test` | Go tests and Python script tests | Go 1.25.5, Python 3 |
| `boot-dev` | Development only: run against a host QEMU | host `/usr/bin/qemu-system-x86_64`, built `dist/guest` |

Kernel, QEMU and Guest assembly write component records under `dist/build-current/`:
the component's own inputs plus every output size and SHA256. A target is skipped only when
the record matches the current inputs and all outputs verify; missing or corrupt output,
an input change, or a missing record rebuilds. Use `FORCE_REBUILD=1` for a full rebuild.
Each check prints `component <kind>: HIT|MISS` and its elapsed time. The same verified
Guest is assembled once and reused by all four CLI/GUI entry points, and the original
payload/trailer format is unchanged.

```sh
make piwork                                    # import the locked official release
make piwork-check                              # read-only verification of that import
make piwork-lock TAG=v0.0.12                   # explicit release-input update (network)
make piwork-source                             # explicit source compile of the locked commit
make guest PIWORK_SOURCE=/home/p/Projects/piwork  # assemble the Guest once
make source-check                              # verify the clean, locked checkout (source mode)
# Reuse that Guest for the two GUI builds below; do not refresh the frozen lock.
```

`source-refresh` is refused while the lock selects `official-release`: a release update must
replace the assets, program identity and image digests together, so use `make piwork-lock`.
Locks without `piwork.inputMode` remain source locks and can still use `source-refresh`.

With the locked Guest and QEMU resources already built, rebuild only the GUI bodies and
append the existing resources (no upstream refresh):

```sh
python3 scripts/gui-build.py --platform linux
# On native Windows, with the same checkout, lock and dist/piwork/metadata.json:
# powershell -File scripts/gui-build-windows.ps1 -Source C:\src\piwork-microvm -Output C:\src\piwork-microvm\dist\launcher-gui-windows.exe -Version <wrapper-version> -Commit <git-commit>
# Then, on the resource-build host:
PIWORK_RELEASE_VERSION=<version> python3 scripts/bundle.py --entry gui --platform windows --body /path/to/launcher-gui-windows.exe
```

Linux uses `CGO_ENABLED=1` and tags `desktop production webkit2_41`; native Windows uses
`CGO_ENABLED=1`, tags `desktop production`, and `-H windowsgui`. CLI builds keep CGO disabled.
The native body script is the Windows half when the common resource-build host is Linux;
all Guest/QEMU resources remain embedded in the final EXE. Node is only needed to run the
optional frontend regression command `node --test scripts/frontend_test.mjs`, not to build
or run the GUI. No build command tags, pushes or publishes.

### Outputs

- `dist/piwork-microvm` and `dist/piwork-microvm.exe`, each with a `.sha256` sidecar.
- `dist/piwork-microvm-gui` and `dist/piwork-microvm-gui.exe`, each with a `.sha256` sidecar.
- GUI intermediates use independent names: `dist/launcher-gui-<platform>[.exe]`,
  `dist/payload-gui-<platform>.tar.gz` and `dist/bundle-manifest-gui-<platform>.json`. They
  never overwrite CLI intermediates or the CLI artifacts.
- Intermediates: `dist/source/<commit>/piwork`, `dist/piwork/images.json`,
  `dist/piwork/metadata.json`, `dist/piwork/import.json`, `dist/piwork/upstream-release/`,
  `dist/guest/`, `dist/qemu/`, `dist/qemu-windows/`. The imported binary set and image
  archive are published atomically: a failed verification leaves the previous input intact.

### Upstream pinning

[`build.lock.json`](build.lock.json) is the source of truth. `piwork.inputMode` selects
`official-release` (current) or `source`; a lock without the field is a source lock. The
current lock pins `https://github.com/pphboy/piwork.git`, release tag `v0.0.12`, the actual
build commit `4f127751fc4805e504a1af0d7b48c02739f72489` and the separate publication commit
`c4ce9bbd8fea9d990979332e57b61876cda20da2`. It also records the four asset sizes/SHA256,
program and UI identity, and the three production image digests. `piwork.commit` is always
the actual build commit, never the publication commit. In the 0.0.12 native-v2 metadata,
program identities/digests come from `nativePrograms`, full image identities come from the
release manifest, and the publication commit is independently resolved from the official Git tag.
The original downloaded metadata and executable bytes remain unchanged.

Normal builds consume the lock and never follow `main`, a moving tag or `latest`. In source
mode they use the full locked commit at `dist/source/<commit>/piwork` and reject modified
inputs. The bundled upstream version is `0.0.12` (an upstream Preview), independent of the
wrapper version.

### Local source and reproducibility

`make source PIWORK_SOURCE=/path/to/piwork` uses a local clone only as the clone source on first
checkout. It never resets that clone, never copies dirty or untracked files, and verification
hard-fails on a modified input. No Piwork patches are applied.

The payload tarball is built deterministically (sorted entries, `mtime` 0, fixed modes, gzip
`mtime` 0), but the Guest ext4 rootfs uses freshly generated UUIDs, so whole-artifact byte
reproducibility is not promised. Builds do not push or publish. Source mode uses the local
namespace `docker.io/piwork-microvm-local`; official mode pulls images by digest and never
pushes to any registry.

Readable license texts for the imported binaries, their Go modules and the production images
are written to `dist/piwork/upstream-release/licenses/` and embedded in every artifact under
`provenance/piwork-upstream/licenses/`. Guest package texts stay under
`provenance/guest-licenses/` and in `guest-licenses.tar.gz`. Each `INDEX.json` records a
component whose text could not be extracted instead of dropping it, and none of these files
requires booting the VM.

## Releases

Releases are published on GitHub and cut from a tagged commit. Piwork MicroVM has its own
version, independent of the upstream Piwork version it bundles; the annotated git tag is the
source of truth, and `--version` reports both. The current lock uses Piwork 0.0.12 **Preview**.
The earlier wrapper v0.2.1 / Piwork 0.0.11
plan remains an unpublished draft. The current Linux retry uses local `0.2.2-dev` builds;
no new release has been published. Use a new wrapper version for a future release, rather
than replacing the existing v0.2.1 tag or frozen plan.

| Asset | Contents |
| --- | --- |
| `piwork-microvm-v<version>-<platform>-amd64[.exe]` | CLI for Linux x86-64 (ELF) or native Windows x86-64 (PE) |
| `piwork-microvm-gui-v<version>-<platform>-amd64[.exe]` | GUI for the same two platforms, with its own body and payload |
| `*.sha256` | Checksum for the matching binary |
| `release-manifest.json` | Locked inputs, four artifact hashes and scoped verification status |
| `qemu-patches.tar.gz` | Corresponding source for the modified GPL component |
| `guest-licenses.tar.gz` | Readable license texts for every package in the Guest image |
| `piwork-licenses.tar.gz` | Readable texts for the imported binaries, their Go modules and the production images |

The GUI needs a native body: build it on native Windows with
`scripts/gui-build-windows.ps1`, then run `scripts/bundle.py --entry gui --platform windows
--body ...` on the resource host. Wails is not cross-compiled; a Linux GUI never substitutes
for the Windows one. The Windows body writes its build record, and packaging refuses a body
whose version, platform, entry or locked inputs do not match.

`make release VERSION=0.2.2` runs the gate, tests, Linux builds, the four-artifact checks,
manifest and notes, then freezes a version plan under `dist/release-plans/v0.2.2/` and stops.
It never tags, pushes or publishes, and no container image is pushed to a registry.
`make release-publish VERSION=0.2.2` is the separate remote step: it verifies the frozen plan
and local bytes, creates or reuses the annotated tag, creates a draft, uploads missing assets,
checks every remote size and SHA256, and only then makes the release public.

If an upload is interrupted, rerun the same command. The frozen plan and notes are reused;
matching remote assets are skipped, and an incomplete placeholder that verifiably belongs to
the same draft plan is removed before re-upload. A tag pointing at another commit, a completed
asset with different content, or an already public release with different content is refused
rather than overwritten. Upload retries are per file; GitHub offers no in-file resume. The four
full artifacts still dominate transfer time.

`make release-publish-dry-run VERSION=0.2.2` prints the frozen tag and asset list without
creating a tag or touching the remote.

Verification is recorded against the **locked inputs**, not against the downloaded bytes: the
Guest ext4 rootfs is regenerated with fresh UUIDs on every build, so two builds of the same
inputs still differ. The manifest carries a full input fingerprint and separate `build`,
`integration`, `real-model` and `upstream` scopes; only a record with the same fingerprint can
mark a scope verified, and upstream records never upgrade a MicroVM scope. Verify a download
with the checksum from its release.

### Upgrading an existing 0.2.0 installation

**Historical 0.0.11 input issue:** one retained Linux test installation was rejected before SQLite WAL recovery, also reproducible with the original Core outside MicroVM. The original [0.0.11 evidence](openspec/changes/archive/2026-10-23-import-official-piwork-binaries/acceptance.md) retains that failure. The [0.0.12 retry](openspec/changes/archive/2026-10-23-import-official-piwork-binaries/acceptance-0.0.12.md) separately verifies the same data in an independent copy with the new official Core. Keep complete stopped backups, including WAL/SHM; this focused result is not a general upgrade or downgrade guarantee.

Stop the old launcher normally first, then copy both `installation.json` and the state disk to
an independent directory. Start the new artifact against that copy and check the existing
account, Work, Files and Service data plus a normal stop/restart. Keep the stopped original and
its backup untouched. This release reports only what the tested copy does; it does not promise
general downgrade compatibility. To roll back, use the untouched stopped installation with the
old release files, never an old Core opened against an upgraded copy.

Release notes carry the corresponding source for every GPL/LGPL component (including BusyBox,
qboot, libfdt and the Guest packages), their locked checksums, a written offer, and the known
limitations of this distribution. Readable license texts are also embedded under `provenance/` in every artifact and in
`guest-licenses.tar.gz`/`piwork-licenses.tar.gz`, without booting the VM.

## Acceptance and evidence

The completed change's
[tasks.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/tasks.md) currently records
**43 of 43 tasks complete, none unchecked**; treat that file as the living source of truth. See
[proposal.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/proposal.md),
[design.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/design.md) and the synced
main specs under [`openspec/specs/`](openspec/specs/). The prior change is archived at
[2026-10-21-make-piwork-microvm](openspec/changes/archive/2026-10-21-make-piwork-microvm/) with
46 of 46 tasks complete.

| Evidence | Date | Scope |
| --- | --- | --- |
| [completion-acceptance.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/completion-acceptance.md) | 2026-10-21 | Real provider `deepseek-flash` over `anthropic-messages` on Linux/KVM and native Windows 11 Home build 26200/WHPX; six final-artifact fault-recovery cases; real-model tool calls with cross-restart session continuation; database `integrity_check=ok` |
| [two-port-acceptance.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/two-port-acceptance.md) | 2026-10-21 | 0.0.9 dual-port artifacts; the real-provider row is **NOT VERIFIED** at that stage, because no real key was available |
| [acceptance.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/acceptance.md) | 2026-10-20 | 0.0.8 artifacts on the same two hosts |
| [windows-gate.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/windows-gate.md) | 2026-10-20 | Development gate only, explicitly not final-artifact acceptance |
| [0.0.12 retry](openspec/changes/archive/2026-10-23-import-official-piwork-binaries/acceptance-0.0.12.md) | 2026-10-22 | Current official input; Linux CLI/GUI builds and focused WAL/data retry; Windows and real models not reverified |
| [Official binary integration](openspec/changes/archive/2026-10-23-import-official-piwork-binaries/acceptance.md) | 2026-10-22 | Piwork 0.0.11 Preview official inputs; both native GUIs, production Work/Files/Service, saved administrator ZIPs and stopped 0.0.10 copies; both empty-directory installations reopened; retained Linux 0.0.11 data has a known SQLite/WAL failure; real models not verified |
| [Frozen Core log-export acceptance](openspec/changes/archive/2026-10-22-update-guest-piwork-log-export/acceptance.md) | 2026-10-22 | Piwork 0.0.10 at `29e3471`; both native GUIs, real Desktop fault/gap ZIP downloads, stopped-copy persistence and one custom UI/Core port pair; no real model call |
| [GUI acceptance](openspec/changes/archive/2026-10-22-add-cross-platform-desktop-launcher/acceptance.md) | 2026-10-22 | Native Linux/KVM and Windows/WebView2/WHPX CoreLoop, dialogs/exports, Work/Files/Services, persistent databases and fault recovery; real AI inference not verified |

### GUI acceptance

The archived GUI record covers C1/W1–W5, English default, saved English/Chinese switching,
Launcher normal/error exports and safe stop with its original Piwork input. The
[prior frozen Core integration](openspec/changes/archive/2026-10-22-update-guest-piwork-log-export/acceptance.md)
uses the newly built 0.0.10 Guest on Linux/KVM and native Windows/WebView2/WHPX. It covers
Desktop fault/gap ZIPs saved on Host, stopped-installation copies, language persistence,
safe shutdown and the custom 19190/19191 path. The [0.0.11 official-input record](openspec/changes/archive/2026-10-23-import-official-piwork-binaries/acceptance.md) records that earlier input’s build, scoped integration and stopped-copy upgrade, including both a passing empty-directory Linux deployment/reopen and the unresolved retained-data SQLite/WAL case. None of these scoped records claims a new real-model call
or an untested Windows version. GUI builds never tag, push or publish.

### Linux acceptance

`make acceptance-microvm` needs a prebuilt `dist/piwork-microvm`, a real `/dev/kvm`, Docker for
the outer isolation harness, and Playwright/Chromium for the browser tests. The launcher runs
inside a minimal clean root that holds only the final executable; the harness itself stays
outside that root.

### Port acceptance

`make acceptance-ports` boots the final artifact at alternate Host ports (8080, 8081, 17891 and
80) one VM at a time, inside an isolated container network namespace, without touching an
existing Host installation. It checks that a controlled listener on port 7171 is left untouched,
that exactly the two selected loopback ports are forwarded, and that invalid or occupied ports
fail safely before any KVM or data work.

### Windows acceptance

Windows acceptance runs native Edge and native Node as **test tools**. Compile
`cmd/acceptance-windows` and `cmd/acceptance-guest-windows` with
`GOOS=windows GOARCH=amd64 go build`, then copy them and the test scripts/fixtures,
`dist/piwork/images.json`, native Node and Playwright to a Windows-local test tree.
`scripts/acceptance-windows.ps1 -Root <tree> -Port 8080 -Phase first` runs the browser checks
against a running final PE; add `-CorePort <port>` for a custom Core port. `-Phase recovery`
checks the existing baseline, and `-Phase failures` requires a stopped test installation.

### Not shipped in product artifacts

`cmd/acceptance-windows`, `cmd/acceptance-guest-windows`, `cmd/acceptance-chroot` and
`cmd/microvm-probe` are test and development tooling only. The product commands are
`cmd/piwork-microvm` and `cmd/piwork-guest`.

A historical 0.0.9 synthetic OpenAI Responses fixture reproduced history HTTP 503 for tool IDs
such as `call-1|fc-1`. Its Run and raw history/Memory persisted, but history reading failed. That
fixture was not rerun for the frozen 0.0.10 input; this is historical evidence, not a claim about
current tool sessions. Real-provider records identify their tested model and protocol. Piwork
business source remains unchanged.

## Scope and limitations

- No Host directory sharing, mapped drive, SMB, FUSE or file synchronization.
- No TCG or alternate-machine fallback; hardware acceleration is required.
- Windows testing used native Windows 11 Home build 26200, which does not establish every
  Windows version's compatibility. The version matrix and a second clean computer are outside
  this release's agreed acceptance scope.
- A single data disk always has only one VM writer, and builds run on Linux only without
  pushing or publishing.
- The GUI adds the system WebView/GTK runtime prerequisites listed above. Those prerequisites
  do not apply to the CLI. The GUI does not embed the Piwork WebUI, add account/model/Runtime
  forms, run in the tray or manage a second installation.

## License

The original code of Piwork MicroVM is licensed under [Apache-2.0](LICENSE). See
[NOTICE](NOTICE). Third-party components, including Piwork, Linux and QEMU, and patches to
upstream components retain their respective licenses and notices. Bundled third-party license
files are included in the extracted resources.

## Related documents

- [AGENTS.md](AGENTS.md) - repository commit and documentation conventions
- [build.lock.json](build.lock.json) - pinned upstream commit and build inputs
- [openspec/specs/](openspec/specs/) - synced main specifications
- [LICENSE](LICENSE) and [NOTICE](NOTICE) - licensing
