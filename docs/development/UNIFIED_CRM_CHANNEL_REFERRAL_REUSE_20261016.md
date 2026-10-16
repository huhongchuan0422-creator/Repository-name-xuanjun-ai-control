# 玄钧云汇统一CRM三渠道身份与推荐归因：复用现有资产的集成约束
日期：2026-10-16。Owner明确：Telegram、飞书、官网AI聊天三者共用唯一Customer ID；推荐链接转发后保留原推荐关系。SOURCE_CONTRACT_ONLY，未生产部署或完成三渠道E2E。

## 资产优先复用（禁止第二套CRM）
- `scripts/community_visual_feedback_identity.py`：已有Telegram/Feishu/Web一次性挑战绑定、customer_id/tenant_id/project_id关联、消息追加留证及去重模型；`tests/test_stage5_visual_feedback_identity.py`包含13项相关离线用例。该模块目前为社区项目离线候选，不得直接当全平台生产CRM；迁移时映射到现有统一Customer/Identity/Project，不直接复制其SQLite为第二个客户主库。
- `plans/COMMUNITY_VISUAL_OMNICHANNEL_ASSET_AND_DEPLOYMENT_20261015.md`：三入口身份关联、渠道Adapter、消息证据的既有接线计划。
- 既有Telegram XuanJunAI_ServiceBot、用户飞书认证Bridge、网站AI/客户中心、CRM及推荐/佣金台账：首先盘点实际Owner、部署服务器、凭据权限和历史归因。英国开发通知飞书、原东京币安飞书、用户认证及重要通知飞书各自隔离，不混用生产token与机器人。企业微信不再是新功能准入依赖。
- `docs/legal/templates/referral.md`：已有推荐结算原则；推荐归因不等于佣金已获得，需财务核验真实可分成毛利及退款等事实。

## 唯一客户身份及多项目
全平台只允许一个权威`customer_id`，Tenant/Project/Business membership为独立授权维度。Telegram `provider_subject`、飞书 `open_id`（区分app_id/tenant）和站内会话subject通过服务端签名/Webhook验真、站内登录及限时一次性挑战绑定到同一个customer_id；相同昵称、手机号声明、点击链接、项目号均不能直接作为合并客户身份的证据。绑定冲突进入MANUAL_REVIEW，不覆盖旧账号；支持解绑、重绑、授权撤销、账号注销的受控历史与审计。渠道事件以(provider, app_id/tenant, event_id)去重，附Customer/Project/Business场景和授权校验，客户回复及AI对话均记入原CRM会话，不允许在没有身份核验的情况下将消息写入某已知客户。

## 推荐链接携带关系：分享可传播，不可擅自改关系
使用独立`referral_code`或带签名、可验证的推广token，服务端签发分享URL：`https://wenwenwenyiyiyi.work/?ref=<opaque_referral_code>`（仅示例路径，正式路由由Work确认）。转发链接保留同一推荐码；落地页只能在匿名、必要且合规告知下暂存短期待确认候选归因，不能写死为已绑定客户。注册/登录并验证真实客户后，服务端校验来源、授权/活动、时间窗、邀请归属及反作弊规则，以事务绑定归因事件；同一客户不得因跨设备、三渠道重复点击而生成多条有效推荐关系。同一码同客户重放幂等；不同码竞争/历史绑定冲突进入待人工规则核验，不采用最后点击自动覆盖已确认的原推荐人；禁止自己推荐自己、循环关系、多层级链式佣金。

客户打开好友转发链接：新的真实客户身份属于被推荐人，推荐关系指向原有效推荐人，转发者若不是原推荐人不得凭分享行为自动取代推荐归属。若转发者希望使用自己的推荐人身份，必须分享其自身经授权生成的专属推荐链接。一码可被多次转发，按各被推荐人产生独立归因事件。推荐佣金仅按现有合法业务/订单及验证毛利润规则计提，`REFERRAL_CLICKED`、`PENDING_VERIFICATION`、`ATTRIBUTED`、`ORDER_ELIGIBLE`、`COMMISSION_PENDING`、`SETTLED`、`REVERSED/DISPUTED`清晰区分；点击、绑定、交易、收入、佣金不可混成一个状态。

## Work正式接线验收（所有未验证项保持HOLD）
1. 国内CRM单一customer_id全渠道读取；Telegram、飞书、网页分别身份验真和绑定；开发飞书与币安飞书的通知凭据隔离。
2. 同一客户在三入口留言进入同一个CRM档案，且消息渠道/应用/项目留证；另一用户、另一项目和未登录访客不能读取或绑定。
3. A的推荐链接发给B，B再发给C：在符合规则并真实注册后，B、C均归属于A；B自身专属码与A的码区别明确；跨渠道、跨设备重新打开不覆盖已确定绑定。
4. 尝试自荐、循环、同客户多次注册/多设备、过期或篡改码、两个码抢绑定、重复Webhook、退款后佣金冲正，均有明确拒绝/人工复核/幂等事实；UNKNOWN不作成功。
5. 真实CI、模拟与实机区分，短信/站内/Telegram/飞书消息通知需取得真实回执。上线前经隐私/反作弊/佣金审核和Owner Release Gate；不因离线模型可执行就对外宣称正式上线。
