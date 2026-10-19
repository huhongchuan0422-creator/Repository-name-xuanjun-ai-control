# P2 coordination rewrite — ISOLATED_TEST_ONLY

Base: `23df8fa18b45946de96dac4f77a0aa181618eb05`. Original PR17 task remains authoritative; this component adds no new production task queue, no AuthorityStore, no signature issuer and no Grant. This code is not the old frozen 16-stage installer. Existing WAL journal and prior receipts are retained without destructive migration.

## Functional nodes (minimal complete boundaries)

| Node | Function | Input/dependency | Owned resources | Acceptance | Recovery/freeze |
| --- | --- | --- | --- | --- | --- |
| Artifact version | Stage verified immutable artifact | signed manifest and scoped storage (window one) | artifact version root | manifest/hash/real file readback | only own version, freeze immutable SHA |
| Plugin version | Stage plugin version | artifact version | own plugin root | plugin digest and readonly readback | do not touch preceding artifact version |
| Isolated runtime | Start/stop owned workload | staged version (window two) | runtime root, logs and process identity | real process and health readback | reconcile existing PID identity; never blindly restart |
| Coordinator | Gate dependencies, durable intents, inspect and recover | component adapters and plan pin | private SQLite/WAL in its own root | dependency readback; no duplicate committed side effects | RUNNING remains HOLD until trusted reconciliation |
| Wake/outbox | Publish deterministic timeout events | coordinator durable records | coordinator outbox | idempotent event records | provider UNAVAILABLE until actually connected |
| Production integration (outside scope) | exact trust, registry, Grant, Writer/Fence, encrypted transport | trusted site-specific machinery | external trusted resources | authenticated onsite tests | explicit separate release admission |

Original P2 function mapping: release staging -> Artifact version; plugin installation -> Plugin version; process/service lifecycle -> Isolated runtime; plan predecessor checks, checkpoints and idempotence -> Coordinator; timeouts/wake -> Wake/outbox; AuthorityStore/Grant, signed plan, issuer, Registry, protected transport, lease/fence, legacy unit/cgroup control, backups and 16-stage migration -> external production integration, **NOT IMPLEMENTED here**. Host systemd and cgroup manipulation are explicitly not replaced by container adapters.

## JSON

Request must include schema=1, scope=ISOLATED_TEST_ONLY, installation_id, batch_id, attempt_id, absolute private root, version (64 hex), deadline_utc (Unix seconds), and inputs dictionary. The plan contains schema, release, ordered batches, and is pinned by journal SHA. Result contains identity, status COMMITTED/NO_EFFECT/HOLD, receipt {path,sha256} or null, error object or null. Only authenticated fixed trusted adapters can change effects. Adapter execute/inspect/recover are separate; request does not contain executable module names, scripts or shell strings. A real adapter must return a bounded receipt stored in its own root and repeatable independently inspectable actual state.

CLI:
```bash
python -m production.p2_install.coordinator tick --root /absolute/private/coordinator --plan /path/to/plan.json
python -m production.p2_install.coordinator inspect --root /absolute/private/coordinator --plan /path/to/plan.json --request /path/to/request.json
python -m production.p2_install.coordinator recover --root /absolute/private/coordinator --plan /path/to/plan.json --request /path/to/request.json
```
CLI execute currently has no installed trusted effect adapter and correctly returns HOLD/ADAPTER_UNAVAILABLE; application embedding must inject a fixed vetted adapter. The private root must preexist, mode 0700, owner=current effective UID. No external wake provider is present; outbox delivery remains UNAVAILABLE. No attempt is made to wake chats or pretend ACK.

## Timing and safety

Current Owner thresholds: 5 minutes without RECEIVED, 15 without STARTED or actual PROGRESS, 30 for escalation, same cause 30 minutes method review and 60 minutes stop old method. The tick emits durable one-shot records, never treats HEARTBEAT as real progress and never automatically calls execute. It does not currently receive authoritative lifecycle events from PR17; therefore end-to-end tick eligibility and 30/60 same-cause method switching are not validated. Timeout never authorizes a second writer. Counts are local ISOLATED_TEST_ONLY records; not a production Grant consumption or an AuthorityStore substitute. Once production Grant support is wired by integrator, it must be authoritative and replace local admission.

## Verification boundary

The new unit tests exercise real temporary file side effects, receipt digest verification, persistent journal reopening, predecessor drift, timeout idempotence, and a local five-attempt cap. These tests cannot validate true production identities, real worker crash/reparent PID survival, cloud/inbox acknowledgment, signed Grants, distributed fences or the combined P2 installer. Such results must remain NOT_TESTED/HOLD.

## Window three incremental repair (2026-10-20)

- `round_id` separates an installation round from every batch operation: multiple nodes in one round do not consume multiple installation attempts. `Coordinator(..., grant=trusted_authority_adapter)` fails closed when the Grant adapter is unavailable; `admit_round(request, ordinal)` is an explicit external contract and MUST be implemented against the original durable AuthorityStore/Grant before live use. The local `coordinator_rounds` table is merely an isolated projection, **not** authorization or production quota.
- `Coordinator(root, plan, component_roots={"batch":"/private/component"}, ...)` pins component roots separately from the coordinator WAL root. No request-supplied module imports or shell commands.
- Execution receipts remain immutable. A fresh observation with a different receipt must carry independently hashed evidence of `request_sha256`, `commit_receipt_sha256`, and verified real effect; otherwise HOLD. The current window-two runtime observation format does not yet provide these linkage fields and requires a fixed trusted integration adapter without modifying the window-two source.
- Adapter calls run in bounded child processes. Timeout of the coordinating call terminates the adapter invocation and **does not establish absence of effects or authorize a second launch**. The component may retain an in-flight child or owned process; only its trusted inspect/reconcile can decide a safe next step.
- An intent saved before `journal.begin` is queried with the original attempt, never re-executed blindly. Evidence insufficient means HOLD. `event(request,kind,evidence)` stores append-only lifecycle observations, including repeated progress events, while `tick()` continues to publish idempotent outbox records marked UNAVAILABLE without a real notification provider.
- Remaining barriers: original AuthorityStore/Grant adapter implementation and authoritative identity binding; window-two observation provenance bridge; real wake Provider; external PR17 lifecycle event delivery; stronger same-root-cause 30/60 handling and process-kill/response-loss integration tests. These are not production-complete.

## Owner revision — isolated rewrite scope (2026-10-20)

This isolated coordinator has NO five-round or five-Attempt admission limit. An installation may execute every approved functional node and may query/recover an existing attempt without consuming an installation quota. Prior production Grant/AuthorityStore records are untouched; production authorization is out of scope. Any historical coordinator_rounds rows remain preserved but no longer control admission.

A separate development-failure escalation mechanism records root cause per installation, across batches and restarts. At the earlier of ten failures or one hour, tick writes a unique Dots escalation to the durable outbox with evidence and alternative-method request. At thirty minutes for the same root cause, a method-change record is created. These thresholds do not grant install retries and do not reset on reboot. Until a real Dots delivery adapter and verified ACK exist, notification status is UNAVAILABLE (not delivered). The current interface requires explicit failure(request,cause,evidence) calls; live event producers must be connected and authenticated before this can be treated as automated escalation.

CLI can opt into only the fixed local runtime module with --runtime and --component-root batch=/private/runtime/path. Run in isolated Python 3.11 container, never on the Python 3.6 host and never against production state. Example:

```sh
python -m production.p2_install.coordinator execute --root /tmp/private-coordinator --plan /tmp/plan.json --request /tmp/request.json --runtime --component-root runtime=/tmp/private-runtime
```

The runtime source must be part of the same checkout/container image. This CLI does not import arbitrary user-specified modules. Its observation protocol still requires a trustworthy commit-linked readback adapter; a raw runtime adapter that lacks this proof will correctly HOLD rather than falsely commit. Subprocess timeout is not proof of process cleanup; real process ownership reconciliation remains necessary.
