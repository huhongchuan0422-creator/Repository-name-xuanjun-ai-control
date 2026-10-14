# Community payment split: two advertiser-managed placements (Owner requirement 2026-10-10)

Status: REQUIREMENT_APPROVED / IMPLEMENTATION_NOT_STARTED.
Architecture scope: V2.7 Stage 5, XUANJUN_CAUSE_COMMERCE_PAYMENT_V1, nodes 5.7 Advertising and 5.8 Admin; UI hooks must be reserved when building 5.3 Payment and post-payment receipt, not deferred as incompatible refactor.

## Required customer-facing flow
1. Consumer scans merchant QR, arrives at a trusted payment amount-entry page.
2. **AD_SLOT_PAYMENT_AMOUNT**: an advertisement placement on the amount-entry page, visible without obscuring the amount, merchant, payment confirmation, consent or security notices.
3. Consumer enters amount, confirms, follows the provider-authorized payment flow; any external hosted pay page may have rules that prohibit inserting ads. Do not promise control over provider-owned pages.
4. After server-side provider verification/reconciliation confirms result, show payment-result / receipt page with **AD_SLOT_PAYMENT_SUCCESS**, a second, independently configurable placement. Do not equate browser redirect with settled payment.
5. Failed/cancelled/pending payments have truthful statuses and must never falsely display a successful paid receipt. Define a separate visibility policy for result-page ads by payment status.

## Merchant/customer administration
- Authorized merchant or organization admins can create, upload, schedule, preview, approve, activate, pause, archive, and report on advertisements assigned to their eligible merchant/store/payment context.
- Separate slot configuration, creative/media type, image/text/link, validity dates, priority, display constraints, campaign status, moderation, audit and optional frequency rules.
- Multi-tenant isolation: merchant A must never see/change merchant B creatives or metrics; platform admins have bounded, auditable permissions.
- Asset upload, URLs and redirect links require content safety, malware checks where applicable, privacy, accessibility, and appropriate legal/advertising review.
- Track ad impressions/clicks using idempotent events and honest measurement definitions, not payment or ledger data. Ads must not modify the payment amount, provider order, merchant beneficiary, charitable split, refunds, finance ledger or payment confirmation.
- One campaign may target both slots or different campaigns can be assigned to each; each slot has a fallback state when no approved active ad exists.

## Design and QA gates
- Payment status always comes from server-side verified provider evidence and reconciliation; preserve anti-replay and idempotency.
- Reserve these two slots in payment journey UI and schemas at nodes 5.3 and 5.7; implement authenticated management under existing Admin Console Framework node 5.8, not a second advertising backend.
- Test mobile amount entry, QR deep-link integrity, payment success/pending/failure, two independent slot selection rules, no-ad fallback, XSS/URL injection, abusive creative, tenant isolation, accessibility, creative expiration, impression/click dedup, performance, provider hosted-page boundaries and refunds.
- Payments must still function if ad service fails. Block ads from controlling navigation or masking the checkout/confirmation action.
- No production payment changes or customer adverts are authorized by this file. Validate payment provider capabilities, licensed merchant identity and actual flow before build/release.

## Owner补充：微信小程序／公众号＋双管理后台（2026-10-14）

本项目不是仅有两块广告位的支付页。目标是**完整社区商家展示、消费者扫码收款、平台分账及双层管理系统**。两个广告位属于支付旅程里的可选模块，不得取代商家主页、支付或分账核心能力。

### 业务终端与页面
1. 微信小程序（可扫码跳转小程序商家页／收银页）；微信公众号H5（微信内网页打开）。采用同一后端支付与商户权限接口，前端适配微信OAuth、JSAPI/小程序支付的真实官方能力；最终采用哪一种可单独启用。不得假定没有微信认证、商户号等条件就能上线收款。
2. 商家对消费者的前端展示页：商家名称、认证标识、Logo/轮播图、简介、地址/营业时间/联系方式、门店、产品或服务、动态活动、合规披露、订单/客服入口、商家专属二维码；多商家域隔离。商家展示与金额输入分开，不强迫消费者先购物车下单。
3. 二维码扫码支付：识别不可篡改的merchant/store及收款场景→后端查商户有效状态、收款权限和二维码签名→金额输入与AD_SLOT_PAYMENT_AMOUNT→消费者确认金额及收款主体→微信官方支付创建订单→支付回调签名及订单归属核验→服务端查单/对账→已核实成功页面及AD_SLOT_PAYMENT_SUCCESS。支付中／失败／取消／退款必须显示真实状态，浏览器跳转绝不等于付款成功。
4. 商家管理后台（Merchant Console）：商家/门店展示内容、商品服务、二维码、员工角色、收款/订单、退款申请、结算与分账明细、广告管理（草稿、素材、审批、投放、报表）、消息、财务导出。店员仅访问获授权门店，商家不得审核自己要求平台审核的素材或跨商家查看数据。
5. 平台管理员后台（Platform Console）：商家入驻与审核、主体/KYC材料状态、角色权限、商户号及通道配置引用、分账规则与审批、交易/退款/异常对账、风控、平台与商家广告审核、全局审计/运营统计、系统配置、对账告警及运维回滚。运营与财务审批职责分离，高风险变更须二次核验；不可让平台管理员绕过支付平台的真实资金清结算规则。

### 业务模块与财务边界
- entity：tenant / merchant / store / staff / storefront / QR / provider merchant binding / payment order / provider transaction / refund / split instruction / split settlement / reconciliation / advertisement / audit。
- 财务：实际支付服务商的分账能力、支持的资金接收方、费率、时点、退款及手续费归属，必须逐项核实；不自行假设公众号/小程序具有相同支付权限，亦不把平台内部账本写为真实资金到账。
- 一笔钱：原始订单、支付单、支付状态、退款单、分账规则版本、分账执行及查询对账证据应分离、支持幂等。分账金额按最小币种单位整数计算，汇总不得超出可分配金额；退款、撤销、冲正以及支付失败都必须形成可追踪反向流水及账务不变量。
- 广告可展示、失败降级不影响支付；商家与平台后台可以分别管理权限内广告，平台广告审核不可由商家自批；付款金额/收款人/分账比例不可由广告输入或跳转覆盖。

### 开发顺序与门禁
A. 先只读盘点东京、国内、英国、韩国已有服务/代码/微信接口/支付通道和GitHub业务仓库，结果标REUSE/EXTEND/MIGRATE/MISSING/UNKNOWN；未经实机凭据检查，不认定微信商户号、分账接口或备案已就绪。
B. 确认独立业务仓库及受保护分支后，完成五端（商家展示、小程序、公众号H5、商家后台、平台后台）路由及数据合同；锁定租户隔离、支付可信回调、清结算状态机和模块接口。
C. 使用隔离测试环境完成商家展示、二维码和离线支付状态模拟、双管理端UI及广告组件；先模拟支付，不连真实资金。
D. 对接实际微信平台资质、支付商户号/分账产品配置及退款，完成测试环境真回调/查单/分账对账验证。
E. 全链路安全QA、灰度、独立Release、回滚与真实支付Canary后才开放生产；未核实的账户及商家资质保留UNKNOWN。

### 部署／服务器归属
- 英国P2/P3为研发控制面，不作为社区支付生产数据库或收款API。
- 东京交易、韩国交易/小说、国内现有运营环境均不可被默认复用为支付生产服务；先做主机资源、服务/端口、账本隔离、数据地域、访问权限及支付合规能力的只读资产检查。优先隔离新业务环境（独立服务器/容器及数据库，具体采购待测算），不能共用交易密钥或数据库。
- GitHub只存架构/无密测试/版本化代码/CI，禁止上传真实小程序Secret、支付API私钥、证书、用户身份材料、银行账户、支付报文。
- 所有部署须固定来源commit、secretRef、签名产物、数据库迁移及回滚、健康检查、灰度验证和责任人；没有外部支付实际权限不进行真钱测试。

### 当前证据
Stage5 两广告位规则PR73已合并，独立SQLite候选PR75待审；这些是离线基础，不是已交付微信端、支付分账或管理后台。独立正式业务仓库和生产服务器环境尚未核实，状态UNKNOWN／NOT_STARTED。
