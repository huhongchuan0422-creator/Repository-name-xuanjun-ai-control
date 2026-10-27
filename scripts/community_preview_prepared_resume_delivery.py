"""Exact existing-PREPARED carrier update and continuation entry for Issue76.

This is not a first installer and never creates a C attempt.  It accepts only the
already durable community-update-f131... PREPARED sequence-1 transaction, swaps
the reviewed carrier atomically, and then exposes inspect/resume/query/recover.
"""
import argparse
import ctypes
import errno
import fcntl
import hashlib
import io
import json
import os
import pwd
import re
import socket
import stat
import sys
import zipfile

HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/opt/xuanjun-community-preview'
CONTROL=BASE+'/control-stopped-v1'
JOURNAL=BASE+'/update-journal'
ATTEMPT='community-update-f13155ed63a3-818fe0b0622c-stopped-v1'
PLAN='f5466ce54309e7799f89fe1181d15962e681dfe936e6e574bfe5192f2b4333d6'
PROOF=BASE+'/backup-2330-to-f131-v1/stopped-handoff-v1.json'
ACTIVE=JOURNAL+'/active-attempt.json'
CHECKPOINT=JOURNAL+'/'+ATTEMPT+'/checkpoint.json'
EVENT=JOURNAL+'/'+ATTEMPT+'/event-000001.json'
SOURCE='/home/admin/community-post-b-c-resume-source-40507335425.zip'
SOURCE_SHA='b939a7c1010b0b9ae8f8eaa5916b91bee18aed810827ed2239234f680b364b33'
INNER='post-b-c-resume-delivery/control-stopped-v1.zip'
INNER_SHA='7d513919031cb30bf752fccacc30f2c8bbf21fa5b4a067eb30587c5615fc9bf3'
MANIFEST_MEMBER='post-b-c-resume-delivery/manifest.json'
OLD_MANIFEST='e48e439e766b6c0b0b57147bbb9e9f4ffac203dc322a5ae599ecdcc8bd87ff8a'
NEW_MANIFEST='fcdeb39aae034f0b7bea312067306171a174021311ebea610c3fa957a1c7cc17'
LOADER_SHA='da5889402610289578409f1863675a10fc5030f42d73fd2719383ad6203fe766'
PROOF_SHA='5b9a63243c7a2da70c52f64a6d6289c90fd31fc361c463c3b2a042d65f095e10'
ACTIVE_SHA='750b24fa597b5a67de8a706cbb4d5cbe1da1d356786291871fde11964fc1ca00'
PREPARED_SHA='87e03ba110bc3f4b517b826ff21c7b44c85015d7dae41af6826a7858a4e2752a'
DELIVERY=BASE+'/prepared-resume-76ca971e826f85e8'
INTENT=DELIVERY+'/update-intent.json'
RECEIPT=DELIVERY+'/update-receipt.json'
STAGE='control-stopped-v1.prepared-resume-76ca971e826f85e8.stage'
RETAINED='control-stopped-v1.prepared-resume-76ca971e826f85e8.previous'
SHA=re.compile(r'[0-9a-f]{64}\Z')

class Hold(RuntimeError):pass
def need(v,r):
    if not v:raise Hold(r)
def sha(v):return hashlib.sha256(v).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def identity(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def read(path,limit=8*1024*1024,uid=0,mode=0o600):
    before=os.lstat(path);need(stat.S_ISREG(before.st_mode) and before.st_uid==uid and stat.S_IMODE(before.st_mode)==mode and before.st_nlink==1 and 0<before.st_size<=limit,'PROTECTED_FILE_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        opened=os.fstat(fd);need(identity(before)==identity(opened),'FILE_CHANGED_ON_OPEN')
        out=[];left=opened.st_size
        while left:
            part=os.read(fd,min(65536,left));need(part,'SHORT_READ');out.append(part);left-=len(part)
        need(identity(opened)==identity(os.fstat(fd))==identity(os.lstat(path)),'FILE_CHANGED_DURING_READ')
        return b''.join(out)
    finally:os.close(fd)

def exact_json(raw):
    try:v=json.loads(raw.decode('ascii'))
    except (ValueError,UnicodeError):raise Hold('EXACT_JSON_REQUIRED') from None
    need(raw==canonical(v),'CANONICAL_JSON_REQUIRED');return v

def write_exclusive(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        os.fchown(fd,0,0);os.fchmod(fd,0o600);view=memoryview(raw)
        while view:
            n=os.write(fd,view);need(n>0,'WRITE_FAILED');view=view[n:]
        os.fsync(fd)
    finally:os.close(fd)

def mkdir_private(path):
    os.mkdir(path,0o700);fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fchown(fd,0,0);os.fchmod(fd,0o700);os.fsync(fd)
    finally:os.close(fd)

def protected_dir(path):
    s=os.lstat(path);need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'PROTECTED_DIRECTORY_REQUIRED')

def snapshot_authority():
    rows={}
    for root,names in ((BASE,[n for n in os.listdir(BASE) if n.startswith('bc-c-resume-approval')]),
                       (BASE+'/backup-2330-to-f131-v1',[n for n in os.listdir(BASE+'/backup-2330-to-f131-v1') if n.startswith('c-preconfirmation-resume-plan') or n=='stopped-handoff-v1.json']),
                       (JOURNAL,[n for n in os.listdir(JOURNAL) if n=='active-attempt.json'])):
        for name in sorted(names):
            path=root+'/'+name;rows[path]=sha(read(path,4*1024*1024))
    for path in (CHECKPOINT,EVENT):rows[path]=sha(read(path,16384))
    return rows

def state():
    proof=read(PROOF,16384);active=read(ACTIVE,16384);checkpoint=read(CHECKPOINT,16384);event=read(EVENT,16384)
    need(sha(proof)==PROOF_SHA and sha(active)==ACTIVE_SHA and sha(checkpoint)==PREPARED_SHA and checkpoint==event,'EXACT_PREPARED_BYTES_REQUIRED')
    value=exact_json(checkpoint)
    need(value.get('phase')=='PREPARED' and value.get('sequence')==1 and value.get('new_id') is None and value.get('plan_sha256')==PLAN,'EXACT_PREPARED_STATE_REQUIRED')
    need(exact_json(active)=={'attempt':ATTEMPT,'plan_sha256':PLAN},'EXACT_ACTIVE_ATTEMPT_REQUIRED')
    return value

def tree_manifest(root):
    raw=read(root+'/manifest.json',65536);manifest=exact_json(raw)
    need(type(manifest) is dict and manifest.get('install_root')==CONTROL and manifest.get('updates_enabled') is False and type(manifest.get('files')) is dict,'EXACT_MANIFEST_REQUIRED')
    for name,meta in manifest['files'].items():
        need(type(meta) is dict and set(meta)=={'bytes','sha256','uid','mode'} and meta['uid']==0 and meta['mode']=='0600' and SHA.fullmatch(meta['sha256']),'MANIFEST_ENTRY_REQUIRED')
        body=read(root+'/'+name,131072);need(len(body)==meta['bytes'] and sha(body)==meta['sha256'],'CARRIER_MEMBER_CHANGED')
    return sha(raw),manifest

def source():
    admin=pwd.getpwnam('admin');outer=read(SOURCE,16*1024*1024,admin.pw_uid,0o600);need(sha(outer)==SOURCE_SHA,'SOURCE_ARTIFACT_CHANGED')
    with zipfile.ZipFile(io.BytesIO(outer)) as z:
        inner=z.read(INNER);manifest=z.read(MANIFEST_MEMBER)
    need(sha(inner)==INNER_SHA and sha(manifest)==NEW_MANIFEST,'SOURCE_PIN_CHANGED')
    with zipfile.ZipFile(io.BytesIO(inner)) as z:
        names=z.namelist();need(len(names)==len(set(names)) and 'manifest.json' in names,'INNER_MEMBER_SET')
        bodies={n:z.read(n) for n in names}
    need(bodies['manifest.json']==manifest and sha(bodies['loader.py'])==LOADER_SHA,'LOADER_OR_MANIFEST_CHANGED')
    parsed=exact_json(manifest);need(set(bodies)==set(parsed['files'])|{'manifest.json'},'INNER_MANIFEST_SET')
    for name,meta in parsed['files'].items():need(len(bodies[name])==meta['bytes'] and sha(bodies[name])==meta['sha256'],'INNER_MEMBER_CHANGED')
    return parsed,bodies

def create_stage(manifest,bodies):
    root=BASE+'/'+STAGE;need(not os.path.lexists(root),'STAGE_ALREADY_EXISTS');mkdir_private(root)
    dirs=sorted({p for name in bodies for p in ['/'.join(name.split('/')[:i]) for i in range(1,len(name.split('/')))] if p},key=lambda x:(x.count('/'),x))
    for d in dirs:mkdir_private(root+'/'+d)
    for name,body in bodies.items():write_exclusive(root+'/'+name,body)
    need(tree_manifest(root)[0]==NEW_MANIFEST,'STAGE_VERIFY_FAILED')
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def exchange(left,right):
    libc=ctypes.CDLL(None,use_errno=True);fn=getattr(libc,'renameat2',None);need(fn is not None,'RENAME_EXCHANGE_REQUIRED')
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
    parent=os.open(BASE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if fn(parent,left.encode(),parent,right.encode(),2)!=0:raise Hold('RENAME_EXCHANGE_'+str(ctypes.get_errno()))
        os.fsync(parent)
    finally:os.close(parent)

def locks():
    lease=os.open(JOURNAL+'/community-update.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK);entry=os.open(BASE+'/site-prepare-v1.py',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(entry,fcntl.LOCK_EX|fcntl.LOCK_NB);return lease,entry

def inspect():
    lease,entry=locks()
    try:
        s=state();current,_=tree_manifest(CONTROL);authority=snapshot_authority()
        return {'record':'ISSUE76_PREPARED_RESUME_INSPECT','attempt':ATTEMPT,'phase':s['phase'],'sequence':s['sequence'],'new_id':s['new_id'],'current_manifest_sha256':current,'target_manifest_sha256':NEW_MANIFEST,'proof_sha256':PROOF_SHA,'active_attempt_sha256':ACTIVE_SHA,'checkpoint_sha256':PREPARED_SHA,'authority_set_sha256':sha(canonical(authority)),'update_receipt':RECEIPT,'site_executed':False}
    finally:os.close(entry);os.close(lease)

def receipt_value(authority_sha):
    return {'format':1,'record':'ISSUE76_PREPARED_RESUME_CARRIER_UPDATED','attempt':ATTEMPT,'phase':'PREPARED','sequence':1,'new_id':None,'old_manifest_sha256':OLD_MANIFEST,'new_manifest_sha256':NEW_MANIFEST,'source_artifact_sha256':SOURCE_SHA,'carrier_archive_sha256':INNER_SHA,'loader_sha256':LOADER_SHA,'authority_set_sha256':authority_sha,'retained_path':BASE+'/'+RETAINED,'B_rerun':False,'post_b_replayed':False,'C_started':False,'updated':True}

def update():
    lease,entry=locks()
    try:
        state();before=snapshot_authority();manifest,bodies=source();current,_=tree_manifest(CONTROL)
        if os.path.isfile(RECEIPT):
            receipt=exact_json(read(RECEIPT,16384));need(current==NEW_MANIFEST and receipt==receipt_value(sha(canonical(before))) and tree_manifest(BASE+'/'+RETAINED)[0]==OLD_MANIFEST,'EXISTING_RECEIPT_CONFLICT');return receipt
        need(current in (OLD_MANIFEST,NEW_MANIFEST),'UNREVIEWED_CURRENT_CARRIER')
        if current==NEW_MANIFEST:need(os.path.isfile(INTENT),'UPDATE_INTENT_REQUIRED_FOR_REOPEN')
        if not os.path.isdir(DELIVERY):mkdir_private(DELIVERY)
        intent={'format':1,'attempt':ATTEMPT,'phase':'PREPARED','sequence':1,'new_id':None,'old_manifest_sha256':OLD_MANIFEST,'new_manifest_sha256':NEW_MANIFEST,'source_artifact_sha256':SOURCE_SHA,'carrier_archive_sha256':INNER_SHA,'loader_sha256':LOADER_SHA,'authority_set_sha256':sha(canonical(before))}
        if os.path.isfile(INTENT):need(read(INTENT,16384)==canonical(intent),'UPDATE_INTENT_CONFLICT')
        else:write_exclusive(INTENT,canonical(intent))
        stage=BASE+'/'+STAGE;retained=BASE+'/'+RETAINED
        if current==NEW_MANIFEST and os.path.isdir(retained):
            need(tree_manifest(retained)[0]==OLD_MANIFEST and snapshot_authority()==before,'UPDATE_RECONCILE_UNKNOWN')
            receipt=receipt_value(sha(canonical(before)));write_exclusive(RECEIPT,canonical(receipt));return receipt
        if not os.path.exists(stage):create_stage(manifest,bodies)
        stage_sha,_=tree_manifest(stage);current,_=tree_manifest(CONTROL)
        if current==OLD_MANIFEST and stage_sha==NEW_MANIFEST:exchange('control-stopped-v1',STAGE)
        current,_=tree_manifest(CONTROL);stage_sha,_=tree_manifest(stage)
        need(current==NEW_MANIFEST and stage_sha==OLD_MANIFEST,'UPDATE_RECONCILE_UNKNOWN')
        need(not os.path.lexists(retained),'RETAINED_PATH_CONFLICT');os.rename(stage,retained);parent=os.open(BASE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(parent);os.close(parent)
        need(snapshot_authority()==before,'AUTHORITY_HISTORY_CHANGED')
        receipt=receipt_value(sha(canonical(before)))
        write_exclusive(RECEIPT,canonical(receipt));return receipt
    finally:os.close(entry);os.close(lease)

def load():
    raw=read(CONTROL+'/loader.py',131072);need(sha(raw)==LOADER_SHA,'LOADER_CHANGED')
    ns={'__name__':'fixed_stopped_loader'};exec(compile(raw,CONTROL+'/loader.py','exec'),ns);return ns['load'](NEW_MANIFEST)

def invoke(operation):
    need(os.path.isfile(RECEIPT),'UPDATE_RECEIPT_REQUIRED');state();need(tree_manifest(CONTROL)[0]==NEW_MANIFEST,'UPDATED_CARRIER_REQUIRED')
    module=load();arg={'resume':'--reopen-prepared','recover':'--recover-known-failure'}[operation]
    return module.main([arg])

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('operation',choices=('inspect','update','resume','query','recover'));a=p.parse_args(argv)
    need(os.getresuid()==(0,0,0) and socket.gethostname().split('.')[0]==HOST,'EXACT_ROOT_HOST_REQUIRED')
    if a.operation in ('inspect','query'):result=inspect()
    elif a.operation=='update':result=update()
    else:return invoke(a.operation)
    print(json.dumps(result,sort_keys=True,separators=(',',':')));return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except BaseException as e:
        reason=str(e) if type(e) is Hold and re.fullmatch(r'[A-Z0-9_]+',str(e)) else 'PREPARED_RESUME_UNKNOWN'
        print(json.dumps({'record':'ISSUE76_PREPARED_RESUME_HOLD','reason':reason,'retry_safe':False,'site_executed':False},sort_keys=True,separators=(',',':')));raise SystemExit(2)
