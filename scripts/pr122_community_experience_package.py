"""Review-only mobile UI overlay. No installer or production writes."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import gzip

ROOT=Path(__file__).resolve().parents[1]
TARGET='visual/community-payment/mobile/'
# Exact role.js bytes from source 0bdf513c, not the historical 790937 release.
BASELINE_ROLE_JS = b'"use strict";\n(()=>{document.body.classList.toggle(\'preview-wide\',[\'platform\',\'website-admin\'].includes(document.body.dataset.previewRole));})();\n'

def adapt_role_navigation(text):
    """Derive navigation only; frozen role inputs remain byte-bound and unchanged."""
    import re
    routes={
        '/visual/community-local-e2e/':'/'+TARGET,
        '/visual/community-local-e2e/index.html':'/'+TARGET,
        '/visual/community-payment/merchant-dashboard/':'/'+TARGET+'merchant.html',
        **{'/visual/community-local-e2e/'+role+'.html':'/'+TARGET+role+'.html'
           for role in ('merchant','community','beneficiary','platform')},
    }
    # Match anchors only. Never touch script text, assets, forms or API endpoints.
    parts=re.split(r'(<(?:script|style)\b[^>]*>.*?</(?:script|style)>)',text,flags=re.S|re.I)
    for i in range(0,len(parts),2):
        parts[i]=re.sub(r'(<a\b[^>]*\bhref=")([^"]+)(")',
                       lambda m:m[1]+routes.get(m[2],m[2])+m[3],parts[i])
    return ''.join(parts)

def prepare_mobile_page(text, name):
    allowed={'index.html','merchant.html','community.html','beneficiary.html','platform.html'}
    if name not in allowed:raise ValueError('UNEXPECTED_MOBILE_PAGE')
    text=adapt_role_navigation(text)
    if name=='index.html' and '<script src="./role.js" defer></script>' not in text:
        text=text.replace('</body>','<script src="./role.js" defer></script></body>',1)
    return text

def collect_mobile_files(root,derive_navigation=False):
    root=Path(root)
    source=root/'demos/work-community-experience'
    files={TARGET+name:(source/name).read_bytes() for name in ('index.html','experience.css','experience.js','role.css','role.js')}
    if derive_navigation:
        files[TARGET+'index.html']=prepare_mobile_page(files[TARGET+'index.html'].decode(),'index.html').encode()
    else:
        files[TARGET+'role.js']=BASELINE_ROLE_JS
    # Reuse byte-bound deployed role pages as build data; no iframe/CSP bypass.
    frozen=(root/'evidence/pr122-site-hub-experience/PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes()
    assert hashlib.sha256(frozen).hexdigest()=='b66eba8c958b10925064053f41dc575a6eb301616bc414d139cdddd98a2e7cb3','FROZEN_ROLE_PACKAGE_DRIFT'
    import re
    from urllib.parse import urljoin
    with tarfile.open(fileobj=io.BytesIO(frozen),mode='r:gz') as archive:
        for role,old in {'merchant':'visual/community-payment/merchant-dashboard/index.html','community':'visual/community-local-e2e/community.html','beneficiary':'visual/community-local-e2e/beneficiary.html','platform':'visual/community-local-e2e/platform.html'}.items():
            html=archive.extractfile('pr122-site-hub/overlay/public/'+old).read().decode()
            def links(match):
                value=match[2]
                if value.startswith(('/','#','https:','http:','data:')):return match[0]
                return match[1]+'="'+urljoin('/'+old,value)+'"'
            html=re.sub(r'(src|href)="([^"]+)"',links,html)
            html=html.replace('</head>','<link rel="stylesheet" href="./role.css"></head>',1)
            bar='<nav class="device-role-tools" aria-label="项目导航"><a href="/visual/community-payment/">← 返回项目</a><span>模拟体验 · 无真实资金</span></nav>'
            html=html.replace('<body>','<body data-preview-role="'+role+'">'+bar,1)
            html=html.replace('</body>','<script src="./role.js" defer></script></body>',1)
            files[TARGET+role+'.html']=(prepare_mobile_page(html,role+'.html') if derive_navigation else html).encode()
    dependency=root/'demos/community-local-e2e/app.js'
    # Production uses the existing stage adapter, not a duplicate payment engine.
    import re
    app=dependency.read_text().replace('"/demo/','"/_preview/community-api/').replace("'/demo/","'/_preview/community-api/")
    app=re.sub(r'credentials\s*:\s*["\']omit["\']','credentials:"same-origin"',app)
    manifest={'schema':1,'state':'REVIEW_ONLY_NOT_DEPLOYED','source_commit':os.environ.get('GITHUB_SHA'),
              'simulation_only':True,'real_payment':False,'private_feedback_open':False,
              'source_owner':'Work integration; original ChatGPT pages retained',
              'inherited_role_package_sha256':hashlib.sha256(frozen).hexdigest(),
              'dependencies':[{'path':'visual/community-local-e2e/app.js','sha256':hashlib.sha256(app.encode()).hexdigest()}],
              'files':[{'path':n,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in sorted(files.items())]}
    if derive_navigation:
        manifest['navigation_derivation']={'state':'NEW_CANDIDATE_PENDING_REVIEW','source_commit':os.environ.get('GITHUB_SHA','UNKNOWN'),'mechanisms':[{'path':name,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()} for name in ('scripts/pr122_community_experience_package.py','demos/work-community-experience/role.js')]}
    return files,manifest

def build(output,stage=None,derive_navigation=False):
    if derive_navigation and stage is not None:
        raise ValueError('NAVIGATION_DELTA_REQUIRES_FINAL_CANDIDATE_MANIFEST_REBUILD')
    files,manifest=collect_mobile_files(ROOT,derive_navigation)
    raw=(json.dumps(manifest,sort_keys=True,indent=2,ensure_ascii=False)+'\n').encode()
    files['MANIFEST.json']=raw
    output.mkdir(parents=True,exist_ok=True)
    stream=io.BytesIO()
    with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as archive:
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo('pr122-community-experience/'+name);member.mode=0o644;member.size=len(data);archive.addfile(member,io.BytesIO(data))
    package=stream.getvalue();(output/'COMMUNITY_EXPERIENCE_REVIEW_ONLY.tar.gz').write_bytes(package)
    (output/'COMMUNITY_EXPERIENCE_MANIFEST.json').write_bytes(raw)
    if stage is not None:
        public=stage/'public'
        assert (stage/'MANIFEST.json').is_file() and public.is_dir(),'TEST_STAGE_REQUIRED'
        for row in manifest['dependencies']:
            assert hashlib.sha256((public/row['path']).read_bytes()).hexdigest()==row['sha256'],'DEPENDENCY_DRIFT'
        for name,data in files.items():
            if name=='MANIFEST.json':continue
            p=public/name;assert not p.exists(),'NO_OVERWRITE'
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    print(json.dumps({'state':'REVIEW_ONLY','tar_sha256':hashlib.sha256(package).hexdigest(),
                      'manifest_sha256':hashlib.sha256(raw).hexdigest(),'files':len(manifest['files']),'production_changes':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--stage',type=Path);p.add_argument('--derive-navigation',action='store_true');a=p.parse_args();build(a.output,a.stage,a.derive_navigation)
