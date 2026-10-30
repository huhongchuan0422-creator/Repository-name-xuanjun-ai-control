"""Read only the original fixed 4f Hosted artifact. Never load/run/build an image."""
import datetime
import gzip
import hashlib
import json
import os
import re
import stat
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH='feature/chatgpt-community-wechat-sp-offline-20261017'
WORKFLOW='.github/workflows/chatgpt-community-wechat-sp-offline.yml'
PRODUCT='4f1c3aea2c01ead25c5bd075535b8ce7bd9cd5f5'
IMAGE_CONTROL='151f95b175357867d5bb426783bd74420a83cedb'
IMAGE_RUN=41108321174
IMAGE_JOB=124243988517
ARTIFACT=13002167810
OUTER_BYTES=532467544
OUTER_SHA='e3cd59f1d12d3e1a5386e42c71b2e75f03749a6db7cb985a5758f3e1169d4f82'
CHUNK=262144
MAX_TAR=2147483648
MEMBERS={'community-image-id.txt','community-backend-image.tar.gz',
         'community-image-tests.log','community-backend-image.sha256'}
SOURCE_FILES={'app/scripts/community_platform_reviewer_admission.py': 'b1cd7717e521908e83ee1f5d2b838c1f41c0b0a5ba00322a531c1d84685eb3ba', 'app/scripts/community_reviewer_maintenance.py': '99f5076b3b32a34a12a9b54a76382eeaa721673ddfbf593368fc1a54322e0520', 'app/scripts/community_reviewer_web_bridge.py': '2ecae7a9938c49bc2ae5288cddd3b729c01c4bacd0146195b9f44952f9432529', 'app/scripts/community_mini_http.py': '4f7f6f45955113d9d3eeaa9d0a3693a46d570a3f95b99b46c1d4c2342ead9e4f', 'app/demos/community-stage/web-session.js': '37428f20105d630b48e431aef7c01b5bb040215adc58f8488eabe37f529947f2'}
READ_MARKER='[community-image-evidence-fixed4f]'
SCOPE_MARKER='[community-image-evidence-scope]'

def require(value,code):
    if not value:raise ValueError(code)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def strict_json(raw):
    def pairs(values):
        result={}
        for key,value in values:
            require(key not in result,'DUPLICATE_JSON_KEY')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs)

def copy_hash(src,dest=None,limit=MAX_TAR,chunks=False):
    h=hashlib.sha256();count=0;rows=[]
    while True:
        parts=[];wanted=CHUNK
        while wanted:
            part=src.read(wanted)
            if not part:break
            parts.append(part);wanted-=len(part)
        raw=b''.join(parts)
        if not raw:break
        require(count+len(raw)<=limit,'BYTE_BUDGET_EXCEEDED')
        h.update(raw)
        if dest is not None:dest.write(raw)
        if chunks:rows.append(dict(offset=count,bytes=len(raw),sha256=sha(raw)))
        count+=len(raw)
    result=dict(bytes=count,sha256=h.hexdigest())
    if chunks:result.update(chunk_bytes=CHUNK,chunks=rows)
    return result

def provenance(run,jobs,artifacts,now=None):
    now=time.time() if now is None else now
    require(run.get('id')==IMAGE_RUN and run.get('head_sha')==IMAGE_CONTROL
        and run.get('head_branch')==BRANCH and run.get('path')==WORKFLOW
        and run.get('event')=='workflow_dispatch' and run.get('status')=='completed'
        and run.get('conclusion')=='success' and run.get('repository',{}).get('full_name')==REPO
        and run.get('head_repository',{}).get('full_name')==REPO,'EXACT_IMAGE_RUN_REQUIRED')
    for page,key in [(jobs,'jobs'),(artifacts,'artifacts')]:
        require(type(page.get('total_count')) is int and 0<page['total_count']<=100
            and isinstance(page.get(key),list) and len(page[key])==page['total_count'],'COMPLETE_METADATA_REQUIRED')
    selected=[j for j in jobs['jobs'] if j.get('name')=='community-backend-image']
    require(len(selected)==1 and selected[0].get('id')==IMAGE_JOB
        and selected[0].get('run_id')==IMAGE_RUN and selected[0].get('head_sha')==IMAGE_CONTROL
        and selected[0].get('status')=='completed' and selected[0].get('conclusion')=='success','EXACT_IMAGE_JOB_REQUIRED')
    selected=[a for a in artifacts['artifacts'] if a.get('name')=='community-backend-image-candidate']
    require(len(selected)==1,'EXACT_IMAGE_ARTIFACT_REQUIRED');a=selected[0];w=a.get('workflow_run',{})
    expiry=datetime.datetime.strptime(a.get('expires_at',''),'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc).timestamp()
    require(a.get('id')==ARTIFACT and a.get('expired') is False and expiry>now
        and a.get('size_in_bytes')==OUTER_BYTES and a.get('digest')=='sha256:'+OUTER_SHA
        and w.get('id')==IMAGE_RUN and w.get('head_sha')==IMAGE_CONTROL and w.get('head_branch')==BRANCH
        and w.get('repository_id')==1413132159 and w.get('head_repository_id')==1413132159,'EXACT_IMAGE_ARTIFACT_REQUIRED')
    return dict(repository=REPO,workflow=WORKFLOW,product_source_sha=PRODUCT,image_control_sha=IMAGE_CONTROL,
        image_run=IMAGE_RUN,image_job=IMAGE_JOB,artifact_id=ARTIFACT,artifact_expires_at=a['expires_at'],
        status='SOURCE_IMAGE_BYTES_VERIFIED_NOT_INSTALLED',image_executed=False,site_access=False)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def opener():return build_opener(ProxyHandler({}),NoRedirect())

def api(suffix,token):
    url='https://api.github.com/repos/'+REPO+suffix
    with opener().open(Request(url,headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+token}),timeout=30) as response:
        require(response.status==200 and response.geturl()==url,'EXACT_GITHUB_RESPONSE_REQUIRED')
        raw=response.read(1048577);require(len(raw)<=1048576,'METADATA_BYTE_LIMIT')
        return strict_json(raw)

def download(path,token):
    require(bool(token),'EXISTING_READ_TOKEN_REQUIRED')
    url='https://api.github.com/repos/'+REPO+'/actions/artifacts/'+str(ARTIFACT)+'/zip'
    o=opener()
    try:response=o.open(Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'}),timeout=30)
    except HTTPError as error:
        require(error.code==302,'FIXED_ARTIFACT_REDIRECT_REQUIRED')
        location=error.headers.get('Location','');error.close()
    else:
        response.close();raise ValueError('FIXED_ARTIFACT_REDIRECT_REQUIRED')
    p=urlparse(location)
    require(p.scheme=='https' and p.hostname and not p.username and not p.password
        and p.port in (None,443) and not p.fragment and any(p.hostname.endswith(s) for s in
        ('.blob.core.windows.net','.actions.githubusercontent.com','.githubusercontent.com','.s3.amazonaws.com')),
        'GITHUB_ARTIFACT_STORAGE_REQUIRED')
    # No Authorization on signed storage request. No redirects/proxy/retries.
    with o.open(Request(location),timeout=60) as response,Path(path).open('xb') as out:
        require(response.status==200 and response.geturl()==location,'EXACT_STORAGE_RESPONSE_REQUIRED')
        result=copy_hash(response,out,OUTER_BYTES,True)
    require(result['bytes']==OUTER_BYTES and result['sha256']==OUTER_SHA,'FIXED_OUTER_BYTES_REQUIRED')
    return result

def safe_name(name):
    p=PurePosixPath(name)
    require(bool(name) and str(p)==name and not p.is_absolute() and '..' not in p.parts and '\\' not in name,'ARCHIVE_PATH_REQUIRED')
    return name

def read_small(t,item,limit=1048576):
    require(item.isfile() and 0<=item.size<=limit,'SMALL_REGULAR_MEMBER_REQUIRED')
    raw=t.extractfile(item).read(limit+1);require(len(raw)==item.size,'MEMBER_SIZE_MISMATCH')
    return raw

def inspect_docker(path,image_id):
    rows={};blobs={};layers=[];stamps=[];source_files={};seen=set()
    with tarfile.open(path,'r:') as t:
        items=[]
        for item in t:
            require(len(items)<4096,'DOCKER_MEMBER_LIMIT');items.append(item)
        for item in items:
            name=safe_name(item.name);require(name not in seen,'DUPLICATE_DOCKER_MEMBER');seen.add(name)
            if item.isdir():
                require(name in ('blobs','blobs/sha256'),'UNEXPECTED_DOCKER_DIRECTORY');continue
            require(item.isfile(),'DOCKER_REGULAR_FILE_REQUIRED')
            require(name in ('manifest.json','index.json','oci-layout','repositories')
                or re.fullmatch(r'blobs/sha256/[0-9a-f]{64}',name),'DOCKER_MEMBER_NAME_REQUIRED')
            record=copy_hash(t.extractfile(item),limit=MAX_TAR);rows[name]=dict(record)
            require(record['bytes']==item.size,'MEMBER_SIZE_MISMATCH')
            if name.startswith('blobs/'):
                require(record['sha256']==name.rsplit('/',1)[1],'OCI_BLOB_HASH_MISMATCH')
                blobs[name]=record
        manifest_raw=read_small(t,t.getmember('manifest.json'))
        manifest=strict_json(manifest_raw)
        require(isinstance(manifest,list) and len(manifest)==1,'ONE_DOCKER_IMAGE_REQUIRED')
        image=manifest[0];config_path=image.get('Config')
        require(config_path in blobs and 'sha256:'+blobs[config_path]['sha256']==image_id,'IMAGE_CONFIG_ID_MISMATCH')
        require(image.get('RepoTags')==['community-preview:'+PRODUCT],'FIXED_PRODUCT_TAG_REQUIRED')
        config_raw=read_small(t,t.getmember(config_path));config=strict_json(config_raw)
        c=config.get('config',{});env=c.get('Env',[])
        require(config.get('os')=='linux' and config.get('architecture')=='amd64'
            and c.get('User')=='10001:1008' and c.get('Entrypoint')==['python','-B','-m','scripts.community_platform_host']
            and isinstance(env,list) and [x for x in env if x.startswith('COMMUNITY_SOURCE_SHA=')]==['COMMUNITY_SOURCE_SHA='+PRODUCT]
            and c.get('Labels',{}).get('org.opencontainers.image.revision')==PRODUCT,'FIXED_IMAGE_CONFIGURATION_REQUIRED')
        names=image.get('Layers')
        require(isinstance(names,list) and 0<len(names)<=128 and len(set(names))==len(names)
            and all(n in blobs for n in names),'EXACT_DOCKER_LAYERS_REQUIRED')
        require(config.get('rootfs')=={'type':'layers','diff_ids':['sha256:'+blobs[n]['sha256'] for n in names]},'ROOTFS_DIFF_IDS_REQUIRED')
        index=strict_json(read_small(t,t.getmember('index.json')))
        require(index.get('schemaVersion')==2 and len(index.get('manifests',[]))==1,'EXACT_OCI_INDEX_REQUIRED')
        descriptor=index['manifests'][0];digest=descriptor.get('digest','');oci_path='blobs/'+digest.replace(':','/')
        require(oci_path in blobs and descriptor.get('size')==blobs[oci_path]['bytes'],'OCI_DESCRIPTOR_REQUIRED')
        oci=strict_json(read_small(t,t.getmember(oci_path)))
        require(oci.get('schemaVersion')==2 and oci.get('config',{}).get('digest')==image_id
            and oci.get('config',{}).get('size')==len(config_raw)
            and [d.get('digest') for d in oci.get('layers',[])]==['sha256:'+blobs[n]['sha256'] for n in names]
            and [d.get('size') for d in oci.get('layers',[])]==[blobs[n]['bytes'] for n in names],'OCI_MANIFEST_LINK_REQUIRED')
        total_entries=0
        for name in names:
            count=0
            with tarfile.open(fileobj=t.extractfile(name),mode='r|') as layer:
                for item in layer:
                    count+=1;total_entries+=1
                    require(total_entries<=200000,'LAYER_ENTRY_LIMIT')
                    # Layer paths are never extracted or executed.
                    n=item.name.removeprefix('./')
                    if n!='.':safe_name(n)
                    for tracked in list(source_files)+(['app/COMMUNITY_SOURCE_SHA'] if stamps else []):
                        pieces=tracked.split('/')
                        removals={'.wh..wh..opq'}
                        for i,part in enumerate(pieces):
                            prefix='/'.join(pieces[:i])
                            removals.add((prefix+'/' if prefix else '')+'.wh.'+part)
                            removals.add((prefix+'/' if prefix else '')+'.wh..wh..opq')
                        require(n not in removals,'SOURCE_WHITEOUT_DENIED')
                    if n in ('.wh.app','app/.wh..wh..opq','app/.wh.COMMUNITY_SOURCE_SHA','.wh..wh..opq'):
                        require(not stamps,'SOURCE_STAMP_WHITEOUT_DENIED')
                    protected=set(SOURCE_FILES)|{'app/COMMUNITY_SOURCE_SHA'}
                    ancestors={str(parent) for target in protected for parent in PurePosixPath(target).parents if str(parent)!='.'}
                    if n in ancestors:require(item.isdir(),'SOURCE_ANCESTOR_NOT_DIRECTORY')
                    if n=='app/COMMUNITY_SOURCE_SHA':
                        raw=read_small(layer,item,41)
                        require(raw==(PRODUCT+'\n').encode() and item.mode==0o444,'FIXED_SOURCE_STAMP_REQUIRED')
                        stamps.append(dict(layer=name,path=n,bytes=len(raw),sha256=sha(raw),mode=item.mode,source_sha=PRODUCT))
                    if n in SOURCE_FILES:
                        raw=read_small(layer,item,2000000)
                        require(sha(raw)==SOURCE_FILES[n],'FIXED_SOURCE_FILE_MISMATCH')
                        require(n not in source_files,'DUPLICATE_SOURCE_FILE')
                        source_files[n]=dict(layer=name,bytes=len(raw),sha256=sha(raw))
            layers.append(dict(name=name,bytes=blobs[name]['bytes'],sha256=blobs[name]['sha256'],entries=count))
        require(len(stamps)==1 and set(source_files)==set(SOURCE_FILES),'FIXED_SOURCE_CLOSURE_REQUIRED')
    return dict(image_id=image_id,config_path=config_path,config_bytes=len(config_raw),source_env=PRODUCT,
        oci_revision=PRODUCT,architecture='amd64',entrypoint=c['Entrypoint'],source_stamp=stamps,
        source_files=source_files,layers=layers,layer_entries=total_entries,
        all_oci_blob_path_hashes_verified=True,archive_members=rows,image_manifest=manifest),config_raw,manifest_raw

def inspect_outer(path,work):
    path=Path(path);work=Path(work)
    with path.open('rb') as stream:outer=copy_hash(stream,limit=OUTER_BYTES,chunks=True)
    require(outer['bytes']==OUTER_BYTES and outer['sha256']==OUTER_SHA,'FIXED_OUTER_BYTES_REQUIRED')
    records={}
    with zipfile.ZipFile(path) as z:
        items=z.infolist()
        require(len(items)==4 and {i.filename for i in items}==MEMBERS,'EXACT_IMAGE_MEMBERS_REQUIRED')
        for item in items:
            require(stat.S_ISREG(item.external_attr>>16) and not item.flag_bits&1
                and 0<=item.file_size<=MAX_TAR,'REGULAR_IMAGE_MEMBER_REQUIRED')
            dest=work/item.filename
            with z.open(item) as source,dest.open('xb') as out:records[item.filename]=copy_hash(source,out,MAX_TAR)
            require(records[item.filename]['bytes']==item.file_size,'MEMBER_SIZE_MISMATCH')
    image_raw=(work/'community-image-id.txt').read_bytes()
    require(re.fullmatch(rb'sha256:[0-9a-f]{64}\n',image_raw),'IMAGE_ID_REQUIRED')
    image_id=image_raw.decode().strip()
    checksum=(work/'community-backend-image.sha256').read_text().split()
    require(checksum==[records['community-backend-image.tar.gz']['sha256'],'community-backend-image.tar.gz'],'INNER_GZIP_SHA_REQUIRED')
    tar_path=work/'image.tar'
    with gzip.open(work/'community-backend-image.tar.gz','rb') as source,tar_path.open('xb') as dest:
        raw_tar=copy_hash(source,dest,MAX_TAR)
    layout,config,manifest=inspect_docker(tar_path,image_id)
    return {'OUTER_CHUNKS.json':outer,'MEMBERS.json':records,'RAW_TAR_HASH.json':raw_tar,
        'ACTUAL_DOCKER_ARCHIVE_LAYOUT.json':layout},config,manifest

def main():
    env=os.environ
    require(env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REPOSITORY')==REPO
        and env.get('GITHUB_REF')=='refs/heads/'+BRANCH and re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')),'EXACT_HOSTED_CONTEXT_REQUIRED')
    event=strict_json(Path(env['GITHUB_EVENT_PATH']).read_bytes())
    require(READ_MARKER in event.get('head_commit',{}).get('message','')
        and SCOPE_MARKER in event.get('head_commit',{}).get('message',''),'EXACT_READ_SCOPE_REQUIRED')
    out=Path('community-4f-image-evidence')
    require(not out.exists(),'EVIDENCE_OUTPUT_EXISTS')
    token=env.get('GITHUB_TOKEN','');require(bool(token),'EXISTING_READ_TOKEN_REQUIRED')
    prefix='/actions/runs/'+str(IMAGE_RUN)
    binding=provenance(api(prefix,token),api(prefix+'/jobs?per_page=100',token),api(prefix+'/artifacts?per_page=100',token))
    with tempfile.TemporaryDirectory(prefix='fixed-4f-image-',dir=env['RUNNER_TEMP']) as tmp:
        work=Path(tmp);download(work/'outer.zip',token)
        reports,config,manifest=inspect_outer(work/'outer.zip',work)
        binding.update(evidence_control_sha=env['GITHUB_SHA'],evidence_run_id=env['GITHUB_RUN_ID'],
            fixed_outer_bytes=OUTER_BYTES,fixed_outer_sha256=OUTER_SHA,image_id=reports['ACTUAL_DOCKER_ARCHIVE_LAYOUT.json']['image_id'])
        reports['PROVENANCE.json']=binding
        out.mkdir(mode=0o700)
        for name,value in reports.items():(out/name).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
        (out/'docker-image-config.json').write_bytes(config);(out/'docker-manifest.json').write_bytes(manifest)
        hashes={p.name:dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in out.iterdir()}
        (out/'EVIDENCE_MANIFEST.json').write_text(json.dumps(hashes,sort_keys=True,indent=2)+'\n')
    print('FIXED_4F_IMAGE_BYTES_INSPECTED_NO_LOAD_NO_BUILD_NO_INSTALL')

if __name__=='__main__':
    try:main()
    except Exception as error:
        # No signed URL, token, downloaded body or arbitrary exception text in logs.
        code=error.args[0] if type(error) is ValueError and len(error.args)==1 and re.fullmatch('[A-Z0-9_]{1,90}',str(error.args[0])) else type(error).__name__
        raise SystemExit('FIXED_IMAGE_EVIDENCE_FAILED:'+code) from None
