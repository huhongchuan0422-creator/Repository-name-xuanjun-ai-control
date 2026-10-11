# XuanJun AI Control Plane

Private control-plane repository for XuanJun AI / XuanJun Yunhui engineering orchestration.

## Authority
- Owner-delegated task coordinator: ChatGPT Work; UK OpenClaw/Codex executes approved specs using the existing authorized quota route.
- Task source: this existing GitHub repository; current candidate is PR #17 head_sha, not a cached merge_commit_sha. Runtime state and leases remain in the existing ledger.
- Current status and execution order: canonical/PROJECT_STATE.md and plans/UNFINISHED_TASK_TRACKER_20261011.md. Assigned work is distinct from actual dispatch/deployment.
- Architecture source: 玄钧云汇开发架构与开发顺序 V2.7
- Phase order: Stage 0 asset audit -> Stage 1 UK AI development control plane -> subsequent stages.
- Production safety: no direct trading production writes from UK control plane.
- Tokyo starts as read/export/package migration source.
- Korea is the isolated Binance migration target.
- Secrets must never be committed; only SecretRef identifiers and evidence references are allowed.

## Git policy
- main is release/control-state only.
- Work occurs on task branches and PRs.
- Agents must not push production changes directly to main.

