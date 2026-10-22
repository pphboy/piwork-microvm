# Piwork 0.0.12 Linux retry

Checked on 2026-10-22, following the user's request to download 0.0.12 and retry the retained-data failure. **The previously failing Linux data copy now passes with the original official 0.0.12 Core**, including two starts, two clean stops and preservation of the original account, Work, file hashes and Service SQLite counter. The original failed installation remains untouched. The earlier [0.0.11 report](acceptance.md) and its failure retain their original input identity.

This is a local Linux retry, not a new public release or a general compatibility guarantee. Native Windows and real model calls were not repeated. The wrapper's trial version is `0.2.2-dev`; no new tag, push, registry push or release publication was performed. The existing v0.2.1 / 0.0.11 draft and tag were left alone.

## Locked official input

- Upstream Piwork **v0.0.12 Preview**, `official-release` mode.
- Actual binary source: `4f127751fc4805e504a1af0d7b48c02739f72489`.
- Publication/tag commit: `c4ce9bbd8fea9d990979332e57b61876cda20da2`.
- Full input fingerprint: `183580f9718d61a12a5cff16097a517d5f2fc5ce00a5bae5fdb34071d95c6481`.
- Official archive SHA256: `d85bf5b884fdc64f8f3f571b0df34a474cf36e86ed630ea5b0a3c8b947aaf957`.
- Original Core SHA256: `e7d65de554b6a32c347e43d36377033c07757702fa7723573ab523c838012d97`.
- Original CLI SHA256: `ea6cee0d8c0ce3cc4fadbec69806fb0d1dba233202b8d96ea7a02cb7e333be69`.

The official `release-build.json` changed format: native program identities/digests are under `nativePrograms`, while full image identities are in `release-manifest.json`. It no longer supplies the old `publicationCommit`, `programs` or `archives` fields. The importer now understands this native-v2 layout, independently resolves the official Git tag, compares image references across the assets and verifies each executable digest. Original downloaded metadata and executable bytes are not rewritten. Legacy releases still require their stated publication commit to match the tag. Five focused tests cover this compatibility and conflicting/malformed identities; the full Python suite has 129 passing tests.

The prepared input check verifies all 654 recorded outputs, original binary identities, embedded references and the three production images. Core still runs natively in the Guest; Guest Docker loads the Agent/Helpers. No upstream npm/Go or production-image build was run. Kernel and Linux QEMU cache checks hit; changed application inputs caused a new Guest assembly, shared by the Linux CLI and GUI. Both final Linux bodies, trailers, payload digests and complete resource manifests passed inspection. These artifact integrity checks do not turn input-level acceptance into a byte-reproducibility claim.

## Actual Linux/KVM checks

| Case | Result |
| --- | --- |
| Retained 0.0.11 data that previously failed before WAL recovery | Original account/Work/Service, three file hashes and SQLite counter match on both 0.0.12 starts; both launcher exits 0, runtime metadata removed |
| Previously passing 0.0.11 empty-installation data, copied after normal stop | Same two-start, data-preservation and clean-stop checks pass |
| New empty data root, actual native Wails GUI | Start, About 0.2.2-dev / upstream 0.0.12, KVM and original native Core identity pass |
| New installation's browser workflow | Administrator creation, QuickStart, production Agent Work, Files edit/upload/download/delete and production Service pass |
| Service persistence and access | ext4 SQLite counter, exact file bytes, anonymous rejection, WebSocket and SSE pass; no model inference |
| Administrator logs | Real ZIPs saved on Host and opened before and after GUI restart; manifests report complete |
| New installation's GUI stop/reopen | Native stop confirmation, clean stop, GUI restart, unchanged account/Work/Service/file hashes/counter, second clean stop pass |
| Original test installations and user's default installation | Both original test disk/metadata hashes and the default installation metadata hash remain unchanged |
| Native Windows 0.0.12 or real models | **not verified** |

The retained-data tests use full independent qcow2 copies, not main-database-only copies and not an empty replacement for the failed data. No manual checkpoint, database repair or format-marker rewrite was applied to the retry copies before launching the official 0.0.12 Core. Recovery in these runs is the new Core's own behavior. All test VMs were stopped cleanly; the GUI was closed afterward.

## Evidence and limits

[evidence/piwork-0.0.12/](evidence/piwork-0.0.12/) contains the Linux build identities, separate integration records for the failed-data copy, clean-data copy and fresh GUI, original-source preservation hashes, allowlisted session/ZIP summaries and actual GUI screenshots. The scoped verification record accepts this input's Linux evidence and leaves Windows and real models unverified; it does not inherit 0.0.11 platform results.

`make piwork-lock TAG=v0.0.12`, `make guest qemu`, the official read-only check, both Linux packaging entries, `go test ./...`, 129 Python tests and `git diff --check` passed. Raw logs, credentials, synthetic keys, ZIPs, databases, disks and executables remain outside Git. Existing license collection and missing-text indexes remain embedded; this retry does not claim a new license-coverage audit or universal WAL/crash-recovery coverage. No release plan for all four artifacts was generated for 0.0.12.
