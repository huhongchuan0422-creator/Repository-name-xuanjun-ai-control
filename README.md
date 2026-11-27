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

The synchronized V2.7 development document is [available here](docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.md); [editable Word version](docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.docx). Section7.7 incorporates Owner's ecology rightsV1.1 revision, with related node2.15 and acceptance requirements. [Exact byte manifest](docs/development/MANIFEST.json) distinguishes document synchronization from runtime acceptance and physical server receipts. It does not grant P2 installation, activity launch or ecological issuance.

## Mini 前端开发/测试环境（2026-11-27 修测冻结补充，不绑定任何作者 session）
- 运行时：Node 22.14.0（镜像 /opt/node-v22.14.0-linux-x64/bin）、npm 10.9.x、Python 3.11（无 pip 时复用已验证 vendored 测试依赖）。
- 测试依赖（版本按 CI 声明 cryptography==50.0.2；无网络环境可复用既有已验制品）：`PYTHONPATH=<deps目录> `（内含 cp311 cryptography/cffi/pycparser）+ 仓库根与 tests 目录。
- 现成命令（仓库根执行）：
  - `node tests/merchant_submit_contract.cjs` — 本人直提合同（confirm/revision/UNKNOWN GET）合成检查，零网络。
  - `CASE=success|unknown|gate|platform-phone|stale-platform|legacy|original-gap python3 tests/submit_chain_http.py` — 原 Page/session HTTP 到原服务，provider 边界全合成。
  - `node clients/community-mini/merchant-pages.test.cjs` — 页面回归（真实主入口 onOwnerSubmitTap 驱动）。
- 配置/模板：开发版上传仅需环境变量 `WECHAT_MINIPROGRAM_PRIVATE_KEY`（SecretRef，仅经 env 注入）与 `COMMUNITY_MINI_CI_MODULE_ROOT`（miniprogram-ci 安装位）；无作者身份白名单、无 session 锁；入口 scripts/community_mini_preview.cjs（preview|upload 二选一，upload 需 workflow_dispatch 或 control_source_sha 精确 push，见 EXPLICIT_FIXED_PRODUCT_UPLOAD_REQUIRED L16-19）。
- 安维安装入口：本仓为自包含 portable 源（.git 独立、无 alternates/锁）；同版交付 = 分支 feature/chatgpt-community-wechat-sp-offline-20261017 上的本地 commit + `git bundle`，安维在原授权 GitHub 渠道 fetch/push 并以 ls-remote 回读 SHA 为同步证据；本站不新增权限、不强推。
