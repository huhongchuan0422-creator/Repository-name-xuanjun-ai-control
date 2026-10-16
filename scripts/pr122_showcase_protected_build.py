"""Fixed-code, data-only protected showcase builder. Never activates a website.

Install/deployment and Owner trust enrollment are separate permissions. The CLI
has no arbitrary source, command, output, environment or policy arguments.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.request
from scripts import pr122_showcase as site
from scripts import pr122_showcase_trust as trust
from scripts.pr122_showcase_sources import verify_review, WORKFLOW_ID, REPO
from scripts.pr122_showcase_package import build as package

CODE = Path('/usr/local/lib/xuanjun-showcase')
CONFIG = Path('/etc/xuanjun-showcase')
BASE = Path('/var/lib/xuanjun-showcase-builder')
REQUEST = CONFIG / 'BUILDER_REQUEST.json'
SHELL = CONFIG / 'APPROVED_SITE_SHELL.tar.gz'


def private_bytes(path, limit=16000000):
    for parent in reversed((path, *path.parents)):
        s = parent.lstat()
        site.need(s.st_uid == 0 and not stat.S_ISLNK(s.st_mode) and not stat.S_IMODE(s.st_mode) & 0o022, 'BUILDER_TRUSTED_PATH')
        if parent != path: site.need(stat.S_ISDIR(s.st_mode), 'BUILDER_PARENT_TYPE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        site.need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o600 and s.st_size <= limit, 'BUILDER_PRIVATE_INPUT')
        return f.read(limit+1)


def fetch(path):
    # Public repository; no token/proxy/keylog env is consumed by this adapter.
    request = urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,
        headers={'Accept':'application/vnd.github+json','User-Agent':'XuanJun-Protected-Builder'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=20) as response:
        raw=response.read(12000001)
        site.need(len(raw)<=12000000,'BUILDER_GITHUB_RESPONSE_LIMIT')
        return json.loads(raw)


def safe_data_path(name):
    path=Path(name)
    site.need(type(name) is str and re.fullmatch(r'showcase/[A-Za-z0-9_./-]+',name) and '..' not in path.parts and not any(p.startswith('.') for p in path.parts), 'BUILDER_DATA_PATH')
    if name=='showcase/published-main-r2.json':return path
    site.need(len(path.parts)>=4 and path.parts[:2]==('showcase','projects'), 'BUILDER_DATA_NAMESPACE')
    declaration=len(path.parts)==4 and path.suffix=='.json'
    asset=len(path.parts)>=8 and path.parts[3]=='views' and path.parts[5].startswith('v') and path.parts[6]=='public'
    site.need(declaration or (asset and path.suffix.lower() in {'.html','.css','.js','.mjs','.json','.png','.jpg','.jpeg','.webp','.svg','.ico','.woff','.woff2'}), 'BUILDER_DATA_TYPE')
    return path


def materialize(commit, output, api):
    # Read only declarations and public assets; never fetch/import/execute remote
    # Python, workflow, package hooks or shell scripts, even from approved commits.
    metadata=api('git/commits/'+commit)
    site.need(metadata['sha']==commit,'BUILDER_SOURCE_COMMIT')
    tree=api('git/trees/'+metadata['tree']['sha']+'?recursive=1')
    site.need(tree.get('sha')==metadata['tree']['sha'] and not tree.get('truncated'),'BUILDER_SOURCE_TREE')
    rows=[r for r in tree['tree'] if r['type']=='blob' and (r['path'].startswith('showcase/projects/') or r['path']=='showcase/published-main-r2.json')]
    site.need(0<len(rows)<=2000 and len({r['path'] for r in rows})==len(rows),'BUILDER_SOURCE_COUNT')
    total=0
    for row in rows:
        path=safe_data_path(row['path'])
        site.need(row['mode']=='100644','BUILDER_SOURCE_MODE')
        blob=api('git/blobs/'+row['sha'])
        site.need(blob.get('encoding')=='base64','BUILDER_BLOB_ENCODING')
        raw=base64.b64decode(''.join(blob['content'].split()),validate=True)
        total+=len(raw)
        site.need(len(raw)<=8000000 and total<=64000000,'BUILDER_SOURCE_SIZE')
        site.need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==row['sha'],'BUILDER_BLOB_IDENTITY')
        target=output/path;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(raw)
    return metadata['tree']['sha']


def validate_request(request, now):
    fields={'schema','commit','ci_run_id','review_comment_ids','reviewer_logins','mechanism_manifest_sha256','shell_tar_sha256','legacy_pages_sha256','issued_unix','expires_unix'}
    site.need(type(request) is dict and set(request)==fields and request['schema']==1,'BUILDER_REQUEST_SCHEMA')
    site.need(type(request['commit']) is str and re.fullmatch('[0-9a-f]{40}',request['commit']),'BUILDER_COMMIT')
    for key in ('mechanism_manifest_sha256','shell_tar_sha256','legacy_pages_sha256'):
        site.need(type(request[key]) is str and re.fullmatch('[0-9a-f]{64}',request[key]),'BUILDER_REQUEST_HASH')
    site.need(type(request['ci_run_id']) is int and request['ci_run_id']>0,'BUILDER_CI_ID')
    ids=request['review_comment_ids'];logins=request['reviewer_logins']
    site.need(type(ids) is list and bool(ids) and len(ids)<=100 and all(type(i) is int and i>0 for i in ids) and len(set(ids))==len(ids),'BUILDER_REVIEW_IDS')
    site.need(type(logins) is list and bool(logins) and all(type(v) is str and re.fullmatch('[A-Za-z0-9-]{1,100}',v) for v in logins),'BUILDER_REVIEW_LOGINS')
    start,end=request['issued_unix'],request['expires_unix']
    site.need(type(start) is int and type(end) is int and start<=now<end and 0<end-start<=7200,'BUILDER_REQUEST_EXPIRED')


def construct(request, stage, shell, api=fetch):
    """Pure candidate construction in a newly owned stage, no deployment code."""
    validate_request(request,time.time())
    run=api('actions/runs/'+str(request['ci_run_id']))
    site.need(run['head_sha']==request['commit'] and run['status']=='completed' and run['conclusion']=='success' and run['workflow_id']==WORKFLOW_ID and run['event'] in ('push','workflow_dispatch'),'BUILDER_EXACT_CI')
    tree=materialize(request['commit'],stage/'source',api)
    registry=stage/'source/showcase';objects=site.discover(registry)
    approvals={}
    for identifier in sorted(request['review_comment_ids']):
        approvals.update(verify_review(identifier,objects,set(request['reviewer_logins']),api,known_only=True))
    site.need(bool(approvals) and any(v['decision']=='PUBLIC_CONTENT_APPROVED' for v in approvals.values()),'BUILDER_NO_APPROVED_CONTENT')
    pages_raw=(registry/'published-main-r2.json').read_bytes()
    site.need(site.sha(pages_raw)==request['legacy_pages_sha256'],'BUILDER_LEGACY_MAPPING')
    owned,files=site.project_public_pages(registry,objects,approvals)
    # Until separately configured/audited authority stores exist, an empty market
    # is deliberate. Never synthesize sellable prices or module admissions.
    catalog=site.compile_catalog(objects,approvals,{}, {**json.loads(pages_raw),**owned})
    manifest=site.render(catalog,stage/'public',False,files,shell)
    (stage/'public/SHOWCASE_MANIFEST.json').write_bytes(site.canonical(manifest))
    result=package(stage/'public',stage/'SHOWCASE_RELEASE.pending',False)
    result.update(source_commit=request['commit'],source_tree=tree,source_ci_run_id=request['ci_run_id'],review_comment_ids=request['review_comment_ids'],production_changes=0,state='CANDIDATE_AWAIT_ARTIFACT_AUDIT_AND_RELEASE_PERMISSION')
    return result


def verified_code(expected):
    # All execution uses the already installed, reviewed mechanism, not code from
    # the content commit. No git checkout or subprocess is used by this builder.
    site.need(Path(__file__).resolve().parent.parent==CODE,'BUILDER_INSTALLED_CODE_ONLY')
    manifest_path=CODE/'MECHANISM_MANIFEST.json'
    raw=manifest_path.read_bytes();site.need(site.sha(raw)==expected,'BUILDER_CODE_MANIFEST')
    manifest=json.loads(raw)
    for row in manifest['files']:
        name=Path(row['path'])
        site.need(not name.is_absolute() and '..' not in name.parts,'BUILDER_CODE_PATH')
        target=CODE/name
        for ancestor in (target,*target.parents):
            s=ancestor.lstat();site.need(s.st_uid==0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode&0o022,'BUILDER_CODE_OWNER')
        data=target.read_bytes();site.need(len(data)==row['size'] and site.sha(data)==row['sha256'],'BUILDER_CODE_DRIFT')
    site.need(any(r['path']=='scripts/pr122_showcase_protected_build.py' for r in manifest['files']),'BUILDER_SELF_BINDING')


def durable_write(path, raw):
    fd=os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())

def main():
    site.need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','BUILDER_FIXED_HOST_ROOT')
    raw=private_bytes(REQUEST);request=json.loads(raw);validate_request(request,time.time())
    verified_code(request['mechanism_manifest_sha256'])
    site.need(site.sha(private_bytes(SHELL))==request['shell_tar_sha256'],'BUILDER_SHELL_HASH')
    shell=site.official_shell(SHELL,request['shell_tar_sha256'])
    before=private_bytes(trust.TRUST)
    for ancestor in (BASE,*BASE.parents):
        a=ancestor.lstat();site.need(stat.S_ISDIR(a.st_mode) and a.st_uid==0 and not stat.S_ISLNK(a.st_mode) and not a.st_mode&0o022,'BUILDER_BASE_PARENT')
    os.umask(0o077)
    s=BASE.lstat();site.need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700 and not BASE.is_symlink(),'BUILDER_BASE_REQUIRED')
    stage=BASE/('build-'+site.sha(raw));stage.mkdir(mode=0o700)
    try:
        result=construct(request,stage,shell)
        site.need(private_bytes(REQUEST)==raw and private_bytes(trust.TRUST)==before,'BUILDER_REQUEST_OR_TRUST_DRIFT')
        validate_request(request,time.time())
        # Recheck exact comments, CI and trust immediately before candidate seal.
        objects=site.discover(stage/'source/showcase')
        for identifier in request['review_comment_ids']:
            verify_review(identifier,objects,set(request['reviewer_logins']),fetch,known_only=True)
        site.need(private_bytes(trust.TRUST)==before,'BUILDER_FINAL_TRUST_DRIFT')
        validate_request(request,time.time())
        result.update(request_sha256=site.sha(raw),trust_snapshot_sha256=site.sha(before),mechanism_manifest_sha256=request['mechanism_manifest_sha256'])
        durable_write(stage/'BUILD_RECEIPT.json',site.canonical(result))
        with (stage/'SHOWCASE_RELEASE.pending').open('rb') as stream:os.fsync(stream.fileno())
        os.rename(stage/'SHOWCASE_RELEASE.pending',stage/'SHOWCASE_RELEASE.tar.gz')
        fd=os.open(stage,os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        print(json.dumps(result,sort_keys=True))
    except Exception:
        durable_write(stage/'BUILD_HOLD.json',site.canonical({'state':'HOLD','retry_allowed':False,'production_changes':0}))
        raise

if __name__=='__main__':main()
