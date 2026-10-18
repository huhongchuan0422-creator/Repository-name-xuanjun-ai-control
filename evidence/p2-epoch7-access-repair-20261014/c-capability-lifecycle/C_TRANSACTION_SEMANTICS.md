# Claim successor capability lifecycle, local candidate

This is the changed transaction contract accepted for implementation by original Task5 PR58 comment 6218328313. It is not equivalent to the prior shared prepared-token deadline, and old Schema3/Owner permissions do not authorize it.

## Exact timing version

The signed claim_successor contract must contain timing_policy = PREPARED_START_30S_ORDERED_GUARDS_PUBLICATION_MIN_V1. Missing or different values are rejected. The new compiler is staged only at the independent claim-lifecycle sibling; old resourcebind and claim-successor kits remain intact.

## Prepare, consume, check, publish

1. Original prepare runs every original predecessor, approval, lock, preflight, inner gate and binding check. It creates one prepared handle bound to the actual driver, held lock, context, authorization, original predecessor and exact successor names.
2. The handle has its original maximum 30-second start window and an immutable conversion of the then-signed UTC expiry into a monotonic ceiling. One critical section consumes it before commit checks. Replay or concurrent entry is refused; a rejected or interrupted attempt does not issue another handle.
3. Commit performs the real complete ordered checks again. Start/predecessor/binding/approval work must fit the consumed start window. Full preflight retains its own original 30-second guard. The following predecessor proof must finish within that already-running guard before the inner gate begins.
4. The real final inner gate retains its own original guard and its original check set. Final binding and publication use that existing remaining deadline. No deadline is refreshed by a caller, check failure, retry, clock rollback, or token mutation.
5. Only a private per-invocation ordered record of actual check returns can mint publication once. Its deadline is min(publication mint + 30 seconds, existing final-inner deadline, immutable prepare UTC-to-monotonic ceiling). Current wall time must also remain before signed UTC expiry. Invalid, nonfinite or backward clocks fail closed.
6. The two fixed exclusive publications retain no-follow, owner/mode/ACL, O_EXCL, fsync and protected readback. The first publication and confirmation must succeed before the second can begin. A failed or uncertain write is permanent HOLD, with no completion retry. This is not an atomic filesystem transaction.
7. Time checks precede completion sealing. After successful admission, the original phase guards, writer fencing, D6 census, HOLD save, containment and safety cleanup remain in force. Admission expiry must not revoke already-sealed safety cleanup.

## Preserved predecessor and namespace contract

The exact 1641-byte historical outer record SHA256 a5602f7e70e22edbab683518f21ae8b851369fb61008e7683af1451f4b357055 remains immutable. Historical inner absence, actual predecessor metadata, exact successor absences and the measured predecessor proof are checked by original functions. No old record is deleted, renamed, reset, treated as absent, or removed from resource inventories.

The transaction parent permits only its separately reviewed size/mtime_ns/ctime_ns reconciliation. Before the first actual new outer publication, its fresh proof remains exact; the existing post-confirmation allowance is not activated merely by an attempted-write flag. All other identity, authority, contents and namespace checks remain.

An installation lock does not freeze global processes or databases. Last-check-to-publication races remain possible; later phase guards may HOLD and run original containment. No test promises successful UK execution.

## Finite telemetry

The real coordinator state records bounded fixed stage names, finite monotonic and UTC samples, recorded deadlines and one fixed failure predicate. It excludes private paths, source/configuration buffers, credentials and free-form exceptions. A future separately reviewed launcher must project this new field; the historical launcher does not already cover it. Reporting errors cannot replace the original failure or retry an attempt.

## Required evidence and limits

Focused regression includes two individually valid 20-second guard spans, each individual guard expiry, publication exhaustion, UTC expiry, wall rollback/forward jump, monotonic anomalies, atomic consumption/replay/concurrency, forged or changed private progress/context/predecessor, interrupts before/after mint, partial/unknown publication, D1-D6 and later phase/cleanup boundaries. These are synthetic-clock local checks, not UK performance measurements.

A fresh published compiler source/tree, archive/manifest, authenticated preparation, new private Plan/Seed/Packet, original independent exact approval, and new Owner action authorization are still needed. Current source/artifact pins stay unbound until real publication. No prior approval expiry is extended.


## Owner long-term installation policy — maximum five controlled attempts (2026-10-18)

Applies to **future installation releases, new installer implementations and new approvals for every project**, including a future reviewed P2 revision. A grant covers **at most five** uniquely identified attempts; it does not authorize five runs regardless of outcome. Success terminates the grant. A consumed or expired old grant is never reopened by this policy.

Required authorization binding: exact source commit/tree, Kit and Manifest SHA256, target host and execution identity, operational scope (including installation, activation and bounded safety rollback if applicable), validity UTC window, grant ID, maximum_attempts <= 5, recovery entrypoint and explicit retry eligibility conditions. Any material code or scope change requires a new, independently reviewed bound grant. Platform controls, independent review and production approval remain mandatory.

The implementation must persist an append-only attempt ledger with unique grant_id/attempt_id, monotonically increasing attempt ordinal 1..5, request identity, exact command SHA, Run/Job/InvokeId where available, timestamps, preflight identity and lock proof, per-step checkpoint/output fingerprints, log digest and verified terminal state. Atomic claim and global fencing must prevent concurrent writers and duplicate dispatch, including after crash or restart.

State semantics: READY -> CLAIMED -> RUNNING -> {SUCCESS, VERIFIED_NO_WRITE_FAILURE, VERIFIED_SAFE_RECOVERY_POINT, PARTIAL_WRITE, UNKNOWN, CONFLICT, HOLD}. Only VERIFIED_NO_WRITE_FAILURE or VERIFIED_SAFE_RECOVERY_POINT may make a next ordinal eligible **after** external state is reconciled and the independent retry predicates are checked; the already completed steps must be detected and skipped based on persisted identity/fingerprints. PARTIAL_WRITE, UNKNOWN, CONFLICT and any failure without a proven recovery checkpoint always HOLD, with the original InvokeId queried under a separate permitted query when needed, never blindly redispatched. All five consumed or a SUCCESS is terminal. No overlapping execution, no reset on code change and no backup/checkpoint deletion.

The new coordinator must have offline regression tests for unique ordinals, <=5 bound, first-attempt success, clean failure then next attempt, safe-checkpoint resume without redoing completed stages, exactly-five exhaustion, expiry, changed Kit/host/identity, crash between intent and receipt, two writers, duplicate claim, partial write, UNKNOWN, non-fast-forward history, and crash recovery. Exact matched hosted CI and independently verified artifact must precede any production permission.

**Compatibility hold:** the existing frozen Epoch7 Claim-Successor remains `authorized_successors=1`, `automatic_retry=false`, its 30-second single-use start token and failure fencing remain unchanged. They MUST NOT be loosened by merely changing approval text, a constant or CI fixture. Adapting this transaction is a separate source+manifest+test+artifact+private version binding revision for Dots independent incremental review; the current UK Plan/Seed/Packet, frozen files and old grants are preserved. Until such implementation and review: P2_INSTALL_RETRY_POLICY=ONE_ATTEMPT_FROZEN; FIVE_ATTEMPT_MIGRATION=NOT_IMPLEMENTED; P2_RELEASE=HOLD.
