# Project Delivery Contract V1

Status: `TEST_ONLY / SOURCE_INCREMENT / NOT_DEPLOYED`

## Reused authority and scope

This contract is a read-only task-center-side bridge for the existing Customer
Project Center. It reuses Task Supervisor and GatewayKernel tenant, project,
task, attempt and `input_version` facts. It creates no CRM, customer center,
registry, task framework, ledger, approval route or deployment route.

`ProjectDeliveryContract.normalize()` validates an already-observed website
event. It performs no write. The event must match the authenticated tenant,
the canonical task's `project_id`, and the canonical task `input_version` as
`ui_version`. The result remains `VALIDATED_NOT_PERSISTED`; the production
adapter is `NOT_CONNECTED`.

## Producer, interface and permission boundary

| Facts | Original producer | Task-center interface | Permission | Current status |
| --- | --- | --- | --- | --- |
| task/project/input version | Task Supervisor + GatewayKernel | `gateway_task_metadata` through authenticated context | tenant context | connected in TEST_ONLY |
| page baseline, comment, change, rectification, recheck, page acceptance, delivery | Customer Project Center / CRM | exact event contract in `project_delivery_contract.py` | original service actor and authorization reference | production adapter `NOT_CONNECTED` |
| confirmation | customer, requester, or platform Owner in original service | read-only normalized event | original service permission | AI/developer/reviewer/system cannot confirm |
| case-study selection | original authorized customer/Owner decision | allowlisted opaque `content_ref` only | explicit authorization plus local publication allowlist | customer backend content is never emitted |

The task-center projection has `mutation=NONE`. UI actions must return to the
original Customer Project Center for its own authentication, RBAC and durable
recording. A normalized event is not proof that a production adapter exists.

## Event and version contract

Source events are converted to canonical read events:

- `PAGE_UI_CONFIRMED` -> `UI_BASELINE_CONFIRMED`
- `CUSTOMER_COMMENT_RECORDED` -> `PAGE_COMMENT_RECORDED`
- `PAGE_CHANGE_REQUESTED`
- `PAGE_RECTIFICATION_SUBMITTED`
- `PAGE_RECHECK_RECORDED`
- `PAGE_ACCEPTED` / `PAGE_REJECTED`
- `PROJECT_DELIVERED`
- `SHOWCASE_REFERENCE_ALLOWED`

Every event binds `tenant_id`, `project_id`, `page_id`, `ui_version`,
`task_id`, `attempt_id`, `event_id`, actor/permission/authorization references,
and evidence/change/delivery/acceptance/content references. Unknown optional
facts are explicit `UNKNOWN`; they are not omitted or inferred.

The reducer keys page records by `(project_id, page_id, ui_version)`, so a new
version never overwrites the old baseline or its audit events. Page states are
`CONFIRMED`, `PENDING_CHANGE`, `PENDING_RECHECK`, `PENDING_ACCEPTANCE`,
`ACCEPTED`, `REJECTED`, or `UNKNOWN`. A rejection exposes only its evidence
reference as `rejection_reason_ref`.

`PROJECT_DELIVERED` exits the project from active development only when every
tracked page/version is `ACCEPTED`. Otherwise it remains active with
`BLOCKED_INCOMPLETE_PAGE_ACCEPTANCE`; the attempted delivery event remains in
the audit list. The contract cannot manufacture a front-end "passed" state.

## Case-study privacy

The public-facing case-study projection contains only an opaque `content_ref`
when both conditions hold:

1. an authorized `SHOWCASE_REFERENCE_ALLOWED` event explicitly sets
   `showcase_allowed=true`; and
2. the same reference is in the publication caller's allowlist.

No full customer page, backend record, comment, credential or customer data is
copied into the showcase projection.

## Integration example

1. The original website records and authorizes the action.
2. A future approved adapter emits the exact event schema without secrets.
3. Task center validates tenant/project/task/UI-version binding.
4. `build_project_delivery_projection()` exposes page-version state and audit
   references to the digital-twin read model.
5. Mutations remain in the website service; deployment and customer acceptance
   remain separate evidence domains.

Until that adapter is separately implemented and accepted, no events yields
`NOT_CONNECTED`, page acceptance remains `UNKNOWN`, and production status is
`NOT_IMPLEMENTED`.

## Verification boundary

`tests/test_project_delivery_contract.py` uses local TEST_ONLY SQLite fixtures.
It verifies cross-tenant/project/version rejection without writes, confirmation
role separation, page lifecycle and audit retention, incomplete-delivery
blocking, double-allowlisted showcase references, and explicit missing-adapter
state. These tests are not hosted integration, deployment, customer acceptance,
or permission to access customer data.
