# MCP Development Closure Evidence V1

Status: `SOURCE_INCREMENT / TEST_ONLY / NOT_DEPLOYED`

## Purpose and ownership

`scripts/mcp_development_closure.py` is a pure, fail-closed evidence reader for
the existing task-center, GatewayKernel, ModelControl, Codex execution adapter,
candidate review, and canonical terminal records. It creates no task, queue,
registry, CRM, ledger, writer authority, credential, process, or deployment.
The owning services remain the only producers and mutation authorities.

The reader binds one chain to the exact tuple:

`tenant / task / attempt / role / role-instance / request / intent / run /
session / process / writer-principal / fence / epoch`.

An attempt or Writer-generation mismatch is a whole-chain `HOLD`, not a reason
to merge an old receipt into the new attempt. `run_id` and `session_id` are
selected only from the canonical task (including its canonical authority run /
session fields); a process receipt cannot nominate its own run. The intent and
trusted process receipt must both match the canonical session, and a projected
role instance's `current_request_id`, when present, must match the request.

## Stage contract

1. `SENT`: accepted `SENT_INTENT` event only. It proves send intent, not remote
   receipt or execution.
2. `ACK`: an accepted ACK/RUNNING event plus a remote execution/thread ID. It
   proves acknowledgement, not process liveness or work.
3. `PROCESS_STARTED`: exact task/attempt/run/session/process/epoch receipt from a
   trusted process observer. The current canonical schema has no such joined
   producer, so the live projection remains `UNKNOWN` until one is connected.
4. `REAL_AI_CALL`: current request success plus an attributable live-provider
   receipt with provider request ID and response SHA. Fixture transports and
   model text are explicitly rejected as proof of a real call.
5. `TESTS_PASSED`: frozen, current-attempt checklist with all required entries
   passed and no `NOT_EXECUTED` item.
6. `ARTIFACT_SUBMITTED`: canonical 64-hex artifact bound to that checklist,
   attempt, and authenticated executor.
7. `INDEPENDENT_REVIEW`: distinct QA and Security reviewers, neither the
   executor, passed the same current candidate.
8. `ACCEPTED`: a third independent acceptor plus canonical task `SUCCESS`,
   revoked Writer authority, and a terminal receipt for the exact artifact.

All eight stages must be `PROVEN` on the same identity for a closure verdict of
`PROVEN`. Missing producers are `UNKNOWN`; invalid/stale authority is `HOLD`.

## Strict admission for two future real tasks

`admission_for_real_task` can be called before each real task using a snapshot
from the original services. It requires current Writer authority, current
executor assignment, consistent request/intent generation, an active
`CODEX_EXECUTION` or `MODEL_INFERENCE` connection, attributable included/free
quota, and an idempotency key. Admission never claims that a process, model
call, artifact, review, or acceptance occurred.

For two consecutive tasks, retain two separate admission and closure receipts;
do not copy run/session/process/provider receipts between task IDs. After an
interruption, reconcile the original intent/request and current epoch before
admission. `UNKNOWN` effects are not automatically replayed.

## Current source and live boundary observed 2026-10-30

- Source HEAD observed while implementing: `94658821e64a391f833e3f61d0c3faa0de83990e`
  on `feature/digital-twin-projection-20261030`.
- Loopback `127.0.0.1:8765` was listening with the existing installed
  `/opt/xuanjun-task-center-test/current/scripts/task_center_app.py`, MCP and
  outbound flags. This was process/listener observation only; the live DB,
  endpoint, credentials, worker state, and external model were not read or
  changed.
- Current source supports persistent Codex intent, app-server thread/turn IDs,
  ModelControl requests, writer snapshots, frozen checklist/candidate review,
  and canonical acceptance gates.
- There is no canonical process-receipt producer joining OS process identity to
  task/attempt/run/session/epoch, and no canonical live-provider response
  receipt that distinguishes real provider calls from injected fixture
  adapters. Consequently live end-to-end development closure and the required
  two consecutive real tasks remain `UNKNOWN / NOT_EXECUTED` here.
- SDK transport remains `NOT_IMPLEMENTED`; Hosted/account capability remains
  `UNVERIFIED`; production deployment and P2/P3 installation are outside this
  source increment.

## Verification boundary

`tests/test_mcp_development_closure.py` uses isolated dictionaries only. It
proves fail-closed identity binding and decision rules, not a real model call,
live MCP task, deployed endpoint, installation, or customer acceptance.
