# 英国社区容器复用国内身份、CRM与公共大脑：最小差异

原Issue76 #6313455771。本轮只核源码与提出接口候选，不执行服务器、DNS、凭据、认证或消息调用；不新增身份系统、不迁库、不跨机挂载活动SQLite。公共大脑和客服中心留国内，社区业务及公益视频留英国独立容器。

## 实际读取的源码证据

国内证据来自Owner已有的customer-brain-source.json.gz（压缩件SHA256 e5047757261a270cd9c5c4a3c8ac50057053bf546143275f713a1bb9eba5a489），不是本轮现场采集。已读取源码快照，不证明现时部署版本/路由可达/凭据授权。原文可能含内部配置，不复制进仓库。

| 来源/摘要 | 已证实的接口或数据关系 | 未证实/不得推定 |
|---|---|---|
| scripts/pr122_customer_core.py；原固定SHA cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0 | Center是原SQLite accounts/sessions/projects/members/links/events/audit组件；CenterIdentity/MiniPayments/Commerce等依赖其实际对象和数据库 | 名称Center不证明它就是国内客服中心；其实际部署位置及与国内CustomerRepository的绑定未取得 |
| 国内ai_service/customer_context_core.py；8181fd7cf76cdb1ec729e4fa94e9160a32fb0f560de54175b0b4c0e55bbcd40f | CustomerIdentityResolver.resolve(channel,channel_identity)经CustomerRepository.hash_private_value及SQLAlchemy CustomerSource映射身份，未知身份返回IDENTITY_UNKNOWN并审计；DomesticRealCustomerWorkflow调用原客户工作流 | 未见对英国社区提供原会话验证、tenant/project/store/role授权投影的受控HTTP接口。此处customer_id不能直接与PR122 user_id等同 |
| 国内ai_service/internal_provider_neutral_bridge.py；94745003e7857bce1d6694bee24c6a3377650f37a50db1f29671a96a1b2b19a3 | POST /provider-neutral/bridge/v1/round-trip；GET /healthz；schema provider-neutral-bridge.v1；四个X-Bridge头、HMAC、300秒时限、request_id+nonce重放库、有限并发/请求体、脱敏审计。DomesticRealCustomerCoreAdapter复用workflow.handle_message | 只有源码协议证据；实际base URL/TLS/网络策略/调用身份与既有SecretRef授权未知。服务HMAC不等于最终客户授权；/healthz PASS不等于社区/health READY或真机验收 |
| 同桥接validate_provider_neutral_message | 允许FEISHU/TELEGRAM/WECOM及两个明确测试渠道；要求UNTRUSTED_USER_CONTENT；不接受秘密字段/文本 | 没有小程序/WEB渠道；不得冒充TG/飞书或用测试渠道接生产。不得把session、AppSecret、SecretRef或Authorization塞进消息metadata绕过规则 |
| 同桥接POST /provider-neutral/model/v1/complete | 独立模型RPC请求/响应校验及处理路径存在 | 不等于CRM查询、身份鉴权或公共大脑知识检索API；不能为接社区擅自扩大模型RPC权限 |
| 国内ai_service/semantic_conversation_brain.py；4f7d9001aea36fc26d0f3bd72ab5865741f7f3463805302c304b947fdebf5863 | SemanticConversationBrain.answer、BusinessAuthorityProvider.retrieve及约束/claim gate复用业务权威和客户上下文 | 是国内进程内能力，不是已核跨机HTTP知识服务 |
| 国内knowledge/service.py；33d88c3385df98df07a469e9da17acbd981ffb6a4ec65623dd908186e3072831 | KnowledgeService.query等原知识方法存在 | 未提供独立外部路由或英国调用许可；不把知识文件复制英国冒充复用 |
| 国内crm/commercial_authority.py；6e07f840786c8d2760146a72ddbbce4661959c054242285bbed70bf1a3d8ed25 | build_customer_commercial_projection等原商业状态/下一动作投影与敏感信息限制 | 不是已核通用CRM CRUD接口或社区交易/Finance授权 |

结论：PR122 Center与国内客服/CRM数据模型在已读源码中是不同组件；共享实际身份映射仍NOT_VERIFIED。不能凭同名或相同昵称/手机号合并用户，也不能把桥接200响应当授权。

## 最小接续差异，不重建系统

1. **先绑定权威身份来源。** 原国内身份/客服Writer从已持有源码给出实际登录/微信绑定入口、CustomerRepository/CustomerSource与PR122账户/项目关系的权威证据。缺现成映射时保持UNKNOWN，不自动注册/合并账户。只需这一条身份链所涉源码与脱敏部署引用，不要求重采全服务器。
2. **已有消息桥接优先复用，但先补契约缺口。** 公共大脑仍在国内调用原workflow/KnowledgeService。确认原桥接已有调用权限、TLS、URL、凭据引用与审计后，复用其传输验签/TTL/防重放/并发，不另造鉴权协议。不增加渠道或放宽forbidden校验；若小程序服务边界确需新增类型/渠道，由原国内Writer在原桥接集中提出精确增量及审核，本窗口不代改其活动源码或开启第二Writer。
3. **身份/CRM授权投影是独立缺项。** 当前材料未提供可直接复用的原会话验证、租户/项目/门店/角色投影接口。最小候选是在原权威服务边界只返回该用户对该请求的必要授权结果与审计关联；准确路由、授权证明来源、调用者/audience绑定、有效期、撤权复查及原审计持久化必须由原接口源码确认。不得用消息中的external_sender_id/customer_id或英国客户端自报scope替代它，也不得将会话令牌经禁止携带凭据的消息通道传递。本项是候选合同，不是新API已实现的声明。
4. **英国侧只接业务服务边界。** from_existing_runtime保持同进程API，不传RemoteCenter代理、不放宽type检查、不复制Center。原CenterIdentity、MiniPayments、PartnerPrepay、Commerce与Onboarding目前存在Center.db事务/加密/订单归属耦合，不能靠把对象替换为HTTP客户端实现跨机原子性。先按原国内身份授权投影确定可抽出的最小调用接点，再增量改原模块；跨机超时或授权未知拒绝新交易，已有UNKNOWN只核原request/reference，不能重放写操作。订单/支付/退款/分账仍复用原规则，Finance仍UNCONFIRMED。
5. **咨询与交易分离。** 国内桥接回复只服务咨询/知识结果，不能授予商户资格或直接驱动付款、退款、分账、CRM身份合并。断网/超时保留原身份和业务结果的不确定状态，不以AI回复作为授权或账务回执。

### 下一最小材料/责任方

下一责任方是原国内身份/客服源码Writer提供已持有的：实际认证/微信绑定路由与校验函数；CustomerSource/CustomerRepository相关定义及PR122关联来源；对应租户/项目/角色投影与原审计调用；原桥接URL/TLS/SecretRef名称与已有UK调用权限的脱敏引用（不提供秘密值）。现有快照引用database.models.CustomerSource、database.repositories.CustomerRepository/AuditRepository，但未包含它们的完整定义或正式HTTP认证入口；这些是准确缺项，不虚构文件名或端口。

此证据到齐后，本窗口在同一原分支交最小英国业务边界增量。没有这些证据时，不先写一个“永远PASS”的适配器、模拟身份网关或新IAM服务。公共大脑、客服中心及其数据继续国内，不以本方案申请迁库。

## 有界验证方案

| 范围 | 应验证的最少事实 | 当前结果 |
|---|---|---|
| 原桥接协议复用 | 正确MAC、过期/篡改/重放拒绝，URL/TLS校验和forbidden字段不放宽；request_id贯穿原审计 | 源码机制已核；未调用现场/未代替原国内测试 |
| 权威身份映射 | 当前会话/微信身份来自原验证器；未知/撤销拒绝；PR122与国内客户对应可追溯且无自动建号 | 缺真实接口证据，NOT_EXECUTED |
| UK scope | 同用户/tenant/project/store/role/audience绑定；错租户/错店/跨项目拒绝；服务MAC不能代替用户权限 | 候选验收，接口冻结后补受影响测试 |
| 事务/网络异常 | 国内授权超时/响应未知/回执错配拒绝新写；不重试资金或身份写入；审计事件与业务reference可关联 | 候选验收，不冒充已实现跨机事务 |
| 知识/咨询 | 原国内workflow与公共大脑路径，用户问题按不可信内容处理，拒绝秘密泄漏和越权上下文 | 源码关系已核，UK端到端未验证 |
| 回归复用 | 1ac19e4a Hosted39580901541的1821项结果只证明原同进程组合/业务边界 | 复用，不改绑到新跨机接口或真机验收 |

## 资源与域名最小决策

Owner硬上限：社区对英国CPU、内存、可分配业务存储分别≤1/5；公益视频分别≤1/3，合计最高8/15。这是最高许可，不是预留承诺。实际还需扣除既有服务、B5/P2不可削减预算和系统恢复预留，不足继续下调。PID与日志按真实宿主/控制器/存储及总体预算各设有限硬上限，不能由CPU比例猜日志字节。数值与实际设置仍待容量证据，未设置。

| 候选 | 源码/现有配置证据 | 冲突、证书与映射状态 |
|---|---|---|
| community-preview.wenwenwenyiyiyi.work | 原connection.json、nginx候选、小程序构建及健康硬门禁已绑定，优先复用 | 实际DNS/TLS/入口→英国映射和可用性未核，不改DNS或上传新码 |
| video.wenwenwenyiyiyi.work | 现有自有网站域下的二级候选，仅名称建议 | 在本轮已核配置中未命中，不等于全域无冲突；证书/入口/英国视频映射UNKNOWN |
| preview.community.wenwenwenyiyiyi.work | 自有网站域下三级备选，非已配置入口 | 全域冲突UNKNOWN；*.wenwenwenyiyiyi.work不能直接证明覆盖该三级名，须精确证书证据；若采用需先变更候选构建/健康origin再获准实施 |
| center.wenwenwenyiyiyi.work | 原DNS主计划记录CNAME到custom-domains.chatgpt.site | 已有用途，排除为英国社区/国内身份API候选，不改动 |

公共大脑/客服不因本方案新增公网域名或暴露内部桥接。候选域名不是已占用、已签证书或已发布的声明。本轮不查现场、不改DNS/证书/网络/凭据/权限，BACKEND_NOT_READY硬门禁和客户未验收状态保留。
