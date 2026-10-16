"""Reviewed English wording for the static hub handoff; no browser translation."""
import html
import re

PAIRS = '''产品与购买|Products and purchase
产品可视化中心|Product visual center
可视化中心|Visual center
共建共享|Co-build and share
客户项目|Customer projects
首页|Home
玄钧云汇|Xuanjun Yunhui
静态预览候选 · 非正式报价、支付、活动领取或客户登录|Static preview candidate · No official quotation, payment, activity claim or customer sign-in
离线演示候选 · 不提供真实支付、权益领取、收益结算和客户登录|Offline demo candidate · No real payments, entitlement claims, earnings settlement or customer sign-in
从独立模块、行业解决方案到定制开发，按实际交付状态查看能力、依赖和报价。|Explore standalone modules, industry solutions and custom development with their actual delivery status, dependencies and quotation requirements.
体验社区分账演示|Explore the community payment demo
查看生态共建|Explore ecosystem participation
功能与规则|Functions and rules
月付、年付、买断、定制均为支持的报价模型，不代表所有产品当前可购买。|Monthly, annual, one-time and custom quotation models are supported; this does not mean every product is currently available to buy.
人民币与美元并列展示；第三方成本、代购服务费、部署费、维护费独立披露。|CNY and USD prices are displayed together. Third-party costs, purchasing service fees, deployment and maintenance are disclosed separately.
正式付款需服务端真实报价、资格核验、合同及Finance确认。|Real payment requires a server-authorized quotation, eligibility checks, a contract and Finance confirmation.
费用规则与开发优惠|Service credits and development discounts
普通合格自营服务，专项金额最多抵扣90%。|Special service credit may cover up to 90% of eligible ordinary in-house service fees.
定制开发先享ECV等级折扣，再对折后费用抵扣最多50%。|Custom development receives the applicable ECV tier discount first; special service credit may then cover up to 50% of the discounted eligible development fee.
第三方成本不得抵扣，推荐佣金只对实际可确认正毛利依权威规则产生。|Third-party costs cannot be offset. Referral commissions require verified positive gross profit under the authoritative rules.
查看共建共享身份等级及利润共享规则|View ECV tiers and co-creation profit-sharing rules
定制开发费用模拟|Custom development quote simulator
此为只读估算，非真实订单、付款或可支付佣金。|This is a read-only estimate, not an order, payment or payable commission.
原开发报价（元） |Original development quote (CNY) 
当前ECV持有量 |Current ECV units 
可用专项抵扣余额（元） |Available special service credit (CNY) 
已确认直接成本（元；留空表示未知） |Verified direct cost (CNY; leave blank if unknown) 
计算开发实付|Calculate development amount due
详细页面入口|Explore details
功能模块目录|Function module catalog
查看已登记规则、演示及接线状态|View registered rules, demos and integration status
权益优惠规则|ECV discount rules
共创项目方案|Co-creation proposals
SaaS模块功能目录|SaaS function module catalog
统一商品四视图：功能说明、依赖与就绪资料、双币报价、工程与交付版本。支持月付、年付、买断、免费、按量、部署费、维护费；仅经Price Book批准才显示实际售价。|Each product has four views: functions, dependencies and prerequisites, dual-currency pricing, and engineering and delivery versions. Monthly, annual, one-time, free, usage, deployment and maintenance options require approved Price Book entries before an actual selling price is shown.
模块列表|Module list
选购相关模块|Explore related modules
通过真实可点击的示例业务流程了解模块。未经审核的演示不接真实支付或生产客户数据。|Explore modules through clickable example workflows. Unapproved demos do not connect to real payments or production customer data.
行业案例与模块目录|Industry examples and module catalog
查看公开演示|View public demos
通过项目案例→模块→角色流程→报价说明进入可视化体验；所有DEMO功能须明确标注真实接口是否连接。|Explore project examples, modules, role workflows and quotation guidance. Every demo must state whether real interfaces are connected.
现有社区分账离线演示可以体验消费者、商家、社区、分账方及平台角色；不表示已接真实微信支付。|The existing offline community demo presents consumer, merchant, community, beneficiary and platform roles. It does not imply a connection to real WeChat Pay.
其他行业案例需要权威模块登记及实际交付证据后才能公开。|Other industry examples require authoritative module registration and delivery evidence before publication.
行业案例及模块预览|Industry examples and module previews
社区分账：消费者扫码金额、两个广告位、商家、社区、分账方与平台角色。|Community payment: consumer amount entry, two ad placements, and merchant, community, beneficiary and platform roles.
社区分账案例|Community payment example
社区分账演示|Community payment demo
社区分账多角色演示|Community multi-role payment demo
社区分账可视化演示|Community payment visual demo
社区分账 · 多角色业务演示|Community payment · Multi-role business demo
DEMO · 隔离数据|DEMO · Isolated data
按角色查看和跨角色流程，复用已登记的社区离线演示源码。|Explore role views and cross-role workflows using the registered offline community demo.
消费者|Consumer
商家|Merchant
社区|Community
分账方|Beneficiary
平台运营|Platform operations
SaaS模块|SaaS modules
已存在的角色演示源码位于仓库 demos/community-local-e2e。本候选采用独立入口，不复制重写原模块；发布时必须由受控制品将其映射到 /visual/community-local-e2e/。|Role demos reuse the existing community-local-e2e modules. Their version-bound assets must be mapped together with the required simulation service before release.
部署前置：验证六个目标文件与脚本资源均属于同一审核版本，禁止仅发布本入口页造成404。未接真实微信支付或生产分账。|All six role entry files and scripts must belong to the same approved version. Publishing only this entry page is insufficient. No real WeChat Pay or production profit distribution is connected.
共建 · 共治 · 共享|Co-build · Co-govern · Share
参与生态建设、记录真实贡献、参与产品方向讨论；生态权益不是虚拟币、股权或收益承诺。|Help build the ecosystem, record real contributions and discuss product direction. ECV is not a cryptocurrency, equity interest or promise of returns.
了解产品服务|Explore products and services
体验可视化案例|Explore visual examples
贡献入口：消费者、推荐者、开发者、共创发起人、合作伙伴及专项服务购买者。|Participation includes consumers, referrers, developers, co-creation initiators, partners and special service purchasers.
权益总量永久上限2,000万份：交易贡献池900万份、活动专项池1,100万份；创始与共建配额是同一总量的另一分类维度。|ECV has a permanent cap of 20 million units: 9 million in the transaction contribution pool and 11 million in the activity pool. Founder and co-builder allocations are another classification of this same total.
正常贡献来源每份ECV一次性附带500元专项自营服务抵扣额；购买专项服务包赠送的ECV不附带该500元。|Each eligible ECV from ordinary contributions includes a one-time CNY 500 in-house service credit. ECV gifted with a purchased special service package does not include this additional CNY 500.
符合规则的专项抵扣限适用自营服务费，最高抵扣比例90%；第三方成本不抵扣，额度用完不恢复。|Credit applies only to eligible in-house service fees, up to 90% for ordinary services. Third-party costs are excluded and spent credit is not replenished.
活动领取、积分发放、治理投票与未来价值共享均需独立准入；当前不开放领取或现金兑现。|Activity claims, allocation, governance voting and future value sharing each require separate approval. Claims and cash redemption are not open.
权益来源必须分别核算|Track each source separately
正常贡献|Ordinary contributions
每份符合规则的ECV一次性附带500元专项抵扣额；使用后不再次发放。|Each eligible ECV includes a one-time CNY 500 credit that is not issued again after use.
购买专项服务包|Purchased special service packages
客户得到订单明确的真实服务额度，获赠ECV本身不另外附带500元；10元起是政策起点，不是已发布SKU。|Customers receive the service amount specified in their order. Gifted ECV adds no extra CNY 500 credit. A CNY 10 starting point is a policy proposal, not a published SKU.
共创发起人|Co-creation initiator
项目提出人可按审核过的贡献记录展示昵称与共创发起人身份。平台注册、登录、编辑资料等共享基础模块属于玄钧自主研发，不因复用在共创项目中而改记发起人。|A project proposer may be credited by nickname as its co-creation initiator after contribution review. Shared registration, sign-in and profile modules remain Xuanjun's own work; reuse in a co-creation project does not transfer attribution.
活动与治理|Activities and governance
抖音与X粉丝活动、推荐活动、治理投票及链上验证均为规划/待验收，当前没有领取、转让、交易或自动分红入口。拟议未来价值共享不构成当前分红或股权承诺。|Douyin and X fan activities, referral activities, voting and on-chain verification are planned or awaiting acceptance. There is no claim, transfer, trading or automatic dividend entry. Proposed future sharing does not promise current dividends or equity.
开发折扣 · 专项抵扣 · 共创共享|Development discounts · Service credit · Co-creation sharing
身份等级与定制开发优惠|ECV tiers and custom development discounts
生态权益身份等级和共创项目分成资格是不同的权利。达到对应ECV门槛后，可按报价版本享受定制开发折扣，再抵扣折后开发费的最多50%。|ECV discount tiers and co-creation profit-sharing eligibility are separate rights. Eligible ECV holdings determine the quoted custom development discount; credit may then cover up to 50% of the discounted eligible fee.
ECV持有量|ECV holdings
权益值|ECV units
2份|2 units
10份|10 units
20份|20 units
40份|40 units
80份|80 units
150份|150 units
开发折扣|Development discount
9折|10% off (pay 90%)
8折|20% off (pay 80%)
7折|30% off (pay 70%)
6折|40% off (pay 60%)
5折|50% off (pay 50%)
4折|60% off (pay 40%)
两类专项服务抵扣|Two service credit limits
普通合格自营服务费、部署费及维护费：专项余额最多抵扣90%。|Credit may cover up to 90% of eligible ordinary in-house service, deployment and maintenance fees.
定制开发：先使用等级折扣，再对折扣后的合格开发费用抵扣最多50%。|Custom development: apply the tier discount first, then credit up to 50% of the discounted eligible development fee.
第三方成本不能使用专项服务额度抵扣；真实余额不足时只扣剩余可用数额。|Third-party costs cannot be offset. If available credit is insufficient, only the remaining eligible balance is used.
真实成本决定推荐佣金|Verified costs determine referral commission
示例：开发费原价6,000元 → 150 ECV享4折后2,400元 → 专项抵扣1,200元 → 客户实付1,200元。已核直接成本2,000元，本单毛利-800元，因此本单不新增一级推荐佣金。永久推荐关系不因此失效，后续佣金仍遵守累计毛利润、收款及退款冲回规则。|Example: CNY 6,000 original development fee → CNY 2,400 after the 150-ECV discount → CNY 1,200 credit → CNY 1,200 paid. With verified direct cost of CNY 2,000, gross profit is minus CNY 800 and no new first-level referral commission accrues on this order. The permanent referral relationship continues; future commissions follow cumulative gross profit, collection and refund reversal rules.
共创模块后续销售净利润共享|Net profit sharing from later module sales
已确认的共创项目采用八档10%—80%共享规则，档位依原始开发定价而非折扣价判定；具体档位区间以生效的业务规则与合同为准。分配基于模块销售经核实的实际净利润，不是按项目标价直接分配。共创发起人展示昵称；平台通用基础能力归属玄钧AI实验室。|Confirmed co-creation projects use eight sharing tiers from 10% to 80%, determined by original development pricing rather than the discounted price. Monetary bands require effective business rules and contracts. Sharing uses verified actual module-sale net profit, not the project list price. Initiators use nicknames; generic platform capabilities remain Xuanjun AI Lab's work.
本页不提供真实权益核销、交易下单、分账结算或收益承诺。使用下面的离线计算器不会扣减余额。|This page does not redeem entitlements, place real orders, settle profit shares or promise returns. Offline calculations do not debit balances.
身份等级与开发折扣|ECV tiers and development discounts
身份等级与开发优惠|ECV tiers and development discounts
共创项目广场|Co-creation projects
共创共享收益|Co-creation profit sharing
权益专项金额明细|ECV and service credit details
生态活动|Ecosystem activities
生态治理|Ecosystem governance
先享等级折扣，专项抵扣额再按折后开发费最多抵扣50%。普通合格自营服务费最多抵扣90%，第三方成本不抵扣。|Apply the tier discount first, then credit up to 50% of the discounted eligible development fee. Eligible ordinary in-house services allow up to 90%; third-party costs are excluded.
查看费用模拟|Open quote simulator
了解定制共创|Explore custom co-creation
用户提出真实需求→复用审查→开发成本核定→原价报价及有效协议→开发验收→小模块封装→SaaS上架复售。|Real requirement → reuse review → verified development cost → original quotation and effective agreement → development acceptance → small module packaging → SaaS listing and resale.
共创门槛：原始定制开发定价不少于1000元（不含第三方成本）；既定报价原则为内部估算成本×3。未验证成本不得视为0。|The original custom development price must be at least CNY 1,000, excluding third-party costs. The pricing principle is three times estimated internal development cost. Unverified cost must not be treated as zero.
共创发起人公开只显示昵称，平台的注册、登录、用户资料、权限等基础模块仍归属玄钧AI实验室；共创署名不自动赋予利润共享权。|Only the initiator's nickname is public. Registration, sign-in, profiles, permissions and other foundation modules remain Xuanjun AI Lab's work. Attribution does not automatically grant profit-sharing rights.
共享规则|Sharing rules
共创模块销售后的利润共享|Profit sharing from co-created module sales
经审核的共创项目适用既定八档共享：10%、20%、30%、40%、50%、60%、70%、80%。档位按|Approved co-creation projects use eight sharing tiers: 10%, 20%, 30%, 40%, 50%, 60%, 70% and 80%. The tier is determined by the 
原始开发定价|original development price
判断，不因开发折扣或专项抵扣变化。|, regardless of development discounts or service credit.
八档原价金额区间须依权威合同/现行正式规则显示；未核实的区间不会在此凭空填写。|The eight price bands require an authoritative contract or current formal rule. Unverified monetary bands are not invented here.
模块复售分配以真实已确认收入、最终可归属成本和有效合同确定的可共享净利润计算，不以项目报价或预测销量发放。推荐佣金独立依累计毛利润及实付收款核算，不能重复扣除成本。|Module resale sharing uses confirmed revenue, attributable final costs and contract-defined shareable net profit. Project quotations or forecast sales do not trigger payment. Referral commissions are accounted for separately using cumulative gross profit and actual collections, without counting costs twice.
权益与专项服务明细|ECV and special service details
权益值ECV、普通来源附带的500元/份一次性专项抵扣额度、客户已购服务包额度、购包赠ECV、推荐佣金、共创收益均为不同账目，不能相加为现金。|ECV, the one-time CNY 500 credit per eligible ordinary-source unit, purchased package balances, gifted ECV, referral commissions and co-creation earnings are separate ledgers and cannot be added together as cash.
正常合格来源ECV：每份一次性附带500元专项抵扣额，用完不恢复。|Eligible ordinary-source ECV: one-time CNY 500 credit per unit, not replenished after use.
购买专项服务包赠ECV：|ECV gifted with a purchased service package: 
不另外附带500元|no additional CNY 500 credit
；仅享订单本身规定服务额度。|; only the service amount specified in the order applies.
抵扣合格普通自营服务最高90%；折扣后定制开发最高50%；第三方成本不抵扣。|Credit covers up to 90% of eligible ordinary in-house services or 50% of discounted custom development; third-party costs are excluded.
服务额度使用和权益核销不得重复生成ECV。|Using service credit or redeeming entitlements must not generate duplicate ECV.
预计、待确认、已结算及冲回需要分别记账，本页面不作实际收入承诺。|Estimated, pending, settled and reversed amounts require separate records. This page does not promise actual income.
余额查询和账本导出须待权威后台身份、审计及权限接通。|Balance queries and ledger exports require the authoritative backend's identity, audit and permissions integration.
生态活动中心|Ecosystem activity center
抖音和X活动各三批10万有效名额，对应每人2、1、0.5权益值；各平台预算35万份。另有推荐人1、被推荐人2权益值的活动候选，推荐人本活动最多获20份，具体有效推荐条件须批准。|Douyin and X each plan three batches of 100,000 valid places, granting 2, 1 and 0.5 ECV per person, with a 350,000-unit budget per platform. A proposed referral activity grants 1 ECV to the referrer and 2 to the referred person, capped at 20 for each referrer; valid referral conditions require approval.
粉丝身份、关注资格、去重及风险核验必须由可信服务器完成，不相信浏览器自报粉丝状态。|Fan identity, follow eligibility, deduplication and risk checks require a trusted server, not browser-declared status.
当前|Currently 
未开放领取|claims are not open
，不采集平台授权密码，也不虚假显示资格已审核。|. Platform authorization passwords are not collected and eligibility approval is not fabricated.
生态治理与发展方向|Ecosystem governance and development direction
规划允许生态贡献者对产品方向、社区方案、服务优化与生态规则提出建议，未来按已批准权重使用权益值参与投票。|The plan allows contributors to suggest product directions, community solutions, service improvements and ecosystem rules, and later vote with ECV under approved weighting rules.
投票前须认证身份、确定议题与版本、验证资格、实行幂等防重并留下不可篡改审计。|Voting requires authenticated identity, a defined proposal and version, eligibility checks, idempotent duplicate prevention and tamper-evident audit records.
当前治理投票功能未上线，不显示虚构票数或投票成功回执。|Governance voting is not live. No invented vote counts or success receipts are displayed.
生态角色包括消费者、推荐者、开发者、共创发起人、合作伙伴。身份、优惠等级及利润共享资格分别认定。|Roles include consumers, referrers, developers, co-creation initiators and partners. Identity, discount tiers and profit-sharing eligibility are assessed separately.
客户项目与验收|Customer projects and acceptance
需求、版本预览、反馈、测试、验收与后续模块产品化使用统一项目体系。|Requirements, version previews, feedback, testing, acceptance and later module productization use one project framework.
浏览公开演示|Browse public demos
了解定制服务|Explore custom services
公开案例允许匿名预览；客户私有项目必须经可信身份与项目权限验证。|Public examples allow anonymous previews. Private customer projects require trusted identity and project authorization.
网页AI、Telegram、飞书反馈未来绑定同一客户/项目；未连接的渠道不得显示已发送。|Web AI, Telegram and Feishu feedback will bind to the same customer and project. Disconnected channels must not display a sent confirmation.
本静态页不收集客户资料、凭证、合同签字或付款。|This static page does not collect customer data, credentials, contract signatures or payments.
私有项目验收说明|Private project acceptance guidance
公共演示|Public demos
客户项目预览与验收|Customer project previews and acceptance
客户项目验收|Customer project acceptance
客户项目应能查看需求、合同、版本、开发测试、反馈、整改及验收记录。公开演示允许匿名，私有项目需要服务端认证、租户和项目权限。|Customer projects should expose requirements, contracts, versions, development tests, feedback, corrections and acceptance records. Public demos allow anonymous access; private projects require server-side authentication, tenant and project permissions.
网页AI、Telegram、飞书需通过同一客户身份的可信绑定与记录留证接入；当前静态页面不收集任何客户私有资料或伪造消息发送。|Web AI, Telegram and Feishu require trusted binding to one customer identity and durable records. This static page does not collect private customer data or fabricate message delivery.
玄钧云汇 · 共建、共治、共享 · 所有上线能力以正式验收为准|Xuanjun Yunhui · Co-build, co-govern and share · Availability requires formal acceptance
玄钧云汇 · 正式权益与订单以审核后的权威系统为准|Xuanjun Yunhui · Official entitlements and orders use the approved authoritative system
'''

TRANSLATIONS = dict(line.split('|', 1) for line in PAIRS.splitlines() if line)
TRANSLATIONS['定制开发折扣'] = 'Custom development discount'

def translate_fragment(source):
    """Translate text nodes; fail closed when Chinese wording has no mapping."""
    def text(match):
        raw = match[0]
        if not re.search('[\u4e00-\u9fff]', raw):
            return raw
        decoded = html.unescape(raw)
        if decoded in TRANSLATIONS:
            return html.escape(TRANSLATIONS[decoded], quote=False)
        if decoded.endswith(' | 玄钧云汇'):
            title = decoded.removesuffix(' | 玄钧云汇')
            if title in TRANSLATIONS:
                return html.escape(TRANSLATIONS[title]+' | Xuanjun Yunhui', quote=False)
        raise ValueError('MISSING_ENGLISH_TRANSLATION: '+repr(decoded))
    return re.sub(r'(?<=>)[^<]+(?=<)', text, source)
