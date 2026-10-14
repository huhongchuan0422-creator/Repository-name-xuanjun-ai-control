# Feature Compliance Gate — implementation contract (2026-10-15)

### 1 Design

Purpose: validate that registered FEATURE_ID entries link a design section, development-stage section, concrete acceptance criteria, test files and reuse decisions. Run without paid AI, credentials, or server access. Do not treat a passing structural check as an independent code/security audit.

### 2 Development Sequence

Bootstrap an isolated compliance tool branch from main; verify deterministic negative and positive cases; ship a PR check with stable job name `feature-compliance`; verify against a normal PR, merge only after evidence review; then configure the main branch protection required check. This must not merge PR118/PR17, deploy production, modify Fence, or trigger financial operations. Later, add new-file/FEATURE_ID association with migration exceptions for historical work; do not claim that is implemented in this bootstrap.

### 3 Acceptance

A valid registry entry passes; missing design, stage, criteria, test file, or verified/deployed evidence fails. The workflow runs on every pull request and main push; preserve a stable status-check context and use existing GitHub Actions. Required status check becomes enforceable only after a successful bootstrap and a separate branch protection setting by an administrator.

### 4 Rollout and rollback

Release isolated code and registry first, then confirm a normal PR run. Record workflow ID, tested SHA, success/failure evidence, and administrator's branch protection setting. On false blocks, fix in a new PR; do not disable safety gates silently. A GitHub CI success does not imply server synchronization.
