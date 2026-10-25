## 2026-10-25 — Current fixed caller approval and input contract

The fixed caller now verifies and compiles the exact hash-pinned transaction/call module bytes from the protected installed scripts directory before dispatch. It has no external checker callback; the operation-specific approval is read from the fixed root-0600 approval record, and both old/new archives are read from the fixed protected input names. Production entry still refuses if those inputs or the fresh approval are absent.



At the current source head, the fixed in-process entry is `scripts/community_preview_carrier_handoff_entry.py`. It no longer accepts an external `authority_checker` and is not a CLI. The original unique installation Writer calls `run('execute')`, `run('status')`, or `run('rollback')` only inside its already-authorized process. The caller reads the exact fixed inputs from the existing protected parent; it does not accept caller-supplied archive bytes.

Fixed input files (must already exist; code never creates or downloads them):
- `/opt/xuanjun-community-preview/control-stopped-v1-1d639.zip`
- `/opt/xuanjun-community-preview/control-stopped-v1-005c.zip`

Each must be a root-owned regular file, mode 0600, single-link, opened with `O_NOFOLLOW|O_NONBLOCK`, stable FD/path identity, size at most 4 MiB, and match the exact archive SHA pins above. Missing/mismatched inputs HOLD. These fixed paths are a delivery precondition for the original installer; no transport or download route is created here.

Short-lived approval record:
- Fixed path: `/opt/xuanjun-community-preview/carrier-handoff-approval.json`.
- Must be root-owned regular file, mode 0600, single link, no-follow/nonblocking open, at most 16 KiB, canonical compact sorted-key JSON, duplicate keys and non-finite values rejected, and the same FD/path identity must remain unchanged.
- Exact schema (no additional/missing keys):
```json
{
  "format": 1,
  "host": "iZd7oeikknn1z21sq6ji6zZ",
  "operation": "execute",
  "attempt": "community-update-f13155ed63a3-818fe0b0622c-stopped-v1",
  "old_archive_sha256": "5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4",
  "old_manifest_sha256": "e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a",
  "new_archive_sha256": "2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff",
  "new_manifest_sha256": "d1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd",
  "issued_at": 1800000000,
  "expires_at": 1800000300
}
```
The example timestamps above are schema illustration only, **not a real approval**. The record must bind the exact requested operation and attempt, and satisfy `issued_at <= current_time <= expires_at <= issued_at + 600`. A separate fresh record is required for status or rollback; old B/C approvals cannot authorize this transaction. Re-read from the same FD and recheck FD/path identity, content, pins, operation and expiry immediately before dispatch. Missing, stale, replaced, malformed, or mismatched record is HOLD.

The entry verifies the transaction and call module source SHA before loading/compiling those exact bytes from the fixed installed `control-stopped-v1/scripts` directory. Fixed source pins:
- `community_preview_carrier_handoff_admission.py`: `c23f183753e726dd25a117f730d4180da4f59dcde379591d1dfae5258f74f386`.
- `community_preview_carrier_handoff_call.py`: `a597e426c0cd696621594c8c62f0fc300fc2a67d17e67236891c0421b8f0a5bc`.

Original Writer invocation/result consumption:
```python
from scripts.community_preview_carrier_handoff_entry import run
result = run('execute')  # one call only; consumes fixed inputs + current approval
if result.get('state') != 'SWAPPED_OLD_RETAINED_IN_STAGE':
    # Do not call execute again. Use a separately approved, read-only status call.
    raise RuntimeError('HANDOFF_NOT_ACCEPTED_INSPECT_ONLY')
# After any exception/UNKNOWN: separately approved run('status'), read-only.
# A separately approved run('rollback') is allowed only by the transaction's
# exact ownership/history/absence checks; no automatic rollback or retry.
```
No shell command or direct module execution is supplied because that would create a second entrypoint outside the original Writer. The existing `resume-b-partial.sh` remains unchanged and must not run before handoff acceptance and its separate B-resume gate.

This is source/caller implementation only. The original installer has not been edited or invoked; no approval record is fabricated here. Required fixed input files and a fresh approval must be provisioned by the original installation owner after package review. `REAL_PYTHON_3_6_8=NOT_RUN`.

---

### Exact fixed-entry source hashes at HEAD 29f401f2cef00fb7913858f27daca4378cc2bc22

- `scripts/community_preview_carrier_handoff_entry.py`: 14377 bytes, SHA256 `0c7736143a9405a3395955e589ec0932fa9db30481b3fbc08cbbca001d21f099`.
- `tests/test_community_preview_carrier_handoff_entry.py`: 2243 bytes, SHA256 `aacd02f48996b5d0dac448b81236e3ed4aa157b7cdc5264b35ccea42bc4a06b1`.
- `tests/test_community_preview_carrier_handoff_admission.py`: 34113 bytes, SHA256 `5085c8111211be4cc289e75f0205f395dd6fa380e34ff3b4826b4f42246f9995`.
- CI stage: two verified original artifacts; parse and execute 38 transaction tests (36 previously verified plus 2 actual adapter/fixed-entry on-disk integration cases), 5 adapter tests, and 5 fixed-entry guard tests; exact-HEAD Hosted status must be verified independently.
- External execution constraint: there is no currently bound and independently approved `authority_checker` at the unique installation Writer. The in-process call refuses without it; root/admin identity is not authorization. The current source delivery contains no standalone production shell command, because inventing one would bypass that gate.
- Isolated cross-check: 48/48 on reconstructed e96 source plus scope-equivalent patches under Python 3.13.5; this is not exact-head Hosted acceptance and does not verify Python 3.6.8.

## Issue76 fixed protected entry handoff material — source-only

- `scripts/community_preview_carrier_handoff_entry.py`: fixed in-process `run(operation, authority_checker, old_archive_bytes, new_archive_bytes)`. The existing **single installation Writer** must supply an independently verified and current action-authority checker; root/admin sudo/loginuid identity **alone never authorizes execution**.
- `scripts/community_preview_carrier_handoff_call.py`: existing dispatch adapter, with the correct `rollback` argument order; it must not be executed as an independent shell entry.
- `tests/test_community_preview_carrier_handoff_entry.py` and the fixed fixture's `test_fixed_entry_real_exchange_and_rollback_in_isolated_directory`: test host/authority failure, exact archive pins, true isolated on-disk exchange and rollback via the entry, and duplicate rollback HOLD.
- Fixed UK authority identity: host `iZd7oeikknn1z21sq6ji6zZ`, root through original `admin → sudo -n` with matching `SUDO_USER/SUDO_UID/SUDO_GID` and kernel `loginuid`.
- Fixed protected parent `/opt/xuanjun-community-preview`; original journal `/opt/xuanjun-community-preview/update-journal`; original ENTRY `site-prepare-v1.py`; original lease `community-update.lock`. Existing files are opened `NOFOLLOW` and checked by fd and path identity; no new lock namespace or Session.acquire.
- Original 1d carrier archive: `5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4`; manifest `e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a`.
- Reviewed 005c carrier archive: `2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff`; manifest `d1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd`.
- Existing `resume-b-partial.sh` remains unchanged: 1883 bytes, SHA256 `40c3a03ae9da44d404e2cdf8c58b5507f73825c244d08ddd70b0ceee5a27b42f`. It is **not** part of the carrier exchange and must never execute before the new carrier is independently accepted and B-resume's separate authorization gate is met.

**Fixed in-process call, not a live CLI**:

```python
from scripts.community_preview_carrier_handoff_entry import run
# Called by the independently authorized original unique Writer:
result = run('execute', existing_action_authority_checker,
             verified_old_archive_bytes, verified_new_archive_bytes)
# An uncertain result is not retried; use the original same-entry 'status'.
# 'rollback' is a distinct action requiring its own approval and exact ownership.
```

`existing_action_authority_checker` must verify an actual protected Owner approval for the specific operation/host/attempt in the single original execution chain. It cannot be replaced with a new lambda, asserted flag, simulated permit or saved chat receipt. This exact integration and the contemporary live authorization are external to this source candidate: **MISSING means HOLD**. The adapter is not a production authorization mechanism.

All operations preserve original B-intent, expired permissions, freeze/history and old carrier. `UNKNOWN` means only read-only reconstruction, never automatic execute replay or emergency service start. Python3.6.8 verified environment: `REAL_PYTHON_3_6_8=NOT_RUN`.

---

## 2026-10-25 — Fixed original-entry call material (source-only)

Latest adapter candidate files:
- `scripts/community_preview_carrier_handoff_call.py`: 3461 bytes, SHA256 `a597e426c0cd696621594c8c62f0fc300fc2a67d17e67236891c0421b8f0a5bc`.
- `tests/test_community_preview_carrier_handoff_call.py`: 2838 bytes, SHA256 `87ed798ad7189bc946ad05c8c15217f3089a904cc743216fe3c6b667d62c06cf`.
- Original transaction module SHA256 `c23f183753e726dd25a117f730d4180da4f59dcde379591d1dfae5258f74f386`, 35329 bytes.
- Existing fixed resume script is reused without modification: 1883 bytes, SHA256 `40c3a03ae9da44d404e2cdf8c58b5507f73825c244d08ddd70b0ceee5a27b42f`.

Fixed source pins:
- Host identifier: `iZd7oeikknn1z21sq6ji6zZ`.
- Parent target: `/opt/xuanjun-community-preview/control-stopped-v1`.
- Old archive SHA256 `5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4`; old manifest SHA256 `e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a`.
- New archive SHA256 `2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff`; new manifest SHA256 `d1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd`.
- Historical outer artifacts: old 107650 bytes/SHA256 `a9b034ce85734cf26f4b18058f6840f6434aac0c31322b0664fda7e78eb68956`; new 117926 bytes/SHA256 `f529ca439a9decc95efa4cf4f93391e0ba93719565ad952629d752ef7640ca34`.

Fixed call surface from the already-authorized original entry (not a shell/CLI):
```python
from scripts.community_preview_carrier_handoff_call import (
    call_once_from_original_entry,
    reconcile_from_original_entry,
    rollback_from_original_entry,
)

# original_entry_context must be the original entry's live context:
# parent_fd, journal_fd, ENTRY fd, original lease fd, freshly read identity
# witnesses, immutable old/new archive bytes, and history_refs acquired by
# that original entry. It must supply its existing authority_check callback.
result = call_once_from_original_entry(original_entry_context)
# If result/transport is UNKNOWN, do not call execute again:
result = reconcile_from_original_entry(original_entry_context)  # read-only
# Rollback only after independent review proves the exact module conditions:
# rollback_from_original_entry(original_entry_context)
```

No direct `python module.py` command is supported. The adapter intentionally does not open production paths, manufacture identity witnesses, create approvals, or call `Session.acquire`/B/C hooks. It accepts only the already-held original entry FDs and its own authority verifier. The original installation entry's context-construction call site is not present in this repository source candidate; therefore the adapter is auditable call material, but **not yet proof of a complete live call chain**. Do not invoke it until the original installer binds the real context; do not invent that context from historical artifact metadata.

Safe stop/reconcile contract:
1. Before execute, the original entry verifies its existing authority, exact host, fixed old/new archive+manifest pins, parent/journal/ENTRY/lease identities, original history refs, and absence of transaction/active-attempt conflicts.
2. Call execute exactly once. Only `SWAPPED_OLD_RETAINED_IN_STAGE` with `retry_safe=False` is accepted.
3. Any exception or UNKNOWN is reconciled only through read-only `status`; never repeat execute.
4. Rollback is a separate explicit call only when status proves the current tree and retained stage are exactly this transaction's new/old trees, history and identities remain unchanged, no active-attempt or retained-path conflict exists, and no prior rollback intent/result exists. Any UNKNOWN or identity/history mismatch means HOLD.
5. No B/C execution, permit creation/renewal, intent deletion, service start/stop, or carrier operation is part of this call.

Local/CI syntax command:
`python -B -m py_compile scripts/community_preview_carrier_handoff_admission.py scripts/community_preview_carrier_handoff_call.py tests/test_community_preview_carrier_handoff_admission.py tests/test_community_preview_carrier_handoff_call.py`
Isolated command:
`PYTHONPATH=. python -B -m unittest tests.test_community_preview_carrier_handoff_admission tests.test_community_preview_carrier_handoff_call -v`

Current CI for this call-material candidate must be checked against its exact pushed HEAD. No live execution is authorized. `REAL_PYTHON_3_6_8=NOT_RUN`.

---

## 2026-10-25 — old-to-new carrier handoff candidate (NOT ACCEPTED)

Current source-code candidate (before this documentation-only update): `eca61484c1e9de271001089b28b8078dbb97c818`.
- Tree SHA reconstructed from the eac base tree and exact current blobs for all changed paths: `54dd96b05f74296f58775e969b21199cf7976f5d`.
- Latest push-triggered Hosted run/log/artifact: NOT_VERIFIED through the available connector; empty PR-only run results are not evidence that no push run exists.

- Installed historical carrier: archive SHA256 `5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4`, manifest SHA256 `e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a`.
- New fixed candidate: archive SHA256 `2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff`, manifest SHA256 `d1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd`.
- Exact nested source fixtures are retrieved read-only from original GitHub artifacts: run `40125347707`, artifact `12572781194`, outer SHA256 `a9b034ce85734cf26f4b18058f6840f6434aac0c31322b0664fda7e78eb68956`; and run `40160005255`, artifact `12586026477`, outer SHA256 `f529ca439a9decc95efa4cf4f93391e0ba93719565ad952629d752ef7640ca34`. CI verifies both outer ZIPs and nested archive/manifest digests before using the nested full-tree fixtures.

`scripts/community_preview_carrier_handoff_admission.py` now contains a real isolated-directory transaction candidate: full manifest/member binding, durable pre-intent before staging, exclusive non-overwrite stage creation, nested directory/file fsync, original ENTRY/journal/lock FD/path checks, fixed historical B-intent/approval/freeze/permit identity binding, atomic directory exchange, read-only state reconstruction, and separately journalled one-shot rollback. Failure after exchange or rollback is UNKNOWN and cannot be blindly replayed. Tests use temporary directories only; no production path is opened by a CLI and no B/C hook is called.

**Not accepted for production.** The candidate still requires independent review of the exact final source and actual Hosted logs. A CI status query that returns no push-run rows is UNKNOWN, not PASS. No UK live identity or authorization is inferred from artifact fixtures. No installed carrier has been switched, and historical intent/approval/freeze/permit files have not been altered.

`REAL_PYTHON_3_6_8=NOT_RUN`: no approved isolated genuine CPython 3.6.8 environment is available. Do not install/download an interpreter or use the UK production host for compatibility testing.

---
# STOPPED_HANDOFF_V1 — current verified source candidate and historical proposal

## Current verified status — 2026-10-25 Beijing

This section is the current delivery entry. The historical proposal text below is preserved verbatim as historical evidence and must not be read as the current test/authorization state.

- Current verified **source candidate**: `1d639347f404f952998b3b414a95e48f66571c3c`
- Source candidate Tree: `1317d8c7d5b8bce494cd0a52f8eff317c2f984b8`
- Authoritative Issue76 receipt: `#6388552736`
- Hosted evidence: Run `40125347707`, **139/139 PASS**, `COMPLIANCE_PASS`
- Reviewed dedicated artifact: `12572781194`
- Owner source / isolated-test / review / plan authorization was extended through **2026-10-25 09:00 Beijing time** for this source work.
- **Server installation, B/C execution, backup, stop/start, deployment and other live-site actions remain NOT AUTHORIZED and NOT EXECUTED.**
- Later documentation-only commits do not create a new source candidate and must not be described as a new source validation. In particular, this documentation update is separate from the verified source candidate above.

## Historical 285 proposal text — preserved verbatim

# STOPPED_HANDOFF_V1 — proposal, NOT_EXECUTED

Base: 2853904258ca036a4abcdc2c829278634c45370b / cebc6622540458500c6ea6e25f9bb3bd0decf980.
Only source/review/plan authorized until 2026-10-24 14:00 UTC (Beijing22:00).
No new commit, Tree, build artifact, Hosted run or deployment is claimed.
21 proposed new test methods plus5 necessary original running-path regressions are code only; no test has run.
Old A manifests remain historical285 artifacts; the new V2 manifest/binder is separate.
Builder commit_binding reports a candidate SHA ONLY if every shipped source matches
that exact Git blob and any Hosted GITHUB_SHA agrees. A dirty review copy gets null.
A actual success, original3b6 and f131 image are reused; no install/load/image build here.

## New scope and authority

B/C entry is disabled by default. Only existing admin sudo/loginuid + controlling TTY,
root0600 canonical protected approvals and exact manifest-bound sources can admit actions.
Queued acknowledgements are possible: they are manual action records, NOT independent
Owner authentication, signed servertrust, credentials or new grants.

The new control carrier target is /opt/xuanjun-community-preview/control-stopped-v1.
It MUST NOT replace A's control-oci2330-v1, site-prepare-v1.py or old rollback records.
Original v1 builder now rejects changed sources before producing a falsely named v1.
The proposed v2 builder produces a NEW archive, full bytes/SHA/manifest and complete
direct-sudo wrappers. It does not install files, build/load f131, or execute B/C.
V2 source installation/transport itself remains a separate explicitly reviewed site
write scope; A's successful installation permission is not reused for it.

Fixed source file set is SOURCE_FILES; root700 directories/root600 files. Exact bootstrap
loader SHA and manifest SHA are generated only from actual proposed source bytes.
There are no invented artifact digests or runtime placeholders to execute.
Public delivery metadata contains no config/DB/customer/credential bodies.

## Actual B chain and sources

Original snapshot/validate_clones/clone_run/copy_roots/authorize/resource cleanup remain
byte-for-byte unchanged. The new Session holds BOTH the original ENTRY flock and the
same community-update.lock open-file description continuously, from before B through C.
The Journal duplicates that actual descriptor; it does not acquire a different lock later.

B approval fixed /opt/xuanjun-community-preview/bc-b-approval.json, exact keys:
format(int1), host, mode(STOPPED_HANDOFF_V1), attempt, carrier_manifest_sha256,
issued_at/expires_at(real integer <=600s), freeze_sha256,
actions(exact ["SNAPSHOT","THREE_ISOLATED_CLONES"]).
Original writer-freeze-reference.json must originate from actual separately reviewed
maintenance responsibility. The program does not stop/start old, fabricate this witness,
or infer all external writers are frozen solely from old.running=false.
It independently verifies old fixed ID/name/image/OCI, original isolation/mounts,
socket gone, bounded full data/config trees and unchanged immutable snapshot.

Each B stage needs an actual TTY acknowledgement. It publishes the original canonical
stage permission (new root600 EXCL), calls the original stage, persists actual result
and permission hashes, then archives/removes ONLY that identical permission.
A two evidence fields remain untouched; B permissions use actual freeze/snapshot hashes.
Existing active permissions, partial B intent, old backup directory or clones HOLD,
are preserved, and cannot be replayed or silently retried.

Three actual original clone calls produce protected full-body records:
clone-restore-old.json, clone-verify-f131.json, clone-verify-downgrade.json.
Each binds exact attempt/image/code SHA and actual original captured logical result.
Record creation follows the original call, with pre/post stopped/freeze checks.
All three full results must match each other and clone-results logical SHA.
C also rereads private-manifest, all immutable snapshot files and actual current two
trees under the SAME lease. A boolean or root JSON by itself is not proof.
Historical clone evidence remains protected on-host, not publicly uploaded.

## Explicit stopped C path

prepare_stopped records current.running=false without ever fabricating true.
It versions the mode and attempt and computes its own plan SHA. Default prepare,
running guard and Update.run remain semantically unchanged.
A separate current C approval at /opt/xuanjun-community-preview/bc-c-approval.json
must bind format1/host/mode/attempt/carrier_manifest_sha256/plan_sha256/real <=600s
issued_at/expires_at and exact C_ACTIONS.
After B prints its safe plan SHA, missing C approval waits at most120s (only absence).
An existing malformed, denied, expired or mismatched approval immediately HOLDs.
No copied chat text, CLI/body boolean or latest version creates permission.

The protected handoff record binds host/mode/attempt/plan/actual approval SHA/evidence
semantic hashes. Journal records bind planSHA, C approvalSHA and protected reference
body+identity digest. Same-byte replacement therefore changes the binding.
PREPARED -> STOPPED_HANDOFF_ACCEPTED -> OLD_RENAME_INTENT -> OLD_RETAINED ->
NEW_RUN_INTENT -> NEW_KNOWN. It never logs fictional OLD_STOP_INTENT/OLD_STOPPED
or starts old merely to satisfy a running precondition.
Real references, immutable snapshot/clone bodies, exact current old ID/image/route/name,
socket and current trees are checked before and AFTER durable intent, adjacent to
rename/run. Another writer reviving, socket reappearing or reference replacement HOLDs.
Once a known new container legitimately starts writing, current trees are no longer
required to equal the old snapshot. Backup immutability, live protected identity,
fresh exact HTTPS version and old/new single-writer checks continue.
No cross-Docker or cross-DB atomicity is claimed.

UNKNOWN or partial/mismatched history does not resume/rewrite/retry. Recover is a
separate explicit entry, requiring existing exact history and KNOWN_FAILURE/new ID,
the same plan/approval/immutable backup. Unknown new run or stop-new never starts old.
A new process may inspect/recover existing history, but cannot rerun B or accept a
new stopped handoff based only on a record. The B->first-C path requires bdone in the
actual Session that executed B under the continuously held lease.

## Fixed budgets and operational risks

Original4GiB/20000entries per root, depth32, relative path1024, each tree120s,
clone CLI120s, original stdout16KiB, source131072B, private manifest8MiB remain.
Whole Session <=600s plus exact individual approval/freeze deadlines; unknown clocks HOLD.
Snapshot capacity is original7T+1GiB /7N+128 inodes, plus daemon/tmpspace.
CLI kill/reap does NOT prove a daemon clone or operation was cancelled.
No automatic old start on any B/C HOLD; old may remain stopped. This outage risk,
probe residue handling, exact maintenance responsibility and separate C action approval
must be specifically accepted before any future site run.

Old2330 lacks backend observed_at. Original HTTPS/recovery health still demands real
fresh time; process restoration can remain HOLD and must not be called ROLLED_BACK PASS.
No synthetic timestamps, private proxy spoofing, OCR enablement or payment grants.

## What has NOT been done / remaining values and responsibility

Source integration, Python compile, PTY/whole-entry tests, the full related
release/checkpoint/composition regression set, manifest build and Hosted CI are now
required evidence for this source candidate. They never authorize site installation,
B/C, backup, stop/start, official preview, OCR or WeChat publication. The unknown old
stage_bc draft remains outside this integrated path and must not be overwritten.

The real controller source binding is byte-exact: after the final cleanup ownership fix,
`scripts/community_preview_update_checkpoint.py` SHA256 is
`e9029ca3e0c36fb1656995fcbe77f46739ee7abfc490adbd0cf4808f0e41b826` and
`community_preview_update_composition.PINS[controller]` must equal that value. Any later
controller byte change requires a fresh pin and the complete related regression set.
Cleanup ownership is one-shot and cleanup uncertainty is terminal. Journal, Session,
LiveBindings and Composition clear each owned descriptor/object field before invoking
`close`; an exceptional close sets persistent `cleanup_unproven`, continues the first
pass across the remaining owned handles, and every later close call stays HOLD without
retrying any consumed integer. This covers both pre-effect close failure and the case
where an exceptional close already released the fd and its integer was recycled to an
unrelated replacement resource. Composition and compose-exception cleanup attempt
Journal and LiveBindings independently and aggregate cleanup UNKNOWN instead of
short-circuiting the second owner. Journal.from_original_parent explicitly retains a
successfully constructed Journal until its temporary parent descriptor is closed; if
that temporary close is unproven it attempts Journal cleanup and returns only
JOURNAL_PARENT_CLEANUP_UNKNOWN, never the constructed object.

Future Owner/coordinator inputs once, before exact stage approval:
new protected v2 installation and actual hashes; fresh fixed old/current and route
binding; whole-writer maintenance responsibility and actual root freeze witness;
real protected data capacity; B actual snapshot/three clone evidence; final plan-bound
C approval and truthful rollback-health limitation decision. No private input upload.
Physical B/C/backup/stop/start/update/WeChat/OCR remain separately unapproved.

## Source-only installation admission (not executed)

The generated carrier is **not an installer**. Any later separately approved root installer must create the fixed `control-stopped-v1` directory chain as root-owned mode `0700`, create every listed regular file as root-owned single-link mode `0600`, verify the manifest and file hashes before import, and publish atomically. A generic ZIP `extractall` is not an admitted installation path. The existing A `control-oci2330-v1` tree is never overwritten.

The wrapper shell is intentionally login-shell-preserving: its outer shell return code is not acceptance. Acceptance requires both a structured Python `BC_RESULT` record and a matching `SUDO_CHILD_EXIT=0`; the wrapper also emits `BC_OUTER_NOT_ACCEPTANCE` to make this explicit. B/C server installation, snapshot, stop/rename/run/recovery and deployment remain separately authorized现场 actions and are not performed by this source delivery.


## Fixed V2 carrier installation entry — source candidate only

The carrier itself remains the independently reviewed frozen bytes: `control-stopped-v1.zip`
SHA256 `5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4` and canonical
`manifest.json` SHA256 `e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a`.
The installer is an external delivery tool and is not inserted into that carrier ZIP.

`scripts/community_preview_bc_install.py` accepts only those exact package/manifest bytes. It validates
the complete ZIP member set, duplicate names, traversal/absolute/backslash paths, Unix regular-file
mode, DEFLATE method, per-file size/hash and the internal manifest before any destination write.
It publishes only the fixed new `/opt/xuanjun-community-preview/control-stopped-v1` target. Existing
final target or deterministic `.installing-<archive-prefix>` partial state is HOLD; A's
`control-oci2330-v1` is never opened for write or removed. Writes are dir-fd relative with NOFOLLOW/
EXCL, private directories are 0700 and files 0600, all file/directory data is fsynced, the complete
temporary tree is reverified, and only then is the sibling directory atomically renamed to the final
name followed by parent fsync and final reread. Generic `extractall` is not used.

Failure before publish leaves no final `control-stopped-v1` success name. A `.installing-*` directory
may remain as explicit inspection evidence and blocks automatic retry; its inspection/removal is a
separate future root action, not automatic recovery. Tests use a temporary non-production directory
and explicit identity fixture only; they are not evidence that root installation occurred.

Future Owner operation material (NOT EXECUTED here), from the reviewed repository root after separately
placing the exact two frozen input files at protected absolute paths:

```sh
sh deploy/community-preview/install-stopped-v1.sh /ABS/PATH/control-stopped-v1.zip /ABS/PATH/manifest.json
```

The shell invokes `sudo -n python3 -I -B -S` and the installer independently requires the fixed UK host,
root effective identity, original admin sudo environment and matching kernel loginuid. A successful
install result only establishes carrier bytes at the new V2 path; it does not authorize or execute B/C.

## Fixed installer execution binding (source-only, not executed)

The reviewed wrapper never imports the installer from the current working directory. A future separately reviewed Owner preparation must place the exact reviewed installer at fixed `/opt/xuanjun-community-preview/install-stopped-v1.py` as root-owned regular single-link mode `0600`. The wrapper's sudo-side Python bootstrap opens that exact absolute path with `O_NOFOLLOW`, verifies regular/nlink/owner/mode/full identity and the reviewed installer SHA256, reads the bytes through that same verified descriptor, rechecks path identity, and compiles/executes those exact bytes. CWD-relative Python source is not admitted.

Atomic publish records the transition immediately after successful `renameat2(..., RENAME_NOREPLACE)`. Any later parent `fsync`, final path/tree verification, temporary-directory fd close, or install-parent fd close failure is `V2_INSTALL_PUBLISHED_UNKNOWN`: `target_published=true`, `retry_safe=false`, with truthful `parent_fsync_completed`. The installer never auto-removes the published target and never retries the install under that condition. Pre-publish failures keep `target_published=false`; an empty concurrently-created TARGET is still protected by `RENAME_NOREPLACE` and must retain its original inode.

## Final install-state consumption contract — source only

Immediately before the single `renameat2(..., RENAME_NOREPLACE)` attempt, the installer records that publish was attempted and retains the verified TEMP directory identity. If the publish call raises — including an exception after the kernel may already have renamed the directory — classification never depends on a following Python boolean assignment. One bounded no-follow identity reconciliation under the already-held parent fd checks TEMP and TARGET: the original TEMP identity still present proves this carrier was not published; the same identity at TARGET proves publication; any missing/mismatched/non-directory/read error is `V2_INSTALL_PUBLISHED_UNKNOWN`. The foreign empty-TARGET race therefore remains a nonpublished HOLD with its inode unchanged because the original TEMP identity is still present.

Every `V2_INSTALL_HOLD` is conservatively `retry_safe=false`, including a partial `.installing-*` directory. A published or unprovable result is also never automatically retried or removed. Parent close is attempted once; a close failure after an existing `PublishedUnknown` does not replace the original UNKNOWN, while a close failure after an otherwise successful publish becomes `PublishedUnknown`.

The shell entry consumes the install result separately from B/C. It admits success only for child exit 0 plus exactly one complete newline-terminated JSON success receipt with the exact frozen archive/manifest/install-root fields, `publish_attempted=true`, `target_published=true`, `retry_safe=false` and `parent_fsync_completed=true`. Nonzero exit, missing/truncated/malformed/oversize/multiple receipts become `V2_INSTALL_ENTRY_UNKNOWN` with `inspect_only=true`, `retry_safe=false` and `bc_admitted=false`. There is no automatic install retry and no automatic B/C invocation. SIGKILL/OOM are not promised to emit a receipt; their absent/nonzero result is simply UNKNOWN/inspect-only.

## Final installer receipt binding correction — source only

The reviewed installer SHA256 is `646c7f78e275afe5807d9c0572356607db9dc0ca917f2acb10012e5fc85dd4a7`
and the reviewed wrapper SHA256 is `c9d7b50c0b491bb960cc4181e7233435590ab7238de20a2f4e2336e7bedf88fc`.
If a successful install result is converted to `V2_INSTALL_PUBLISHED_UNKNOWN` solely because the final
install-parent close is unproven, the already verified `temp_identity_sha256` from that success result
is copied verbatim into the UNKNOWN record. A 64-hex digest is never treated as an identity tuple and
hashed a second time. The parent descriptor is closed exactly once; an exception after a real close
remains UNKNOWN and the consumed fd integer is never retried.

`V2_INSTALL_HOLD` output is produced by the installer's production `hold_record()` formatter, including
`retry_safe=false`. Receipt-consumption tests execute the actual second inline Python parser extracted
from the reviewed shell itself. Success requires exactly one complete success receipt plus exit 0;
nonzero, missing, truncated, malformed, multiple or oversized receipt input remains inspect-only UNKNOWN.
