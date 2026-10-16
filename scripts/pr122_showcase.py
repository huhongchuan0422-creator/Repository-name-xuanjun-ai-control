#!/usr/bin/env python3
"""Discover declared work, expose only reviewed versions, render an immutable site.

No purchases, finance writes or production activation. Approval input must come
from the GitHub verifier, never from a project author's status field.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit
from scripts.community_saas_modules import catalog as module_catalog

KINDS={'project','page','milestone','acceptance','module','ecology'}
ID=re.compile(r'[a-z][a-z0-9-]{0,63}')
SHA=re.compile(r'[0-9a-f]{64}')
CSP="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"

def need(ok,why):
    if not ok:raise ValueError(why)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def identity(item):return (item['project_id'],item['kind'],item['id'])
def local_url(url):
    need(type(url) is str and url.startswith('/') and not url.startswith('//') and '\\' not in url and not any(ord(c)<32 for c in url),'LOCAL_URL_REQUIRED')
    parsed=urlsplit(url);need(not parsed.scheme and not parsed.netloc and '%' not in parsed.path and '..' not in PurePosixPath(parsed.path).parts,'UNSAFE_URL')
    return url

def validate(item):
    need(type(item) is dict and item.get('kind') in KINDS,'OBJECT_KIND')
    for key in ('id','project_id'):need(type(item.get(key)) is str and ID.fullmatch(item[key]),'INVALID_ID')
    need(type(item.get('version')) is int and item['version']>0,'INVALID_VERSION')
    need(item.get('visibility') in ('PUBLIC','PRIVATE'),'VISIBILITY')
    for key in ('title','summary'):
        need(type(item.get(key)) is dict and set(item[key])=={'zh','en'} and all(type(v) is str and 0<len(v)<=2000 for v in item[key].values()),'BILINGUAL_COPY_REQUIRED')
    fields={'project':{'state','scenarios','required_milestones'},'page':{'href','role','artifact_sha256','release_artifact_sha256'},'milestone':{'state','evidence_url'},'acceptance':{'project_version','snapshot_sha256','evidence_url','members'},'module':{'module_id','package_sha256','demo_href'},'ecology':{'initiator_nickname'}}
    required={'kind','id','project_id','version','visibility','title','summary'}|fields[item['kind']]
    optional=set()
    need(required<=set(item)<=required|optional,'UNKNOWN_OR_MISSING_FIELDS')
    if item['kind']=='project':
        need(item.get('state') in ('PLANNED','DEVELOPING'),'PROJECT_STATE_REQUIRES_ACCEPTANCE_EVENT')
        need(type(item.get('required_milestones')) is list and len(set(item['required_milestones']))==len(item['required_milestones']) and all(type(v) is str and ID.fullmatch(v) for v in item['required_milestones']),'REQUIRED_MILESTONES')
        need(type(item.get('scenarios')) is list and all(type(s) is dict and set(s)=={'zh','en'} and all(type(v) is str and v for v in s.values()) for s in item['scenarios']),'PROJECT_SCENARIOS')
    if item['kind']=='page':
        local_url(item['href']);need(type(item.get('role')) is str and len(item['role'])<=100,'PAGE_ROLE')
        need(all(type(item.get(k)) is str and SHA.fullmatch(item[k]) for k in ('artifact_sha256','release_artifact_sha256')),'PAGE_ARTIFACT_BINDING')
    if item['kind']=='milestone':
        need(item.get('state') in ('PLANNED','IN_PROGRESS','DONE'),'MILESTONE_STATE')
        need(type(item.get('evidence_url')) is str and item['evidence_url'].startswith('https://github.com/'),'DEVELOPMENT_RECORD_REQUIRED')
    if item['kind']=='acceptance':
        need(type(item.get('members')) is list and 0<len(item['members'])<=5000 and all(type(r) is dict and set(r)=={'kind','id','version','object_sha256'} and r['kind'] in ('project','page','milestone') and type(r['object_sha256']) is str and SHA.fullmatch(r['object_sha256']) for r in item['members']),'ACCEPTANCE_MEMBER_REFERENCES')
        need(type(item.get('project_version')) is int and item['project_version']>0 and SHA.fullmatch(item.get('snapshot_sha256','')),'ACCEPTANCE_SNAPSHOT')
        need(type(item.get('evidence_url')) is str and item['evidence_url'].startswith('https://github.com/'),'ACCEPTANCE_EVIDENCE')
    if item['kind']=='module':
        need(type(item.get('module_id')) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,79}',item['module_id']),'MODULE_ID')
        need(SHA.fullmatch(item.get('package_sha256','')) is not None,'MODULE_PACKAGE_BINDING')
        local_url(item['demo_href'])
    if item['kind']=='ecology':need(type(item.get('initiator_nickname')) is str and 0<len(item['initiator_nickname'])<=40,'PUBLIC_NICKNAME_REQUIRED')
    return item

def discover(root):
    result=[];seen=set()
    for path in sorted(Path(root).glob('projects/*/*.json')):
        need(not any(p.is_symlink() for p in (path,path.parent,path.parent.parent)),'DECLARATION_SYMLINK')
        item=validate(json.loads(path.read_text()))
        need(path.parent.name==item['project_id'],'PROJECT_DIRECTORY_MISMATCH')
        key=(*identity(item),item['version']);need(key not in seen,'DUPLICATE_VERSION');seen.add(key)
        result.append(item)
    return result

def compile_catalog(items,approvals,prices=None,published_pages=None):
    """Pure selection. approvals are verified external records keyed by object SHA.

    Failed/new draft versions do not replace retained approved declarations.
    Progress is a count of evidenced milestones, never a guessed percentage.
    """
    selected={};pending=[];approved_versions=[]
    for item in items:
        validate(item);digest=sha(canonical(item));proof=approvals.get(digest)
        if item['visibility']!='PUBLIC' or not proof or proof.get('decision')!='PUBLIC_CONTENT_APPROVED':
            pending.append({'project_id':item['project_id'],'kind':item['kind'],'id':item['id'],'version':item['version']});continue
        if item['kind']=='page' and (published_pages or {}).get(item['href'])!={'artifact_sha256':item['artifact_sha256'],'release_artifact_sha256':item['release_artifact_sha256']}:
            pending.append({'project_id':item['project_id'],'kind':'page','id':item['id'],'version':item['version']});continue
        approved_versions.append({**item,'review':{'comment_id':proof['comment_id'],'commit':proof['commit'],'ci_run_id':proof['ci_run_id']}})
        key=identity(item)
        if key not in selected or item['version']>selected[key]['version']:
            selected[key]={**item,'review':{'comment_id':proof['comment_id'],'commit':proof['commit'],'ci_run_id':proof['ci_run_id']}}
    projects=[];module_queue=[];market=[];events=[]
    for project in sorted((i for i in selected.values() if i['kind']=='project'),key=lambda i:i['project_id']):
        pid=project['project_id'];members=[i for i in selected.values() if i['project_id']==pid]
        pages=sorted((i for i in members if i['kind']=='page' and (published_pages or {}).get(i['href'])=={'artifact_sha256':i['artifact_sha256'],'release_artifact_sha256':i['release_artifact_sha256']}),key=lambda i:i['id'])
        milestones=sorted((i for i in members if i['kind']=='milestone'),key=lambda i:i['id'])
        snapshot=sha(canonical({'project':{k:v for k,v in project.items() if k!='review'},'pages':[{k:v for k,v in p.items() if k!='review'} for p in pages],'milestones':[{k:v for k,v in m.items() if k!='review'} for m in milestones]}))
        member_refs=[{'kind':i['kind'],'id':i['id'],'version':i['version'],'object_sha256':sha(canonical({k:v for k,v in i.items() if k!='review'}))} for i in [project,*pages,*milestones]]
        acceptance=next((i for i in members if i['kind']=='acceptance' and i['project_version']==project['version'] and i['snapshot_sha256']==snapshot and sorted(map(canonical,i['members']))==sorted(map(canonical,member_refs))),None)
        done={m['id'] for m in milestones if m['state']=='DONE'}
        required=set(project['required_milestones'])
        accepted=bool(acceptance and pages and required and required<=done)
        projects.append({**project,'state':'ACCEPTED' if accepted else project['state'],'pages':pages,'milestones':milestones,
                         'progress':{'done':len(required&done),'total':len(required),'percent':None},'snapshot_sha256':snapshot,'snapshot_members':member_refs,'acceptance':acceptance if accepted else None})
        for item in members:
            if item['kind']=='ecology':events.append(item)
            if item['kind']=='module':
                module_queue.append(item);quote=(prices or {}).get(item['module_id'])
                if quote and quote.get('publication_eligible') is True and quote.get('package_sha256')==item['package_sha256']:
                    market.append({**item,'offers':quote['offers'],'purchase_href':None,'purchase_enabled':False})
    # All existing independently defined modules enter registration discovery, but
    # an unreviewed definition/offer never becomes a public product.
    cases={p['project_id']:p for p in projects if p['state']=='ACCEPTED'}
    by_hash={sha(canonical({k:v for k,v in i.items() if k!='review'})):i for i in approved_versions}
    for event in (i for i in approved_versions if i['kind']=='acceptance' and i.get('members')):
        members=[]
        for ref in event['members']:
            need(type(ref) is dict and set(ref)=={'kind','id','version','object_sha256'},'ACCEPTANCE_MEMBER_FORMAT')
            record=by_hash.get(ref['object_sha256'])
            if not record:members=[];break
            need(record['project_id']==event['project_id'] and all(record[k]==ref[k] for k in ('kind','id','version')),'ACCEPTANCE_MEMBER_IDENTITY')
            members.append(record)
        originals=[i for i in members if i['kind']=='project']
        if len(originals)!=1:continue
        original=originals[0];pages=sorted((i for i in members if i['kind']=='page'),key=lambda i:i['id']);milestones=sorted((i for i in members if i['kind']=='milestone'),key=lambda i:i['id'])
        need(len({identity(i) for i in members})==len(members) and len(originals)+len(pages)+len(milestones)==len(members),'ACCEPTANCE_MEMBER_SET')
        payload={'project':{k:v for k,v in original.items() if k!='review'},'pages':[{k:v for k,v in i.items() if k!='review'} for i in pages],'milestones':[{k:v for k,v in i.items() if k!='review'} for i in milestones]}
        required=set(original['required_milestones']);done={i['id'] for i in milestones if i['state']=='DONE'}
        if original['version']!=event['project_version'] or not pages or not required or not required<=done or sha(canonical(payload))!=event['snapshot_sha256']:continue
        record={**original,'state':'ACCEPTED','pages':pages,'milestones':milestones,'progress':{'done':len(required),'total':len(required),'percent':None},'snapshot_sha256':event['snapshot_sha256'],'acceptance':event}
        previous=cases.get(original['project_id'])
        if previous is None or (record['version'],event['version'])>(previous['version'],previous['acceptance']['version']):cases[original['project_id']]=record
    return {'schema':1,'projects':projects,'cases':list(cases.values()),
            'developing':[p for p in projects if p['state']=='DEVELOPING'],'planned':[p for p in projects if p['state']=='PLANNED'],
            'modules':market,'ecology':events,'registration_candidates':module_catalog(),'review_queue':pending,'reviewed_module_candidates':module_queue}

CSS='''body{margin:0;background:#f5f5f7;color:#1d1d1f;font:17px/1.6 system-ui,sans-serif}header,main,footer{max-width:1120px;margin:auto;padding:24px}nav{display:flex;gap:18px;flex-wrap:wrap}a{color:#0066cc}h1{font-size:clamp(32px,5vw,60px);line-height:1.12}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:22px}.card{background:white;border-radius:24px;padding:28px}small{color:#606068}.notice{border-left:3px solid #0066cc;padding:12px}a:focus-visible{outline:3px solid #0066cc;outline-offset:4px}@media(max-width:600px){header,main,footer{padding:18px}.card{padding:22px}}'''

def render(catalog,output,preview=False,project_files=None):
    output=Path(output);need(not output.exists(),'OUTPUT_ALREADY_EXISTS')
    base=output/'showcase';base.mkdir(parents=True);(base/'assets').mkdir();(base/'assets/showcase.css').write_text(CSS)
    labels={'cases':('成熟项目案例','Completed projects'),'projects':('正在开发的项目','Projects in development'),'modules':('SaaS功能市场','SaaS modules'),'roadmap':('产品发展路线','Product roadmap'),'ecosystem':('生态共建共享','Co-creation ecosystem')}
    def page(relative,title,body,en=False):
        escape=html.escape;lang='en' if en else 'zh-CN';prefix='/showcase/en/' if en else '/showcase/'
        nav=''.join('<a href="'+prefix+k+'/">'+v[en]+'</a>' for k,v in labels.items())
        clean=relative.removeprefix('en/').removesuffix('index.html')
        languages='<nav aria-label="Language"><a lang="zh-CN" href="/showcase/'+clean+'">中文</a><a lang="en" href="/showcase/en/'+clean+'">EN</a></nav>'
        banner='<p class="notice">'+('Review preview — not published' if en else '送审预览，尚未公开发布')+'</p>' if preview else ''
        target=base/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('<!doctype html><html lang="'+lang+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'｜玄钧云汇</title><link rel="stylesheet" href="/showcase/assets/showcase.css"></head><body><header><a href="/">玄钧云汇</a><nav>'+nav+'</nav>'+languages+'</header><main>'+banner+'<h1>'+escape(title)+'</h1>'+body+'</main><footer><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">渝ICP备2026024862号</a></footer></body></html>')
    for en in (False,True):
        language='en' if en else 'zh';prefix='en/' if en else '';escape=html.escape
        states={'PLANNED':('规划中','Planned'),'DEVELOPING':('开发中','In development'),'IN_PROGRESS':('进行中','In progress'),'DONE':('已完成','Completed'),'ACCEPTED':('已验收','Accepted')}
        def cards(items,case_view=False):
            return '<div class="grid">'+''.join('<article class="card"><h2><a href="/showcase/'+prefix+('cases/' if case_view else 'projects/')+p['project_id']+'/">'+escape(p['title'][language])+'</a></h2><p>'+escape(p['summary'][language])+'</p><small>'+escape(states[p['state']][en])+' · '+str(p['progress']['done'])+'/'+str(p['progress']['total'])+'</small></article>' for p in items)+'</div>' if items else '<p>'+('No reviewed content available yet.' if en else '审核通过后将在这里展示。')+'</p>'
        for key in ('cases','projects','roadmap'):
            items=catalog['cases'] if key=='cases' else catalog['developing'] if key=='projects' else catalog['projects']
            page(prefix+key+'/index.html',labels[key][en],cards(items,key=='cases'),en)
        for project,is_case in [(p,False) for p in catalog['projects']]+[(p,True) for p in catalog['cases']]:
            roles=''.join('<li><a href="'+escape(p['href'],quote=True)+'">'+escape(p['title'][language])+'</a></li>' for p in project['pages'])
            milestones=''.join('<li>'+escape(m['title'][language])+': '+escape(states[m['state']][en])+' <a href="'+escape(m['evidence_url'],quote=True)+'">'+('Record' if en else '开发记录')+'</a></li>' for m in project['milestones'])
            progress=project['progress'];scenarios='<ul>'+''.join('<li>'+escape(v[language])+'</li>' for v in project['scenarios'])+'</ul>'
            body='<p>'+escape(project['summary'][language])+'</p>'+scenarios+'<p>'+('Evidenced milestones: ' if en else '有记录的里程碑：')+str(progress['done'])+'/'+str(progress['total'])+'</p><ul>'+roles+'</ul><h2>'+labels['roadmap'][en]+'</h2><ul>'+milestones+'</ul>'
            page(prefix+('cases/' if is_case else 'projects/')+project['project_id']+'/index.html',project['title'][language],body,en)
        modules=''
        for item in catalog['modules']:
            offers=''.join('<li>'+escape(offer['mode'])+' · '+escape(cadence)+': ¥'+str(amount['cny_minor']//100)+'.'+str(amount['cny_minor']%100).zfill(2)+' / US$'+str(amount['usd_minor']//100)+'.'+str(amount['usd_minor']%100).zfill(2)+'</li>' for offer in item['offers'] for cadence,amount in offer['totals_by_cadence'].items())
            modules+='<article class="card"><h2>'+escape(item['title'][language])+'</h2><p>'+escape(item['summary'][language])+'</p><a href="'+escape(item['demo_href'],quote=True)+'">'+('Demo' if en else '功能演示')+'</a><ul>'+offers+'</ul><p>'+('Purchasing is not enabled.' if en else '真实购买尚未开放。')+'</p></article>'
        page(prefix+'modules/index.html',labels['modules'][en],modules or '<p>'+('No modules have passed listing admission yet.' if en else '模块通过测试、审核和上架准入后自动展示。')+'</p>',en)
        ecology='<p>'+('Rules and project contributions are separate from ownership of the platform foundation.' if en else '共创项目贡献与平台自研基础模块归属分开登记。')+'</p><nav><a href="/ecosystem/">'+('Rules' if en else '共建共享规则')+'</a><a href="/ecosystem/tiers/">'+('Tiers and discounts' if en else '等级与开发折扣')+'</a><a href="/ecosystem/ledger/">'+('Service credits' if en else '专项金额说明')+'</a><a href="/ecosystem/profit-sharing/">'+('Profit sharing' if en else '共创净利润共享')+'</a></nav>'
        ecology+=''.join('<article class="card"><h2>'+escape(e['title'][language])+'</h2><p>'+escape(e['summary'][language])+'</p><small>'+('Initiator: ' if en else '共创发起人：')+escape(e['initiator_nickname'])+'</small></article>' for e in catalog['ecology'])
        page(prefix+'ecosystem/index.html',labels['ecosystem'][en],ecology,en)
        page(prefix+'index.html','Explore XuanJun' if en else '探索玄钧云汇',cards(catalog['projects']),en)
    for name,raw in (project_files or {}).items():
        relative=PurePosixPath(name);need(not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='showcase','PROJECT_FILE_PATH')
        target=output/name;need(not target.exists(),'PROJECT_FILE_COLLISION');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    # Never leak review queues, private declarations, costs or unpublished versions.
    public={k:catalog[k] for k in ('schema','projects','cases','developing','planned','modules','ecology')}
    (base/'catalog.json').write_bytes(canonical(public))
    files=[{'path':p.relative_to(output).as_posix(),'size':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(output.rglob('*')) if p.is_file()]
    return {'schema':1,'files':files,'preview_only':preview,'production_deployed':False}



def scan_public_tree(path):
    path=Path(path);need(path.is_dir() and not any(p.is_symlink() for p in (path,*path.parents)),'PAGE_BUNDLE_SYMLINK')
    rows={};blobs={}
    for file in sorted(path.rglob('*')):
        need(not file.is_symlink(),'PAGE_BUNDLE_SYMLINK')
        if not file.is_file():continue
        relative=file.relative_to(path).as_posix();need(re.fullmatch(r'[A-Za-z0-9_./-]+',relative),'PUBLIC_FILENAME')
        need(all(not part.startswith('.') for part in PurePosixPath(relative).parts),'HIDDEN_PUBLIC_FILE')
        need(file.suffix.lower() in ('.html','.css','.js','.mjs','.json','.png','.jpg','.jpeg','.webp','.svg','.ico','.woff','.woff2'),'PUBLIC_ASSET_TYPE')
        raw=file.read_bytes();need(len(raw)<=8000000,'PUBLIC_FILE_LIMIT')
        if file.suffix.lower() in ('.html','.svg'):
            from html.parser import HTMLParser
            class CSPMarkup(HTMLParser):
                def handle_starttag(self,tag,attrs):
                    values=dict(attrs)
                    need(tag not in ('style','base') and not (tag=='script' and not values.get('src')),'EXTERNAL_SCRIPT_STYLE_REQUIRED')
                    need(not any(k.startswith('on') or k=='style' for k,v in attrs),'INLINE_HANDLER_OR_STYLE')
            CSPMarkup().feed(raw.decode('utf-8'))
        rows[relative]={'sha256':sha(raw),'size':len(raw)};blobs[relative]=raw
    need(len(rows)<=1000 and 'index.html' in rows and sum(v['size'] for v in rows.values())<=100000000,'PAGE_BUNDLE_COUNT')
    return rows,blobs


def project_public_pages(root,objects,approvals):
    """Versioned page bundles; one reviewed declaration binds every local asset.

    New page/role navigation needs no central menu edit. Retained immutable
    versions remain available until explicitly revoked by the review authority.
    """
    root=Path(root);eligible={};files={}
    active_projects={p['project_id'] for p in compile_catalog(objects,approvals)['projects']}
    for item in objects:
        if item['kind']!='page' or item['visibility']!='PUBLIC' or item['project_id'] not in active_projects:continue
        if approvals.get(sha(canonical(item)),{}).get('decision')!='PUBLIC_CONTENT_APPROVED':continue
        path=root/'projects'/item['project_id']/'views'/item['id']/('v'+str(item['version']))/'public'
        if not path.exists():continue  # Existing production pages use a live receipt.
        need(not any(p.is_symlink() for p in (path,*path.parents)),'PAGE_BUNDLE_SYMLINK')
        prefix='showcase/projects/'+item['project_id']+'/views/'+item['id']+'/v'+str(item['version'])+'/'
        need(item['href']=='/'+prefix,'GENERATED_PAGE_URL_REQUIRED')
        rows,source_blobs=scan_public_tree(path)
        blobs={prefix+name:raw for name,raw in source_blobs.items()}
        need(rows['index.html']['sha256']==item['artifact_sha256'] and sha(canonical(rows))==item['release_artifact_sha256'],'PAGE_BUNDLE_IDENTITY')
        eligible[item['href']]={'artifact_sha256':item['artifact_sha256'],'release_artifact_sha256':item['release_artifact_sha256']}
        for name,raw in blobs.items():need(name not in files,'PAGE_COLLISION');files[name]=raw
    return eligible,files
