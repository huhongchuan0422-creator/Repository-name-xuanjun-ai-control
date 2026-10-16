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

## 强制签约与收款阻断门禁：客户完全知情（Owner追加裁定，2026-10-16）

PRE_CONTRACT_FULL_DISCLOSURE_GATE=REQUIRED；NO_DISCLOSURE_NO_CONTRACT_NO_PAYMENT=ENFORCED_DESIGN。
玄钧云汇及未来所有定制项目在签署合同、生成可付款订单、支付定金、收取尾款或开始会产生费用的开发前，必须把全部已知必需条件和可能的持续费用完整披露给客户并取得准确版本的有效确认。资料允许日后分批提交，但清单本身必须售前一次告知。任何必需项缺失、适用性不明确、价格或采购责任UNKNOWN、授权范围未披露、客户未有效确认，均为BLOCKED：不签、不收款、不诱导先付费；不能通过人工编辑前端标志绕开服务端门禁。

必须披露并由客户确认的五组事实：
（A）全部产品和服务：功能范围、标准模块、定制开发、安装部署、维护、升级、退出/迁移；分项首期、按月/年续费、按量/超额、税费、服务费、第三方采购本金、实际支付币种，以及CNY/USD双币报价、报价期限、锁价条件、可能变更情形。价格未核实的必需项不能写0，也不能生成确定总价。
（B）客户需要提供、客户可以自购、玄钧可代购、玄钧可合法免费/付费提供的资源选择，分别说明所有权、合同责任、官方购买渠道、推荐配置与来源可验证的价格范围、推荐价、初次和续期费用；不适用项及原因也应说明。
（C）一次性完整授权范围：项目全生命周期会对域名/DNS、服务器/轻量、OSS/RDS、证书、自动采购与支付、部署、备份、监控、运维、升级、回滚、续费、账户及敏感权限做哪些具体操作，最大预期操作范围、资源边界、费用预算、凭据保存与撤销办法、无法授权的替代方案；不得用一句“全权授权”掩盖具体能力或超范围操作。
（D）客户全程材料/认证：营业执照、签约代表授权、域名实名、ICP备案/APP备案、软著/应用商店资质、支付商户/分账准入、回调域名、第三方平台账号及API权限、有效期、审核周期和不可代办的本人核验；每项写出谁提供、如何申请、官方入口、教程、缺失后果及时间风险。
（E）密钥和敏感授权：逐项列出API Key、AppSecret、OAuth、支付证书/私钥、云RAM角色/STS等确实需要的凭据类型、所需最小权限、谁创建、何时提交、更新轮换、撤权、专用SecretRef/OAuth安全通道；不得要求客户将秘密填进公开聊天、普通附件、Telegram、飞书或GitHub。

## 机器可执行的支付与合同门禁契约
每笔报价和合同必须绑定唯一project_id/customer_id、版本化requirements_manifest、authorization_manifest、resource_options、material_and_credentials_manifest、complete_pricebook_snapshot、scope_and_delivery_sla、customer_acknowledgement。每份清单保留内容哈希、有效时间、客户操作和可信身份、语言/币种、确认时间、审核及变更记录；签约与付款API必须在可信服务器端重新验证版本与确认，不能只依赖前端勾选框或AI口头说明。
门禁规则：DISCLOSURE_COMPLETE=PASS AND RESOURCE_ACQUISITION_EXPLAINED=PASS AND AUTHORIZATION_SCOPE_CONFIRMED=PASS AND MATERIALS_AND_PLATFORM_CERTIFICATIONS_DISCLOSED=PASS AND PRICE_AND_RECURRING_COSTS_CONFIRMED=PASS AND CUSTOMER_ACKNOWLEDGED=PASS AND NO_CRITICAL_UNKNOWN=TRUE。任何不成立，合同签署与支付订单创建返回HOLD，清楚列出缺少什么及如何补齐。允许完全披露且明确仍需客户日后本人认证的分阶段开发，但不得将未解决的上线条件或未知必要费用包装成无风险承诺。
订单确认后若范围、必要资源、权限、真实成本或上线条件实质改变，系统先暂停新增收费，生成版本化变更单、影响与退款/延期方案，取得客户再次明示确认后才生效；既有已付订单合同、签署和账单不能静默覆盖。付款失败、重复付款、退款、渠道结果UNKNOWN都与原Finance交易事实对账，禁止重复扣款。

## 强制验收与阻断测试
1. 任一必需价格、域名/备案或第三方API成本未知，报价仅可展示候选/预算区间，正式合同/付款不可开。
2. 客户未看到RAM/服务器最高预期授权范围或未确认资料/密钥准备清单，收款与签约必须拒绝。
3. 有自有域名/自购/代购/玄钧合法提供等选项时，报价和归属各自正确；隐藏续费价格或售后再追加必需品必须阻断。
4. 客户变更服务器/支付渠道/部署地域导致依赖变化，旧确认失效，须重新披露和确认。
5. 前端篡改PASS、跨客户复用确认、伪造授权、过期报价、同一幂等键不同订单载荷、重复付款及断线UNKNOWN都必须由服务端拒绝或对账，不得假报通过。
6. 手机/PC客户完整选购与一次性知情确认、下载凭据清单/合同附件、真实CI与独立审核、后台拦截、客服一致性、退款责任须留准确版本的端到端证据。
门禁实装前状态为POLICY_REGISTERED / ENFORCEMENT_NOT_DEPLOYED / CONTRACT_PAYMENT_RELEASE=HOLD。已有符合有效合同的历史订单不得被新规则无依据追溯修改。
