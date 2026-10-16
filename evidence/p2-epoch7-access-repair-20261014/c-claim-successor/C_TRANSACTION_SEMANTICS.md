# Claim-only successor transaction contract — review checkpoint

Status: locally implemented contract submitted for exact source review. This document grants no host action, new approval or execution permission.

## Fixed predecessor and invariant scope

Parent outer name remains epoch7-recovery-sequence.json, original bytes 1641 / SHA256 a5602f7e70e22edbab683518f21ae8b851369fb61008e7683af1451f4b357055; binding SHA25673ca008c00b9cf2b80a5b368ceebf6b3d5bf9c7278566d925355b3c12fc1e2ba; state SHA256bbe789b615ee9237626263ea8cfc0c7d39b79c8feb0f62d303e9d16238c6bff7. Original complete review is6212022929 /88023d5e6d4d93d5f263892f900caf6ced21d1f4f038d01419e4ee854aa94a48. Original plan eae1e341408b821af0902a225021394d6f2e91a6c557bafe3dcd67a29c3b08da and seed6de7d12246826388949723e9238cd464686e6e86847187946837df927c97a550 remain inherited evidence, not automatically new authority.

Accept only canonical exact parent bytes and full binding, HOLD / CLAIM_INTENT / admission / create_inner_attempt, admission UNKNOWN, receipt OBSERVED, no interruption, completed=[], phase_evidence={}, containment=[], secondary_errors=[] and no automatic replay flags. Original inner epoch7-recovery-execution.json must remain absent. Parent is only read; never rename/delete/replace/reset it.

One fixed successor namespace is proposed, with no caller-selected names:
- epoch7-recovery-sequence-successor-a5602f7e70e22edba.json
- epoch7-recovery-execution-successor-a5602f7e70e22edba.json

All context/approval, journal, authority, resource/phase-intent, failure/receipt and containment consumers must bind these SAME names and the complete parent hash. Historical predecessor references retain the OLD names. No global constant mutation or runtime monkeypatch changes the old coordinator.

107 runtime payloads and 16 business phase behavior/order remain unchanged. New code is limited to predecessor validation, new exact approval binding, successor admission/publication and necessary name propagation/diagnostics.

## New approval contract

The original complete approval is inherited plan evidence only. A new exact full approval must bind predecessor raw size/hash/binding/state, old review identity, original plan/seed/body, selected reviewed successor implementation/source/manifest, fixed new names, complete effects scope, one successor, automatic_retry=false, and an exact UTC expiry. Actual new review ID/full-body SHA and immutable implementation pins remain UNBOUND until real publication/review; absent/unbound values refuse before effects.

The same original approval-fetch mechanics are retained: exact public HTTPS review before install lock and again under the same existing install lock. Subsequent checks use that exact authenticated cached body and recheck its UTC expiry; no hidden additional network. Monotonic expiry also prevents a backward wall-clock jump extending an in-process prepared capability. Exact timestamp grammar and clock bounds are validated, not supplied by an arbitrary callback that returns True.

## API and ordering

The ordinary frozen resume entry cannot adopt this predecessor. A separately selected, reviewed successor path is required.

prepare_successor(driver, contract):
1. Require one unused driver and exact new approval/contract; verify the same original install lock is held.
2. Authenticate the protected predecessor, original inner absence and both successor absences. Check original inputs/plan/seed/context and all existing admission bindings.
3. Execute the complete original prepare-time preflight and retained gate (including the full inner gate). No claim is created.
4. Return a process-local prepared capability bound by object identity to this driver, lock and contract, exact context/input hashes, the authenticated new review, fixed journal names, and a monotonic expiration no later than30 seconds after preparation or the approval's mapped expiry. It is not serializable/exportable or transferable between drivers/processes. No token is production authorization by itself.

commit_successor(driver, prepared):
1. Consume the prepared object before any operation; a second use always refuses. Require same driver/lock/context/new approval, unexpired wall-clock and monotonic limits, unchanged parent and absence of old inner/new claims. No prepare-success flag can satisfy a live check.
2. Execute all original current admission guards AGAIN under that same lock: original binding/locked approval, full preflight, preserved/runtime/activation/targets/generation/sandbox checks, complete writer exclusion and final full inner gate. The original guard's30-second deadline remains; the effective commit deadline cannot exceed either that deadline or the prepared expiry. No retry, extended deadline or PID exemption.
3. After the final successful real-time recheck, only bounded pure serialization and the two fixed exclusive claim publications/readbacks are allowed before phase admission. Recheck lock/context/expiry immediately before each write. Protected descriptor ancestry/authority/CAS checks and fsync/readback remain mandatory. These checks are not a substitute for step2.
4. First publish and confirm the successor outer CLAIM_INTENT via existing O_EXCL machinery. Then publish and confirm successor inner ADMITTED via a narrowly guarded prechecked-commit method that accepts only this exact single-use capability. It must not rerun a census between the two writes or accept a caller-created dictionary/boolean as authority. Both raw payloads must match those derived from the same exact approval/context.
5. Only after BOTH publications are confirmed is full admission recorded and the original16 phases entered. All original later phase guards, journal writes, readbacks and containment remain active.

The install lock does not freeze global PIDs or DBs. The reviewed contract must explicitly accept or reject the bounded check-to-publication gap; context/hash equality alone is never described as a current-state proof. The before-write held-lock/deadline proof is necessary but cannot make these two filesystem publications atomic.

## Failure semantics

Before any claim write, a refused/expired/failed check creates no successor claim and starts no phase. Existing original preflight private DB temporary copies and other disclosed read effects remain possible.

Once the first publication begins, every error, timeout, interruption, uncertain write or failed readback is terminal for this successor. Do not retry a write, create the second file after any first-write uncertainty, adopt a partial file, delete/rename the old or new record, or automatically start another attempt. Keep first error and all known created/confirmed/unknown publication states. Any existing successor claim prevents a later invocation.

Two files are not atomically published. If the first is confirmed and the second fails, preserve the first and stop before phases. If neither persistent record can be confirmed after a write attempt, absence cannot be interpreted as unused permission: the terminal report and human ledger require manual reconciliation. No software can prove an interrupted pre-create syscall never occurred solely from later absence; this limit is explicit, not a restart loophole.

Later phase failures preserve the original HOLD/containment rules. No claim is made that all future census races will be caught before publication.

## D6 exact same-census classification

The production predicate remains PID equality AND DB-map equality. Both comparisons must actually be evaluated to distinguish PID_LIST_CHANGED, DB_MAP_CHANGED, BOTH_CHANGED. A failed DB read is UNKNOWN_DB_OBSERVATION (preserve the original read exception), never DB_CHANGED. Preserve both Boolean results when available, plus bounded counts/hash-only summaries; no raw process names/argv/environment/private paths/DB content. The two observations come from the original census, no extra scan. No branch is exempted or admitted on UNKNOWN. A failed last preclaim census prevents claim publication; later phase failure retains existing containment.

## Required narrow tests and remaining bindings

Test exact predecessor success and each raw/schema/binding/state/plan/seed mutation; existing old inner or either new claim; changed names at every consumer; old-review reuse and missing/expired new approval; changed lock/context/capability/replay; PID-only/DB-only/both and DB-read-error; post-prepare changes caught by real commit checks; first/second write partial/unknown/readback failure; control interruption/deadline and no second completion; later-phase census failure using unchanged containment. End-to-end must traverse genuine factory/authority and new names, with explicitly synthetic host boundaries. Old source/107 payload and16 phase behavior invariants remain independently checkable.

No new review, compiler manifest, source commit or executable command is invented. Those are later publication/binding gates, separate from local semantic tests.

## Explicit implementation clarifications

The expiry field is admission_expires_at_utc: it bounds preparation and both confirmed claim publications. Only the real completed capability seals admission. It does not revoke the original independently guarded containment or receipt-saving authority after an attempted or admitted transaction. A partial claim may still save HOLD after admission expiry. No new production phase starts unless both claims and the exact capability have completed. This distinction must appear in the new approval.

The predecessor creation changes the fixed transaction parent's measured size/mtime_ns/ctime_ns. The successor collection retains actual inventory and all actual metadata; it requires the same dev/ino/uid/gid/mode/nlink, all original children exactly, and one exact fixed predecessor. Only those three mutable fields of that one directory may differ from historical evidence; every other directory remains exact. The measured proof is separately bound into the new plan and approval. This proves the finite current relation, not that only the predecessor caused the timestamp changes. ACLs are freshly checked against the original no-extended-ACL rule, with no invented historical ACL values.

Predecessor-file integrity is checked during prepare/commit and ordinary phase boundaries and all17 resource checkpoints. The cheap per-chunk receipt method retains the original immutable authority/lock checks without new file scans. A detected predecessor drift stops ordinary progress; it does not create a new blanket condition suppressing the original independently attempted safety containment or HOLD-save path.


## Completion attestation and publication observations

Prepared capability identity and transition history are kept in a private process-local registry. Public stage/confirmed/used fields cannot manufacture completion, clone the capability, or seal admission. Outer and inner confirmation each authenticate the actual protected readback and exact expected bytes. The later admission seal uses the recorded completion in memory; it adds no journal reads or large raw hashing to per-chunk authority checks.

The final state records both publication attempts separately as NOT_ATTEMPTED, ATTEMPTED_UNKNOWN or CONFIRMED, together with the terminal capability stage. A completed readback remains recorded even if a later deadline check fails. Transaction-parent mutable-stamp reconciliation is enabled only after the outer write/readback has actually been confirmed; before the first O_EXCL those stamps must still match the prepared proof.
