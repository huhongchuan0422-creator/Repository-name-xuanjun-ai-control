# UK development: script-first inference budget guard (2026-10-12)

Status: **SOURCE PROPOSAL / NOT INSTALLED / NOT AN EXECUTOR / NOT P2 OR P3 PASS**.
Owner rule supersedes any prior plan that spends model quota on mechanical supervision. This file is an explicit addendum to `plans/MODEL_POLICY_20261011.md` and the existing PR #17 staged-execution contract. No existing lease, task, OAuth session or production service is modified by documenting it.

## Mandatory priority and quota limits

1. **SCRIPT_FIRST**: use trusted deterministic scripts, GitHub Actions, local lint/compile/test, immutable hashes, SQLite reads, status snapshots, retries gated by observed side effects, and static UI/report rendering. Do not use a model to poll, keep a heartbeat, format status, repeat unchanged QA, calculate hashes, compare metadata, watch logs or notify that nothing changed. A supervisor event must not recursively trigger itself.
2. **At 30% Codex subscription-period consumption** (`codex_period_used_pct >= 30`), stop new Codex inference and prefer an independently verified **ChatGPT non-Codex chat** generation/review route. A ChatGPT chat that runs a Codex CLI, Codex app-server, native Codex harness, or OpenClaw Codex runtime is NOT a non-Codex fallback.
3. **If and only if the ChatGPT non-Codex chat quota is verifiably exhausted**, resume the existing **ChatGPT/Codex OAuth subscription** route while the daily budget is strictly below 50%. A chat error, inaccessible UI, unknown quota or unverified independent review is NOT exhaustion. No Astra, alternate model, API key, new paid API, credential copying, or production auth deletion.
4. **At 50% of the day's unified model budget** (`daily_total_used_pct >= 50`), stop all new development inference (Coordinator, Developer, QA, Security, retries, cron, intake, restart and fallback included). Only free of inference, already-authorized safe mechanical work may continue; never execute an unreviewed patch. Do not resume model work before **00:00 Asia/Shanghai on the next calendar day**, and only after a fresh authoritative budget reading, unique-writer reconciliation and relevant gates.
5. Fresh quota evidence is mandatory before **every** inference call, not just once per task. It must be no older than ten minutes and bind the correct local day, quota source, observation time and measured provider route. Unknown/missing/stale/non-comparable measurements => `HOLD`; the script MUST NOT extrapolate from "17% remaining" or other historical/week-only screenshots.
6. Daily spending across independent Codex and ChatGPT quota pools cannot be obtained by adding percentages with different denominators. `daily_total_used_pct` requires a **proven comparable aggregate meter** or a precisely owner-defined normalized budget in the canonical ledger. If neither exists, `daily_total_meter_verified=false`, and model admission stays `HOLD`. Source availability, quota reset, and billing status remain UNKNOWN until measured.
7. Do not create a second task queue/ledger or start a second writer. Preserve task/spec/run/session/workdir/checkpoint/lease/fence/epoch/budget/side-effect evidence; existing fence 17RR stays revoked. These controls govern *admission*, not a synthetic claim of execution.

## Decision matrix

| Evidence | Inference admission |
|---|---|
| Daily total used >= 50% | HOLD until next Asia/Shanghai day + fresh evidence |
| Daily total unknown, stale, wrong day or non-comparable | HOLD, do not poll via model |
| Codex period used <30%, Codex independently AVAILABLE | CODEX_OAUTH |
| Codex period used >=30%, verified independent non-Codex ChatGPT AVAILABLE | CHATGPT_NON_CODEX_CHAT |
| Codex period used >=30%, ChatGPT quota verified EXHAUSTED, Codex AVAILABLE, daily <50% | CODEX_OAUTH |
| Any other combination | HOLD |

`CODEX_INFERENCE_CALLS=0` for Issue #19 must come from independently audited **actual runtime and fallback** invocation counts, including OAuth CLI/app-server/native harness/OpenClaw Codex; this pure policy script only establishes `gate_inference_calls=0` for itself. `NEW_PAID_API_USAGE` is separately audited. Never infer zero Codex inference from no API key.

## Deterministic implementation

- Implementation: `stage1/uk_quota_policy.py`; no network, subprocess, model SDK, OAuth or API access.
- Wrapper: `scripts/uk-quota-gate.py --evidence /SECURE/CANONICAL_LEDGER_EXPORT.json`. Exit 0 means a verified route was allowed at the observation instant; exit 3 means HOLD. JSON response contains `route`, `reason` and `resume_not_before`.
- Tests: `python3 -m unittest discover -s stage1 -p 'test_uk_quota_policy.py' -v`. Tests use synthetic evidence only; do not spend quota.
- Evidence file must be protected, regular, non-symlink, non-world-readable/writable under trusted parents; it is a read-only export from the **existing** canonical ledger. Merely setting `quota_source=AUTHORITATIVE` inside untrusted data is not attestation: caller must verify provenance, meter semantics and immutable evidence reference before writing the export.
- A deployment dispatcher/Coordinator must **invoke this guard before any actual model path**, attach the bound verdict to its canonical ledger and fail closed if the guard or evidence is unavailable. Until this wiring and its tests are verified on the actual installed UK host, this is **SOURCE_ONLY_NOT_ACTIVE** and must not be reported as enforced.
- At next-day resumption, recompute the day-specific 50% allowance from *new* authoritative readings; a date change alone does not prove quota reset or license another attempt.

## Current project blockers, separate from quota policy

As of PR #17 receipt `6115075801`, a previous 120-second inference-consuming supervisor was disabled after about 17% weekly quota remaining was observed. No replacement polling is allowed. There is no admitted durable UK Developer, P2 not installed, P3 not started; Issue #19 non-Codex entrypoint not verified, so it is not usable by assumption. UK root/systemd/cgroup/OAuth changes still need one independently reviewed, exact scoped approval package. Do not activate this gate by overwriting production files from a PR comment.

**Acceptance**: deterministic tests; verified authoritative dual-route metering and day aggregation; admission traces at 29.99/30/49.99/50; ChatGPT exhausted vs technical error; unavailable model and unknown evidence HOLD; measured script overhead no model inference; independent reviews; then authorized real-host admission. Only P2/P3 and #19 E2E may claim completed after their own separate real end-to-end gates.
