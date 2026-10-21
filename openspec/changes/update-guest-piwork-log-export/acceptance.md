# Frozen Guest log export acceptance

## Scope

This record covers the focused integration acceptance for the frozen upstream input in
`proposal.md` and `tasks.md`. It does not rerun the closed GUI matrix, the full network or
deployment matrices, or a real-provider model flow. Earlier GUI records keep their original
identities and are not claimed as this upgrade's result.

Verification is against the locked inputs and the recorded runs; the hashes below identify
the local files actually exercised, not byte-reproducible builds or a release.

## Locked input and build identity

| Item | Recorded value |
| --- | --- |
| Upstream source | `https://github.com/pphboy/piwork.git` |
| Commit | `29e3471e02e53094c1e1f427a88de6a2a24fb963` |
| Tree | `3dc3eeef7e09c91f95ff949fa4709e279ae3176c` |
| Source state | branch `main`, `modified=false`, no patches, resolved `2026-10-21T19:01:56Z` |
| Declared version | `0.0.10` (not rewritten to `0.0.11`) |
| Source input hash | `1c1eba086ca1c69ceb99ce39883f546d79e8417c17a6c976ba81175825d13181` |
| Wrapper development identity | build commit `0338e5203a00d0de7e88d274e8d3eda970e3daab`, version `0.0.0-dev.0338e5203a00` |
| Images | `piwork-core`, `piwork-agentd`, `piwork-file-helper`, `piwork-snapshot-helper` at `0.0.10-29e3471e02e5-1c1eba086ca1` |
| Agent image | `sha256:73be88b72ab2c1e60d0493e74f9aaab3f65f0a827ebadc316a76a8ee4dc89394` |
| File-helper image | `sha256:26338f36abb965cbf5078a4248f2ee1e8d4e0b69349551ee1c7bd80f8b77e363` |
| Snapshot-helper image | `sha256:6ab6725e6649183c3680012c542cf7eb71b8e609d91c2cd689d951102cad752c` |
| Guest license texts | `167/167` shipped packages present |

Both platform caches embed the same new Guest payload:

| Payload | SHA256 |
| --- | --- |
| `guest/kernel` | `e774c55b76f2e6e2cae9bd85c98a51b7e820466fbd359bb4894ebc446cf85c90` |
| `guest/initramfs` | `5383096e247302f998c5ba5647afb2e43aa7ce5c5e1cdad02644b8646f0f3e6d` |
| `guest/rootfs.ext4` | `4da853361f4f4a709c1e147edba4afe5ef96e915c1a0b98141490b1ecf8884a9` |
| `guest/state.qcow2` | `c8b8f8d1727f4f9f39fab3fffdcba7758ac2b54bef14adc24a062d86fca45538` |

- Linux cache `7d6c54d9409e518ea9da8657f9ac4958160d4c020c6c2ee1b9367ee8d01308ef`, 312 files.
- Windows cache `54a6ab3e3ff8c6daa09f590a5e2c118a12f7590f2fc33530135926eddc694b29`, 337 files.

## Final artifacts

| Local artifact | Bytes | SHA256 |
| --- | --- | --- |
| `dist/piwork-microvm-gui` | 397127309 | `646d0ddf68e8143af510104fe6fd6ba819a57ae1f32b03b555226e6167556ce3` |
| `dist/piwork-microvm-gui.exe` | 414813324 | `9e94eb4282815bb81274d33d142e548298ce4515ad3665d06b24a7f512286af9` |
| `dist/piwork-microvm` | 392789727 | `305f908879bbd93cfca325d44e5d95129daf55a2fd147ec4c0c3261974b24788` |
| `dist/piwork-microvm.exe` | 409597985 | `f4934188b948efabf273fe3e3374f16145489f45e87ebf393703fa813eb8a808` |

CLI smoke reports `piwork-microvm 0.0.0-dev.0338e5203a00`, `upstream Piwork 0.0.10
(29e3471e02e53094c1e1f427a88de6a2a24fb963)` and `bundle manifest v2`.

## Actual native GUI and export results

| Check | Linux | Native Windows |
| --- | --- | --- |
| Copy installation | `25a12249a5bb853883e6dc7358ba0ec3` | `3d7c8bbeca64f3ea428b322cbf5ae1c7` |
| Native path | WSLg/WebKitGTK, KVM, QEMU `microvm` | WebView2, WHPX, QEMU `microvm`; PIDs 44608, then 1884 |
| Default language / restored choice | English first; Chinese switch and reopen | English first; Chinese restored across reopen |
| Work inspected | `work-b7b73a99-441d-4d2e-bb2b-e70c826411b8` | `work-38060a62-0f2c-473d-a6f0-8dc850e5d3ff` |
| Fault export | complete, 11136 B, `5784012d4d8b3fed0b492cc196cc2c32002984e3f01dad0043f86c4402e956d8` | complete, 10872 B, `71c176349939aa61abc5b6259aff8fedce464687a044e40ff6fc1f6d8416cd2a` |
| Gap export | partial, 17256 B, `a3f73ac352478dc40be3115e95585a3fedb0418cb47105606e0d21c5b27b6dfb` | partial, 19943 B, `9ed3166d6138fab675180cccf4fa07b2ce1bfda2a93122dd148eefdb8a00d4ea` |
| Gap reason | `source archive was already incomplete` | `source archive was already incomplete` |

Both hosts downloaded the ZIP through the Desktop admin `Export logs` path, saved it to the
Host and opened it. The fault packages are complete with no warnings and contain the Core
log; the controlled gap packages are `complete=false`, `warningCount=1`, and name the
partial source. Unpacked manifests contain only source IDs, states, sizes and digests; no
test credential or real provider key was found in the retained evidence.

## Copy recovery and source preservation

| Check | Linux | Native Windows |
| --- | --- | --- |
| Databases / backing | 4 `ok` on ext4 | 4 `ok` on ext4 |
| Service counter after reopen | `3` | `3` |
| Core logs backing | ext4 | ext4 |
| Clean stop | runtime and unclean marker absent, disk retained | runtime and unclean marker absent, disk retained |
| GUI close | same copy reopened | GUI exited; `zh-CN` preference and installation ID retained |

After the controlled Work/Service fault, the Linux reopen reported `degraded` with the
expected failed Service; the Work files matched their recorded SHA256. Source installations
were stopped before copying and were not written:

- Linux source `/home/p/piwork-gui-complete/data/piwork-microvm`, disk SHA256
  `7f45cdf5de23259a28d460b4aeb3e0abd28c7dcfb08e9db26aa5314f16396241`, unchanged.
- Windows source `C:\Users\p\piwork-gui-accept-win4\数据 目录`, disk SHA256
  `aa6a6b855751e5b92230e4aed93e0f18456954cfb5dd55024032ac76ee4269a0`, unchanged.
- The unrelated user installation kept its metadata and running QEMU; mutations: none.

## Custom ports and 7172

Linux used the final CLI with the dedicated copy:

- QEMU forwarded `127.0.0.1:19190` to Guest `19190` and `127.0.0.1:19191` to Guest `19191`.
- Guest ran `/usr/local/bin/piwork-core --ui-port 19190 --core-port 19191 --data-dir
  /var/lib/piwork/core`; it listened on both ports plus the internal Agent RPC `7172`.
- Core version reported `0.0.10`, commit `29e3471e...`, `modified=false`.
- Browser origin `http://127.0.0.1:19190` and Core `http://127.0.0.1:19191` served
  Desktop/session/works requests with HTTP 200, then the VM stopped cleanly.

Both `--port 7172` and `--core-port 7172` exited 1 before data access with
`port 7172 is reserved for internal Agent RPC`; no install data was created.

## Not verified / boundaries

- No real AI key or real-provider model call was used; fault traffic came from a controlled
  Service.
- The custom 19190/19191 path was exercised only on Linux, as scoped; Windows used the
  default 17891/17871 path.
- The evidence is an allowlisted copy of manifests, JSON results and real screenshots. ZIP
  archives, VM disks, binaries, images and temporary files are not committed.
- No tag, release, push, sync or archive was performed; independent OpenSpec verify is
  still pending.

## Evidence

- `evidence/linux/`: GUI screenshots, fault/gap manifests and export screenshots, recovery,
  clean stop, custom-port proof, Core version and CLI smoke.
- `evidence/windows/`: GUI screenshots, fault/gap manifests and export screenshots, native
  process records, clean stop/close, recovery storage and CLI smoke.
- Input, cache, artifact and source-preservation records: `evidence/build-inputs.json`,
  `evidence/cache-inputs.json`, `evidence/backup-and-preservation.json`.
