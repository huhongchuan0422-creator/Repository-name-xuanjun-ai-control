# P2 GitHub 凭据与英国原生接口准备证据（2026-10-13）

冻结制品保持不变：artifact 11796280855，源码 f01148fdeaa60c0a6dc1e9d30e9e707b61a65c06，源码树 3fc23b2a01bd8f01ea0edcef9216ded7313409c2；Release HOLD / INSTALL NO。

## 实际完成

- Owner 在英国终端运行受保护输入程序，返回 PROTECTED_GITHUB_INPUT=STORED、REPOSITORY_READ=VERIFIED、WRITE_PERMISSION=NOT_TESTED。凭据仅留于主机 root 私有文件，未写入本证据。
- 英国任务 [38379261267](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38379261267) 成功克隆私有 bare 镜像并验证上述冻结提交与源码树。受保护镜像回执 SHA256：2b45e14a2045bdc9ae7c23f282a31d21635db97c66e2a0394a10de0c6f360395。
- 英国任务 [38380533693](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38380533693)，job 115239523068，结论 SUCCESS。只读 SDK 检查与离线 Node import 验证 context-DyPstb2Q.mjs 具名导出 resolveSandboxContext、ensureSandboxWorkspaceForSession，均为函数。入口 SHA256：db7fc7539455da0c564d4ded0d04da1c764a46903d1632489b8bd04641098320。
- 本任务原生策略输入回执 SHA256：f5627dfb826c343447ecdcd6ae6f4bda1d51941d1fc6db464d4eeccd4f94500f。

## 实际发现与未完成条件

现有 OpenClaw 配置 SHA256 为 569e7f4eb66860caf05e23fc1d00098d9f67c9204347b979ab39696f184fbba3；defaults.sandbox 未显式配置，所检查 agent 的显式 sandbox 条目为空。不能将“接口导出通过”替代真实 Docker 沙箱策略及读写隔离验收。

完整受保护安装计划仍须纳入：developer 写工作区与 platform-engineer 只读工作区的明确策略、原生 peer identity 文件、Owner callback 私有凭据与 GitHub intake 凭据目标的受保护引导、完整 provisioning 哈希、旧 writer 停止及 cgroup 空证明、真实 relay 接线与 outbox ACK、TLS 服务和续期安排。GitHub 写权限未测试。不得据此声称可正式安装。

本轮没有启停生产服务、修改现有 OpenClaw 配置、运行模型、启动第二个 writer，或修改 canonical ledger/lease/epoch/outbox。

责任划分不变：Work 负责 P2 源码与完整安装前置准备；ChatGPT 负责第4项开发闭环与第5项独立审核；正式安装仍受独立 Release 与 Owner 手动边界约束。
