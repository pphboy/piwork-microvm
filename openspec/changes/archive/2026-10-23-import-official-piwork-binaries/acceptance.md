# Official Piwork 0.0.11 integration and retained WAL issue

Checked on 2026-10-22. Wrapper target: **v0.2.1**. Binary import, cache reuse, four artifact builds, the scoped integration checks and frozen local release preparation are complete. The latest user instruction defers further pushes, uploads and public release until the user fixes Core and requests an update. Actual publication is not claimed. The existing-data WAL failure remains a known issue.

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
| Empty-directory installation: GUI normal stop/reopen and original data | passed | passed |
| Previously retained 0.0.11 test data: GUI reopen | **failed: Core rejects SQLite before WAL recovery** | this data case not rerun |
| Dedicated stopped 0.0.10 copy upgrade, normal stop and reopen | passed | passed |
| Original installation/backup hashes unchanged | passed | passed |
| CLI custom 19190/19191; 7172 refused before installation access | passed | not rerun; scoped to Linux |
| Real AI/model calls or full historical failure matrix | not verified | not verified |

Windows image/binary inspection additionally used a supplementary native controller on the stopped test disk. Its report is separate from the GUI-started process and browser records; it stopped with ext4 unmount confirmed. It is not presented as a live inspection through the GUI's persistent private pipe.

The dedicated Windows 0.0.10 seed used stopped Linux test data, was actually run and checked on native Windows with the existing v0.2.0 CLI, then stopped and copied into separate backup/upgrade directories. This is the tested migration path; it does not claim universal compatibility or downgrade support. Both original sources and untouched backups retain their recorded hashes. Reverting uses those backups and the old artifact, never an old Core on an upgraded disk.

## Known issue in retained Linux test data

The actual GUI performs its normal shutdown and reports clean stop. Subsequent starts of that installation exit in the Guest with:

```text
CORE_STORAGE_FORMAT_UNSUPPORTED: use an independent supported Go data directory
```

The same failure was reproduced with the original official binary in an independent disk copy. Read-only inspection found matching schema version, marker/database identity and schema objects. SQLite `quick_check` succeeds when the original database and WAL are opened together. Checking only the original main database with `immutable=1` instead reports an out-of-order rowid and an index-entry count mismatch. The locked upstream `corestore.Open` validates with `immutable=true` before recovering the WAL.

The original installation database, format marker and official binary were not rewritten to bypass the failure. Diagnostic recovery was confined to a separate private copy. Private disk/database copies stay outside Git. [evidence/integration-linux.json](evidence/integration-linux.json) records the bounded findings; its status is **failed**, so a new-installation pass cannot give Linux integration an unqualified verified status.

The user subsequently directed continuing the binary replacement and release scope, using an empty data directory for deployment. That new Linux GUI installation created a new administrator and real production Work/Files/Service, saved/opened an administrator ZIP, stopped cleanly and reopened with identical account/Work/Service identities, file hashes and SQLite counter. The separate `evidence/linux-empty/` records prove that no old installation or disk was copied into it.

For isolation, the original official Core also rejected the failed data copy in a container **without MicroVM**, networking or a Host Docker socket. Recovering/checkpointing the WAL in that private diagnostic copy made the same unmodified Core reach `app.listening`. The original failed installation was not repaired or rewritten. This establishes that MicroVM is not required to reproduce the storage-check failure; it does not claim the shutdown interaction has been exhaustively diagnosed.

The known failure is retained and is not described as fixed. Linux integration is reported as `verified-with-known-issues`, with both the passing empty-directory case and this failed case linked. The user-approved binary delivery scope does not add an upstream patch or Guest data repairer. Retain stopped backups; do not use the new-deployment result as a general upgrade or downgrade guarantee.

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

Explicit rebuilds with existing compiler/Docker caches measured Kernel 17.58s, Linux QEMU 14.21s, Windows QEMU 13.20s and Guest assembly 33.47s. They are not cold-build measurements. The new application required a newly assembled Guest, then the same verified Guest fed all four entries. No completed-upload timing is available: publication created a draft and an upload attempt was stopped on the latest user instruction; no asset upload completed. These measurements are not a future-release SLA.

The Guest/BusyBox index has 167/167 readable package texts. All 38 imported Go module texts were collected. The Agent image index explicitly records missing extracted texts for `libgcc-s1` and `libstdc++6` version `12.2.0-14+deb12u1`; those entries were retained, and the release-note generator discloses the gap and corresponding-source coverage.

## Evidence and checks

- [evidence/build-linux.json](evidence/build-linux.json), [evidence/build-windows.json](evidence/build-windows.json): build identities and licensing.
- [evidence/integration-windows.json](evidence/integration-windows.json): passing current-input Windows scope.
- [evidence/integration-linux-empty.json](evidence/integration-linux-empty.json): current-input empty-directory Linux GUI deployment and reopen.
- [evidence/integration-linux.json](evidence/integration-linux.json): retained-data Linux failure; never superseded by the new-installation pass.
- `evidence/linux-empty/`, `evidence/linux/`, `evidence/windows/`: allowlisted real screenshots, Guest identities, ZIP summaries and session records.
- `evidence/upgrade-linux/`, `evidence/upgrade-windows/`: stopped-copy data and source/backup preservation results.
- `evidence/import-timings.json`, `evidence/packaging-timings.json`, `evidence/timings.json`: measured stages.

Repository Go tests passed; 124 Python tests passed at `f713c6e`, including input/cache/publication recovery tests, strict evidence matching and three authenticated draft-lookup tests. The frozen `e4347a8` source passed its 121-test suite during local release preparation. The draft-lookup fix is a separate publication-tooling commit; it does not change the frozen source, inputs, notes or assets. Strict OpenSpec validation passed. Evidence collection excludes credentials, raw ZIPs, disks, binaries and database contents, and checks the known test passwords/synthetic keys. The independent README/demo change is untouched.

## Local completion and deferred publication

The user adjusted the completion boundary to the implemented specifications, focused verification and local release preparation, leaving Core repair and subsequent updates to a later task. This changes the execution scope of task 5.6; it does not waive or weaken the publication tool's complete-asset, frozen-input or conflict checks.

- `make release VERSION=0.2.1 REUSE_ARTIFACTS=1` passed in an isolated clean checkout at `e4347a8`; the main checkout's independent README/demo plan was left untouched.
- The frozen local plan has 12 assets: four CLI/GUI binaries, four checksums, the release manifest, QEMU patches and two readable license archives. A final read-only `verify_plan` checked every size/SHA256 and the notes against the same source and locked inputs. The publication dry run passed without remote writes; the notes include corresponding source, upstream Preview status and the retained WAL issue.
- Before the deferral, source through `f713c6e` and the annotated `v0.2.1` tag targeting `e4347a8` had already been pushed. The release remains an unpublished draft with zero assets after stopping the publisher and upload child. The latest public release remains v0.2.0; its release/asset identities, sizes and digests match the pre-attempt snapshot. Container images were never pushed.
- The closure commits remain local. No tag was moved, draft deleted or public release edited during closure. This is local implementation completion, not public release completion.

[evidence/local-finalization.json](evidence/local-finalization.json) records the bounded final checks and actual remote state. Tests of interrupted retry, incomplete placeholders, completed asset conflicts, wrong tag targets, mismatched plans and already-public releases remain passing; no successful real upload or public-release result is invented.

After Core is fixed, the next task must explicitly lock the new official input and associated image identities, re-import the binaries, assemble a new Guest, rebuild the four wrappers and revalidate the changed inputs. The existing frozen v0.2.1 plan and tag retain their old identity; use a new wrapper version/plan for changed source or inputs. These current-input acceptance records do not automatically verify the repaired Core. Preserve the retained failure and untouched stopped backups.
