# V2.7 Stage1: Chat / Work-Codex quota switching
Owner-approved policy: 2026-10-10
Implementation: NOT_STARTED. Quota telemetry: NOT_VERIFIED.

Integrate into existing Stage1 Task Gateway (1.8), Node Registry (1.9), Owner Review (1.10), Drift Guard (1.11), Dot Adapter (1.12), AI Usage Governor (1.13), Eval (1.14), and E2E Canary (1.15). Design alongside existing architecture; keep prerequisite and release gates. Do not introduce a second task registry.

1. Use available ChatGPT ordinary chat quota as first priority.
2. If chat remaining quota cannot be queried, keep using the currently available ordinary chat mode without artificial UNKNOWN-driven pauses; only switch when an actual provider usage-limit/unavailable event occurs. Checkpoint and use Work/Codex only when its execution interface is supported. Do not manufacture quota exhaustion, run artificial prompts to burn quota, or presume a closed conversation can continue itself.
3. On verified 30% aggregate weekly Codex usage, including OpenClaw usage that actually consumes the SAME quota pool, check chat quota recovery. Return to chat if verified available.
4. Otherwise continue Work/Codex until cumulative weekly usage reaches 50%; then pause model-dependent development for the remainder of that calendar day.
5. On the following day (Asia/Shanghai), check chat first. If chat is still unavailable, continue Work/Codex using remaining weekly quota, with checkpoints and provider limits respected.
6. When Codex weekly quota is exhausted, check chat again. If chat is restored, resume chat-first. If not, create a deduplicated Owner action notice through the existing Telegram outbox and Owner workbench when operational. Until notification is actually connected, persist the notice for the next active conversation.
7. GitHub Actions and approved deterministic non-model tests can continue after model development pauses, provided dependencies and production gates are respected.

Evidence requirements: Record weekly total/used, daily usage, reset time, shared quota pool ID, chat availability, source and timestamp. If authoritative quota APIs are unavailable, preserve UNKNOWN; do not invent remaining capacity or assume chat recovery. OpenClaw usage billed to a different API/provider must be tracked separately, not falsely counted as Codex weekly quota. Local task accounting is ESTIMATE unless reconciled with provider-reported limits.

Task handoff between modes retains TASK_ID, Stage/Node, dependency graph, commit, PR, CI/QA/Audit results, CHECKPOINT, lease/fencing, next action and idempotent notification. This policy does not itself enable ChatGPT conversations to run while closed. Real unattended orchestration needs a verified persistent execution service.

Acceptance scenarios: weekly 29% to 30%; 49% to 50%; next-day resume without resetting weekly total; weekly exhaustion; verified chat recovery; UNKNOWN provider quota; OpenClaw outside shared pool; repeated retries; notification deduplication. No claim of production delivery before CI, independent QA, audit and UK staging canary.

## Human-blocker skip and batching — Owner authorization 2026-10-10
- Human-required steps (login, 2FA, credentials, manual platform approval, purchasing, high-risk production cutover) become WAITING_HUMAN with explicit instructions, owner, evidence and a durable checkpoint. Do not keep retrying them or repeatedly interrupt Owner.
- Consult V2.7 dependency graph and dispatch independent ready nodes/workstreams that are already authorized. A blocked predecessor never becomes PASS, and its dependent nodes may not bypass it. If several nodes need humans, accumulate a deduplicated consolidated Owner action queue; request a single grouped intervention when no useful independent work remains, at a material deadline, or when a safety decision is urgent.
- Maintain node provenance, CI/QA/audit gates, task lease/fencing, idempotent writes and release authorization. Pausing one task must not globally pause safely runnable others. All statuses must reflect observed evidence.
- Do not imply this chat can autonomously send the accumulated notice when user is absent; deliver through verified persistent Telegram/Owner Workbench when connected, otherwise keep it pending and show it at the next active conversation.
- Acceptance: several human-blocked nodes with independent successors; true dependency blocked; eventual grouped notification; recovery and no duplicate effects.
