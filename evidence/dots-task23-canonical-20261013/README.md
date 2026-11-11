# Contract 6134634728 integration evidence (not an installed runtime)

This directory is a bounded proposal for the existing P2 owner. It does not
contain or create another operational database, queue or supervisor service.
`PROVENANCE.json` binds the exact previously downloaded frozen artifact,
original `stage1/execution_supervision.py`, proposed patch and method fixture.
The source is not represented as a tracked main stage1 file.

The P2 owner must compare the current packaged source SHA256 with
`base_source_sha256` before applying the patch. A changed base requires a new
reviewed delta; never silently apply with fuzz. The owner retains shared source,
canonical transaction, pinning, package imports and manifest ownership.

The proposed `record_inventory_notice` must run inside the owner's EXISTING
admitted, pinned canonical mutation transaction. The caller verifies the actual
connection/file identity and activation before/after, and rolls back on ANY
exception. Supplied labels are not proof. The method re-reads current metadata,
compares lineage inside that transaction and inserts a deduplicated notice only
through existing `_event`/supervision_delivery tables. No task execution state is
changed, no ACK is invented, no notification is sent and no model is invoked.
Duplicate notices preserve existing delivery/dead-letter state after restart.
Missing runtime admission/pinning prevents real integration and remains HOLD.

The pure `assert_inventory_lineage` helper is comparison, not authorization.
`notice_only=True` permits a notice about an unsupervised task with UNKNOWN run
fields after its actual task/checkpoint/file/activation lineage is matched; it
never authorizes a resume, receiver call or execution. The owner must continue
to apply existing operation authorization and STOP/fence/effects checks.

Policy6134670620: native WORK/CHATGPT/DOTS are not callable model backends here.
`receiver_continuation_policy` defaults to deny with no fallback. Mechanical
routes are proposals requiring their existing reviewed executor; the function
itself invokes nothing. Native chat inference/quota is not claimed free.
Runtime enforcement/audit counters remain ENFORCEMENT_NOT_VERIFIED until actual
admitted integration is independently tested; fixture results are not that proof.

Tests use disposable local SQLite fixtures and exact proposed method excerpts.
They cover stale run/fence/epoch/checkpoint, all nine entry pairs, stopped reader,
terminal without next-action evidence, duplicate/restart/dead-letter retention,
unsupervised-task inclusion and zero dispatch. They do not substitute for the UK
3.6.8 runtime, real receipt delivery/ACK, 5/10/15 faults or independent review.

## Version-bound UK mechanical acceptance input contract (not dispatched)

P2 shared owner supplies integrated commit/tree, frozen archive and manifest
SHA256, included adapter/shared-source hashes, approved activation binding and
existing ledger device/inode, review receipt, and its existing Runner job path.
Missing any prerequisite is BLOCKED_INPUT, not a Runner failure. Do not open a
new DB, change lease/fence, install, enable timers or call models from this fixture
suite. Host activation/mutation needs the existing separately admitted mechanism.

After that admission, the existing mechanical executor must report each case
separately with exact artifact, task/attempt/run/session, lease/fence/epoch,
generation/instance/checkpoint and event/delivery identities:

1. Complete inventory includes canonical tasks with no supervised run; bad bounded
   metadata in one task does not omit later tasks. No registry/table replacement.
2. Existing 5/10/15-minute start/progress/result cases use real elapsed canonical
   deadlines. Heartbeat alone cannot count as progress or reset a due deadline.
3. Stale run/fence/epoch/checkpoint/activation changes between observation and the
   notice transaction fail before event/task mutation. UNKNOWN effects never replay.
4. Restart/repeated scan retains one decision event and existing delivery attempt,
   ACK and dead-letter state. Report delivered/failed/pending separately; queueing
   a notice is not successful delivery or successor ACK.
5. All nine WORK/CHATGPT/DOTS origin-successor pairs retain task identity and
   checkpoint. Native model invocation is prohibited; unavailable transport is
   CAPABILITY_UNAVAILABLE. Readable/stopped readers never establish a writable
   active receiver. Actual native reception and ACK require real evidence.
6. Terminal-without-next-action remains visible. Verify exact next responsibility
   and receipted continuation or an explicit capability/human gate; no synthetic
   PASS, model fallback or new queue. Mechanical-only continuation is distinct
   from native coding and must not impersonate it.

Receipt fields: integrated_commit, tree, artifact_id, archive_sha256,
manifest_sha256, python_version, sqlite_version, runner_job, case_id,
observed_lineage, pre/post canonical hashes, event/delivery ids, actual result,
model_dispatch_count, mutation_scope, next_owner and receiver_ack. Keep secret
values/raw checkpoints out of GitHub. NOT_RUN, BLOCKED_INPUT and
CAPABILITY_UNAVAILABLE are valid non-PASS outcomes. Local/hosted fixtures cannot
populate UK acceptance fields.
