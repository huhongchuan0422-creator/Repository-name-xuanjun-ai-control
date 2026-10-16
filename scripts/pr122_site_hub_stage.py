#!/usr/bin/env python3
"""Build an isolated, review-only site overlay. Never activates a release."""
import argparse
import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath

SOURCE_HASH = '74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63'
MENUS = [
    ('solutions', [('产品可视化中心', '/visual/'), ('行业案例', '/visual/catalog/'), ('社区分账演示', '/visual/community-payment/')]),
    ('capabilities', [('SaaS产品目录', '/marketplace/modules/'), ('功能选配', '/marketplace/modules/'), ('产品与购买', '/marketplace/'), ('共建共享', '/ecosystem/'), ('权益等级与开发折扣', '/ecosystem/tiers/')]),
    ('custom-ai', [('定制开发服务', '/custom-ai'), ('客户项目中心', '/customer/projects/'), ('项目预览与验收', '/customer/projects/acceptance/'), ('共创项目广场', '/ecosystem/co-create/')]),
]
EN = {'产品可视化中心':'Product visual center', '行业案例':'Industry examples', '社区分账演示':'Community payment demo', 'SaaS产品目录':'SaaS catalog', '功能选配':'Module options', '产品与购买':'Products and purchase', '共建共享':'Co-build and share', '权益等级与开发折扣':'ECV tiers and development discounts', '定制开发服务':'Custom development', '客户项目中心':'Customer projects', '项目预览与验收':'Preview and acceptance', '共创项目广场':'Co-creation projects'}
CSS = '''/* Verified selectors: live apex and pinned Work V2 source. */
@media(min-width:1181px){.primary-nav .nav-group{column-gap:5px}.primary-nav .nav-group>a{padding-right:0}.primary-nav .nav-group>button{width:24px;padding:0;text-align:left}}
.xj-hub{padding:36px 0 60px}.xj-hub .hero{display:block;min-height:0;padding:28px;background:#fff;border:1px solid #dce5f1;border-radius:18px;margin:20px 0}.xj-hub .hero h1{font-size:clamp(28px,5vw,48px)}.xj-hub .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:16px}.xj-hub .card{min-height:0;margin:10px 0;padding:22px}.xj-hub .card h2{font-size:22px}.xj-hub .btn{display:inline-block;padding:10px 16px;background:#2057d4;color:white;border-radius:10px;margin:6px}.xj-hub input{max-width:100%;padding:8px;border:1px solid #abbcd4;border-radius:6px}.xj-hub label{display:block;margin:12px 0}.xj-hub table{display:block;overflow:auto}.xj-hub th,.xj-hub td{padding:10px;text-align:left}.xj-hub a:focus-visible,.xj-hub button:focus-visible,.xj-hub input:focus-visible{outline:3px solid #75a7ff;outline-offset:3px}
'''

def menu_patch(text):
    if 'id="primary-nav"' not in text:
        return text
    english = bool(re.search(r'<html[^>]*lang="en"', text))
    first = re.search(r'<div class="nav-group"><a href="([^"]+)/solutions">', text)
    prefix = first[1] if first else ''
    for key, entries in MENUS:
        link = prefix + '/' + key
        items = ''.join('<a href="%s">%s%s</a>' % (url, EN[label] if english else label, ' (Chinese preview)' if english and key != 'custom-ai' else '') for label,url in entries)
        pattern = r'(<div class="nav-group"><a href="'+re.escape(link)+r'">.*?<div class="nav-panel">)(.*?)(</div></div>)'
        if key != 'custom-ai':
            text, count = re.subn(pattern, lambda m:m[1]+m[2]+items+m[3], text, count=1, flags=re.S)
        else:
            pattern = r'<a href="'+re.escape(link)+r'">(Custom &amp; Delivery|Custom & Delivery|定制与交付)</a>'
            def custom(m):
                label = 'Expand Custom &amp; Delivery menu' if english else '展开定制与交付菜单'
                return '<div class="nav-group">'+m[0]+'<button type="button" aria-expanded="false" aria-label="'+label+'">⌄</button><div class="nav-panel">'+items+'</div></div>'
            text, count = re.subn(pattern, custom, text, count=1)
        if count != 1:
            raise ValueError('UNEXPECTED_NAV_STRUCTURE:'+link)
    return text.replace('</head>', '<link rel="stylesheet" href="/assets/xuanjun-site-integration.css"></head>', 1)

def build(root, source, output):
    if output.exists():
        raise ValueError('OUTPUT_ALREADY_EXISTS')
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError('SOURCE_ARCHIVE_HASH_MISMATCH')
    output.mkdir(parents=True)
    public = output/'public'
    public.mkdir()
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
    home=(public/'index.html').read_text()
    for p in public.rglob('*.html'):
        text=p.read_text()
        patched=menu_patch(text)
        if patched!=text:p.write_text(patched)
    header=re.search(r'<header\b.*?</header>',menu_patch(home),re.S)[0]
    footer=re.search(r'<footer\b.*?</footer>',home,re.S)[0]
    hub=root/'demos/xuanjun-site-hub'
    for p in sorted(hub.rglob('*.html')):
        relative=p.relative_to(hub)
        if str(relative)=='index.html':continue
        text=p.read_text()
        text=re.sub(r'<header\b.*?</header>',lambda _:header,text,count=1,flags=re.S)
        text=re.sub(r'<footer\b.*?</footer>',lambda _:footer,text,count=1,flags=re.S)
        text=text.replace('<main>','<main class="xj-hub">',1)
        text=text.replace('<link rel="stylesheet" href="/assets/xuanjun-hub.css">','<link rel="stylesheet" href="/yunhui.css?v=yunhui-work-v2-20261013"><link rel="stylesheet" href="/assets/xuanjun-site-integration.css">')
        text=text.replace('</body>','<script src="/yunhui.js?v=yunhui-work-v2-20261013" defer></script></body>')
        target=public/relative
        if target.exists():raise ValueError('NEW_ROUTE_COLLISION:'+str(relative))
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    # No /demo API or new simulation backend is enabled by a static overlay.
    shutil.copyfile(hub/'assets/ecv-quote.js',public/'assets/ecv-quote.js')
    (public/'assets/xuanjun-site-integration.css').write_text(CSS)
    for locale in ('','zh-cn/','en/'):
        p=public/(locale+'index.html')
        text=p.read_text();english=locale=='en/'
        section='<section data-site-hub="review-candidate"><h2>'+('Co-build and share' if english else '共建共享')+'</h2><p>'+('New service previews are currently in Chinese.' if english else '了解生态权益、开发折扣、专项服务抵扣与共创项目。')+'</p><div class="actions"><a class="button" href="/marketplace/">'+('Browse products and services' if english else '浏览产品与服务')+'</a><a class="button secondary" href="/visual/">'+('Explore visual solutions' if english else '体验可视化方案')+'</a><a class="button secondary" href="/ecosystem/">'+('Co-build and share' if english else '进入共建共享')+'</a></div></section>'
        p.write_text(text.replace('</main>',section+'</main>',1))
    manifest={p.relative_to(public).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in public.rglob('*') if p.is_file()}
    result={'status':'ISOLATED_INTEGRATION_CANDIDATE','production_approved':False,'source_archive_sha256':SOURCE_HASH,'base_files':len(old),'final_files':len(manifest),'changed_existing':[k for k,h in old.items() if manifest[k]!=h],'added':[k for k in manifest if k not in old],'files':manifest,'release_blockers':['English content for new pages pending','Community demo POST service and asset mapping pending','Exact CSP generation and browser acceptance pending','Live current baseline reconciliation pending','Independent review and controlled installer approval pending']}
    (output/'MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    build(Path(__file__).resolve().parents[1],a.source_archive,a.output)
