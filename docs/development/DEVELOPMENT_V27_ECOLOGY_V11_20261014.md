# 最新执行规则入口（Owner 2026-10-19）

所有现有及未来任务必须遵循[全项目开发、审核与交付规则](OWNER_DELIVERY_RULES_20261019.md)。Dots负责监督协调独审，ChatGPT负责开发及安装验收，Work负责Owner对接、架构及文档。尽可能按最小独立功能节点交付；审核通过后不另签安装许可；每轮10次失败/1小时升级Dots，累计30次/5小时升级Owner，任一先到。详细边界、继承和持久记录要求以该文件为准，与下列历史角色和执行流程冲突时采用新规则；业务架构与财务约束保留。现有P2不为本规则重新拆分。自动调度和门禁须实际实现后才可称生效。

---

# 玄钧云汇开发架构与开发顺序 V2.7（生态权益V1.1同步版）

同步日期：2026-10-14。第7.7节按Owner附件《贡献权益(2).txt》更新；运行状态仍以canonical ledger与执行回执为准。

玄钧云汇开发架构与开发顺序

统一整合版  V2.6

产品架构  数据与安全  商业财务  工程交付  运营治理

2026年10月9日

玄钧云汇定位为 AI 企业解决方案超市，通过模块市场、方案组合器、AI 产品经理和企业运营层，将客户需求转化为可购买、可部署、可计量、可持续复用的企业能力。

本架构用于后续开发、Dot 调度、OpenClaw 执行与工程验收。建设顺序以基础能力和依赖关系为准：先建立权威数据、安全与工程控制，再建设模块、模型和基础设施能力，随后打通报价、付款、交付和运营，最后扩展共创生态与空间交互。

架构要求与运行状态分开管理。本文件规定目标能力和工程边界；具体模块是否已开发、已验证或已部署，由 Canonical Project State 与真实证据记录，不以架构描述代替完成证明。

V2.6  定制开发与模块订阅衔接  标准模块封装  后台定价  GEO后续功能板块  V2.7  额度节约与开源复用（2026-10-09）

V2.7增补标记（2026年10月9日）：本文件中红色字体为2026-10-09当日新增或修改的内容；黑色字体为V2.6原有内容，未作改动。

今日修改清单：①新增9.10开源代码复用规范；②新增10.18 Codex与模型额度节约运行方案（含方向与关键限制前置门）；③新增12.8 V2.7落地顺序；④新增22.10 V2.7一致性验收；⑤在1.3、10.3、10.13和节点1.13各补充一段交叉引用；⑥封面增加V2.7标记与本说明。既有阶段0至8、68个既有节点、第6.6节推荐规则及价格与财务规则均未改动。

2026年10月14日生态权益更新：新增第7.7节ECV共建共享机制V1.1，关联更新7.5/7.6、节点2.15、21.3及22.5。总量、分池、交易门槛、粉丝活动、创始人同比释放、反作弊与上线验收均以该节为准；既有CP、推荐佣金与生产权限边界保持。


## 章节导航

1 总体定位与架构原则

2 权威数据与安全基础

3 产品体系与模块注册

4 模型路由与 AI 质量体系

5 基础设施控制与自动供给

6 商业定价与财务账本

7 共创贡献与声誉网络

8 客户发现与方案交付流程

9 工程开发与发布门禁

10 运营调度与恢复治理

11 方案知识与长期演进

12 开发主线与依赖总览

13 阶段0 既有资产盘点

14 阶段1 英国 AI 开发控制面

15 阶段2 玄钧云汇共享 Foundation

16 阶段3 客户产品层与统一 Marketplace

17 阶段4 玄钧内部真实使用

18 阶段5 公益商业支付解决方案

19 阶段6 公益 AI 内容引擎

20 阶段7 公益数字运营联合套件

21 阶段8 扩展生态与远期能力

22 全程验收与执行约束

23 GEO智能增长后续功能板块详细方案


## 1 总体定位与架构原则

### 1.1 产品定位与业务闭环

平台由 AI MODULE MARKETPLACE、SOLUTION COMPOSER、AI PRODUCT MANAGER 与 ENTERPRISE OPERATING LAYER 组成。客户可以直接浏览并选择模块，也可以向 AI 描述问题；系统补齐依赖、核验条件、组合方案、核算成本并报价，付款后完成供给和部署。

统一业务闭环：客户需求 → 发现与模块详情 → 依赖检查 → 购买前就绪检查 → 方案组合 → Commercial 与 Finance → 报价 → 订单与付款及钱包 → 基础设施、Provider 与 Connector → 部署 → 真实使用 → Usage、成本与财务 → 监控与审计 → Solution Graph → 产品化 → Marketplace → 下一位客户。

### 1.2 架构责任域与横向能力

Customer Experience 和 Product / Marketplace 分别承担客户入口与商品定义。模型、基础设施、商业财务、工程发布、运营调度和知识复用共同构成其余责任域；安全、身份、权限与审计贯穿全部责任域。

| 责任域 | 主要职责 | 权威对象或入口 |
| --- | --- | --- |
| 客户体验 | 发现、咨询、选择与客户及合作伙伴工作台 | 官网、AI Guide、Search、Dashboard |
| 产品与模块市场 | 统一商品、依赖、兼容性与产品来源 | Module / Connector / Package Registry |
| 模型与 AI 能力 | 按角色路由、质量评测与成本策略 | Model Router、Provider Registry、Rate Card |
| 基础设施控制 | 容量、供给、部署与完整生命周期 | Infrastructure Control Plane、Blueprint Registry |
| 商业与财务 | 成本、价格、钱包、收入与推荐结算 | Commercial / Finance、Usage、Ledger |
| 工程与发布 | 版本、测试、构建、安全和发布门禁 | Git、CI、Artifact、Release Gate |
| 运营与任务治理 | 节点调度、限额、恢复、监控与备份 | Canonical State、Task / Node Registry |
| 知识与共创生态 | 方案知识、产品化、贡献、声誉及凭证 | Solution Graph、Provenance、Contribution |


### 1.3 开发前的资产复用检查

任何新功能开发前，必须同时检查东京现有资产、国内运营服务器资产、英国 DEV 资产，以及 Canonical Project State、Git Repository、Module Registry、Connector Registry、Service Catalog、既有测试和既有文档。

检查结果分类为 EXISTING_AND_REUSABLE、PARTIALLY_AVAILABLE、NEEDS_INCREMENT 或 TRULY_MISSING。必须先搜索和读取真实证据，再判断复用、扩展或开发；不能因当前未看到而推断需要重建。

V2.7补充：资产复用检查之后，只有复杂且通用的功能才判断是否值得检索开源代码，简单功能直接开发；检索次数、候选数量、许可证与安全要求按第9.10节执行，已登记的评估结果不重复检索。

### 1.4 不可拆分的工程原则

统一原则：READ_BEFORE_ACT、SEARCH_BEFORE_NOT_FOUND、REUSE_BEFORE_BUILD、EXTEND_BEFORE_DUPLICATE、RESUME_BEFORE_RESTART、EVIDENCE_BEFORE_ASSUMPTION、CANONICAL_BEFORE_CHAT_MEMORY、WRITE_MEMORY_AFTER_TASK、FOUNDATION_BEFORE_VERTICAL、MODULE_BEFORE_PROJECT、AUTHORITY_BEFORE_MODEL_GUESS、EVENT_BEFORE_POLLING、LEDGER_BEFORE_BALANCE、TEST_BEFORE_RELEASE、VERSION_CONTROL_BEFORE_CHANGE、BUILD_ONCE_DEPLOY_MANY、SECRET_NEVER_IN_SOURCE、ROLLBACK_BEFORE_PRODUCTION、OBSERVABILITY_BEFORE_SCALE、AI_CHANGE_MUST_BE_EVALUATED、NEED_BEFORE_COMPLEXITY。

一个能力只有一个权威定义；Marketplace、Finance、Ledger、Registry 和 Task 系统必须复用统一基础，禁止按行业、产品来源或界面层再建平行系统。

### 1.5 与当前负载相匹配的实现

当前优先采用 systemd、container、reverse proxy、standard deployment package、modular monolith、async jobs 与 standard CI/CD。遵循 ARCHITECT_FOR_SCALE、IMPLEMENT_FOR_CURRENT_LOAD。

不为标准化提前引入 Kubernetes、Service Mesh、复杂多集群、大型微服务平台、自建 GitHub 替代品、复杂 Data Lake、Multi-region Active-Active、复杂 Service Discovery 或复杂 Internal Developer Portal。

### 1.6 业务承诺与自动化边界

每项销售能力必须区分目标设计、已开发、已测试、已获渠道权限、已真实验证和可正式交付。只有对应版本、地区、账号类型、权限与真实验证均有证据时，才可对客户标为可用；演示视频或规划文字不能代替生产完成证明。

玄钧提供企业软件、受控自动化和约定实施服务。销售说明必须明确工作范围、客户前置条件、责任方、验收指标、费用、运行限制、支持范围和退出方式。不承诺播放量、订单、收益或完全无人介入；自动化目标是在合法授权与既定策略范围内持续执行，人工验证、平台要求的确认和高风险例外保留检查点。

企业SaaS与交易项目保持部署、租户、凭证、预算和权限隔离。复用既有代码与设计资产不等于复用生产交易权限或占用已指定用途的服务器；云汇生产资源单独核价、审批和供给，不因本次文档扩展自动采购或部署。

客户数据仅按授权用于服务交付、经营分析和租户内优化。跨客户复用采用去标识化且获授权的结构、模板和统计证据；客户原始数据、商业秘密、API凭证和未授权内容不得进入公开案例、公共训练集或其他租户。

定制产品须在付款前确认背景知识产权、新增成果、客户专有配置和平台可复用模块的权利范围。共创身份、贡献值和推荐佣金不自动产生源码所有权、股权、现金兑付权或第三方数据使用权。

### 1.7 首批项目驱动的平台建设

正式实施路线为：资产复用检查→英国开发与交付控制面→首批业务所需最小Foundation→统一选品报价付款交付→内部真实使用→社区分账场景及公益视频业务验证→模块产品化→中国市场试点→按证据扩展全球市场与共创生态。平台总体设计保留扩展能力，实际建设由首批项目依赖驱动。

社区分账和公益视频分别落入第18章支付分账方案与第19章内容引擎。社区商业分账、公益款项和平台服务费须独立标识用途、主体和资金路径；社区分账不能因项目名称自动视为公益募捐。两个项目被选为首批验证场景，是否可正式交付仍由账号准入、合同、支付路径和真实验收决定。

首版Marketplace可以只提供这两套方案及已验证组成模块。可搭配范围通过依赖和兼容检查确定，核心必选项自动补齐；尚未实现的功能显示规划或不可用。业务可以从少量明确选项开始，不以模块数量作为上线条件。

优先建设可重复使用的任务、授权、成本、部署和证据基础。每项能力标记CORE_REQUIRED、CONDITIONAL_REQUIRED或DEFERRED，并记录首次需要它的业务动作；只实现对应最小范围。按第12.5节进入业务，不要求先做完所有远期底座，也不允许将安全、财务完整性和发布门禁降为可选。

## 2 权威数据与安全基础

### 2.1 权威边界与数据职责

| 组件 | 职责 |
| --- | --- |
| MODEL | 理解、表达和推理 |
| AUTHORITY | 提供真实业务事实 |
| CALCULATOR / FINANCE | 确定性计算与财务数字 |
| WORKFLOW | 执行受控动作 |
| LEDGER | 记录历史事实 |
| REGISTRY | 提供结构化权威配置 |


UNKNOWN 必须保留为 UNKNOWN，禁止转换为 0、SUPPORTED 或 READY。模型不得猜测业务真值、费用、账户事实或模块支持情况。GitHub 不替代 Canonical State、Task Registry 或 Secret Store，ChatGPT 也不替代 Canonical State。

### 2.2 环境隔离与凭证管理

开发环境至少分为 DEV、TEST、STAGING 与 PRODUCTION。禁止 DEV 直接使用生产数据库，禁止测试使用真实客户 Secret，禁止 Agent 为方便直接修改生产。

凭证继续复用 Secure Secrets Portal 和 SecretRef。API Key、Password、Private Key、OAuth Token、Customer Credential 与 Production .env 不得进入 Git。安全基础检查至少覆盖 SECRET_SCAN、DEPENDENCY_SCAN、SAST、LICENSE_SCAN 和 SBOM。

### 2.3 第三方代码隔离与零信任

建立XUANJUN_THIRD_PARTY_CODE_QUARANTINE。第三方源代码、依赖包、构建产物在通过Release Gate前必须与Production Repository、Production Secret、Customer Data、Finance、Wallet完全隔离。

至少分区：QUARANTINE_SOURCE_REPO / QUARANTINE_BUILD / SECURITY_ANALYSIS / SANDBOX_RUNTIME / APPROVED_ARTIFACT_REGISTRY。未经批准的源代码不得直接进入正式Repository或Production Runtime。

第三方代码进入流程：SOURCE INTAKE → SOURCE HASH → PROVENANCE/LICENCE CHECK → SECRET SCAN → SAST → DEPENDENCY SCAN → MALWARE/VIRUS SCAN → OBFUSCATION/DANGEROUS API REVIEW → SBOM → SANDBOX BUILD → DYNAMIC BEHAVIOR ANALYSIS → NETWORK/FILE/PERMISSION TEST → SECURITY AUDIT → SIGNED ARTIFACT → STAGING → CANARY → PRODUCTION。

供应链安全：锁定依赖版本、校验包Hash/签名、依赖来源Allowlist、恶意/投毒包检测、Typosquatting检查、SBOM、License Scan、可复现构建优先。

Sandbox默认：NO_PRODUCTION_SECRET、NO_CUSTOMER_RAW_DATA、NO_FINANCE_WRITE、NO_WALLET_WRITE、NO_CROSS_TENANT_ACCESS、NETWORK_EGRESS_DEFAULT_DENY、EPHEMERAL_RUNTIME、RESOURCE_LIMIT。

第三方Module默认零权限。只能通过Capability Broker申请显式Allowlist能力；不得直接读取API Key、Private Key、OAuth Token、支付凭证、客户资金账户或其他Tenant数据。

高危行为包括但不限于：破坏/删除数据、勒索/加密文件、远程控制、挖矿、凭证窃取、绕过授权、横向移动、提权、隐蔽持久化、恶意外联、资金/订单篡改、关闭审计、绕过Kill Switch。发现即BLOCKED并进入安全处置。

生产必须支持：SIGNED_RELEASE_ONLY / RUNTIME_AUDIT / MODULE_REVOCATION / EMERGENCY_KILL_SWITCH / RAPID_ROLLBACK。

第三方代码必须经过本节隔离审查后，才能进入第9章的统一发布链。来源审查与运行隔离属于准入前置条件，不能由普通功能测试代替。

### 2.4 资金安全的统一边界

Finance、Wallet 与 Ledger 的事实和写入权统一归属受控财务能力。支付传输、回调确认、账本完整性和资金权限集中在第6章定义；第三方产品只通过 Finance Capability API 使用这些能力。

### 2.5 多租户身份与统一审批

第一版采用 MULTI_TENANT，建立 Tenant、Organization、User、Identity、RBAC、Permission 与 Audit；Creator / Developer 身份关联这一共享模型。WORKFLOW_ENGINE、APPROVAL_WORKFLOW、EVENT SYSTEM 与 JOB / CHECKPOINT 统一服务采购、退款、发布、商户和内容审核。

### 2.6 接口与服务治理

轻量建设 SCHEMA_REGISTRY、API VERSION、EVENT SCHEMA、DATABASE MIGRATION 与 Contract Test，约束接口和数据演进。Service Catalog 连接 Service、Repository、Runtime、Server、Module、Connector、SecretRef、Monitoring、Backup 和 Version，引用原系统权威记录。

ADMIN_CONSOLE_FRAMEWORK 通过 Menu、Page、Action、Permission 与 Metric 接受模块注册，不按项目另建后台。详细建设分别见第15章节点2.5、2.6、2.12和2.13。

### 2.7 费用额度与实际资金流转边界

内部用量额度、会计账本与实际支付服务分别建模。CUSTOMER_WALLET记录客户合同项下预付费用和消费，不作为自由转账、储蓄或投资账户；不默认开放客户之间转账或任意提现。退款通过已核实支付路径和受控财务流程处理。

公益商业支付方案优先接入适用于经营主体、地区、商户类型和公益用途的支付服务商。必须登记PAYMENT_FLOW_PROFILE，列明收款主体、商户合同、资金持有人、分账主体、退款与拒付责任、公益款受益方、税务和准入依据。内部Finance不得因存在Wallet或Split接口而被视为具有资金托管、支付或募捐资格。

正式资金路径在节点5.2和5.3前核实；许可或合同条件未知时保留UNKNOWN，阻塞相应生产资金动作。公开内容与经营分析仅读取获准的汇总事实，不取得资金写权限。

## 3 产品体系与模块注册

### 3.1 注册中心与商品层级

产品层核心对象：MODULE_REGISTRY、CONNECTOR_REGISTRY、PACKAGE_REGISTRY、MODULE_TAXONOMY、CAPABILITY_GRAPH、CHANNEL_PROFILE_REGISTRY、COMPATIBILITY_MATRIX、DEPENDENCY_RESOLVER。

CAPABILITY_REGISTRY 记录统一能力；PRODUCT_TYPE、CREATOR_RELATION 与来源字段连接产品类别和创作者。Industry、Role、Goal、Channel、Workflow、Automation Level、Deployment、Security 与 Pricing Tags 支持分类和能力图谱。

| 层级 | 商品类型 | 作用 |
| --- | --- | --- |
| 1 | FOUNDATION | 共享基础能力 |
| 2 | GENERAL MODULE | 可复用通用模块 |
| 3 | INDUSTRY SOLUTION / PACKAGE | 行业知识、工作流和模块组合 |
| 4 | CUSTOM EXTENSION | 客户需求驱动的定制扩展 |


一个 Module 只有一个权威定义，允许多个索引引用，即 ONE MODULE MULTIPLE INDEX REFERENCES。行业方案采用通用模块加行业知识、行业 Workflow 与 Connector；不能为餐饮、酒店等行业复制多套 AI 客服。

### 3.2 同一模块的四个视图

四个视图共享同一个 MODULE_ID，不建立四套模块数据库。产品页面、就绪检查、报价和部署读取同一模块定义中的相应视图。

#### 3.2.1 产品视图

PRODUCT VIEW 面向客户说明价值、能力、场景、边界和版本。

字段：module_name、one_line_value、detailed_description、supported_use_cases、typical_workflows、supported_industries、supported_roles、supported_channels、included_features、excluded_features、known_limitations、configurable_items、Demo、status、version。

#### 3.2.2 依赖与就绪视图

DEPENDENCY / READINESS VIEW 字段：FOUNDATION_REQUIRED、MODULE_REQUIRED、OPTIONAL_DEPENDENCY、OPTIONAL_ADDON、required_connectors、required_permissions、required_documents、required_verifications、required_external_accounts、required_subscriptions、required_api_access、infrastructure_requirements、customer_system_requirements、eligibility_rules、region_and_license_constraints、third_party_dependencies。

#### 3.2.3 商业视图

COMMERCIAL VIEW 字段：pricing_model、setup_fee、subscription_fee、included_usage、usage_rate、implementation_fee、managed_service_fee、third_party_cost、infrastructure_cost、minimum_commitment、price_floor、list_price、promotion、currency、tax、cost_model、target_margin、effective_from、effective_to、price_version。

#### 3.2.4 工程视图

MODULE_MANIFEST 字段：module_id、version、capabilities、dependencies、permissions、API、events、configuration、SecretRef requirements、infrastructure、test_suite、health_check、rollback、deployment、owner、repository、release_version。

### 3.3 产品来源与创作者身份

所有产品必须记录 PRODUCT_ORIGIN 与 PRODUCT_PROVENANCE，并复用现有产品 Registry。

| 来源 | 定义 |
| --- | --- |
| XUANJUN_ORIGINAL | 玄钧自主提出，由玄钧 AI 和工程体系开发 |
| CUSTOMER_AI_CO_CREATED | 客户提出思路或需求，玄钧 AI 完成澄清、复用判断、开发、测试与产品化 |
| THIRD_PARTY_DEVELOPER | 外部开发者提交，经安全审查、隔离验证和 Release Gate 后上架 |


每个产品至少关联 PRODUCT_ID、VERSION、PRODUCT_ORIGIN、CREATOR_ID(S)、PROVENANCE_EVENT、SECURITY_STATUS、PRICE、REVENUE_ATTRIBUTION 与 CONTRIBUTION_ATTRIBUTION。

平台自有 AI 开发者身份为 XUANJUN_AI_DEVELOPER。这是平台拥有、可审计和可追溯的 AI 开发者角色，不是虚构自然人。自主研发与 AI 辅助客户研发的开发贡献，均按统一 Contribution 与 Reputation 规则计入该角色。

客户共创角色可包括 IDEA_ORIGINATOR、PRODUCT_CO_CREATOR、AI_DEVELOPER、SECURITY_CONTRIBUTOR 与 MAINTAINER。产品来源、收入归属和贡献归属须分别记录。

### 3.4 小工具产品与设备授权

MICRO_TOOL 即 1 元起小工具，是 Marketplace 的本地低价产品层级，复用 Registry、Version、Security、Finance、Contribution、Reputation、Provenance、Release、Update 与 Revocation。差异在价格、复杂度、交付方式和授权范围，不设独立商城或账本。

1元起小工具默认授权模型：MICRO_TOOL_LICENSE_SCOPE=ONE_DEVICE；LIFETIME_FOR_LICENSED_DEVICE=YES；UNLIMITED_SEATS=NO。

公司/个人购买一份，仅允许一台授权设备使用；100台电脑需要100份License。更换电脑默认视为新设备，需要重新购买。

用户侧规则可以表述为“绑定电脑MAC/设备”；工程实现不得只信任单一MAC地址，因为MAC可被修改、网卡可变化。

正式实现采用DEVICE_FINGERPRINT：以MAC作为一个因子，并结合OS Device ID / Machine UUID / TPM或等价硬件标识（按平台可用性）生成规范化设备指纹。

服务端存储设备指纹的不可逆/最小化表示；License由服务端签名并绑定PRODUCT_ID + VERSION/POLICY + CUSTOMER_ID + DEVICE_FINGERPRINT + LICENSE_ID。

首次激活必须通过服务端授权；离线使用的小工具可下发签名License Token，由本地验证签名与设备指纹，不在客户端保存可伪造余额、权限或明文Secret。

授权验证失败、设备指纹明显变化、License被撤销或签名不合法时拒绝激活；硬件更换的默认商业规则仍为重新购买，不自动迁移License。

MICRO_TOOL_START_PRICE=1 RMB，表示最低起售价而非所有工具固定1元。适用条件为一次开发成型、在客户设备本地执行、无持续模型/API调用成本及无未覆盖的持续服务成本。销售页明确功能、设备和版本政策；不承诺永久免费云服务或永久兼容所有未来操作系统。

暂时不支持小工具云端业务调用：MICRO_TOOL_CLOUD_EXECUTION=DISABLED。服务端授权激活、签名License、下载更新与撤销属于交付控制服务，分别核价，不表示允许云端业务计算。需要云端模型或持续API能力的需求进入已有标准Module产品流程，不以1元终身本地工具名义出售。

本地工具若存在第三方许可、分发、支付、激活、更新、设备支持或约定维护成本，均计入真实成本后定价。开发为一次性投入也需明确回收或有限摊销策略，不能把一次开发误认为总成本为0。存在本地按量或其他持续成本时须事先披露并确定买断覆盖范围；不能核算或可能转为云端业务调用时，第一版本不作为Micro Tool上架。

最低售价为MAX(1元，适用返佣政策下的Price Floor)。默认不含人工定制实施；选购实施时服务费单列，按第6.7节核算。License规则、设备绑定和更换设备政策沿用本节，资金和授权校验不因低价而简化。

### 3.5 渠道能力与规则注册

扩展既有CHANNEL_PROFILE_REGISTRY和CONNECTOR_REGISTRY，建立CHANNEL_REQUIREMENT_PROFILE与CHANNEL_POLICY_VERSION，不新增平行渠道数据库。发布、评论回复、私信、广告、数据读取分别登记能力和授权，任一能力获准不能推导其他能力可用。

配置字段：channel_id、region、legal_entity_type、account_type、app_type、app_status、permission_scope、review_status、oauth_status、verification_requirement、allowed_use_case、content_type、media_spec、quota_policy、publish_mode、user_confirmation_required、commercial_disclosure、synthetic_media_disclosure、copyright_rule、link_rule、data_read_scope、metric_coverage、data_retention、third_party_cost、policy_source_url、policy_checked_at、effective_from、review_due_at、rule_version和canary_evidence_id。

发布模式明确为DIRECT_PUBLISH、CONFIRM_THEN_PUBLISH或EXPORT_FOR_MANUAL_PUBLISH。第三方排程服务只在其已获准的渠道、账号和功能范围内使用；不能以浏览器模拟、共享账号或代理IP绕过平台审核、权限或发布限制。

#### 3.5.1 首批渠道规则基线

以下为2026年10月7日公开资料核实的设计基线，引用见第22.7节。具体客户与项目账号是否获准，仍需登录对应控制台核实并完成真实Canary。配额、格式、权限名和政策变化由版本化配置更新，不在业务代码写死。

#### TikTok

Direct Post未审核客户端受私密发布等限制；工具用途需面向真实创作者，官方不接受仅供自己或团队管理账号的内部上传工具。展示应用审核、用户预览与确认、隐私选择、商业内容披露和当前发布限额；默认不承诺无人值守批量公开发布。[1]

#### YouTube

视频上传需要对应OAuth授权；特定未审核API项目上传受私密限制，公开发布须满足项目审核条件。内容需遵守原创、版权和重复批量内容规则；商业披露和合成内容标记按适用规则填写。上传权限与Analytics读取授权分开检查。[2][3][4]

#### Instagram与Facebook

按选用的登录方案与API版本核对账号类型、发布对象、权限及审核。Meta维护的Instagram文档说明专业账号场景；不能把个人账号当作同等支持，也不混用不同登录方案的前置条件。Facebook页面能力独立登记。部分官方页面公开读取受限，具体scope、配额和审核要求未核实前保持UNKNOWN。[5]

#### LinkedIn

Community Management API有应用准入及分级审核要求，官方列出注册法律实体、商业用途、组织验证及演示材料条件。个人与组织发布及数据读取分别核实权限，不能由普通登录能力推导Page管理能力。[6]

#### 抖音

发布能力须申请并获准且经用户授权；官方发布规范包含正式应用等条件。记录实际控制台权限、应用版本、内容类型、商业及AI内容标记要求；上传成功不能等同公开发布成功，需跟踪发布结果与审核。[7][8]

#### 哔哩哔哩

官方开放平台提供稿件相关能力，并要求身份资料及审核；具体应用的准入材料、发布与编辑范围、投稿限制和数据读取能力逐项核实。现阶段不承诺所有账号都可API投稿。[9]

#### 小红书

本次公开资料未核实到可用于本项目的通用笔记自动发布授权。商城开放接口不能当作笔记发布接口。先提供内容导出与待发布任务，API发布及经营数据读取标为UNKNOWN，获得平台可用授权与Canary证据后再启用。[10]

#### Telegram与企业微信

用于授权消息、客户沟通、私域跟进与CRM，不与公域视频发布能力混为一类。Telegram检查Bot及目标会话/频道权限，不承诺Bot API取得完整平台经营报表；企业微信按应用类型、可见范围、客户联系及消息接口分别核实。两者均不推导任意主动私信或无限群发能力。[11][12]

#### 3.5.2 规则更新与失效处理

规则以官方资料和控制台授权证据为来源。出现政策更新、scope变化、权限撤销、Token失效或Canary失败时，重新计算受影响模块和方案就绪状态，暂停对应动作并保留任务，不删除客户资产。定期检查仅唤醒必要采集或校验任务，不使用LLM无意义轮询。

渠道规则和产品规则存在冲突时执行更严格的适用约束。人工确认尚未完成则保存checkpoint；不自动改成浏览器绕过方式。平台元数据请求、有限退避和状态API查询不等同LLM轮询，但必须遵守配额和成本上限。

### 3.6 Connector接入与授权生命周期

每个Connector记录供应商、API版本、支持动作、地区与账号类型、申请材料、权限范围、授权主体、SecretRef、配额、费用、Token有效期、撤销入口、依赖和验证证据。用户登录、发布、读数和资金权限分别登记，不由其中一个权限推导其他能力。

生命周期为：需求与既有能力检查→官方接口核实→申请或授权→凭证安全接入→沙箱与契约测试→有限真实Canary→按已获权限启用→健康及到期管理→续期或撤销。人脸、验证码、平台审核和必须由用户确认的动作生成前置任务与checkpoint；其他独立路径可继续。

Token刷新由受控服务执行，失败或撤销立即暂停依赖动作；保留队列和结果，不重复提交已成功发布、采购或付款。重试采用退避、配额和预算限制。供应商接口变化先做兼容测试和版本更新；未知权限保持UNKNOWN，客户可以重新确认导出、草稿或其他允许的交付模式。

验收包括最小权限、跨租户拒绝、失效与撤销停用、重复回调去重、超时查证、费用计量、敏感日志检查及恢复。API接入是独立可注册能力，复用统一Connector和Task系统；不为每个渠道复制一套接入框架。

### 3.8 免费主体框架与功能板块归属

主体框架免费，包括账号与租户入口、模块目录、基础导航、购买及账单查看、权限入口和必要的自助管理外壳。免费不代表赠送付费业务功能、无限模型调用、服务器、行情、部署或人工服务。没有启用功能模块时，框架不执行对应业务任务；安全与授权基础不能因免费而关闭。

除主体框架外，每个业务功能必须有板块归属。板块是面向客户的分类与组合入口，Module是可版本化能力，Feature是具体功能，Package是商业套餐；四者分开建模，复用原Registry，不新建平行商城。

一个功能允许属于多个板块，使用唯一FEATURE_ID和MODULE_ID，通过多对多分类引用展示。primary_owner负责维护，sector_ids用于多归属；技术依赖关系与商业分类关系分别记录。分类变化不改变客户已有授权。

同一客户从不同板块取得同一功能时，报价检查已有权益、套餐覆盖与实例范围。相同权益不重复出售；同一执行事件只计量一次。不同实例或额外容量只有事先明确商业范围时才能另收费，不能因多归属重复扣费。

### 3.9 金融交易自动化板块

金融板块是玄钧云汇的新增专业板块，提供客户自主配置策略、风控、交易授权、部署与运行管理。原有币安直接跟单和并联带单业务不变，策略、账户与收费保持独立，不把自主模式自动接入统一策略。当前为PLANNED_NOT_LAUNCHED，本文件不是上线证明。

扩展目标包括加密资产交易所、证券及期货市场。实际通常通过券商、期货经纪商或交易所获授权接口接入；不宣传可以直接接入任意证券交易所。逐一登记市场、地区、提供方、账号类型、品种、订单类型、行情许可、交易权限、费率、限流、测试与生产状态。黄金须明确具体产品，如黄金期货，而非视为单一接口。

金融功能包括账户连接、行情、策略配置、回测及模拟、风控、执行、订单与持仓核对、通知、审计和部署。按客户实际需求逐步实现，先用现有Binance资产形成模板，再按需求和权限证据扩展提供方；不因架构列举就开发所有市场。

AI理解客户意图并生成结构化策略；客户确认版本后，确定性执行器和风控执行。提供只分析提醒、逐单确认、预授权规则自动执行三种授权级别。每个账户与规则有独立权限、暂停和撤销控制；平台人员不得擅改客户策略或开平仓。凭据通过SecretRef管理，默认不申请提现或资金转移权限。

执行必须处理订单幂等、提交超时后的状态查证、部分成交、撤单竞争、重启恢复、持仓对账、时区交易日历及合约到期。不能因HTTP超时盲目重新下单，也不能将模型输出直接视为可信订单。共享环境保持租户隔离与容量限额；独立部署明确客户与平台运维权限。

原有客服保留直接跟单、带单合作、自主工具三条路径，按客户意图自然澄清，已知信息不重复追问。自主板块未上线或未支持对应市场时只登记需求，不提供虚构入口或收取不可交付服务费用；原公开渠道披露边界保持不变。

### 3.10 从需求阶段建立标准模块封装

客户定制与玄钧自研均须在需求阶段形成模块产品定义。公共核心、租户配置、客户专属扩展分开；一个客户一套配置，不默认复制一套账户、财务、后台或程序。

模块定义与既有四视图共用MODULE_ID，包含生命周期处理、配置Schema、套餐功能、权限、额度、计量事件、依赖、价格引用、文档及演示。Module Version、Plan Version、Price Version与Contract Entitlement Version分别管理。

启用、配置、升级、停用、恢复、导出与必要清理具有受控接口；开通幂等，授权在服务端验证，功能开关不能代替付费权益。标准核心升级保留客户配置，专属扩展独立兼容测试。

模块目录从第一版存在；目录可见性支持INTERNAL、CUSTOMER_PRIVATE、INVITE_BETA、PUBLIC_MARKET。客户专属模块可进入“我的模块”和统一订阅，不因纳入管理就向其他客户公开。

公共销售须具有合同许可的复用权、租户隔离、安全测试、价格、文档与真实交付证据。自研模块不需要虚构客户开发订单，其研发投入独立归集，后续客户只支付所购买服务。

模块初期采用模块化单体和按需后台任务，专用部署按真实隔离或容量需求配置，不提前建设复杂插件平台。

## 4 模型路由与 AI 质量体系

### 4.1 按业务角色调用模型

统一采用 PROVIDER_NEUTRAL_MODEL_ROUTER。业务代码调用角色，而不是写死具体模型名。角色示例包括 CUSTOMER_BRAIN、PRODUCT_MANAGER、CONTENT_DIRECTOR、MULTIMODAL_ANALYSIS、LOW_COST_SUMMARY 与 CODE_AUDITOR。

路由决策条件：QUALITY、SAFETY、BUSINESS CORRECTNESS、LATENCY、CONTEXT、MULTIMODAL、REGION、DATA POLICY、CUSTOMER PLAN、PROVIDER HEALTH、CURRENT PRICE、BUDGET、RATE LIMIT、AVAILABILITY。

Router 确定 Provider、Model、Fallback 与 Cost Policy。供应商与权威价目分别进入 AI_PROVIDER_REGISTRY、MODEL_PROVIDER_RATE_CARD。质量、安全和业务正确性优先，随后优化成本。

### 4.2 AI 变化的评测与版本化

建立 XUANJUN_AI_EVAL_FOUNDATION。AI 变化必须经过评测，结果用于工程发布门禁。

评测维度：Semantic Accuracy、Business Correctness、Context Retention、Tool Selection、Hallucination、Authority Compliance、Sensitive Data、Naturalness、Latency、Cost。

版本化对象：PROMPT_VERSION、MODEL_ROUTING_VERSION、AGENT_INSTRUCTION_VERSION、TOOL_POLICY_VERSION、GUARD_VERSION、EVAL_SET_VERSION。

模型负责理解和解释；Authority 提供事实，Finance 与 Calculator 提供确定性数字，Workflow 执行动作。报价、余额和收入确认不由自由文本推理直接决定。

## 5 基础设施控制与自动供给

### 5.1 控制平面的管理范围

统一建设 XUANJUN INFRASTRUCTURE CONTROL PLANE，管理内部服务器、Trading Production、DEV / BUILD / TEST、Domestic Operations、Common Brain、Database、Content、GPU、Backup、Shared SaaS、Customer Dedicated 与 Customer Managed Infrastructure。

### 5.2 完整生命周期与支出前置条件

生命周期顺序：DISCOVER → SIZE → REUSE EXISTING CAPACITY → COMPARE → QUOTE → APPROVAL → PURCHASE → PROVISION → BOOTSTRAP → DEPLOY → VERIFY → REGISTER → MONITOR → BACKUP → OPERATE → RENEW → SCALE → MIGRATE → RETIRE。

控制原则：REUSE_EXISTING_CAPACITY_BEFORE_BUY、CUSTOMER_PAYMENT_BEFORE_PURCHASE、AI_PLAN_BEFORE_SPEND、APPROVAL_BEFORE_HIGH_RISK_WRITE、BLUEPRINT_OVER_MANUAL_SETUP、NO_MANUAL_EXPIRY_MEMORY。

先复用现有容量，再比较和报价；客户付款先于对应采购，AI 计划先于支出，高风险写入先经批准。到期、续费与容量状态由系统管理，不依赖人工记忆。

### 5.3 服务器蓝图与标准部署

建立 SERVER_BLUEPRINT_REGISTRY。

蓝图类型：XUANJUN_DEV_BUILD_TEST_V1、XUANJUN_TRADING_PRODUCTION_V1、XUANJUN_DOMESTIC_OPERATIONS_V1、XUANJUN_CONTENT_PRODUCTION_V1、XUANJUN_CUSTOMER_AI_STANDARD_V1、XUANJUN_CUSTOMER_DEDICATED_V1。

Blueprint 定义项：OS、Runtime、CPU / Memory、Disk、System User、Directory、Python、Node、Container、Firewall、SSH、systemd、Monitoring、Backup、Health、TLS、Application Stack、Security Baseline、SecretRef、Deployment。

自动化优先使用 Cloud API、Terraform / OpenTofu、cloud-init、Ansible / Configuration Management 与 Deployment Package。正常服务器应实现 NO_ENGINEER_MANUAL_SSH_REQUIRED，人工主要处理 Approval、HUMAN_VERIFICATION、Exception 与 High Risk。

### 5.4 英国开发环境的参考角色

英国 DEV 服务器作为 REFERENCE_SERVER、AUTOMATED_PROVISIONING_CANARY、STANDARDIZED_AI_DEVELOPMENT_ENVIRONMENT 与 DEV_BUILD_TEST_STAGING_CONTROL_NODE，验证标准化供给和开发环境后再推广部署。

### 5.5 自动采购的授权与预算政策

采购统一引用SPEND_POLICY，字段至少为owner、tenant、purpose、supplier_account、allowed_providers、allowed_regions、allowed_resource_types、allowed_specs、purchase_limit、monthly_commitment_limit、currency、expiry、renewal_policy、approver与policy_version。客户项目使用已确认报价和已核实收款形成额度，内部项目使用Owner明确批准预算；订阅、续费与按量费用计入未来承诺成本。

在有效长期授权、明确预算及供应商权限范围内，报价、查库存、创建资源、初始化、部署和健康验证自动执行，无需逐条Shell命令或每次采购重复确认。超范围、预算不足、价格变化超过政策容差、不可逆数据删除或需要人工验证时，提交具体资源、价格、影响和回退方案后暂停依赖动作。禁止用后续客户预期收入作为当前采购资金。

阿里云等供应商通过受控适配器接入，生产执行使用最小RAM权限及SecretRef，不给模型直接读取云账户密钥。采购前登记QUOTE_ID、RESERVATION_ID和唯一PURCHASE_INTENT_ID；供应商支持幂等键时固定使用同一键。调用超时先查询供应商订单与资源，状态未知不得重购。

资源创建后登记云订单、实例ID、用途、租户、蓝图、实际费用和续费时间，进行启动、权限、TLS、健康、备份及恢复检查。失败时依实际状态清理仅本次产生且确认可释放的临时资源；预付费退款不假定可得。支持闲置告警、按批准策略停机、续费提醒和月度账单对账。

英国服务器首先承载开发与交付控制面。客户生产负载按租户和负载选择独立运行环境；不把DEV、STAGING和客户PRODUCTION混在同一数据库或凭证域。英国地区、实例库存、报价和供应商资格在采购时核实，本文件不预购资源，也不把文档中的4C16G参考规格当作实际已存在资产。

## 6 商业定价与财务账本

### 6.1 统一引擎与职责分工

共享引擎：COMMERCIAL_ENGINE、FINANCE_ENGINE、CUSTOMER_WALLET、USAGE_METER、USAGE_RATING_ENGINE、PROCUREMENT_ENGINE、PROFITABILITY_ENGINE、REVENUE_RECOGNITION_ENGINE、REFERRAL_ENGINE。

所有模块复用统一收费系统，不得各自实现钱包、计费或账本。Commercial 决定价格策略，Finance 提供真实成本与最低安全价格，Calculator 执行确定性计算；MODEL 只理解和解释，禁止 LLM_FREEFORM_PRICING。

Commercial 负责：Price Book、Package Pricing、Contract Pricing、Promotion、Quote Strategy、Market Positioning。

Finance 负责：成本真值、Landed Cost、FX、Tax、Payment Cost、Margin、Wallet、Billing、Invoice、Payment、Reconciliation、Refund、Chargeback、Revenue Recognition、Referral Settlement、Profitability。

### 6.2 成本核算与价格形成

模块正式销售前必须完成直接成本核算。

成本项目：MODEL_COST、API_COST、SERVER_COST、GPU_COST、DATABASE_COST、STORAGE_COST、BANDWIDTH_COST、CONNECTOR_COST、THIRD_PARTY_LICENSE_COST、PAYMENT_PROCESSING_COST、FX_COST、TAX、IMPLEMENTATION_COST、MAINTENANCE_COST、SUPPORT_COST、MONITORING_COST、BACKUP_COST、OPERATION_COST、EXPECTED_FAILURE_COST、RISK_RESERVE、OTHER_DIRECT_COST。

价格形成顺序：FULL_DIRECT_COST → MINIMUM_SAFE_MARGIN → PRICE_FLOOR；再结合 MARKET_REFERENCE_PRICE、COMPETITOR_PRICE、CUSTOMER_VALUE、PRODUCT_MATURITY、CUSTOMER_LTV 与 STRATEGIC_PRIORITY，形成 LIST_PRICE、PROMOTIONAL_PRICE、PARTNER_PRICE 与 CUSTOM_QUOTE。

### 6.3 采购归属与费用披露

| 模式 | 资源归属 |
| --- | --- |
| CUSTOMER_MANAGED / BYOK / BYOI | 客户提供 API、Cloud、Domain、Subscription 和 Provider Account |
| XUANJUN_MANAGED | 玄钧采购或托管 API、Server、Storage、Subscription 及其他 Provider |
| HYBRID | 客户与玄钧分别提供部分资源 |


每项成本必须明确 OWNER、BILLING_PARTY 与 PROCUREMENT_MODE。

报价必须披露：FIRST_PAYMENT、ONE_TIME_IMPLEMENTATION、CUSTOM_DEVELOPMENT、CONNECTOR_FEE、MONTHLY_FIXED_COST、ESTIMATED_USAGE_COST、SERVER_COST、STORAGE、BANDWIDTH、MODEL、THIRD_PARTY_SUBSCRIPTION、CHANNEL_COST、MANAGED_SERVICE、PAYMENT_COST、FX、TAX、INITIAL_WALLET_TOPUP、ESTIMATED_MONTHLY_TOTAL。

报价须区分一次性、固定、Usage 与第三方费用，并明确首次付款、初始钱包充值及预计每月合计，禁止隐藏成本。

### 6.4 预付钱包与收入确认

普通客户采用 PREPAID_ONLY 与 NO_NEGATIVE_BALANCE。执行顺序为 ESTIMATE_MAX_COST → RESERVE → EXECUTE → SETTLE_ACTUAL_COST → RELEASE_UNUSED_RESERVE。

Wallet Ledger 事件：TOPUP、RESERVE、CONSUMPTION、SETTLEMENT、RELEASE、REFUND、BONUS、PROMOTION、ADJUSTMENT、CHARGEBACK。

Wallet Ledger 不可变。TOPUP != REVENUE，UNUSED_BALANCE != REVENUE，RESERVE != REVENUE。充值、未消费余额和冻结不构成收入；只有实际消费并完成 Revenue Recognition 才进入收入。

### 6.5 支付传输与资金账本完整性

所有支付、钱包、账单、提现、退款、分账等关键数据必须采用安全传输，禁止明文或仅依赖前端状态。公网链路使用现代TLS；服务间在适用场景采用mTLS或等效服务身份认证。

关键请求/回调必须支持：REQUEST_SIGNATURE / WEBHOOK_SIGNATURE / TIMESTAMP / NONCE / ANTI_REPLAY / IDEMPOTENCY_KEY / CANONICAL_PAYLOAD / SERVER-SIDE_RECONCILIATION。

支付结果不得以浏览器/客户端“支付成功”页面作为资金事实；必须由服务端通过支付Provider回调签名、主动查询或收款侧权威证据完成确认和对账。

客户资金账户采用SERVER_AUTHORITATIVE_LEDGER。客户端只能提交业务命令，绝不能提交或修改“最终余额”。

禁止把balance作为客户可写字段；余额由不可变双分录/多分录Ledger实时或准实时计算/投影。所有充值、消费、冻结、释放、退款、提现、调整必须形成Ledger Entry。

任何余额修正禁止直接UPDATE历史分录或balance；只能通过ADJUSTMENT / REVERSAL / COMPENSATING_ENTRY产生新的审计事实。

Database权限必须分离：Customer/API role无Ledger写权限；业务服务仅通过受控Ledger Service写入；高风险人工调整要求强身份认证、完整审计，并按金额/风险触发Approval。

敏感资金数据：ENCRYPTION_IN_TRANSIT + ENCRYPTION_AT_REST；高敏字段支持Field-level Encryption；密钥由SecretRef/KMS/HSM类能力托管并轮换，禁止进入源代码和日志。

账本需要Tamper-evident证据：ENTRY_ID / EVENT_ID / IDEMPOTENCY_KEY / CREATED_AT / ACTOR / SOURCE / PREV_HASH或等价完整性证据 / AUDIT_TRAIL。

第三方产品不得直接修改Finance/Wallet/Ledger；如需收费、退款、支付等能力，只能调用受权限控制的玄钧Finance Capability API。

### 6.6 一级推荐关系与永久返佣

正式规则：REFERRAL_COMMISSION_RATE=30%；REFERRAL_DEPTH=1；REFERRAL_RELATION_DURATION=NO_FIXED_EXPIRY。永久指已确认客户与一级推荐人的关系不设固定到期日：客户以后符合条件的实际消费、续费、增购及复购持续纳入计佣，不设6个月、12个月或首次订单截断；客户暂停消费时不产生新佣金，恢复后沿用原绑定。

推荐人只负责介绍客户，不承担实施、培训、维护或售后。客户交付由玄钧或另行签约的实施服务方承担，其成本先进入直接成本；推荐佣金不替代实施报酬。A推荐B、B推荐C时，A只获得B的合格消费佣金，C的佣金只归B；不产生二级、团队、招募或下线奖励。

永久关系覆盖同一canonical_customer_id及已验证合并身份，不自动扩展到客户的所有关联公司、员工或下属企业。更换手机号、账号迁移、续费或更换销售人员不得重置归属；注销后重新注册须通过合法最小化身份核对判断是否同一客户。不得无限保留不必要个人资料。

建立REFERRAL_ATTRIBUTION_LEDGER、REFERRAL_POLICY_VERSION和CUSTOMER_REFERRER_BINDING。政策版本、30%比例和无固定期限随绑定冻结；不得以更新政策、产品迁移或公司内部重组单方降低既有合格关系权益。法律限制、经证实的欺诈、法院命令或双方书面变更采用有理由、有证据、可申诉的例外流程；正常已结算权益不得追溯取消。经营终止或主体承继的处理必须写入伙伴合同，永久不代表固定收益或无限支付保证。

#### 6.6.1 可分成毛利润的确定性公式

计量范围为同一已绑定客户、同一结算币种下的合格平台产品与服务，从绑定生效日起累计。R_t为截至t已实际交付或消费、完成收入确认且满足收款条件的合格不含销售税净收入；扣除折扣、退款、贷项与已确认拒付。充值、押金、未消费预付款、代收公益款和客户支付流水不进入R_t。

C_t为同一收入范围内已最终核实的累计直接成本：模型/API、基础设施按实际归属分配、存储带宽、连接器与第三方许可、支付手续费、实际汇兑成本、实施人工或承包服务、可归属支持维护及已约定摊销等。同一成本只扣一次。销售税已从收入剔除时不得再扣；一般管理费、股东分配、所得税、获客广告费及本次推荐佣金不进入计佣直接成本。预估成本、未发生风险准备和任意内部加价不能冒充已结算实际成本。

累计毛利润G_t = R_t − C_t，对应ELIGIBLE_REFERRAL_GROSS_PROFIT累计口径。累计应计佣金E_t = 30% × MAX(G_t, 0)。当期佣金变动ΔE_t = E_t − E_(t−1)。正值为新增佣金，负值为成本补记、退款或拒付引起的COMMISSION_REVERSAL。采用累计差额，禁止逐订单只取正毛利却忽略同一范围的亏损，禁止退款后又从充值或新账号重复计佣。

例：上一期累计净收入1,000元、直接成本400元，则E=180元；下一期发生净退款200元且成本未返还，累计毛利降为400元，E=120元，本期ΔE=−60元。冲回用新增分录记录，不改历史账；已付部分先按合同抵扣后续可支付佣金，不直接扣客户钱包或外部账户；异常追偿进入财务流程。

收入确认、收款、成本最终核实和归因均完成后才计提。已确认收入但未收款、第三方成本未知或存在未决争议的金额显示待确认，不估算为可支付。各币种分别核算；转换采用Finance已批准并留存的实际汇率与时间点。金额用最小货币单位或定点小数，累计目标按币种精度四舍五入后求差，避免逐笔舍入损失或重复获利。

#### 6.6.2 推荐绑定与归因规则

上线默认建议：推荐链接或邀请码形成90天有效候选归因；90天是首次绑定窗口，不是永久返佣期限。客户首次合格付费前展示并确认推荐人，最早被客户确认的有效归因胜出；cookie、UTM或最后一次广告点击不能覆盖已确认关系。正式绑定在首次合格消费前完成，跨设备靠登录身份和邀请码核验，不靠设备指纹替代客户身份。

既有付费客户默认不允许追溯绑定；尚未付费且无既有有效归属的客户可以确认推荐人。导入的历史关系须双向证据和审批，不能批量强占存量客户。推荐人可以同时是客户，只有他自己的实际合格消费归其上一级，自己的推荐佣金收入不再向上计佣。禁止自荐、循环关系、伪造账号、刷单退款套利和未披露的关联交易。

普通取消合作不自动抹除已确认合格客户关系；限制新增推广与限制支付分别处理。收款资料、身份税务或风控未完成时可保留应计权益但暂停支付，完成后按账本补付。变更绑定必须核对客户意愿、原关系证据和合同，记录生效日与审批，不追溯重分已结算历史。

#### 6.6.3 结算与付款规则

云汇初版建议按Asia/Shanghai月度结算：自然月归集；次月5日生成可结算明细，客户或第三方事实迟到的条目保持待确认；至少保留7天对账申诉窗口。通过退款与拒付风险期限、收款和成本最终核实后进入可支付，次月15日作为首个计划付款批次；未到风险释放日则顺延。可支付累计达到100元人民币或事先公布的等值门槛再付款，小额持续累计，无固定失效期限。此为云汇新方案，不改变其他项目原有周结规则。

退款/拒付风险释放期限由产品、支付服务商及合同规则配置risk_release_at，不把统一30天假定为所有渠道安全期。提现/付款方式、手续费承担、税务凭证与地区支持上线前公布；云汇不默认沿用交易项目的单一收款渠道。推荐佣金账户与客户消费钱包分离，显示账本投影，不允许推荐人直接改账或自行确认付款。

### 6.7 实施成本与复杂度核算

IMPLEMENTATION_SERVICE_FEE记为S，表示客户单独确认的、不含销售税且按交付里程碑确认的实施服务净收入。订阅费、客户充值、商品流水和硬件/API代采购款不得混入S。实施成本默认预算C_impl_est = S × 50%，是报价预算和实施资源额度，不是客户折扣，也不是推荐人承担成本。

复杂度先依据工时、工程和测试单价、现有连接器复用、数据迁移、系统数量、地区语言、权限审核、培训及验收要求形成工作量估算。标准项目按50%预算；简单项目可用30%、复杂项目可用70%作为初版估算参考，最终以工时成本与供应商报价校核并版本化。这些参考比例不得替代实际成本事实，也不限制实际支出可超过预算。

C_impl_final = 已核实人工工时 × 对应成本单价 + 实施承包发票/已锁定合同成本 + 直接实施测试或工具成本。与模型、基础设施等其他直接成本逐项去重。每个里程碑核对预算与实际差额；报价无实际证据时佣金仅展示预估，不进入支付。若服务方合同约定S的50%为固定报酬且完成验收，则据合同形成实际成本，不重复加入同一人工。

#### 6.7.1 报价演算与扣费次序

以下均为假设预算演算，服务费S=1,000元、其他直接成本100元；实际结算按已核实成本重算。实施成本先扣，剩余毛利润再乘30%，不从服务费直接返30%，也不先返佣再扣实施成本。

| 预算情形 | 实施成本 | 其他成本 | 毛利润 | 推荐佣金 | 玄钧剩余 |
| --- | --- | --- | --- | --- | --- |
| 简单 30% | 300 | 100 | 600 | 180 | 420 |
| 标准 50% | 500 | 100 | 400 | 120 | 280 |
| 复杂 70% | 700 | 100 | 200 | 60 | 140 |


正式报价应计算返佣后贡献：K = (R − C) × 70%（毛利润为正时）。若最低目标为返佣后贡献占净收入m，则Price Floor ≥ C ÷ (1 − m/0.70)，要求0≤m<0.70。例：实际直接成本500元，目标贡献率20%，不含税净售价至少700元，此时毛利润200元、推荐佣金60元、剩余贡献140元。支付费等随售价变化的成本必须联立计算，不能把可变成本当固定常数。

无推荐订单佣金为0；有推荐与无推荐的报价成本模型分别显示，但正式价格不得低于对应批准底价。平台剩余贡献仍须覆盖一般管理、研发、获客、税后经营等费用，不能直接称为净利润。

### 6.8 推荐人后台与财务透明

Partner Dashboard复用统一身份、RBAC、CRM和Admin框架。模块包括伙伴协议与政策版本、邀请链接/邀请码、候选归因、已绑定客户、业绩、收益、结算单、收款资料、申诉及通知。推荐人只能查看自己一级关系范围，客户名称默认脱敏，不展示客户Secret、完整联系方式、交易敏感数据或不相关业务明细。

业绩展示点击、注册、确认绑定、首付客户、活跃付费客户、续费/增购、已确认净收入和真实转化率，清楚区分候选客户与永久绑定客户。收入展示预估、待确认、应计、待风险释放、可支付、已支付、已冲回和争议冻结；预估金额不得计入可提现。

每条佣金展示客户脱敏ID、订单/账期、产品、收入确认日、R、逐类直接成本及依据摘要、G、30%比例、累计E、本期ΔE、舍入与汇率、冲回原因、风险释放日、付款批次与状态。可导出CSV/结算单、提出带证据申诉；成本敏感详情可脱敏，但类别和计算基数必须可核对。

支付与修改收款资料采用权限、强验证、变更通知与审计。管理员不得手改余额；客服只解释账本事实。后台合计必须与Finance/Ledger对账一致，多币种不直接相加，渠道流量归因与合同推荐归因分别显示。

### 6.9 金融订阅与透明资源收费

金融基础订阅为US$19.90/月，单交易所、单交易账户API连接；高级订阅为US$39.90/月，支持多交易所、多交易账户API连接。高级价格币种为美元。多连接不等于无限连接，具体容量、并行策略数和支持范围在产品发布前确定，不擅自承诺无限。

一个API连接按一个提供方下的交易账户授权连接计数。同一账户为交易与只读分别配置凭据时，若共同服务该连接，不因密钥数量重复收费；不同子账户或不同交易账户分别计数。此为建议工程口径，发布前应完成Owner确认及权益测试。

订阅支付工具权益与明确约定的基础服务，不包含额外API、服务器、部署、行情许可、交易佣金及专项维护。不是OpenClaw官方订阅。基础支持与专项服务的边界、响应目标、取消续订、升降级生效时点及退款规则须在购买前说明。

平台代付API按客户可核验实际成本加20%调用服务费，费用＝成本×1.20。成本10美元、服务费2美元、合计12美元；不包含订阅或服务器。实际成本按Provider权威用量与有效费率计算，折扣、退款与冲回按可归属事实处理。免费调用不虚构成本，成本未知不编造金额。该20%是成本加价率，不是20%净利润或收益分成。

BYOK客户自行向供应商付款，平台不得再次收取供应商本金；调用管理费用须另明确基数并授权，未确定前不自动套用。模型调用与券商交易API调用分别列示，接口没有调用费用时不得虚构成本；交易手续费及行情许可属于独立第三方费用。

独立服务器按真实采购价格收费，周期与采购周期一致；共享服务器按公开资源费率或明确分摊规则收费，不重复向每位客户收整台费用。部署、迁移、定制和专项维护按工作范围另行报价，客户确认后执行。套餐包含部分不重复收费。

### 6.10 全产品双币价格与报价版本

每款可售产品、功能、套餐或板块同时展示USD和CNY价格；免费框架显示两币种0。单独销售功能显示自身价格，套餐内功能明确包含及增量0，不虚构单售价格。按量产品显示双币单位费率与估算总额，定制服务在授权前生成双币报价。

美元为金融订阅基准价，人民币动态折算。复用统一汇率服务，记录来源、USD/CNY报价方向、汇率日期、获取时间及有效期；不使用模型猜测。建议Asia/Shanghai每日首次报价获取有效汇率，订单锁价24小时，续订按新账期报价；Decimal按ROUND_HALF_UP保留两位。汇率源尚未验收前保持待配置。

缺少有效任一币种价格或权威成本时阻塞新发布及收费；不改已支付订单和既有账单。双币显示不等于支持双币收款，实际支付币种和渠道单独列明。价格、税费、采购、成本及服务费以同一PRICE_VERSION生成，客服与面板读取统一来源。

钱包沿用现有预存与消费账本，充值不是收入或毛利，不直接生成推荐佣金。实际消费并确认收入后按已有正式规则核算；原币安收费不变。云汇既有推荐比例、实施预算和商业政策不因本次金融定价修改。

### 6.11 定制开发与模块订阅独立收费

一个客户账户、两条收费业务线、一套统一商业财务系统。定制开发依据合同收费；标准模块依据套餐、公开价或有效合同权益收费。开发订单与订阅订单分别记录收入、成本、退款及利润，推荐返佣均读取第6.6节统一规则，不在模块复制比例或结算政策。

统一对象包括Development Contract / Order、Payment / Prepayment Allocation、Module Entitlement、Subscription Schedule、Period Invoice / Usage Order；订单类型与款项用途明确。开发预付款仅抵扣对应合同，不自动转为普通钱包余额，不默认抵扣订阅。例外转用须有合同依据、审批与一次性可追溯分录。

同一客户可以同时定制和选配多个模块，优惠绑定客户、合同、模块及套餐范围，不扩展到所有商品。开发费不表示购买未来全部功能，也不默认为永久免费云服务。

#### 6.11.1 合同与长期费用一起确认

开发报价同时明确范围、开发价、付款节点、变更价、验收与交付条件，以及交付模块、包含额度、初始服务期、续费价格、周期、优惠期限、调价规则、支持范围及取消规则。签约前展示一次性费用与持续费用，不能验收后才增加未约定订阅。

默认以验收通过且具备实际使用条件为服务起算条件，合同有其他约定时执行合同。免费期可以按日或自然月计算，保存时区、period_start、period_end及边界规则；不得因开发延误提前耗尽免费期。

开发费、初始模块服务、维护及专属扩展分别标识履约范围。合同将初始服务包含在开发总价中时保留履约关联及适用的分摊依据，不能因独立订单重复收取或确认收入。

#### 6.11.2 交付事件自动建立模块权益与订阅

验收完成→核验开通条件→映射标准模块及专属扩展→创建合同权益→建立订阅计划→初始化租户配置→开通→显示当前服务期及首次续费日。此过程不是客户重新购买一次，也不重复收开发费。

交付事件绑定合同、验收版本、模块/套餐、服务起算日、权益和幂等键。模块可以私有交付，无须等待公开上架。付尾款前是否允许开通由合同决定，不硬编码统一规则；开通失败保留真实状态，恢复时不重复扣款或重复授予。

示例金额仅用于说明：开发20,000元，预付款5,000元、尾款15,000元；公开订阅299元/月，合同专属99元/月，验收开通后3个自然月包含在初始服务内。2027年1月1日开通则1月至3月初始期，4月1日首次续费99元。开发款结清与模块服务有效分别展示。

#### 6.11.3 自动续费与到期处理

自动纳入订阅管理、生成续费账单及提醒，不等于自动扣款。支持手动续费、已授权余额续费及具备有效支付渠道授权的扣款。余额充足不是授权证据，授权绑定模块、周期、付款来源、可接受金额及版本，可撤销。

建议到期前14天、7天、1天提醒，实际按客户策略配置。失败有限退避并查证，余额不足进入待付款，不形成负余额。已创建账单不得重复生成；重复支付回调不得重复扣余额或延长服务期。

取消自动续费默认本期继续、下期不扣款；立即停用、退款另行处理。到期按模块规则暂停新增任务或高成本调用，保留查看、导出和续费入口，按已公布保留期限处理数据，不能直接删除。恢复不改历史订单。

年订阅、月订阅及按量组合明确额度重置、升降级、差额和生效时点；续费是延长既有订阅，不再收开通费，除非新增独立实施服务且事先确认。

### 6.12 定制成本与统一账务衔接

预算估算、已归集实际成本、待确认成本分别记录。实际AI调用、专用资源、软件账单、经核验工时及事先确定成本标准有证据；UNKNOWN不能填0，预算不能自动变为已结算成本。

客户专属研发、公共核心研发、产品化改造及后续运行成本分开，使用事先确定的归集/分摊政策与唯一成本来源，不既全部归入首批合同又重复扣到订阅。第6.7节实施预算参考不作为定制研发毛利的默认事实。

定制报价可以基于工作量、交付风险和客户价值，不要求向客户公开内部成本。成本未完成结算时展示利润暂估/待核算，按统一规则暂停相应可支付佣金。

收款、预付款分配、订单核销、服务履约、收入确认、退款与佣金分别记录。账户余额付款不是第二次现金到账；初始免费权益不产生虚假收款，订阅按履约保存收入证据。具体会计科目与分摊依据遵从统一财务政策。

历史合同收款迁移保留原凭证、实际到账、已抵扣额、合同权益与服务期限，只迁移一次，不伪造新收款。客户社区经营、分账、公益及第三方业务资金不进入玄钧软件收费钱包或平台服务收入；相关业务数据与玄钧收费账本按权限隔离。

### 6.13 后台套餐、定价与政策调整

后台统一设模块产品、套餐额度、价格版本、合同客户权益、订阅续费、财务成本六个管理区。分别管理功能定义、能力组合、金额周期、专属优惠及履约账务，不让调整价格覆盖模块代码或合同。

Price Book至少记录MODULE_ID、PLAN_ID、币种、计费单位、税费口径、setup_fee、固定订阅、included_usage、usage_rate、生效时间、适用客户、锁价期限、优惠叠加、成本预算、底价、审批与版本。双币展示、汇率、锁价与有效性沿用6.10，不在模块另设汇率服务。

价格状态为DRAFT→PREVIEW→APPROVED→EFFECTIVE→RETIRED。发布前模拟新客户、存量续费、合同锁价、即将到期优惠和已生成账单的影响。有效合同约定优先，其次有效客户权益、适用促销、公开价；优惠叠加有明确规则。

固定续费价与按公开价折扣分别记录。成交锁定价格、服务期、额度及权益快照；新价不改历史付款，不取消合同优惠。存量续费按已约定调价机制通知；需要重新授权的金额变化不无声扣款。

Owner不能直接改余额或历史分录。价格、权益及合同变更记录原因、范围、责任人与证据；AI只建议，获有效授权且通过对应审批的确定性流程执行。

## 7 共创贡献与声誉网络

### 7.1 身份与账本对象

XUANJUN WEB3 CONTRIBUTION NETWORK 前期采用中心化运行、可验证、不可交易的贡献网络。Web3 用于记录身份、来源、贡献、声誉、凭证和历史，不以发币或二级市场为前提。

核心对象包括 CREATOR_ID、DEVELOPER_ID、PRODUCT_PROVENANCE、CONTRIBUTION_EVENT、CONTRIBUTION_LEDGER、REPUTATION_EVENT 与 CREDENTIAL，连接第3章产品身份与第6章收入确认事实。

### 7.2 贡献值的生成与归属

CONTRIBUTION_POINT（CP）规则：1 RMB ELIGIBLE_ATTRIBUTABLE_NET_REVENUE = 1 CP。CP 只能在 Revenue Recognition、直接成本、退款和 Chargeback 等事实完成后生成；充值、钱包余额、未消费预付款和订单展示金额不得直接生成 CP。

同一笔已确认可归属净收入不得重复生成经济贡献值。多人或多角色共同贡献时，在同一 CONTRIBUTION_EVENT 中按归属比例分配，系统级 CP 总量不得超过该笔 ELIGIBLE_ATTRIBUTABLE_NET_REVENUE 对应值。

XUANJUN_AI_DEVELOPER、客户创作者与第三方开发者采用同一 CP 规则。自主产品可将相应开发贡献归属平台 AI 开发者；客户 AI 共创产品按预先定义的 Contribution Attribution 在客户、AI 开发者等角色间分配。

### 7.3 声誉与经济贡献分离

REPUTATION_SCORE（RS）与 CP 分离，用于衡量安全、质量、维护、履约、退款、投诉、版权和隐私事件、漏洞响应及版本稳定性等可信度，不按收入简单累加。

### 7.4 权利边界与证明策略

硬规则：CONTRIBUTION_POINT_TRANSFERABLE=NO；CONTRIBUTION_POINT_TRADABLE=NO；CONTRIBUTION_POINT_WITHDRAWABLE=NO；CONTRIBUTION_POINT_PURCHASABLE=NO。

硬规则：CONTRIBUTION_POINT_CASH_VALUE=NONE；EQUITY_RIGHT=NONE；PROFIT_RIGHT=NONE；SECONDARY_MARKET=DISABLED；P2P_TRANSFER=DISABLED。

CP、RS 与 Credential 在前期均不可转让、不可交易、不可提现、不可购买，不代表现金、股权或利润权。XUANJUN_AI_DEVELOPER 采用相同规则，不设后台特权加分。

未来如将贡献值、声誉值、凭证或其他生态资产开放为可转让、可交易或可兑现能力，上线前必须重新完成法律、监管、税务、财务与安全审查，不得自动开启。

第一阶段不上链也不影响业务，先建立 Append-only、可审计、可签名的 Contribution / Provenance Ledger。后续按需要将批次 Hash 或 Merkle Root 等证明锚定到合适链上，不把客户身份、收入、账户、Secret 或企业敏感数据直接上链。

可扩展 Verifiable Credential 与 DID；它们属于身份与证明层，不自动产生 Token、交易权或资产权。

### 7.5 凭证签发验证与纠错

首批凭证类型为创作来源、贡献确认、交付验收及维护安全记录。每份关联credential_id、issuer_id、subject_id、tenant_id、product_id、product_version、event_ids、evidence_refs、claims、policy_version、issued_at、valid_from、valid_until_if_any、status_ref、signing_key_id及签名。证据读取受授权控制，公开展示只包含获准最小字段。

生命周期为证据完成→确定性规则判定→受控签发→持有人查看或导出→验证→暂停或撤销→补偿记录与重新签发。签发和计分不能由自由文本直接写入；同一来源事件去重，原记录不覆盖。退款、归属纠错和证据失效先形成补偿事件，再更新投影或撤销旧凭证。

验证检查签发者、格式、签名、主体、产品版本、有效期及状态，并按用途核对证据与规则。签名或链上Hash只能证明来源和完整性，不能单独证明业务事实真实。维护密钥轮换、泄露后的批次撤销、验证入口、申诉及审计；第一阶段可采用站内签名凭证，只有标准兼容测试通过后才标记为相应Verifiable Credential。

贡献值CP、声誉RS、推荐佣金、客户钱包与凭证分别建模并关联统一事件。第7.2节1元合格可归属净收入生成1CP的既有口径保持不变，推荐佣金继续按第6.6节毛利润30%计算。提需求、反馈、测试和安全维护可以先记录非经济贡献事件及相应凭证，不凭空产生收入CP。RS采用版本化指标、样本数、观察期、奖惩依据和申诉，不以单一订单或收入作为可信度。 生态权益值ECV为独立限量对象，按7.7节总量、交易分档及活动专项规则生成，不能与CP或佣金相加当成同一余额。

### 7.6 共建共治共享的阶段治理

共建从需求建议、测试、授权反馈、维护和安全贡献开始；贡献记录区分提出者、开发者、审核者与维护者，避免重复计分和同一主体自我背书。共治首先开放规则提案、产品路线建议、质量评议与申诉，由已公布的责任角色处理并说明结果。

提案记录范围、提出者、资格规则、讨论期、参与记录、结论、执行责任和证据。早期投票属于咨询意见，除已明确授权事项外不直接变成生产指令；身份去重和异常参与检查先于扩大治理。贡献值或声誉不自动授权访问客户数据、修改资金、部署代码或决定他人的合同权益。

共享通过已确认合同中的推荐佣金、创作报酬、维护报酬和约定服务权益落实。不同角色可兼任，但收益依据、直接成本和支付分录分别记录。推荐人只负责一级推荐；实施合作另签合同，同一实施成本不得重复扣除。未来拟引入可交易或限量生态资产时另设阶段，不修改当前CP的不可交易及无现金权益政策。 本次新增的限量生态权益值机制按7.7节单独核算，不改变CP；可交易、可兑现及利润分配能力仍须另行审查与验收。

凭证和可选链上证明先服务真实身份、来源与履约验证；元宇宙在已有用户、产品、交易和协作需求后建设。空间界面继续读取现有Ledger、Registry和Graph，不另造贡献余额。

### 7.7 生态共建共享权益机制（V1.1）

依据Owner于2026年10月14日提交的《贡献权益(2).txt》更新。本节定义生态权益值（ECV），与7.2节CP、RS、现金钱包、推荐佣金分别记账、关联统一贡献事件。ECV不按1元净收入等于1CP的规则直接生成；原CP口径与第6.6节推荐政策不因本节修订而改变。既有不可交易、不可提现、无固定收益与权限边界继续适用；本节的未来价值共享属于待形成并验收的机制，不构成现时固定收益、法定股权或可自动执行的利润权。

开发状态：规则已更新，功能与平台权限未验收，活动默认关闭；生态账户、贡献事件、资金及审计沿用既有权威系统，不建立第二余额。

修订日期：2026年10月13日

本版更新总量分池、交易额门槛、两平台粉丝活动、创始人同比释放及反作弊要求。规则记录不代表功能已开发、权益已发放或活动已获准上线。

#### 7.7.1 生态机制设计理念

玄钧云汇生态体系以“共建、共治、共享”为核心理念，构建一个由消费者、推广者、开发者、生态合作伙伴以及创始团队共同参与发展的长期商业生态。

传统商业模式中，消费者完成购买后，与企业未来发展之间的连接较弱；推广者创造市场价值，但通常只能获得一次性收益；开发者创造技术价值，但无法长期分享生态成长成果。

玄钧云汇希望通过生态权益机制，将不同角色创造的价值进行量化，使每一个真正参与生态建设的人，都能够成为生态发展的参与者、建设者和共享者。

生态权益体系将消费者、推广者、开发者、生态赞助者等不同角色连接起来，让价值创造者能够参与生态治理，并共享生态长期发展的成果。

#### 7.7.2 玄钧云汇生态权益总量设计

玄钧云汇生态权益总量永久限定为：

1000万份生态权益值。

生态权益总量固定，不进行无限增加，以保证生态权益体系长期稳定。

按释放来源划分：

第一档交易贡献池：300万份。

第二档交易贡献池：300万份。

第三档交易贡献池：300万份。

活动专项池：100万份，其中两平台粉丝活动合计70万份，创始人活动联动额度30万份。

合计：300万＋300万＋300万＋100万＝1000万份，永久封顶，不增发。

按受益人划分，沿用原文创始生态权益30%、生态共建权益70%的总量结构：

三档交易贡献池合计900万份，含创始生态权益270万份及生态共建权益630万份；每档300万份含创始90万份、共建210万份。

活动专项池100万份，含两平台粉丝共建权益70万份及创始人联动权益30万份。

创始额度合计300万份，共建额度合计700万份。来源分池与受益人分类是同一总量的两个维度，不能相加重复计算。

活动预算分配不等于实际发放。尚未符合条件或尚未领取的额度保持未释放，不能提前划给创始人，也不能重复从三档交易池扣取。

创始生态权益用于体现创始团队在玄钧云汇生态建设过程中的长期贡献，包括：

商业模式设计；

技术体系建设；

品牌建设；

战略规划；

生态发展推动。

生态共建权益用于奖励所有参与玄钧云汇生态建设的成员，包括：

消费者；

推广者；

开发者；

生态赞助者；

合作伙伴；

其他生态贡献者。

创始生态权益与生态共建权益按照同一释放机制同步产生，不提前释放，不单独释放。

#### 7.7.3 生态权益释放原则

玄钧云汇生态权益采用：

“贡献产生、阶段递减、总量限制”的释放机制。

生态权益不会一次性发行，而是在生态参与者创造真实价值时，根据当前生态发展阶段对应的释放系数产生。

交易贡献池的阶段依据为玄钧云汇累计有效交易额；活动专项池按第十二节独立规则释放，不能把粉丝授权、关注、领取或创始人同步释放算作交易额。

累计交易额统一使用人民币等值；美元按固定统计汇率1美元＝6.8元人民币换算，仅用于本机制统计，不代表实时兑换报价。每笔有效交易只计一次，不能因消费者、推广者、开发者多角色获益而重复计入交易额。充值、押金及尚未消费的预付款不直接计为有效交易；退款、撤销和作弊交易需有可追溯调整记录。其他币种换算规则未明确前不得随意计入。

三档门槛明确为：第一档0至1亿元人民币（含1亿元）；第二档超过1亿元至10亿元人民币（含10亿元）；第三档超过10亿元人民币。

美元统计等值分别约为14,705,882.352941美元、147,058,823.529412美元，以人民币换算后的精确值比较，不用展示取整值决定跨档。跨档交易按各档实际覆盖金额分段核算，不能把整笔交易重复算入两档。

不同发展阶段采用不同释放比例：

早期阶段释放速度较高，用于吸引生态建设者；

成长阶段释放速度降低，用于保持生态长期稳定；

成熟阶段进一步降低释放速度，用于保障生态权益持续价值。

#### 7.7.4 第一阶段：生态启动阶段

适用范围：

玄钧云汇累计有效交易额0至1亿元人民币等值以内（含1亿元）。

本档总释放上限300万份，包含共建210万份和创始90万份。额度用完即暂停本档，不能提前使用第二档额度。

该阶段属于生态建设初期，为鼓励消费者、推广者、开发者以及生态支持者参与建设，采用最高权益释放比例。

释放规则：

消费者：

每产生100元消费金额，获得10份生态权益值。

推广者：

每产生100元销售业绩，获得10份生态权益值。

开发者：

每获得100元项目分成，获得10份生态权益值。

生态赞助者：

每投入100元生态建设支持，获得100份生态权益值。

该阶段目标是快速建立生态基础，让早期贡献者能够获得较高比例的生态权益。

#### 7.7.5 第二阶段：生态成长阶段

适用范围：

玄钧云汇累计有效交易额超过1亿元、且不超过10亿元人民币等值。

本档总释放上限300万份，包含共建210万份和创始90万份。额度用完即暂停本档，不能提前使用第三档额度。

进入生态成长阶段后，为保证生态权益长期持续释放，所有权益获取比例按照第一阶段规则降低50%。

释放规则：

消费者：

每产生100元消费金额，获得5份生态权益值。

推广者：

每产生100元销售业绩，获得5份生态权益值。

开发者：

每获得100元项目分成，获得5份生态权益值。

生态赞助者：

每投入100元生态建设支持，获得50份生态权益值。

该阶段重点是在扩大生态规模的同时，控制权益释放速度，保持生态长期发展能力。

#### 7.7.6 第三阶段：生态成熟阶段

适用范围：

玄钧云汇累计有效交易额超过10亿元人民币等值。

本档总释放上限300万份，包含共建210万份和创始90万份。本档额度释放完毕，不再新增交易贡献权益；活动专项池也只能在自身100万上限内继续依规则释放。

第三阶段按照第二阶段规则再次降低50%。

释放规则：

消费者：

每产生100元消费金额，获得2.5份生态权益值。

推广者：

每产生100元销售业绩，获得2.5份生态权益值。

开发者：

每获得100元项目分成，获得2.5份生态权益值。

生态赞助者：

每投入100元生态建设支持，获得25份生态权益值。

该阶段代表生态进入成熟期，通过降低释放速度，使三档合计900万交易贡献额度能够长期服务生态发展，并与100万活动专项额度分别核算。

#### 7.7.7 阶段释放限制机制

每一个交易阶段均设置300万份独立总额度，创始人与共建参与者释放共同占用该档额度。

第四至六节列明的10／5／2.5份及100／50／25份，沿用原文参与者获取系数，属于共建侧权益。创始侧按照共建侧有效实际释放量乘3／7同步核算，不能在300万档位上限之外再加30%。同一贡献的重复回调不得重复发放。

创始侧按累计有效共建释放额计算，再减去已净释放额，得到本次差额；取整余数累计保留，不能逐笔向上取整。每档共建210万、创始90万、总计300万的限额同时生效。接近额度边界时先核算可发放余额，不得超发，超出部分不得自动挪用下一档。

活动专项额度不随交易额跨档自动解锁，也不占用或扩大三档交易贡献额度。

当某一阶段对应的生态权益额度全部释放完成后，该阶段立即停止继续产生新的生态权益。

即：

当前阶段权益池释放完成后，即使继续产生消费、推广、开发或赞助贡献，也不会继续按照该阶段规则释放。

暂停期间贡献记录仍可保存，但不生成权益债务，不自动追溯补发；下一档达到交易额条件后，才按新档规则处理此后符合条件的贡献。若未来制定补发规则，须另行审批并计入对应额度，不能默默突破上限。

交易额进入下一档时适用下一档系数；上一档未用余额保持封存，不自动挪入新档。退款导致交易额回落时不得自动重开已关闭档或重置历史已释放额度，需版本化对账处理。

例如：

第一阶段生态共建权益额度已经全部释放完成。

即使累计交易额仍未进入第二阶段，第一阶段也不再继续增加生态权益。

只有达到下一阶段条件后，才启动新的释放规则。

通过该机制，保证生态权益释放具有明确边界，避免早期阶段无限释放导致生态权益过快消耗。

#### 7.7.8 生态权益永久有效机制

依法依规、符合规则且有效入账的玄钧云汇生态权益永久有效；误发、重复发放、退款关联调整和确认作弊的冲正不属于时间到期清零，须保留原记录与调整凭证。

生态权益不会因为时间流逝自动失效，不设置强制清零机制。

生态权益持有人长期保留其生态身份和历史贡献记录。

生态权益代表：

长期贡献证明；

生态成员身份；

生态治理参与基础；

未来生态价值共享依据。

#### 7.7.9 生态价值共享机制

玄钧云汇未来经营产生利润后，将根据企业发展情况建立生态价值共享机制。

企业利润的一定比例进入生态价值共享池，用于奖励长期参与生态建设的成员。

生态价值共享不采用固定收益模式，而是根据企业真实经营成果、生态贡献以及生态权益权重综合计算。

计算因素包括：

生态权益数量；

贡献类型；

持续参与时间；

生态活跃程度；

实际生态贡献价值。

通过这种方式，实现：

企业发展创造价值；

生态成员共享价值；

贡献越长期，价值连接越深入。

#### 7.7.10 生态治理机制

玄钧云汇生态权益持有人拥有生态治理参与权。

生态治理范围包括：

产品发展方向建议；

生态规则优化；

生态项目讨论；

社区发展规划；

生态合作方向建议。

治理权采用综合权重机制，不单纯按照资金投入决定。

综合参考：

生态权益数量；

贡献历史；

参与时间；

生态贡献程度。

确保生态治理由真正建设生态的人共同参与。

#### 7.7.11 生态模型总结

玄钧云汇生态体系通过固定1000万生态权益总量，结合三档各300万的递减释放机制、100万活动专项池及创始人同比释放机制，将消费者、推广者、开发者、生态赞助者以及创始团队连接成为共同发展的生态共同体。

消费者通过消费创造市场价值；

推广者通过传播推动生态增长；

开发者通过技术创造生态能力；

生态赞助者通过资源支持推动生态建设；

创始团队负责生态方向和长期发展。

最终形成：

贡献产生权益；

权益参与治理；

生态创造价值；

成员共享成长。

玄钧云汇希望建立的不只是一个商业平台，而是一套能够长期运行的生态共建体系。

共建生态，共治未来，共享成长。

#### 7.7.12 抖音与X粉丝活动专项规则

1. 额度来源

活动专项池总计100万份。抖音粉丝预算35万份，X粉丝预算35万份，创始人同比释放预算30万份。全部计入1000万总上限，不额外增发；X活动仍须完成能力、费用与上线验收后才能启用。某平台未上线或未领完的预算不得自动转给另一平台或创始人。

2. 每个平台独立分为三批

第一批：有效领取序号1至100,000，每人限领一份，每份2权益值，本批合计200,000权益值。

第二批：有效领取序号100,001至200,000，每人限领一份，每份1权益值，本批合计100,000权益值。

第三批：有效领取序号200,001至300,000，每人限领一份，每份0.5权益值，本批合计50,000权益值。

每个平台最多300,000个有效领取名额，合计350,000权益值；两平台共600,000个平台领取名额、700,000权益值，不将其写成60万独立自然人。

同一人在同一平台整个活动仅能领取一次，不能在三批各领一次。先到先得依据完成身份绑定、粉丝与风控核验并成功入账的服务端事务序号；同一事务内分配档位并扣减额度，不能按客户端时间或历史关注排名分配。失败、重复及待审核申请不计为成功领取。

同一自然人能否分别参加抖音和X两场活动，Owner尚未最终确认；须在活动上线前明确并配置跨平台去重政策，不能由开发人员自行扩大领取范围。

3. 粉丝资格是硬条件

用户须授权绑定其本人平台账号，并在领取核验时关注玄钧指定的官方账号。平台稳定用户标识须与生态账号安全绑定，不能用昵称、手填账号或截图替代身份验证。

授权登录成功不等于已关注；未关注禁止发放，权限不足、查询失败、分页不完整或证据过期等情况标记待核验，禁止按粉丝通过。官网和SaaS使用同一账户与领取账本。

粉丝验证具体方案在活动开发阶段补齐。只信任与申请人、指定官方账号、核验时间及领取请求绑定的可靠证据；不能直接信任浏览器或小程序上传的hasFollowed=true。接口返回成功也不等于关注状态为真。

平台资格记录只服务于本活动，并依授权范围、必要性和保留期限处理；不收集平台密码，不在日志或文档保存访问令牌。

4. 创始人联动释放

两平台累计有效实际领取权益值记为U，0≤U≤700,000。

活动创始人累计应释放F＝min(300,000，U×3／7)。

每次入账后按累计应释放值减去创始人已净释放值补齐差额，发至经确认的创始人生态账户；未领取预算、失败请求和待审核申请不计入U。不得再对活动池或创始人份额重复叠加30%。

例：U为70,000时F为30,000；U为350,000时F为150,000；U为700,000时F为300,000。以权益值数量计算，不按用户人数计算。

使用定点数或精确有理数运算，统一精度须支持0.5，并对3／7的循环小数保留累计余数；按累计值向下截取可入账精度，末次在总上限内结清，不使用二进制浮点逐笔四舍五入造成超发。

无效领取、重复发放或确认作弊需冲正U，并据此调整F；创始人已使用部分不足冲正时进入负债／冻结待对账状态，不删除历史记录或伪造余额。具体冲正和申诉流程须验收后启用。

5. 防刷与防薅羊毛

同一平台稳定ID、生态账号、活动资格和请求幂等键联合去重；解绑重绑、改昵称、换登录方式、并发请求和重复回调均不能再领。

结合同IP短时批量注册／领取、设备关联、多账号共用设备或验证信息、异常频率、自动化请求、异常网络与行为模式进行风险评估；同IP不等于同一自然人，不得仅凭共享IP一刀切拒绝家庭、企业或校园用户。设备/IP信号可能变化或被伪造，不能单独证明真人唯一性。

服务端限频、短期单次领取凭证、身份和会话绑定、重放防护、原子扣额、唯一约束及审计记录为开发要求。账号关联与设备数据须遵循最小必要原则和适用隐私要求，不能为了防刷无限采集用户信息。

风险较低且资格明确者按规则入账；高风险者暂缓并进入人工复核，不占正式成功名额；确认作弊者拒发或有证据冲正，同步调整创始人联动额。用户可申诉，记录触发原因、证据、审核人、结果及版本；误判纠正遵循公开活动规则，不暗中重排已成功领取的名额。

已撤销的名额是否重新开放、取关后的处理、风险审核时限、跨平台资格以及人工复核标准须在上线前明确。不得擅自以取关为由追缴已合法领取且永久有效的权益；领取时资格要求与领取后规则分开披露。

6. 开发与上线验收门禁

状态：规则已记录；真实权限、可靠粉丝核验及完整领取功能未验收，活动默认关闭。先复用既有身份、权益账本、审计与风控模块，不另建相互矛盾的余额系统。

需逐平台验收：已关注合法账号领取成功；未关注拒绝；身份冒用、伪造关注、过期结果、接口错误／限流、分页缺失均不发放；多账号关联、重复绑定、同IP正常家庭与批量作弊分别处理；接口重放、跨入口并发及超额请求不得重复或超发。

必须验证第100,000／100,001、200,000／200,001及300,000／300,001名边界；各平台350,000上限、活动共建700,000上限、创始人300,000上限和总量10,000,000上限；失败重试、崩溃恢复、退款／作弊冲正、舍入余数与审计一致性。

平台能力或费用未确认时不得开启自动发放；须核对活动规则、权益用途披露、个人信息授权与适用合规要求。原文生态共享用途沿用，不将权益表述为固定收益、保本承诺或已取得法定股权。

#### 7.7.13 平台能力核查记录

核查日期：2026年10月13日。以下为官方公开文档能力，不代表本项目应用已获批或实测通过。

抖音：网站OAuth可用于身份绑定；粉丝列表接口最多查询5,000人且不保证顺序，不能据此完整确认30万名申请人的资格。小程序tt.checkFollowAwemeState需申请权限，返回客户端hasFollowed；该布尔值本身不是供官网服务端验真的证明。现有应用后台需登录，尚未读取实际已开通权限；开发阶段优先检查已有服务端能力，再确定可靠验证方案。

X：提供授权用户身份及服务端粉丝／关注列表接口，可据此设计身份绑定与关系核验；必须处理分页、权限、受保护账号、核验时效和异常，未查到不应冒充完整证明。项目现有权限、实际调用与费用预算尚未核实。

X当前公开列价普通Following/Followers读取0.01美元／资源；满足自有应用所有者读取本人数据条件的Owned Reads为0.001美元／资源。一次读取30万资源的示例分别为3,000／300美元，不含其他身份查询及跨日复查，不是活动总报价。开发前以控制台适用价格复核并审批费用，本文不授权购买或调用收费接口。

官方参考：

https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/user-data/get-fans-list

https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/api/open-interface/follow/check-follow-aweme-state

https://docs.x.com/x-api/users/follows/introduction

https://docs.x.com/x-api/users/lookup/quickstart/authenticated-lookup

https://docs.x.com/x-api/getting-started/pricing

https://help.x.com/en/rules-and-policies/x-contest-rules

#### 7.7.14 本次变更记录

2026年10月13日，依据Owner确认更新：

1. 修正旧交易额阶段门槛，统一为1亿元及10亿元人民币等值分界，美元统计汇率6.8。

2. 三档释放总额度各300万，另设100万专项池；保留1000万总上限，创始30%／共建70%的原文总结构，并明确额度内包含关系。

3. 抖音旧方案10万人各1份更新为三批各10万人，分别2／1／0.5权益值；X计划同规则。各平台35万，两平台共70万预算，尚未实际发放。

4. 活动创始人30万按用户有效实际领取的3／7同步释放，不提前发放、不重复叠加。

5. 新增粉丝硬核验、去重、共享IP辨别、多账号关联、反重放、并发限额、人工复核及冲正要求；验证方案延至活动开发时完善，但验收前禁止上线领取。

6. 本权益机制已同步至本开发文档第7.7节及节点2.15、阶段8、全程验收的关联要求；未表示源码、生产账本、平台设置或活动功能已实现。

## 8 客户发现与方案交付流程

### 8.1 客户入口与发现模式

客户体验入口包括官网、AI Guide、Search、Industry Index、Goal Index、Role Index、Workflow Index、Channel Index、Integration Index、Package Index、Popular / Starter、Module Marketplace、Custom Requirement 入口、Customer Dashboard 与 Partner Dashboard。系统负责理解客户，客户无需先理解技术架构。

| 模式 | 客户情况 | 路径 |
| --- | --- | --- |
| A | 明确知道所需功能，例如 AI 剪视频 | Search → Module Detail → Select，不强制 AI 诊断 |
| B | 知道问题但不知道模块，例如减少客服人工 | Goal / Industry / Workflow 或 AI Product Advisor |
| C | 不知道如何解决 | AI BUSINESS DIAGNOSIS，理解企业、行业、规模、现有系统、客户来源、员工、重复工作、痛点、预算和目标后推荐 Solution |


AI_GUIDE_REQUIRED_FOR_ALL_CUSTOMERS=NO。AI Guide 是重要入口，但不要求全部客户经过同一路径。

### 8.2 模块详情的客户说明

模块页面读取第3章四个统一视图，必须让客户判断模块是否符合需求，覆盖以下信息：

功能、可完成与不可完成事项、适用企业和场景、标准流程、输入、输出、可配置能力、当前状态、版本及已验证能力。

Foundation、Module 与 Connector 依赖；资料和认证；营业执照或行业许可证；第三方开发者账号、会员、订阅、API 及具体权限。

服务器、GPU 和存储要求；国家、地区和主体类型限制；第三方费用承担方；一次性、每月固定、Usage 和可选 Addon 费用。

#### 8.2.1 文字 视频与版本证据

每个板块必须有文字说明和结构化字段，这是搜索、AI理解、无障碍阅读、报价、合同与验收的共同事实来源。说明至少包含适用客户、问题、输入输出、支持/不支持功能、前置条件、费用、人工介入、权限边界、版本状态和可验收结果；视频不能替代费用或限制说明。

核心解决方案和可视交互模块同时提供短演示视频：建议60至120秒，展示真实输入、关键步骤、结果和至少一个限制。复杂方案另提供3至5分钟实施说明；简单本地小工具可使用截图或短动图，不强制每个工具拍摄长视频。以上时长是制作建议，不是技术门槛。

PRODUCT_DEMO_ASSET字段包含product_id、module_version、demo_version、recorded_at、language、caption/transcript、input_sample、evidence_id、demo_type和rights_status。模拟演示明显标记；真实演示去除客户身份与Secret，版本变化后自动标记需复核。演示视频、字幕及文字描述共同接受事实、版权和隐私审核。

#### 8.2.2 勾选渠道时的即时展示

客户勾选渠道时立即展示该渠道支持的具体动作和发布模式、账号/主体/地区要求、认证与应用审核、授权范围、素材规格、频率/配额、版权和商业/AI披露要求、链接限制、可读取指标、数据延迟、客户待办、第三方费用与规则核实日期。适用版本与来源可展开查看，不能只显示一个平台Logo和支持标签。

逐项前置条件显示已满足、待客户处理、硬阻塞或未核实。允许客户选择受阻渠道用于评估，但明确说明该动作暂不可交付；硬阻塞或未知不得进入普通付款。若方案允许剔除受阻动作、改为用户确认或导出，必须展示新交付范围并重新报价及确认，不静默降级。

选择多个渠道时逐渠道检查，同时核对内容格式、权限和跨渠道费用。付款前保存channel_requirement_snapshot和customer_acknowledgement，部署和每次发布前再核实实时授权及政策；快照用于追溯而不是冻结平台规则。

### 8.3 购买前就绪检查

PRE_PURCHASE_READINESS_CHECK 必须在正式付款前执行，以 NO_POST_PAYMENT_SURPRISE 为原则。

检查范围：Foundation、Module dependencies、Connector、客户主体、证照、材料、实名认证、企业认证、开发者认证、账号等级、第三方会员、API申请资格、API权限、Region、Provider、Domain、SSL、备案、Callback、IP White List、服务器、GPU、客户现有系统接口、第三方费用。

| 结果 | 处理要求 |
| --- | --- |
| READY | 可正常报价和购买 |
| READY_WITH_ACTIONS | 原则可实施，但存在客户前置任务，生成 CUSTOMER_READINESS_CHECKLIST |
| BLOCKED | 明确硬阻塞，默认 NORMAL_PAYMENT_DISABLED；提供替代方案或 SPECIAL_REVIEW |
| UNKNOWN | FURTHER_VERIFICATION_REQUIRED，不得直接标为 READY 或 SUPPORTED |


客户前置任务清单字段：ACTION_REQUIRED、RESPONSIBLE_PARTY、EXPECTED_EXTERNAL_COST、BLOCKS_DEPLOYMENT、CAN_PAY_BEFORE_COMPLETE、DEADLINE_IF_ANY。

### 8.4 缺口分析与新增能力判断

AI_FIT_GAP_ANALYSIS 比较 CUSTOMER REQUIREMENT、MODULE CAPABILITIES、CONFIGURABLE ITEMS、EXISTING CONNECTORS、EXISTING WORKFLOW 与 EXISTING ASSETS。

处理顺序必须为 CONFIGURE_EXISTING → EXTEND_EXISTING_MODULE → ADD_CONNECTOR → ADD_WORKFLOW → BUILD_NEW_MODULE。

只有现有模块无法合理扩展、扩展会破坏通用性、属于全新核心能力、权限或生命周期完全不同、安全模型明显不同，或具有明确独立产品价值时，才允许 NEW_MODULE_CREATION。

### 8.5 方案购物车与交付确认

SOLUTION_CART 将客户选择转成完整可实施方案，而非只汇总商品。

输入：Selected Modules、Industry、Existing Systems、Channels、Region、Budget、Automation Level、Deployment Preference、Security Requirement、Customer Prerequisites、BYOK / Managed Preference。

后台检查：DEPENDENCY CHECK、COMPATIBILITY CHECK、DUPLICATE CHECK、CONNECTOR CHECK、REGION CHECK、READINESS CHECK、INFRASTRUCTURE SIZING、MODEL REQUIREMENT、PRICING CHECK。

输出：FINAL SOLUTION、Required Foundation、Required Modules、Optional Addons、Connector、Configuration、Implementation Difficulty、Infrastructure、Model Usage、Security Requirement、Customer Actions、Estimated Timeline、One-Time Cost、Monthly Fixed Cost、Estimated Usage Cost、Third-party Cost。

方案经 Commercial 与 Finance 核价后形成报价，完成客户确认和付款，再调用基础设施、模型与 Connector 能力供给和部署。涉及定制的新能力，须先经过第9章工程发布流程；交付后的真实用量进入第6章计费及第10章运营闭环。

### 8.6 两种购买路径与客户界面变化

客户工作台统一设置“我的项目、功能市场、我的模块、账单与付款”。定制客户从项目自然进入模块管理，标准选配客户从市场进入模块管理，不必经过项目开发界面。

定制待签约显示范围、开发价、付款节点与后续订阅；开发中显示款项、里程碑、交付物与变更；待验收显示测试、验收、尾款和开通条件；交付后项目归档，模块显示使用状态、初始服务期与首次续费。

标准客户看公开套餐/有效专属价格、依赖、开通费、订阅及用量，确认后直接支付或服务余额抵扣，也可明确的组合付款。异步开通显示配置进度与真实结果，不把付款成功当作模块已可用。

“我的模块”卡片显示名称、套餐、额度、有效期、下次续费金额、自动续费状态及使用/配置/续费入口。开发结清、订阅有效与付款授权分别展示；不能统一用“已付款”表达三种状态。

续费页展示账期、金额、合同优惠依据、付款来源及取消入口；逾期页说明受限功能、数据保留期限、导出与恢复。客户可同时查看开发合同账单及模块周期账单，不重复付款。

市场说明与模块开发同步完成：适用客户、能力与限制、流程、输入输出、配置、依赖、版本、费用、续费、支持、隐私和退出。付款前检查已有权益避免重复出售；必要部署费、第三方费用及依赖总价不能隐藏。

## 9 工程开发与发布门禁

### 9.1 需求到生产的统一链路

统一开发链：REQUIREMENT → ARCHITECTURE → NODE → OWNER VISIBILITY → GIT BRANCH → DEVELOPMENT → CI → TEST → SECURITY → BUILD → AUDIT → RELEASE GATE → MERGE → RELEASE → STAGING → CANARY → PRODUCTION → OBSERVABILITY → BACKUP → EVIDENCE → CANONICAL STATE → DOT NEXT NODE。

开发前执行第1章复用检查与第10章节点说明。第三方来源还需第2章隔离准入；涉及模型、资金或授权时，分别执行对应领域评测和权限约束。

新功能验收标准由Work与独立QA在开发前明确；分层测试责任、关键回归和真实Canary按9.8节执行。

### 9.2 源码管理与独立审计

建设 XUANJUN_SOURCE_CONTROL_FOUNDATION_V1。Git 用于本地版本管理，GitHub 作为 PRIVATE REMOTE。PUBLIC_REPOSITORY=NO，PRIVATE_REPOSITORY=YES，DIRECT_AGENT_PUSH_TO_MAIN=FORBIDDEN。

Agent 标准流程：Task → Task Branch → Developer → Test → Security → Independent Auditor → Release Gate → Merge。开发、独立审计和发布门禁职责必须区分。

### 9.3 持续集成与构建证据

CI 检查项：Format、Lint、Unit、Integration、Regression、Security、Dependency Scan、Secret Scan、Build、SBOM、Artifact、Evidence。

正式 Build 绑定信息：SOURCE_COMMIT、BUILD_ID、VERSION、DEPENDENCY_LOCK、TEST_RESULT、SECURITY_RESULT、SBOM、ARTIFACT_HASH、RELEASE_STATUS。

遵循 BUILD_ONCE_DEPLOY_MANY：正式构建绑定源码、依赖锁、版本、测试、安全结果、SBOM 与产物 Hash，验证后的同一产物逐环境部署，避免在生产重建未经核验的版本。

### 9.4 发布和产品化的衔接

环境顺序为 STAGING → CANARY → PRODUCTION，发布前完成 Release Gate，具备回滚方案和安全证据。生产运行支持签名发布、运行审计、模块撤销、紧急 Kill Switch 与快速回滚。

新能力完成 TEST、SECURITY、AUDIT 与 PRODUCTION 后，执行 REUSE_CLASSIFICATION → PRODUCTIZATION → MODULE / CONNECTOR REGISTRY → MARKETPLACE，将可复用成果写回统一产品体系。

### 9.5 按需Agent角色与程序门禁

首期采用6个注册角色：项目调度、应用开发、独立测试QA、独立审计、基础设施平台工程、SRE安全运维。按任务唤起，不以6个常驻模型会话或6路并行为目标。数量是当前职责和成本下的起始方案，不宣称未经运行测量的全局最优。Work承担总体架构和重大设计，Coordinator依据蓝图落实节点与复用检查，避免再设一个全程重复规划的架构Agent。测试执行尽量交程序，QA独立制定或核验适用验收用例。

发布准入由独立Release Gate Service执行确定性规则，CI、健康检查、额度计数、依赖就绪、备份定时和通知去重同样优先由程序完成。服务通过最小机器身份提交合并或发布；它与Developer及Auditor的权限分离。原有Release Gate职责保留，运行时是否需要模型只取决于未解决的判断问题，不为名称单独常驻一个Agent。

| 角色 | 主要产出 | 调用条件 |
| --- | --- | --- |
| PROJECT_COORDINATOR | 依据Work蓝图执行任务图、复用检查、依赖及异常协调 | 需要判断时唤起；常规调度由程序执行 |
| DEVELOPER | 任务分支、实现、自测与变更说明 | 明确范围内的应用开发与修复 |
| TEST_QA_ENGINEER | 独立验收用例、集成与端到端测试、缺陷报告 | 新功能、跨域或关键流程；常规回归由CI执行 |
| INDEPENDENT_AUDITOR | 独立安全、权限及重要业务正确性审查 | 准备合并或发布的变更；按风险选深度 |
| INFRASTRUCTURE_PLATFORM_ENGINEER | 云资源、蓝图、部署环境及运行时 | 供给、基础设施或环境变更 |
| SRE_SECURITY_ENGINEER | 可观测性、恢复、安全配置及故障处置 | 运行异常、可靠性变更或恢复演练 |


### 9.6 Agent权限与发布授权

每个角色绑定独立身份、工作目录、工具Allowlist、网络范围及可见会话。Developer只写任务分支和DEV沙箱；TEST_QA_ENGINEER读取需求与冻结提交，独立编写测试、执行隔离验证及记录缺陷，不修改被测业务代码；Auditor读取同一提交和证据，审查安全、权限及重要业务正确性，无生产发布权。Coordinator执行Work蓝图、批准队列和受控状态，不能给自己加权限。平台工程师和SRE通过限定动作的执行服务运维，不持有可任意访问客户账本的root入口。

独立审计不能以另一段提示词替代权限隔离。审计者不得修改被审产物或覆盖测试结果；自动扫描与测试结果由CI身份写入，审计结论绑定commit和artifact hash。发布服务只接受全部要求对应同一版本的证据，任一修改使旧审计或产物门禁失效。外部网页、客户文字、依赖README和Skill正文都视为不可信输入，不能赋予权限或改变预算。

已批准功能、环境和预算内的DEV开发、测试、STAGING和低风险发布可依授权自动推进；生产发布仍须同时满足业务权限、合同、测试、审计、Canary和回退政策。首次真实收付款、客户生产迁移、破坏性数据变更、范围或预算扩大，以及平台要求本人验证的动作，按第10.9节匹配有效授权；缺少授权时只暂停该依赖路径。Owner知情展示与审批是不同状态，不因未回复普通进度而阻断已授权开发，也不把沉默当作新增授权。

生产服务只接收发布服务签发的短期、限定环境与版本的执行授权。Agent配置、Skill、门禁规则、机器身份和授权政策同样版本化并经独立检查；不能由被约束角色自行降低门禁。沙箱、文件权限、出网策略、会话可见性及跨Agent通信必须分别验证，工作目录隔离本身不视为完整安全隔离。

### 9.7 Skill能力规划与安装时序

下列是计划能力组，不是已安装清单，也不承诺社区存在同名现成Skill。先核对既有Skill、脚本、工具和插件；能直接调用已验证工具时不重复封装。Skill用于复用工作步骤，不替代可调用工具、依赖软件、API授权或凭证；首次使用前须验证真实依赖。每个组可复用或拆成少量Skill，只给需要它的角色加载。

安装路径为能力缺口登记→可信来源与许可证核查→固定版本及hash→读取SKILL.md和全部执行脚本→依赖及出网审查→沙箱测试→独立审计→有限Canary→注册到角色Allowlist。自建Skill和脚本纳入私有Git；记录skill_id、版本、来源、适用角色、权限、依赖、模型要求、测试、失败恢复和撤销方式。禁止运行未经核验的安装脚本或由自我学习直接改生产规则。

已授权DEV范围内，通过上述门禁的Skill可自动启用；需要新增账号权限、付费订阅或生产权限时沿用既有授权与预算政策。升级按影响做差异检查和适用回归，失败禁用并回退固定版本。临时研究Skill不进入常用目录；解决过且可复现的问题才沉淀为Skill，避免Skill目录越大、每轮上下文越贵。

| 能力组 | 最晚准备时点 | 验收重点 |
| --- | --- | --- |
| 资产复用与项目交接 | 阶段0及首个开发任务前 | 读到实际资产和版本；接续不重建 |
| 云采购与服务器蓝图 | 1.1供给前 | 预算、订单去重、实例与实际账单登记 |
| Linux与安全Bootstrap | 1.1初始化前 | 最小身份、网络、SecretRef及重启恢复 |
| Git CI与构建证据 | 1.2至1.4开发准入前 | 保护分支、依赖锁、测试和产物hash |
| 部署 Canary与回滚 | 1.5首次部署前 | 同一产物部署；健康失败能回退 |
| 监控 备份与恢复 | 1.6完成及真实数据进入前 | 状态库恢复、证据可用、故障通知 |
| OpenClaw模型运行时 | 1.7执行及模型切换前 | 身份、模型实测、沙箱和路由评测 |
| 任务协议与事件恢复 | 1.8至1.13自动派发前 | 去重、租约、受控预算及断线续跑 |
| 测试 安全与供应链审计 | 1.4准备；适用代码准入前完成 | 漏洞、密钥、权限、授权及业务回归 |
| API接入与授权管理 | 对应Connector第一次接入前 | 权限有效、撤销停用、超时查证 |
| 支付 分账与推荐对账 | 资金业务动作及推荐开放前 | 确定性计算、核销、退款、成本去重 |
| 内容版权与渠道发布 | 公益视频首个真实发布前 | 素材权利、事实、渠道授权及规则 |
| FinOps与计量 | 首个收费调用或资源消费前 | 用量与账单证据；未知金额不填0 |
| 贡献凭证与治理 | 首次签发或治理开放前 | 证据来源、去重、撤销及权限边界 |


### 9.8 独立测试QA与分层验收

新功能开发前，Work确定功能验收标准，QA据此设计独立用例及风险清单；Developer实现并自测，CI运行确定性测试，QA核验功能、边界、失败恢复和端到端结果，Auditor独立审查安全及关键业务规则。任何被要求的测试缺失、UNKNOWN或失败都不能计为PASS。QA不等于安全审计，也不能由Developer一句自测通过替代。

测试层次覆盖适用的单元与业务规则、接口契约、跨模块集成、端到端、异常及恢复、安全隔离和性能容量。普通修复运行影响范围内回归；新增功能或跨域变更由QA更新验收用例；支付、分账、钱包、推荐、授权与模型切换保留关键回归集。成功后的重复全量测试仅在新变更、失败或未解决风险出现时执行。

工程闭环测试覆盖请求鉴权、越权拒绝、重复派发、旧租约提交拒绝、断线重连、服务重启、事件重放、预算暂停与恢复、取消时的副作用对账、Skill撤销和下一节点推进。正确结果需同时检查持久状态、执行记录和实际副作用数量，不能只看消息返回成功。

资金测试采用经审核的确定性样例，覆盖到账核销、未消费充值不计收入与返佣、毛利30%一级推荐、默认50%实施预算与实际成本、成本去重、部分退款、拒付、四舍五入、跨续费归因及对账。CP收入口径、RS和推荐佣金分开验证。先沙箱及模拟，再按权限进行小额真实Canary；模拟成功不冒充真实支付验收。

渠道与内容测试覆盖授权失效、配额、发布规格、重复提交、未知发布结果查证、版权与事实、指标缺失和未归因。模型测试验证实际调用的provider、model和版本，并比较真实业务用例、工具选择、边界行为、响应质量和成本；只改配置或模型自称不能证明切换完成。具体样例与阈值进入版本化Eval Registry。

性能测试以批准的预期负载确定延迟、吞吐、资源、错误率及队列上限，覆盖长任务和限流；目标未定时不得宣称达到生产容量。备份和灾备必须实测恢复。发布前由QA形成绑定commit、artifact hash、用例集版本、环境、结果和缺陷的报告；Release Gate核验CI、QA、Audit、健康、Canary及回退全部适用证据。缺陷通过测试失败→修复→失败用例复测与影响回归→更新证据闭环解决。

### 9.9 模块商业化从需求阶段纳入工程验收

每项客户定制或自研任务输入均包含模块产品定义、三层边界、市场说明、计量、授权及价格引用。先设计再开发；不等项目末尾才临时改造成可选配模块。

初始实现包含注册、租户配置、受控启停、权益检查、用量事件、升级兼容、文档与套餐映射。最终公开上架测试验证新租户可选配、配置及恢复；私有交付按合同验收，不强制先公开。

QA覆盖开发预付款抵扣、重复验收事件、免费期起算、专属价保护、无授权不扣款、回调幂等、开通失败恢复、续费取消、退款和数据保留，以及跨租户拒绝与专属资料保护。

### 9.10 开源代码复用规范（V2.7新增）

规则编号GITHUB_CODE_REUSE_POLICY_V1，属全局开发规则，适用于SaaS主体框架、模块市场、统一计费、GEO、社区分账、公益视频、AI客服、CRM及未来客户定制开发。原则是优先复用、减少重复开发，同时不降低代码质量、不增加不必要的系统复杂度，不允许无限检索GitHub而消耗模型额度。

开发顺序：①检查玄钧已有代码；②检查已封装的标准SaaS模块；③检查已验证的开源技术资产登记；④判断是否值得检索GitHub；⑤只有确有收益时才检索；⑥选择成熟且许可证兼容的代码；⑦进行最小适配开发；⑧完成测试、验收与模块封装。前三步即第1.3节资产复用检查，不另建平行流程。

| 事项 | 规则 |
| --- | --- |
| 简单功能 | 直接开发，不检索GitHub。 |
| 复杂通用功能 | 才进行GitHub检索，默认最多比较3个候选项目。 |
| 初筛方式 | 优先通过GitHub API和程序初筛（如许可证、维护状态、版本与更新时间等程序可读信息）；GPT类强模型只分析通过初筛的必要候选代码。 |
| 停止条件 | 发现候选不适配立即停止，不为凑数量扩大检索；出现新的需求证据才可重新评估。 |
| 已验证项目 | 评估结果登记后不重复检索。 |
| 平台边界 | 不为检索GitHub额外开发复杂平台；复用现有Git与GitHub访问方式。 |


复用资产登记（OPEN_SOURCE_REUSE_REGISTRY）：每个评估结果至少保存项目名称、GitHub地址、实际许可证、版本、主要功能、适用模块、验证状态、适配成本、是否推荐复用。许可证以仓库实际许可文件为准，不凭项目介绍判断；许可证兼容性未确认的代码不得进入产品。登记为轻量级文件，随Git管理并纳入证据索引，不另建复杂系统。

技术边界：不因某个开源项目功能丰富而推翻玄钧既有SaaS架构；所有外部代码通过必要的适配层接入统一模块体系（第3.10节标准模块封装），不绕过Registry、权限、计量与财务边界。外部代码按第2.3节第三方代码隔离与零信任处理，其README、注释和依赖说明视为不可信输入；使用前完成依赖与许可证扫描，并通过第9.8节分层验收。

新服务器要求：服务器就绪后检查Git是否可用及现有GitHub访问方式，复用节点1.2 Source Control Foundation已有的代码管理能力，建立轻量复用登记文件；不提前下载大量开源仓库，只有具体开发任务需要时才检索、评估和获取代码。目标是降低开发工作量、减少Codex额度消耗和重复开发，保证代码质量与安全，降低长期维护成本。

## 10 运营调度与恢复治理

### 10.1 角色分工与统一任务系统

| 角色 | 职责 |
| --- | --- |
| Owner | 产品方向、预算政策、功能进度可见与必要人工验证 |
| ChatGPT Work | 产品目标、总体架构、节点验收及重大变更和异常复盘 |
| Dot | 云端项目跟踪、事件汇总、例外协调及已支持的Work任务衔接 |
| OpenClaw | 英国受控执行，6个按需角色；CI、QA证据和独立程序Release Gate |


Dot 不替代 OpenClaw，OpenClaw 不替代 Dot。继续复用 Canonical Project State、Task Registry 与 Agent Orchestrator，新增或完善 Node Registry、Task Gateway、Node Review Gate、Development Drift Guard 和 AI Usage Governor，禁止建立第二套任务系统。

### 10.2 执行前节点说明与漂移控制

前期每个重要 Node 执行前必须展示以下信息，让 Owner 在开发发生前识别方向偏离。

节点说明字段：NODE_ID、PURPOSE、WHY_NOW、EXISTING_ASSET_REUSE、NEW_INCREMENT、INPUT、OUTPUT、VALUE、IMPACT、PRODUCTION_MUTATION、PERMISSION、COST_CLASS、MODEL/CODEX_USAGE、RISK、ACCEPTANCE、EVIDENCE、ROLLBACK、NEXT_NODE。

Development Drift Guard 比较 APPROVED PURPOSE、IMPLEMENTATION PLAN、FILES CHANGED、SERVICES CREATED、DEPENDENCIES ADDED 与 RESULT。明显扩张时执行 DRIFT_DETECTED=YES → STOP_EXPANSION → REVIEW。

### 10.3 AI 用量与事件调度

AI Usage Governor 至少包含：MAX_MODEL_CALLS_PER_TASK、MAX_MODEL_CALLS_PER_NODE、MAX_CODEX_CALLS_PER_NODE、MAX_RETRIES、MAX_AGENT_DEPTH、MAX_PARALLEL_HEAVY_TASKS、MAX_CONTEXT_SIZE、TASK_DEDUPLICATION、NO_AGENT_RECURSION、NO_LLM_POLLING。

OpenClaw 完成任务 → Event → Dot Wakeup。禁止 Dot 不断调用 LLM 询问任务是否完成，禁止无必要轮询和 Agent 递归；通过任务去重、调用上限、重试上限、上下文和并行深度限制控制成本。

V2.7补充：AI Usage Governor各限额的取值方法、任务分级、上下文分层、额度来源分账与成本度量按第10.18节配置；该节不改变上述限额项目，只规定如何取值与度量。

### 10.4 检查点与暂停恢复

所有长任务必须保存 Checkpoint。人工验证路径：HUMAN_VERIFICATION_REQUIRED → SAVE CHECKPOINT → SKIP DEPENDENT PATH → CONTINUE OTHER WORK → HUMAN COMPLETE → RESUME。

Codex 额度不足路径：RESOURCE_LIMIT → SAVE CHECKPOINT → PAUSE → RESUME LATER。暂停后从保存位置续跑，禁止重新从头执行。

### 10.5 可观测性与健康检查

统一建设 Structured Logging、Metrics、Health Check、Alerting，并按规模逐渐增强 Tracing。健康检查包含 LIVENESS、READINESS 与 DEPENDENCY_HEALTH。

Metrics 覆盖：Availability、Latency、Errors、Queue、CPU、Memory、Disk、Network、Model Calls、Tokens、Cost、Retries、Deployment Health。

### 10.6 备份与恢复验证

GitHub 不是唯一备份。

备份覆盖对象：Repository Mirror、Database、Configuration、Artifact、Canonical State、Task Registry、Module Registry、Finance Ledger、Infrastructure Metadata、Critical Evidence。

必须定期执行 BACKUP_RESTORE_CANARY。备份有效性需要 Backup 与 Successful Restore Test 共同证明，不能只以备份文件存在作为完成依据。

### 10.7 跨渠道经营指标与服务改进

建立BUSINESS_METRICS_CENTER板块，复用Channel Adapter、CRM、Usage、Finance、Workflow和Solution Graph。目标是从授权渠道与内部系统取得经营证据，持续跟进、综合分析、生成并执行符合策略的改进任务；不创建第二套CRM、资金账本或发布系统。

#### 10.7.1 采集与数据质量

按渠道建立METRIC_CAPABILITY_PROFILE，区分公开可读、需授权、需额外审核、仅客户导出及不可获取。优先官方API和Webhook，补充经许可的客户CSV导入；不以网页抓取推导任意经营数据权限，不预设所有渠道都有播放、点击、成交或收入API。渠道接入不能自动获得经营指标读取权。

METRIC_FACT至少记录tenant_id、channel_account_id、content_id、campaign_id、metric_name、metric_definition_version、time_window、timezone、currency、source、fetched_at、event_time、raw_value、quality_status、permission_status、attribution_model和source_evidence。保留原始快照和标准化投影；UNKNOWN、NOT_SUPPORTED、STALE与真实0分开显示。

渠道曝光、播放、互动、粉丝、点击按平台原定义保存；不同平台的观看阈值和互动口径不可强行当同一指标比较。累计值与期间增量分开，迟到数据回补，Webhook及周期快照幂等去重。采集失败、Token撤销、限流或Schema变化触发告警和有限退避，不把失败值写0。

#### 10.7.2 综合分析与权威归因

经营漏斗为内容触达→落地页访问→线索→试用/演示→首付→实际消费→收入确认→毛利润→返佣后贡献→续费。平台事件、UTM/链接/邀请码、客户授权CRM和Finance事实关联；不能关联的成交保留未归因，不能因时间接近就认为内容带来订单。推荐绑定用于佣金权利，营销首次/末次触达用于效果分析，两者不相互覆盖。

板块展示渠道与内容效果、合格线索、付费转化、CAC、激活与首次价值时间、客户交付/支持工时、失败率、单位任务成本、净收入、毛利润、推荐支出、返佣后贡献、续费和退款。交易流水与平台收入分别展示；钱款和利润只读Finance权威事实。收入按账期匹配，费用按受益范围归集，不重复把佣金计入获客成本和同一贡献指标。

AI报告引用证据、缺失范围、样本量、比较周期、基线和置信程度。相关性不作为因果证明；增长变化先核对埋点、季节性、平台口径和价格变化。不能把增加播放量作为唯一优化目标，目标必须同时约束客户结果、质量、安全、成本和投诉。

#### 10.7.3 自动改进的执行链

链路：COLLECT→VALIDATE→ANALYZE→HYPOTHESIS→CHANGE_PLAN→POLICY_CHECK→EVAL→CANARY/EXPERIMENT→MEASURE→KEEP_OR_ROLLBACK→SOLUTION_EVIDENCE。每个改进记录improvement_id、baseline、hypothesis、expected_metric、guardrail、sample/window、change_version、budget、owner、approval_policy、result和rollback。自动化先有可测基线，后有动作权限，不能让AI直接改所有服务。

低风险允许在已授权范围内自动调整内部素材标签、重复任务去重、既定额度内的失败重试、已批准内容队列的候选排序或排程建议；实际发布仍受渠道确认与既定发布策略。中风险如提示词、模型路由、客服知识和内容模板改动，必须通过AI Eval、小范围试验与可回滚门禁，只有预授权策略明确允许才自动发布。

高风险价格、合同、30%永久返佣、推荐归属、财务分录、支付/退款、客户权限、数据保留、生产代码和外部广告预算扩张不得由分析模块直接修改；生成任务交由原有审批、工程或Finance链处理。本模块无Finance Write和权限扩张权。

试验预先确定主要指标、样本和观察期，避免每天查看后提前认定成功。设置成本、错误率、投诉与关键业务正确性止损条件；样本不足保持待观察，不无限试验。预算耗尽保存checkpoint，失败回滚到已验证版本。每周形成经营复盘，每月形成单位经济和服务产品化复盘，日常异常事件驱动跟进。

#### 10.7.4 模块验收

至少完成一个获授权真实渠道加CRM和Finance的端到端Canary，证明数据回补去重、口径对齐、未归因保留、UNKNOWN不写0、跨租户拒绝、权限撤销停采、日报可追溯，以及一个低风险改进的基线、执行、效果和回退证据。其他渠道逐个标记覆盖范围，不以单一渠道通过代表全球支持。

### 10.8 ChatGPT Dots与OpenClaw连接协议

ChatGPT负责需求、架构与审查，Dot负责项目跟踪、已授权节点派发及例外协调，OpenClaw负责受控执行；Canonical与Task Registry持有任务真值。通过适用插件或远程工具入口封装已有Task Gateway，先验证当前账号和执行环境实际支持的连接方式，不把远程服务器描述为默认已经接通。

统一任务契约至少包括task_id、project_id、node_id、tenant_id、actor、goal、scope、input_refs、dependency_refs、policy_version、authorization_ref、budget_ref、idempotency_key、deadline、callback_ref和expected_result_schema。结果包含status、source_commit、artifact_refs、test_refs、cost_events、evidence_refs、checkpoint、blocker、next_node与completion_event_id。凭证只传SecretRef引用，不传密钥明文。

入口支持鉴权、工具与项目Allowlist、角色权限、请求校验、签名或等价完整性保护、过期及重放防护。读取状态、创建任务、取消任务、采购意图和发布意图分别授权；不得提供可绕过门禁的任意生产Shell入口。授权绑定任务范围、版本和预算，不能复用到不同采购或发布。

异步请求先返回task_id，再以持久队列执行。统一状态为PENDING、RUNNING、WAITING_APPROVAL、WAITING_EXTERNAL、PAUSED_RESOURCE、SUCCEEDED、FAILED或CANCELLED。使用lease与超时恢复保证同一任务同一时刻只有一个有效执行者；重复请求返回原任务。外部副作用使用独立幂等意图，不宣称网络调用天然只执行一次。

Completion Event包含事件ID、任务ID、结果版本和证据引用。事件写入持久outbox，回执确认前可重发，接收端按事件ID去重；断线重连先对账和恢复未完成任务，再推进Next Node。机器健康检测和有限状态查询可执行，LLM不持续轮询。Dot或聊天暂时不可用时已部署服务继续按既定策略运行。

首个连接Canary选择低风险小功能，证明请求鉴权、创建及去重、断线恢复、结果回传、独立测试审计、发布证据和下节点推进。异常情况下不重复采购、发布或付款；当前无法建立连接则登记准确blocker，不将手工转发标记为自动闭环。

### 10.9 长期授权可靠性与真实成本

自动化动作由AUTHORIZATION_POLICY统一管理，按项目、动作、环境、数据范围、金额、期限和例外定义。已有效授权且满足门禁的重复动作自动执行；Owner掌握预算、政策和例外处理，不按每个命令重复审批。平台或客户要求的确认、超出授权范围和资金风险例外按已有Workflow处理。

持续业务运行由服务器上的持久服务、任务队列、定时器和状态库承接。内容制作、发布、CRM跟进、订单交付和财务核销分别为受控工作流；英国工程控制面发布验证后的版本，Dot协调节点和例外。聊天窗口、个人电脑、浏览器前台及单次模型对话不成为正常生产运行依赖。

自动化可降低重复劳动和新增客户的边际投入，但人工审核、客服例外、接口申请、版权、故障处理、云资源、模型、支付、分发和维护成本均归集。管理人工不重复计入订单直接成本；订单实施工时按第6.7节计入。内部项目也记录成本，不以自动化为由记为0。

发布、采购、付款和客户通知采用幂等、去重、限额、超时查证及熔断。连续失败停止重试并保存checkpoint，按照已配置责任人和通知策略报告；数据未知、供应商中断或模型异常时进入降级模式。预先测试回滚、备份恢复与撤销授权，不用低价替代容错设计。

每项目设置自动成功率、人工介入次数与分钟、首次价值时间、第二次交付工时、支持工时、直接成本、返佣后贡献和恢复时间。每周期同时记录分子分母与观察期。扩张依据人工投入与单位经济实际下降且质量稳定，不以任务执行次数或AI生成量证明无人化。

### 10.10 人工 Work Dots与英国控制面的职责

Owner确定产品方向、资金预算、业务政策和必要人工验证，并查看节点功能与真实进度。Work将目标转成版本化的范围、接口、依赖图和验收标准，处理重大架构变化及反复失败；不在每个成功步骤重复审阅同一方案。Dots持续跟踪责任、汇总事件、协调例外，并在已支持的方式下创建或继续Work任务。英国OpenClaw与6个按需角色执行批准的任务；英国控制面保存权威状态，交付后的生产服务按既定策略独立运行。

Dots运行在其云端环境，英国服务器部署的是Dot连接适配器、Task Gateway和状态服务，不假定可在英国自行安装Dots本体。Work与Dots能访问的插件、远程工具、事件及后台任务必须以当前账号实际能力为准。仅打开SSH或登录网页不能证明闭环；原始SSH、浏览器模拟和人工复制不作为正常生产调度链。

优先采用当前账号可用且获准的插件或MCP工具封装Task Gateway。先验证get_project_state、create_task、get_task_result和接收事件；自建入口必须通过连接、权限及端到端测试。Dot触发Work任务优先用其支持的任务能力，不假定OpenClaw能够通过任意Webhook直接启动当前Work会话。英国也不把Pro订阅视为无限API预算；ChatGPT授权入口、Codex入口与API付费凭证分别登记和验证。

### 10.11 单一任务图与自动开发循环

完整循环为Owner目标→Work范围与验收→批准的Node Graph→Owner功能卡可见→Gateway核验依赖、授权及预算→OpenClaw执行→程序CI与独立审计→Release Gate→STAGING及适用Canary→证据和权威状态提交→完成事件→Dots或本地调度器推进已批准下一节点。常规成功不额外唤起Work；重大偏离、两次同因失败或业务判断才提交Work诊断。

Dots协调项目级目标，英国Coordinator处理节点内队列，统一共享Canonical与Registry；每个节点只指定一个派发者。默认由英国受控调度器推进已批准的就绪任务，Dots提出变更或处理例外，不能同时抢派同一节点。Gateway采用状态版本比较、唯一task_id、幂等键、有效lease和fencing token阻止旧执行者提交；外部副作用仍按第10.8节查证和去重。

节点工程阶段单独记录QUEUED、DESIGN_READY、IMPLEMENTED、CI_PASS、AUDITED、STAGING_PASS、CANARY_PASS、DELIVERABLE。任务执行状态继续使用10.8节枚举；节点受阻记录reason与依赖，不重复创造一套任务终态。SUCCEEDED表示该任务验收完成，不等于对应功能已获渠道权限或已正式上线。完成事件与状态在同一可靠提交路径写入outbox，失败重发不触发重复采购、发布或付款。

Work读取证据时只接收目标、输入版本、变更diff、失败片段、已尝试项和证据索引；源码和完整日志按需读取。每次交接标明项目、节点、版本、当前阶段、唯一blocker与下一动作。聊天记录与Dots记忆作为辅助，Canonical状态、Git及服务证据为准。功能完成后写回Module或Connector Registry、测试、运行手册和Skill候选，而非再造第二套后台。

### 10.12 Owner进度看板与通知规则

Owner看板复用1.9 Node Registry和1.10 Owner Review，首版只做一个受身份保护的项目页面。展示当前里程碑、正在开发的中文功能、为何现在做、可用范围、已验收阶段、下一节点、阻塞及需要Owner的动作。节点展开可看验收清单、commit、测试结果、产物、部署环境、Canary、回退点、费用和最近证据时间。已规划、已开发、已验证、可正式交付分别显示。

重要节点开始前写入中文功能卡，说明功能、客户价值、已有资产、新增范围、影响、成本和验收；已批准范围内按计划推进，不要求Owner逐命令确认。演示截图或视频用于辅助理解，技术门禁仍读取真实证据。进度按里程碑验收项及明确分母显示，不以AI输出字数、Agent轮次或提交数量计算百分比；节点权重在基线固定，新增范围需记录变更。

通知策略由Owner登记渠道和频率后执行：正常进展按节点完成或摘要窗口合并；超预算、权限撤销、生产故障和必须本人验证立即通知对应例外。通知内容采用功能、阶段、本次结果、剩余问题、费用与下一步六项，避免倾倒日志。英国服务先记录notification intent；实际发送以当前渠道权限为准。本文件仅规划通知，不等于已创建定时任务或已向外部渠道发消息。

看板显示Work、Dots、Gateway、OpenClaw和生产服务各自连接状态及最后成功时间。未知记UNKNOWN，不能用其他项目PASS替代云汇证据。Owner可暂停项目、暂停节点、改优先级、调整预算和取消未执行任务；取消停止新增派发，执行中的外部动作按安全边界处理并对账，不假定已产生副作用可撤回。

### 10.13 额度 并行与故障升级

建议首期同时运行不超过2个重任务，初始spawn深度不超过1，由Coordinator直接分派，子角色不能递归招募。这属于运行初值，真实CPU、内存、磁盘、模型限额和队列数据确认后调整；注册6个角色不代表服务器能同时承载6套构建。共享资源和同一数据库迁移串行，独立只读检查或不冲突工作树可并行。

先由脚本完成状态查询、格式、测试、健康检查、扫描、额度计数和通知拼装；模型用于需求、设计、开发、独立审查及异常判断。架构和高风险变更使用经评测的强模型；摘要和分类可用经评测的低成本模型；任务权限与费用不能由廉价分类器最终决定。按项目记录真实模型与入口，不未经评测强制切换。

每任务配置max_model_calls、max_tokens、max_cost、max_runtime、max_patch_attempts及resource_limits，并继承节点和项目剩余额度。预算预留、已消费、未知待对账和未来承诺分别记录；并发任务不能各自使用完整项目余额。价格或订阅余量无法权威读取时保留UNKNOWN，采用调用和时间上限，不填假成本或假重置时间。客户资金、生活资金、债务预算和其他项目预算不自动互相填补。

建议单一问题初始自动补丁上限为3次；相同失败指纹连续出现2次时暂停重复补丁，把证据包交Work复盘一次。指纹覆盖服务、版本、错误类别及关键堆栈；无新证据不得原命令重跑。修复次数计入原任务总预算，创建子任务不能刷新额度；达到限制转PAUSED_RESOURCE或对应受阻原因，待策略允许后从checkpoint恢复。生产健康变差时优先按授权回退到已知版本，再分析，不边故障边无限重构。

新增角色必须有持续积压、清晰隔离职责和可测量收益。前20个实际完成节点用于基线观察；测试与审计持续成为瓶颈时可按业务域扩展QA或增加专项验证角色，内容质量或数据分析形成持续业务队列时再启用专业角色。QA不能取代独立安全审计，运营Agent不默认加入工程调度树；判断依据是交付时间、返工、安全结果和每个验收节点的额度成本，而非固定追求7个或8个。

V2.7补充：本节的补丁上限与相同失败指纹连续2次暂停的规则保持不变，即同一失败原因在一次有依据的针对性修复后仍失败，任务即暂停并保存现场；失败指纹不同且有实际进展时，才在3次总上限内继续。只有出现新的独立证据，才可形成新的明确修复任务，且仍计入原任务总预算。额度不足时的暂停顺序见第10.18.4节。

### 10.14 脱机运行与控制面恢复

Work或Dots离线时，英国调度器可继续执行已批准、依赖就绪且预算有效的任务；遇到新设计、范围变化或不可自动解决的例外保存检查点并等待。额度不足只暂停模型步骤，已部署业务、监控、备份和已授权确定性任务继续运行。Gateway不可用时不接受新意图，本地已持久化任务按lease政策执行；恢复后先核对状态和副作用，再补发事件。

首期英国控制面可以单机，明确存在单点故障；通过异地加密备份、状态和证据恢复脚本降低恢复风险，不把单机写成高可用。初始建议工程控制面RPO不超过24小时、RTO不超过4小时，必须以演练实测确认后才作为承诺。生产资金账本另行确定更严格目标，不能沿用工程目标。恢复演练验证队列、lease、Git、Artifact、SecretRef引用、政策版本和重复副作用防护。

### 10.15 Owner对话与工作调度

币安运维环境和云汇开发环境分别配置Owner对话调度角色。优先复用已有主Agent并调整路由与职责，不机械新增两套核心。该角色负责快速沟通、理解任务、分派、进度汇总、人工节点及异常升级；长时间开发、测试、审计交给相应执行角色。

对话入口与执行任务采用独立会话、异步队列和容量预留，不能因一个长工具调用阻塞Owner新消息；仅增加Agent名称而复用同一阻塞队列不算完成。先检查安装版本真实并发与路由能力，无法满足时明确限制并给出最小修复。

正常可用条件下以10秒内发出接收回执、60秒内给出任务ID或明确阻塞为设计验收目标，而非已达成承诺。回执只说明收到，不伪装任务完成。Owner随时可查状态、追加约束、暂停或取消，变更合并到原任务契约。进行中的关键原子操作在安全检查点响应暂停。

任务分派包含目标、范围、权威输入、权限、预算、依赖、验收、截止或超时及回滚。独立任务并行，有冲突写入或依赖顺序时串行；执行角色按需唤起，保留独立QA，不固定Agent数量，不让Owner对话角色长时间包办开发。

按阶段和异常推送简短进度，无变化时不反复耗模型轮询。任务lease、心跳与超时由程序处理；无回执、worker失联、预算不足或权限阻塞进入明确状态并通知Owner。保存checkpoint后续跑，禁止无限重试与无限Agent递归。

验证以后台运行长任务期间连续发送Owner消息为主，检查接收与响应延迟、分派证据、状态查询、取消、worker失败与恢复，以及资源成本；仅单次空闲聊天通过不足以验收。配置实施属于后续运维任务，文档更新不等于已配置。

### 10.16 Owner与客户可视化工作台

复用Admin Console Framework交付Owner管理面板和客户工作台，各模块通过页面、动作、权限、指标注册，不按行业另建后台。客户可通过对话或面板操作同一任务、同一配置和同一账本，修改均有权限校验与版本冲突保护。

Owner面板显示项目节点、真实进度、任务与Agent状态、人工待办、发布与回滚、资源、成本及异常；可管理板块、套餐、价格版本和权限。平台管理员不默认获得客户交易决策权，也不得手改余额或账本事实。

客户面板显示已购板块与权益、配置、连接状态、部署位置、任务、用量、双币费用、余额、账单、预算、通知、数据导出与退出。金融页增加策略版本、模拟结果、订单、持仓、风险、暂停与授权撤销。实际交易数据来自权威提供方，不显示模型猜测。

面板按租户和角色隔离，敏感凭据仅显示状态与掩码；提供手机版适配、必要的二次确认和失败反馈。删除、采购、改价、实盘授权等关键动作保持既有权限与审批，不因可视化界面绕过门禁。

### 10.17 到期与安全退出

订阅、预存预算及服务器到期分开管理。到期前通知客户，停止新付费任务或新开仓按约定执行；不得直接停机遗留无法管理的持仓，也不得无授权替客户平仓。明确保护订单、有限交接期、客户接管、凭据撤销和数据导出，续费策略受客户预算约束。

### 10.18 Codex与模型额度节约运行方案（V2.7新增）

目标：在不降低关键任务质量的前提下，减少无效模型调用、重复上下文、重复审计、重复开发、无依据重试、Agent间重复分析和方向性错误。判断优化是否有效，以“每个验收通过任务的总成本（COST_PER_ACCEPTED_TASK）”为准，含返工、重试、人工介入与等待；不只比较单次调用或每百万Token单价。不以降低模型版本换取表面节省，可调节的是推理强度、上下文范围和重复工作。

额度浪费有两类来源：执行层面的重复与循环，以及上游决策层面的方向错误与过度复杂。后者影响更大，因此本节把方向核验放在第一位，再处理执行层控制。

| 浪费来源 | 控制措施 | 落点 |
| --- | --- | --- |
| 方向错误：先认证、先开发，后发现核心需求无法满足 | 方向与关键限制前置门（10.18.1） | 10.18.1 |
| 重复审计、重复开发 | 任务指纹与TASK_DEDUPLICATION；开发前先查Canonical State与证据索引；同版本且已PASS的审计无新证据不重跑 | 1.3、10.3 |
| 上下文重复发送 | 稳定前缀＋权威摘要＋任务快照＋按需证据；日志先由程序过滤 | 10.18.3 |
| 无依据重试与循环 | 失败指纹、补丁上限、同指纹暂停、保存现场 | 10.13 |
| 确定性工作交给模型 | 计算、状态、校验、统计、日期判断由程序完成 | 9.5、10.13 |
| Agent重复分析 | 单一任务负责人；专业执行者只接收明确任务、已确认接口和验收标准 | 9.5 |


#### 10.18.1 方向与关键限制前置门（DIRECTION_AND_CONSTRAINT_GATE）

凡涉及付费认证、采购、第三方平台接入或新开发路线，必须先按顺序完成：业务需求→平台或供应商能力核实（以官方资料为准）→关键限制检查→最小真实验证→确认可行后，才可付费、认证或正式开发。接口能够接通与满足业务体验是两项独立验收，不能互相代替。

每个此类决策形成一页决策记录：核心需求、已核实的能力与限制、验证证据、结论（GO、NO_GO或NEED_EVIDENCE）及停止条件。企业微信方向出现的偏差是设立本门禁的实际教训。

发现既有方案不满足核心需求时必须立即报告：方案错在哪里、应当停止什么、最短纠正路径是什么；已投入部分记为沉没成本，不为维护原判断而继续追加投入。同时遵守不擅自扩大任务范围：执行时只完成Owner已确认的目标，范围变化走变更流程。

#### 10.18.2 任务分级与推理强度

| 任务类型 | 执行者 | 推理强度 | 说明 |
| --- | --- | --- | --- |
| 与Owner快速沟通、状态查询 | 强模型 | 低 | 立即返回TASK_ID或进度，不同步执行长任务 |
| 理解新需求、确定范围 | 强模型 | 中 | 读取相关蓝图与现状，不重新设计整体体系 |
| 已明确的代码修改 | 强模型 | 低至中 | 只读相关文件与测试 |
| 普通模块开发 | 强模型 | 中 | 按需读取代码与接口 |
| 总体架构、复杂模块设计、复杂故障、财务/权限/安全关键审核 | 强模型 | 高 | 保留完整证据；极高强度须在节点说明中写明理由 |
| 日志筛选、JSON整理、佣金与到期计算、服务状态、测试统计 | 程序 | 无 | Decimal、SQL、Git、Schema校验器、Linter、测试程序、规则引擎 |
| 分类、摘要、索引 | 规则程序或经评测的低成本模型 | 按评测 | 不得决定权限、费用、资金与安全授权 |


降低推理强度不等于降低模型版本。财务、支付、客户权限和生产部署相关任务不因额度不足自动降级；额度不足时按10.18.4暂停低优先级任务。业务代码仍调用Model Router角色（第4.1节），不写死具体模型名；具体模型、价格与缓存规则以MODEL_PROVIDER_RATE_CARD和官方资料为准并保存核验日期，本节不写死价格或额度数字。

不采用“一个强模型指挥、大量廉价模型写代码”的默认方案：理解偏差会引发返工与重复测试，反而增加总成本。当前以少量强Agent配合确定性程序为准，新增角色须满足第10.13节的持续积压、隔离职责和可测收益条件。

#### 10.18.3 上下文分层与缓存

分层读取：稳定前缀（规则、工具定义、角色指令，版本化并保持稳定）→权威项目摘要（PROJECT_MANIFEST、TASK_STATE、MODULE_REGISTRY摘要）→当前任务快照→按需证据（相关文件、日志片段、测试摘要）。不默认加载全部项目历史，新任务直接读取状态，不重读整个聊天记录。

任务快照字段：项目、架构版本、TASK_ID、目标、已确认事项、已完成事项（引用证据ID）、本轮需读取的文件、本轮禁止事项。摘要中的“已完成”必须能追溯到代码、测试结果和部署证据，不能单凭一句“完成”作为证明。

日志与工具：日志先由程序过滤，模型只读取关键错误、必要上下文、相关配置和测试摘要；能由一个脚本或批处理一次完成的操作不拆成多轮往返，但仍须满足授权、回滚与门禁要求。

缓存：仅在正式API且供应商支持时启用评估；稳定内容放前、动态内容放后，保持工具定义与公共前缀稳定，相关任务集中执行；记录输入、缓存命中、缓存写入、输出与推理Token及费用（字段以实际接口返回为准）；先裁剪不必要的上下文，再优化缓存，不为命中缓存而无限扩大上下文。ChatGPT或Codex订阅入口的缓存与额度规则不假定与API相同。

裁剪边界：预算是告警与调度机制，不是对关键证据的截断。任何裁剪都不得导致合同规则、安全边界、财务规则及当前任务关键证据丢失。

#### 10.18.4 额度来源分账与暂停顺序

每台服务器和每个Agent登记实际认证方式：ChatGPT或Codex套餐额度、OpenAI API按量费用、其他供应商额度。三类额度互不填补，新增服务器不等于新增额度；不跨业务借用其他项目的模型额度。无法通过官方接口读取的剩余额度与重置时间标记UNKNOWN，不伪造数值。

额度不足沿用第10.4节路径：RESOURCE_LIMIT→SAVE CHECKPOINT→PAUSE→RESUME LATER。暂停按优先级从低到高：探索研究、一般开发、阻塞主线节点的开发、客户已付款交付、生产故障处理；确定性程序和已部署业务不受影响。恢复后从检查点继续，不重做已完成开发。

#### 10.18.5 成本度量与节约目标

| 指标 | 用途 |
| --- | --- |
| COST_PER_ACCEPTED_TASK | 每个验收通过任务的总成本，核心指标 |
| 首次验收通过率、返工与修复次数 | 衡量质量与来回绕圈 |
| 重复工具调用与重复审计拦截次数 | 发现无效工作 |
| 方向变更次数（因方向错误停止的任务数） | 衡量前置门是否有效 |
| 每Agent、每任务、每节点Token与费用 | 定位异常消耗 |
| 缓存命中率（接口可得时） | 判断重复上下文是否被计费 |
| 额度状态 | 可读取则展示，否则UNKNOWN |


上述指标接入第10.12节Owner看板及节点1.13、1.14。下列为需要验证的管理目标，不是已实现效果，也不是供应商承诺；以前20个实际完成节点作为基线观察。

| 事项 | 初期目标 |
| --- | --- |
| 重复全量审计 | 减少80%以上 |
| 无依据的修复循环 | 原则上消除 |
| 重复读取大型文件 | 减少50%以上 |
| 同一问题多Agent重复分析 | 减少70%以上 |
| 关键任务验收成功率 | 不低于优化前 |
| 单个验收通过任务的总成本 | 争取降低30%至50% |


#### 10.18.6 模型升级验证

新模型进入生产前，选择20个以上真实代表性任务测试，覆盖复杂架构、普通代码、复杂故障、权限与安全、财务规则、模块封装、订阅计费、文档理解、长上下文和异常恢复，并与当前模型的可比任务对照。记录首次与最终验收成功率、总Token、实际费用、执行时间、工具调用次数、人工介入与返工次数。验收成功率明显下降时，不因价格较低而采用较弱模型。

更换模型前先验证其要求的接口形式（例如工具调用所用API）与现有适配器兼容，不能只替换模型名称。未完成真实配置验证前，不声明新模型生产可用。东京币安生产配置保持不变，不为节省额度直接修改交易执行、客户生产模型路由或财务生产链路。

## 11 方案知识与长期演进

### 11.1 企业方案知识图谱

XUANJUN ENTERPRISE SOLUTION GRAPH 是长期数据资产，将客户需求、实施选择、实际成本、故障与效果连接为可复用证据。

记录范围：什么企业、什么行业、什么规模、什么问题、原来什么系统、选了什么Module、用了什么Connector、什么Provider、什么服务器、什么配置、实施时间、真实成本、真实售价、发生什么故障、最终效果、后续新增什么需求。

每完成客户必须产生：NEW_SOLUTION_KNOWLEDGE、NEW_COMPATIBILITY_EVIDENCE、NEW_COST_EVIDENCE、NEW_DEPLOYMENT_PATTERN、NEW_FAILURE_KNOWLEDGE、NEW_REUSABLE_ASSET。

### 11.2 需求驱动的产品化循环

产品化循环：CUSTOMER REQUIREMENT → EXISTING ASSET SEARCH → GAP → QUOTE → CUSTOM DEVELOPMENT → TEST → AUDIT → PRODUCTION → REUSE CLASSIFICATION → PRODUCTIZATION → MODULE / CONNECTOR / WORKFLOW / PACKAGE → MARKETPLACE。工程安全门禁按第9章执行。

更多客户带来更多 Module、Connector 与成熟 Package，减少后续定制、缩短交付时间并降低单客户成本，为提升 Margin 和 Marketplace 能力提供基础；效果应由实际成本和交付证据验证。

### 11.3 Web3 与元宇宙的演进边界

元宇宙不建立第二套经济、身份、产品或贡献数据库；它是玄钧现有Enterprise Solution Graph、Creator/Developer Identity、Product Provenance、Contribution、Reputation、Credential和AI Agent的空间化/3D交互层。

未来映射关系：Creator/Developer → Avatar/Studio；Organization → Digital Enterprise Space；Module/Micro Tool/Package → Digital Product/Object；Marketplace → Spatial Marketplace；AI Agent → Interactive Digital Agent。

元宇宙中的等级、徽章、展厅、创作历史、产品采用量等必须来自现有权威Ledger/Registry/Graph，不允许在3D层另造不可对账的数据。

前期完成WEB3_READY，不以Blockchain/Token/3D为业务前置依赖；后续按真实规模、合规条件和客户价值逐步启用Credential、可选链上证明、DID、Spatial Interface。

### 11.4 首批方案与联合套件

首个确定性企业方案是公益商业支付解决方案，包含商户、接入审核、支付、分账、公益项目、对账、广告和后台管理；首个 AI 原生企业方案是公益内容引擎，包含素材、视频分析、AI 内容导演、对话式编辑、文案声音字幕、渲染、审核、发布和分析。两者按阶段5和阶段6顺序推进，逐次验证并产品化。

PUBLIC_WELFARE_DIGITAL_OPERATIONS_SUITE 组合两套已验证能力，共用 Foundation、Registry、Finance、Workflow、Admin 与 Channel。Content Engine 仅能读取 APPROVED_PUBLIC_DATA，禁止修改 Finance、Split 或 Charity Amount，禁止读取无关 Sensitive Ledger。

### 11.5 壁垒所需的可复用证据与资产

壁垒按工程资产建设，不以模型接入、模块数量或账号数量代替竞争优势。SOLUTION_EVIDENCE_PROFILE记录行业问题、客户授权范围、输入输出、连接器、规则版本、实施时间、复用比例、任务成功率、成本、毛利润、客户效果与失败恢复。

优先沉淀行业工作流模板、渠道准入与兼容矩阵、可重放验收数据、版本化评测集、真实成本曲线、可复用部署蓝图和服务改进策略。客户退出提供合同约定的数据导出、授权撤销与迁移；长期留存应依赖交付价值和可信经营，而不是隐藏数据或阻止迁移。

定制产品化前核对客户IP与数据授权，分离通用能力和专有配置。每次完成项目更新Solution Graph，量化第二次交付工时是否降低、复用是否提高、效果是否稳定；未形成这些证据时，对外只称设计优势，不称已建立市场壁垒。

### 11.6 中国先行的市场与产品验证

全球自媒体矩阵是长期方向，首版优先中国市场的一类客户、一个明确问题和两条可获准渠道。先用自营项目验证素材→审核→获准发布→授权线索→CRM→选品→报价→收款核销→交付→持续使用的闭环，再将成功流程提供给客户。内容可以先采用现有允许工具与草稿交付，不等待自建全部内容能力。

社区分账与公益视频的第一批试点优先选择已有真实接触、资金路径和素材授权可核实的组织。明确使用者、付款者、受益者、采购预算和验收责任；公益叙事不能代替付款意愿。先验证3至5个限定范围付费试点，再邀请5至10位匹配客户群的推荐伙伴；这些数量为建议验证规模，不构成成交或工期承诺。

营销内容以具体问题、真实操作、可核实案例和教程为主，每条连接对应方案与下一步。账号数量随可持续素材、授权、交付和支持能力增加；不先铺大量同质内容账号。渠道发布条件按3.5节执行，推荐关系按6.6节固定，营销最后点击不覆盖既有永久关系。

扩展新地区前建立地区就绪记录：语言、本地案例、账号准入、API动作、数据条件、收付款、税费处理、成本、支持、退款和续费。以重复交付、正向返佣后贡献、渠道验证、结算一致和持续使用作为进入条件；一次成交或短期流量上涨不视为全球模式成立。

### 11.7 本地工具与推荐的转化路径

1元起工具承担试用、需求验证和交付展示，优先选择与后续方案相关且本地无调用成本的素材整理、文件处理或内容检查类功能。公开价格、设备授权、版本支持和边界；优惠试用和拉新补贴单独预算，不以遗漏支付、支持或更新成本维持低价。

统一漏斗为访问→购买→下载→激活→实际使用→需求沟通→标准方案购买→续费或合格推荐。关联获授权来源与客户身份，同时记录退款、支持成本及各阶段转化分母；不存在真实使用时不以下载量作为成功。推荐资格不要求购买工具或付费入会，不计入招募下级奖励。

推荐入口提供规则、典型毛利润演算、适合客户、范围限制和透明后台。先验证伙伴带来的有效客户、首次成交、60至90天持续推荐与结算纠纷，再扩大伙伴网络。实施由玄钧或另签合同的服务方承担，不要求推荐人免费实施；长期收益只展示实际确认或明确标注的假设。

### 11.8 AI需求开发与内容项目扩展

需求先记录问题、频率、现有替代、目标用户、输入输出、数据权限、预算和验收标准。先搜索既有资产再执行配置、扩展、连接器、工作流或新模块。重复需求、可复用性、可交付权限、维护成本和付费意愿作为优先级依据；客户专有需求保留专有配置，不强行产品化。

自动报价明确标准范围、实施里程碑、验收、变更次数及支持；超范围变更重新核价和确认，避免低价订单变成无限定制。新模块完成测试、审计、Canary、成本和权利分类后才上架；未使用或持续亏损的模块评估修复、调整定价或下架，已有合同权益按约定履行。

小说、短剧、漫剧和音乐作为后续独立自营项目，以同一控制面复用素材、任务、模型计量、版本、审核、授权发布、CRM及经营分析。专业能力分别建设：小说长程一致性，视频连续性与配音，音乐与声音授权等。每项目分开核算资源、调用、版权、人工和收入，既有小说资产先审查复用，不在云汇重复开发或占用交易生产资源。

一次优先验证一个新增内容方向。预设项目预算、内容质量、版权与发布条件、产出节奏和继续或暂停标准；生成内容成功不等于能够变现。样本不足时保持试验，不同时扩展多条内容业务。

## 12 开发主线与依赖总览

### 12.1 组件映射与任务拆分规则

文档章节不直接等同于新开发任务。同一系统的不同视图先形成统一 Component Map，再检查既有资产、确认已存在能力，只创建最短增量任务。实现同一个组件的架构定义、字段、安全约束和开发节点必须指向同一权威对象。

每个阶段开始前，DUAL_SERVER_EXISTING_ASSET_AUDIT=REQUIRED、CANONICAL_STATE_READ=REQUIRED、GIT_STATE_READ=REQUIRED。已有能力采用 REUSE、EXTEND、MIGRATE、DEPRECATE 或 MISSING 标记；先复用，再补齐。

### 12.2 正式阶段顺序

| 阶段 | 目标 | 进入下一阶段的条件 |
| --- | --- | --- |
| 0 | 资产盘点与组件映射 | 资产和权威状态已核实 |
| 1 | 英国 AI 开发控制面 | UK_AI_DEVELOPMENT_CONTROL_PLANE=PASS |
| 2 | 玄钧云汇 Foundation | 相关底座逐块 Canary 并注册，达到最小可用 |
| 3 | 客户产品层与 Marketplace V1 及 Micro Tool | 模块发现、就绪、报价、付款与交付闭环可验证 |
| 4 | 玄钧 INTERNAL TENANT | 内部真实使用，问题与证据进入 Solution Graph |
| 5 | 公益商业支付解决方案 | 生产就绪并完成首次产品化 |
| 6 | 公益 AI 内容引擎 | 内容审核、真实发布 Canary 与产品化完成 |
| 7 | 公益数字运营联合套件 | 复用两项目，权限与数据边界成立 |
| 8 | 后续GEO功能、市场扩展与公众第三方生态 | 达到真实规模，第三方安全基础先于开放 |
| 远期 | 可选凭证证明与空间界面 | 业务、合规、财务与安全条件支持 |


### 12.3 Foundation 的统一依赖链

身份、Tenant、RBAC 与 Audit → Creator / Developer Identity（含 XUANJUN_AI_DEVELOPER）→ Module / Connector / Product Origin / Provenance Registry → Workflow / Approval → Finance / Wallet / Immutable Ledger → Contribution / Reputation / Credential → Third-party Code Quarantine / Security Gate → Payment & Fund Integrity → Micro Tool Device Licensing → Infrastructure Control Plane → Model Router / Provider Registry → Dependency / Compatibility。

分类标签、Admin Console、采购、Schema / API、Service Catalog 与 Solution Graph 的基础模型按第15章逐项建设，并与其依赖组件连接。上面的主链表达交付依赖，第15章的2.1至2.19保留组件节点编号；节点编号不是绕过安全前置条件的许可。

资金安全随 Finance 与 Wallet 同步实现，在2.17集中验收；第三方代码隔离从首次外部代码接入前执行，在2.16验收；License 必须先于小工具交付。Dot 与 Usage Governor 同步上线，不能先开启无限调度再补限额。

### 12.4 客户流程与工程流程的关系

客户业务顺序按第8章执行：就绪检查 → 方案组合及缺口分析 → 成本与报价 → 客户确认 → 订单、Invoice、Payment → 钱包或采购预留 → Provision 与部署。工程顺序按第9章执行：任务分支 → 开发 → CI、测试、安全、构建、审计 → Release Gate → 合并与版本发布 → STAGING → CANARY → PRODUCTION。定制订单触发工程链，已有发布版本直接进入受控交付。

### 12.5 最小底座与逐步扩展的进入条件

第15章节点编号为组件目录，首批范围以业务依赖为准。CORE_REQUIRED包括身份租户权限、统一产品与连接器注册、工作流与事件检查点、必要API契约、财务及资金完整性、凭证安全、最小模型计量、部署健康回滚、监控恢复、真实订单和交付证据。相关安全与支付动作在执行前完成适用验收。

CONDITIONAL_REQUIRED按触发建设：充值消费需要Wallet及Usage；云资源采购需要Procurement与Infrastructure；1元工具交付需要设备授权及本地License；推荐对外启用需要归因、永久30%规则和后台结算；外部代码准入需要Quarantine；贡献收入产生前需要CP归属与补偿机制。部分能力可先建立最小事件与引用，不提前建设无当前用途的完整界面。

DEFERRED包括公众第三方市场、复杂推荐算法、多地区高可用、完整外部可验证凭证互通、链上锚定、DID和3D空间。Provenance与原始贡献事件从底座开始记录，后续证明能力可升级；早期数据不得因缺完整凭证界面丢失。

阶段顺序维持0至8。阶段3先实现首批项目需要的最小选择、就绪、报价、订单和交付；3.10小工具与3.11伙伴后台分别在正式开放该入口前PASS，不能以其商业推广阻塞不依赖它们的首批业务验证。阶段4验证内部流程，阶段5支付分账与阶段6内容引擎分别完成真实试点后产品化；原编号不代表必须顺序完成所有非依赖节点。

每项验证结果绑定客户或内部租户、版本、账号、地区和证据。首批框架通过一个端到端Canary并不宣称全球支持；首次生产交付具备已验证权限、付款、部署、验收、支持和恢复。第二次交付使用同一发布产物或经过审核的新版本，记录复用率、工时与成本变化。

### 12.6 V2.5增量落地顺序

先核实币安Owner对话路由并完成长任务期间响应Canary；云汇开发环境建立时配置相同职责的独立对话调度。随后在最小Foundation实现免费框架、Owner和客户面板、板块多归属、权益去重、双币价格与统一计费。金融功能在币安主线稳定及云汇控制面就绪后，按真实需求形成首个模板，不改变首批既有业务项目顺序。

金融发布前必须确定高级连接容量、套餐支持范围、BYOK收费、部署报价、汇率源、到期交接与目标市场准入。进入条件是可验收的模拟与执行安全、客户权限、成本及真实适配证据；不把所有市场接完作为首个模板前置条件。

### 12.7 V2.6基础能力前置与GEO后置

阶段0/1核验复用与工程控制；阶段2随架构实现模块产品定义、租户配置、权限/计量、Price Book版本、定制合同订单、权益、订阅计划、交付衔接、续费及统一财务事件的最小闭环。它们是首批业务交付与收费的前置能力，不等待GEO或其他后续模块。

阶段3交付“我的项目、市场、我的模块、账单付款”最小界面及后台价格/合同权益/订阅管理。阶段4内部验证两种付款、交付、初始服务期、账单续费及恢复；阶段5/6首批项目从开工按统一标准封装，阶段末完成产品化门禁，而非阶段末才开始考虑封装。

GEO列为阶段8的后续业务功能，内部实施先于其客户试点及公开销售；“先自用”仅表示GEO自身上线顺序，不将它提升到阶段4前置项目。可先登记MODULE_ID、能力描述及公共接口，不执行GEO采集、采购或开发任务。

原有阶段0至8和68个既有节点不重排；基础增量映射2.2、2.4至2.8、2.12、2.17及3.1、3.7至3.9，不为文档章节另造平行引擎。GEO实际任务仅在后续阶段门槛与已批准队列具备时创建。

### 12.8 V2.7额度节约与开源复用的落地顺序

V2.7不新增阶段，也不改变既有阶段0至8及68个节点的编号与顺序；以下按依赖关系映射到既有节点，只补缺口。

| 顺序 | 内容 | 对应既有节点或章节 |
| --- | --- | --- |
| P0 | 只读核实各服务器实际模型、认证方式、额度来源与已有用量；不修改任何生产配置 | 阶段0盘点；节点1.7、1.13 |
| P1 | 任务唯一ID与防重复规则 | 节点1.8、1.13 |
| P2 | 权威状态与证据索引，任务快照可追溯到代码、测试、部署证据 | Canonical Project State；节点1.9 |
| P3 | 快速响应的Coordinator与执行Agent分工 | 9.5、10.15、节点1.12 |
| P4 | 成本与Token监控及Owner看板字段 | 10.12、节点1.13 |
| P5 | 上下文分层与缓存优化 | 10.18.3、节点1.14 |
| P6 | 新模型代表性任务的质量与成本验证 | 4.2、10.18.6、节点1.14、1.15 |
| P7 | 按实测结果调整模型分工与限额 | 10.13 |
| 并行 | 轻量开源复用登记文件，随Git就绪建立 | 节点1.2；9.10 |


执行边界：本增补先做只读核实与设计；优先复用现有OpenClaw、Dot与调度能力，不重复开发已有组件；不直接修改东京币安生产的模型、交易执行、客户生产模型路由及财务生产链路；新服务器完成真实配置验证前，不声明新模型生产可用；未经Owner明确批准，不增加订阅、不购买大量API额度或服务器资源。

## 13 阶段0 既有资产盘点

### 13.1 检查范围与输出

必须检查：Tokyo、Domestic、Existing Binance Project、Existing OpenClaw、Existing Multi-Agent、Existing CRM、Existing Finance、Existing Billing、Existing Secure Secrets、Existing Model Router、Existing Model RPC、Existing Task Registry、Existing Canonical Project State、Existing Windows Operator、Existing Channel Adapters、Existing Monitoring、Existing Backup、Existing Documentation。

输出 XUANJUN_EXISTING_ASSET_MAP_V1，并将每项标为 REUSE、EXTEND、MIGRATE、DEPRECATE 或 MISSING。将资产对应到 Component Map、当前服务、代码库、测试、配置、SecretRef、权威状态与真实证据，禁止按新架构重建已有能力。

### 13.2 阶段完成条件

已读取 Canonical 与 Git 状态，东京和国内的既有资产检查有记录；后续任务能说明复用资产和唯一新增缺口。检查英国 DEV 资产时，先确认是否实际存在，再判断复用或供给；不把规划能力记为已完成。

## 14 阶段1 英国 AI 开发控制面

### 14.1 项目目标与范围

首个正式工程为 XUANJUN_UK_AI_DEVELOPMENT_CONTROL_PLANE_V1。英国服务器参考规格为4C16G，承载REFERENCE_SERVER、DEV、BUILD、TEST、STAGING、OpenClaw、Dot连接适配器、CI和任务控制面；Dots本体在其云端运行。实际规格、库存、价格和是否已采购以资产证据为准，不承担TRADING_PRODUCTION_WRITE。

交付范围是标准化开发与自动交付控制面，包含自动供给、Git 与私有 GitHub、CI、测试、安全、Artifact、环境隔离、SecretRef、可观测性、备份恢复、回滚、OpenClaw、Task Gateway、Node Registry、Dot、Owner Review、Drift Guard、Usage Governor、AI Eval、Checkpoint / Resume 与 Canonical State Sync。控制面 PASS 前不正式大规模开发云汇业务 Module。

### 14.2 建设节点与前置依赖

#### 节点 1.1 Infrastructure Provisioning Foundation

完成 Server Identity、Asset Registry、Blueprint、cloud-init、Configuration Management、IaC、Security Baseline、System User、SSH Policy、Firewall、Time Sync、Runtime、Monitoring、Backup 与 Lifecycle。首个蓝图为 XUANJUN_DEV_BUILD_TEST_V1。

依赖与验收：先完成资产盘点；标准供给、安全、注册、监控和恢复路径可验证。 自动采购按5.5节配置预算与权限，超时先查证资源，未确认状态不重购。

#### 节点 1.2 Source Control Foundation

安装 Git，建立 GitHub Private Repository，完成 Repository Structure、Gitignore、Machine Identity、Least Privilege、Branch Strategy、Branch Protection、Task Branch、Commit Convention、PR、Tag 与 Release；Agent 禁止直接 Push main。

依赖与验收：复用现有代码资产，版本与权限边界成立。

#### 节点 1.3 Standard Development Environment

固定 Python、Node、Package Manager、System Dependencies、Database Version、Compiler、FFmpeg 等基础工具、Container 规则与 Environment 规则；必须启用 Dependency Lock。

依赖与验收：开发环境可重现，避免部署时临时改变依赖。

#### 节点 1.4 CI Foundation

建立 FORMAT、LINT、UNIT TEST、INTEGRATION TEST、SECRET SCAN、DEPENDENCY SCAN、BUILD、ARTIFACT 与 EVIDENCE。先实现最小可用 CI，再逐步增强 SAST、SBOM、LICENSE SCAN。

依赖与验收：后续增强项必须在适用安全准入或正式发布前满足第2章和第9章门禁，不能因 CI 初期最小化而跳过生产审查。

#### 节点 1.5 Deployment Foundation

建立 DEV、TEST、STAGING，支持 Versioned Artifact、Deployment Manifest、Health Gate、Canary 与 Rollback；Production 只接收 Versioned Release Artifact。

依赖与验收：依赖版本管理、CI 与标准环境；发布、健康、Canary 和回退有证据。

#### 节点 1.6 Observability and Recovery

完成 Structured Logging、Health、Metrics、Alerting、Backup、Repository Mirror、Restore Canary 与 Rollback。

依赖与验收：日志、健康与恢复路径可核验。

#### 节点 1.7 OpenClaw 标准运行环境

复用现有OpenClaw和可迁移配置，按9.5节注册6个按需角色，按9.6节分配权限；Release Gate优先为独立规则服务。角色、配置、Skill及模型路由须以已安装版本验证，模型迁移按Canary→Eval→切默认执行。

依赖与验收：标准环境、部署和恢复已就绪，不复制已有执行系统。

#### 节点 1.8 Task Gateway

建立或扩展 XUANJUN_TASK_GATEWAY_V1，优先暴露 get_project_state、get_task_queue、create_task、get_task_status、get_task_result 与 request_owner_approval。禁止复制 Task Registry。

依赖与验收：通过受控入口复用现有任务状态与结果。 任务输入输出、鉴权、幂等、执行lease和Completion Event按10.8节实现，连接方式实测后确认。

#### 节点 1.9 Node Registry

建立 PROJECT → MILESTONE → NODE → TASK 结构。Node 记录 Status、Dependency、Owner、Agent、Cost、Risk、Evidence、Acceptance、Checkpoint、Git Commit 与 Result。

依赖与验收：节点能指向真实任务和版本，支持依赖及恢复。

#### 节点 1.10 Owner Node Review

建立 XUANJUN_NODE_REVIEW_GATE，前期重要 Node 执行前向 Owner 展示功能、目的、复用资产、新增内容、影响、成本、风险、验收和下一 Node。

依赖与验收：重要节点可见，不要求每个 Shell 命令逐项审批。 看板与通知落实10.12节，展示不等同新增审批。

#### 节点 1.11 Development Drift Guard

防止简单任务扩展成巨大重构。发现 Scope Drift 时停止自动扩张，按第10章比较目的、计划、变更、依赖和结果。

依赖与验收：执行范围可对照，扩张可停止。

#### 节点 1.12 Dot 接入

Dot 读取 Project State、Node Graph 与 Task Result，发现 Blocker，选择已批准 Next Node，派发 OpenClaw，接收 Completion Event 后继续。Dot 不自行无限创建项目。

依赖与验收：依赖 Task Gateway、Node Registry 与 Review Gate；与1.13同步上线。 采用10.8节事件协议，断线恢复和重复事件不重复派发；生产业务由持久服务执行。

#### 节点 1.13 AI Usage Governor

与 Dot 同步上线，限制 Model Calls、Codex Calls、Retries、Agent Depth、Heavy Parallel Tasks、Context 与 Recursion。采用 EVENT DRIVEN，禁止 LLM POLLING。

依赖与验收：调度与限额同时生效，资源不足保存检查点。 执行10.13节初始并行、修复与升级政策，具体费用预算另以有效授权登记。

V2.7补充：各限额的取值依第10.18节任务分级与成本度量设定；上线前先只读核实各服务器实际使用的模型、认证方式与额度来源，无法权威读取的数据标记UNKNOWN。

#### 节点 1.14 AI Eval Foundation

建立 Model Eval、Prompt Eval、Agent Eval、Tool-selection Eval 与 Business Correctness Eval，为 Customer Brain、AI Product Manager、Content Director、Dot 与 OpenClaw Agent 提供统一测试。

依赖与验收：评测版本和结果纳入发布证据，符合第4章。

#### 节点 1.15 端到端开发 Canary

选择低风险小功能，完整跑 Owner Goal → Dot Node Graph → Owner 查看节点 → Task Gateway → OpenClaw → Branch → Development → CI → Test → Audit → Merge → Release → Deploy → Canary → Evidence → Canonical State → Dot 自动进入下一 Node。

依赖与验收：同时执行第9章安全和 Release Gate；通过后记录 UK_AI_DEVELOPMENT_CONTROL_PLANE=PASS。 同时验证连接断线、事件去重、资源限额续跑及失败回退，不将文档规划或手工转发记为自动闭环。 逐项完成14.5节，局部PASS不得代替整体闭环。

### 14.3 闭环建设的最短执行顺序

以下批次映射既有节点，不新增平行开发路线或重复计数。批次A先完成阶段0，确认英国资源是否存在、可复用资产、当前连接和唯一缺口；云汇与币安、易币、小说的资产和凭证隔离。阶段0输出当前事实与可执行计划，不把其他项目的部署结论作为云汇完成证明。

批次B完成1.1至1.7的最小工程环境，并在首次付费调用前落实1.13的基础调用和预算限制。首次Bootstrap可使用现有获准执行入口，尚未建设的Task Gateway不能作为购买第一台服务器的前置循环依赖。采购若缺有效预算或云账号权限，只完成报价、蓝图和申请材料，登记真实blocker；不能因本方案授权设计而推定购买获准。

批次C按1.8→1.9→1.10及1.11→1.12与完整1.13同步的依赖建立Gateway、状态、Owner看板、漂移控制和Dot连接，配置6个按需角色与程序Release Gate。先做只读连接，再做DEV低风险写入；生产凭证尚不接入。具体OpenClaw配置采用已安装版本的有效schema与实测权限，本文不提供未经核对的生产配置键。

批次D完成1.14和1.15。低风险Canary建议实现Owner节点详情的只读功能并附适用测试，完整经过分支、构建、审计、STAGING、事件与下一批准节点；再验证重复派发、断网重连、租约过期、额度暂停、测试失败阻塞、Skill撤销和重启恢复。所有适用证据成立后，才标记工程闭环PASS。

批次E进入首批项目相关2.x、3.x及内部真实使用；其后按18章社区分账、19章公益内容、20章联合套件和21章扩展推进。工程Canary通过只证明开发控制面，不代替真实支付、内容发布、客户交付或经营成效验收。首批Skill按9.7节最晚时点逐组进入，不一次性安装全部渠道、行业和元宇宙能力。

### 14.4 首轮任务与落地证据

首轮任务为XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1。执行内容是只读核对阶段0资产、Canonical和Git、Agent及Skill、模型入口、英国资源、预算政策、可用插件或工具，以及现有任务协议。一次返回Current Fact Map、Reuse Map、唯一Blocker、6角色映射、Skill Gap List、节点批次、权限与预算缺口及最短下一动作。

首轮无需新购服务器、迁移生产或安装新Skill；只读检查能完成的集中执行，遇到无法访问的服务器明确NOT_VERIFIED并给出所需入口，不凭聊天记忆补PASS。已经完成且证据有效的部分直接复用。后续自动执行依既有长期授权、范围及具体预算推进；必要人工验证集中成清单，其他独立路径继续。

### 14.5 上线前闭环验收清单

必须证明：Owner能看懂当前功能和节点；Work能读到对应版本证据；Dots可通过已验证入口协调任务；Gateway拒绝越权和重复意图；OpenClaw按需调用正确角色；Developer不能绕过审计或发布门禁；重启及断网后不重复外部副作用；预算不足准确暂停且可恢复；Skill可撤销；已批准下一节点自动推进。

连接验收分开记录WORK_TOOL_ACCESS、DOT_TOOL_ACCESS、DOT_EVENT_DELIVERY、OPENCLAW_ROLE_DISPATCH、GATEWAY_AUTHORIZATION、OWNER_VISIBILITY、CI_AUDIT_RELEASE、CHECKPOINT_RESUME与NEXT_NODE_ADVANCE。某环节尚不支持外部事件时，英国本地闭环仍可验收，但整体必须标为PARTIAL并注明差距。机器可按政策低频对账；不能以反复LLM询问或手工复制替代事件闭环PASS。

## 15 阶段2 玄钧云汇共享 Foundation

### 15.1 启动条件与组件建设方式

UK开发控制面PASS后启动XUANJUN_YUNHUI_FOUNDATION_V1。Foundation以2.1至2.19作为组件目录，按第12.5节业务依赖确定首批范围，逐块Canary、注册并形成Reusable Asset。首批动作所需最小底座PASS后进入客户产品层，其余节点在适用动作前完成，不要求所有远期能力先行实现。

### 15.2 共享组件与安全验收节点

#### 节点 2.1 Identity and Tenant Foundation

从第一版实现 MULTI_TENANT，包含 Tenant、Organization、User、Identity、RBAC、Permission 与 Audit。同步建立 Creator / Developer 最小身份：XUANJUN_AI_DEVELOPER、CUSTOMER_CREATOR / IDEA_ORIGINATOR、THIRD_PARTY_DEVELOPER、SECURITY_CONTRIBUTOR / MAINTAINER。

依赖与验收：平台 AI 开发者从第一版存在，所有后续组件复用该身份与审计边界。

#### 节点 2.2 Registry Foundation

建立 MODULE_REGISTRY、CONNECTOR_REGISTRY、PACKAGE_REGISTRY、CAPABILITY_REGISTRY 与 CHANNEL_PROFILE_REGISTRY。统一 ID、Version、Status、Authority、Region 与 Capability。增加 PRODUCT_ORIGIN、PRODUCT_PROVENANCE、CREATOR_RELATION 与 PRODUCT_TYPE，产品来源与 MICRO_TOOL 按第3章定义。

依赖与验收：依赖2.1；统一四视图，不建立第二套 Registry 或 Marketplace；同步建立第3.5节渠道规则、权限和指标覆盖模型及版本，不把公共文档视为实际账号已获准。

V2.6同步增量与验收：同步落实3.10：模块产品定义、公共核心/租户配置/专属扩展、目录可见性、生命周期及版本分离，从首个模块开始使用。

#### 节点 2.3 Taxonomy and Capability Graph

建立 Industry、Role、Goal、Channel、Workflow、Automation Level、Deployment、Security 与 Pricing Tags，再形成 Capability Graph。

依赖与验收：标签引用统一注册对象，支持多入口发现。

#### 节点 2.4 Dependency and Compatibility

建立 DEPENDENCY_RESOLVER、COMPATIBILITY_MATRIX、DUPLICATE_DETECTION 与 CONFLICT_DETECTION。

依赖与验收：依赖注册与能力图谱，是 Solution Composer 的前置基础。

#### 节点 2.5 Workflow Approval and Event

建立 WORKFLOW_ENGINE、APPROVAL_WORKFLOW、EVENT SYSTEM 与 JOB / CHECKPOINT。采购审批、退款审批、模块发布、商户审核和内容审核统一复用。

依赖与验收：依赖身份与权限，动作和暂停恢复可审计。

#### 节点 2.6 Admin Console Framework

建立 ADMIN_CONSOLE_FRAMEWORK。Module 通过 Menu、Page、Action、Permission 与 Metric 注册后台，不为每个项目另建后台。

依赖与验收：复用 Registry、RBAC 与 Workflow。

V2.6同步增量与验收：同步注册模块、套餐、价格版本、合同权益与订阅管理的后台页面/动作/权限；定价变更预览及审批复用现有Workflow。

#### 节点 2.7 Finance Core

优先复用币安项目已有 Finance 资产，抽象 FINANCE_ENGINE、COMMERCIAL_ENGINE、PRICE BOOK、SUPPLIER REGISTRY、RATE CARD、COST ENGINE、MARGIN ENGINE、QUOTE ENGINE、BILLING、INVOICE、PAYMENT、RECONCILIATION、REFUND 与 PROFITABILITY。

依赖与验收：同步具备 Payment Intent、Provider Callback、Webhook Signature、Idempotency、Anti-Replay 与 Server-side Reconciliation；落实第6.6至6.8节30%永久一级推荐、累计毛利差额、50%实施预算及实际成本优先，成本归集和去重、归因绑定、结算冻结及冲回；资金成功状态来自服务端证据。

V2.6同步增量与验收：同步实现6.11至6.13的开发合同订单、款项用途、里程碑与订阅订单独立核算、成本预算/实际/UNKNOWN、价格版本及成交快照；推荐引用统一6.6。

#### 节点 2.8 Wallet and Usage

建立 CUSTOMER_WALLET、IMMUTABLE WALLET LEDGER、USAGE_METER、RATING ENGINE 与 REVENUE_RECOGNITION。采用 SERVER_AUTHORITATIVE_LEDGER，余额由不可变双分录或多分录账本投影；TOPUP != REVENUE。

依赖与验收：依赖 Finance；消费、冻结、释放、退款、提现与调整形成分录，修正只新增补偿事实，客户端和第三方不得直接写资金表。

V2.6同步增量与验收：同步建立Entitlement与Subscription Schedule、免费期起算、首次续费、服务期、计量和授权扣款；验收及付款事件去重，预存与消费及履约收入分离。

#### 节点 2.9 Procurement

建立 PROCUREMENT_ENGINE，统一 Server、API、Subscription、Provider、Domain 与 Third-party 的采购。

依赖与验收：依赖报价、资金预留与 Approval，遵循客户付款先于采购。 落实5.5节长期授权、采购意图去重、承诺支出限额、实际账单及续费政策。

#### 节点 2.10 Infrastructure Foundation

将英国参考环境验证过的 Provisioning、Blueprint、Asset Registry、Monitoring、Backup、Cost Ledger 与 Lifecycle 抽象为 XUANJUN INFRASTRUCTURE CONTROL PLANE。

依赖与验收：复用阶段1标准供给，满足第5章生命周期与蓝图要求。

#### 节点 2.11 AI Foundation

建立或抽象 PROVIDER_REGISTRY、MODEL_ROUTER、RATE CARD、Prompt / Policy Registry、AI Eval 与 AI Usage Meter。业务代码只按 ROLE 调用。

依赖与验收：复用阶段1评测与第4章路由原则，成本计量关联 Finance。

#### 节点 2.12 Schema and API Governance

轻量建设 SCHEMA_REGISTRY、API VERSION、EVENT SCHEMA、DATABASE MIGRATION 与 Contract Test。

依赖与验收：约束接口、事件和数据库演进，不引入无必要复杂平台。

V2.6同步增量与验收：冻结开发验收/交付、模块启用/恢复、订阅账期、支付/退款、用量与权益事件契约，供后续每个模块复用。

#### 节点 2.13 Service Catalog

连接 Service、Repository、Runtime、Server、Module、Connector、SecretRef、Monitoring、Backup 与 Version。

依赖与验收：服务目录引用各系统权威记录，不能另造独立真值。

#### 节点 2.14 Solution Graph Foundation

先建立数据结构，确保每次真实项目可以写入 Solution Evidence，不要求一开始开发复杂图数据库。

依赖与验收：支持第11章的实施、兼容性、成本、故障和复用证据。

#### 节点 2.15 Creator Contribution and Reputation Foundation

建立 CREATOR_PROFILE、DEVELOPER_PROFILE、PRODUCT_PROVENANCE、CONTRIBUTION_EVENT、CONTRIBUTION_LEDGER、REPUTATION_EVENT 与 CREDENTIAL。按第7章生成和分配 CP，声誉独立计算。 同步定义ECV政策版本、来源池、受益人分类、贡献/领取事件、累计交易额、累计余数、净释放及冲正投影，复用现有Contribution Ledger与审计。

依赖与验收：依赖 Creator 身份、产品归属和收入成本事实；平台 AI 与外部 Creator 使用同一规则，不设后台特权加分。CP、RS、Credential 前期均不可转让、交易、提现或购买，不代表现金、股权或利润权。 先记录原始贡献与来源事件；收入CP和RS按第7章分离，凭证签发、补偿与撤销采用7.5节；外部互通不作为首批依赖。 ECV实施按7.7节：身份、真实贡献、分池总量、幂等与冲正先验收；抖音/X逐平台权限、可靠服务端粉丝核验、费用与跨平台政策未确认时活动关闭。CP/ECV迁移或映射须另行定义，不覆盖历史记录。

#### 节点 2.16 Third Party Code Security Foundation

建立 XUANJUN_THIRD_PARTY_CODE_QUARANTINE、隔离源码和构建区、SECURITY_ANALYSIS、SANDBOX_RUNTIME、APPROVED_ARTIFACT_REGISTRY；执行第2章完整供应链与动态行为安全流水线。

依赖与验收：Capability Allowlist、Network Egress Default Deny、Runtime Audit、Revocation、Emergency Kill Switch 和 Rollback 生效。公众开发者市场可后置，但 Schema、隔离、安全流水线和 Runtime 权限必须先 PASS。

#### 节点 2.17 Payment and Fund Integrity Foundation

集中验收 TLS、适用服务间 mTLS 或等效身份、Signature、Timestamp、Nonce、Anti-Replay、Idempotency，以及独立 Ledger Service、数据库权限分离、敏感字段加密、SecretRef / KMS、Audit Trail 和 Tamper-evident Entry。

依赖与验收：与2.7和2.8统一实现；高风险人工调整经过 Approval Workflow 并采用补偿分录，不 UPDATE 历史金额或余额。

#### 节点 2.18 Micro Tool Device Licensing Foundation

建立 MICRO_TOOL 产品类型与 LICENSE_SERVICE，落实 ONE_DEVICE、LIFETIME_FOR_LICENSED_DEVICE、DEVICE_FINGERPRINT、签名 License 与最小化指纹存储。商业与安全规则按第3.4节执行，1元起、本地业务执行、无云端业务调用，授权/分发控制成本纳入定价。

依赖与验收：依赖产品、客户身份和支付确认；离线签名验证不得把客户端权限、价格、余额或 Secret 当作权威事实。

#### 节点 2.19 Web3 and Metaverse Readiness Foundation

第一版完成 WEB3_READY，使 Identity、Provenance、Contribution、Reputation 与 Credential Schema 稳定。

依赖与验收：Blockchain 不是运行依赖，Metaverse 不是前置项目；后续证明和空间界面复用现有权威数据。 当前最小范围为稳定身份与事件引用及数据扩展接口；链上、DID和空间实现按12.5节延后。

## 16 阶段3 客户产品层与统一 Marketplace

### 16.1 最小可用底座先于前台

Foundation 达到最小可用后启动客户产品层。按照第8章客户路径组织入口，工程上先形成详情、条件和就绪能力，再连接方案、价格、订单与供给。

### 16.2 客户产品建设节点

#### 节点 3.1 Module Detail

展示详细功能、能力、边界、依赖、价格、条件与限制，读取同一模块四视图。落实文字说明、结构化字段及适用模块演示视频/截图；勾选渠道立即展示准入、规则、费用、数据覆盖及客户待办。

依赖与验收：依赖 Registry，不重复维护页面真值。

V2.6同步增量与验收：同步展示初始与续费价、套餐额度、开通方式、依赖、包含和另收费项目；自研与定制按同一产品标准提供说明。

#### 节点 3.2 Discovery

建立 Search、Popular、Industry、Goal、Role、Workflow、Channel、Integration 与 Package。AI Guide 为重要入口之一，不是强制入口。

依赖与验收：依赖详情、标签和能力图谱。

#### 节点 3.3 Customer Prerequisite

建立 CUSTOMER_PREREQUISITES，将主体、资料、认证、账号、API、基础设施、地区和费用条件结构化。

依赖与验收：与依赖视图和客户清单一致。

#### 节点 3.4 Pre Purchase Readiness

实现 READY、READY_WITH_ACTIONS、BLOCKED、UNKNOWN，正式付款前执行检查。

依赖与验收：未知不转为就绪；硬阻塞关闭普通付款，按第8.3节处理。付款前保存渠道要求和客户确认快照；部署与发布再次核实实时政策和授权，受阻替代模式须重新确认范围和报价。

#### 节点 3.5 Solution Composer

完成 Dependency、Compatibility、Connector、Infrastructure、AI Requirement、Readiness 与 Solution Build。

依赖与验收：依赖 Dependency Resolver、Compatibility Matrix、就绪、基础设施和模型能力。 首版只开放首批两套方案的已验证模块组合，核心依赖自动补齐，不以选项数量作为验收指标。

#### 节点 3.6 Fit Gap

客户现有模块不完全满足时，依次 CONFIGURE → EXTEND → CONNECTOR → WORKFLOW → NEW MODULE。

依赖与验收：新模块符合第8.4节条件，增量开发执行第9章门禁。

#### 节点 3.7 Pricing and Quote

Solution 完成后依次 Cost → Margin → Market Price → Quote。

依赖与验收：Finance的真实成本和底价先于Commercial报价策略。实施S按复杂度核价，默认50%预算；报价计算扣除直接成本后30%推荐佣金与70%平台贡献，展示预估/实际区别，不承诺毛利预估即付款。 定制研发单独按工作量与证据核算，不将实施默认预算比例当作开发实际成本。

V2.6同步增量与验收：同步生成开发费和后续订阅报价，应用合同/客户权益及双币价格版本，市场调价不覆盖已锁订单。

#### 节点 3.8 Order and Payment

Readiness 通过 → Quote → Customer Confirm → Order → Invoice → Payment → Wallet / Procurement Reservation。

依赖与验收：满足就绪付款规则，Payment 由服务端确认，预留不计收入。

V2.6同步增量与验收：同步交付两种购买路径及账单界面，付款与开通分别显示；自动进入续费管理不等于自动扣款。

#### 节点 3.9 Automated Provisioning

Payment Confirmed → Procurement → Infrastructure → Deployment → Health → Customer Environment Ready。

依赖与验收：按第5章供给与第9章发布控制，部署健康通过才标记环境可用。

V2.6同步增量与验收：交付时按合同创建模块权益、专属配置和订阅计划，项目转“我的模块”；开通失败可恢复，幂等防重复收费。

#### 节点 3.10 Micro Tool Marketplace and Delivery

在统一 Marketplace 增加 Micro Tool 板块，支持低价工具搜索、购买、下载、激活、更新与版本回滚；共用 Product ID、Creator、Provenance、Security、Finance、Contribution、Reputation 和 Release。

依赖与验收：支付确认 → License 签发 → Device Activation → Download / Install → Local License Verification（在线仅限授权与更新控制）→ Update。低购买摩擦不能绕过安全审查和授权；业务执行本地，云端业务调用关闭；成本、最低1元与版本支持范围披露完整。 按11.7节记录激活、使用、支持成本与后续方案转化；其开放不阻塞无工具依赖的业务试点。

#### 节点 3.11 Referral Partner Dashboard

复用身份、CRM、Finance和Admin框架，按第6.8节交付伙伴协议、一级关系、邀请、业绩、逐类成本、30%佣金、结算、收款和申诉。

依赖与验收：依赖2.1、2.7、2.8与3.8；真实绑定、跨续费不重置、退款冲回、权限隔离、导出对账和金额舍入验证通过后，才开放正式推荐付款。 推荐资格不以购买工具或招募下级为条件；按11.7节有限伙伴试运行后扩大。

#### 节点 3.12 Business Metrics Minimum Loop

先建立Metric Fact、口径版本、质量状态、事件关联和可追溯经营看板，复用已授权渠道及CRM、Usage、Finance。

依赖与验收：依赖渠道权限、2.14 Solution Graph、真实订单和交付事件；先内部验证采集与归因，指标未知保留；完整内容效果与自动改进在6.9接入，不为本节点提前自建全部内容引擎。

## 17 阶段4 玄钧内部真实使用

大量外部客户进入前，玄钧先成为 INTERNAL TENANT，真实使用 Module Registry、Finance、Wallet、Model Router、Infrastructure、Content、CRM、Channel 与 Workflow。每个内部真实问题写入 Solution Graph。

本阶段检验自己的产品和实际运营路径。问题反馈回统一组件，修复后保留测试与证据；内部使用结果用于判断客户交付是否就绪，不以演示页面代替真实闭环。额外验证渠道勾选与规则失效、单层永久归因、实施成本去重、推荐后台和经营指标UNKNOWN处理；内部或合成财务测试不产生对外真实返佣。

内部真实使用同步验证开发合同→验收→模块权益→初始服务期→续费账单，以及普通模块选配→支付→配置→周期服务两条完整路径。测试不产生真实对外佣金；GEO不作为本阶段必需验证模块。

## 18 阶段5 公益商业支付解决方案

### 18.1 项目定位与启动门槛

项目为 XUANJUN_CAUSE_COMMERCE_PAYMENT_V1，定位 FIRST REAL DETERMINISTIC ENTERPRISE SOLUTION。启动条件为 UK Development Control Plane PASS、XuanJun Foundation Ready、Module Registry Ready、Finance / Ledger Ready、Workflow / Approval Ready。

核心能力包括 Merchant、Onboarding、Approval、Payment、Split、Charity Project、Reconciliation、Advertising 与 Admin，复用共享 Foundation。

### 18.2 项目内部开发顺序

#### 节点 5.0 Existing Asset Audit

先检查可复用商户、身份、支付、账本、工作流及后台资产。

#### 节点 5.1 Tenant Merchant Store Identity RBAC Audit

建立或复用租户、商户、门店、身份、权限和审计。

#### 节点 5.2 Onboarding and Approval

完成商户接入与审核，复用 Approval Workflow。

#### 节点 5.3 Payment

接入权威支付事实，复用 Payment Core 和签名对账。

#### 节点 5.4 Split

在付款确认与账本事实基础上实现 Split。

#### 节点 5.5 Charity

关联公益项目与公益金额事实，不让内容层修改资金。

#### 节点 5.6 Reconciliation Refund Reversal

完成对账、退款与冲回，采用统一补偿分录。

#### 节点 5.7 Advertising

建立广告能力，连接已验证商业数据。

#### 节点 5.8 Admin

通过 Admin Console Framework 注册管理能力。

#### 节点 5.9 Production Readiness

检查安全、账本、权限、监控、备份、Canary 与回滚。

#### 节点 5.10 Productization

将验证后的能力分类、注册并产品化。

### 18.3 产品化交付

最终可复用产品：MERCHANT_MANAGEMENT、BUSINESS_ONBOARDING、APPROVAL_WORKFLOW、PAYMENT_CORE、SPLIT_ENGINE、RECONCILIATION、ADMIN_CONSOLE、ADVERTISING_BASIC、CHARITY_PROJECT、CAUSE_COMMERCE_SOLUTION_PACK。

完成后先把商户、接入、审核、支付、分账、对账、后台、广告和公益项目能力回写 Registry 与 Solution Graph，再进入下一真实项目。

### 18.4 社区分账首批试点与可复用范围

社区分账作为首批支付方案场景配置，按支付服务商、商户合同和参与方分别核实。社区交易总额、公益金额、商户应收和玄钧服务净收入分别记录；仅合格平台服务收入进入推荐毛利润及经济贡献计算，商户流水不作为平台收入。

试点验收覆盖商户资格、确定性分账规则、支付核销、重复回调、部分退款、拒付、金额舍入、账期对账、授权撤销及恢复。规则版本与每笔执行结果关联；分账不得让LLM临时决定金额，付款成功证据必须可追溯。

首个项目将经过验证的Merchant、Onboarding、Payment、Split、Reconciliation和Admin注册为统一模块，保留客户专有配置。前台只开放已获准搭配与可选项；第二个客户的接入记录实施时间、配置复用和异常人工，形成可重复交付证据。

## 19 阶段6 公益 AI 内容引擎

### 19.1 项目定位与启动条件

项目为 XUANJUN_PUBLIC_WELFARE_CONTENT_ENGINE_V1，定位 FIRST REAL AI-NATIVE ENTERPRISE SOLUTION。第一项目与 Foundation 已验证基础能力后启动。

核心能力：Media Asset、Video Analysis、AI Content Director、Conversational Editor、Copy、Voice、Subtitle、Render、Review、Publishing、Analytics。

### 19.2 项目内部开发顺序

#### 节点 6.0 Existing Asset Audit

核查现有媒体、模型、内容、渠道、审核及数据资产。

#### 节点 6.1 Media Foundation

建立可复用媒体素材基础。

#### 节点 6.2 ASR Scene Keyframe Search

完成语音识别、场景、关键帧与搜索。

#### 节点 6.3 AI Content Director

在素材分析和 Authority 基础上建立 AI 内容导演。

#### 节点 6.4 Conversational Editor and EDL

建立对话式编辑与 EDL，支持受控编辑工作流。

#### 节点 6.5 Render

完成渲染能力与版本化输出。

#### 节点 6.6 Copy Voice Subtitle Cover

完成文案、声音、字幕与封面能力。

#### 节点 6.7 Fact Privacy Copyright Review

发布前执行事实、隐私与版权审核。

#### 节点 6.8 Channel Adapter and Publish Canary

复用Channel Adapter及第3.5节规则配置，逐渠道核实发布与读数权限、用户确认、披露、规格及配额，完成该模式的Real Publish Canary；未经准入不称全自动公开发布。

#### 节点 6.9 Analytics

复用3.12扩展为第10.7节跨渠道经营指标与服务改进：采集→质量校验→CRM/Finance归因→综合分析→策略门禁→Eval→小范围试验→效果评估→保留或回滚。只在预授权范围自动动作，高风险生成原有审批任务。

#### 节点 6.10 Productization

将验证能力写回产品和方案知识，注册BUSINESS_METRICS_CENTER与SERVICE_IMPROVEMENT_ENGINE，附真实指标覆盖、权限和改进证据。

### 19.3 产品化交付

最终可复用产品：MEDIA_ASSET_MANAGER、VIDEO_ANALYSIS、AI_CONTENT_DIRECTOR、CONVERSATIONAL_EDITOR、COPYWRITING_ENGINE、VOICE_ENGINE、SUBTITLE_ENGINE、VIDEO_RENDER_ENGINE、CONTENT_REVIEW、SOCIAL_PUBLISHING、CONTENT_ANALYTICS、PUBLIC_WELFARE_CONTENT_SOLUTION_PACK。

所有内容操作遵循下一章的财务数据边界，发布和真实平台接入保留审核、权限与 Canary 证据。

### 19.4 公益视频与经营事实的连接

内容引擎通过获授权公开数据读取公益或经营事实，建立事实日期、来源、使用范围和素材权利链。公益金额、项目进展、受益人和合作方描述须经对应事实与隐私范围校验，不由AI编造效果，也不把商业分账全部包装成公益。

视频制作、审核与发布结果关联内容ID及版本，线索通过获授权来源标记进入CRM。经营看板分别显示内容表现、有效线索、订单与平台收入；无法关联的记录保留未归因。内容层不得改Finance事实，客户聊天自报付款只触发财务查证。

先将自营素材和首批项目用作INTERNAL TENANT验证，然后以相同模块为获授权客户交付。Canary覆盖真实素材→事实与权利审核→允许模式发布→数据采集→CRM线索→选品订单→收款核销→服务交付及复盘；无需等待其他内容类别上线。

## 20 阶段7 公益数字运营联合套件

形成 PUBLIC_WELFARE_DIGITAL_OPERATIONS_SUITE，包含 Merchant、Payment、Split、Charity、Advertising、AI Content、Social Publishing 与 Analytics。套件组合阶段5和阶段6的已验证模块，不复制两套后台、支付、账本或渠道系统。

Content Engine只能读取APPROVED_PUBLIC_DATA；经营分析按租户授予必要只读汇总，推荐后台按一级关系授权。禁止修改 Finance、Split 或 Charity Amount，禁止读取无关 Sensitive Ledger。内容分析、制作和发布所需数据必须经过公开范围授权，资金真值由 Finance / Ledger 持有。

验收时检查套件依赖、产品版本、公共数据范围、内容审核与发布、资金对账、成本、权限和恢复证据。真实使用结果回写 Solution Graph。

## 21 阶段8 扩展生态与远期能力

### 21.1 达到真实规模后的增强

Module、Connector、Customer 与 Solution Evidence 达到真实规模后，再增强 Recommendation Engine、Advanced Semantic Search、Advanced Solution Graph、Third-party Developer Marketplace、Agency Partner、Solution Partner、Technology Partner、Advanced FinOps、Advanced Tracing、Feature Flag Platform、Project Generator 与 Developer Portal。

公众大规模开放第三方开发者生态属于本阶段；第三方 Schema、隔离仓库、审核流水线、Capability 权限与 Signed Artifact 基础已在2.16提前建设，并须先 PASS。

### 21.2 基础设施复杂化的真实触发条件

只有大量服务、水平扩容、多节点调度、复杂 High Availability、GPU Resource Pool、频繁 Deployment、复杂 Tenant Isolation 或单机架构真实瓶颈出现后，才评估 Kubernetes、Service Mesh、Multi-region 与 Complex Service Discovery。

### 21.3 可选证明与空间交互

后续根据真实需求启用 Verifiable Credential、可选 On-chain Proof 与 DID，再发展 Metaverse Spatial Interface。沿用第7章权利边界和第11章演进模型，不重新建立经济、身份、产品或贡献数据库。 限量生态权益及粉丝活动依7.7节独立门禁启动，不以链上或空间界面建设代替资格、额度、账本与风控验收。

### 21.4 GEO后续业务板块

项目XUANJUN_GEO_INTELLIGENCE在首批底座、交易交付、内部验证、社区分账、公益视频及联合套件的既定主线后，作为阶段8可按需求启动的业务功能。其独立启动无需等待DID、链上证明或元宇宙。

启动时先复核既有资产，再在INTERNAL TENANT实施品牌事实、官网基础、监测基线及内容优化；随后3至5家客户试点，通过证据、交付与单位经济验收后开放自助选配。详细方案见第23章。

GEO复用基础架构已完成的模块注册、定价、合同权益、订阅、财务、推荐、编辑审核、CRM和任务系统，新增仅为网站诊断、AI回答采样、指标及内容优化。固定返佣比例不写入GEO。

## 22 全程验收与执行约束

### 22.1 统一完成标准

成功标准：REUSABLE、VERSIONED、TESTED、AUDITED、DEPLOYABLE、OBSERVABLE、RECOVERABLE、COSTED、PRICED、DOCUMENTED、TRACEABLE、PRODUCTIZABLE。

完成不能只以代码写完判断；还需可复用、版本化、经过测试与审计、可部署、可观测、可恢复、成本和价格可核算、文档和追溯完整、能够产品化。

### 22.2 节点执行与续跑

每个节点按第10章展示 PURPOSE、WHY_NOW、资产复用、新增内容、输入输出、影响、权限、费用、风险、验收、证据、回滚与 NEXT_NODE。人工验证保存检查点后继续其他独立路径；资源限额保存检查点并暂停；恢复时续跑，不从头重建。

Finance / Wallet / Payment Integrity 在生产资金动作前通过验证；第三方隔离在外部代码准入前验证；Micro Tool License 在交付前验证；模型变化在切默认前评测；渠道规则在选择/付款/发布三个时点验证；30%永久一级推荐上线前验证累计公式、实际成本、关系冻结与对账；经营自动改进须有基线、权限、预算、Eval及回滚；标准构建经 Release Gate、Staging 与 Canary 后进入生产。

### 22.3 最终系统形态

最终形成 STANDARDIZED AI SOFTWARE FACTORY、ENTERPRISE SOLUTION MARKETPLACE、AUTOMATED DELIVERY CONTROL PLANE 与 ENTERPRISE SOLUTION GRAPH。工程控制面、共享 Foundation、模块市场与知识图谱连接为同一可持续复用体系。

### 22.4 本次增补的一致性验收

30%比例、单层、无固定期限及累计差额公式在报价、伙伴协议、前台、后台、Calculator和Ledger一致。校验50%仅为默认实施预算、实际成本优先，退款/拒付补记产生正确冲回；复杂度调整有依据；永久关系跨续费和身份合并保持；新增3.11与3.12节点不越过既有依赖。

小工具按1元起定价、本地执行、无云端业务调用；渠道勾选显示规则和费用，未知阻塞普通付款；文字与演示版本一致；经营优化不改资金、价格、合同或推荐归属。文档定义不等于模块已经实现。

### 22.5 首批框架与生态路线增补验收

连接验收：Task Gateway鉴权、任务契约、去重、lease、断线事件补发及checkpoint恢复有证据；开发Canary经过既有测试审计与发布链。采购验收：预算预留、最小权限、供应商幂等或超时查证、实际资源费用及续费管理通过，未确认成功不重购。

业务验收：Connector授权与撤销、首批可选组合、支付服务端核销、社区分账规则及退款对账、公益事实与素材授权、CRM未归因、持续服务恢复有证据。自动化成本包含真实人工与支持，不能假定0；重复交付的质量、工时和贡献有同条件记录。

生态验收：CP与推荐佣金口径分离、非经济贡献可记录、签发与撤销可追溯、治理权限明确、推荐单层永久关系不变。中国试点与新地区就绪分别登记，小工具本地和价格成本条件不变；小说等新项目单独预算，链上与元宇宙不成为首批上线前置条件。 新增ECV验收：1000万总量、三档各300万、活动100万、创始300万/共建700万同时守恒；1亿/10亿交易门槛与跨档分段、固定美元统计汇率6.8、池耗尽停止、退款不自动重开、3/7累计余数及冲正可追溯。两平台各35万，领取序号100000/100001、200000/200001、300000/300001与并发去重/崩溃恢复均测试；未关注/伪造/过期/接口失败不发放，共享IP正常用户与作弊分开处理，跨平台参与政策等未决项须上线前明确。

测试验收包含独立QA、适用回归、接口与集成、端到端、异常恢复、安全及容量。资金、授权、模型切换和发布关键流程未验证时不能因CI部分通过放行。

### 22.6 自动开发运作体系验收

新增设计按9.5至9.8、10.10至10.14和14.3至14.5验收。初始6角色按需运行、程序门禁和有效授权相互独立；增减角色须有负载与成本证据。所有节点功能卡、状态、版本和费用有权威来源；相同失败按限制升级，无无限Agent递归或LLM轮询。

Dot连接适配器与云端Dots区分；英国资源与连接当前状态保持事实口径。文档规定目标和落地任务，不声明已建立远程连接、已安装Skill、已启用定时通知或已采购服务器。原有68个节点及商业规则保持，新增执行批次映射原节点，不重复创建任务系统。

### 22.7 官方资料与核实范围

公开资料核实日期为2026年10月7日。以下链接是实现时核实的起点；公开文档不能代替项目应用审核和客户实际授权。Meta及企业微信部分页面读取受限，小红书通用发布能力未核实，因此相应字段保持UNKNOWN并列入控制台验证。

[1] TikTok Content Sharing Guidelines  https://developers.tiktok.com/docs/en/content-sharing-guidelines

[2] YouTube Videos insert  https://developers.google.com/youtube/v3/docs/videos/insert

[3] YouTube频道变现政策  https://support.google.com/youtube/answer/1311392

[4] YouTube Analytics和Reporting授权  https://developers.google.com/youtube/reporting/guides/authorization

[5] Meta维护的Instagram API文档  https://www.postman.com/meta/instagram/documentation/23987686-9386f468-7714-490f-9bfc-9442db5c8f00

[6] LinkedIn Community Management App Review  https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review

[7] 抖音创建视频  https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/create/create-video/

[8] 抖音发布能力使用规范  https://partner.open-douyin.com/docs/resource/zh-CN/dop/operation-standard/platform-capabilities/useclue

[9] 哔哩哔哩开放平台与服务协议  https://open.bilibili.com/  https://open.bilibili.com/agreement/developer-service

[10] 小红书开放平台  https://open.xiaohongshu.com/

[11] Telegram Bot API  https://core.telegram.org/bots/api

[12] 企业微信开发文档  https://developer.work.weixin.qq.com/document/

工程连接与Agent能力的官方核查起点如下。安装时还须读取已安装版本对应说明；公开文档不能证明当前账号已获得工具、事件或服务器权限。

[13] ChatGPT Dots Tasks and memory  https://learn.chatgpt.com/docs/dots/tasks-and-memory

[14] ChatGPT Dots Computers and apps  https://learn.chatgpt.com/docs/dots/computers-and-apps

[15] OpenClaw Skills  https://docs.openclaw.ai/tools/skills

[16] OpenClaw Agent permissions  https://docs.openclaw.ai/gateway/security/tool-permissions

[17] OpenClaw Multi-agent routing  https://docs.openclaw.ai/concepts/multi-agent/index.html

### 22.8 V2.5新增验收要求

价格验收：基础US$19.90/月、高级US$39.90/月；基础一个提供方一个交易账户连接，高级多连接容量有明确上限。所有可售权益双币可追溯，缺失关闭新收费；API20%服务费、BYOK、共享分摊、退款冲回及套餐去重有测试。

交互验收：Owner对话在长任务期间可响应，真实分派有任务ID和执行证据；Owner与客户面板跨租户隔离，对话与界面状态一致。多板块引用同一功能不复制定义、不重复计量。

金融验收：模拟先行、明确授权、订单幂等、超时查证、重启恢复、持仓核对、停订安全交接。已支持与规划市场分开，原币安统一策略与收费无变化。

版本记录：由V2.4增补为V2.5，日期2026年10月8日。原有22章、工程门禁、推荐政策与长期路线保留；本次新增设计不声明生产已实施。高级美元币种已获Owner纠正。其余新增工程口径与默认时效作为实施方案，在发布前完成相应验收及必要确认。 V2.6于2026年10月9日补充模块商业化与订阅衔接基础、后台定价治理及后续GEO板块，原商业规则不因模块新增而改变。

### 22.9 V2.6新增一致性验收

架构及开发节点同时覆盖模块封装、价格版本、合同订单、权益与订阅衔接；第一份定制合同和首个模块收费前相关最小基础已验证，不推迟到GEO建设。

定制开发和模块订阅订单独立、履约关联完整；充值不重复收入、开发款不默认抵模块款、初始免费期按合同起算、优惠受保护、续费授权可撤销、异步开通状态真实且重复事件无重复收费。后台调价影响预览、订单快照、合同锁价、数据保留与恢复通过测试。

GEO位于阶段8，自用先于其商用但不改变总体主线。实际产品观察、API基准、网站事实独立统计，UNKNOWN不写0；采集、租户隔离、抓取安全、预算及发布版本验证后才销售。所有模块继续采用统一6.6推荐规则，新增功能不重定义比例。


### 22.10 V2.7新增一致性验收

额度节约与开源复用机制只有取得运行证据后才可标记为已实现，不以本文描述代替完成证明。

验收项：①各服务器实际模型、认证方式与额度来源已登记，Codex套餐额度、API按量费用和其他供应商额度互不混用，无法读取的数据为UNKNOWN且未伪造；②同一TASK_ID不重复创建，同版本下已通过的审计未在无新证据时重跑；③相同失败指纹在一次有依据的修复后仍失败时任务暂停并保存证据包，无无限重试、无目的切换模型和Agent递归；④任务快照字段完整并可追溯到代码、测试与部署证据，上下文裁剪未丢失合同规则、安全边界、财务规则及关键证据；⑤涉及付费认证、采购、第三方平台接入的新路线均有方向与关键限制前置门的决策记录；⑥确定性工作由程序完成，关键任务未因额度不足被自动降级；⑦成本度量以验收通过任务的总成本为单位，节约目标在前20个实际完成节点基线之后核对，未达成时如实记录；⑧新模型在代表性任务验证并确认工具调用接口兼容前不进入生产，东京币安生产配置未被改动；⑨开源代码复用遵守检索限制，评估结果已登记，许可证与第三方代码安全检查完成，外部代码通过适配层接入。

## 23 GEO智能增长后续功能板块详细方案

实施归属：阶段8后续业务模块。公共基础按第3、6、8、9、12、15和16章提前建设；本章不授权提前启动GEO开发、采购或发布。

### 23.1 产品定位与边界

产品名：玄钧GEO智能增长 / XuanJun GEO Intelligence。

交付能力：品牌事实管理、网站诊断、AI回答采样、内容优化、审核发布、线索分析。

用户价值：帮助企业知道AI是否提及自己、引用哪些页面、哪些问题缺少答案，以及如何把答案完善为真实可用内容。

不承诺固定排名、必被推荐或销量增长；不把模型训练收录、网页抓取与实时回答引用混为一谈。

SEO是基础，GEO增加对AI回答、引用来源、品牌事实和自然语言需求的分析。

公共大脑是内部知识与权限基础，写入公共大脑不会自动让外部AI搜索认识玄钧。

Schema、FAQ、llms.txt可以按需要使用，但不是购买后即可获得推荐的“秘钥”。Google官方明确没有AI搜索专属必需标记；结构化数据要与页面可见内容一致。

### 23.2 结合玄钧云汇的业务与基础设施

公开业务优先聚焦：企业AI客服、AI工作流、CRM集成、多模型接入、模块化SaaS。

每个业务先核验当前状态：AVAILABLE / BETA / PLANNED / RETIRED。只有已可交付内容能进入当前销售承诺；规划功能可介绍路线，但明确未上线。

公开官网和自媒体沿用现有业务边界，不引入币安交易、收益展示、客户财务资料、交易密钥或私域业务记录。

云汇GEO定价独立于金融模块19.9美元、39.9美元订阅，不能直接套用。

现有资产一次性核查：

官网路由与多语言、公共大脑/知识权限、身份/租户、模型网关、异步任务、内容编辑审核、CRM、Usage、Billing、Finance、Referral、审计与版本恢复。

标记EXISTS_VERIFIED / PARTIAL / PLANNED_ONLY / NOT_FOUND / UNKNOWN，附路径、版本、证据、复用方式、缺口。

东京和国内服务器只进行授权范围内的资产核查，复用代码或受控接口，不把GEO任务直接压到交易生产服务上。韩国小说/易币环境不承担GEO生产。

英国云汇开发环境是否真实可用必须查证；正式商业部署使用独立SaaS运行环境，不因方案存在就购买新机器。

复用能力按当前Canonical状态、代码版本及现场验证证据登记；架构目标不等于已完成状态。

### 23.3 自用实施：先把玄钧做成真实案例

#### 23.3.1 品牌事实库

建立玄钧AI实验室、玄钧云汇及英文名称之间的关系，确定一个统一英文写法。

字段：事实ID、主体、名称/别名、产品、事实正文、来源、责任人、公开等级、地区、语言、状态、生效与失效日期、核验时间。

资料分为PUBLIC_APPROVED、INTERNAL、PRIVATE。只允许PUBLIC_APPROVED进入官网草稿和对外生成上下文。

事实示例：是否提供BYOK、支持哪个客服渠道、收费标准、部署周期、数据保存方式。没有证据时标待核验，不能补写。

产品更新产生失效事件，联动检查引用该事实的页面、报价、客服知识和草稿。

#### 23.3.2 客群与首批主题

先选两类客户：有官网且需要降低重复客服工作的小企业；需要客服、CRM、自动化组合的服务型企业。

中文、英文分别服务真实市场，不一开始扩展全球所有语言。

首批成交主题建议：AI客服部署与费用、模型费用控制、官网客服与CRM集成。

企业微信外部客户接入、Telegram等主题必须先核验能力和适用条件，再决定是否作为销售主题。工程准备完成不等于客户渠道已可用。

#### 23.3.3 官网技术清单

核查现有主域wenwenwenyiyiyi.work及既有中英文路由，先映射再调整，不新建重复栏目。

检查HTTP状态、HTTPS、robots、sitemap、canonical、hreflang、重定向、移动端、文本可读性、标题、内链、WAF和实际抓取日志。

核心正文要能在可抓取HTML中读取，不能只有登录后对话或图片文字。

OAI-SearchBot与GPTBot权限分别处理；Google Search与Google-Extended的控制用途分别处理。

robots不承担访问鉴权；后台、私有对象和API必须由真正的认证与权限保护。

机器人身份不能只信User-Agent，按官方资料核验来源；放行搜索抓取不等于关闭WAF。

变更必须有差异、备份、预览、发布后核验和回滚。

官网诊断以实际HTTP响应、抓取日志和站长工具证据为准；单次外部访问失败不能直接推断网站故障或索引状态。

#### 23.3.4 第一批12个页面

按现有路由复用，以下为内容主题，不是强制新增URL：

1 企业与品牌介绍：主体关系、联系方式、可交付服务。

2 模块市场说明：已上线、测试中、规划中分别展示。

3 AI客服解决方案：适合谁、接入路径、人工接管。

4 AI客服成本说明：模型、部署、订阅、用量分开。

5 工作流解决方案：真实输入、处理、输出和失败处理。

6 CRM集成说明：已支持系统、数据权限和限制。

7 多模型/BYOK说明：费用承担、密钥和数据边界。

8 部署与数据安全说明：可验证做法，不写虚假认证。

9 GEO产品说明：诊断和采样能力、结果边界。

10 软件选型指南：客观比较自建、SaaS、托管的条件。

11 自用案例：方法、时间窗、样本、成本和实测结果。

12 常见问题：部署周期、试用、取消、退款、支持。

先做6个中文核心页面及对应英文页，再完善其余主题。已有页先修，不为达到数量新写重复内容。

页面结构：直接回答→适用条件→操作步骤→费用与限制→证据→更新日期→下一步咨询/试用。

自然写作，不为了固定字数、关键词密度或“AI友好句式”牺牲质量。

案例使用真实日志、经允许的截图和方法说明；没有客户案例时如实采用自用验证。

#### 23.3.5 外部证据建设

先完善已授权官方账号资料，再每周发布1—2篇有实际操作价值的内容或教程。

真实合作伙伴案例、技术文档、开发者社区讨论按相关性逐步建设；不购买虚假口碑或批量垃圾链接。

同一内容按渠道重写，不机械复制几十个平台。平台发布权限尚未接通时输出待发布包，不伪装自动发布成功。

官网是事实主源；外部资料链接回对应事实页面并保持一致。

### 23.4 监测方法：把数据做可信

#### 23.4.1 首批问题库50题

30题中文、20题英文；35题无品牌发现、10题选型比较、5题品牌准确性。

品牌题与无品牌题独立统计，避免“问到品牌就算发现”的误导。

例：小企业如何部署可转人工的AI客服？AI客服订阅之外有什么费用？What AI support tools offer BYOK for small businesses?

每题记录意图、客户阶段、语言、地区、主题、关联产品、是否含品牌及版本。

排序：商业相关性、可交付性、内容缺口、优化工作量。初期评分是人工判断，不冒充搜索量。

#### 23.4.2 三条证据轨道

A 产品观察：实际ChatGPT Search、Google AI Mode/AI Overviews等具体入口，在许可与可用条件下人工或授权渠道采样。

B 联网API基准：官方联网API，用于可自动化趋势检测；单独标注“API基准”，不称为实际App排名。

C 网站事实：抓取、索引、日志、真实访问与转化数据。

豆包、元宝、Kimi、DeepSeek等逐个查证接入方式。搜索API不等于这些App的原生回答接口。

GEO阶段最初只启用1个可自动化API轨道，加1个少量人工产品观察轨道。没有接通的产品显示未支持/待人工，套餐不卖虚假覆盖。

#### 23.4.3 样本单位

1样本=1问题×1具体入口×1语言×1地区×1次独立回答。

一次回答内部可能多次调用搜索，成本按真实工具用量计算。

自用首月：50题×1个API入口×4轮=200样本；10个重点题×1个实际产品×2次独立采样×2轮=40样本，共240样本。

重复使用新会话，避免历史对话带入品牌；记录账号状态、个性化、时间、地区及联网状态。

中文英文是不同样本。重复采样也计数；多品牌从同一回答提取可以共享一次调用成本，但不能跨客户复用私有回答。

#### 23.4.4 原始证据

保存问题文本、回答、返回引用URL、请求参数、入口与模型、时间、采集方式、状态、成本、版本、证据哈希。

产品观察可用经许可的截图/导出；API保留原始响应。人工评审记录操作者与依据。

网页抓取标为独立资料，不混入原始回答。

禁止在监测提示中要求AI“推荐玄钧”；提示与地区配置变更产生新基线。

#### 23.4.5 指标

有效样本：请求成功、证据完整、入口配置满足设计条件的回答；品牌未出现的有效回答仍进入分母。

技术失败、登录墙、验证码、证据缺失不记为品牌0分，单独统计。

品牌提及率=提及品牌有效样本/该分组有效样本。

正向推荐率=在用户需求下明确提供该品牌作为可选方案的有效样本/该分组有效样本。

官网引用率=回答明确引用经核验的官方域名URL样本/该分组有效样本。纯文字域名不算引用。

品牌事实错误率=含错误事实的品牌描述样本/含可核验品牌描述的样本。

采集成功率=有效样本/计划样本；无AI摘要出现属于入口状态，不能无声删除，应另报触发率。

竞争出现份额=本品牌提及次数/固定竞品集合提及总次数；允许多品牌共现，不称为市场份额。

报告同时给分子/分母、样本数、数据来源、失败率与可比性。API和产品观察不能拼成一个“全网推荐率”。

模型/入口/题库/地区发生重要变化时分开趋势。小样本波动不作为改善证据，优先看多轮持续结果。

### 23.5 优化与成交闭环

每条建议附：发现证据、问题对应页面、原因假设、改动、预计成本、风险、验收方法。

优先级：阻断抓取/事实错误→成交页面缺失→费用及限制不清→引用证据不足→外部可信资料不足。

先修基础和6个重要页，再按问题缺口每周补2—3个内容单元；内容单元可以是现有页面的一段，不必每次新建文章。

每次记录变更ID、页面版本、上线时间、关联问题及负责人。

优化后按固定条件复测。可以使用分批上线主题作比较，但没有严谨对照时只报告相关变化，不能声称全部由GEO造成。

归因从首次发布开始：

访问记录已知AI来源、referrer、落地页、活动UTM（仅在可控制的链接添加）、咨询、注册及订单事件。

普通AI引用无法强制带UTM；来源可能丢失。已知AI、客户自报、未知来源分别展示，不猜成AI流量。

CRM记录线索、需求、合格状态、成交及订单归属；可配置首次/末次触点，但同一收入不可重复累计。

不按假想AI曝光量核算收入。净增订单需实验或可信对照，否则显示“可识别AI来源订单”。

自用关键指标：有效证据数、关键事实准确率、相关询盘、合格线索、成交、单线索成本及贡献毛利。

### 23.6 SaaS功能与客户流程

免费主框架：账户、企业资料、模块市场、工作台；免费诊断如提供，限制网站页数、次数和预算，不提供无限AI调用。

付费GEO流程：选模块→企业建档→域名验证/授权→选市场与问题→诊断→看证据与任务→生成内容→审核→导出/发布→周期复测→查看用量与账单。

没网站的客户可以先整理公开事实和建站需求；无完整落地页时不承诺同等GEO效果。建站作为独立模块报价。

首个商用版本必须具备：

企业/品牌事实库、网站诊断、问题库、一个可用API适配器、人工证据导入、原始结果、指标面板、优化任务、草稿审核、用量预算、统一计费/返佣接入。

内容编辑从自用开始就有局部修改、自动保存、版本和审核。第一版只支持导出或现有自家发布路径，先不开发通用CMS。

第二版增加一个客户需求最多的CMS、更多授权数据渠道、CRM自动事件。

企业版团队权限、多品牌、API导出按真实需求开启；不为功能清单一次性做满。

客户面板六个页签：

总览：品牌准确性、提及/引用、样本、线索、关键任务。

诊断：技术与内容问题、证据、严重度、修复状态。

监测：具体入口、题库、结果、引用、失败及历史。

内容：草稿、局部编辑、差异、审核、发布记录。

增长：来源、咨询、订单与归因可信度。

费用：套餐、成功样本、失败记录、预算、BYOK费用承担。

Owner面板另看模块收入、成本、贡献毛利、佣金、任务异常、接口可用性和进度。

### 23.7 架构与省额度运行方式

统一身份/租户→GEO业务API→异步任务→采集/诊断/生成角色→证据与指标→审核/发布→CRM/账单。

公共大脑提供批准事实与上下文；模型网关负责Provider与预算；财务Ledger、Referral使用共享能力，不复制GEO专属财务引擎。

模型模式沿用PLATFORM_MANAGED / BYOK / DEDICATED_PROVIDER。记录Provider归属，不把客户自行支付的API账单再作为平台支出扣佣。

一个快速对话协调入口：理解目标、立即返回任务ID/进度、调度后台、回答状态。确认受理目标在服务正常条件下3秒内，不让它同步做长篇研究。

后台角色：采集诊断、内容规划生成、质量审核、报告解释。按任务需要实例化，不要求常驻独立Agent。

抓取规则、指标、价格、佣金用代码；轻模型做摘要/抽取；强模型只做复杂规划、事实冲突和关键文案审核。

同一答案一次提取品牌、竞品、引用；不多Agent重复阅读。实时监测不使用陈旧缓存冒充新采样。

运行状态：QUEUED、RUNNING、WAITING_REVIEW、WAITING_EXTERNAL、PAUSED_BUDGET、SUCCEEDED、FAILED、CANCELLED。

任务有幂等键、重试上限、超时、检查点及预算预留；取消后停止新调用，重启恢复不重复扣款。

预算80%预警，100%停止新调用；已启动任务存在有限超支风险，用最大预估成本预留控制。

人工验证形成待办，独立任务继续；配额不足保存记录暂停，恢复后从检查点继续。

Work负责方案与验收，OpenClaw负责实际工程执行；Dots只在可写接管能力实测通过时进入闭环。未验证时使用可复制任务单，不依赖假设存在的通道。

### 23.8 数据与安全

核心实体：brand_fact、source、question_set/version、surface_capability、run、observation、citation、audit_issue、optimization_task、content_version、approval、publication、usage_event。

收入、成本、推荐归属与佣金引用平台统一实体，不重复造表和余额体系。

每条业务数据带tenant_id，后端校验与数据库隔离共同实施；对象存储下载同样检查租户。

URL抓取防SSRF：仅允许HTTP(S)，拒绝私网/环回/链路本地/云元数据地址，重定向重新核验，防DNS重绑定，限制响应大小、跳数、并发与时间。

外部内容作为不可信资料，不能指挥工具执行、读取其他租户或改变价格。密钥走SecretRef，发布令牌与抓取进程分离。

站点修改先验证域名控制与授权范围；公开只读诊断也遵守网站访问限制，不绕过验证码/登录墙。

内容状态：DRAFT→IN_REVIEW→APPROVED→PUBLISHING→PUBLISHED；编辑后旧审批失效。发布锁定审批版本和哈希，防止审批后内容被替换。

可以批准有限范围的自动发布策略；权限、栏目、时间、预算及撤销机制明确，越界再次审核。

公开数据、内部数据、秘密数据分别控制；没有客户允许，不用于其他客户知识库或公开案例。

建议试点原始证据保存90天、汇总12个月，商用按合同、成本及适用要求确定；提供导出、删除与备份到期策略。

### 23.9 收费设计：保留原稿价格梯度，先验证再发布

以下人民币金额仅为套餐预算提案，不是已批准Price Book。公开销售前按第6.10节完成双币展示与正式报价版本；缺少有效价格不收费。

单次诊断：149元，1品牌、最多30页、15题、30个成功API样本、1份报告，7天交付窗口；不含实际App全覆盖或人工代运营。

基础版：349元/月，1品牌、30题容量、240成功标准API样本、50页网站月检、最多2个已开通API入口、月报；不含代写/发布。

专业版：1399元/月，1品牌、60题容量、720成功标准API样本、200页月检、最多3个已开通API入口、4篇草稿、在线编辑/客户审核；不含无限人工审稿。

企业版：4199元/月起，最多3品牌、150题总容量、2400成功标准API样本、500页月检、10篇草稿、团队权限；专用数据与定制集成另报价。

入口数是上限，只有已验证入口可供选择。首期只有1个API入口时按1个出售，不能借“最多3个”暗示已支持。

成功API样本包、产品观察、额外品牌/语言、技术改造、托管人工分别列SKU。高价第三方数据不包含在标准样本内。

失败样本不扣成功样本额度，失败原因与供应商实际费用仍记录；不能无限免费重试。

人工产品观察按入口、题数、重复次数、交付周期定额报价，与API样本分开。

BYOK仍收平台功能与交付费，明确客户自行承担API费用，不将BYOK简单等于免费。

不先卖年付或承诺无限使用。先月付试点测真实成本和取消原因，再决定折扣。

### 23.10 成本预算与单客户经济性

不沿用未经验证的实时汇率及腾讯价格。供应商费用从签约价目表/实际账单录入，保存币种、生效日期、模型、工具与版本。

样本成本=输入/输出模型费用+搜索工具费用+第三方数据费+分摊计算/存储+直接人工+重试损耗。

一个样本可能产生多个收费工具调用；不能把“240样本”直接等同“240次搜索”。

现有ChatGPT额度可辅助设计与人工审核，商用自动任务仍必须确认合法可用的调用方式和计费主体，不能把个人订阅视为无限SaaS成本来源。

预算模型（全部是假设，需试点校正）：

每成功标准API样本0.15元，人工综合40元/小时。

基础版：240×0.15=36；抓取/存储/基础设施14；客服0.5小时=20；重试等10；合计80元。

专业版：720×0.15=108；草稿生成与审核预算42；基础设施40；客户支持1小时40；重试20；合计250元。

企业版：2400×0.15=360；内容相关120；基础设施120；直接人工10小时400；专用服务/重试200；合计1200元。

支付手续费、实际相关税费和额外供应商收费需要另按统一口径纳入；以上不是完整审计成本。

若API单位成本升至0.50元，仅采样费用分别为120/360/1200元，不能继续沿用80/250/1200总成本假设。

不要为保证售价强行降质；改额度、分层数据SKU或调价。

按建议售价及上述总成本假设计算模块毛利：

基础349－80=毛利269元。

专业1399－250=毛利1149元。

企业4199－1200=毛利2999元。

推荐佣金及返佣后贡献由SaaS统一财务与推荐系统按当期有效规则计算，GEO不固化比例或另设公式。

以上尚未扣固定研发、管理、获客及未归集费用，不叫净利润。

定价评估读取SaaS统一费用与推荐政策，结合实测直接成本和目标贡献毛利确定。

自用首月预算：外部现金300—800元封顶为建议额度，人工15—25小时×40元=600—1000元内部估值；新购基础设施与外包另列，不预购大型监测工具。

SaaS基础设施规划200—800元/月是假设，不是供应商报价；已有独立环境满足要求时先复用。

开发初估：资产核查1—2人日、自用增量5—8、商业MVP10—15、测试/试点5—8，总21—33人日。AI协助会减少部分编码劳动，但不消除集成与验收。 仅在GEO阶段触发评估；不得据此提前排到首批项目之前。

按内部500—1000元/人日折算约1.05万—3.3万元，是投入估值，不是必须支付给外包或保证工期。共性框架缺失时重新估算。

实际现金、人工估值、固定成本与单客户直接成本分别记账，不能重复归集。

### 23.11 接入SaaS统一商业与推荐体系

GEO是玄钧云汇SaaS的功能板块之一，不建立独立推荐返佣政策。

推荐资格、归属、计提基数、比例、收入确认、成本归集、退款调整、结算周期与支付方式，全部遵从SaaS统一规则及其有效版本。

GEO只上报模块标识、订单、服务履行、用量、可归属成本及相关证据，由平台统一Billing / Finance / Referral计算和结算。

模块报价、报告、后台与任务单不硬编码返佣比例；展示相关数据时读取平台权威结果。

平台政策调整由统一体系管理，GEO不维护第二份规则。

测试重点是事件完整、归属正确、幂等及与平台计算结果一致。

### 23.12 GEO阶段内开发与验收

本节仅在21.4的后续启动条件满足后执行。顺序为既有资产复核→玄钧自用基线→内容与网站优化→连续观测→3至5家商用试点→收费及退款周期验证→按付费需求扩展。

每步只补GEO业务缺口，复用已建设公共基础；不建立另一个报价、财务、推荐或订阅系统。

QA核验租户证据/下载隔离、SSRF/提示注入、指标分母与失败状态、API与产品观察分组、采样版本、重启取消与预算、批准内容哈希与回滚、统一账务/退款接口、CRM未知来源及订单去重。

至少一个可售入口连续4轮有证据，计划样本有效率目标95%；无未关闭严重问题，客户能完成建档至费用核对。30天实测成本和真实支付/付费意向用于决定下一投入，不承诺30天必成交。

### 23.13 权威技术依据与维护

Google AI搜索站点指南：

https://developers.google.com/search/docs/appearance/ai-features

说明SEO基础仍适用，无额外专属必需文件/标记；Search Console的Web统计包含相关AI搜索流量，不能据此分离出完整AI Mode专属曝光。

OpenAI机器人说明：

https://developers.openai.com/api/docs/bots

说明搜索抓取与训练抓取用途及控制分别处理。

OpenAI API价格页：

https://developers.openai.com/api/docs/pricing

上线时以实际模型与工具版本核价；所有平台价目和支持能力都要保存核验日期。

本方案的套餐、工时、单位成本、预算和经营门槛是玄钧的建议设计，不是平台官方价格、行业平均或实测结果。

GEO阶段执行方向：先自用验证，再客户试点和SaaS选配；总体开发顺序始终遵从第12及21.4节。

