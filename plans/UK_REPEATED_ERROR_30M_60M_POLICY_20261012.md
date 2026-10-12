# UK development error repetition: 30-minute alert / 60-minute hard stop
Date: 2026-10-12
Status: SOURCE AND POLICY ONLY — NOT INSTALLED OR ACTIVE ON UK

This is an Owner-mandated addition to `plans/UK_SCRIPT_FIRST_QUOTA_POLICY_20261012.md`, `plans/MODEL_POLICY_20261011.md` (latest policy overrides historical 6.1 text), and existing PR #17 staged execution contract. Applies to **all** UK development-related Coordinator, Developer, QA, Security, Release, cron, intake, approval, restart/recovery and ChatGPT non-Codex fallback attempts. It does not authorize model calls, privileged installation, release or a second task queue.

## Hard requirements

1. A repeated error is identified by **one stable root-cause fingerprint** bound to the original `task_id`, `spec_sha256`, `failure_fingerprint`, `first_seen_at`, current `last_seen_at`, `attempt_count`, actual evidence and existing canonical ledger record. Normalized message text alone is insufficient if the cause is ambiguous. Preserve the first occurrence when the same underlying failure repeats, including across process crashes, webhook events, days, sessions and coordinator restarts. A new wrapper/fence/worker or updated status comment **must not reset the clock**.
2. **30 minutes since first observation** of the same unresolved root cause: notify Owner once through the *existing* Owner notification/outbox channel, with concrete failed action, fingerprint, time range, repeated attempts, quota consumed if observed, current artifact/checkpoint, side-effect uncertainty and **at least two distinct alternatives** (or explicit evidence why no safe alternative exists). Do not send customer messages. Continue identical method only if still authorized, budget permitted and not past 60 minutes; prefer a lower-cost alternative immediately. One stable idempotency key per incident+milestone; avoid self-notifying GitHub comment event storms.
3. **60 minutes since first observation**: mandatory `HOLD_METHOD_CHANGE_REQUIRED`. Stop and fence any further *same-method* code/deployment/model retries; preserve checkpoint, ledger and budgets. No third/fourth recovery of the identical mechanism. Review the root cause, propose and independently assess an actually different implementation/entrypoint before a new method starts. The alternative must pass existing authorization/QA/Security/Release gates; if unavailable stay HOLD and notify Owner. An approval to try a new method cannot waive system permissions or enable paid API.
4. A resolved incident may close only with a durable, artifact-bound **real success / independent evidence**; speculative "looks fixed", a status comment, new fence, different wording or cleanup is not resolution. Multiple distinct failures can each have a separate incident only with independently defensible roots. The 60-minute HOLD applies to the original failure until real resolution.
5. **Scripts handle clocks, de-duplication, state comparisons, diagnostic collection and escalation** without AI inference. No model polling. An actionable Owner alert is generated as pure data, then the existing notification transport performs delivery and writes a delivery receipt to the canonical ledger. The script may not call an AI, deliver a message, create a task or modify services. Failure to deliver preserves a pending alert key for idempotent recovery, not repeated model invocations.
6. Before any new inference, both `UK_MODEL_QUOTA_30_CHAT_50_DAILY_V1` and this repeated-error policy must permit the attempt. Quota 50% HOLD overrides an otherwise allowed retry. 60-minute same-method HOLD overrides available quota. UNKNOWN evidence fails closed.
7. Existing production models: `openai/gpt-5.6-sol`, `fallbacks=[]`, existing OAuth. Do not use Astra or newly paid APIs; don't delete/copy login credentials. The Codex/ChatGPT quotas and actual usage must be independently metered. In particular, a GitHub workflow or pure script is not itself ChatGPT no-Codex acceptance.

## Decision contract

A **read-only export of the existing canonical ledger** must include schema, source attestation, stable task ID, 64-character spec SHA256, root-cause SHA256, first/last UTC-or-offset timestamps, local observation timestamp, `resolved`, `attempt_count`, and notification-delivery acknowledgments. Missing/untrusted/contradictory evidence returns `HOLD_ERROR_EVIDENCE_INVALID` (not a fresh attempt). Escalation is measured by actual elapsed wall time, **never by number of messages or per-run timers**.

| Same unresolved root cause elapsed | Script result | Model/worker behavior |
|---|---|---|
| 0–29:59 | `OBSERVE` | Existing authorization and budget gate still required |
| 30:00–59:59 | `ALERT_30M` | Owner report+alternative assessment; no silent continuation |
| >=60:00 | `HOLD_METHOD_CHANGE_REQUIRED` | Same-method attempts forbidden; no budget reset |
| Identity / time / source / old side effect UNKNOWN | `HOLD_ERROR_EVIDENCE_INVALID` | No retry until reconciled |
| Durable verified resolution | `RESOLVED` | Incident can close with canonical evidence |

Implementation: `stage1/uk_error_watchdog.py`, which has no inference/network side effects. The stable Owner notification IDs are generated deterministically but sent only through the existing outbox **after a reviewed integration**. Source tests: `python3 -m unittest discover -s stage1 -p 'test_uk_error_watchdog.py' -v`.

## Current PR #17 application

- Latest confirmed repeated error was requester-bound native Developer termination with Gateway journal `Harness completion requester lifecycle was replaced`; this failure occurred repeatedly and is beyond the 60-minute escalation. Status stays `HOLD_METHOD_CHANGE_REQUIRED` / `HOLD_NO_SAFE_BOOTSTRAP`; **do not spawn another native child**.
- Reference last UK receipt `6115075801`: previous 120-second model-based supervisor disabled; weekly OAuth quota ~17% remains **historic observation only**, not a daily meter. P2 not installed, P3 not started, Issue #19 not accepted. Keep the saved dirty checkpoint and no second writer.
- Next admissible step is a **script-only, independently reviewed design and exact permission/rollback package** for a durable mechanical supervisor using the existing canonical ledger (or a proven alternate durable mechanism). It must not assume standalone OAuth, a user systemd manager, a registered Developer agent, or a verified non-Codex ChatGPT chat source. UK privileged actions remain gated.
- `CODEX_INFERENCE_CALLS=0` and `NEW_PAID_API_USAGE=NONE` cannot be inferred from this source file; only runtime audit can support them.

This file is a specification, not a claim that a UK host or webhook has enforced it. Real host activation requires separate reviewed hash-bound integration into *every* inference/retry entrypoint and a 30/60 minute simulated evidence test without model calls.
