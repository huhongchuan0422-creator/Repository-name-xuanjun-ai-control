#!/usr/bin/env python3
"""Build an isolated, review-only site overlay. Never activates a release."""
import argparse
import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.pr122_site_hub_public_copy import public_page, legacy_public_wording, reviewed_page_copy, localize_hub_links, project_public_brand
from scripts.pr122_site_hub_english import translate_fragment
from scripts.pr122_site_hub_experience import CSS as EXPERIENCE_CSS, disclosures, home as improve_home
from scripts.pr122_website_release import write_csp_metadata, Deadline

SOURCE_HASH = '74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63'
ICP_NUMBER = '渝ICP备2026024862号'
ICP_URL = 'https://beian.miit.gov.cn/'

def icp_footer(text):
    """Keep the Owner-confirmed registration in the established site footer."""
    footer=re.search(r'<footer\b.*?</footer>',text,re.S)
    if footer is None:raise ValueError('OFFICIAL_SITE_FOOTER_MISSING')
    link='<p class="fineprint" data-site-icp="2026024862"><a href="'+ICP_URL+'" target="_blank" rel="noopener noreferrer">'+ICP_NUMBER+'</a></p>'
    if 'data-site-icp=' in footer[0]:
        if footer[0].count(link)!=1:raise ValueError('ICP_FOOTER_DRIFT')
        return text
    if ICP_NUMBER in footer[0]:raise ValueError('UNEXPECTED_EXISTING_ICP_MARKUP')
    return text[:footer.end()-9]+link+text[footer.end()-9:]

MENUS = [
    ('solutions', [('产品可视化中心', '/visual/'), ('行业案例', '/visual/catalog/')]),
    ('capabilities', [('SaaS产品目录', '/marketplace/modules/'), ('功能选配', '/marketplace/modules/'), ('产品与购买', '/marketplace/')]),
    ('custom-ai', [('社区分账演示', '/visual/community-payment/'), ('定制开发服务', '/custom-ai'), ('客户项目中心', '/customer/projects/'), ('项目预览与验收', '/customer/projects/acceptance/')]),
    ('labs', [('共建共享', '/ecosystem/'), ('权益等级与开发折扣', '/ecosystem/tiers/'), ('共创项目广场', '/ecosystem/co-create/'), ('共创收益共享', '/ecosystem/profit-sharing/'), ('权益及专项金额说明', '/ecosystem/ledger/'), ('生态活动', '/ecosystem/activities/'), ('生态治理', '/ecosystem/governance/')]),
]
EN = {'产品可视化中心':'Product visual center', '行业案例':'Industry examples', '社区分账演示':'Community payment demo', 'SaaS产品目录':'SaaS catalog', '功能选配':'Module options', '产品与购买':'Products and purchase', '共建共享':'Co-build and share', '权益等级与开发折扣':'Yunhui Ecosystem Rights and development discounts', '定制开发服务':'Custom development', '客户项目中心':'Customer projects', '项目预览与验收':'Preview and acceptance', '共创项目广场':'Co-creation projects'}
EN.update({'共创收益共享':'Co-creation profit sharing','权益及专项金额说明':'Rights and service-credit guidance','生态活动':'Ecosystem activities','生态治理':'Ecosystem governance'})
CSS = '''/* Verified selectors: live apex and pinned Work V2 source. */
.primary-nav .nav-group{display:flex;flex-wrap:wrap;column-gap:5px}.primary-nav .nav-group>a{padding-right:0;flex:0 1 auto}.primary-nav .nav-group>button{width:24px;padding:0;text-align:left;flex:none}.primary-nav .nav-panel{flex-basis:100%}
.xj-hub{padding:36px 0 60px}.xj-hub .hero{display:block;min-height:0;padding:28px;background:#fff;border:1px solid #dce5f1;border-radius:18px;margin:20px 0}.xj-hub .hero h1{font-size:clamp(28px,5vw,48px)}.xj-hub .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:16px}.xj-hub .card{min-height:0;margin:10px 0;padding:22px}.xj-hub .card h2{font-size:22px}.xj-hub .btn{display:inline-block;padding:10px 16px;background:#2057d4;color:white;border-radius:10px;margin:6px}.xj-hub{overflow-wrap:anywhere}.xj-hub select,.xj-hub button{max-width:100%;white-space:normal}.xj-hub input,.xj-hub select{width:100%;min-width:0}.xj-hub .btn{max-width:100%;margin:6px 0;white-space:normal}.xj-hub input{max-width:100%;padding:8px;border:1px solid #abbcd4;border-radius:6px}.xj-hub label{display:block;margin:12px 0}.xj-hub .xj-table-scroll{width:100%;max-width:100%;overflow-x:auto}.xj-hub .xj-table-scroll table{display:table;table-layout:fixed;width:100%;min-width:420px}.xj-hub .xj-table-scroll caption{white-space:normal;overflow-wrap:normal}.xj-hub .xj-table-scroll:focus-visible{outline:3px solid #75a7ff;outline-offset:3px}.xj-hub th,.xj-hub td{padding:14px;text-align:left;border-bottom:1px solid #e6e9ee;white-space:normal;overflow-wrap:break-word}.xj-hub caption{text-align:left;font-size:20px;font-weight:650;padding:20px 0 12px}.xj-hub table{width:100%;border-collapse:collapse;margin:22px 0}.xj-hub .hero p{max-width:76ch;line-height:1.8;margin:18px 0}.xj-hub .actions{display:flex;flex-wrap:wrap;gap:8px}.xj-hub a:focus-visible,.xj-hub button:focus-visible,.xj-hub input:focus-visible{outline:3px solid #75a7ff;outline-offset:3px}
'''

def menu_patch(text):
    if 'id="primary-nav"' not in text:
        return text
    english = bool(re.search(r'<html[^>]*lang="en"', text))
    first = re.search(r'<div class="nav-group"><a href="([^"]+)/solutions">', text)
    prefix = first[1] if first else ''
    for key, entries in MENUS:
        link = prefix + '/' + key
        items = ''.join('<a href="%s">%s</a>' % (prefix+url, EN[label] if english else label) for label,url in entries)
        pattern = r'(<div class="nav-group"><a href="'+re.escape(link)+r'">.*?<div class="nav-panel">)(.*?)(</div></div>)'
        if key not in ('custom-ai','labs'):
            text, count = re.subn(pattern, lambda m:m[1]+m[2]+items+m[3], text, count=1, flags=re.S)
        else:
            names = '(Custom &amp; Delivery|Custom & Delivery|定制与交付)' if key=='custom-ai' else '(Co-creation|共创生态)'
            pattern = r'<a href="'+re.escape(link)+r'">'+names+r'</a>'
            def custom(m):
                label = ('Expand Custom &amp; Delivery menu' if english else '展开定制与交付菜单') if key=='custom-ai' else ('Expand Co-creation menu' if english else '展开共创生态菜单')
                return '<div class="nav-group">'+m[0]+'<button type="button" aria-expanded="false" aria-label="'+label+'">⌄</button><div class="nav-panel">'+items+'</div></div>'
            text, count = re.subn(pattern, custom, text, count=1)
        if count != 1:
            raise ValueError('UNEXPECTED_NAV_STRUCTURE:'+link)
    return disclosures(icp_footer(text.replace('</head>', '<link rel="stylesheet" href="/assets/xuanjun-site-integration.css"></head>', 1)))

def integrate_mobile_navigation(root, public):
    """Add the exact preview files before this build's final CSP and hash pass."""
    from scripts.pr122_community_experience_package import collect_mobile_files, TARGET
    from scripts.pr122_site_hub_unified_package import derive_entry_navigation
    files,provenance=collect_mobile_files(root,derive_navigation=True)
    allowed={TARGET+n for n in ('index.html','merchant.html','community.html','beneficiary.html','platform.html','experience.css','experience.js','role.css','role.js')}
    if set(files)!=allowed:raise ValueError('NAVIGATION_FILE_SET')
    declared={r['path']:r for r in provenance['files']}
    if len(provenance['files'])!=9 or set(declared)!=allowed:raise ValueError('NAVIGATION_MANIFEST_SET')
    for name,data in files.items():
        if (public/name).exists():raise ValueError('NAVIGATION_NO_OVERWRITE:'+name)
        if len(data)!=declared[name]['size'] or hashlib.sha256(data).hexdigest()!=declared[name]['sha256']:raise ValueError('NAVIGATION_FILE_HASH')
    dependencies=provenance['dependencies']
    if len(dependencies)!=1 or dependencies[0]['path']!='visual/community-local-e2e/app.js':raise ValueError('NAVIGATION_DEPENDENCY_SET')
    if hashlib.sha256((public/dependencies[0]['path']).read_bytes()).hexdigest()!=dependencies[0]['sha256']:raise ValueError('NAVIGATION_DEPENDENCY_HASH')
    entries={}
    for locale in ('','zh-cn/','en/'):
        path=public/(locale+'visual/community-payment/index.html')
        entries[path]=derive_entry_navigation(path.read_text(),locale)
    # All inputs and destinations validated before the first output mutation.
    for name,data in files.items():
        target=public/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    for path,text in entries.items():path.write_text(text)
    provenance=dict(provenance)
    provenance['integration_mechanisms']=[{'path':'scripts/'+name,'sha256':hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()} for name in ('pr122_site_hub_stage.py','pr122_site_hub_unified_package.py')]
    return provenance

def build(root, source, output, fixture=None, derive_navigation=False, delivery_review=False):
    if output.exists():
        raise ValueError('OUTPUT_ALREADY_EXISTS')
    if fixture is None and hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError('SOURCE_ARCHIVE_HASH_MISMATCH')
    output.mkdir(parents=True)
    public = output/'public'
    public.mkdir()
    if fixture is not None:
        # Hosted browser fixture is explicitly smaller than the original site.
        # It cannot claim full-source acceptance or become a production bundle.
        pins=json.loads((fixture/'PINS.json').read_text())
        for name,digest in pins.items():
            payload=(fixture/name).read_bytes()
            if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('FIXTURE_HASH_MISMATCH')
            target=public/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    else:
      with tarfile.open(source) as archive:
        seen=set()
        for member in archive.getmembers():
            if member.name in seen:
                raise ValueError('DUPLICATE_ARCHIVE_MEMBER')
            seen.add(member.name)
            if not member.name.startswith('package/public/') or member.isdir():
                continue
            relative=PurePosixPath(member.name.removeprefix('package/public/'))
            if not member.isfile() or relative.is_absolute() or '..' in relative.parts:
                raise ValueError('UNSAFE_ARCHIVE_MEMBER')
            target=public/str(relative)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    old={p.relative_to(public).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in public.rglob('*') if p.is_file()}
    if fixture is None:
        corrected=(root/'deploy/pr122-domestic-website/overlay/public/assets/tiktok-integration.js').read_bytes()
        if hashlib.sha256(corrected).hexdigest()!='6fa38b952b70862e5a835ae79e4eedfe4b3d0323a8d819bbfb7ef81bddd8aa67':
            raise ValueError('APPROVED_TIKTOK_OVERLAY_DRIFT')
        (public/'assets/tiktok-integration.js').write_bytes(corrected)
    home=(public/'index.html').read_text()
    for p in public.rglob('*.html'):
        text=p.read_text()
        patched=legacy_public_wording(menu_patch(text), bool(re.search(r'<html[^>]*lang="en"',text)))
        if patched!=text:p.write_text(patched)
    hub=root/'demos/xuanjun-site-hub'
    extra_styles={}
    extra_scripts={}
    def externalize_styles(text):
        def tag(match):
            raw=match[0]
            style=re.search(r'\sstyle="([^"]*)"',raw)
            if not style:return raw
            cls='xj-inline-'+hashlib.sha256(style[1].encode()).hexdigest()[:12]
            extra_styles[cls]=style[1]
            raw=raw[:style.start()]+raw[style.end():]
            if re.search(r'\sclass="',raw):
                raw=re.sub(r'(\sclass=")',lambda m:m[0]+cls+' ',raw,count=1)
            else:raw=raw[:-1]+' class="'+cls+'">'
            return raw
        return re.sub(r'<[^>]+>',tag,text)
    for p in sorted(hub.rglob('*.html')):
        relative=p.relative_to(hub)
        if str(relative)=='index.html':continue
        original=p.read_text()
        original=original.replace('静态预览候选 · 非正式报价、支付、活动领取或客户登录','方案与交互演示 · 真实购买、支付、权益领取及客户登录暂未开放')
        if str(relative)=='visual/community-payment/index.html':
            original=original.replace('已存在的角色演示源码位于仓库 demos/community-local-e2e。本候选采用独立入口，不复制重写原模块；发布时必须由受控制品将其映射到 /visual/community-local-e2e/。','选择一个角色，体验消费者付款、商家经营及社区协作。全部订单与付款均为模拟，不产生真实资金。')
            original=original.replace('部署前置：验证六个目标文件与脚本资源均属于同一审核版本，禁止仅发布本入口页造成404。未接真实微信支付或生产分账。','商家工作台提供三家模拟商家的页面样例；原多角色流程使用隔离模拟会话。两类演示数据分别展示，尚未统一。')
            original=original.replace('href="/visual/community-local-e2e/merchant.html"><h2>商家</h2>','href="/visual/community-payment/merchant-dashboard/"><h2>商家工作台（中文演示）</h2>')
        # Only the original quote UI is replaced by its reviewed bilingual adapter.
        # Other page scripts are preserved verbatim and moved to hashed CSP-safe assets.
        def script(match):
            if str(relative)=='marketplace/index.html':return '<script src="/assets/ecv-quote-ui.js" defer></script>'
            raw=match[1];name='hub-script-'+hashlib.sha256(raw.encode()).hexdigest()[:16]+'.js'
            extra_scripts[name]=raw
            return '<script src="/assets/'+name+'" defer></script>'
        original=re.sub(r'<script>(.*?)</script>',script,original,flags=re.S)
        if str(relative)=='visual/community-payment/merchant-dashboard/index.html':
            # Preserve this delivered stand-alone SaaS shell; it has its own header.
            # The Chinese demo is explicitly labelled in localized entry pages.
            target=public/relative;target.parent.mkdir(parents=True,exist_ok=True)
            original=externalize_styles(original)
            original=original.replace('</head>','<link rel="stylesheet" href="/assets/xuanjun-site-integration.css"></head>')
            original=icp_footer(original.replace('</body>','<footer></footer></body>'))
            target.write_text(original)
            continue
        if str(relative)=='marketplace/index.html':
            original=original.replace('<form id="ecvQuote">','<form id="ecvQuote"><label>Service / 服务 <select id="serviceKind"><option value="custom">Custom development / 定制开发</option><option value="ordinary">Ordinary in-house service / 普通自营服务</option></select></label>')
        for locale in ('','zh-cn/','en/'):
            template=(public/(locale+'index.html')).read_text()
            header=re.search(r'<header\b.*?</header>',template,re.S)[0]
            footer=re.search(r'<footer\b.*?</footer>',template,re.S)[0]
            text=original
            # Translate the delivered content before inserting the established English shell.
            if locale=='en/':
                text=text.replace('Service / 服务','Service').replace('Custom development / 定制开发','Custom development').replace('Ordinary in-house service / 普通自营服务','Ordinary in-house service')
                text=translate_fragment(text).replace('lang="zh-CN"','lang="en"',1)
            if str(relative) in ('ecosystem/index.html','ecosystem/tiers/index.html'):
                rule=('ECV has a fixed total of 20 million units. Lawfully acquired rights remain valid long-term and cannot be transferred or traded. ECV is not a cryptocurrency, equity or fixed-return product. The highest eligible development discount tier applies; tiers do not stack.' if locale=='en/' else '生态权益总量固定2,000万份，合法取得的生态权益长期有效，不转让、不买卖；生态权益不是虚拟货币、股权或固定收益产品。开发折扣按符合条件的最高档计算，各档不叠加。')
                text=text.replace('</main>','<section class="hero"><p>'+rule+'</p></section></main>',1)
            if str(relative)=='visual/community-payment/index.html' and locale=='en/':
                text=text.replace('</main>','<p class="notice">The existing role demo is currently in Chinese and uses synthetic data only.</p></main>',1)
            text=public_page(text, relative.as_posix(), locale=='en/')
            header=re.sub(r'href="/(?:zh-cn/|en/)?" lang="(zh-CN|en)"',lambda m:'href="/'+('en/' if m[1]=='en' else 'zh-cn/')+relative.parent.as_posix()+'/" lang="'+m[1]+'"',header)
            header=re.sub(r'aria-current="page"','',header)
            current='en/' if locale=='en/' else 'zh-cn/'
            header=header.replace('href="/'+current+relative.parent.as_posix()+'/" lang=', 'aria-current="page" href="/'+current+relative.parent.as_posix()+'/" lang=')
            text=re.sub(r'<header\b.*?</header>',lambda _:header,text,count=1,flags=re.S)
            text=re.sub(r'<footer\b.*?</footer>',lambda _:footer,text,count=1,flags=re.S)
            text=text.replace('<main>','<main class="xj-hub">',1)
            text=text.replace('<link rel="stylesheet" href="/assets/xuanjun-hub.css">','<link rel="stylesheet" href="/yunhui.css?v=yunhui-work-v2-20261013"><link rel="stylesheet" href="/assets/xuanjun-site-integration.css">')
            # Localize only hub content links, never assets or the mapped Chinese role demo.
            text=localize_hub_links(text,locale)
            text=externalize_styles(text)
            text=text.replace('</body>','<script src="/yunhui.js?v=yunhui-work-v2-20261013" defer></script></body>')
            canonical='https://wenwenwenyiyiyi.work/'+locale+relative.parent.as_posix()+'/'
            text=text.replace('</head>','<link rel="canonical" href="'+canonical+'"></head>',1)
            target=public/locale/relative
            if target.exists():raise ValueError('NEW_ROUTE_COLLISION:'+str(target.relative_to(public)))
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    # No /demo API or new simulation backend is enabled by a static overlay.
    (public/'assets').mkdir(exist_ok=True)
    shutil.copyfile(hub/'assets/ecv-quote.js',public/'assets/ecv-quote.js')
    shutil.copyfile(hub/'assets/ecv-quote-ui.js',public/'assets/ecv-quote-ui.js')
    shutil.copyfile(hub/'assets/community-preview-session.js',public/'assets/community-preview-session.js')
    # Copy only the existing role-demo assets. Their POST service stays loopback-only.
    aliases={'/demo/merchant/app.js':'merchant.js','/demo/platform/app.js':'platform.js'}
    demo_base='/visual/community-local-e2e/'
    for p in sorted((root/'demos/community-local-e2e').glob('*')):
        if not p.is_file() or '.test.' in p.name:continue
        text=p.read_text()
        if p.suffix in ('.js','.mjs'):
            text=text.replace('"/demo/','"/_preview/community-api/').replace("'/demo/","'/_preview/community-api/")
            text=re.sub(r'credentials\s*:\s*["\']omit["\']','credentials:"same-origin"',text)
        if p.suffix=='.html':
            text=re.sub(r'src="(/demo/[^"]+\.js)"',lambda m:'src="'+demo_base+aliases.get(m[1],m[1].removeprefix('/demo/'))+'"',text)
            text=text.replace('href="/demo/"','href="'+demo_base+'"')
            text=text.replace('href="../visual/community-payment/index.html"','href="/visual/community-payment/"')
            text=text.replace('href="../legal/','href="/visual/legal/')
            text=text.replace('</head>','<link rel="stylesheet" href="/assets/xuanjun-demo-integration.css"></head>',1)
            text=text.replace('<body>','<body><nav aria-label="演示导航"><a href="/visual/community-payment/">返回社区演示 / Back to demo roles</a> · <a href="/marketplace/">浏览产品 / Browse products</a></nav>',1)
            text=text.replace('</body>','<p id="demoSessionState" role="status">正在准备隔离模拟会话。</p><script src="/assets/community-preview-session.js" defer></script></body>',1)
            if p.name=='saas-panel.html':
                text=text.replace('<body>','<body><p role="status">SaaS身份与报价服务未连接 / SaaS identity and quote service not connected</p>',1)
                text=re.sub(r'<button\b', '<button disabled aria-disabled="true"', text)
        target=public/'visual/community-local-e2e'/p.name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    for p in sorted((root/'demos/legal').glob('*.html')):
        target=public/'visual/legal'/p.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    (public/'assets/xuanjun-demo-integration.css').write_text('body{font-family:system-ui,sans-serif;min-width:320px;margin:0;padding:20px;overflow-wrap:anywhere}main{max-width:1100px;margin:auto}input,select,button{max-width:100%;font:inherit;padding:8px;margin:4px}label{display:inline-block;max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}button:disabled{opacity:.6}a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #75a7ff;outline-offset:3px}')
    for name,raw in extra_scripts.items():(public/'assets'/name).write_text(raw)
    (public/'assets/xuanjun-site-integration.css').write_text(CSS+'\n'+EXPERIENCE_CSS+'\n'+''.join('.'+cls+'{'+value+'}' for cls,value in sorted(extra_styles.items())))
    for locale in ('','zh-cn/','en/'):
        p=public/(locale+'index.html')
        text=p.read_text()
        p.write_text(improve_home(text,locale))
    # Route-scoped text fixes run after existing generation, before hashing/CSP.
    for p in public.rglob('*.html'):
        text=p.read_text();updated=reviewed_page_copy(text,p.relative_to(public).as_posix())
        if updated!=text:p.write_text(updated)
    navigation=integrate_mobile_navigation(root,public) if derive_navigation else None
    delivery=None
    if delivery_review:
        from scripts.pr122_delivery_host import integrate
        delivery=integrate(root,public)
    brand_projection=project_public_brand(public)
    # Reuse the already reviewed CSP implementation, never enable unsafe-inline.
    with Deadline(20) as deadline: csp=write_csp_metadata(public,output,deadline)
    manifest={p.relative_to(public).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in public.rglob('*') if p.is_file()}
    result={'status':'HOSTED_BROWSER_FIXTURE_ONLY' if fixture else 'ISOLATED_INTEGRATION_CANDIDATE','production_approved':False,'source_archive_sha256':None if fixture else SOURCE_HASH,'base_files':len(old),'final_files':len(manifest),'changed_existing':[k for k,h in old.items() if manifest[k]!=h],'added':[k for k in manifest if k not in old],'files':manifest,'csp':csp,'release_blockers':['Production simulation service isolation and admission pending','Browser acceptance pending','Live current baseline reconciliation pending','Independent review and controlled installer approval pending']}
    result['brand_projection']=brand_projection
    if delivery is not None:result['delivery_review']=delivery
    if navigation is not None:result['navigation_derivation']=navigation
    (output/'MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-archive',type=Path);p.add_argument('--browser-fixture',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--derive-navigation',action='store_true');a=p.parse_args()
    if bool(a.source_archive)==bool(a.browser_fixture):p.error('Choose exactly one pinned full archive or browser fixture')
    build(Path(__file__).resolve().parents[1],a.source_archive,a.output,a.browser_fixture,a.derive_navigation)
