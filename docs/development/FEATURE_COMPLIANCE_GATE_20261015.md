# Feature Compliance Gate — implementation contract (2026-10-15)

### 1 Design

Purpose: validate that registered FEATURE_ID entries link a design section, development-stage section, concrete acceptance criteria, test files and reuse decisions. Run without paid AI, credentials, or server access. Do not treat a passing structural check as an independent code/security audit.

### 2 Development Sequence

Bootstrap an isolated compliance tool branch from main; verify deterministic negative and positive cases; ship a PR check with stable job name `feature-compliance`; verify against a normal PR, merge only after evidence review; then configure the main branch protection required check. This must not merge PR118/PR17, deploy production, modify Fence, or trigger financial operations. Later, add new-file/FEATURE_ID association with migration exceptions for historical work; do not claim that is implemented in this bootstrap.

### 3 Acceptance

A valid registry entry passes; missing design, stage, criteria, test file, or verified/deployed evidence fails. The workflow runs on every pull request and main push; preserve a stable status-check context and use existing GitHub Actions. Required status check becomes enforceable only after a successful bootstrap and a separate branch protection setting by an administrator.

### 4 Rollout and rollback

Release isolated code and registry first, then confirm a normal PR run. Record workflow ID, tested SHA, success/failure evidence, and administrator's branch protection setting. On false blocks, fix in a new PR; do not disable safety gates silently. A GitHub CI success does not imply server synchronization.


### 5 Original community preview registration

Issue76 adds only the missing default-branch registration at the existing `.github/workflows/chatgpt-community-wechat-sp-offline.yml` path. Selecting the original community branch executes that branch's reviewed workflow, not this registration stub. This main-derived PR carries no community business source, SDK, upload Secrets, deployment or self-hosted job. Existing upload Secrets references stay exclusively in the original branch workflow; no new credentials or permissions. PR136 is a distinct older fixed-package workflow and is not reused or changed here.

The registration inputs are preview_enabled=false, exact preview_source_sha, fixed uk-path-candidate and preview_evidence_run_id. An enabled request on main, another branch/repository, mismatched/malformed SHA, wrong target or absent numeric evidence ID fails. Even a structurally valid registration guard only reports registration, never performs an upload. Actual selected-branch preview must retain its original test gate, require a successful same-SHA push Hosted evidence run plus unexpired source artifact, rebuild the current exact source package, and retain backend readiness and original runner identity gates. No dummy push or automatic dispatch.

The main-based Hosted acceptance only executes registration negative/positive tests and existing normal PR governance. This PR is not approval to merge, dispatch, access a server or upload. Original 12516640 SP40041063448/Preparation40041063447 and 66-route evidence remain separate reusable evidence.
