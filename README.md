# XuanJun AI Control Plane

Private control-plane repository for XuanJun AI / 玄钧AI新 engineering orchestration.

## Authority
- Architecture source: 玄钧AI新开发架构与开发顺序 V2.7
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

The current authoritative V2.7 development document is [available here](docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.md); [Historical Word content reference with the current display brand](docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.docx). The Word content reflects an older revision and is not synchronized with current MD sections or business rules; use the current MD as the development reference. Section7.7 incorporates Owner's ecology rightsV1.1 revision, with related node2.15 and acceptance requirements. [Historical byte manifest](docs/development/MANIFEST.json) retains the original 2026-10-14 synchronization evidence; it does not bind these later-edited documents. The 2026-10-19 update changes the public display brand to 玄钧AI新 only, including English brand positions. Historical quoted evidence and the separate Yunhui Ecosystem Rights business name are retained. Current candidate bytes require their own review and binding. It does not grant P2 installation, activity launch or ecological issuance.

### Current full-site brand review package

The current 玄钧AI新 full-site review output uses the explicit `FULL_STATIC_BRAND_REVIEW_V1` contract: exactly 1,241 archive members, 1,197 public overlay files, 101 new public paths and 1,288 final public files. The reader checks the exact fixed non-public member set, source-pin/overlay path equality, final manifest byte hashes, stage provenance and the original pinned source archive. Existing `LEGACY_UNIFIED_V1` (459 members) and `FULL_STATIC_REVIEW_V1` (460 members) remain separate exact contracts and cannot accept this new package by count relaxation. New artifacts require fresh source, manifest, package and approval bindings through the existing process; review output does not issue installation or execution permission.
