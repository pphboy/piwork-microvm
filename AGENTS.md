# Repository conventions

## Commits

- Keep OpenSpec specifications and planning artifacts separate from implementation commits.
- Split implementation commits by a coherent feature or behavior, in dependency order. Do not put every feature into one large `feat` commit or split only by file type.
- Include focused tests with the feature they verify. Shared acceptance tooling, real-model verification and fault-recovery tooling may have their own focused test commits.
- Commit acceptance reports and recorded evidence separately from the code that produces them. Keep user documentation separate when it spans multiple features.
- For an initial import, describe the current implementation honestly; do not fabricate a sequence of historical changes.
- Keep build artifacts, VM disks, runtime state and credentials out of Git. Commit locally unless the user explicitly requests a push.
