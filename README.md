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
