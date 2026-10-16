# 玄钧云汇全生命周期一次性授权门禁 V1

Owner于2026-10-16明确：最高目标为全自动经营；禁止按“下一步需要什么权限”反复要求Owner/客户登录授权。所有定制项目和玄钧自营系统立项时，须一次性盘点整个生命周期可能需要的账号、资源、操作、预算、认证、资料、密钥、例外及后期续费运维权限，生成可理解的最大预计授权范围与可选方案，客户一次性选择确认。该规则属于商务售前和系统集成的强制门禁，不能仅靠模型记忆。当前文档登记不构成生产授权或完成接入。

## 规则与安全边界
- ONE_TIME_FULL_LIFECYCLE_AUTHORIZATION_GATE=REQUIRED。项目全链：营销/获客→CRM/推荐→AI选购与报价→客户签约/付款→域名/备案→云采购/部署→验收→使用/维护→升级/续费→退出/迁移→财务核销及审计。按真实适用性明确所有预计权限，禁止先收款才临时发现缺域名、资质、权限或客户材料。
- 一份授予的是项目所需“完整能力范围”，不是不限范围的全局管理员权限。使用一个或少量可审计的可信执行身份可以降低沟通，但权限仍限定资源归属、业务动作、预算、地域和时间。账户所有权转移、管理员提权、密钥导出、无上限资金支付和跨客户数据访问不是默认授权。法定实名、第三方审批、客户有效签署不能由AI冒充。
- 一次授权后，正常额度内采购/部署/维护/续费/回滚自动执行，内部按已批准业务政策触发，不再逐单找Owner。超范围/超预算/新法规/供应商能力变更/账号授权被撤销等才进入异常，由客户或有权人员一次性补充特定授权。不得为了避免打扰而隐瞒重大新需求或自行越权。

## 一次性授权清单结构
每条至少记录 project_id、owner/customer、provider_account、operation_category、maximum_scope、resource_scope、required_permissions、optional_permissions、customer_provides/customer_buys/xuanjun_procures/xuanjun_provides、supplier_cost、service_fee、budget_limit、billing_currency、authorization_evidence、credential_ref、expiry/rotation、revocation_method、customer_action、external_approval、rollback、acceptance_evidence 和 status；缺成本/资格/授权证据为UNKNOWN/HOLD，不当作PASS。

## 玄钧自营统一授权基线
- 阿里云：ECS/SWAS、域名/DNS/备案适用支持、OSS/NAS/RDS/缓存、VPC/SLB/EIP/NAT/CDN、容器/镜像/函数计算、证书/备份/日志/监控、真实订单/支付与续费，按必要产品API核实权限；不以“账号没钱”当作无风险。
- 国内：官网、统一CRM/Customer/Project/Identity、私有文件和SecretRef、客户沟通、SaaS/Finance、受控数据库迁移/部署/回滚。
- 英国：GitHub/Runner、P2/P3调度、开发测试、独立审核证据、部署编排和通知；不可通过新增授权绕过既有生产门禁。
- 韩国：币安系统运维、备份、迁移与恢复；真实交易按独立风险系统和客户/Owner限额授权，不因服务器运维许可一并打开交易。
- GitHub、媒体账号、Telegram/用户飞书、网站AI、第三方支付、电子签、财务/发票/退款及供应商应用分别做完整接线盘点。认证主体和密钥只经既有可信渠道，公开文档不得存明文。

## 面向定制客户的售前体验
在AI选购助手中一次性展示所有可预见必选/可选/不适用能力、最高所需授权与拒绝该权限的交付影响；逐项提供客户已有/自购/玄钧代购/玄钧提供、费用区间及推荐价格、首年及续费、申请/实名认证/密钥/OAuth教程。客户确认准确版本并完成所需有效授权后才触发相应付费与任务。资料可以分批提供，但需求必须在首次方案阶段一次披露。

## 验收
分别选玄钧完整自动经营、社区分账国内多商户、纯展示网站、境外轻量网站四种案例，证明AI可在付款前生成完整授权清单，不让客户先付款后补齐可预见权限；一个项目的合法授权不会泄漏到另一项目；单个可信执行身份可按策略执行普通采购部署续费；超预算、错主体、撤权、未知支付、重启和重复任务皆停住而不产生未经授权副作用。登录复制粘贴次数和超出最初授权的临时补授权次数作为验收指标。复用已有CRM/Commercial/Procurement/Finance/GitHub，不创建第二套系统。PR122/P2/PR17生产门禁不变。
