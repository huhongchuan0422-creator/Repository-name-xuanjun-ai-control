# S09 stopped-install transaction review packet

Exact tested checkout: `e0d68c9e2d5db42967017a8f6f8f81224f437208`.
Transaction SHA256: `99225aacc11cae6dc9d190015c95c9883e13d8e2691da864fb026f8afdfee315`.
Test SHA256: `b7cd36097702f144e08493a8c9da2c7f533a5078c21dbdab013c3fa3893b211f`.

[Hosted validation run39004183744/job117313146649](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39004183744/job/117313146649) completed SUCCESS on 2026-10-17 (CST). All9 tests passed. Tests use a temporary root-owned directory and mock systemctl, protected snapshot and previous host receipt. This is real filesystem failure/rollback testing; it is NOT PID1/systemd239 sandbox, live host installation, independent acceptance or production PASS.

## Implemented behavior

- `manifest` emits exact three unit hashes without host operations.
- `install-stopped` exclusively creates three new candidate unit files, journals intent and creation ownership, reloads unit metadata, requires all stopped and verifies protected metadata unchanged.
- `rollback-stopped` removes only exact-byte, transaction-owned, still-stopped unit files. Changed, foreign, running or unknown files are preserved and cause HOLD. Partial failures preserve journals and private state.
- No start, restart, enable, traffic change, business request, database restore, account creation, writer transfer or Tokyo shutdown entry exists.
- New units have PrivateNetwork=yes and no Install section. They refer to the corrected domestic-r2 preliminary copied root. UID65534 is only the tested copy identity, not an accepted persistent production identity.
- Host/root, exact source+manifest, separate root-private admission, bounded expiry, exclusive attempt directory and lock are required. Admission-file provisioning must occur through the original independently reviewed authority; a claimed GitHub comment id in a local JSON file is not independent authorization.
- The program does not create its own admission or infer it from repository changes, tests or RAM connectivity.
- Host attempt directory: /var/lib/xuanjun-pr99-s09-stopped-install-v1. No such attempt was created by this implementation/CI run.

## Still required before production

This replaces the old template-only gap only for stopped/quarantined unit installation and rollback. Production activation and cutover remain unsupported. Effective bridge endpoint, persistent identity and restricted write set, complete source/data verification, real authenticated upstream acceptance, final consistent snapshot, canonical single writer and original independent host admission remain unresolved. Existing two-round copied health/restart evidence is inherited, not replayed. No completed major migration node is claimed.

Tests cover successful stopped install+rollback, foreign target rejection, changed/running rollback conflicts, injected partial install failure and subsequent owned rollback, missing ownership evidence, mandatory quarantine, exact source/expiry admission rejection, and symlink rejection.

Original protected units, bridge, winctl, Work/current, Korea443, UK masks, Finance timers and Tokyo writer/cutover gates are unchanged.


R2 host evidence: [R2_EXECUTION_RECEIPT_20261017.json](R2_EXECUTION_RECEIPT_20261017.json). Code staging run39004046272, runtime assembly run39004107195, callback/restart acceptance run39004155870 all succeeded. Two rounds × three health200; two callbacks × two rounds invalid requests403; all temporary processes stopped. This is no production or real upstream/signed-success auth approval. R2 copy receipt completed2026-10-17 12:52:15 CST. Source changes are exactly two literal19443→18443 adaptations, preserving the existing loopback domestic bridge18443 and original Tokyo tunnel19443.
