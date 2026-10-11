# Repeated-error escalation and stop policy — Owner mandate 2026-10-12

This addendum applies to all UK development, P2/P3, Issue #19, and future autonomous task runs. **SOURCE_ONLY; NOT DEPLOYED.** Deterministic scripts implement timers and state changes; no model may be invoked just to check elapsed time.

## Fingerprint and timing

- Identify each failure by a stable fingerprint: parent task/spec + phase + normalized error code + affected component + immutable artifact hash + relevant environment identity. Do not reset its clock when retrying, changing worker/session/fence, or paraphrasing the error. Record `first_seen_at`, `last_seen_at`, retry count, evidence links, proposed alternatives, and effects in the **existing canonical ledger** (not a new queue).
- At **30 elapsed minutes without verified resolution of the same failure**: create exactly one Owner notification with fingerprint, attempts, quota consumed if verified, impact and two or more materially different remedies (or explicit reason alternatives are unavailable). Reassess whether the approach is wrong. Deduplicate notification; do not send repeated identical alerts.
- At **60 elapsed minutes without verified resolution**: set the affected task/failure to `HOLD_CHANGE_METHOD`, revoke permission for further identical attempts, stop that strategy, preserve artifacts/checkpoint/budget and reconcile unknown side effects. No new model inference or automatic reruns for the same approach. Require a genuinely different mechanism, bounded review and approved restart decision; a fresh agent/fence is not a new approach.
- 30 and 60 minutes are measured in wall-clock `Asia/Shanghai` based on durable monotonic/UTC timestamps. An executor restart, callback timeout, changed discussion, or calendar day boundary does not restart the fingerprint clock. Suspend only the affected task; unrelated safe work can proceed within existing gates.
- 30-minute and 60-minute notifications are *condition-driven*; no model polling. A trusted supervisor/cron may examine the canonical ledger mechanically only after being independently installed and admitted. No customer messages.

## Existing incident

PR #17 fence 17/17R/17RR experienced repeated requester lifecycle replacements. Status remains `HOLD_NO_SAFE_BOOTSTRAP`, old writer revoked, checkpoint preserved, and model-based 120-second supervisor was disabled. It already qualifies for the 60-minute stop; **do not restart the same requester-bound native child**. The alternative must be genuinely independent durable host supervision with unique ledger/fence and authorized OAuth access, or a mechanical, isolated non-model task to validate durable scheduling before model integration.

## Gate layering

The Owner's additional budget policy in `plans/UK_SCRIPT_FIRST_QUOTA_POLICY_20261012.md` also applies: script first; switch at verified 30% Codex subscription consumption to independently verified non-Codex ChatGPT chat; verified exhaustion of that chat may permit Codex return if under the daily aggregate cap; stop all development inference at 50% verified daily total until next day and fresh meter. Unknown quota or alternate model availability means HOLD. Cannot add percentages from unrelated quota denominators.

Implementation requires deterministic tests for exact 29:59 / 30:00 / 59:59 / 60:00 boundaries, retry/worker/fence changes, duplicate notifications, checkpoint retention, and method-change admission. A document is not proof the runtime enforces this.
