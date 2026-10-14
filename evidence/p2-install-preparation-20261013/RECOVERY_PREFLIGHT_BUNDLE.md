# P2 consolidated recovery preparation — not a release approval

Owner authorized dot's bounded source maintenance on 2026-10-14 after the prior
developer's stop/handoff. Use the existing branch and expected-head update.
This does not grant a canonical runtime lease, change the ledger, restart a
runner, or permit concurrent installation. Owner performs UK commands manually.
The one review thread remains PR58 request 6159620928; PR17 remains the tracker.
Do not submit each observation as a separate review request.

## Frozen baseline retained

- Original artifact: 11865804223, 102 runtime files.
- ZIP: 099271480e82f28d8d4a0f1ceb9c2f2e4efc493af26dbaa9e106bfaf785f2dd5.
- Archive: c2d593d662fbce4a0c2fa454cc4a18dbec327c0bd0bf3d6d72849d9a5a79970d.
- Manifest: 9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3.
- Plan, 22,468 bytes: ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a.
- Original postchecker: e83b769b64547d75e130423b88684459d62f247ee1bd9b604d6740e3445bdb78.
- Recovery predecessor: eadadca08d5e9aa471db72042214d24d468f0799.

The original first-install approval was consumed by a failed installation.
The actual transaction remains HOLD / epoch 2 PREPARED / staged generation.
Never rerun first install or delete the receipts, retained NSS resources,
database, backup, generation, sidecars, caches or activation journal to pass a gate.

## One bounded source revision

1. Preserve all 13 observed CPython 3.6 smoke caches. Require the exact observed
   file set/hash, root ownership, 0444 mode, source binding, header metadata,
   original staging-path shape and every code-object field reproduced by compiling
   the already hash-verified source. Compilation/deserialization does not execute
   cached code. Extra, missing, changed, symlinked or unbound caches fail closed.
   The raw source package still cannot contain any bytecode.
2. Preserve the observed empty WAL and exact SHM of the original source database.
   Require the original database hash, WAL length zero, pinned SHM bytes, owner and
   mode. A journal, nonempty WAL, changed SHM/main DB or missing member is HOLD.
   This narrow source exception does not apply to the backup or staged generation.
   Include all sidecars in the FD-holder scan and compare the file sets again
   after preflight. File presence is not evidence of an active writer; absence of
   observed holders is not a perpetual lease grant.
3. Inspect backup/generation SQLite content using private temporary copies, never
   open the original production files through SQLite during verification. Preserve
   their exact manifest/hash comparison and remove only the newly created scratch
   copies. Main database and sidecar evidence is included in the snapshot digest.
4. Reject unclassified source/release files. Verify original installed metadata:
   root:root, directories 0555, the two declared helper executables 0555 and all
   other installed files 0444. Installed manifest bytes must match the original.
5. Require the original `complete_install_executor.py` sibling to exist with its
   pinned hash and protected authority during verify-only, before any recovery
   effect. Recheck it when post-install validation actually runs.
6. Require the new independent approval on PR58. After its network read, repeat
   the complete snapshot under the same existing installation lock; any change
   blocks before resume. The old first-install approval remains inadmissible.

No original package byte, plan hash, shared ledger source or workflow is changed.
No Work/Codex/model endpoint is called by this revision. Existing preflight does
bounded DNS/port availability and CLI checks; verification also uses temporary
inspection files. `effects=0` describes installation effects, not absence of all
reads, scratch I/O or transient availability checks.

## Bound local developer results and limits

Recovery executor SHA256:
`a3c183128cbdd0e404e2eba47951f2fd4936aaa549a4dc5e6dea29e3c5fafdad`

Unchanged recovery regression file SHA256:
`bd374005cae2e5137db631177028a4e7128f39c78551ea122d0e46472c01536a`

New retained-evidence regression file SHA256:
`3dad0584987d6e7e835c2a5f86407c45cb42e604f3da4e1bb21e328a56f7d194`

On Python 3.6.8, run as two separate script entrypoints in an isolated root-mapped
user namespace: existing impacted recovery tests 13/13 PASS; new tests 28/28 PASS.
Fixtures cover cache semantics, tamper/header/path/extra-file negatives, exact
release modes, missing/drifted postchecker, sidecar drift/scope and copy inspection,
approval destination and state change during approval. Original tests retain the
real renderer/24 provision bindings and ActivationStore plus mocked external
effects/partial failures/duplicate-attempt rejection. No production changes occur.

The local 3.6.8 build uses GCC 14.2 and SQLite 3.46.1; it is not the UK runtime.
`python -m unittest discover` crashed with exit 139 in local ctypes `_reset_cache`;
standalone `python -c 'import ctypes'` reproduced the crash without repository code.
The two direct entrypoints succeeded. This environment fault is NOT a passed
aggregate check and must be disclosed; it does not certify UK ctypes/dependencies.
The fresh UK verification and any independent reviewer tests remain required.

Reproduction (absolute paths, same original artifact and plan):

    P2_SOURCE_ROOT=/absolute/xuanjun-p2-package \
    P2_ORIGINAL_PLAN=/absolute/protected-core-install-plan.json \
    python3 -B evidence/p2-install-preparation-20261013/test_recover_exact_hold.py
    python3 -B evidence/p2-install-preparation-20261013/test_recovery_retained_evidence.py

## Single complete review package checklist

- [x] Exact unchanged baseline archive/manifest/102 file hashes rechecked locally.
- [x] Four preparation defects addressed together, with approval-boundary negatives.
- [x] Impacted direct-entry local Python 3.6.8 tests, with the discovery failure disclosed.
- [ ] Published commit/expected-head update and existing exact-commit CI receipts.
- [ ] Fresh UK complete verify-only snapshot for this code hash (not predecessor).
- [ ] Current runtime/prerequisite/process/scheduler/dependency reconciliation.
- [ ] Other independent reviewer decision on the complete delta and UK snapshot.
- [ ] Final Owner one-resume command bound to the approved code and snapshot.
- [ ] Same-transaction failure containment/rollback instructions and exact receipts.

This document is preparation, not a staged or partial request for approval. Submit
the whole package once the installation-before-effect evidence above is assembled.
The author of the prior recovery candidate cannot independently approve that
candidate, and dot cannot approve its own changes. The independent reviewer must
give one complete decision or the complete remaining blocker list.

## Execution and failure boundary

Retain original one-attempt behavior, existing lock, exact HOLD/cutover checks and
epoch 2 transition through original ActivationStore. Reuse resources without
reinstalling NSS, restaging/cutting over DB again, overwriting release or replaying
historical notifications. A fresh snapshot and a NEW exact independent approval
must match immediately before effects. Unknown state always stays HOLD.

Failure fencing and bounded rollback remain integrated into that one resume.
There is no separate public rollback CLI and no claim that all NSS resources can
be removed. Retain data/prerequisites; stop any activated runtime prefix; restore
only authenticated provisioning where safe; preserve legacy masks. Nested failure
or uncertain effects means HOLD and manual reconciliation, never blind retry.
If independent review requires a different rollback deliverable, resolve it before
giving Owner an executable resume command rather than inventing a cleanup command.

## Installation is not production acceptance

Successful postchecked installation still leaves Relay/Outbox delivery ACK,
authorized real model E2E, complete P2/P3 and actual failure recovery acceptance
pending. No quota-consuming model operation is authorized by this source repair.
UK Runner isolation must remain until queued work and old bindings are reconciled.
The runtime guard is temporary across reboot. Do not advertise global writer
exclusion from the finite observations or restart an old window/runner.

## Consolidated B1/B2 follow-up to PR58 review 6161796086

The dfd96068 candidate received HOLD for two fail-open directory collectors.
This delta replaces both os.walk collectors with one bounded FD-anchored collector:
all ancestors opened O_NOFOLLOW, child names bound with dir_fd, exact lstat/fstat
identity checks, bounded depth/entry/file bytes, successful before/after directory
listings, and propagated permission/ENOENT descendant/read errors. Unknown
symlinks, devices, FIFO/socket entries and cross-device descendants are rejected.
Only a genuinely absent optional fixed root is accepted, after readable parent
absence checks; missing descendants after a positive observation remain errors.

Notifier checks additionally validate the actual cgroup v1 name=systemd mount,
existing readable controller/system.slice and inactive/masked state before and
after collection; services require MainPID=0. Timers have no MainPID property;
that explicit timer-only case still requires inactive/masked and the same complete
cgroup absence/empty proof. Every present group must have a readable empty
cgroup.procs. Other cgroup control files are classified but not opened or written.

New source SHA256: 45affbb3b9298999d7e71bfb93b3ef5cb824464000ac78a927fd7c388614d74e.
New test_recovery_scan_errors.py SHA256:
7f53164b8ef969fdf801e87b90d3d280031e9197ce04dec5c8297b5935c1e97a.
Python3.6.8 root-mapped isolated new tests: 38/38 PASS. Prior retained-evidence
suite: 28/28 PASS on this delta. The old13 suite rerun locally crashed BEFORE tests
at the previously disclosed ctypes _reset_cache environment fault (exit139), so
no new local13 PASS is claimed. Owner UK prior13 PASS remains historical only.
UK must run all13+28+38 against the new exact candidate and complete verify-only;
no production operation is requested. The prior snapshot cannot authorize this
new code, even if its data digest stays unchanged. Original102 artifact, runtime,
plan, leases, workflows and installation effects are unchanged.

Keep B1/B2 in one delta response to the same PR58 review, after UK evidence arrives.
Do not submit partial defect-by-defect approvals or rerun the original installation.
