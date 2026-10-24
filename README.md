# XuanJun AI Control Plane

Private control-plane repository for XuanJun AI / XuanJun Yunhui engineering orchestration.

## Authority
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

## Mandatory development execution rules

Work and OpenClaw must read and follow [开发执行与反馈强制规则](docs/DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md) before dispatch or continuation. Deliver results, actively advance ready nodes, track missing receipts, preserve interrupted tasks and unblock independent work. Documentation and alerts are not proof of deployed execution capabilities.

## Development document and ecology rules

The current integrated V2.7 development document is [the Markdown version here](docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.md); the [2026-10-14 editable Word historical snapshot / 历史可编辑快照](docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.docx) is retained for audit history and is not claimed to be synchronized with later Markdown additions. Section7.7 incorporates Owner's ecology rightsV1.1 revision, with related node2.15 and acceptance requirements. [Exact byte manifest](docs/development/MANIFEST.json) distinguishes document synchronization from runtime acceptance and physical server receipts. It does not grant P2 installation, activity launch or ecological issuance.
