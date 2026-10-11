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
OPENCLAW_DEVELOPMENT_HANDOFF=FAILED_CANDIDATE_RECEIVED_NEW_BOUNDED_DESIGN_APPROVED
OPENCLAW_OWNER_REPORTED_CANDIDATE=4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2
OPENCLAW_CANDIDATE_ARTIFACT_RECEIPT=PATCH_TREE_MANIFEST_VERIFIED
OPENCLAW_CODE_QA=FAIL
OPENCLAW_SECURITY=FAIL_OWNER_REPORTED
OPENCLAW_OLD_RETRY_PATH=HOLD_CHECKPOINT_OWNER_REPORTED
OPENCLAW_NEW_REPAIR_STARTED=A1_A2_DONE_B_REPAIRING_OWNER_RELAYED
OPENCLAW_REPAIR_CONTROL_SHA=76c0cfe7f7a4dd9ed52a9dc719897c95c437ba8b
OPENCLAW_REPAIR_SPEC_SHA256=deb334171fdbc10d9ab8abff046493526ca5c992428d514629a86cf32859fc6a
OPENCLAW_REPAIR_TRIGGER=OWNER_FEISHU_MANUAL
RUNNER_TO_OPENCLAW_AUTOMATIC_INTAKE=NOT_DEPLOYED_NOT_ACCEPTED
WORK_INTAKE_CANDIDATE_CODE=CANDIDATE_QA_SECURITY_REVIEW_PASS
WORK_INTAKE_PLATFORM_ADMISSION=HOLD
OPENCLAW_REPAIR_B=ISOLATED_245_OF_248_HOLD_SECOND_EXTENSION_APPROVED
OPENCLAW_REPAIR_C=NOT_STARTED_UNTIL_RELEASE_ADMISSION
STAGE1_RELEASE_ADMISSION=HOLD
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


## Bounded repair receipt — 2026-10-11 18:16 Asia/Shanghai

Owner relayed the UK OpenClaw receipt binding control SHA 76c0cfe7f7a4dd9ed52a9dc719897c95c437ba8b and spec SHA256 deb334171fdbc10d9ab8abff046493526ca5c992428d514629a86cf32859fc6a. A1 /root/repair_a1 and A2 /root/repair_a2 report STARTED in independent directories with openai/gpt-5.6-sol via existing OAuth/Codex. Agent names are session identifiers, not evidence of OS root execution. This is an Owner-relayed execution receipt, not an independent host probe. B waits for A2 contract freeze; C remains NOT_STARTED. Preserve this exact active source/spec and old failure budget/checkpoint; subsequent documentation commits do not restart this execution.

The automatic chain is separate: Runner source pickup is verified, but automatic intake/wakeup/persistent receipt is not deployed or accepted. Work's intake increment must deduplicate identical parent task/spec bytes across later control commits, retaining each control SHA as a receipt binding; it must import this manual start as an already-accepted receipt without another wakeup. No old Coordinator CODEX_EXEC or production write is authorized by intake.

## Latest Owner-relayed repair inspection — 2026-10-11 19:29 CST

A1 reported completed at ae72ec7405540a59e63273a5711ed8f38e66b20e; A2 reported completed/frozen at abbreviated local commit 9df09fa. B is repairing from fb2cc90 with two uncommitted test files. Owner relayed 248 tests: 241 PASS / 3 FAIL / 4 ERROR, activation-store contract compatibility, Owner callback 403 and dashboard manifest hash synchronization. Independent QA/security NOT_STARTED; no deployment or production mutation reported. These are relayed observations, not Work-reproduced tests or independently acquired new artifacts. GitHub could not resolve A1/A2 commit references at this check; this does not invalidate a local commit. Full A2 SHA, final clean combined B SHA, patch/manifest bytes and clean final combined tree remain NOT_RECEIVED.

Current source/spec remain 76c0cfe7/deb33417; preserve original task identity, failure budget and checkpoints. Do not restart A1/A2 on later control metadata updates. Current scope is B integration repair, then same-frozen-artifact independent QA/security; release remains HOLD and C NOT_STARTED. End-to-end delivery/restart acceptance is indexed in plans/TASK_INTAKE_POWER_RECOVERY_ACCEPTANCE_20261011.md. It refines existing gates, grants no new production permission, and creates no new task registry.

## B scope admission — 2026-10-11 19:32 CST

Owner reports B implementation at fb2cc9081fa8d215bf186046b53bae9b9334ad7b, subset 228 tests and compile/diff checks PASS; full 248 remains 241 PASS/3 FAIL/4 ERROR. Two diagnostic test files and cache leave working tree unclean. B stopped for the concrete test/bootstrap scope boundary. Work approves plans/WORK_APPROVED_B_SCOPE_EXTENSION_20261011.json under the same parent/spec/B attempt, without a new task, budget reset, A1/A2 restart or production change. The permitted continuation updates exactly three obsolete test modules and scripts/uk-dev-bootstrap.py to the canonical activation/socket contract; never restores DB-string fallback, weakens auth, drops negative assertions or executes the installer. EXTENSION_EXECUTOR_RECEIPT=NOT_VERIFIED; source publication is not proof B resumed. The current old-spec intake dedupe remains unchanged.

B scope continuation must acknowledge original spec deb33417 plus the exact new extension file SHA256. This revision is an additive contract for the same B attempt, not a new intake task; the original task/spec bytes and dedupe key remain fixed. No Work session-directory permission, new gh credential or Feishu routing grant is required to read the controlled Runner checkout. Automatic delivery of this addendum is not installed or verified; request a real bound receipt before reporting RESUMED.

## Isolated candidate result and second B scope extension — 2026-10-11 20:05 CST

Owner reports prior extension89d22f verified and its four files aligned. The earlier local248/248 relied on two uncommitted test diffs and is superseded: isolated checkout925cfba3171ebb43a872ef2a0ab7ffc390a5a516 returned245 PASS/1 FAIL/2 ERROR of248. IndependentQA/security NOT_STARTED; no deployment. Owner pins minimal delta a1fa635117286a0ccdf4c83060d9e8042719c07401b3fa13226ca176cc168861; actual new bytes not received by Work, local commit object unresolved via GitHub.

Work approves plans/WORK_APPROVED_B_SCOPE_EXTENSION_V2_20261011.json for exactly stage1/test_development_service.py and stage1/test_owner_dashboard.py under the same B checkpoint/budget. Old isolation fixtures may follow broker v2 while retaining privilege/fence/resource negative tests. A single admitted Worker may be pinned5.6 with zero internal fallback; dashboard must preserve Owner global6.1 primary/5.6 sole fallback and distinguish that policy from actual/Worker observations. Global5.6-only/zero-fallback policy assertions are NOT_APPROVED. No production change, new task, A1/A2 restart or original-spec mutation. ExtensionV2 receipt/resume NOT_VERIFIED. Freeze and isolate the final committed combination before QA/security; no local dirty-tree green substitution.
