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
