# Owner autonomous execution directive — 2026-10-10

Status: OWNER_APPROVED_POLICY / NOT_A_CLAIM_OF_DEPLOYMENT.

## Communication until authenticated Owner Workbench + Telegram notification are truly live
- Owner does not intend to initiate chat turns. For tasks that genuinely require human action or decision, report consolidated instructions/results in this ChatGPT conversation while it is available. The chat window **cannot initiate unsolicited messages or continue running after the turn ends**. Persistent notification and continuation must be implemented and verified using the approved Stage1 architecture; until then, no claim of autonomous notification or background execution.
- For authorized, low-risk work that does not require a human, continue in the documented V2.7 dependency order using actual available tools and persistent execution systems. Do not unnecessarily interrupt Owner.
- Prioritize integration of authenticated Owner progress/approval board and Telegram actionable notifications using existing Portal, Registry, CRM, Outbox, and authority systems; do not create duplicate infrastructure. Stage1 dependencies, CI, independent QA, security audit, release gates and staging/canary stay mandatory.
- Ordinary task successes should not spam Telegram. Preserve checkpoint, lease/fencing, duplicate-safe outbound events, and restart/recovery evidence.

## Korea resources and inactive workloads
- Owner confirms Korea host has about 2 GB RAM and is an approved **candidate** for Binance migration, noting Tokyo formerly operated at a similar size before RAM expansion.
- Owner reports EasiCoin business effectively inactive and Novel Factory not planned to start in the near term. This is business priority input, NOT proof that existing systemd processes are stopped or that resources are free.
- Do not automatically terminate/delete/disable EasiCoin or Novel services; inventory live processes, measured memory/CPU/disk and auto-start status first, then develop an isolation-aware capacity plan. Use bounded work and explicit acceptance criteria, avoiding OOM and service collisions.
- Korea Binance order-write remains disabled. Migration must pass resource, isolation, secrets, API read-only, shadow, reconciliation, rollback, independent verification and explicit high-risk cutover gates. Preserve Tokyo rollback and October 21 expiry/extension decision.

## Next safe actions
1. Merge this directive only after normal PR checks; sync Canonical with live evidence, not unverified historical claims.
2. Verify currently connected Actions/Runner execution capability and existing protected services; no claim of a scheduled run unless witnessed.
3. Complete Stage0 reuse map, Stage1 prerequisites 1.1—1.7; prioritize incremental 1.8—1.13 Owner console/Telegram/checkpoint work, then 1.14—1.15.
4. When genuine human intervention is indispensable, batch actions in the active conversation. Otherwise operate through verified durable orchestration, and checkpoint if that infrastructure is absent.

Safety remains: no raw credentials in Git/CI; no Tokyo production mutation; no UK trading writes; no Korea Binance live orders until distinct release approval.