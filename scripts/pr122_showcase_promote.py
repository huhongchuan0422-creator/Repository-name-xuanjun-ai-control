#!/usr/bin/env python3
"""Fixed domestic static showcase publisher; reuse the original reviewed engine.

Transport/installation require a protected operator channel. No automatic apply
retry, Runtime operations, Nginx edits, DNS changes or unrelated website writes.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import time
from types import SimpleNamespace
from scripts.pr122_showcase import need,sha,canonical
from scripts.pr122_showcase_sources import github,WORKFLOW_ID

BASE=Path('/var/lib/xuanjun-showcase')
POLICY=Path('/etc/xuanjun-showcase/policy.json')
PUBLISHER=Path(__file__).resolve().with_name('pr122_website_release.py')
PUBLISHER_SHA='7253f3b86a6ad17dadc85c26deda17a5ccaaa8f76c65da21572be39658993895'


def load_engine():
    need(sha(PUBLISHER.read_bytes())==PUBLISHER_SHA,'PUBLISHER_SOURCE_DRIFT')
    spec=importlib.util.spec_from_file_location('showcase_reviewed_publisher',PUBLISHER);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    # The only policy adaptation: a fixed, isolated showcase namespace. All
    # envelope, transaction, deadline, locking and recovery logic stays unchanged.
    module.APPROVED_BASE=BASE
    return module


def approval(comment_id,policy,fetch=github,now=None):
    now=time.time() if now is None else now
    c=fetch('issues/comments/'+str(comment_id));need(c['id']==comment_id and c['user']['login'] in policy['publishers'] and c['issue_url'].endswith('/issues/122'),'RELEASE_COMMENT_ORIGIN')
    need(c['body'].startswith('XUANJUN_SHOWCASE_RELEASE\n'),'RELEASE_COMMENT_FORMAT');gate=json.loads(c['body'].split('\n',1)[1])
    need(gate.get('decision')=='RELEASE_APPROVED' and gate.get('scope')=='SHOWCASE_STATIC_ONLY' and gate.get('max_executions')==1 and gate.get('rollback_approved') is True,'RELEASE_DECISION')
    start=gate['issued_unix'];end=gate['expires_unix'];need(type(start) is int and type(end) is int and start<=now<end and 0<end-start<=7200,'RELEASE_EXPIRY')
    need(type(gate['artifact_id']) is int and type(gate['ci_run_id']) is int,'RELEASE_IDS')
    for key in ('tar_sha256','package_manifest_sha256'):need(type(gate[key]) is str and len(gate[key])==64 and all(ch in '0123456789abcdef' for ch in gate[key]),'RELEASE_HASH')
    need(gate['review_comment_id']!=comment_id,'SEPARATE_REVIEW_REQUIRED')
    review=fetch('issues/comments/'+str(gate['review_comment_id']))
    need(review['id']==gate['review_comment_id'] and review['user']['login'] in policy['reviewers'] and review['issue_url'].endswith('/issues/122') and review['body'].startswith('XUANJUN_SHOWCASE_PUBLICATION_REVIEW\n'),'PUBLICATION_REVIEW_ORIGIN')
    body=json.loads(review['body'].split('\n',1)[1]);need(body.get('decision')=='AUDIT_PASS' and body.get('reviewer_role')=='INDEPENDENT_AUDITOR','INDEPENDENT_PUBLICATION_REVIEW')
    for key in ('tar_sha256','package_manifest_sha256','commit','ci_run_id'):need(body.get(key)==gate[key],'PUBLICATION_REVIEW_BINDING:'+key)
    run=fetch('actions/runs/'+str(gate['ci_run_id']))
    need(run['head_sha']==gate['commit'] and run['status']=='completed' and run['conclusion']=='success' and run['workflow_id']==WORKFLOW_ID and run['event'] in ('push','workflow_dispatch'),'EXACT_RELEASE_CI')
    artifact=fetch('actions/artifacts/'+str(gate['artifact_id']));need(not artifact['expired'] and artifact['workflow_run']['id']==gate['ci_run_id'] and artifact['workflow_run']['head_sha']==gate['commit'],'ARTIFACT_CI_BINDING')
    gate['release_comment_id']=comment_id
    return gate


def unpack(raw,gate):
    need(len(raw)<=16000000 and sha(raw)==gate['tar_sha256'],'PUBLICATION_TAR_HASH')
    expected={'showcase-release/'+name for name in ('source.tar.gz','PUBLICATION.json','bundle/candidate-manifest.json','bundle/source-pin.json','bundle/PACKAGE_MANIFEST.json')}
    data={};total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r|gz') as archive:
        for m in archive:
            need(m.isfile() and m.name in expected and m.name.removeprefix('showcase-release/') not in data and 0<=m.size<=16000000,'PUBLICATION_MEMBERS')
            total+=m.size;need(total<=40000000,'PUBLICATION_EXPANSION_LIMIT')
            value=archive.extractfile(m).read(m.size+1);need(len(value)==m.size,'TRUNCATED_PUBLICATION_FILE')
            data[m.name.removeprefix('showcase-release/')]=value
    need({'showcase-release/'+n for n in data}==expected,'PUBLICATION_MEMBERS')
    need(json.loads(data['PUBLICATION.json'])=={'schema':1,'preview_only':False,'scope':'SHOWCASE_STATIC_ONLY','public_file_count':len(json.loads(data['bundle/candidate-manifest.json'])['files'])},'NOT_A_PRODUCTION_CANDIDATE')
    need(sha(data['bundle/PACKAGE_MANIFEST.json'])==gate['package_manifest_sha256'],'PACKAGE_MANIFEST_HASH')
    for row in json.loads(data['bundle/PACKAGE_MANIFEST.json'])['files']:
        name='bundle/'+row['path'];need(name in data and len(data[name])==row['size'] and sha(data[name])==row['sha256'],'PACKAGE_FILE_HASH')
    pin=json.loads(data['bundle/source-pin.json']);need(not pin['overlay_baselines'] and sha(data['source.tar.gz'])==pin['source_archive_sha256'] and len(data['source.tar.gz'])==pin['source_archive_size'],'SNAPSHOT_SOURCE_HASH')
    rows=json.loads(data['bundle/candidate-manifest.json'])['files'];need(0<len(rows)<=5000,'PUBLIC_COUNT')
    names=set();expected_files={}
    for row in rows:
        name=row['path'];path=Path(name)
        need(not path.is_absolute() and '..' not in path.parts and path.parts[0]=='showcase' and all(not part.startswith('.') for part in path.parts),'PUBLIC_NAMESPACE')
        need(path.suffix.lower() in ('.html','.css','.js','.mjs','.json','.png','.jpg','.jpeg','.webp','.svg','.ico','.woff','.woff2'),'PUBLIC_TYPE')
        import re
        need(re.fullmatch(r'showcase/[A-Za-z0-9_./-]+',name),'PUBLIC_FILENAME')
        need(name not in names,'DUPLICATE_PUBLIC_FILE');names.add(name);expected_files['package/public/'+name]=row
    observed=set();total=0
    with tarfile.open(fileobj=io.BytesIO(data['source.tar.gz']),mode='r|gz') as source:
        for m in source:
            need(m.isfile() and m.name in expected_files and m.name not in observed and 0<=m.size<=8000000,'SOURCE_FILE_IDENTITY')
            observed.add(m.name);total+=m.size;need(total<=100000000,'SOURCE_EXPANSION_LIMIT')
            raw=source.extractfile(m).read(m.size+1);row=expected_files[m.name]
            need(len(raw)==m.size==row['size'] and sha(raw)==row['sha256'],'SOURCE_MANIFEST_BINDING')
    need(observed==set(expected_files),'SOURCE_FILE_SET')
    return data


def https_smoke(manifest,deadline):
    import urllib.request
    for row in manifest['files']:
        deadline.check('SHOWCASE_HTTPS')
        request=urllib.request.Request('https://wenwenwenyiyiyi.work/'+row['path'],headers={'User-Agent':'XuanJun-Showcase-Release'})
        with urllib.request.urlopen(request,timeout=5) as response:
            raw=response.read(row['size']+1)
            need(response.status==200 and len(raw)==row['size'] and sha(raw)==row['sha256'],'SHOWCASE_HTTPS_FILE:'+row['path'])
            need(response.headers.get('Content-Security-Policy') and response.headers.get('X-Content-Type-Options')=='nosniff','SHOWCASE_HTTPS_HEADERS')
    return {'real_https':True,'files':len(manifest['files']),'browser':'PENDING'}


def publish(raw,gate,engine=None,smoke=https_smoke):
    engine=engine or load_engine();data=unpack(raw,gate)
    import shutil
    total=sum(row['size'] for row in json.loads(data['bundle/candidate-manifest.json'])['files'])
    need(shutil.disk_usage(BASE.parent).free>=max(3*total+len(raw),268435456),'INSUFFICIENT_RELEASE_DISK_SPACE')
    tx='showcase-'+str(gate['artifact_id']);release='showcase-'+gate['tar_sha256'][:20]
    engine.secure_dir(BASE,0o755,os.geteuid(),True)
    with engine.Deadline(180) as deadline,engine.lock(BASE,5,deadline,os.geteuid()):
        need(not (BASE/'transactions'/(tx+'.json')).exists(),'TRANSACTION_EXISTS_DO_NOT_RETRY')
        previous=os.readlink(BASE/'current') if (BASE/'current').is_symlink() else None
        need(previous==gate.get('previous_release'),'PREVIOUS_POINTER_DRIFT')
        previous_manifest=None
        if previous is not None:
            old=engine.direct_previous_release(BASE,previous);previous_manifest=engine.snapshot(old/'public',deadline)
            engine.verify_tree(old/'public',previous_manifest,deadline,0)
            need(sha(canonical(previous_manifest))==gate.get('previous_manifest_sha256'),'PREVIOUS_MANIFEST_DRIFT')
        else:need(gate.get('previous_manifest_sha256') is None,'UNEXPECTED_FIRST_BASELINE')
        private=BASE/'inputs';engine.secure_dir(private,0o700,os.geteuid(),True)
        folder=private/tx;need(not folder.exists(),'INPUT_TRANSACTION_EXISTS');folder.mkdir(mode=0o700)
        # Immutable exact input bytes are the rollback archive for this snapshot.
        (folder/'approved-source.tar.gz').write_bytes(raw);(folder/'approval.json').write_bytes(canonical(gate))
        for name,value in data.items():
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.write_bytes(value)
        args=SimpleNamespace(webroot_base=BASE,bundle=folder/'bundle',source_archive=folder/'source.tar.gz',transaction_id=tx,release_id=release,
                             approved_package_manifest_sha256=gate['package_manifest_sha256'],lock_wait_seconds=5,deadline_seconds=180,allow_non_root_test=False)
        engine.prepare(args,deadline)
        # An expired approval cannot switch the pointer after preparation.
        need(time.time()<gate['expires_unix'],'GATE_EXPIRED_BEFORE_ACTIVATION')
        if previous is not None:engine.verify_tree(Path(previous)/'public',previous_manifest,deadline,0)
        engine.activate(args,deadline);engine.check(args,deadline)
        checked=smoke(json.loads(data['bundle/candidate-manifest.json']),deadline)
        engine.atomic_json(folder/'HTTPS_RECEIPT.json',checked)
        return {'state':'HTTPS_SMOKE_PASS_AWAIT_BROWSER','transaction_id':tx,'release_id':release,'production_browser':'PENDING','runtime_changes':0,'main_website_pointer_changes':0}



def rollback(artifact_id,engine=None):
    engine=engine or load_engine();need(type(artifact_id) is int and artifact_id>0,'ARTIFACT_ID')
    tx='showcase-'+str(artifact_id);folder=BASE/'inputs'/tx
    raw,_=engine.read_trusted_bytes(folder/'approval.json',0)
    gate=json.loads(raw);need(gate['artifact_id']==artifact_id and gate['rollback_approved'] is True,'ROLLBACK_GATE_BINDING')
    source,_=engine.read_trusted_bytes(folder/'approved-source.tar.gz',0);unpack(source,gate)
    args=SimpleNamespace(webroot_base=BASE,bundle=folder/'bundle',source_archive=folder/'source.tar.gz',transaction_id=tx,
                         release_id='showcase-'+gate['tar_sha256'][:20],approved_package_manifest_sha256=gate['package_manifest_sha256'],
                         lock_wait_seconds=5,deadline_seconds=180,allow_non_root_test=False)
    with engine.Deadline(180) as deadline,engine.lock(BASE,5,deadline,0):
        receipt=engine.load_json(BASE/'transactions'/(tx+'.json'),deadline)
        if receipt['state'] in ('ACTIVATION_INTENT','UNKNOWN_AFTER_ACTIVATE'):receipt=engine.reconcile(args,deadline)
        if receipt['state'] in ('PREPARED','HOLD_PARTIAL','PREPARE_INTENT'):
            observed=os.readlink(BASE/'current') if (BASE/'current').is_symlink() else None
            need(observed==gate.get('previous_release'),'UNEXPECTED_POINTER_BEFORE_ACTIVATE')
            engine.atomic_json(folder/'RECOVERY.json',{'state':'ABORTED_BEFORE_ACTIVATION','retry_apply':False})
            return {'state':'ABORTED_BEFORE_ACTIVATION','production_changes':0}
        result=engine.rollback(args,deadline)
        observed=os.readlink(BASE/'current') if (BASE/'current').is_symlink() else None
        need(observed==gate.get('previous_release'),'ROLLBACK_POINTER')
        return {'state':result['state'],'main_website_pointer_changes':0,'runtime_changes':0}


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('apply','rollback'));p.add_argument('--approval-comment-id',type=int);p.add_argument('--candidate',type=Path);p.add_argument('--artifact-id',type=int);args=p.parse_args()
    need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','FIXED_HOST_ROOT_REQUIRED')
    engine=load_engine()
    for path in (Path(__file__).resolve(),PUBLISHER,POLICY):
        with engine.open_trusted_file(path,0):pass
    os.umask(0o022)
    if args.command=='rollback':print(json.dumps(rollback(args.artifact_id,engine),sort_keys=True));return
    need(args.approval_comment_id and args.candidate,'APPLY_INPUT_REQUIRED')
    policy=json.loads(POLICY.read_text());gate=approval(args.approval_comment_id,policy)
    os.umask(0o022);print(json.dumps(publish(args.candidate.read_bytes(),gate,engine),sort_keys=True))

if __name__=='__main__':main()
