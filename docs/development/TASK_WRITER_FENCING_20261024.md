# TASK WRITER FENCING V2.1 — 2026-10-24

Status: SOURCE IMPLEMENTATION IN PROGRESS. PRODUCTION_FENCING_HOLD.

This module is a safety primitive under the existing canonical task_supervisor.
It is not a new task center and does not add multi-role or multi-model routing.

## 1. Canonical authority

Authority states are exactly:

```
UNKNOWN
NONE -> VALID -> REVOKING -> REVOKED
```

READY remains a task state, never an authority state.

Initial writer admission is NONE -> VALID. The canonical store, not the caller,
allocates fence=max_fence+1 and epoch=max_epoch+1.

Takeover has no REVOKED -> NONE -> VALID gap. One canonical transaction must
verify REVOKED, the exact stored receiver ACK, complete resource coverage and
the reserved resource set; the store then allocates max+1 and changes directly
to VALID.

Migrated active v2 attempts become authority UNKNOWN and task HOLD. UNKNOWN
cannot transition directly to NONE or VALID. Only the dedicated trusted
recovery entry may transition UNKNOWN -> REVOKING after recording recovery
evidence; normal drain/readback/coverage/ACK/takeover rules then apply.

Legacy task claim/HANDOFF records remain coordination evidence only. They are
not fencing authority and cannot establish production writer isolation.

## 2. Ticket and caller identity

A WriterTicket is a canonical selector containing task, writer scope, attempt,
lease, fence, epoch, valid_until, checkpoint/spec, assigned run/session,
gateway and resource set.

A ticket digest proves bytes only. It is not caller authentication. Every
prepare/dispatch must additionally bind a trusted caller context to the
assigned run/session/gateway. Reading another writer's ticket does not grant
authority.

The caller cannot choose a higher epoch or fence. Allocation is canonical
max+1 only.

valid_until uses trusted_now < valid_until. A trusted-clock rollback is HOLD.
Expiry rejects future commits but does not prove that a process or remote side
effect stopped.

## 3. Resource scope and conflict registration

Writer uniqueness is defined over real conflicting resource_key values, not
only task_id. Different tasks that can mutate the same branch, database
keyspace, object or deployment resource are conflicting writers.

A resource set is normalized and sorted. All keys are conflict-checked and
registered inside the same canonical DB transaction. The operation either
owns the complete set or owns none; partial acquisition is forbidden.

Cross-process action locks are also acquired in fixed resource-key order to
avoid lock-order deadlock.

If only same-task successor fencing is implemented for a resource type, its
guarantee must be labelled SAME_TASK_SUCCESSOR_ONLY, not GLOBAL_UNIQUE_WRITER.

## 4. CommitLease

A final guard followed by an unlocked write still has TOCTOU. A protected
effect therefore uses a context-managed CommitLease:

```
acquire sorted shared action locks
re-read canonical authority while locked
validate ticket + trusted caller + time
CAS PREPARED -> DISPATCHING
keep locks held
perform external effect
persist CONFIRMED or UNKNOWN
release locks
```

The shared lock spans the final canonical check, dispatch and durable outcome.

Local flock is LOCAL_ONLY. It does not prove distributed isolation. Multi-host
or direct-credential writers require a unique admitted gateway,
resource-native fencing or capability isolation.

## 5. Revocation

Revocation order is fixed:

1. VALID -> REVOKING in canonical state.
2. REVOKING rejects every new CommitLease/new intent.
3. Acquire the same resource set exclusively and wait for old shared leases.
4. Timeout returns REVOCATION_NOT_COMPLETED and remains REVOKING.
5. Reconcile all old PREPARED/DISPATCHING/UNKNOWN operations.
6. Obtain a real invalidation receipt for every resource_key.
7. Compute and persist a coverage digest bound to old attempt/spec/resources.
8. Only then REVOKING -> REVOKED.
9. Store exact receiver ACK.
10. One takeover transaction validates REVOKED+ACK+coverage and changes
    directly to new VALID while allocating max+1.

A process crash can release a local lock while a remote request remains
UNKNOWN. Lock release therefore never implies revocation completion.

During REVOKING the old attempt cannot create PROGRESS, TERMINAL, INTENT,
CommitLease or new effects through the fencing path. Only dedicated readback
and reconciliation of already-existing operations is admissible.

## 6. Operation state and reconciliation

Operation identity is immutable:

```
operation_id UNIQUE
(task_id, attempt_id, event_id) UNIQUE
```

State machine:

```
PREPARED -> DISPATCHING -> CONFIRMED
                        -> UNKNOWN
                        -> NOT_APPLIED
                        -> CONFLICT
```

All transitions use CAS.

UNKNOWN is not redispatched. A trusted readback/reconcile path may append
evidence and CAS UNKNOWN/DISPATCHING to CONFIRMED, NOT_APPLIED or CONFLICT.
A repeated UNKNOWN observation is append-only evidence and does not consume the
one final receipt.

Final receipt is append-once per operation. Same bytes are idempotent;
different bytes conflict.

APPLIED_EXACTLY/CONFIRMED cannot be inferred from equal content alone. It
requires a resource operation marker or an attributable unique before/after
revision chain.

For GitHub the offline CAS model binds repo, branch, expected base HEAD,
before tree/blob, requested blob, operation marker and readback commit/parent/
tree/blob. A changed HEAD is CONFLICT; the fencing layer never auto-rebases,
auto-merges or silently substitutes a new expected HEAD.

## 7. Resource invalidation coverage

old_fence_invalidated is not a global boolean.

Each conflicting resource_key needs its own invalidation receipt. The complete
sorted receipt set produces a coverage digest bound to old attempt/spec/resource
scope.

Any missing, UNKNOWN or UNFENCED resource keeps the entire scope HOLD.

Fake/offline receipts prove SOURCE behavior only and must never be presented as
production resource receipts.

## 8. Schema and migration ownership

task_supervisor.py is the only schema/DDL/migration owner.
task_writer_fence.py creates no authority database and performs no DDL.

Normal opening of an existing v1/v2 ledger returns HOLD_MIGRATION_REQUIRED
before persistent mutation.

offline_migrate_v2_to_v3 is explicit and is used only with isolated fixture
copies in this source phase. Production database migration requires separate
approval and is NOT_EXECUTED.

recovery_generation remains supervisor/outbox recovery state; it is not a
writer authority generation.

## 9. Inventory and verdicts

Source phase distinguishes:

```
FRAMEWORK_INVENTORY_COMPLETE
PRODUCTION_INVENTORY_INCOMPLETE
PRODUCTION_FENCING_HOLD
```

A shared token, raw client or any write path that bypasses the admitted gateway
is UNFENCED_PATH_PRESENT and forces production HOLD.

The proposed 3/10/30/60 minute coordination policy is PROPOSED_UNADOPTED and
DEFAULT_DISABLED. Existing supervisor 5/10/15 recovery behavior is unchanged.
No timeout creates writer authority.

## 10. Source acceptance

Required isolated tests include:

- concurrent claim single winner;
- same resource conflict across different tasks/scopes;
- atomic resource-set registration;
- stale/old ticket rejection;
- stolen ticket caller mismatch;
- prepare/dispatch epoch or revocation race;
- CommitLease shared lock spanning dispatch outcome;
- revocation exclusive wait and timeout;
- process-loss DISPATCHING/UNKNOWN restart recovery;
- UNKNOWN readback to final state without redispatch;
- append-only reconcile observations and one final receipt;
- operation identity/event collision rejection;
- clock rollback and expiry fail closed;
- REVOKING produces zero new effects;
- per-resource coverage + exact ACK + gapless takeover;
- v2 normal open zero-write HOLD and explicit fixture migration;
- active v2 migration -> UNKNOWN/HOLD;
- equal GitHub content without marker is not CONFIRMED;
- raw/shared credential bypass produces PRODUCTION_FENCING_HOLD.

Passing source tests can establish SOURCE_FRAMEWORK_PASS only.
Production remains FENCING_HOLD until real gateway/credential/resource fencing,
production inventory, production DB migration and deployment are independently
approved and evidenced.
