# ChatGPT 原生开发任务推进表（权威GitHub工作表）

记录时间：2026-10-16。状态规则：CODE_MERGED不等于独立审核/部署PASS；UNKNOWN不计完成。任何条目必须由真实提交、CI、独立审核与外部依赖证据更新。不覆盖Work/Dots/OpenClaw所有权。

## A. 已明确 OWNER=CHATGPT_NATIVE 的20项独立离线任务

| Issue | 工作范围 | Owner证据 | 代码阶段 | 审核阶段 | 下一动作 |
|---|---|---|---|---|---|
| 62 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 63 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 64 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 65 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 66 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 67 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 68 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 69 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 70 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 71 | Stage5广告/付款离线合同 | CHATGPT_NATIVE（Issue） | PR #73 已合并源码 | Hosted16/16通过；source merged；生产非范围 | 源码已交付，不重复；仅记录集成外部依赖 |
| 78 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 79 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 80 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 81 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 82 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 83 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 84 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 85 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 86 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |
| 87 | Stage5商家/门店/扫码离线合同 | CHATGPT_NATIVE（Issue） | PR #88 已合并源码 | Hosted20/20通过；独立源码审查限定通过 | 真实业务集成仍OPEN，目标授权前不重写 |

原始交付PR #73与#88均已MERGED。**准确证据更新**：PR73提交92e0f13，Hosted 16/16 PASS，Issue62–71已CLOSED（见PR73评论6162030833）；PR88提交7a1d62e，Hosted20/20 PASS，独立源码修复审查PASS_WITH_SCOPE_LIMITS（评论6162610215），已squash合入main（见6162724673），Issue78–87仍OPEN，因为真正业务集成与目标授权未完成。不得把“开着”重算成20个离线源码未开发。

## B. Stage5 Phase2 非外部依赖20节点（PR #122 / Issue #76）

| 节点 | 功能 | 登记 | 下一动作 |
|---|---|---|---|
| 01,02,03,04,06,07,08,17,19,20 | 报价、订单、权益、审核、市场、双币、订单中心、跨库审计、幂等、备份 | IMPLEMENTED_CANDIDATE 10项 | 验证准确HEAD与独立审核，不重复编码 |
| 05 | 身份/租户 | PARTIAL | 完善离线权限契约；生产身份阻塞独立记录 |
| 09 | 权益续费 | PARTIAL | 校验端到端只读交互、到期和异常 |
| 10 | Owner定价审批 | PARTIAL | 版本/权限/证据和交互验收 |
| 11 | Finance适配 | PARTIAL | 离线事件契约，真实验证器不得自证 |
| 13 | 订单与Finance事件 | PARTIAL | 保证同订单关联及重放拒绝 |
| 15 | 退款冲正 | PARTIAL | 离线审阅/状态不变量，真实退款阻塞 |
| 18 | WAL/故障恢复 | PARTIAL | 增加异常恢复/跨库非原子状态覆盖 |
| 21 | 标准部署制品 | PARTIAL | 内容/依赖/哈希/拒绝秘密统一核验 |
| 22 | 配置与密钥隔离 | PARTIAL | 仅离线server注入；生产密钥外部依赖 |
| 23 | 健康与回滚 | PARTIAL | fail-closed与可验证离线回滚计划 |

原计划外部依赖：12、14、16、24、25，不混入20项。PR122保持Draft；生产Release Gate仍HOLD。此表保留仓库现有登记的PARTIAL，未取得独立验收不升PASS。

## C. 历史ChatGPT相关控制面任务（责任逐PR确认）

| 锚点 | 已知事实 | 执行状态 | 下一动作 |
|---|---|---|---|
| Issue #19 | 三原生入口接力与回执闭环 | OPEN / 运行验收未整体证明 | 核对PR #35/#47/#50等任务所有权和回执；ChatGPT仅完成自有路径 |
| Issue #13 / PR #14–17 | Stage1持久队列与通知/受控运行 | OPEN / 尚未证明整体真实E2E | 复用现有Stage1、Python3.6与隔离门禁；不启动第二writer |
| PR #58 | Task4/5审核修复与ACK | OPEN DRAFT | 集中检查原源码/独立审核，代码可补则补，不替代Work/P2发布 |
| Issue #18 | 本地embedding | BLOCKED_BY_DEVELOPMENT_LOOP_ACCEPTANCE | 依赖尚未满足，不强行启动 |
| PR #122 | Stage5 25节点及ChatGPT代码增量 | OPEN DRAFT | 只补非外部范围，集中验收 |

## D. 进度原则

- CODE_MERGED / SOURCE_CANDIDATE / TEST_PASS / INDEPENDENT_AUDIT_PASS / HOST_ACCEPTED 五层分开，禁止使用“完成”模糊替代。
- 任何单writer、fence、side-effect未知均为HOLD，不借聊天窗口交接绕过。
- 后续更新须附commit、CI run、审核回执及有证据的真实状态。30分钟重复错误主动说明；1小时停止旧方案。
