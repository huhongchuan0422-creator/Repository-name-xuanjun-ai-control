# TASK WRITER FENCING V2.1 — 2026-10-24

Status: SOURCE IMPLEMENTATION IN DEVELOPMENT. PRODUCTION_FENCING_HOLD.

This is a source-safety module under the existing canonical
`task_supervisor`. It is not a second task center, does not add multi-role or
multi-model scheduling, and does not grant production credentials, deployment
permission, resource-native authority, or production takeover.

## 1. Canonical authority

Authority states are:

```
UNKNOWN
NONE -> VALID -> REVOKING -> REVOKED
```

READY is only a task state.

Initial source claim is NONE -> VALID. The canonical store allocates
`max_fence+1` and `max_epoch+1`; the caller cannot choose a generation.

Takeover has no REVOKED -> NONE/READY -> VALID gap. One canonical transaction
must verify REVOKED, the exact append-once receiver ACK, the exact resource
scope digest, the independent coverage digest and the reserved resource set,
then allocate max+1 and move directly to new VALID.

Migrated active v2 attempts become authority UNKNOWN and task HOLD. UNKNOWN
cannot move directly to NONE or VALID. A dedicated trusted source-inventory
recovery path must atomically persist the inventory evidence, reserve the exact
normalized resource set, record its scope digest and move UNKNOWN -> REVOKING.
Insufficient or conflicting inventory remains HOLD.

Legacy coordination `claim()` and HANDOFF payload booleans are not fencing
authority.

## 2. Ticket and trusted caller

WriterTicket is a selector bound to task, attempt, lease, fence, epoch,
valid_until, checkpoint/spec, caller_id, run, session, gateway and resource
scope digest/set. A ticket digest proves bytes only.

Every writer operation checks the exact trusted caller_id + run + session +
gateway against canonical assignment. Reading another writer's ticket is not
authority.

Writer APIs do not accept a caller-provided `now`. Time is injected only by
the Supervisor clock. Validity requires `trusted_now < valid_until`. Clock
rollback is HOLD. Expiry rejects new commits but does not prove that the old
process or a remote effect stopped.

## 3. Resource identity and reservation

Conflict is defined by canonical `resource_key`, not only task_id. Different
tasks writing the same branch, database keyspace, object or deployment target
must conflict.

A trusted source adapter normalizes resource keys before canonical storage.
Whitespace, control/NUL bytes, dot/dot-dot path segments, empty segments and
alias forms are rejected. The canonical store conflict-checks and reserves the
entire sorted resource set in one SQLite transaction; partial ownership is
forbidden.

The source adapter and local lock provider are SOURCE/LOCAL_ONLY evidence. They
do not imply global production isolation.

## 4. Fixed Fence and CommitLease

A trusted `Fence` instance owns one pinned LOCAL_ONLY lock provider/root.
Individual CommitLease/revoke calls cannot choose another root.

The lock root is canonical, private, owner-bound and pinned by inode. Lock
files use NOFOLLOW, exact owner/mode, nlink=1 and inode recheck. Root path
replacement or symlink substitution fails closed.

CommitLease sequence:

```
acquire sorted shared resource locks
re-read canonical source authority
validate ticket + caller + trusted clock
CAS PREPARED -> DISPATCHING
hold the shared lock
perform source/offline effect
persist CONFIRMED or UNKNOWN
release shared lock
```

Thus no unlocked final-guard -> effect window exists inside the admitted source
path.

A local flock is never a distributed/global fence. Multi-host or direct-token
writers require a separately approved unique gateway, resource-native fencing
or equivalent capability isolation. Production remains HOLD.

## 5. Operation identity, receipts and attribution

Operation identity is immutable:

```
operation_id UNIQUE
(task_id, attempt_id, event_id) UNIQUE
```

State transitions use CAS:

```
PREPARED -> DISPATCHING -> CONFIRMED
                        -> UNKNOWN
                        -> NOT_APPLIED
                        -> CONFLICT
```

During revocation an undispatched PREPARED operation may only reconcile to
NOT_APPLIED with trusted evidence that dispatch never began.

UNKNOWN is not redispatched. Dedicated trusted readback may append evidence and
CAS DISPATCHING/UNKNOWN to CONFIRMED, NOT_APPLIED or CONFLICT. UNKNOWN
observations are append-only evidence and do not consume the final receipt.

Each operation has at most one final receipt. Same bytes are idempotent;
different bytes conflict. Receipt outcome, operation_id, resource_key and
operation_marker must match the operation.

CONFIRMED additionally requires an attributable before -> CAS/effect -> after
chain. Equal content alone is insufficient.

The pure offline `FakeTransactionalSink` produces attributable FAKE_TXN
receipts. The pure offline `OfflineGitCAS` validator binds repo, branch,
base HEAD, before tree/blob, requested after tree/blob, operation marker and
readback commit parent/tree/blob. It performs no network call and owns no
credential. A changed branch/head/tree/blob/marker is conflict, never an
automatic rebase or substituted HEAD.

## 6. Revocation and drain

Revocation is re-entrant for the same generation:

1. VALID -> REVOKING blocks every new intent and CommitLease.
2. Acquire the same fixed provider's resource set exclusively.
3. Timeout returns REVOCATION_NOT_COMPLETED and remains REVOKING.
4. A successful exclusive drain persists one LOCAL_ONLY drain receipt bound to
   old attempt/lease/fence/epoch/ticket/spec/scope/provider.
5. Reconcile every PREPARED/DISPATCHING/UNKNOWN operation.
6. Obtain one exact source invalidation receipt per resource_key from the same
   fixed source adapter/provider.
7. Only after drain + zero unresolved operations + complete resource receipts
   may canonical authority move REVOKING -> REVOKED.

A crashed process can release a local lock while its remote effect is UNKNOWN;
therefore lock release alone never completes revocation.

During REVOKING an old attempt cannot create new PROGRESS, TERMINAL, INTENT,
CommitLease or effect through the fenced path. An already DISPATCHING effect
may only persist its final CONFIRMED/UNKNOWN result. Dedicated reconcile is the
only recovery path for existing operations.

## 7. Resource invalidation and coverage

A resource invalidation receipt is not an arbitrary
`outcome=INVALIDATED` assertion. In source tests it must be emitted by the
trusted LOCAL_ONLY source adapter and bind:

- task_id;
- old attempt, lease, fence and epoch;
- old ticket SHA;
- spec SHA;
- canonical resource scope digest;
- exact resource_key;
- fixed lock provider;
- source adapter identity;
- evidence ID.

The canonical store verifies all bindings.

`resource_scope_digest` and `coverage_digest` are independent.
Coverage binds old identity/spec/scope, the persisted drain receipt and the
sorted per-resource invalidation receipt hashes.

Missing, UNKNOWN, conflicting or unfenced coverage keeps the whole scope HOLD.
Fake/source receipts never count as production resource receipts.

## 8. Receiver ACK and gapless takeover

Receiver ACK is exact and append-once per old generation. The ACK binds:

- old task/attempt;
- new attempt/owner/entry/caller/run/session/lease/gateway;
- checkpoint/spec;
- resource_scope_digest;
- coverage_digest.

Exact replay is idempotent. Different bytes conflict and cannot overwrite the
stored ACK.

Only a canonical transaction that revalidates REVOKED + exact ACK + both
digests + all resource claims may assign the next max+1 generation and move
directly to new VALID.

## 9. Schema, preflight and migration

`task_supervisor.py` is the sole schema/DDL/migration owner.
`task_writer_fence.py` owns no authority DB and performs no DDL.

Normal runtime opening of an existing v1/v2 ledger first uses immutable
read-only preflight. It returns `HOLD_MIGRATION_REQUIRED` before any RW open,
journal-mode change, WAL/SHM/journal creation or task mutation.

Only explicit `offline_migrate_v2_to_v3` is available in this source phase.
Production migration is NOT_EXECUTED and separately approved.

Migration tests include multiple interruption failpoints. DDL/header/authority
changes must roll back so a clean restart can migrate the original v2 fixture.

The schema validator checks primary keys, unique keys, required indexes and
foreign-key topology.

`recovery_generation` remains supervisor/outbox recovery state and is not
writer authority generation.

## 10. Inventory and production verdict

Source and production inventories are separate:

```
FRAMEWORK_INVENTORY = SOURCE_ONLY / testable
PRODUCTION_INVENTORY = INCOMPLETE
PRODUCTION_FENCING = HOLD
```

The production verdict is hard-coded HOLD for this module. Caller booleans such
as inventory_complete/raw_write_capable cannot upgrade it. Unknown or
unadmitted capability is also HOLD.

Shared production tokens, raw clients or any direct mutation path outside the
approved gateway remain `UNFENCED_PATH_PRESENT` until separately removed or
resource-native fenced.

The 3/10/30/60 minute coordination policy remains PROPOSED_UNADOPTED and
DEFAULT_DISABLED. Existing supervisor 5/10/15 recovery behavior is unchanged.
No time threshold creates write authority.

## 11. Source acceptance

Both existing supervisor workflows must execute the current dedicated fencing
suite through the stable `load_tests` aggregation in
`tests/test_task_supervisor.py`. Historical temporary-bridge runs are not
current acceptance.

Applicable T01-T34 coverage includes:

- concurrent claim single winner;
- cross-task same-resource exclusion and multi-resource rollback;
- caller-only stolen ticket rejection;
- caller-time override rejection, expiry and clock rollback;
- fixed lock provider, root replacement/symlink and resource alias negatives;
- operation identity/idempotency and concurrent duplicate operation;
- CommitLease final-check/effect lock span;
- fake transactional sink attribution;
- offline Git branch/head/tree/blob/marker CAS validation;
- missing/mismatched receipt rejection;
- UNKNOWN append-only observations and no replay;
- PREPARED -> NOT_APPLIED only;
- revoke shared wait, timeout and same-generation resume;
- persisted drain requirement before complete;
- exact resource invalidation binding;
- scope digest vs coverage digest;
- ACK exact replay vs conflicting overwrite;
- UNKNOWN inventory recovery through persisted reservation/evidence;
- REVOKING zero new effect;
- v1/v2 zero-write open HOLD;
- multi-failpoint migration rollback/restart;
- foreign-key schema corruption rejection;
- production verdict fixed HOLD.

Source tests may establish a source-framework candidate only. Production
inventory, real adapters, real credentials, OS/DB/cloud permissions,
production migration and deployment remain HOLD/NOT_EXECUTED.
