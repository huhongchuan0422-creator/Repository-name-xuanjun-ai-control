# Canonical Project State

ARCHITECTURE_VERSION=V2.7
CONTROL_REPOSITORY=huhongchuan0422-creator/Repository-name-xuanjun-ai-control
CURRENT_STAGE=0
CURRENT_BATCH=STAGE0_AUDIT_AND_STAGE1_CONTROL_PLANE_COMPLETION
CURRENT_TASK=XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1
STATUS=IN_PROGRESS
TASK_ASSIGNMENT_AUTHORITY=CHATGPT_WORK_OWNER_DELEGATED
EXECUTOR=UK_OPENCLAW_CODEX_WORKER
TASK_SOURCE=EXISTING_GITHUB_CONTROL_REPOSITORY
RUNTIME_DISPATCH=NOT_VERIFIED
OPENCLAW_DEVELOPMENT_HANDOFF=WORK_APPROVED_SCOPE_PENDING_EXECUTOR_RECEIPT
STAGE0_FULL_INVENTORY=NOT_VERIFIED
STAGE1_PRODUCTION_E2E=PARTIAL

## Owner priorities
1. Read and follow V2.7.
2. Re-audit Tokyo reusable assets.
3. Deploy/migrate the UK development control plane.
4. Migrate Binance production from Tokyo to Korea with isolation, shadow/canary, rollback and evidence.
5. After these migrations, continue strictly in V2.7 dependency order.
6. Interrupt Owner only for genuine human verification/authorization.

## Safety
TOKYO_TRADING_PRODUCTION_WRITE=DENY_UNTIL_MIGRATION_GATE
UK_TRADING_PRODUCTION_WRITE=DENY
KOREA_BINANCE_TARGET=ISOLATED_PREPARE_ONLY_UNTIL_CANARY
SECRETS_IN_GIT=DENY
MAIN_DIRECT_AGENT_PUSH=DENY

## Verified facts
- Private GitHub control repository exists and ChatGPT has push/admin-level repository permission through the connected GitHub integration.
- ChatGPT -> GitHub -> GitHub Actions -> log read -> automatic code repair -> rerun -> PASS was proven in an isolated V1 test repository.
- Tokyo canonical trading root was observed at /opt/trading-system.
- Tokyo discovery evidence from 2026-10-10 reported TOKYO_PRODUCTION_MUTATION=NO and MIGRATION_EXECUTED=NO.
- UK OpenClaw 2026.9.9 / selected Codex plugin 2026.9.9 / Codex 0.160.0 were verified by Owner-assisted host/hash-guarded output on 2026-10-11. Actual openai/gpt-5.6-sol inference returned provider openai and the exact nonce, exit 0. Owner observed the Feishu XJ_FEISHU_56_OK reply. The Feishu turn's actual model metadata, bounded failover and primary recovery remain NOT_VERIFIED.
- All four host-guarded Runner inventory jobs passed in run 38124100959 at commit 7ee62840ef0f18e863cfd6b0b67f4d3cd320f4fa. UK/Tokyo/Korea/Domestic Runner access is verified within that read-only scope. Korea iZmj7a5kwr75qc1tul4kf9Z has 2 CPU / 1915884 kB MemTotal and existing novel/yibi unit names; Binance target resource fit, isolation and deployment remain NOT_VERIFIED. Unit names alone do not prove active load.

## Next executable dependency
Continue the existing Stage 0 inventory while completing Stage 1 controlled Worker/dispatcher activation, independent QA/security/release gates and the HTTPS Owner workbench. All four Runner paths have fresh read-only execution evidence; root deployment access and production migration are separate gates. Preserve the current Stage 0 task ID as the parent audit scope, not as a claim that no Stage 1 development occurred. Existing-node work and exact dependencies are indexed in plans/UNFINISHED_TASK_TRACKER_20261011.md; this file does not create a second runtime task queue.

## Tokyo Runner verification (2026-10-10 20:50 Asia/Shanghai)
- Runner registered as `xuanjun-tokyo-readonly` with matching custom label, work folder `_work`, runner version 2.337.0.
- systemd unit `actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.xuanjun-tokyo-readonly.service` observed `active` and `enabled`, running as uid/gid 1001 `githubrunner` with no supplemental groups.
- Runner journal evidence: `Connected to GitHub`, `Listening for Jobs`, `tokyo-discovery` job completed `Succeeded` at 2026-10-10T12:50:16Z.
- OS checks observed `TRADING_READ=YES`, `TRADING_ROOT_WRITE=NO`. The four inspected directories (`/opt/trading-system`, `trading_execution`, `ai_service`, `runtime`) were `drwxr-xr-x admin:admin`.
- **Scope of PASS:** registration/service/first workflow execution only. **Security status: PARTIAL / NOT_VERIFIED** for recursive file write permissions, ACLs, other writable locations, workflow trust/branch protection and availability of sensitive data. Naming the Runner `readonly` does not enforce read-only access.
- Current workflow `.github/workflows/tokyo-readonly-discovery.yml` has `workflow_dispatch` and main push-on-workflow/script triggers; token `contents: read`. Workflow/script are currently discovery-only, but future edits could expand execution. Production write authority must remain forbidden.
- No Binance migration or production cutover occurred. Avoid raw secrets in CI logs/artifacts.
- Next: harden Tokyo Runner/workflow trust and permissions; verify successful job logs, then perform bounded read-only inventory. Continue domestic Runner and Korea isolated-prep in dependency order.

## Owner-delegated dispatch correction — 2026-10-11

Owner explicitly assigns task planning and dispatch to ChatGPT Work; the UK
OpenClaw/Codex path executes approved bounded tasks and returns evidence. Owner
does not need to send each development task to Feishu or reconnect a GitHub tool
for the UK conversational agent. ChatGPT's connected GitHub integration and the
existing host-guarded Runner are the control-plane acquisition path. No new task
system, wildcard credential grant or copied OAuth token is authorized by this.

Use PR #17 head_sha and the intended feature branch as the candidate source;
merge_commit_sha, refs/pull/*/merge, an old cached HEAD and main are not interchangeable
with that candidate. Verify current HEAD at admission, bind the approved spec to
that SHA, and use expected-HEAD protection on writes. Record source provenance.
A GitHub snapshot is not a runtime lease or dispatch receipt.

MODEL_PRIMARY=openai/gpt-6.1-sol
MODEL_ONLY_FALLBACK=openai/gpt-5.6-sol
MODEL_OTHER_OR_ASTRA=DENY
UNAUTHORIZED_PAID_API=DENY

Existing ChatGPT-managed authentication may use its authorized Codex quota.
Remaining quota and cost are UNKNOWN unless measured. Do not ask Owner to repeat
already-passed 5.6 installation/probes. Admission must verify isolated execution,
exclusive dispatch, dependency and budget gates, then register the approved spec
in the existing ledger. Do not insert CODEX_EXEC into the old Coordinator.
Independent ready tasks continue; an affected human dependency is recorded with
reason, checkpoint and next action. Assignment, admission, lease acquisition,
actual start and E2E completion must be reported as distinct states.

