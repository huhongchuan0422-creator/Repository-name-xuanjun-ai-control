# S09 stopped-install transaction review packet

Exact tested checkout: `0bcedbfa7c1532af2a66cfa200a0f2bf4761fcf0`.
Transaction SHA256: `eff812150edb9eb8cf6b26109e71af3fe2bda09448e4682f9868d69c26c34f73`.
Test SHA256: `bbefed8863f8667c39a319d582676135d97cfb3570ced6b3ea6979dce38e685d`.

[Hosted validation run39003744018/job117311845885](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39003744018/job/117311845885) completed SUCCESS at 2026-10-17 12:45:20 CST. All9 tests passed. Tests use a temporary root-owned directory and mock systemctl, protected snapshot and previous host receipt. This is real filesystem failure/rollback testing; it is NOT PID1/systemd239 sandbox, live host installation, independent acceptance or production PASS.

## Implemented behavior

- `manifest` emits exact three unit hashes without host operations.
- `install-stopped` exclusively creates three new candidate unit files, journals intent and creation ownership, reloads unit metadata, requires all stopped and verifies protected metadata unchanged.
- `rollback-stopped` removes only exact-byte, transaction-owned, still-stopped unit files. Changed, foreign, running or unknown files are preserved and cause HOLD. Partial failures preserve journals and private state.
- No start, restart, enable, traffic change, business request, database restore, account creation, writer transfer or Tokyo shutdown entry exists.
- New units have PrivateNetwork=yes and no Install section. They refer to the existing preliminary copied root. UID65534 is only the tested copy identity, not an accepted persistent production identity.
- Host/root, exact source+manifest, separate root-private admission, bounded expiry, exclusive attempt directory and lock are required. Admission-file provisioning must occur through the original independently reviewed authority; a claimed GitHub comment id in a local JSON file is not independent authorization.
- The program does not create its own admission or infer it from repository changes, tests or RAM connectivity.
- Host attempt directory: /var/lib/xuanjun-pr99-s09-stopped-install-v1. No such attempt was created by this implementation/CI run.

## Still required before production

This replaces the old template-only gap only for stopped/quarantined unit installation and rollback. Production activation and cutover remain unsupported. Effective bridge endpoint, persistent identity and restricted write set, complete source/data verification, real authenticated upstream acceptance, final consistent snapshot, canonical single writer and original independent host admission remain unresolved. Existing two-round copied health/restart evidence is inherited, not replayed. No completed major migration node is claimed.

Tests cover successful stopped install+rollback, foreign target rejection, changed/running rollback conflicts, injected partial install failure and subsequent owned rollback, missing ownership evidence, mandatory quarantine, exact source/expiry admission rejection, and symlink rejection.

Original protected units, bridge, winctl, Work/current, Korea443, UK masks, Finance timers and Tokyo writer/cutover gates are unchanged.
