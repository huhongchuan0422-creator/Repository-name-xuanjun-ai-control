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

KINDS={'project','page','milestone','acceptance','module','ecology','feature','feature_acceptance'}
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
    fields={'project':{'state','scenarios','required_milestones'},'page':{'href','role','artifact_sha256','release_artifact_sha256'},'milestone':{'state','evidence_url'},'acceptance':{'project_version','snapshot_sha256','evidence_url','members'},'module':{'module_id','package_sha256','demo_href','requirements'},'ecology':{'initiator_nickname'}}
    fields['feature']={'role','device','milestone_id','page_id','page_version','page_artifact_sha256'}
    fields['feature_acceptance']={'project_version','snapshot_sha256','members','feature_sha256','evidence_url'}
    required={'kind','id','project_id','version','visibility','title','summary'}|fields[item['kind']]
    optional={'sort_order'} if item['kind'] in ('page','milestone') else set()
    if 'sort_order' in item:need(type(item['sort_order']) is int and 0<=item['sort_order']<=9999,'SORT_ORDER')
    need(required<=set(item)<=required|optional,'UNKNOWN_OR_MISSING_FIELDS')
    if item['kind']=='feature':
        need(item['role'] in ('consumer','merchant','community','beneficiary','platform','website-admin'),'FEATURE_ROLE')
        need(item['device'] in ('phone','desktop'),'FEATURE_DEVICE')
        need(item['role'] not in ('consumer','merchant') or item['device']=='phone','PHONE_FIRST_ROLE')
        need(all(type(item[k]) is str and ID.fullmatch(item[k]) for k in ('milestone_id','page_id')),'FEATURE_BINDING')
        need(type(item['page_version']) is int and item['page_version']>0 and type(item['page_artifact_sha256']) is str and SHA.fullmatch(item['page_artifact_sha256']),'FEATURE_PAGE_IDENTITY')
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
    if item['kind']=='feature_acceptance':
        need(type(item.get('feature_sha256')) is str and SHA.fullmatch(item['feature_sha256']),'FEATURE_ACCEPTANCE_IDENTITY')
    if item['kind'] in ('acceptance','feature_acceptance'):
        need(type(item.get('members')) is list and 0<len(item['members'])<=5000 and all(type(r) is dict and set(r)=={'kind','id','version','object_sha256'} and r['kind'] in ('project','page','milestone') and type(r['object_sha256']) is str and SHA.fullmatch(r['object_sha256']) for r in item['members']),'ACCEPTANCE_MEMBER_REFERENCES')
        need(type(item.get('project_version')) is int and item['project_version']>0 and SHA.fullmatch(item.get('snapshot_sha256','')),'ACCEPTANCE_SNAPSHOT')
        need(type(item.get('evidence_url')) is str and item['evidence_url'].startswith('https://github.com/'),'ACCEPTANCE_EVIDENCE')
    if item['kind']=='module':
        need(type(item.get('module_id')) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,79}',item['module_id']),'MODULE_ID')
        need(SHA.fullmatch(item.get('package_sha256','')) is not None,'MODULE_PACKAGE_BINDING')
        local_url(item['demo_href'])
        need(type(item['requirements']) is list and all(type(r) is dict and set(r)=={'zh','en'} and all(type(v) is str and v for v in r.values()) for r in item['requirements']),'MODULE_REQUIREMENTS_REQUIRED')
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
        approved_versions.append({**item,'review':{'comment_id':proof['comment_id'],'commit':proof['commit'],'ci_run_id':proof['ci_run_id'],'module_admission':proof.get('module_admission',False)}})
        key=identity(item)
        if key not in selected or item['version']>selected[key]['version']:
            selected[key]={**item,'review':{'comment_id':proof['comment_id'],'commit':proof['commit'],'ci_run_id':proof['ci_run_id'],'module_admission':proof.get('module_admission',False)}}
    projects=[];module_queue=[];market=[];events=[]
    for project in sorted((i for i in selected.values() if i['kind']=='project'),key=lambda i:i['project_id']):
        pid=project['project_id'];members=[i for i in selected.values() if i['project_id']==pid]
        pages=sorted((i for i in members if i['kind']=='page' and (published_pages or {}).get(i['href'])=={'artifact_sha256':i['artifact_sha256'],'release_artifact_sha256':i['release_artifact_sha256']}),key=lambda i:(i.get('sort_order',999),i['id']))
        milestones=sorted((i for i in members if i['kind']=='milestone'),key=lambda i:(i.get('sort_order',999),i['id']))
        snapshot=sha(canonical({'project':{k:v for k,v in project.items() if k!='review'},'pages':[{k:v for k,v in p.items() if k!='review'} for p in pages],'milestones':[{k:v for k,v in m.items() if k!='review'} for m in milestones]}))
        member_refs=[{'kind':i['kind'],'id':i['id'],'version':i['version'],'object_sha256':sha(canonical({k:v for k,v in i.items() if k!='review'}))} for i in [project,*pages,*milestones]]
        acceptance=next((i for i in members if i['kind']=='acceptance' and i['project_version']==project['version'] and i['snapshot_sha256']==snapshot and sorted(map(canonical,i['members']))==sorted(map(canonical,member_refs))),None)
        done={m['id'] for m in milestones if m['state']=='DONE'}
        required=set(project['required_milestones'])
        accepted=bool(acceptance and pages and required and required<=done)
        features=[]
        for feature in (i for i in members if i['kind']=='feature'):
            bound=next((p for p in pages if p['id']==feature['page_id'] and p['role']==feature['role'] and p['version']==feature['page_version'] and p['artifact_sha256']==feature['page_artifact_sha256']),None)
            feature_digest=sha(canonical({k:v for k,v in feature.items() if k!='review'}))
            # DONE is progress only. An independently authenticated functional
            # acceptance must bind this feature and the exact current snapshot.
            contract=next((i for i in members if i['kind']=='feature_acceptance'
                           and i['project_version']==project['version']
                           and i['snapshot_sha256']==snapshot
                           and i['feature_sha256']==feature_digest
                           and sorted(map(canonical,i['members']))==sorted(map(canonical,member_refs))),None)
            if contract and bound and feature['milestone_id'] in done:
                features.append({**feature,'href':bound['href'],'page_version':bound['version'],'artifact_sha256':bound['artifact_sha256'],'acceptance':contract})
        feature_contract=any(i['kind']=='feature' and i['project_id']==pid for i in items)
        projects.append({**project,'state':'ACCEPTED' if accepted else project['state'],'pages':pages,'milestones':milestones,'features':features,'feature_contract':feature_contract,
                         'progress':{'done':len(required&done),'total':len(required),'percent':None},'snapshot_sha256':snapshot,'snapshot_members':member_refs,'acceptance':acceptance if accepted else None})
        for item in members:
            if item['kind']=='ecology':events.append(item)
            if item['kind']=='module':
                module_queue.append(item);quote=(prices or {}).get(item['module_id'])
                if item['review'].get('module_admission') is True and quote and quote.get('publication_eligible') is True and quote.get('package_sha256')==item['package_sha256']:
                    market.append({**item,'dependencies':next((m['dependencies'] for m in module_catalog() if m['id']==item['module_id']),[]),'offers':quote['offers'],'purchase_href':None,'purchase_enabled':False})
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
        original=originals[0];pages=sorted((i for i in members if i['kind']=='page'),key=lambda i:(i.get('sort_order',999),i['id']));milestones=sorted((i for i in members if i['kind']=='milestone'),key=lambda i:(i.get('sort_order',999),i['id']))
        need(len({identity(i) for i in members})==len(members) and len(originals)+len(pages)+len(milestones)==len(members),'ACCEPTANCE_MEMBER_SET')
        payload={'project':{k:v for k,v in original.items() if k!='review'},'pages':[{k:v for k,v in i.items() if k!='review'} for i in pages],'milestones':[{k:v for k,v in i.items() if k!='review'} for i in milestones]}
        required=set(original['required_milestones']);done={i['id'] for i in milestones if i['state']=='DONE'}
        if original['version']!=event['project_version'] or not pages or not required or not required<=done or sha(canonical(payload))!=event['snapshot_sha256']:continue
        record={**original,'state':'ACCEPTED','pages':pages,'milestones':milestones,'features':[],'feature_contract':any(i['kind']=='feature' and i['project_id']==original['project_id'] for i in items),'progress':{'done':len(required),'total':len(required),'percent':None},'snapshot_sha256':event['snapshot_sha256'],'acceptance':event}
        previous=cases.get(original['project_id'])
        if previous is None or (record['version'],event['version'])>(previous['version'],previous['acceptance']['version']):cases[original['project_id']]=record
    return {'schema':1,'projects':projects,'cases':list(cases.values()),
            'developing':[p for p in projects if p['state']=='DEVELOPING'],'planned':[p for p in projects if p['state']=='PLANNED'],
            'modules':market,'ecology':events,'registration_candidates':module_catalog(),'review_queue':pending,'reviewed_module_candidates':module_queue}

def official_shell(package,expected_sha):
    import io,tarfile
    raw=Path(package).read_bytes();need(sha(raw)==expected_sha,'OFFICIAL_SHELL_PACKAGE_HASH')
    result={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        for language,prefix in (('zh',''),('en','en/')):
            text=archive.extractfile('pr122-site-hub/overlay/public/'+prefix+'index.html').read().decode()
            header=re.search(r'<header\b.*?</header>',text,re.S);footer=re.search(r'<footer\b.*?</footer>',text,re.S)
            need(header and footer and all(label in header[0] for label in (('Solutions','Function Market','Custom') if language=='en' else ('解决方案','功能市场','定制与交付'))),'OFFICIAL_SHELL_STRUCTURE')
            result[language]={'header':header[0],'footer':footer[0]}
    return result

CSS='''body{margin:0;background:#f5f5f7;color:#1d1d1f;font:17px/1.6 system-ui,sans-serif}header,main,footer{max-width:1120px;margin:auto;padding:24px}nav{display:flex;gap:18px;flex-wrap:wrap}a{color:#0066cc}h1{font-size:clamp(32px,5vw,60px);line-height:1.12}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:22px}.card{background:white;border-radius:24px;padding:28px}small{color:#606068}.notice{border-left:3px solid #0066cc;padding:12px}a:focus-visible{outline:3px solid #0066cc;outline-offset:4px}@media(max-width:600px){header,main,footer{padding:18px}.card{padding:22px}}'''

CSS += '\n.showcase-main{max-width:1120px;margin:auto;padding:44px 24px 70px}.showcase-main h1{letter-spacing:-.04em;margin:40px 0 22px}.showcase-main h2{font-size:30px;letter-spacing:-.025em;margin:54px 0 24px}.showcase-main h3{font-size:22px;line-height:1.35;margin:18px 0 14px}.showcase-main a{text-decoration:none}.showcase-main a:hover{text-decoration:underline}.showcase-subnav{display:flex;flex-wrap:wrap;gap:8px;padding-bottom:26px;border-bottom:1px solid #dedee4}.showcase-subnav a{padding:8px 14px;border-radius:20px;color:#4a4a50;background:#fff;font-size:14px}.showcase-lead{max-width:760px;font-size:20px;color:#606068}.showcase-tags{display:flex;flex-wrap:wrap;gap:10px;margin:24px 0}.showcase-tags span,.showcase-status{padding:5px 11px;border-radius:20px;background:#e9edf5;font-size:13px;color:#4d5e77}.showcase-progress{color:#6e6e73;margin:26px 0}.showcase-main .card{min-height:0;border:1px solid #e8e8ed;box-shadow:none;margin:0}.showcase-main .card p{color:#606068;margin:12px 0 24px}.showcase-main .showcase-action{display:inline-block;font-weight:600}.showcase-main .role-cards{margin:28px 0 44px}.showcase-main .milestone h3{font-size:20px}.showcase-main .milestone a{font-size:14px}.showcase-main .notice{font-size:14px;color:#6e6e73;margin:26px 0}@media(max-width:600px){.showcase-main{padding:24px 18px 48px}.showcase-main h1{margin:30px 0 18px}.showcase-main h2{font-size:26px}.showcase-lead{font-size:18px}.showcase-main .card{padding:24px}}\n'

def role_views(project,en=False):
    """Generate role-local screens from independently approved, accepted features.

    No author-provided HTML is invented or executed by this generator. The
    feature action opens the hash-bound reviewed implementation unchanged.
    """
    language='en' if en else 'zh';prefix='en/' if en else '';escape=html.escape
    labels={'consumer':('消费者','Consumer'),'merchant':('商家','Merchant'),'community':('社区','Community'),'beneficiary':('分账方','Beneficiary'),'platform':('平台运营','Platform operations'),'website-admin':('网站管理','Website administration')}
    groups={}
    for feature in project.get('features',[]):
        groups.setdefault((feature['role'],feature['device']),[]).append(feature)
    result=[]
    for (role,device),features in sorted(groups.items()):
        features=sorted(features,key=lambda f:f['id'])
        relative=prefix+'projects/'+project['project_id']+'/roles/'+role+'/'+device+'/index.html'
        title=labels[role][en]
        nav=''.join('<a href="#feature-'+escape(f['id'],quote=True)+'">'+escape(f['title'][language])+'</a>' for f in features)
        cards=''.join('<section class="card" id="feature-'+escape(f['id'],quote=True)+'"><h2>'+escape(f['title'][language])+'</h2><p>'+escape(f['summary'][language])+'</p><a href="'+escape(f['href'],quote=True)+'">'+('Open feature' if en else '进入功能')+' →</a></section>' for f in features)
        body='<header><a href="/showcase/'+prefix+'projects/'+project['project_id']+'/">'+('Back to project' if en else '返回项目')+'</a><p>'+escape(project['title'][language])+'</p><h1>'+title+'</h1></header><nav aria-label="'+('Features' if en else '当前角色功能')+'">'+nav+'</nav><main>'+cards+'</main>'
        result.append({'relative':relative,'href':'/showcase/'+relative.removesuffix('index.html'),'title':title,'device':device,'body':body})
    return result


def render(catalog,output,preview=False,project_files=None,shell=None):
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
        global_header=(shell or {}).get('en' if en else 'zh',{}).get('header')
        global_footer=(shell or {}).get('en' if en else 'zh',{}).get('footer')
        head_assets=('<link rel="stylesheet" href="/yunhui.css?v=yunhui-work-v2-20261013"><link rel="stylesheet" href="/assets/xuanjun-site-integration.css">' if global_header else '')
        script='<script src="/yunhui.js?v=yunhui-work-v2-20261013" defer></script>' if global_header else ''
        if global_header:
            global_header=re.sub(r'\saria-current="page"','',global_header)
            global_header=re.sub(r'href="[^"]*" lang="(zh-CN|en)"',lambda m:'href="/showcase/'+('en/' if m[1]=='en' else '')+clean+'" lang="'+m[1]+'"'+(' aria-current="page"' if m[1]==lang else ''),global_header)
        header=global_header or '<header><a href="/">玄钧云汇</a></header>'
        footer=global_footer or '<footer><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">渝ICP备2026024862号</a></footer>'
        canonical_url='https://wenwenwenyiyiyi.work/showcase/'+relative.removesuffix('index.html')
        target.write_text('<!doctype html><html lang="'+lang+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'｜玄钧云汇</title><link rel="canonical" href="'+canonical_url+'">'+head_assets+'<link rel="stylesheet" href="/showcase/assets/showcase.css"></head><body>'+header+'<main class="showcase-main"><nav class="showcase-subnav" aria-label="'+('Explore work' if en else '作品展示')+'">'+nav+'</nav>'+('' if global_header else languages)+banner+'<h1>'+escape(title)+'</h1>'+body+'</main>'+footer+script+'</body></html>')
    for en in (False,True):
        language='en' if en else 'zh';prefix='en/' if en else '';escape=html.escape
        states={'PLANNED':('规划中','Planned'),'DEVELOPING':('开发中','In development'),'IN_PROGRESS':('进行中','In progress'),'DONE':('已完成','Completed'),'ACCEPTED':('已验收','Accepted')}
        def cards(items,case_view=False):
            return '<div class="grid">'+''.join('<article class="card"><h2><a href="/showcase/'+prefix+('cases/' if case_view else 'projects/')+p['project_id']+'/">'+escape(p['title'][language])+'</a></h2><p>'+escape(p['summary'][language])+'</p><small>'+escape(states[p['state']][en])+' · '+str(p['progress']['done'])+'/'+str(p['progress']['total'])+'</small></article>' for p in items)+'</div>' if items else '<p>'+('No reviewed content available yet.' if en else '审核通过后将在这里展示。')+'</p>'
        for key in ('cases','projects','roadmap'):
            items=catalog['cases'] if key=='cases' else catalog['developing'] if key=='projects' else catalog['projects']
            page(prefix+key+'/index.html',labels[key][en],cards(items,key=='cases'),en)
        for project,is_case in [(p,False) for p in catalog['projects']]+[(p,True) for p in catalog['cases']]:
            generated=role_views(project,en)
            roles='<div class="grid role-cards">'+''.join('<article class="card"><h3>'+escape(p['title'][language])+'</h3><p>'+escape(p['summary'][language])+'</p><a class="showcase-action" href="'+escape(p['href'],quote=True)+'">'+('Try the demo' if en else '进入体验')+' →</a></article>' for p in project['pages'])+'</div>'
            if project.get('feature_contract'):
                roles='<div class="grid role-cards">'+''.join('<article class="card"><h3>'+escape(v['title'])+'</h3><a href="'+escape(v['href'],quote=True)+'">'+('Enter' if en else '进入体验')+' →</a></article>' for v in generated)+'</div>'
            if not is_case:
                for view in generated:
                    target=base/view['relative'];target.parent.mkdir(parents=True,exist_ok=True)
                    notice=('<p>送审预览，尚未公开发布 / Review preview</p>' if preview else '')
                    target.write_text('<!doctype html><html lang="'+('en' if en else 'zh-CN')+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(view['title'])+'｜玄钧云汇</title><link rel="stylesheet" href="/showcase/assets/roles.css"></head><body class="'+view['device']+'">'+notice+view['body']+'<footer><a href="https://beian.miit.gov.cn/" rel="noopener noreferrer">渝ICP备2026024862号</a></footer></body></html>')
            milestones=''.join('<article class="card milestone"><span class="showcase-status">'+escape(states[m['state']][en])+'</span><h3>'+escape(m['title'][language])+'</h3><a href="'+escape(m['evidence_url'],quote=True)+'">'+('View record' if en else '查看记录')+' →</a></article>' for m in project['milestones'])
            progress=project['progress'];scenarios='<div class="showcase-tags">'+''.join('<span>'+escape(v[language])+'</span>' for v in project['scenarios'])+'</div>'
            body='<p class="showcase-lead">'+escape(project['summary'][language])+'</p>'+scenarios+'<p class="showcase-progress">'+('Verified milestones: ' if en else '已核验完成：')+str(progress['done'])+' / '+str(progress['total'])+'</p>'+roles+'<h2>'+labels['roadmap'][en]+'</h2><div class="grid">'+milestones+'</div>'
            page(prefix+('cases/' if is_case else 'projects/')+project['project_id']+'/index.html',project['title'][language],body,en)
        modes={'MONTHLY':('月付','Monthly'),'YEARLY':('年付','Yearly'),'BUYOUT':('一次买断','One-time license'),'FREE':('免费','Free'),'PROMO_ZERO':('零元优惠','Zero-price promotion'),'USAGE':('按量','Usage-based'),'HYBRID':('组合计费','Mixed billing'),'CUSTOM':('按约定','Contract terms')}
        cadences={'MONTHLY':('每月','per month'),'YEARLY':('每年','per year'),'ONCE':('一次性','one time'),'PER_UNIT':('按单位','per unit')}
        modules=''
        for item in catalog['modules']:
            offers=''.join('<li>'+escape(modes[offer['mode']][en])+' · '+escape(cadences[cadence][en])+': ¥'+str(amount['cny_minor']//100)+'.'+str(amount['cny_minor']%100).zfill(2)+' / US$'+str(amount['usd_minor']//100)+'.'+str(amount['usd_minor']%100).zfill(2)+'</li>' for offer in item['offers'] for cadence,amount in offer['totals_by_cadence'].items())
            modules+='<article class="card"><h2><a href="/showcase/'+prefix+'modules/'+item['module_id']+'/">'+escape(item['title'][language])+'</a></h2><p>'+escape(item['summary'][language])+'</p><a href="'+escape(item['demo_href'],quote=True)+'">'+('Demo' if en else '功能演示')+'</a><ul>'+offers+'</ul><p>'+('Purchasing is not enabled.' if en else '真实购买尚未开放。')+'</p></article>'
            requirements='<ul>'+''.join('<li>'+escape(r[language])+'</li>' for r in item['requirements'])+'</ul>' if item['requirements'] else '<p>'+('No additional preparation requirements are declared for this reviewed listing.' if en else '本次获审上架记录未声明额外准备材料。')+'</p>'
            dependency_labels={m['id']:m['title'] for m in module_catalog()}
            dependency_english={'storefront_catalog':'Product catalog','merchant_operations':'Merchant operations','advertising':'Ad management','refund_preview':'Refund preview','split_preview':'Sharing preview','reconciliation_preview':'Reconciliation preview','signed_qr':'Signed QR entry'}
            dependencies=', '.join((dependency_english.get(d,'Required module') if en else dependency_labels.get(d,'依赖模块')) for d in item['dependencies']) or ('None declared' if en else '未声明额外依赖')
            body='<p class="showcase-lead">'+escape(item['summary'][language])+'</p><p>'+('Dependencies: ' if en else '功能依赖：')+escape(dependencies)+'</p><p><a class="showcase-action" href="'+escape(item['demo_href'],quote=True)+'">'+('Try the demo' if en else '体验功能')+' →</a></p><h2>'+('Pricing options' if en else '价格与付款方式')+'</h2><ul>'+offers+'</ul><h2>'+('Preparation and conditions' if en else '准备材料与适用条件')+'</h2>'+requirements+'<p class="notice">'+('Live purchasing and payments are not enabled.' if en else '真实购买与付款尚未开放。')+'</p>'
            page(prefix+'modules/'+item['module_id']+'/index.html',item['title'][language],body,en)
        page(prefix+'modules/index.html',labels['modules'][en],modules or '<p>'+('No modules have passed listing admission yet.' if en else '模块通过测试、审核和上架准入后自动展示。')+'</p>',en)
        ecology='<p>'+('Rules and project contributions are separate from ownership of the platform foundation.' if en else '共创项目贡献与平台自研基础模块归属分开登记。')+'</p><nav><a href="/ecosystem/">'+('Rules' if en else '共建共享规则')+'</a><a href="/ecosystem/tiers/">'+('Tiers and discounts' if en else '等级与开发折扣')+'</a><a href="/ecosystem/ledger/">'+('Service credits' if en else '专项金额说明')+'</a><a href="/ecosystem/profit-sharing/">'+('Profit sharing' if en else '共创净利润共享')+'</a></nav>'
        ecology+=''.join('<article class="card"><h2>'+escape(e['title'][language])+'</h2><p>'+escape(e['summary'][language])+'</p><small>'+('Initiator: ' if en else '共创发起人：')+escape(e['initiator_nickname'])+'</small></article>' for e in catalog['ecology'])
        page(prefix+'ecosystem/index.html',labels['ecosystem'][en],ecology,en)
        page(prefix+'index.html','Explore XuanJun' if en else '探索玄钧云汇',cards(catalog['projects']),en)
    for name,raw in (project_files or {}).items():
        relative=PurePosixPath(name);need(not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='showcase','PROJECT_FILE_PATH')
        target=output/name;need(not target.exists(),'PROJECT_FILE_COLLISION');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    (base/'assets/roles.css').write_text('body{margin:0;background:#f5f5f7;color:#1d1d1f;font:16px/1.6 system-ui,sans-serif}header,main,nav,footer{padding:20px;max-width:1120px;margin:auto}body.phone header,body.phone main,body.phone nav,body.phone footer{max-width:440px}h1{font-size:32px;letter-spacing:-.04em}a{color:#0066cc;text-decoration:none}nav{display:flex;gap:12px;overflow:auto}nav a{white-space:nowrap}main{display:grid;gap:16px}.card{background:white;border-radius:22px;padding:24px}h2{font-size:22px}.desktop main{grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr))}a:focus-visible{outline:3px solid #0066cc;outline-offset:4px}@media(max-width:600px){header,main,nav,footer{padding:16px}h1{font-size:28px}}')
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
