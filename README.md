# Piwork MicroVM

[简体中文](README.zh-CN.md)

Run original Piwork inside one QEMU `microvm` Linux Guest with VirtIO-MMIO.
Targets: Linux x86-64/KVM and native Windows 11 Home x86-64/WHPX, from 21H2.
Windows runtime does not use WSL, Docker Desktop or Hyper-V Manager.
[Implementation progress](openspec/changes/support-windows-and-disk-only-storage/tasks.md)
tracks current support; unchecked acceptance tasks have not passed yet.

Build on Linux with Docker Engine, Go 1.25.5, Git, Python 3, Make, Bash, curl,
qemu-img and internet access. Containers supply kernel/QEMU/MinGW tools, Node 24
and Guest Docker 28.5.2. Inputs are pinned in `build.lock.json`.

```sh
make source-refresh         # explicitly resolve latest official default HEAD
make source-check           # verify the independent clean, locked checkout
make piwork-microvm-all      # both platform artifacts
# Or: make piwork-microvm / make piwork-microvm-windows
```

Normal builds use the full locked commit at `dist/source/<commit>/piwork`.
No Piwork patches are applied; modified inputs are rejected. Server, WebUI and
production Agent/Helpers share the upstream release identity. package-helper
follows upstream's Agent reference. `make source PIWORK_SOURCE=/path/to/piwork`
can obtain committed objects from a local clone; it never resets that clone or
copies dirty files. Builds do not push or publish. Filesystem UUIDs/timestamps
can vary; whole-artifact byte reproducibility is not promised.

Copy only the matching completed artifact to the Host:

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

Linux needs current-user read/write access to `/dev/kvm`. Windows needs firmware
virtualization and **Windows Hypervisor Platform** enabled, including any required
restart. No additional driver, host QEMU, Docker or language toolchain is needed.
Missing hardware acceleration is an error, with no machine/TCG fallback.
Reserve at least 8 GiB for extracted resources and initial data, then allow for
Work growth. Defaults: 2 vCPU/4096 MiB; adjust with `--cpus`/`--memory`.

The launcher prints the access address, persistent disk and filtered diagnostic
log paths, including actual QEMU argv. Only two Host ports are forwarded, both
bound to `127.0.0.1`:

| Option | Host default | Guest port | Purpose |
| --- | --- | --- | --- |
| `--port` | 17891 | 17891 | Browser UI, login, administration, QuickStart and Service Proxy |
| `--core-port` | 17871 | 17871 | Core API for CLI/backend clients |

Both Host ports accept 1–65535 and must differ. Services use the UI's same-origin
`/services/<workId>/<serviceId>/<port>/` path; the old 64-port pool is neither
reserved nor forwarded. Browser origin follows `--port`; HTTP 80 omits `:80`.
Conflicts fail explicitly without stopping other programs. After changing the
port on the same stopped installation, sign in again and reopen Services.
To run Windows and Linux instances concurrently, use independent installations
and different UI/Core ports. A single data disk always has only one VM writer.

The launcher opens the access address. Original Piwork 0.0.9 creates the first
administrator directly in the browser, then uses normal login and QuickStart.
`--no-open` disables browser launch. API keys, passwords and tokens must not
appear in ordinary logs.

`--data-dir` is the **complete installation root**, defaulting to
`${XDG_DATA_HOME:-~/.local/share}/piwork-microvm` on Linux and
`%LOCALAPPDATA%\PiworkMicroVM` on Windows:

| Installation path | Contents |
| --- | --- |
| `installation.json` | Installation identity and initialization state |
| `disks/state.qcow2` | Guest ext4: all business and persistent container data |
| `logs/` | Filtered startup/Guest diagnostics |

The qcow2 has 64 GiB logical capacity, grows with allocation and has no external
backing file. `/mnt/state/core` backs `/var/lib/piwork/core`. Docker uses
`/mnt/state/docker`, including managed containerd and local named volumes;
`/var/lib/containerd` is also bound to the disk. Accounts, model configuration,
Work private/workspace/history/Memory and declared persistent Service data are
there. RootFS is read-only with a temporary overlay. Other temporary container
paths retain upstream semantics.

Use existing **Piwork Files upload/download**. Files stay in the ordinary Work
workspace volume, inside the disk. No Host directory sharing, mapped drive or
file synchronization is included.

Keep the launcher in the foreground. Press **Ctrl+C**, wait for confirmed clean
Guest shutdown, then back up `installation.json` and `disks/state.qcow2` together.
Never mount a running disk or treat a live copy as a consistent backup. Window
closure/OS deadlines/force termination may prevent confirmed shutdown; an unclean
marker remains for the next launch. Missing/corrupt disks are not replaced with
blank ones, and unknown nonempty installation roots are not overwritten.

Verified resources live separately in user cache `piwork-microvm/bundles/<hash>/`.
Delete cache only after stopping; the executable extracts it again and retains
the original installation. Launch never builds/downloads the Guest. Component
builds: `make guest`, `make qemu`, `make qemu-windows`. `make boot-dev` explicitly
uses external QEMU for development.

Acceptance uses the current final artifacts, separate fresh `--data-dir` installations,
and the available Linux/KVM and native Windows Home/WHPX hosts. A fresh data
directory resets installation state; it does not clear Host dependencies or the
verified resource cache. The Windows version matrix and a second clean computer
are outside this release's agreed acceptance scope.

Current builds use original Piwork **0.0.9** at commit `a6c36da16ebc`.
See [completion acceptance](openspec/changes/support-windows-and-disk-only-storage/evidence/completion-acceptance.md)
for real-provider calls, restart history and final-artifact fault recovery results.
The [two-port report](openspec/changes/support-windows-and-disk-only-storage/evidence/two-port-acceptance.md)
and [earlier 0.0.8 report](openspec/changes/support-windows-and-disk-only-storage/evidence/acceptance.md)
retain their original test scope and results.

A separate synthetic OpenAI Responses fixture reproduced history HTTP 503 for
tool IDs such as `call-1|fc-1`. Its Run and raw history/Memory persisted, but history
reading failed. This remains a scoped known failure, not evidence that all tool
sessions fail. Real-provider results identify the tested model/protocol and are
recorded separately. Piwork business source remains unchanged. Windows testing
uses native Windows 11 Home build 26200; it does not establish every Windows
version's compatibility.

Linux acceptance: `make acceptance-microvm` (real `/dev/kvm`, Docker for the
external isolation harness, and Playwright/Chromium for tests). The empty runtime
root contains only the final executable and its extracted resources. The harness
stays outside that root. `make acceptance-ports` tests alternate ports in isolated
network namespaces and preserves the existing Host 7171 service.

Windows acceptance runs native Edge and native Node as **test tools**. Compile
`cmd/acceptance-windows` and `cmd/acceptance-guest-windows` with
`GOOS=windows GOARCH=amd64 go build`, copy them and the test scripts/fixtures,
`dist/piwork/images.json`, native Node and Playwright to a Windows-local test tree.
`scripts/acceptance-windows.ps1 -Root <tree> -Port 8080 -Phase first` runs the browser
checks against a running final PE; add `-CorePort <port>` for a custom Core port.
`-Phase recovery` checks the existing baseline,
and `-Phase failures` requires a stopped test installation. The supplementary
Guest controller prepares the synthetic provider and inspects backing mounts
while holding exclusive disk locks; it is separate from final-PE launch tests and
is never included in a product artifact.

The original code of Piwork MicroVM is licensed under [Apache-2.0](LICENSE).
See [NOTICE](NOTICE). Third-party components, including Piwork, Linux and QEMU,
and patches to upstream components retain their respective licenses and notices.
Bundled third-party license files are included in the extracted resources.
