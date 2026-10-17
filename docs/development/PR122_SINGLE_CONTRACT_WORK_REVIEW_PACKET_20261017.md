# PR122｜单份电子合同离线候选：Work独立集中复审包

状态：READY_FOR_INDEPENDENT_SOURCE_REVIEW_ONLY / PRODUCTION_HOLD

## 责任与版本

- 权威记录：PR122，ChatGPT原生隔离分支 `feature/chatgpt-native-customer-intake-20261016`。
- 审核人：Work（必须独立于本批开发，不能把本文件当作审核结论）。
- 准确源代码：本文件提交后的分支 HEAD，以GitHub实际返回的 commit/tree 为准；审核须按冻结准确 SHA 执行。
- 历史静态合同 draft.5：PR122 #6227191681 `PASS_WITH_SCOPE_LIMITS`；未变化内容只继承，不反复复审。
- 生产：`DRAFT_NOT_FOR_SIGNATURE`、`CONTRACT_SIGN=HOLD`、`PAYMENT=HOLD`、`PROCUREMENT=HOLD`、`DEVELOPMENT_START=HOLD`。
- 当前全部四个新功能模块均为离线候选，未接生产 Customer/Finance/签名服务。

## 完整受审范围

1. `scripts/single_contract_freeze.py`：输入结构、版本标识、两币种展示、50/50开发费、代理代购第三方首期费用、金额类型拒绝、嵌套凭据拒绝、不可变候选摘要。
2. `scripts/single_contract_journal.py`：SQLite BEGIN IMMEDIATE、请求幂等、跨项目/客户读写拒绝、追加约束、存储摘要读回重算、HOLD校验。
3. `scripts/single_contract_preview.py`：未签署纯文本预览、客户内容转义、快照SHA绑定、禁止把预览当法律合同。
4. `tests/test_single_contract_freeze.py`、`tests/test_single_contract_journal.py`、`tests/test_single_contract_preview.py`：正向/负向离线测试。
5. `docs/legal/templates/custom-development.md`、`docs/legal/templates/custom-sow.md`、`docs/legal/registry.json`、两份 `demos/legal` HTML、`tests/test_single_contract_consistency.py`：已审静态基线及变更影响关系。

## 特别要求Work在一次性审核中确认

- 付款计算可否在金额奇数分、异常大数、不同币种及折扣条件下安全拒绝；绝不可把CNY/USD文字当成真实汇率报价。
- 冻结快照的特征/资源/授权/法律字段是否完整：现有代码仅冻结部分需求、资源和付款，不包含所有法定合同条款。快照SHA不等于最终签署合同SHA。
- Boolean `signer_authority_verified` 等均来自调用者，不能自行构成可靠身份/真实批准；必须核查将来可信Provider调用与来源哈希的实际约束。
- 合同预览不是第1—28章完整法律文件；不能误用为可签署生成器。
- SQL只追加触发器不抵御高权限管理者直接修改数据库或日志；缺真正不可抵赖的签署、可信时间及送达证明。
- 业务真实性：支付回执、Finance防重复扣费、供应商代购真实凭证、退款、材料/权限/认证/SecretRef及客户中心身份尚无真实接线。
- 是否存在跨客户租户读取、请求幂等冲突、版本变化未失效、权限撤销后仍可读、磁盘故障、损坏记录及并发路径异常。
- Python 3.6兼容（英国环境）及国内真实客户中心环境分别验证；模拟与生产分开。

## 测试与证据边界

已提交测试源码，但在本批完成前未取得任何绑定准确HEAD的GitHub Hosted CI成功回执；严禁写TEST_PASS。Work须复查实际CI、原始日志及SHA/Tree。无真实执行证据则 `TEST_EXECUTION=NOT_AVAILABLE`；独审允许判定源码问题，但不能签出生产许可。

## 下一实现模块及明确缺口

- 与既有受保护Customer/Project/CRM确认用户身份和项目授权，服务器侧取得不可伪造的合同客户主体与有效签约人。
- 与现有Finance/PriceBook/Quote绑定冻结原始报价值、官方价有效期和已授权预算，并记录真实报价来源；不得重建平行账本。
- 将已审完整合同第1—28章及客户最终选择合成唯一完整文件，精确原文哈希、下载/送达、主动确认、身份及签署记录。
- Finance真实支付到账与采购幂等门禁、授权撤销、争议/退款、迁移/恢复、审计及多租户端到端联调。
- 生产相关缺口属下一阶段明确未交付能力，不得因离线源代码审查通过而认为生产授权或合同成立。

## 独审提交条件

本包只申请 **当前离线候选源码集中独立审核**。Work应一次性审查上述完整受影响调用链，按P0/P1/P2集中列缺陷、修复标准及范围限定，继承静态合同旧审结论；不得拆成逐文件多轮。

不得合并PR122、改动P2、部署客户中心、生成有效签署合同、付款或采购。
