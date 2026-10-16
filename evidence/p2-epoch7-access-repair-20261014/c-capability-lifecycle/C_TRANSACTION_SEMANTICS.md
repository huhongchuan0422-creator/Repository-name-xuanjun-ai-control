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
