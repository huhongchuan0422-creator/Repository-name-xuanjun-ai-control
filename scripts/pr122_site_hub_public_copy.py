"""Work-owned public wording adapter. Internal policy and ledger identifiers stay intact."""
import re
from html import escape

NAME = '云汇生态权益'
EN_NAME = 'Yunhui Ecosystem Rights'


def table(caption, headers, rows):
    return '<table><caption>'+escape(caption)+'</caption><thead><tr>'+''.join('<th scope="col">'+escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'


def wording(text, en=False):
    if en:
        return re.sub(r'\b(?:ECV|EVC)\b', EN_NAME, text)
    text = re.sub(r'(?:生态权益值|生态权益|权益值|ECV|EVC)', NAME, text)
    return text.replace('云汇'+NAME, NAME)


def content(relative, en=False):
    def t(zh, english): return english if en else zh
    def p(zh, english): return '<p>'+t(zh,english)+'</p>'
    tiers=table(t('云汇生态权益 · 六档定制开发折扣','Yunhui Ecosystem Rights · custom development tiers'),
        [t('符合条件的持有量','Eligible holdings'),t('定制开发折扣','Custom development price')],
        [(t(f'满 {n} 份',f'{n} units or more'),t(f'{d}折',f'{d*10}% of quoted fee')) for n,d in [(2,9),(10,8),(20,7),(40,6),(80,5),(150,4)]])
    caps=table(t('专项服务金额怎么用','How service credit applies'),[t('费用类型','Eligible fee'),t('优惠顺序','Order of benefits'),t('抵扣上限','Credit cap')],[
        (t('合格自营服务、部署及维护','Eligible in-house services, deployment and maintenance'),t('按合格费用计算','Applied to eligible fees'),'90%'),
        (t('合格定制开发','Eligible custom development'),t('先享等级折扣，再用专项金额','Tier discount first, then service credit'),'50%'),
        (t('第三方成本','Third-party costs'),t('独立列示，不参与抵扣','Shown separately; excluded'),t('不可抵扣','Not eligible'))])
    caveat=p('实际抵扣不超过可用余额；适用范围与资格以有效合同及核验结果为准。专项服务金额不能提现、转让或买卖，使用后不恢复，也不会再次赠送权益。','Actual credit is limited by the available balance, verified eligibility and contract. Service credit cannot be withdrawn, transferred or traded. Spent credit is not replenished and does not generate new rights.')
    example=p('例如：原开发报价6,000元，符合150份等级享4折，折后2,400元；如有足额合格专项余额，再抵扣1,200元，预计实付1,200元。第三方费用另计。','Example: a CNY 6,000 development quote becomes CNY 2,400 at the eligible 150-unit tier. With sufficient eligible credit, CNY 1,200 is offset and the estimated amount due is CNY 1,200. Third-party fees are separate.')
    pages={
      'ecosystem/tiers/index.html': (t('云汇生态权益，定制开发更从容。','Yunhui Ecosystem Rights for custom development.'),
        p('按符合条件的最高一档享受折扣，各档不叠加。等级折扣之后，还可按规则使用专项服务金额。','The highest eligible tier applies; tiers do not stack. Eligible service credit can be applied after the tier discount.')+tiers+caps+example+caveat),
      'ecosystem/profit-sharing/index.html':(t('共创成果，按约共享。','Share the results of co-creation.'),
        p('经审核并签约的共创模块，后续复用销售可按合同分享可共享净利润。持有云汇生态权益不自动获得收益共享资格。','Approved, contracted co-created modules may share eligible net profit from later reuse sales. Holding Yunhui Ecosystem Rights does not automatically grant sharing eligibility.')+
        table(t('共创模块 · 八档共享比例','Co-created modules · eight sharing tiers'),[t('档次','Tier'),t('可共享净利润比例','Share of eligible net profit'),t('适用条件','Eligibility')],[(str(i),f'{i*10}%',t('以有效合同确认','Confirmed in the effective contract')) for i in range(1,9)])+
        p('共享档位按原始开发定价确认，开发折扣与专项抵扣不降低对应档位。具体金额区间尚未确认，不在此公布。','The sharing tier is based on the original development quote; discounts and credit do not reduce that tier. Specific price bands have not been confirmed and are not published here.')+
        p('实际分配以有效合同及已核实的可共享净利润为准，不按项目报价或预测销量发放，不承诺固定收益。','Distribution follows the effective contract and verified eligible net profit, rather than quoted project fees or forecast sales. No fixed return is promised.')),
      'ecosystem/co-create/index.html':(t('把业务想法，做成共创成果。','Turn a business idea into shared work.'),
        p('从真实需求开始，共同确认范围、交付、验收与模块复用方式。开发报价单独沟通，以双方确认的方案及合同为准。','Start with a real need. Agree on scope, delivery, acceptance and module reuse. Development quotations are discussed individually and confirmed in the proposal and contract.')+
        table(t('共创项目流程','Co-creation process'),[t('阶段','Stage'),t('与你确认的内容','What we agree with you')],[(t(a,b),t(c,d)) for a,b,c,d in [('提出需求','Define the need','应用场景与预期成果','Use cases and intended outcomes'),('方案确认','Agree on the proposal','功能范围、报价与共享条款','Scope, quotation and sharing terms'),('预览与反馈','Preview and feedback','已审核版本及修改意见','Reviewed versions and requested changes'),('验收与复用','Acceptance and reuse','准确版本验收及合同约定的后续共享','Version-specific acceptance and contracted sharing')]])+
        p('共创发起人公开展示昵称。注册、登录、用户资料、通用权限及后台框架等玄钧AI实验室自研基础模块仍归实验室，不因用于客户项目而计为客户共创成果。','Initiators are displayed publicly by nickname. Shared registration, sign-in, profiles, permissions and administration frameworks developed by Xuanjun AI Lab remain its own work; using them in a customer project does not make them customer co-created assets.')),
      'ecosystem/ledger/index.html':(t('权益与专项金额，分开看清楚。','Understand rights and service credit separately.'),caps+caveat+
        p('正常合格贡献来源每份云汇生态权益一次性附带500元专项服务抵扣额；购买专项服务包获赠的权益不另附带500元。所购服务额度以订单为准，与赠送抵扣余额分别记账。','Each unit from eligible ordinary contributions includes a one-time CNY 500 service credit. Rights gifted with purchased service packages do not include this additional CNY 500. Purchased service allowances follow the order and are tracked separately from gifted credit.')),
      'ecosystem/activities/index.html':(t('参与共建，了解你的专属优惠。','Discover benefits for contributing.'),
        '<div class="notice" role="status">'+t('活动筹备中 · 当前未开放领取','Activities are being prepared · Claims are not open')+'</div>'+
        p('关注云汇生态活动，了解云汇生态权益与专项服务金额赠送安排。参与资格、名额和生效时间以正式活动规则为准。','Follow ecosystem activities for information about rights and service-credit gifts. Eligibility, places and opening dates follow the published activity rules.')+caps+
        p('正常合格贡献每份权益一次性附带500元专项服务抵扣额；服务包购买赠送权益不额外附带该金额。不是现金红包，也不能兑换现金。','Eligible ordinary contributions include a one-time CNY 500 service credit per unit. Rights gifted with service-package purchases do not include this additional credit. This is not a cash gift and cannot be redeemed for cash.')+caveat),
      'ecosystem/index.html':(t('共建共享，让贡献有回响。','Build together. Share what we create.'),
        p('客户、开发者与合作伙伴，一起打磨真实可用的产品。云汇生态权益记录合格贡献，开发优惠和共创收益资格分别确认。','Customers, developers and partners build useful products together. Yunhui Ecosystem Rights record eligible contributions; discounts and profit-sharing eligibility are assessed separately.')+tiers+caps+
        p('总量固定2,000万份，合法取得的权益长期有效，不转让、不买卖；不是虚拟货币、股权或固定收益产品。','The total is fixed at 20 million units. Lawfully acquired rights remain valid long term and cannot be transferred or traded. They are not cryptocurrency, equity or a fixed-return product.')),
    }
    if relative not in pages:return None
    title,body=pages[relative]
    links=''.join('<a class="btn" href="'+path+'">'+t(zh,english)+'</a>' for path,zh,english in [('/ecosystem/tiers/','等级与折扣','Tiers and discounts'),('/ecosystem/profit-sharing/','共创收益共享','Profit sharing'),('/ecosystem/activities/','活动与赠送说明','Activities and gifts'),('/ecosystem/co-create/','参与共创','Co-create')])
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
        cards=[('Up to 90%','Eligible in-house service, deployment and maintenance fees.'),('Tier discount + credit','Custom development: the highest eligible tier first, then credit up to 50% of the discounted eligible fee.'),('Know your gift','Eligible ordinary contributions include a one-time CNY 500 credit per unit. Service-package gifted rights exclude this extra credit.')]
        note='Credit is limited by your eligible balance. Third-party costs are excluded. No cash withdrawal. Eligibility and dates follow the activity rules.'
        cta='Explore activities and benefits'
    else:
        title='共建有礼，让好想法更轻松落地。'
        lead='了解专项服务金额赠送与云汇生态权益优惠。活动筹备中，当前未开放领取。'
        cards=[('最高抵扣90%','合格自营服务费、部署费及维护费，用专项服务金额抵扣。'),('等级折扣，再享抵扣','定制开发先享最高适用等级折扣，折后合格开发费再最高抵扣50%。'),('赠送规则，看得明白','正常合格贡献每份权益一次性附带500元专项抵扣额；服务包获赠权益不另附带该金额。')]
        note='抵扣不超过可用合格余额；第三方成本除外，不能提现。参与资格与开放时间以正式活动规则为准。'
        cta='查看活动与优惠规则'
    return '<section class="xj-discover xj-benefits" id="discover-benefits"><h2>'+title+'</h2><p>'+lead+'</p><div class="xj-discover-grid">'+''.join('<article class="xj-feature"><h3>'+a+'</h3><p>'+b+'</p></article>' for a,b in cards)+'</div><p>'+note+'</p><a class="button" href="/'+locale+'ecosystem/activities/">'+cta+'</a></section>'
