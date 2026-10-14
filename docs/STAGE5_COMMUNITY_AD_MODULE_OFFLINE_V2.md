# Stage5 双广告位独立离线模块（第二阶段）

来源：plans/COMMUNITY_PAYMENT_TWO_AD_SLOTS_REQUIREMENT_20261010.md。沿用已合并 PR73 纯规则，新增离线存储/审计/模块接口。仅供隔离研发、样例集成与审查，**不是支付生产代码或已上线 SaaS**。

## 固定边界
- Amount 页面槽：`AD_SLOT_PAYMENT_AMOUNT`；Success页面槽：`AD_SLOT_PAYMENT_SUCCESS`。第三方托管支付页面禁止插入广告。
- 支付成功状态只能由服务器对账证据产生。此库不验证支付结果、不收款、不修改商户分账或退款。
- 主调用方必须提供已经认证的 tenant/merchant/store、用户、角色、支付与广告审批来源；不可直接把 HTTP JSON 中的 `authenticated:true` 当真实认证。
- 本地 SQLite 支持活动草稿、版本化状态变更、独立广告素材审核、插入式审计记录、定时选择和事件ID幂等。表非生产账本；没有后台服务、定时投放器、素材扫描或外部HTTP请求。
- `audit_events` 有 UPDATE/DELETE 拒绝触发器，但不能防止拥有数据库 DDL 权限的人删除/替换整表；生产必须增加独立审计储存、数据库访问控制和签名链。
- 素材URL只做无DNS访问的语法限制；生产需要重定向链、DNS解析、网络隔离、内容审核、防恶意链接和最终目标检查。
- `record_metric` 的原子唯一性只针对事件键：tenant、merchant、store、slot、kind、event_id；外部身份和同事件是否可信需要后续接入。真实支付永不依赖广告服务存活。

## 数据模型和调用合同

`open_offline(path)`: 创建独立空SQLite schema；不会连接生产数据库。

`create_campaign(db, scope, record, actor, now)`: 创建DRAFT/PENDING、version1，需受信任调用方提供tenant和已认证actor；跨商户拒绝。

`change_campaign_state(db, scope, id, next_state, actor, now, expected_version)`: 版本CAS、受控状态机；ACTIVE必须审核通过。

`review_creative(db,scope,id,approved,actor,now,expected_version)`: 仅经可信调用方认证的PLATFORM_ADMIN在已提交审核阶段审批，记录版本及审计；审批身份在此库外验证。

`choose(db,scope,slot,now)`: 只选指定租户/商户/门店、审核通过、ACTIVE、在有效期内的广告；priority降序及id稳定排序，无广告返回None。UI自己处理无广告页面，不得阻断支付。

`list_campaigns(db,scope,limit,after_id)`: 固定范围及有界游标分页，不返回不同租户广告。

`record_metric(db,scope,slot,kind,event_id,campaign_id,now)`: 仅记录已登记广告ID的曝光/点击事件；唯一键重复返回recorded=false；不涉及实际扣费/支付/结算。

## 面向未来业务系统的接口草案（**仅合同，不是HTTP端点**）

| 合同名 | 输入 | 成功响应 | 权限/证据要求 |
|---|---|---|---|
| CreateCampaign | scope、draft、expected tenant actor | id/version/DRAFT | 商户身份、草稿素材审查 |
| SubmitReview | scope、campaign id、version | next version/REVIEW | 认证的对应商户 |
| ModerateCreative | scope、id、version、decision | APPROVED/REJECTED | 可信平台审核者 |
| ActivateCampaign | scope、id、version | ACTIVE/new version | 同商户、已审核 |
| SelectAmountSlot | QR关联scope、server time | creative或无广告 | QR订单对应商户，不得污染金额 |
| SelectSuccessSlot | server-verified payment、scope | creative或无广告 | 真实支付已核验/对账后才展示 |
| RecordAdMetric | scoped signed event | new/duplicate | 防重放、验证曝光/点击来源 |
| CampaignAudit | scope、cursor | 审计历史 | 有权限且禁止跨租户 |

客户端QR重定向不是支付成功凭证；FAILED/PENDING/CANCELLED/REFUNDED显示实际支付状态。广告服务故障必须降级为无广告，支付仍可完成。

## 验收状态

- 第一阶段规则及测试：PR73 已合并。
- 第二阶段离线SQLite和状态机、审核、审计及测试：PR75，独立源码。
- 外部支付Provider、生产商户/租户身份、资金分账、真实广告素材上传和SaaS管理后台：NOT_IMPLEMENTED。
- 业务目标仓库尚未指定；控制仓库代码必须在正式集成前按业务仓库授权迁入独立业务仓库，并重新审核。
- 不部署、不授予 P2/生产 writer、不改变任何既有canonical ledger。
