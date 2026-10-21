# Piwork MicroVM

[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE) ![Platforms](https://img.shields.io/badge/platforms-Linux%20x86--64%20%7C%20Windows%2011%20x86--64-blue) [![Upstream Piwork](https://img.shields.io/badge/upstream%20Piwork-0.0.9-informational)](build.lock.json)

[简体中文](README.zh-CN.md)

Run original Piwork inside one QEMU `microvm` Linux Guest with VirtIO-MMIO, delivered as one
self-contained executable per platform: Linux x86-64/KVM and native Windows 11 Home
x86-64/WHPX, from 21H2. The Windows runtime uses no WSL, Docker Desktop or Hyper-V Manager.

Support status is tracked by
[tasks.md](openspec/changes/support-windows-and-disk-only-storage/tasks.md) for the active
change. That file, not this README, is the source of truth for current support.

## Contents

- [What this is](#what-this-is)
- [Quick start](#quick-start)
- [Command-line reference](#command-line-reference)
- [Networking and access](#networking-and-access)
- [Installation data and persistence](#installation-data-and-persistence)
- [Lifecycle, shutdown and disk safety](#lifecycle-shutdown-and-disk-safety)
- [Logs and diagnostics](#logs-and-diagnostics)
- [Resource cache](#resource-cache)
- [Build from source](#build-from-source)
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
happens when `DISPLAY` or `WAYLAND_DISPLAY` is set. Original Piwork 0.0.9 creates the first
administrator directly in the browser, after which normal login and QuickStart apply.

## Command-line reference

| Option | Default | Valid values | Purpose |
| --- | --- | --- | --- |
| `--data-dir DIR` | OS default root | any path | Complete installation root (metadata, disks, logs) |
| `--port PORT` | `17891` | 1-65535 | Host browser UI/ControlPlane port |
| `--core-port PORT` | `17871` | 1-65535 | Host Core API port for CLI/backend clients |
| `--cpus N` | `2` | 1-64 | Virtual CPUs |
| `--memory MiB` | `4096` | 1024-262144 | Guest memory in MiB |
| `--no-open` | off | - | Do not open the access address in a browser |
| `--startup-timeout D` | `15m` | > 0 | How long to wait for the Guest to become ready |
| `--help`, `-h` | - | - | Show help without touching virtualization or data |

- `--port` and `--core-port` must differ, and both must be in 1-65535.
- Positional arguments are rejected.
- Exit code is `0` on success and for `--help`; any failure exits `1` and prints
  `piwork-microvm: <error>` on stderr.
- Development only: `--assets DIR` and `--qemu PATH` must be given together to use an
  explicitly selected external QEMU. This is not part of the normal user flow.

## Networking and access

Only two Host ports are forwarded, and every Host listener is bound to `127.0.0.1`:

| Option | Host default | Guest port | Purpose |
| --- | --- | --- | --- |
| `--port` | 17891 | 17891 | Browser UI, login, administration, QuickStart and Service Proxy |
| `--core-port` | 17871 | 17871 | Core API for CLI/backend clients |

The browser origin follows `--port`, and HTTP port 80 omits `:80`. A port conflict fails with
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

### Container-supplied components

| Component | Version |
| --- | --- |
| Linux kernel | 6.6.159 |
| QEMU | 10.0.8, with two Windows patches |
| Windows QEMU toolchain | MinGW on Fedora 43 |
| Node | 24 |
| Guest Docker | 28.5.2 |

### Make targets

| Target | What it does | Needs |
| --- | --- | --- |
| `source` | Clone and pin the locked upstream checkout | network, git |
| `source-refresh` | Re-resolve the latest official default-branch HEAD and rewrite `build.lock.json` | network, git |
| `source-check` | Verify the existing clean, locked checkout without fetching | - |
| `kernel` | Build the Guest kernel | Docker |
| `piwork` | Build upstream Piwork and its container images | Docker, Go 1.25.5 |
| `guest` | Assemble the Guest rootfs, initramfs and state disk | `piwork`, `kernel` |
| `qemu` | Build and bundle the Linux QEMU | Docker |
| `qemu-windows` | Build and bundle the Windows QEMU | Docker |
| `piwork-microvm` | Produce the Linux artifact | `guest`, `qemu` |
| `piwork-microvm-windows` | Produce the Windows artifact | `guest`, `qemu-windows` |
| `piwork-microvm-all` | Produce both platform artifacts | both of the above |
| `test` | `go test ./...` | Go 1.25.5 |
| `boot-dev` | Development only: run against a host QEMU | host `/usr/bin/qemu-system-x86_64`, built `dist/guest` |

```sh
make source-refresh         # explicitly resolve latest official default HEAD
make source-check           # verify the independent clean, locked checkout
make piwork-microvm-all     # both platform artifacts
# Or: make piwork-microvm / make piwork-microvm-windows
```

### Outputs

- `dist/piwork-microvm` and `dist/piwork-microvm.exe`, each with a `.sha256` sidecar.
- Intermediates: `dist/source/<commit>/piwork`, `dist/piwork/images.json`,
  `dist/piwork/metadata.json`, `dist/guest/`, `dist/qemu/`, `dist/qemu-windows/`.

### Upstream pinning

[`build.lock.json`](build.lock.json) is the source of truth. It pins
`https://github.com/pphboy/piwork.git`, branch `main`, commit
`a6c36da16ebcc0e96f0e34ef820d857f2bea4877`, resolved 2026-10-20. Normal builds use the full
locked commit at `dist/source/<commit>/piwork`, and modified inputs are rejected. The version
string `0.0.9` comes from upstream's own `package.json`, not from the lock file.

### Local source and reproducibility

`make source PIWORK_SOURCE=/path/to/piwork` uses a local clone only as the clone source on first
checkout. It never resets that clone, never copies dirty or untracked files, and verification
hard-fails on a modified input. No Piwork patches are applied.

The payload tarball is built deterministically (sorted entries, `mtime` 0, fixed modes, gzip
`mtime` 0), but the Guest ext4 rootfs uses freshly generated UUIDs, so whole-artifact byte
reproducibility is not promised. Builds do not push or publish; the container registry
namespace is local only (`docker.io/piwork-microvm-local`).

## Acceptance and evidence

The active change's
[tasks.md](openspec/changes/support-windows-and-disk-only-storage/tasks.md) currently records
**43 of 43 tasks complete, none unchecked**; treat that file as the living source of truth. See
[proposal.md](openspec/changes/support-windows-and-disk-only-storage/proposal.md),
[design.md](openspec/changes/support-windows-and-disk-only-storage/design.md) and the synced
main specs under [`openspec/specs/`](openspec/specs/). The prior change is archived at
[2026-10-21-make-piwork-microvm](openspec/changes/archive/2026-10-21-make-piwork-microvm/) with
46 of 46 tasks complete.

| Evidence | Date | Scope |
| --- | --- | --- |
| [completion-acceptance.md](openspec/changes/support-windows-and-disk-only-storage/evidence/completion-acceptance.md) | 2026-10-21 | Real provider `deepseek-flash` over `anthropic-messages` on Linux/KVM and native Windows 11 Home build 26200/WHPX; six final-artifact fault-recovery cases; real-model tool calls with cross-restart session continuation; database `integrity_check=ok` |
| [two-port-acceptance.md](openspec/changes/support-windows-and-disk-only-storage/evidence/two-port-acceptance.md) | 2026-10-21 | 0.0.9 dual-port artifacts; the real-provider row is **NOT VERIFIED** at that stage, because no real key was available |
| [acceptance.md](openspec/changes/support-windows-and-disk-only-storage/evidence/acceptance.md) | 2026-10-20 | 0.0.8 artifacts on the same two hosts |
| [windows-gate.md](openspec/changes/support-windows-and-disk-only-storage/evidence/windows-gate.md) | 2026-10-20 | Development gate only, explicitly not final-artifact acceptance |

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

A separate synthetic OpenAI Responses fixture reproduced history HTTP 503 for tool IDs such as
`call-1|fc-1`. Its Run and raw history/Memory persisted, but history reading failed. This
remains a scoped known failure, not evidence that all tool sessions fail. Real-provider results
identify the tested model and protocol and are recorded separately. Piwork business source
remains unchanged.

## Scope and limitations

- No Host directory sharing, mapped drive, SMB, FUSE or file synchronization.
- No TCG or alternate-machine fallback; hardware acceleration is required.
- Windows testing used native Windows 11 Home build 26200, which does not establish every
  Windows version's compatibility. The version matrix and a second clean computer are outside
  this release's agreed acceptance scope.
- A single data disk always has only one VM writer, and builds run on Linux only without
  pushing or publishing.

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
