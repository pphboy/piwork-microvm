# Repository conventions

## Commits

- Keep OpenSpec specifications and planning artifacts separate from implementation commits.
- Split implementation commits by a coherent feature or behavior, in dependency order. Do not put every feature into one large `feat` commit or split only by file type.
- Include focused tests with the feature they verify. Shared acceptance tooling, real-model verification and fault-recovery tooling may have their own focused test commits.
- Commit acceptance reports and recorded evidence separately from the code that produces them. Keep user documentation separate when it spans multiple features.
- For an initial import, describe the current implementation honestly; do not fabricate a sequence of historical changes.
- Keep build artifacts, VM disks, runtime state and credentials out of Git. Commit locally unless the user explicitly requests a push.

## Releases

- An annotated git tag is the source of truth for a release version. The wrapper's own version is independent of the upstream Piwork version it bundles; never reuse the upstream version as the release version.
- `make release` stops at local artifacts and never tags, pushes or publishes. `make release-publish` is the separate step that tags and publishes, and container images are never pushed to a remote registry.
- Record verification against the locked inputs, never against artifact bytes: the Guest ext4 rootfs is generated with fresh UUIDs on every build, so artifacts are not byte-reproducible and acceptance evidence never binds to a released hash.
- Release notes must state the corresponding source for the GPL components and the known limitations of the current distribution.
- Artifacts must carry readable license texts for every third-party component they ship, including the Guest rootfs packages and BusyBox. Never require booting the VM to read them, and record a missing text in the index instead of dropping the package.
- A requested Core release covers Core, MicroVM and the Piwork website. After publishing this wrapper with the locked official Core, hand off its actual version, bundled Core version, asset names, sizes, SHA256 and manifest URL to the website update. The overall Core release is complete only after the bilingual website is deployed and its live download links and server instructions are verified. Local builds remain local, and an explicitly narrower release request keeps its stated scope.
