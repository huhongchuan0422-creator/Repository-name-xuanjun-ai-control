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

def build(output,stage=None):
    source=ROOT/'demos/work-community-experience'
    files={TARGET+name:(source/name).read_bytes() for name in ('index.html','experience.css','experience.js','role.css','role.js')}
    # Reuse byte-bound deployed role pages as build data; no iframe/CSP bypass.
    frozen=(ROOT/'evidence/pr122-site-hub-experience/PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes()
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
            bar='<nav class="device-role-tools" aria-label="角色与设备预览"><a href="./">← 消费者体验</a><a href="merchant.html">商家</a><a href="community.html">社区</a><a href="beneficiary.html">分账方</a><a href="platform.html">平台</a><button data-device="phone" type="button">手机视图</button><button data-device="desktop" type="button">电脑视图</button><p>公开模拟预览；各角色范围以原页面说明为准。商家三家样例尚未与消费者订单联动。社区、分账方和平台为现有原型。</p></nav>'
            html=html.replace('<body>','<body data-preview-role="'+role+'">'+bar,1)
            html=html.replace('</body>','<script src="./role.js" defer></script></body>',1)
            files[TARGET+role+'.html']=html.encode()
    dependency=ROOT/'demos/community-local-e2e/app.js'
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
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--stage',type=Path);a=p.parse_args();build(a.output,a.stage)
