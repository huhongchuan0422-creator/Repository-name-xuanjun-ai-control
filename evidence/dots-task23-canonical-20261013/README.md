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
