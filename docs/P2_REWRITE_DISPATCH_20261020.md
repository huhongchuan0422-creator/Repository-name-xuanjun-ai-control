# P2 rewrite coordination record — 2026-10-20 Asia/Shanghai

This is an evidence index under existing PR17, not another queue or execution authority. The integration window owns this file and packaging; component developers retain their respective source directories. No extra manual independent review is added by this rewrite. Platform checks and data protection remain applicable.

## Source rules actually read

- docs/DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md (including later 5/15/30 thresholds and minimal complete functional node rules)
- docs/development/P2_RETAINED_RECOVERY.md
- docs/THREE_NATIVE_ENTRY_HANDOFF.md

The Owner explicitly replaced the old whole-install exception with this rewrite. Old files and production history remain retained.

## Verified component evidence

| Component | Branch | Observed commit | Relevant CI | Meaning |
| --- | --- | --- | --- | --- |
| Artifacts | repair/p2-artifacts-20261020 | 704bfff1b0eabeaff1205d1261bd0b72463d41b1 | 39301033043 success | Component CI; not UK integration acceptance |
| Runtime | repair/p2-runtime-20261020 | fb59b80ed2d1cf572d61e84f06ebfa7dec0e0484 | 39302022007 success | Latest component CI; final readiness not inferred |
| Coordinator | repair/p2-coordinator-20261020 | d02f2a0ecfd4d9bcc28fa388de7535c13177bb95 | 39302071135 success | Latest component CI; execute CLI adapter still unavailable per its documentation |

Coordinator prior failed CI 39302061956 remains history. No status here equates CI success with complete P2 installation. Component heads are snapshots, not permission to merge moving branches.

## Exact execution environment contract

UK host: iZd7oeikknn1z21sq6ji6zZ. Host Python: /usr/bin/python3 3.6.8. Existing Docker image: xuanjun-p2-sandbox:prep-base-20261013; container Python previously observed as 3.11. Packaging must pin and verify the actual image/interpreter identity before acceptance, without repeating already verified delivery files.

Host bootstrap must remain Python 3.6.8 compatible and may only stage/read receipts and invoke the fixed isolated Docker command. Components should run explicitly inside the pinned Python 3.11 container, not be accidentally imported by host Python. Python 3.12 CI is extra portability evidence, not a substitute for target Python 3.11 execution. No system Python replacement.

Preserve network=none, cap-drop=ALL, no-new-privileges, read-only root filesystem, pids/memory bounds and private tmpfs. Only independent isolated storage is writable; no production DB/Signer/Registry/cloud credentials/host Docker socket mounts. Child-workload write access to coordinator and other component state must be resolved explicitly: component directory names alone do not isolate same-UID processes.

## Current integration gaps and next actions

1. Integrator: pin the three final component commits; integrate by exact file ownership; adapt request/root/receipt/deadline schemas; supply fixed artifact/runtime adapters to the coordinator. The coordinator CLI currently documents ADAPTER_UNAVAILABLE. This is not a complete installer yet.
2. Runtime developer: documentation currently checks log bound only on initial observation and later calls. Verify that an unattended child cannot grow logs indefinitely. Continuous bounded collection/termination evidence is still required. Process-liveness health is not application readiness. Document descendant escape limits accurately.
3. Coordinator developer: document and test actual authoritative lifecycle event ingestion, timeout eligibility, 30/60 method-change state, true subprocess interruption/restart and reuse of existing authority interfaces. Local attempt counts must not be represented as production Grant authority.
4. Integrator: map all original P2 functions. Current artifacts/runtime/coordinator components do not implement host migration, real task intake, production transport/authority, application readiness or end-to-end autonomous chat wake. Mark each function implemented, reusable integration pending or unavailable; no silent removal.
5. Integrator: build a minimal complete artifact-install -> actual application start -> application response -> intentional next-node failure -> restart/recover acceptance path, preserving prior files/receipts and proving no duplicate side effects. Run inside the real UK target image. This is isolated acceptance only.
6. Integrator: package exact code and manifest, one Python3.6-compatible UK host command and durable receipts. Do not call the new path production installation until actual production bindings and accepted functional scope exist.

No new UK operation was executed by writing this record. No continuing background supervision is implied. Unknown or partial effects require reconciliation, not blind dispatch. Shared grants and original DB/WAL are never reset or deleted.
