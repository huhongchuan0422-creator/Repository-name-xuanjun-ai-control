"""Customer-facing navigation and home presentation; no production writes."""
import re
from scripts.pr122_site_hub_public_copy import wording, home_promotion

CSS = '''
/* Keep the disclosure control stationary; rotate only its glyph. */
.primary-nav .nav-group{flex-wrap:nowrap;column-gap:5px}
.primary-nav .nav-group>button{display:flex;align-items:center;justify-content:flex-start;min-height:28px;height:28px;line-height:1;transform:none!important}
.primary-nav .nav-group>button span{display:block;line-height:1;transition:transform .16s ease}
.primary-nav .nav-group>button[aria-expanded=true] span{transform:rotate(180deg)}
.primary-nav .nav-panel{max-height:min(65vh,560px);overflow:auto;overscroll-behavior:contain}
.site-header .nav-group>button:focus-visible{outline-offset:2px}
.xj-discover{padding:72px 0}.xj-discover>h2{font-size:clamp(30px,4vw,48px);letter-spacing:-.03em;line-height:1.15;margin:0 0 14px}
.xj-discover>p{max-width:700px;color:var(--muted);font-size:18px;margin:0 0 30px}
.xj-discover-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
.xj-feature{background:#f5f6f8;border:1px solid #e6e9ee;border-radius:24px;padding:32px;display:flex;flex-direction:column;gap:14px;min-width:0}
.xj-feature h3{font-size:25px;line-height:1.2;letter-spacing:-.02em;margin:0}.xj-feature p{color:var(--muted);margin:0}.xj-feature a{color:#1659bd;font-weight:650;margin-top:auto;padding-top:12px;min-height:44px}
.xj-feature small{font-size:12px;color:var(--muted)}.xj-discover .actions{align-items:center}
@media(max-width:1180px){.site-header{grid-template-columns:minmax(0,1fr) auto auto;gap:10px;min-height:76px}.site-header .brand{grid-column:1;grid-row:1;min-width:0}.site-header .mobile-toggle{grid-column:2;grid-row:1}.site-header .header-actions{grid-column:3;grid-row:1;display:flex;justify-self:end}.site-header .header-actions>.button,.site-header .workspace-status{display:none}.site-header .primary-nav{top:100%;max-height:calc(100dvh - 90px);overflow:auto}.primary-nav .nav-group{display:flex;flex-wrap:wrap}.primary-nav .nav-group>a{flex:1}.primary-nav .nav-group>.nav-panel{flex-basis:100%;max-height:none;overflow:visible}.xj-discover-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:780px){.site-header{padding:10px 12px;gap:6px}.site-header .brand{gap:6px}.site-header .brand img{width:34px;height:34px}.site-header .brand b{font-size:15px}.site-header .brand small{display:none}.site-header .mobile-toggle,.site-header .language>button{padding:8px;font-size:13px;min-height:44px;white-space:nowrap}.xj-discover{padding:44px 0}.xj-discover-grid{grid-template-columns:1fr}.xj-feature{padding:26px}.hero .actions{display:flex;flex-wrap:wrap}.hero .actions .button{width:auto}.hero h1{letter-spacing:-.03em}}
@media(prefers-reduced-motion:reduce){.primary-nav .nav-group>button span{transition:none}}
'''

def disclosures(text):
    text = re.sub(r'(<button\b[^>]*aria-label="[^"]*"[^>]*>)⌄(</button>)', r'\1<span aria-hidden="true">⌄</span>\2', text)
    text = text.replace('aria-controls="primary-nav">打开导航', 'aria-label="打开导航" aria-controls="primary-nav">菜单')
    text = text.replace('aria-controls="primary-nav">Open navigation', 'aria-label="Open navigation" aria-controls="primary-nav">Menu')
    return text

def home(text, locale):
    en = locale == 'en/'
    def t(zh, english): return english if en else zh
    def link(path):
        if path.startswith('showcase/'):return '/showcase/'+('en/' if en else '')+path.removeprefix('showcase/')
        return '/' + locale + path
    # Keep the established hero and all original business links, change its two CTAs.
    first = re.search(r'<section class="hero">.*?</section>', text, re.S)
    if first:
        hero = first[0]
        hero = re.sub(r'<h1>.*?</h1>', '<h1>'+t('让AI，真正用在业务里。','AI that fits the way you work.')+'</h1>', hero, count=1, flags=re.S)
        hero = re.sub(r'<p class="lead">.*?</p>', '<p class="lead">'+t('选配模块、体验方案，或定制所需能力。从一个具体需求开始，把范围、费用和交付说清楚。','Choose modules, explore solutions or request a custom capability. Start with a concrete need, with clear scope, fees and delivery.')+'</p>', hero, count=1, flags=re.S)
        actions = ('<div class="actions"><a class="button" href="'+link('marketplace/')+'">'+t('浏览产品与服务','Browse products and services')+'</a><a class="button secondary" href="'+link('visual/')+'">'+t('体验可视化方案','Explore visual solutions')+'</a></div>')
        hero = re.sub(r'<div class="actions">.*?</div>', lambda _: actions, hero, count=1, flags=re.S)
        text = text[:first.start()] + hero + text[first.end():]
    groups = [
        ('products', t('按需选择，让业务先跑起来。','Choose what your business needs.'), t('选配已有模块，或从一个明确需求开始定制。费用与开放状态在详情中说明。','Choose existing modules or start with a defined custom requirement. Each detail page explains fees and availability.'), [
            ('SaaS 产品与模块','SaaS products and modules','查看用途、依赖和服务方式，选择适合你的功能。','Review functions, dependencies and service options.','marketplace/','浏览产品与服务','Browse products and services'),
            ('功能选配','Module options','按业务组合模块，分别确认订阅、买断及第三方费用。','Combine modules and confirm subscription, one-time and third-party fees.','marketplace/modules/','查看获准上架的模块','Explore admitted modules'),
            ('定制开发','Custom development','先明确需求与验收，再确定开发和持续服务费用。','Agree on scope and acceptance before development and ongoing service fees.','custom-ai','了解定制与交付','Explore custom delivery')]),
        ('visual', t('先体验，再判断是否适合。','Experience the workflow first.'), t('从具体业务场景看功能如何协作。演示中的商家、订单和付款均为模拟。','See how functions work together. Demo merchants, orders and payments are simulated.'), [
            ('产品可视化中心','Product visual center','把业务流程、角色与功能放在一起看。','Explore business workflows, roles and capabilities together.','visual/','体验可视化方案','Explore visual solutions'),
            ('社区分账演示','Community payment demo','从消费者付款到商家、社区和平台，查看多角色协作。','Follow the consumer, merchant, community and platform workflow.','visual/community-payment/','选择角色体验','Explore demo roles'),
            ('行业案例','Industry examples','按场景比较方案，区分概念示例与可交付能力。','Compare scenarios with clear concept and delivery status.','visual/catalog/','查看行业案例','Explore industry examples')]),
        ('work', t('作品，在持续生长。','Work that keeps evolving.'), t('查看已验收案例、正在开发的项目和有记录的发展路线。公开展示以已审核版本为准。','Explore accepted work, active projects and an evidenced roadmap. Public demonstrations use reviewed versions.'), [
            ('成熟项目案例','Completed project cases','按实际验收状态查看案例；演示项目不视为已完成交付。','Check actual acceptance status. Demo projects are not completed deliveries.','visual/catalog/','查看成熟案例','Explore completed work'),
            ('正在开发的项目','Projects in development','每个项目独立展示，持续增加已审核的页面和角色。','Each project has its own space for reviewed pages and roles.','visual/community-payment/','查看开发中的作品','Explore active projects'),
            ('产品发展路线','Product roadmap','按真实开发与验收记录查看进展，不使用虚构完成率。','Follow development and acceptance records without invented completion percentages.','customer/projects/','了解产品进展','Explore the roadmap')]),
        ('ecosystem', t('共创生态，让贡献有记录。','Co-create with a clear record of contribution.'), t('了解共建共享、开发优惠与共创规则。权益、专项服务金额和收益资格分别认定。','Explore contributions, development discounts and co-creation rules. Rights, service credit and sharing eligibility are assessed separately.'), [
            ('共建共享','Co-build and share','客户、开发者和合作伙伴，按明确规则参与建设。','Customers, developers and partners contribute under defined rules.','ecosystem/','进入共建共享','Explore the ecosystem'),
            ('权益等级与开发折扣','ECV tiers and development discounts','查看六档折扣，以及普通自营服务90%、折后定制开发50%的专项抵扣上限。','Review six discount tiers and service-credit caps: 90% for eligible in-house services and 50% for discounted custom development.','ecosystem/tiers/','了解权益与折扣','Explore tiers and discounts'),
            ('共创项目广场','Co-creation projects','浏览项目规则，了解模块复用与合同约定的收益共享。','Explore projects, module reuse and contract-based profit sharing.','ecosystem/co-create/','查看共创项目与活动','Explore projects and activities')]),
        ('delivery', t('已有项目，从这里继续。','Continue your existing project.'), t('项目、版本、反馈与验收各有入口。私有项目须验证身份与项目权限，当前页面说明接入条件。','Find project and version acceptance guidance. Private projects require verified identity and project permissions; current pages explain access conditions.'), [
            ('客户项目中心','Customer project center','了解需求、开发、测试与交付记录如何管理。','Understand requirements, development, testing and delivery records.','customer/projects/','查看项目中心说明','View project access guidance'),
            ('预览与验收','Preview and acceptance','了解版本预览、反馈与验收流程。','Understand version previews, feedback and acceptance.','customer/projects/acceptance/','查看验收流程','View acceptance guidance'),
            ('联系玄钧','Contact Xuanjun','从一个具体问题开始，确认方案与下一步。','Start with a concrete problem and agree on next steps.','contact','描述我的需求','Describe my need')])]
    sections = []
    for key, title, desc, cards in groups:
        items = ''.join('<article class="xj-feature"><h3>'+t(a,b)+'</h3><p>'+t(c,d)+'</p><a href="'+link(url)+'">'+t(e,f)+' →</a></article>' for a,b,c,d,url,e,f in cards)
        sections.append('<section class="xj-discover" id="discover-'+key+'"><h2>'+title+'</h2><p>'+desc+'</p><div class="xj-discover-grid">'+items+'</div></section>')
    # Place the business discovery sections immediately after the established hero.
    first = re.search(r'<section class="hero">.*?</section>', text, re.S)
    at = first.end() if first else text.index('<main>')+6
    end = text.index('</main>', at)
    more = '<details class="xj-more"><summary>'+t('更多业务场景与服务说明','More business scenarios and service guidance')+'</summary>'+text[at:end]+'</details>'
    return wording(text[:at]+home_promotion(locale)+''.join(sections)+more+text[end:],en)
