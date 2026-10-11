# Event-only GitHub mediation policy — Owner mandate 2026-10-12

**Status: proposal/documentation only, not proof of deployed ChatGPT event trigger or UK intake.**

Owner explicitly requires GitHub to be the *sole relay* between the ordinary ChatGPT conversation and UK OpenClaw. Owner must not contact OpenClaw directly, relay messages, or trigger model inference just to read state.

## Workflow

1. Owner supplies goals to ChatGPT. ChatGPT writes bounded task/spec or reviewed decisions to GitHub through the connected GitHub tool.
2. GitHub native push/comment/review/supported event triggers the **existing** scoped event continuation and UK Runner/intake path. It does not itself prove the UK intake/service/worker is installed or awake; verify real event delivery and task identity.
3. UK non-model scripts validate event provenance, exact repo/PR/HEAD/spec digest, single canonical ledger/task, lease/fence/epoch, duplicate/idempotency key, and write durable accepted/rejected receipts. No model used for routine event observations.
4. Only a *qualifying unprocessed result or explicit authorized task* may dispatch ChatGPT development/review. Existing connected ChatGPT event automation has been reported enabled; a successful normal-ChatGPT (non-Codex) execution event has NOT been proven. Never state that GitHub can automatically wake arbitrary chats merely because a comment exists.
5. ChatGPT submits patch/result to GitHub as data. UK mechanical checkout, syntax/static CI, independently reviewed same-hash release gate and controlled execution happen only when P2/P3 authority is satisfied.
6. Owner receives only material completed milestones, new failures or exact human approvals. An event created by this same script/ChatGPT decision, a duplicate, or a metadata-only edit is **SKIP** to avoid event recursion.
7. Any broken event route is HOLD; do not ask Owner to initiate a new OpenClaw conversation or substitute model polling. Preserve original checkpoint, budget, and writer exclusivity.

## Quota and failure gates

See `plans/UK_SCRIPT_FIRST_QUOTA_POLICY_20261012.md` and `plans/UK_REPEATED_ERROR_30_60_MIN_STOP_POLICY_20261012.md`. All mechanical event processing must use scripts at zero inference. At 30% of verified Codex period usage prefer independently verified non-Codex ordinary ChatGPT chat; if its quota is verified exhausted and the comparable daily total <50%, Codex OAuth may resume. At 50% verified daily total, stop development inference through the next Asia/Shanghai day pending fresh meter. Non-comparable, unknown meters or chat eligibility => HOLD. Same error 30 minutes => Owner report + evaluate alternative; 60 minutes => stop original strategy, require changed method and review.

## Existing project truth

PR #17: old 120-second model poll supervisor disabled after quota pressure; event continuation reportedly remains enabled. UK persistent dispatcher/ledger/broker, GitHub intake, and real two-task P3 are not installed/accepted. Fence 17RR remains revoked; dirty worktree diff is preserved. No root/systemd or production authority is conferred by this document.

## Acceptance

Prove: a real ordinary ChatGPT event handler (not Work/Codex fallback); real GitHub event handoff without Owner relay; actual UK intake path; negative duplicate/self-loop guards; CLI/app-server/native harness/OpenClaw Codex runtime `CODEX_INFERENCE_CALLS=0` for #19; separate `NEW_PAID_API_USAGE=NONE` evidence; independent QA/Security and P2/P3 host recovery gates. Until then `CHAT_EVENT_E2E=UNVERIFIED`.
