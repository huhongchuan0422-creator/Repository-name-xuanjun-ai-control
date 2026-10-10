# V2.7 Owner Operations Priority — approved 2026-10-10

## Owner decision
Prioritize **Owner Workspace + Human Action Notifications + Automatic Task Resume** within the existing UK Stage 1 nodes 1.8–1.13. Do not create parallel Task Registry, Gateway, Workflow Engine, CRM, Admin Console or notification subsystem.

CHANNEL_PRIMARY_ALERT=TELEGRAM
CHANNEL_SYSTEM_OF_RECORD=AUTHENTICATED_WEB_OWNER_WORKSPACE
NORMAL_SUCCESS_CHATGPT_NOTIFICATION=NOT_REQUIRED
HUMAN_EXCEPTION_NOTIFICATION=TELEGRAM
FULL_EVIDENCE_AND_OPERATION_LOG=WEB_WORKSPACE
EXECUTION_PRODUCTION_WRITE=DENIED_UNTIL_RELEASE_GATES

This is approved product priority and design scope, **not proof of deployed functionality**.

## Existing-asset audit before any implementation
Read and map:
- Existing Tokyo and Domestic Canonical Project State / Task Registry / OpenClaw orchestrator / multi-agent routing
- Existing Telegram bot, webhook/adapter, outbound messages and one-message-one-primary-response rules
- Existing secure Owner portal / Admin Console Framework / RBAC / authentication / approvals
- Existing checkpoint, lease, callback, event outbox, retry and task-completion mechanisms
- GitHub private control repository / Actions workflows / artifacts and UK deployment services

For every reusable capability, record REUSE / EXTEND / MIGRATE / MISSING / UNKNOWN and evidence. Check GitHub source for reuse *after* the local asset scan. External GitHub OSS only for complex missing generic capabilities, up to three license/safety-reviewed candidates.

## Implementation mapping (do not reorder architecture nodes)
- 1.8 Task Gateway: minimal authenticated API on existing Task Registry; create_task/get_project_state/get_task_status/get_task_result/request_owner_approval; idempotency, identity, rate limits, signed events; no shell executor.
- 1.9 Node Registry: project/milestone/node/task, dependency, evidence, cost, approval state, lease/checkpoint, canonical source references.
- 1.10 Owner Node Review & dashboard: Chinese mobile-responsive login-protected UI for progress, verified state, costs, tasks, blocker, human actions, security gates, release evidence, rollback, system health. Task confirmation distinct from view/read.
- 1.11 Drift Guard: stop scope expansion on diff/agent/permission budget mismatch; escalate exceptions.
- 1.12 Dot/notification adapter: verify actually supported Dot connectivity; no assumed cloud event capability. Telegram only routes minimal human-readable alerts referencing secure web action pages; no secrets, sensitive customer info, or administrative approval via unverified chat identity.
- 1.13 Usage Governor: limits, budget, retries, token attribution, stop-on-repeat; event-driven instead of model polling. Launch in sync with 1.12, not after.
- 1.14/1.15 retain mandatory Eval and end-to-end Canary.

## Communication policy
1. Routine success: append evidence and change Owner dashboard; no per-command LLM message.
2. Meaningful milestones: aggregated notice only if configured.
3. Human action needed: Telegram actionable *notice* with task reference, minimal reason, deadline and secure workspace link. Owner approval happens in authenticated role-authorized workspace with re-verification for high-risk operations.
4. Severe issue: Telegram priority alert and persisted incident. If bot/provider unavailable, persist a delivery failure and keep dashboard pending; never treat send intent as delivered.
5. Owner conversations remain responsive using existing coordinator/async worker isolation. No new daemon per agent.
6. Resume: HUMAN_VERIFICATION_REQUIRED -> CHECKPOINT -> unblock independent work -> authenticated human action -> policy/dependency recheck -> RESUME. Model/API budget exhausted -> PAUSED_RESOURCE -> resume only when valid budget.

## Security and proof
- UK cannot receive Binance order-write; Tokyo remains protected source; Korea migration requires isolated shadow/rollback.
- Notifications carry no tokens, API keys, financial secrets or privileged direct-action links; use authenticated workspace.
- At least one real Telegram send/receipt test to verified Owner chat identity, deduplicated message, failure handling and anti-replay; do NOT send now merely because this plan was approved.
- Tests must cover RBAC, cross-tenant denial, replay, duplicated completion, offline/restart lease, cancellation, failure recovery, budget pause/resume, and evidence consistency.
- No production migration/deploy or external notification from this documentation change.
- UK Stage1 control plane remains PARTIAL until evidence-based 1.15 Canary and all required gates.

## Delivery order
Complete safe Stage 0 inventory and Stage1 1.1–1.7 existing-asset mapping; then incrementally prioritize 1.8–1.13 with 1.12/1.13 synchronized. Reuse proven existing UI/Telegram primitives. No unrelated product module or GEO work until the defined gates.
