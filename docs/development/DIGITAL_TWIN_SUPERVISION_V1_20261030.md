# Digital Twin Supervision V1

Status: `TEST_ONLY / READ_ONLY_DECISION / NOT_DEPLOYED`

## Reused authority

This increment reads an already-authorized snapshot of the existing Task
Supervisor, GatewayKernel and writer-fence facts. It creates no table, task
registry, scheduler, lease, fence, credential, executor, monitor process or
background timer. All mutations and recovery admission remain in the original
service.

## Decision rules

- `EXECUTOR_ACK`/`RECEIVED` is acceptance only; it is not process start.
- A heartbeat is displayed separately and never advances real progress.
- A task state does not prove process/session liveness. The process must be
  matched to the canonical run, session and writer epoch.
- A process exit is an observation, not an automatic failure. It may open
  recovery eligibility only when a trusted process observation is exactly
  bound to the current run/session/epoch, or a `PROCESS_EXITED` event contains
  the same complete identity, evidence reference and the fixed trusted process
  observer producer. Same-attempt events with missing, untrusted or old
  execution identity do not prove exit. The next step is
  result/checkpoint/effect reconciliation.
- A result from a mismatched run, session or old writer epoch is rejected
  before its apparent terminal state is interpreted.
- `UNKNOWN`/`DISPATCHING` effects are keyed by the original task, attempt,
  operation and resource. Missing/mismatched keys are `HOLD`; unresolved
  effects are read back and never redispatched.
- Same-attempt recovery is only an eligibility result when the old process is
  proven exited, a same-attempt checkpoint exists and effects are reconciled.
  The original Gateway/Fence/executor must revalidate it and no new authority
  is granted by this read model.
- The successor action ID is deterministic from task, attempt, epoch,
  checkpoint and action, so repeated reads do not create duplicate work.
- Supervisor heartbeat health is reported separately. A fresh record does not
  prove the supervisor process; a stalled supervisor does not rewrite task
  outcome.

## Interface

`evaluate_supervision(snapshot, now, progress_max_age=600,
supervisor_max_age=300)` accepts canonical task facts, events, one execution
observation, one supervisor observation, checkpoints and unknown effects. It
returns `READ_ONLY_DECISION` with decision/reason, progress and heartbeat
facts, supervisor health, unresolved original operation IDs, deterministic
next action and guarded recovery eligibility.

The caller must obtain tenant/project authorization before constructing the
snapshot. This module does not inspect identities, secrets, customer data or
production processes itself.

## Verification boundary

Unit tests cover heartbeat/progress separation, ACK without start, process
exit, safe same-attempt eligibility, unknown-effect HOLD/no redispatch,
missing original keys, old-epoch rejection, missing terminal receipt,
deterministic successor action and independent supervisor-stall reporting.
They are local test substitutes, not a production executor, recovery,
deployment or customer acceptance.
