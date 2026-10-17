"""Work-owned public wording adapter. Internal policy and ledger identifiers stay intact."""
import re
from html import escape

NAME = '云汇生态权益'
EN_NAME = 'Yunhui Ecosystem Rights'


def table(caption, headers, rows):
    return '<div class="xj-table-scroll" tabindex="0" role="region" aria-label="'+escape(caption,quote=True)+'"><table><caption>'+escape(caption)+'</caption><thead><tr>'+''.join('<th scope="col">'+escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def wording(text, en=False):
    # Display text only: never rename resource URLs, IDs or ledger fields.
    parts=re.split(r'(<[^>]*>)',text)
    for i in range(0,len(parts),2):
        if en:
            parts[i]=re.sub(r'\b(?:ECV|EVC|ecosystem[- ]values?)\b', EN_NAME, parts[i], flags=re.I)
        else:
            parts[i]=re.sub(r'(?:云汇)?生态权益值|(?:云汇)?生态权益|ECV|EVC', NAME, parts[i])
    return ''.join(parts)


def content(relative, en=False):
    def t(zh, english): return english if en else zh
    def p(zh, english): return '<p>'+t(zh,english)+'</p>'
    tiers=table(t('云汇生态权益 · 六档定制开发折扣','Yunhui Ecosystem Rights · custom development tiers'),
        [t('权益值门槛','Eligible rights value'),t('定制开发折扣','Custom development price')],
        [(t(f'≥ {n}点权益值',f'≥ {n} rights-value points'),t(f'{d}折',f'{d*10}% of quoted fee')) for n,d in [(2,9),(10,8),(20,7),(40,6),(80,5),(150,4)]])
    caps=table(t('专项服务金额怎么用','How service credit applies'),[t('费用类型','Eligible fee'),t('优惠顺序','Order of benefits'),t('抵扣上限','Credit cap')],[
        (t('合格自营服务、部署及维护','Eligible in-house services, deployment and maintenance'),t('按合格费用计算','Applied to eligible fees'),'90%'),
        (t('合格定制开发','Eligible custom development'),t('先享等级折扣，再用专项金额','Tier discount first, then service credit'),'50%'),
        (t('第三方成本','Third-party costs'),t('独立列示，不参与抵扣','Shown separately; excluded'),t('不可抵扣','Not eligible'))])
    caveat=p('实际抵扣不超过可用余额；适用范围与资格以有效合同及核验结果为准。专项服务金额不能提现、转让或买卖，使用后不恢复，也不会再次赠送权益。','Actual credit is limited by the available balance, verified eligibility and contract. Service credit cannot be withdrawn, transferred or traded. Spent credit is not replenished and does not generate new rights.')
    example=p('例如：原开发报价6,000元，持有150点权益值，享4折，折后2,400元；如有足额合格专项余额，再抵扣1,200元，预计实付1,200元。第三方费用另计。','Example: a CNY 6,000 development quote becomes CNY 2,400 at the eligible threshold of 150 rights-value points. With sufficient eligible credit, CNY 1,200 is offset and the estimated amount due is CNY 1,200. Third-party fees are separate.')
    pages={
      'ecosystem/tiers/index.html': (t('云汇生态权益，定制开发更从容。','Yunhui Ecosystem Rights for custom development.'),
        p('按符合条件的最高一档享受折扣，各档不叠加。等级折扣之后，还可按规则使用专项服务金额。','The highest eligible tier applies; tiers do not stack. Eligible service credit can be applied after the tier discount.')+tiers+caps+example+caveat),
      'ecosystem/profit-sharing/index.html':(t('共创成果，按约共享。','Share the results of co-creation.'),
        p('经审核并签约的共创模块，后续复用销售可按合同分享可共享净利润。持有云汇生态权益不自动获得收益共享资格。','Approved, contracted co-created modules may share eligible net profit from later reuse sales. Holding Yunhui Ecosystem Rights does not automatically grant sharing eligibility.')+
        table(t('共创模块 · 八档共享比例','Co-created modules · eight sharing tiers'),[t('原始开发定价','Original development price'),t('持有权益值','Rights-value holdings'),t('可共享净利润比例','Share of eligible net profit')],[(t(f'≥ {i*1000:,}元',f'≥ CNY {i*1000:,}'),t(f'≥ {i*10}点权益值',f'≥ {i*10} rights-value points'),f'{i*10}%') for i in range(1,9)])+
        p('共享档位取原始开发定价与持有权益值两项条件共同满足的最高档。原始开发定价按折扣及专项抵扣前的开发费计算，不含第三方成本；开发折扣与专项抵扣不降低对应的原始开发定价。','The highest tier whose original development price and rights-value holding thresholds are both met applies. Original development pricing is calculated before discounts and service credit, excluding third-party costs; discounts and credit do not reduce that original price.')+
        p('实际分配以有效合同及已核实的可共享净利润为准，不按项目报价或预测销量发放，不承诺固定收益。','Distribution follows the effective contract and verified eligible net profit, rather than quoted project fees or forecast sales. No fixed return is promised.')),
      'ecosystem/co-create/index.html':(t('把业务想法，做成共创成果。','Turn a business idea into shared work.'),
        p('从真实需求开始，共同确认范围、交付、验收与模块复用方式。开发报价单独沟通，以双方确认的方案及合同为准。','Start with a real need. Agree on scope, delivery, acceptance and module reuse. Development quotations are discussed individually and confirmed in the proposal and contract.')+
        table(t('共创项目流程','Co-creation process'),[t('阶段','Stage'),t('与你确认的内容','What we agree with you')],[(t(a,b),t(c,d)) for a,b,c,d in [('提出需求','Define the need','应用场景与预期成果','Use cases and intended outcomes'),('方案确认','Agree on the proposal','功能范围、报价与共享条款','Scope, quotation and sharing terms'),('预览与反馈','Preview and feedback','已审核版本及修改意见','Reviewed versions and requested changes'),('验收与复用','Acceptance and reuse','准确版本验收及合同约定的后续共享','Version-specific acceptance and contracted sharing')]])+
        p('共创发起人公开展示昵称。注册、登录、用户资料、通用权限及后台框架等玄钧AI实验室自研基础模块仍归实验室，不因用于客户项目而计为客户共创成果。','Initiators are displayed publicly by nickname. Shared registration, sign-in, profiles, permissions and administration frameworks developed by Xuanjun AI Lab remain its own work; using them in a customer project does not make them customer co-created assets.')),
      'ecosystem/ledger/index.html':(t('权益与专项金额，分开看清楚。','Understand rights and service credit separately.'),caps+caveat+
        p('正常合格贡献来源：每取得1点权益值，一次性附带500元专项服务抵扣额；购买专项服务包获赠的权益不另附带500元。所购服务额度以订单为准，与赠送抵扣余额分别记账。','Each rights-value point from eligible ordinary contributions includes a one-time CNY 500 service credit. Rights gifted with purchased service packages do not include this additional CNY 500. Purchased service allowances follow the order and are tracked separately from gifted credit.')),
      'ecosystem/activities/index.html':(t('参与共建，了解你的专属优惠。','Discover benefits for contributing.'),
        '<div class="notice" role="status">'+t('活动筹备中 · 当前未开放领取','Activities are being prepared · Claims are not open')+'</div>'+
        p('关注云汇生态活动，了解云汇生态权益与专项服务金额赠送安排。参与资格、名额和生效时间以正式活动规则为准。','Follow ecosystem activities for information about rights and service-credit gifts. Eligibility, places and opening dates follow the published activity rules.')+caps+
        p('正常合格贡献来源：每取得1点权益值，一次性附带500元专项服务抵扣额；服务包购买赠送权益不额外附带该金额。不是现金红包，也不能兑换现金。','Eligible ordinary contributions include a one-time CNY 500 service credit per rights-value point. Rights gifted with service-package purchases do not include this additional credit. This is not a cash gift and cannot be redeemed for cash.')+caveat),
      'ecosystem/index.html':(t('共建共享，让贡献有回响。','Build together. Share what we create.'),
        p('客户、开发者与合作伙伴，一起打磨真实可用的产品。云汇生态权益记录合格贡献，开发优惠和共创收益资格分别确认。','Customers, developers and partners build useful products together. Yunhui Ecosystem Rights record eligible contributions; discounts and profit-sharing eligibility are assessed separately.')+tiers+caps+
        p('权益值总量固定2,000万点，合法取得的权益长期有效，不转让、不买卖；不是虚拟货币、股权或固定收益产品。','The total rights value is fixed at 20 million points. Lawfully acquired rights remain valid long term and cannot be transferred or traded. They are not cryptocurrency, equity or a fixed-return product.')),
    }
    if relative not in pages:return None
    title,body=pages[relative]
    links=''.join('<a class="btn" href="'+('/en'+path if en else path)+'">'+t(zh,english)+'</a>' for path,zh,english in [('/ecosystem/tiers/','等级与折扣','Tiers and discounts'),('/ecosystem/profit-sharing/','共创收益共享','Profit sharing'),('/ecosystem/activities/','活动与赠送说明','Activities and gifts'),('/ecosystem/co-create/','参与共创','Co-create')])
    return '<main><section class="hero"><h1>'+title+'</h1>'+body+'<div class="actions">'+links+'</div></section></main>'


def public_page(text, relative, en=False):
    main=content(relative,en)
    if main:
        text=re.sub(r'<main\b.*?</main>',lambda _:main,text,count=1,flags=re.S)
        title=re.search(r'<h1>(.*?)</h1>',main)[1]
        text=re.sub(r'<title>.*?</title>',lambda _:'<title>'+title+' | '+('Xuanjun Yunhui' if en else '玄钧云汇')+'</title>',text,count=1,flags=re.S)
    if relative=='marketplace/index.html':
        # Cost and margin are internal. The public estimate always passes UNKNOWN.
        text=re.sub(r'<label>[^<]*<input id="directCost"[^>]*></label>', '',text)
        text=text.replace('第三方成本不得抵扣，推荐佣金只对实际可确认正毛利依权威规则产生。','第三方成本独立列示，不参与专项抵扣。')
        text=text.replace('Third-party costs cannot be offset. Referral commissions require verified positive gross profit under the authoritative rules.','Third-party costs are shown separately and cannot be offset by service credit.')
    return wording(text,en)


def home_promotion(locale):
    en=locale=='en/'
    if en:
        title='More room to build. More ways to save.'
        lead='Explore service-credit gifts and Yunhui Ecosystem Rights. Activities are being prepared; claims are not open.'
        cards=[('Up to 90%','Eligible in-house service, deployment and maintenance fees.'),('Tier discount + credit','Custom development: the highest eligible tier first, then credit up to 50% of the discounted eligible fee.'),('Know your gift','Eligible ordinary contributions include a one-time CNY 500 credit per rights-value point. Service-package gifted rights exclude this extra credit.')]
        note='Credit is limited by your eligible balance. Third-party costs are excluded. No cash withdrawal. Eligibility and dates follow the activity rules.'
        cta='Explore activities and benefits'
    else:
        title='共建有礼，让好想法更轻松落地。'
        lead='了解专项服务金额赠送与云汇生态权益优惠。活动筹备中，当前未开放领取。'
        cards=[('最高抵扣90%','合格自营服务费、部署费及维护费，用专项服务金额抵扣。'),('等级折扣，再享抵扣','定制开发先享最高适用等级折扣，折后合格开发费再最高抵扣50%。'),('赠送规则，看得明白','正常合格贡献来源：每取得1点权益值，一次性附带500元专项抵扣额；服务包获赠权益不另附带该金额。')]
        note='抵扣不超过可用合格余额；第三方成本除外，不能提现。参与资格与开放时间以正式活动规则为准。'
        cta='查看活动与优惠规则'
    return '<section class="xj-discover xj-benefits" id="discover-benefits"><h2>'+title+'</h2><p>'+lead+'</p><div class="xj-discover-grid">'+''.join('<article class="xj-feature"><h3>'+a+'</h3><p>'+b+'</p></article>' for a,b in cards)+'</div><p>'+note+'</p><a class="button" href="/'+locale+'ecosystem/activities/">'+cta+'</a></section>'


def legacy_public_wording(text, en=False):
    """Apply the approved public name to legacy copy without modifying scripts or URLs."""
    parts=re.split(r'(<script\b.*?</script>|<style\b.*?</style>)',text,flags=re.S|re.I)
    for i in range(0,len(parts),2):
        parts[i]=wording(parts[i],en)
        parts[i]=parts[i].replace('The documented Yunhui Ecosystem Rights design total is 10 million; a design total is not evidence of issuance.','Yunhui Ecosystem Rights have a fixed total rights value of 20 million points; the total is not evidence of issuance.')
        parts[i]=parts[i].replace('文档所述云汇生态权益规则设计总量为1000万；规则总量不等于已发放。','云汇生态权益总量固定2,000万点权益值；总量不等于已发放数量。')
    return ''.join(parts)


def _reviewed_page_copy_fragment(text, relative):
    """Narrow public presentation corrections, matched to reviewed HTML evidence.

    No routes, scripts, fees, entitlement calculations or readiness gates are created.
    HTML aliases use the same route key. Unrelated pages remain byte-for-byte intact.
    """
    route=relative
    en=route.startswith('en/')
    if route.startswith(('en/','zh-cn/')):route=route.split('/',1)[1]
    route=re.sub(r'(?:/index\.html|\.html)$','',route)
    if route=='index':route=''
    if en and route.startswith('guides'):
        text=text.replace('Use concept or subject to delivery verification demonstrations for inputs, flow, confirmation and outputs without invented customer data.',
                          'Use concept demonstrations or internal-validation examples to explain inputs, flow, confirmation and outputs without invented customer data.')
    if en and route=='terms':
        text=text.replace('Planned or subject to delivery verification capabilities are not automatically production-ready.',
                          'Planned capabilities and those awaiting delivery verification are not automatically production-ready.')
    if en and route=='about':
        text=text.replace('No unlimited guarantee of security or automation is made.',
                          'Important actions retain confirmation checkpoints, and exceptions can be traced and handled.')
    if route=='labs' or route.startswith('labs/'):
        replacements={
            '本次官网任务不调整权益总量、分池、门槛或释放规则；规则设计不等于已发放。':'权益总量、分池、门槛与释放安排以有效规则为准；规则设计不等于已发放。',
            '具体分池、门槛、释放系数及创始人同步释放规则不由本次官网任务调整。':'具体分池、门槛、释放系数及创始人同步释放安排以有效规则为准。',
            'Detailed total supply, pools, thresholds and release rules are not changed by this website task.':'Total supply, pools, thresholds and release arrangements follow the effective rules.',
            'Detailed ratios, thresholds, release coefficients and founder-linked release are not changed by this website task.':'Detailed ratios, thresholds, release coefficients and founder-linked release follow the effective rules.',
            'Yunhui Ecosystem Rights records verified contributions':'Yunhui Ecosystem Rights record verified contributions',
            'It cannot be transferred or traded, and valid records':'They cannot be transferred or traded, and valid records',
            'Record verified contributions; values are non-transferable, non-tradable':'Record verified contributions; rights are non-transferable and non-tradable',
            '云汇生态权益总量固定2,000万份':'云汇生态权益总量固定2,000万点权益值',
            'fixed total of 20 million units':'fixed total rights value of 20 million points',
        }
        for old,new in replacements.items():text=text.replace(old,new)
    if route=='ecosystem/governance':
        text=text.replace('留下不可篡改审计','保留可核验、可追溯的审计记录')
        text=text.replace('tamper-evident audit records','verifiable, traceable audit records')
    # Empty related sections are omitted rather than populated with invented guides.
    if route.startswith('solutions/'):
        text=re.sub(r'<section><h2>(?:创作流程详情|Creative workflows)</h2><div class="related">\s*</div></section>','',text)
        io_copy={
            'community-commerce':('Business rules and authorized data','Workflow proposals and reconciliation structures'),
            'content-operations':('Topics, source materials and publishing requirements','Content drafts, review results and scheduling records'),
            'creative-digital-content':('Outlines, character settings and creative requirements','Chapter versions, review records and exported content'),
            'customer-service-sales':('Inquiry content','Requirement summaries, follow-up tasks and handling records'),
            'data-observation':('Authorized data sources','Periodic summaries, exception lists and observation records'),
            'enterprise-workflow':('Request information and approval rules','Task status, reminders and archived results'),
        }
        key=route.removeprefix('solutions/')
        if en and key in io_copy:
            incoming,outgoing=io_copy[key]
            text=text.replace('<h2>Input</h2><p>Business rules, authorized data and acceptance criteria.</p>','<h2>Input</h2><p>'+incoming+'</p>')
            text=text.replace('<h2>Output</h2><p>A defined workflow, output records and an acceptance result.</p>','<h2>Output</h2><p>'+outgoing+'</p>')
    if route.startswith('capabilities/'):
        text=re.sub(r'<section><h2>(?:审核与编辑指南|Review and editing guides)</h2><div class="related">\s*</div></section>','',text)
        labels={'customer-communication':'客户与沟通','workflow-collaboration':'流程与协作','content-creation':'内容与创作','data-reporting':'数据与报表','system-connections':'系统连接','local-tools':'本地小工具'}
        key=route.removeprefix('capabilities/')
        if not en and key in labels:
            old=key.replace('-',' ');new=labels[key]
            text=text.replace('<title>'+old+' | 玄钧云汇</title>','<title>'+new+' | 玄钧云汇</title>')
            text=text.replace('<span aria-current="page">'+old+'</span>','<span aria-current="page">'+new+'</span>')
        if not en and key=='content-planning-review':
            old='<dt>费用状态</dt><dd>平台发布权限按实际获批范围另行确认</dd>'
            text=text.replace(old,'<dt>费用状态</dt><dd>待核定</dd>')
            dependency='<h2>系统依赖</h2><p>账号、地区、权限、部署方式和授权数据源在交付前核对。</p>'
            text=text.replace(dependency,dependency[:-4]+'平台发布权限按实际获批范围另行确认。</p>')
    if route=='':
        # Keep existing real destinations while describing what they actually show.
        replacements={
            '成熟项目案例':'场景演示案例','Completed project cases':'Scenario demonstrations',
            '查看成熟案例':'查看场景演示','Explore completed work':'Explore scenario demos',
            '按实际验收状态查看案例；演示项目不视为已完成交付。':'按场景浏览演示方案；演示不代表已完成的客户交付。',
            'Check actual acceptance status. Demo projects are not completed deliveries.':'Browse demonstration scenarios. Demos do not represent completed customer deliveries.',
            '产品发展路线':'项目流程与接入说明','Product roadmap':'Project workflow and access',
            '按真实开发与验收记录查看进展，不使用虚构完成率。':'了解需求、预览、验收流程及私有项目接入条件。',
            'Follow development and acceptance records without invented completion percentages.':'Review requirements, preview and acceptance steps, and private-project access conditions.',
            '了解产品进展':'查看项目接入说明','Explore the roadmap':'View project access guidance',
        }
        def repair_work_section(match):
            section=match[0]
            for old,new in replacements.items():section=section.replace(old,new)
            return section
        text=re.sub(r'<section class="xj-discover" id="discover-work">.*?</section>',repair_work_section,text,flags=re.S)
    return text


def reviewed_page_copy(text, relative):
    # Script/style bytes are outside public wording scope, even for matching strings.
    parts=re.split(r'(<script\b.*?</script>|<style\b.*?</style>)',text,flags=re.S|re.I)
    for i in range(0,len(parts),2):parts[i]=_reviewed_page_copy_fragment(parts[i],relative)
    return ''.join(parts)


def localize_hub_links(text, locale):
    """Localize content routes only; retain the explicitly Chinese role demos."""
    if locale not in ('zh-cn/','en/'):return text
    return re.sub(r'(<main\b.*?</main>)',lambda m:re.sub(r'href="/(marketplace|ecosystem|customer|visual|custom-ai)((?:/[^"#]*)?)"',lambda n:'href="/'+locale+n[1]+n[2]+'"' if not n[2].startswith(('/community-local-e2e/','/community-payment/merchant-dashboard/')) else n[0],m[0]),text,flags=re.S)
