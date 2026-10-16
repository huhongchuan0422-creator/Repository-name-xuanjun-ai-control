"""Fixed candidate-only root bridge. No caller-selected paths or commands."""
import base64
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys
import time
from scripts import pr122_showcase_protected_build as builder
from scripts import pr122_showcase_trust as trust
from scripts.pr122_showcase import need,canonical,sha

POLICY=Path('/etc/xuanjun-showcase/BUILDER_POLICY.json')
UNIT='xuanjun-showcase-build.service'


def store(path,value):
    raw=canonical(value);temporary=path.with_name(path.name+'.pending')
    builder.durable_write(temporary,raw)
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def policy():
    value=json.loads(builder.private_bytes(POLICY))
    need(set(value)=={'schema','mechanism_manifest_sha256','shell_tar_sha256','legacy_pages_sha256','reviewer_logins'} and value['schema']==1,'BUILDER_POLICY_SCHEMA')
    for key in ('mechanism_manifest_sha256','shell_tar_sha256','legacy_pages_sha256'):
        need(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}',value[key]),'BUILDER_POLICY_HASH')
    need(type(value['reviewer_logins']) is list and bool(value['reviewer_logins']) and all(type(v) is str and re.fullmatch('[A-Za-z0-9-]{1,100}',v) for v in value['reviewer_logins']),'BUILDER_POLICY_LOGINS')
    return value


def selection(value,api):
    snapshot=builder.private_bytes(trust.TRUST);enrolled=json.loads(snapshot);comments=[];now=time.time()
    need(type(enrolled.get('anchors')) is dict,'BUILDER_ANCHORS')
    need(len(enrolled['anchors'])<=1000,'BUILDER_ANCHOR_LIMIT')
    deadline=time.monotonic()+45
    for identifier,anchor in enrolled['anchors'].items():
        if anchor.get('scope')!='CONTENT' or int(identifier) in enrolled['revoked_review_ids']:continue
        if anchor.get('expires_unix',0)<=now:continue
        need(time.monotonic()<deadline and len(comments)<20,'BUILDER_SELECTION_BUDGET')
        c=api('issues/comments/'+identifier)
        need(c['id']==int(identifier) and c['user']['login'] in value['reviewer_logins'] and c['issue_url']=='https://api.github.com/repos/'+builder.REPO+'/issues/122','BUILDER_COMMENT_ORIGIN')
        trust.verify(c,'CONTENT',enrolled)
        need(c['body'].startswith('XUANJUN_SHOWCASE_REVIEW\n'),'BUILDER_CONTENT_FORMAT')
        data=json.loads(c['body'].split('\n',1)[1])
        need(data.get('decision') in ('PUBLIC_CONTENT_APPROVED','PUBLIC_CONTENT_REVOKED'),'BUILDER_CONTENT_DECISION')
        comments.append((c,data,anchor))
    if not comments:return None
    comments.sort(key=lambda row:row[0]['id']);latest=comments[-1]
    request={'schema':1,'commit':latest[1]['commit'],'ci_run_id':latest[1]['ci_run_id'],
        'review_comment_ids':[r[0]['id'] for r in comments],**{k:value[k] for k in ('mechanism_manifest_sha256','shell_tar_sha256','legacy_pages_sha256','reviewer_logins')},
        'issued_unix':int(now),'expires_unix':min(int(now)+7200,min(r[2]['expires_unix'] for r in comments))}
    builder.validate_request(request,now)
    key=sha(canonical({'policy':value,'trust_sha256':sha(snapshot),'comments':[[r[0]['id'],sha(r[0]['body'].encode())] for r in comments]}))
    return key,request,snapshot


def execute(value,api=builder.fetch,command=subprocess.run):
    state_path=builder.BASE/'CHANNEL_STATE.json'
    previous=json.loads(builder.private_bytes(state_path)) if state_path.exists() else None
    if previous:need(previous['state'] in ('BUILT','EXPORTED'),'BUILDER_CHANNEL_HOLD_NO_RETRY')
    chosen=selection(value,api)
    if chosen is None:return {'state':'WAIT_OWNER_CONTENT_ENROLLMENT','production_changes':0}
    key,request,snapshot=chosen
    if previous and previous['key']==key:
        need(sha(builder.private_bytes(builder.REQUEST))==previous['request_sha256'],'BUILDER_DUPLICATE_REQUEST_DRIFT')
        return {**previous,'duplicate_build_skipped':True}
    if builder.REQUEST.exists():
        need(previous is not None and sha(builder.private_bytes(builder.REQUEST))==previous['request_sha256'],'FOREIGN_BUILDER_REQUEST')
    record={'state':'PREPARING','key':key,'trust_sha256':sha(snapshot),'production_changes':0}
    store(state_path,record)
    try:
        store(builder.REQUEST,request)
        request_raw=builder.private_bytes(builder.REQUEST);record['request_sha256']=sha(request_raw);store(state_path,record)
        need(builder.private_bytes(trust.TRUST)==snapshot,'BUILDER_PRESTART_TRUST_DRIFT')
        result=command(['/usr/bin/systemctl','start',UNIT],capture_output=True,timeout=250)
        need(result.returncode==0,'BUILDER_UNIT_FAILED_NO_RETRY')
        stage=builder.BASE/('build-'+record['request_sha256'])
        receipt=json.loads(builder.private_bytes(stage/'BUILD_RECEIPT.json'))
        raw=builder.private_bytes(stage/'SHOWCASE_RELEASE.tar.gz')
        need(receipt['runtime']['effective'] is True and receipt['runtime']['mount_namespace']!=os.readlink('/proc/self/ns/mnt'),'BUILDER_RUNTIME_ISOLATION')
        need(not (stage/'BUILD_HOLD.json').exists() and receipt['request_sha256']==record['request_sha256'] and receipt['trust_snapshot_sha256']==record['trust_sha256'] and receipt['tar_sha256']==sha(raw),'BUILDER_OUTPUT_BINDING')
        need(builder.private_bytes(trust.TRUST)==snapshot and builder.private_bytes(builder.REQUEST)==request_raw,'BUILDER_POSTSTART_DRIFT')
        record.update(state='BUILT',stage_name=stage.name,tar_sha256=sha(raw),receipt_sha256=sha(canonical(receipt)))
        store(state_path,record);return record
    except BaseException:
        record.update(state='HOLD',retry_allowed=False);store(state_path,record);raise


def export(value,api=builder.fetch):
    state_path=builder.BASE/'CHANNEL_STATE.json';record=json.loads(builder.private_bytes(state_path))
    need(record['state'] in ('BUILT','EXPORTED'),'BUILDER_EXPORT_NOT_READY')
    chosen=selection(value,api);need(chosen is not None and chosen[0]==record['key'],'BUILDER_EXPORT_REVIEW_DRIFT')
    need(re.fullmatch('build-[0-9a-f]{64}',record['stage_name']),'BUILDER_EXPORT_PATH')
    stage=builder.BASE/record['stage_name'];need(not (stage/'BUILD_HOLD.json').exists(),'BUILDER_EXPORT_HOLD')
    raw=builder.private_bytes(stage/'SHOWCASE_RELEASE.tar.gz')
    receipt=json.loads(builder.private_bytes(stage/'BUILD_RECEIPT.json'))
    need(sha(raw)==record['tar_sha256'] and sha(canonical(receipt))==record['receipt_sha256'],'BUILDER_EXPORT_HASH')
    need(sha(builder.private_bytes(trust.TRUST))==record['trust_sha256'],'BUILDER_EXPORT_TRUST_DRIFT')
    record['state']='EXPORTED';store(state_path,record)
    return {'tar_base64':base64.b64encode(raw).decode('ascii'),'receipt':receipt}


def main():
    need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','BUILDER_CHANNEL_HOST_ROOT')
    need(len(sys.argv)==2 and sys.argv[1] in ('inspect','build','export'),'BUILDER_CHANNEL_FIXED_ACTION')
    value=policy();builder.verified_code(value['mechanism_manifest_sha256'])
    for p in (builder.BASE,*builder.BASE.parents):
        s=p.lstat();need(s.st_uid==0 and p.is_dir() and not p.is_symlink() and not s.st_mode&0o022,'BUILDER_CHANNEL_BASE')
    need(builder.BASE.stat().st_mode&0o777==0o700,'BUILDER_CHANNEL_BASE_MODE')
    if sys.argv[1]=='inspect':
        path=builder.BASE/'CHANNEL_STATE.json'
        print(json.dumps({'state':'INSPECTED','channel_state':json.loads(builder.private_bytes(path))['state'] if path.exists() else 'NOT_RUN','production_changes':0}));return
    from scripts.pr122_showcase_promote import load_engine
    engine=load_engine()
    # Same outer lock used by install/rollback, so a build cannot restart while
    # the channel is being withdrawn. The inner lock deduplicates build/export.
    with engine.open_trusted_file(Path('/var/lib/xuanjun-pr122-site-hub/transaction.lock'),0) as (outer,_):
        fcntl.flock(outer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return locked_action(sys.argv[1],value)

def locked_action(action,value):
    lock=builder.BASE/'channel.lock'
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and s.st_mode&0o777==0o600,'BUILDER_CHANNEL_LOCK')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=execute(value) if action=='build' else export(value)
        print(json.dumps(result,sort_keys=True))
    finally:os.close(fd)

if __name__=='__main__':main()
