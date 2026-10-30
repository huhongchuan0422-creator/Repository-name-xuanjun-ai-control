# Digital Twin Read Model V1

Status: `TEST_ONLY / SOURCE_INCREMENT / NOT_DEPLOYED`

## Scope

`GET /api/admin/digital-twin` is an admin-only, tenant-bound, read-only
projection over the existing Task Supervisor, GatewayKernel and ModelControl
tables. It adds no registry, CRM, ledger, writer, dispatcher or installation
capability. Every action remains in its original service.

The response stores canonical task records once under `records.tasks` and
provides only task-ID indexes under `views.project_task_ids`,
`views.node_task_ids` and `views.ai_task_ids`. Project, node and AI switching
therefore cannot drift into separate state copies.

## Producers and boundaries

| Fact | Existing producer | Read source | Permission | Current boundary |
|---|---|---|---|---|
| project/node/task/dependency/checkpoint | Task Supervisor + GatewayKernel | canonical SQLite via `/api/projection` | tenant context | connected in TEST_ONLY runtime |
| task event/evidence | Task Supervisor `events` | same read snapshot | tenant context | connected; evidence is never inferred |
| role instance/model request/assignment/candidate | ModelControl | selected non-secret tables | `TASK_CENTER_ADMIN` | connected in TEST_ONLY runtime |
| customer/project membership, requirement, page feedback | existing Identity/CRM/Customer Project Center | no proven adapter | original service permission | `NOT_CONNECTED`; fields are `UNKNOWN` |
| P2/P3 install and acceptance receipts | original controlled installer | no proven adapter | original install authority | `NOT_CONNECTED`; no install action exposed |

## State rules

- `PENDING_CLAIM`, `ACCEPTED`, `EXECUTING`, `TESTING`, `PENDING_REVIEW`,
  `BLOCKED`, `RECOVERING`, `COMPLETE`, and `UNKNOWN` are presentation states.
- Animation is allowed only for `EXECUTING`, `TESTING`, or `RECOVERING` when
  a real progress timestamp or evidence reference exists.
- Heartbeat remains separate from progress. The current task projection has no
  verified heartbeat adapter, so task heartbeat fields remain `UNKNOWN`.
- `DISPATCH_SENT`, `EXECUTOR_ACK`, and `HEARTBEAT_OBSERVED` never imply
  completion. `RESUME_STARTED` without a terminal resume receipt remains
  `RECOVERING`.
- Missing CRM, identity, process/session liveness, installation, or acceptance
  facts remain `UNKNOWN`/`NOT_CONNECTED`; they are never fabricated.

## UI integration

1. Authenticate through the existing task-center session flow with
   `TASK_CENTER_ADMIN`.
2. Fetch `GET /api/admin/digital-twin` with same-origin credentials.
3. Render objects from `records.*`; use `views.*_task_ids` only as filters.
4. Use `source_ref`, `event_id`, `evidence_ref`, `attempt_id`, and
   `artifact_sha256` for drill-down. Do not cache a second authoritative state.
5. Send mutations or approvals to the original owning service after its own
   permission check; this endpoint has no mutation route.

The response includes machine-readable `field_contract`, `event_contract`,
`sources`, `gaps`, and `integration_boundaries` for UI feature detection.

## Verification boundary

Unit and HTTP integration tests use local TEST_ONLY SQLite fixtures and prove
tenant-bound projection, reference-only indexes, admin denial, evidence-gated
animation, explicit unknowns, and interrupted-resume display. They are test
substitutes, not two production tasks, a live MCP execution, deployment, or
customer acceptance.
