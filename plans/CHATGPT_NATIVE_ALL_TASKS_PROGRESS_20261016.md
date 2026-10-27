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

## B.1 本次有界源码修复登记（2026-10-16）

- 涉及05：可信角色/租户；11/13：Finance审核职责隔离；22：离线HTTP输入边界。修改路径仅为 `community_saas_phase2` 服务与HTTP以及配套测试，不包括Work/Dots/OpenClaw/生产门禁。
- `FINANCE_EVIDENCE`、`REFUND`、`DEPLOYMENT` 等待审核状态禁止商家自己标记RESOLVED或CANCELLED，只有可信PLATFORM_OWNER在相同tenant作用域内可以结案；离线结案**不代表**实际Finance核销或真实退款。
- JSON解析时拒绝1e9999及负指数溢出为无限大的浮点数；普通有限浮点数保留为数字，再由业务入参验证。新增精确失败路径测试。
- 源码准确提交 `ae7249a4356f859942e6cbf1895795bdd6233184`，Tree `c7bb377042dfd850e8d1dd1c5f4c1f0bd934c8fe`，四个源码/测试文件+本推进表同一受保护提交。代码当前为 `SOURCE_PATCH_TESTED`，**独立审核仍PENDING**，上方PARTIAL节点不升总体PASS。
- 精确源码提交的GitHub Actions **8/8 SUCCESS**：Local Stack `38839021568`、Full Local Integration `38839021559`、Current Main Source `38839021553`、Control `38839021550`、Feature Compliance `38839021566`、Native Entry `38839021549`、Legal `38839021528`、PR122 Website `38839021460`。原始完整集成Job `116774564443` 显示真实新增的5个角色权限测试和3个JSON测试均 `ok`，342项Python回归通过，另有144项相关分组及Chromium验证。独立审核/真实Finance授权/生产验收均不可据CI认定PASS。
- 本次纯文档证据记录不重写以上已测试源码；若HEAD变化须重新核实精确文件及CI关系。PR122保持Draft，真实财务、DNS、东京退役继续HOLD。

## C. 历史ChatGPT相关控制面任务（责任逐PR确认）

| 锚点 | 已知事实 | 执行状态 | 下一动作 |
|---|---|---|---|
| Issue #19 | 三原生入口接力与回执闭环 | OPEN / 运行验收未整体证明 | ChatGPT原生入口与独立审核责任；PR50明确DOTS编码归属，PR17/P2由既有执行者管理，避免跨owner写入 |
| Issue #13 / PR #14–17 | Stage1持久队列与通知/受控运行 | OPEN / 尚未证明整体真实E2E | 复用现有Stage1、Python3.6与隔离门禁；不启动第二writer |
| PR #58 | Task4/5审核修复与ACK | OPEN DRAFT；Task5历史证据A2条件性可接受、最终PASS未证明（PR58#6197897838） | ChatGPT承担既定独审/裁定；A1/A3–A6及完整拓扑仍需独立证据；不重复313项已过CI，不接管英国生产writer |
| Issue #18 | 本地embedding | BLOCKED_BY_DEVELOPMENT_LOOP_ACCEPTANCE | 依赖尚未满足，不强行启动 |
| PR #122 | Stage5 25节点及ChatGPT代码增量 | OPEN DRAFT | 只补非外部范围，集中验收 |

## D. 进度原则

- CODE_MERGED / SOURCE_CANDIDATE / TEST_PASS / INDEPENDENT_AUDIT_PASS / HOST_ACCEPTED 五层分开，禁止使用“完成”模糊替代。
- 任何单writer、fence、side-effect未知均为HOLD，不借聊天窗口交接绕过。
- 后续更新须附commit、CI run、审核回执及有证据的真实状态。30分钟重复错误主动说明；1小时停止旧方案。

## E. 2026-10-16 新验证过的责任和验收

- PR73：准确源HEAD92e0f13，Issue62–71全部 CLOSED，仅离线合同SOURCE_COMPLETE（审核等级不得抬高为生产）；Hosted16/16 PASS。
- PR88：准确源HEAD7a1d62e，独立源码复审SOURCE_REPAIR_PASS_WITH_SCOPE_LIMITS，Hosted20/20 PASS，Issue78–87保持OPEN，剩余真正业务集成受目标授权/真实商户等依赖影响。
- PR50：原回执明确DOTS保留源码归属，不属于ChatGPT待编码队列；Work单独负责共享P2集成。
- PR58：CHATGPT_NATIVE_TASK5的A2只能按“历史保存记录+已审观察器程序保证”分层接受，目前A2_FINAL_PASS=NOT_YET_PROVEN，A1/A3–A6继续HOLD；无权据此激活生产。
