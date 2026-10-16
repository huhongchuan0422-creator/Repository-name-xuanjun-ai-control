"""Compose two exact reviewed static artifacts. No activation or root capability."""
import argparse
import gzip
import hashlib
import io
import json
import re
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
STATIC_SHA='6d641401eb9212d3a6745f07bdf9b8a845aaaeb9fbf03542a8b63eafc38a4d19'
MOBILE_SHA='c24c657ebb101a1a26b56ed2dcd510c676e02d43c1f9dcfbceed9cd28c166d9f'
BASE_SHA='b66eba8c958b10925064053f41dc575a6eb301616bc414d139cdddd98a2e7cb3'
TARGET='visual/community-payment/mobile/'
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return (json.dumps(x,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
def need(ok,why):
    if not ok:raise ValueError(why)
def unpack(raw,digest,prefix,count):
    need(sha(raw)==digest,'INPUT_HASH')
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as a:
        ms=a.getmembers();need(len(ms)==count and len({m.name for m in ms})==count,'MEMBERS')
        need(all(m.isfile() and m.name.startswith(prefix) and '..' not in Path(m.name).parts and 0<=m.size<=8000000 for m in ms),'PATH_OR_TYPE')
        need(sum(m.size for m in ms)<=24000000,'TOTAL_SIZE')
        return {m.name.removeprefix(prefix):a.extractfile(m).read() for m in ms}
def verify(files,rows,exclude):
    need({x['path'] for x in rows}==set(files)-set(exclude) and len(rows)==len(set(files)-set(exclude)),'MANIFEST_SET')
    for x in rows:need(len(files[x['path']])==x['size'] and sha(files[x['path']])==x['sha256'],'MANIFEST_FILE:'+x['path'])
def archive(files):
    buf=io.BytesIO()
    with gzip.GzipFile(filename='',fileobj=buf,mode='wb',mtime=0) as z,tarfile.open(fileobj=z,mode='w') as a:
        for name,b in sorted(files.items()):
            m=tarfile.TarInfo('pr122-site-hub/'+name);m.size=len(b);m.mode=0o644;a.addfile(m,io.BytesIO(b))
    return buf.getvalue()
def compose(static,mobile):
    files=unpack(static,STATIC_SHA,'pr122-site-hub/',449)
    verify(files,json.loads(files['PACKAGE_MANIFEST.json'])['files'],['PACKAGE_MANIFEST.json'])
    phones=unpack(mobile,MOBILE_SHA,'pr122-community-experience/',10)
    m=json.loads(phones['MANIFEST.json']);verify(phones,m['files'],['MANIFEST.json'])
    need(m['source_commit']=='790937a5c96afcf3b3660e36cf36cfaab2002a72' and m['real_payment'] is False and m['private_feedback_open'] is False,'MOBILE_SCOPE')
    for dep in m['dependencies']:need(sha(files['overlay/public/'+dep['path']])==dep['sha256'],'DEPENDENCY_DRIFT')
    candidate=json.loads(files['candidate-manifest.json']);need(len(candidate['files'])==1279,'BASE_COUNT')
    known={x['path']:x for x in candidate['files']};pin=json.loads(files['source-pin.json'])
    for name,b in phones.items():
        if name=='MANIFEST.json':continue
        need(name.startswith(TARGET) and name not in known and 'overlay/public/'+name not in files,'MOBILE_COLLISION')
        files['overlay/public/'+name]=b;pin['overlay_baselines'][name]=None
        known[name]={'path':name,'size':len(b),'sha256':sha(b),'mode':'0644','uid':0,'gid':0}
    old_new={
      '/visual/community-local-e2e/index.html':'/'+TARGET,
      '/visual/community-payment/merchant-dashboard/':'/'+TARGET+'merchant.html',
      **{'/visual/community-local-e2e/'+r+'.html':'/'+TARGET+r+'.html' for r in ('platform','community','beneficiary')}}
    entry=[]
    for locale in ('','zh-cn/','en/'):
        name=locale+'visual/community-payment/index.html';key='overlay/public/'+name;s=files[key].decode()
        for old,new in old_new.items():
            token='href="'+old+'"';need(s.count(token)==1,'ROLE_LINK_DRIFT:'+name+':'+old)
            s=s.replace(token,'href="'+new+'"')
        files[key]=s.encode();known[name]['sha256']=sha(files[key]);known[name]['size']=len(files[key]);entry.append(name)
    candidate['files']=[known[k] for k in sorted(known)];candidate['file_count']=len(known)
    files['candidate-manifest.json']=canonical(candidate);files['source-pin.json']=canonical(pin)
    provenance={'schema':1,'state':'REVIEW_ONLY_NOT_AUTHORIZED','production_approved':False,
       'static':{'source_commit':'e654af3a6a0d59f34b27bbbf8ba3518783c6f719','tar_sha256':STATIC_SHA,'review_comment_id':6217671312},
       'mobile':{'source_commit':m['source_commit'],'tar_sha256':MOBILE_SHA,'review_comment_id':6217103876,'manifest_sha256':sha(phones['MANIFEST.json'])},
       'target_baseline':{'release_id':'pr122-hub-experience-ca7ab933-r2','static_tar_sha256':BASE_SHA,'file_count':1279,'root_receipt_sha256':'PENDING_TARGET_READONLY'},
       'mobile_files':[{'path':x['path'],'sha256':x['sha256']} for x in m['files']],
       'changed_entry_pages':entry,'new_api':False,'runtime_changed':False,'customer_data_open':False}
    files['COMPOSITION_MANIFEST.json']=canonical(provenance)
    files['PACKAGE_MANIFEST.json']=canonical({'schema_version':2,'files':[{'path':k,'size':len(b),'sha256':sha(b)} for k,b in sorted(files.items()) if k!='PACKAGE_MANIFEST.json']})
    need(len(files)==459 and len(known)==1288,'COMPOSED_COUNT')
    return files

def routes(files):
    names=[k for k,v in json.loads(files['source-pin.json'])['overlay_baselines'].items() if v is None]
    need(len(names)==101,'NEW_PUBLIC_COUNT');mapping={}
    for name in names:
        need(re.fullmatch(r'[A-Za-z0-9_./-]+',name) and '..' not in Path(name).parts,'ROUTE_PATH')
        mapping['/'+name]=('file','/'+name)
        if name.endswith('/index.html'):
            directory='/'+name[:-10];mapping[directory]=('file','/'+name);mapping[directory.rstrip('/')]=('redirect',directory)
    text='# PR122 exact reviewed public files; original routes remain in place.\n'
    for path,(kind,target) in sorted(mapping.items()):
        if kind=='redirect':text+='location = '+path+' { return 308 '+target+'; }\n'
        else:
            mime='    types { application/javascript js mjs; }\n    default_type application/javascript;\n' if target.endswith(('.js','.mjs')) else '    default_type text/css;\n' if target.endswith('.css') else '    default_type text/html;\n'
            text+='location = '+path+' {\n    include /etc/nginx/pr122-minimal-cutover/static-security.conf;\n'+mime+'    try_files '+target+' =404;\n}\n'
    return (text+files['runtime-config/server-location.conf'].decode()).encode(),mapping

def smoke_routes(files):
    mapping=dict(routes(files)[1])
    for name in files:
        if not name.startswith('overlay/public/'):continue
        target='/'+name.removeprefix('overlay/public/');route=target
        if target=='/index.html':route='/'
        elif target.count('/')==1 and target.endswith('.html'):route=target[:-5]
        row=('file',target);need(route not in mapping or mapping[route]==row,'SMOKE_ROUTE_COLLISION')
        mapping[route]=row
    return mapping

def build(static,mobile,output,stage=None):
    need(not output.exists(),'OUTPUT_EXISTS');files=compose(static.read_bytes(),mobile.read_bytes());raw=archive(files)
    output.mkdir(parents=True)
    (output/'PR122_UNIFIED_REVIEW_ONLY.tar.gz').write_bytes(raw)
    receipt={'state':'UNIFIED_REVIEW_ONLY_NOT_AUTHORIZED','tar_sha256':sha(raw),'package_manifest_sha256':sha(files['PACKAGE_MANIFEST.json']),
       'candidate_manifest_sha256':sha(files['candidate-manifest.json']),'composition_manifest_sha256':sha(files['COMPOSITION_MANIFEST.json']),
       'member_count':len(files),'manifest_count':len(files)-1,'public_file_count':1288,'new_file_count':101,'overlay_file_count':416,'production_changes':0}
    snippet,mapping=routes(files);receipt['locations_sha256']=sha(snippet);receipt['exact_routes']=len(mapping)
    (output/'locations.conf').write_bytes(snippet)
    (output/'UNIFIED_RECEIPT.json').write_bytes(canonical(receipt))
    (output/'COMPOSITION_MANIFEST.json').write_bytes(files['COMPOSITION_MANIFEST.json'])
    if stage:
        need((stage/'MANIFEST.json').is_file(),'TEST_STAGE_REQUIRED')
        # Only add the nine reviewed phone assets and wire the three entry pages.
        names=[k.removeprefix('overlay/public/') for k in files if k.startswith('overlay/public/'+TARGET)]
        names+=json.loads(files['COMPOSITION_MANIFEST.json'])['changed_entry_pages']
        for name in names:
            p=stage/'public'/name
            need(name.startswith(TARGET) or p.is_file(),'STAGE_ENTRY_MISSING')
            if name.startswith(TARGET):need(not p.exists(),'STAGE_MOBILE_COLLISION')
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(files['overlay/public/'+name])
    print(json.dumps(receipt));return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--static',type=Path,required=True);p.add_argument('--mobile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--stage',type=Path);a=p.parse_args();build(a.static,a.mobile,a.output,a.stage)
