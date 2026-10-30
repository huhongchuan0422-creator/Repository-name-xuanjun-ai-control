# 统一后台模型服务双入口 UI 候选

版本：`MODEL_SERVICE_DUAL_ENTRY_UI_CANDIDATE_V1`  
来源基线：`f1a7c1084a24873902761d8bb003e9f338a37b8b`  
阶段：`UI_CANDIDATE`，等待 Owner 交互审核  
范围：仅 `demos/owner-workbench-v2/#config-models`，不含服务端实现、真实调用或安装

## 1. 两个入口

### A. 自带账号接入

步骤：选择平台 → 选择已验证 API/OAuth → 安全授权 → 读取该连接模型 → 项目启用。

| 事实 | UI 表达 |
|---|---|
| 付款对象 | 客户直接向上游平台付款 |
| 凭据来源 | 客户账号的安全录入或官方授权 |
| 权益来源 | 上游账号与连接可用范围 |
| 计量来源 | 上游平台用量；接入服务费沿既有确认方案 |
| 账单来源 | 上游账单，平台不代收模型费 |
| 绑定键 | 平台 + 账号/连接 + 授权通道 + 模型 + 项目 |

硅基流动、OpenAI、DeepSeek、百炼均显示 `PENDING_VERIFICATION`。核通前：

- 已验证通道为 `NONE_FOUND`；
- 模型列表为 `NOT_LOADED`；
- 不展示 API 安全录入或 OAuth 授权动作；
- 不允许创建连接或启用项目。

OAuth 只有在“官方支持”与“现有获准入口现场验证可用”同时满足时才动态出现。

### B. 购买玄钧AI新 API 服务

步骤：API 商品目录 → 原合同/订单 → 项目权益 → 实际 API 用量 → 原账本对账。

| 事实 | UI 表达 |
|---|---|
| 付款对象 | 客户向玄钧AI新购买 API 服务 |
| 凭据来源 | 平台受保护供应连接；客户无需上游 Key |
| 权益来源 | 原 Contract / Order 生效后的项目权益 |
| 计量来源 | 原 Usage 的实际 API 用量 |
| 账单来源 | 原 Ledger / 对账 |
| 绑定键 | API 商品 + 合同/订单 + 项目权益 + 用量 |

Price Book、Contract、Order、项目权益、Usage、Ledger 当前全部为 `NOT_CONNECTED`。供应成本估算明确不等于客户应付账单，不生成价格、免费承诺或合成订单。

## 2. 与现有手动通道选择的关系

保留 `f1a7` 的 `API_FIRST` / `SUBSCRIPTION_OAUTH_FIRST`。它只在已经绑定的 OpenAI 执行连接之间手动选择；不负责在“自带账号”和“玄钧AI新计费服务”之间切换。

候选同时展示：当前 UI 选择、实际生效来源（当前 `NONE`）、配置版本、失败原因（当前 `BACKEND_NOT_IMPLEMENTED`）与 `fallback=DISABLED`。

## 3. 默认防御与接入门禁

| 类别 | 门禁 |
|---|---|
| Owner 要求 | 先审 UI，确认后才实现服务端与真实业务接线 |
| 权限 | tenant/project/RBAC 由服务端权威校验；按钮隐藏不算授权 |
| 凭据 | 只显示状态或受保护引用；不得进入页面、日志、聊天或制品 |
| 平台能力 | 未经官方与现场验证的平台/通道不得标可用 |
| 计费 | 两入口的付款对象、权益、计量、账单隔离；不得重复收费 |
| 幂等 | 后续订单、连接、项目启用必须有请求幂等键与版本栅栏 |
| 迟到结果 | 必须绑定 tenant/project/connection/version；旧版本结果拒绝生效 |
| 失败 | 明确 HOLD/失败原因；不自动 fallback、不自动充值、不静默换源 |

## 4. 当前实现与未实现

已实现：入口切换、移动布局、事实边界、平台候选门禁、现有手动通道选择保留。

未实现：真实平台探测、API 安全录入、OAuth 授权、模型枚举、项目启用、商品目录、订单/合同、权益、Usage、Ledger、真实模型调用、Hosted 接线、生产安装。

Owner 确认 UI 后，服务端增量必须复用现有 ModelControl、ConnectionManager、Price Book、Contract、Order、Usage、Ledger，不得另造账本或身份系统。
