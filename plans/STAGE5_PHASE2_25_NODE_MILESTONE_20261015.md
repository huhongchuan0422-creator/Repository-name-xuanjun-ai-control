# Stage5 Phase2 25节点开发跟踪与真实依赖（2026-10-15）

基线 PR118 71024b22f0d6110f0507dbd8476468313f8846f2（已获源码审查 PASS_WITH_SCOPE_LIMITS）。本阶段独立 Draft PR122，以PR118为base，严禁在PR118追加未审代码、合并、支付或生产安装。

状态说明：
- `IMPLEMENTED_CANDIDATE`：有对应功能源码/测试，仍需准确HEAD的完整CI与独立审核。
- `PARTIAL`：只有契约/只读路径，尚未满足全部目标。
- `EXTERNAL_DEPENDENCY`：真实资质、提供商接口或生产数据未提供；不得伪造。
- 本文不把单元测试数量冒充25个业务交付，也不把离线测试升级为真实商业上线。

| 节点 | 原计划目标 | 当前状态 | 本阶段实现与剩余缺口 |
|---|---|---|---|
|01|SaaS报价API|IMPLEMENTED_CANDIDATE|Phase2 dispatch quote / quote_read，复用冻结Offer审批|
|02|订单API|IMPLEMENTED_CANDIDATE|prepare、read、status；全部仅离线|
|03|权益查询API|IMPLEMENTED_CANDIDATE|entitlement/capability只读，绝不修改授权|
|04|后台审核API|IMPLEMENTED_CANDIDATE|review_open/review_close、admin_snapshot受角色限制|
|05|统一身份与租户权限|PARTIAL|Principal由server配置token映射；缺生产客户实名/会话认证|
|06|SaaS功能市场|IMPLEMENTED_CANDIDATE|saas-panel本地渲染可信租户功能与报价|
|07|双币价格套餐|IMPLEMENTED_CANDIDATE|不同周期独立显示CNY/USD，不把UNKNOWN当0|
|08|客户订单中心|IMPLEMENTED_CANDIDATE|customer_orders独立租户只读，页面可刷新|
|09|权益续费界面|PARTIAL|展示实时只读权益；续费计划API已存在，完整客户交互未完成|
|10|Owner定价/审批后台|PARTIAL|owner_create_offer和owner_approve_offer仅离线接口；Owner编辑页面及真实权限待完成|
|11|权威Finance适配接口|PARTIAL|沿用plan_finance_claim和只读证据需求；无真正权威验证器|
|12|支付凭证验证|EXTERNAL_DEPENDENCY|真实商户凭据、回调验签、沙箱授权未提供；现有HMAC仅测试夹具|
|13|订单与Finance事件关联|PARTIAL|订单状态机/证明要求已完成离线逻辑；缺权威结算事件|
|14|权益正式执行接口|EXTERNAL_DEPENDENCY|正式授权必须依赖可信已核验支付/财务结果；当前仅intent|
|15|退款撤销冲正|PARTIAL|refund_reversal_plan只读；真实退款/冲正需支付商户资格|
|16|数据库迁移|EXTERNAL_DEPENDENCY|旧/生产DB格式、数据量、备份与授权未知；精确DDL校验只支持当前 schema|
|17|多业务DB一致性|IMPLEMENTED_CANDIDATE|cross_store_audit只读报告，不虚报跨库原子提交|
|18|WAL与故障恢复|PARTIAL|备份与子进程退出后已提交数据恢复测试；未达生产级断电/跨DB原子恢复|
|19|并发及重复事件|IMPLEMENTED_CANDIDATE|沿用PR118 R2双连接锁与事件幂等回归|
|20|备份恢复完整性|IMPLEMENTED_CANDIDATE|backup/verify_backup SHA256、SQLite完整性与防覆盖；无自动生产恢复|
|21|标准部署制品|PARTIAL|确定性离线归档与manifest/hash，未取得生产签名/安装授权|
|22|配置密钥隔离|PARTIAL|loopback server端注入Principal token，无浏览器持久化；无生产密钥管理|
|23|健康检查与回滚|PARTIAL|health/rollback_preview离线HOLD；真实服务启停与部署回滚未执行|
|24|微信小程序公众号接入|EXTERNAL_DEPENDENCY|开发者身份、授权、正式小程序及公众号环境需平台接入|
|25|真实支付服务商联调|EXTERNAL_DEPENDENCY|签约商户号、密钥、沙箱及可验证回调/结算须另行取得|

## 实现位置
- 商业身份/API：scripts/community_saas_phase2.py
- Loopback transport：scripts/community_saas_phase2_http.py
- 页面：demos/community-local-e2e/saas-panel.html 与 .mjs
- 供货/部署前置：scripts/community_saas_phase2_package.py
- 数据备份/恢复：scripts/community_saas_phase2_recovery.py
- 测试：tests/test_stage5_saas_phase2*.py、demos/community-local-e2e/saas-panel.test.mjs
- Feature ID沿用governance/features.json内SAAS_AI_PRICING

## 强约束
1. 所有端点仅离线/loopback；server token只是演示能力，不是微信OAuth或真实客户认证。
2. 无支付确认、真实授权发放、佣金发放、退款交易、云资源采购的隐含权限。
3. 新候选必须独立审核全部变更和影响链才可提升离线候选验收级别。
4. 执行依赖受阻时，不将PARTIAL/EXTERNAL_DEPENDENCY标为完成；外部授权由Owner另行提供。
