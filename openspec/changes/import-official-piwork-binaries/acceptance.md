# Official Piwork 0.0.11 integration — paused before release

Checked on 2026-10-22. OpenSpec progress: **18/21**. Wrapper target: **v0.2.1**, not published. Task 5.2, the final acceptance/commit task 5.5 and publication task 5.6 remain incomplete.

The build imports the original official Core/CLI bytes. Core runs natively in the Guest; Guest Docker loads the three bundled production images. No upstream npm/Go/image compilation or registry push was performed in official mode.

## Locked input basis

- Upstream: Piwork v0.0.11 **Preview**.
- Actual binary source: `a19c6f595fa6b2515d19146f3510dfc9f1ba4b8c`.
- Publication commit: `2142491f5103b58731de4872d153bd1b876860de`.
- Complete input fingerprint: `23c6a0fda864c765cd2d886bacab47b158101dafa62dd5d12840983a1552d3d1`.
- Official archive SHA256: `a909248c9bd9a6571eb26a0dc52773af0a28a932ce24ea3c6706025700be30a9`.

[evidence/locked-inputs.json](evidence/locked-inputs.json) records the complete lock. The two build records separately record four artifact sizes/digests, body identities, original-binary digests and license indexes. These artifact identifiers do not turn input-level acceptance into a reproducibility claim: regenerated ext4 rootfs files have fresh UUIDs.

## Actual scope

| Check | Linux/KVM, WSLg on Debian | Native Windows 11 build 26200, WHPX/WebView2 |
| --- | --- | --- |
| CLI/GUI 0.2.1 builds, original Core/CLI bytes, trailers and resources | passed | passed; GUI body built natively |
| Actual GUI start and About, native Core 0.0.11 and production images | passed | passed |
| Existing browser setup, production Work/Files/Service | passed | passed in native Edge |
| Administrator ZIP saved on Host and opened | passed | passed |
| GUI normal stop | passed | passed |
| Same-installation GUI reopen and original data | **blocked: Core rejects SQLite before WAL recovery** | passed |
| Dedicated stopped 0.0.10 copy upgrade, normal stop and reopen | passed | passed |
| Original installation/backup hashes unchanged | passed | passed |
| CLI custom 19190/19191; 7172 refused before installation access | passed | not rerun; scoped to Linux |
| Real AI/model calls or full historical failure matrix | not verified | not verified |

Windows image/binary inspection additionally used a supplementary native controller on the stopped test disk. Its report is separate from the GUI-started process and browser records; it stopped with ext4 unmount confirmed. It is not presented as a live inspection through the GUI's persistent private pipe.

The dedicated Windows 0.0.10 seed used stopped Linux test data, was actually run and checked on native Windows with the existing v0.2.0 CLI, then stopped and copied into separate backup/upgrade directories. This is the tested migration path; it does not claim universal compatibility or downgrade support. Both original sources and untouched backups retain their recorded hashes. Reverting uses those backups and the old artifact, never an old Core on an upgraded disk.

## Linux reopen blocker

The actual GUI performs its normal shutdown and reports clean stop. Subsequent starts of that installation exit in the Guest with:

```text
CORE_STORAGE_FORMAT_UNSUPPORTED: use an independent supported Go data directory
```

The same failure was reproduced with the original official binary in an independent disk copy. Read-only inspection found matching schema version, marker/database identity and schema objects. SQLite `quick_check` succeeds when the original database and WAL are opened together. Checking only the original main database with `immutable=1` instead reports an out-of-order rowid and an index-entry count mismatch. The locked upstream `corestore.Open` validates with `immutable=true` before recovering the WAL.

No database, format marker or official binary was rewritten to bypass the failure. Private disk/database copies stay outside Git. [evidence/integration-linux.json](evidence/integration-linux.json) records the bounded findings; its status is **failed**, so release verification cannot upgrade Linux integration to verified.

Finishing requires a scope decision: fix the upstream recovery check and import newly published official bytes, or explicitly extend this project to design and verify safe Guest recovery. The existing plan preserves the exact v0.0.11 upstream bytes and does not authorize silently patching them or accepting this exception. No v0.2.1 tag, draft, asset upload or public release was created.

## Measured preparation and packaging

| Stage | Seconds | Conditions |
| --- | ---: | --- |
| Isolated official import, images and licenses | 40.67 | Existing download/image/module caches; no cold network claim |
| Archive/input validation within that import | 0.68 | External metadata and original binaries |
| Image verification/save within that import | 23.45 | Three official production images |
| License collection within that import | 16.41 | Readable binary/module/image texts and index |
| Subsequent read-only official check | 0.51 | Same inputs and output digests |
| Shared Guest + Kernel + both QEMU warm preparation | 8.29 | All four component records hit |
| Four independent payload compressions | 102.15 total | 37.05 / 22.06 / 20.94 / 22.10; bytes matched final payloads |

Explicit rebuilds with existing compiler/Docker caches measured Kernel 17.58s, Linux QEMU 14.21s, Windows QEMU 13.20s and Guest assembly 33.47s. They are not cold-build measurements. The new application required a newly assembled Guest, then the same verified Guest fed all four entries. No upload timing exists because publication did not start. These measurements are not a future-release SLA.

The Guest/BusyBox index has 167/167 readable package texts. All 38 imported Go module texts were collected. The Agent image index explicitly records missing extracted texts for `libgcc-s1` and `libstdc++6` version `12.2.0-14+deb12u1`; those entries were retained, and the release-note generator discloses the gap and corresponding-source coverage.

## Evidence and checks

- [evidence/build-linux.json](evidence/build-linux.json), [evidence/build-windows.json](evidence/build-windows.json): build identities and licensing.
- [evidence/integration-windows.json](evidence/integration-windows.json): passing current-input Windows scope.
- [evidence/integration-linux.json](evidence/integration-linux.json): current-input Linux failure and completed subchecks.
- `evidence/linux/`, `evidence/windows/`: allowlisted real screenshots, Guest identities, ZIP summaries and session records.
- `evidence/upgrade-linux/`, `evidence/upgrade-windows/`: stopped-copy data and source/backup preservation results.
- `evidence/import-timings.json`, `evidence/packaging-timings.json`, `evidence/timings.json`: measured stages.

Repository Go tests passed; 119 Python tests passed, including input/cache/publication recovery tests and strict evidence matching. Strict OpenSpec validation passed. Evidence collection excludes credentials, raw ZIPs, disks, binaries and database contents, and checks the known test passwords/synthetic keys. The independent README/demo change is untouched.
