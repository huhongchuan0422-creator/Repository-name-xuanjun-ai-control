"""Owner-only fixed-channel rebinding transaction. Stdlib only, no customer install.
No sudo capability is added. Source author cannot enroll the root-private anchor.
All old objects/evidence are preserved. Unknown states prohibit apply retry.
"""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import time
import urllib.request
import zipfile

BASE=Path('/var/lib/xuanjun-customer-channel')
INPUT=Path('/root/pr122-customer-channel-upgrade-inputs/REVIEW_ARTIFACT.zip')
EXEC=Path('/usr/local/libexec/xuanjun-customer-channel')
POLICY=Path('/etc/sudoers.d/xuanjun-customer-channel')
TRUST=BASE/'UPGRADE_TRUST.json'
TXN='pr122-customer-preview-channel-20261017'
CONTROL=BASE/'upgrades'/TXN
HOST='iZvt5t8tlrm8oiZ'
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
OLD_CODE='0804e33edac6ad07a711456c0c15708266b2ad8a75c4cb3bdc5964a9b79a96bd'
OLD_TAR='7dd77ef573c338201ddc886b23585422ad4a07ae563a9c6ff92fe5b2f9d97b98'
ARCHIVE='PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz'
FROZEN_ZIP='a662b76d6c3fb010e0944dea157ff898040007cd69124d498bec26c7701138d3'
IDENTITY_ADDITIONS=frozenset({'scripts/pr122_customer_identity.py',
    'tests/test_pr122_customer_identity.py',
    'docs/development/PR122_CUSTOMER_CENTER_IDENTITY_CONTRACT_V1.md'})
IDENTITY_BASE_PATHS_SHA256='88200b5319005bc1e56a20c37f1ba822c8520a81dc2f3c64b4f26b5bfc225a6a'
HOST_INTEGRATION_ADDITIONS=frozenset(["clients/saas-console/build_ecosystem_assets.py","clients/saas-console/package.json","clients/saas-console/src/api.js","clients/saas-console/src/ecosystem-bootstrap.mjs","clients/saas-console/src/ecosystem-view.mjs","deploy/pr122-customer-center/ui/ecosystem/api.mjs","deploy/pr122-customer-center/ui/ecosystem/bootstrap.mjs","deploy/pr122-customer-center/ui/ecosystem/ecosystem-view.mjs","deploy/pr122-customer-center/ui/ecosystem/index.html","deploy/pr122-customer-center/ui/ecosystem/style.css","deploy/pr122-customer-center/ui/twin/bootstrap.mjs","deploy/pr122-customer-center/ui/twin/index.html","deploy/pr122-customer-center/ui/twin/style.css","scripts/community_saas_modules.py","scripts/community_saas_offer_catalog.py","scripts/community_saas_schema_guard.py","scripts/pr122_customer_twin.py","scripts/saas_ecosystem_adapter.py","scripts/saas_ecosystem_http.py","scripts/saas_module_package_gate.py","scripts/saas_pending_packages.py","tests/test_pr122_customer_extension_hosts.py"])
HOST_INTEGRATION_BASE_PATHS_SHA256='36fad3b6e5fbcc286f56ba61c5d86d979565aaadf550b41c61f4c4c63073f88c'

def need(ok,msg):
    if not ok:raise RuntimeError('HOLD:'+msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def secure(path,directory=False):
    path=Path(path);need(path.is_absolute(),'ABSOLUTE_PATH')
    for p in reversed((path,*path.parents)):
        s=p.lstat();need(s.st_uid==0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode&0o022,'ROOT_PRIVATE_PATH')
        if p!=path or directory:need(stat.S_ISDIR(s.st_mode),'DIRECTORY')
        else:need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=25000000,'REGULAR_BOUNDED_FILE')
    return path

def read(path):
    secure(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno());raw=f.read(25000001);after=os.fstat(f.fileno())
    need((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns) and len(raw)<=25000000,'INPUT_DRIFT')
    return raw

def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def create(path,raw,mode):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:os.fchmod(f.fileno(),mode);f.write(raw);f.flush();os.fsync(f.fileno())
    sync(path.parent)
def replace(path,raw,mode):
    import secrets
    pending=path.parent/('.'+path.name+'.'+secrets.token_hex(8));create(pending,raw,mode);os.replace(pending,path);sync(path.parent)
def move(a,b):
    need(not os.path.lexists(b),'DESTINATION_EXISTS');os.rename(a,b);sync(a.parent);sync(b.parent)
def receipt(value):replace(CONTROL/'receipt.json',canonical(value),0o600)
def owner():need(os.geteuid()==0 and os.uname().nodename==HOST and os.environ.get('SUDO_UID')!='1002','OWNER_HOST_REQUIRED')

def unpack(raw):
    need(len(raw)<=10000000,'TAR_SIZE');out={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:
        members=t.getmembers();need(1<len(members)<=125,'TAR_COUNT')
        for m in members:
            need(m.isfile() and m.name.startswith('customer-center/') and '..' not in Path(m.name).parts and m.name not in out and m.size<=8000000,'TAR_PATH_TYPE')
            out[m.name]=t.extractfile(m).read()
        paths={name.removeprefix('customer-center/') for name in out}
        if len(members)<=100 and not (paths & IDENTITY_ADDITIONS) and not (paths & HOST_INTEGRATION_ADDITIONS):pass
        elif len(members)==103 and IDENTITY_ADDITIONS <= paths and not (paths & HOST_INTEGRATION_ADDITIONS):
            baseline=paths-IDENTITY_ADDITIONS-{'CUSTOMER_MANIFEST.json'}
            need(len(baseline)==99 and sha(canonical(sorted(baseline)))==IDENTITY_BASE_PATHS_SHA256,'IDENTITY_CANDIDATE_BASE_PATHS')
        elif len(members)==125 and HOST_INTEGRATION_ADDITIONS <= paths and 'CUSTOMER_MANIFEST.json' in paths:
            baseline=paths-HOST_INTEGRATION_ADDITIONS-{'CUSTOMER_MANIFEST.json'}
            need(len(baseline)==102 and sha(canonical(sorted(baseline)))==HOST_INTEGRATION_BASE_PATHS_SHA256,'HOST_INTEGRATION_BASE_PATHS')
        else:need(False,'CANDIDATE_EXACT_SHAPE')
    raw_manifest=out.pop('customer-center/CUSTOMER_MANIFEST.json');manifest=json.loads(raw_manifest)
    files={x['path']:out.get('customer-center/'+x['path']) for x in manifest['files']}
    need(len(files)==len(manifest['files']) and len(files)==len(out),'MANIFEST_SET')
    for x in manifest['files']:need(files[x['path']] is not None and len(files[x['path']])==x['size'] and sha(files[x['path']])==x['sha256'],'MANIFEST_HASH')
    files['CUSTOMER_MANIFEST.json']=raw_manifest
    return files,manifest,sha(raw_manifest)

def snapshot(folder):
    secure(folder,directory=True);out={}
    for root,dirs,names in os.walk(folder,followlinks=False):
        for name in dirs:secure(Path(root)/name,directory=True)
        for name in names:
            p=Path(root)/name;out[p.relative_to(folder).as_posix()]={'sha256':sha(read(p)),'mode':stat.S_IMODE(p.stat().st_mode)}
    return out

def bundle(expected_zip_sha256=None):
    pin=FROZEN_ZIP if expected_zip_sha256 is None else expected_zip_sha256
    need(type(pin) is str and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'ZIP_PIN_REQUIRED')
    raw=read(INPUT);need(sha(raw)==pin,'FROZEN_ZIP_IDENTITY')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();need(len(names)==len(set(names)) and len(names)<1000,'ZIP_SET')
        need(all(not n.startswith('/') and '..' not in Path(n).parts and i.file_size<=15000000 for n,i in zip(names,z.infolist())) and sum(i.file_size for i in z.infolist())<=80000000,'ZIP_LIMIT')
        archive=z.read(ARCHIVE);code=z.read('rebind-candidate/channel.py');binding=json.loads(z.read('rebind-candidate/REBIND_BINDING.json'))
    files,manifest,msha=unpack(archive)
    need(binding['state']=='REBIND_CANDIDATE_ONLY' and binding['original_channel_sha256']==OLD_CODE and binding['tar_sha256']==sha(archive) and binding['manifest_sha256']==msha and binding['channel_sha256']==sha(code) and binding['source_commit']==manifest['source_commit'] and binding['source_tree']==manifest['source_tree'],'BINDING_IDENTITY')
    need(binding['archive_members']==len(files) and binding['bound_files']==len(files)-1 and binding['actions']==['inspect','plan','apply','rollback'] and binding['sudoers_changed'] is False and binding['vendor_file_count']==160,'FIXED_SCOPE')
    compile(code,'reviewed-channel','exec') # compile only; never import candidate.
    return {'zip_sha256':sha(raw),'binding':binding},files,archive,code

def expected_wrapper():return ('#!/bin/sh\nset -eu\n[ "$#" -eq 1 ] || exit 2\nexec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C SUDO_UID="${SUDO_UID-}" /usr/bin/python3 -I -B '+str(BASE/'channel.py')+' "$1"\n').encode()
def expected_policy():return ('githubrunner ALL=(root) NOPASSWD: '+', '.join(str(EXEC)+' '+x for x in ('inspect','plan','apply','rollback'))+'\n').encode()
def plan(ignore_transaction=False,expected_zip_sha256=None):
    owner();need(ignore_transaction or not os.path.lexists(CONTROL),'TRANSACTION_EXISTS_DO_NOT_RETRY')
    need(json.loads(read(BASE/'grant-state.json'))=={'state':'GRANTED'},'ORIGINAL_GRANTED_REQUIRED')
    need(sha(read(BASE/'channel.py'))==OLD_CODE and sha(read(BASE/ARCHIVE))==OLD_TAR,'ORIGINAL_CHANNEL_BASELINE')
    for path,mode in ((BASE/'channel.py',0o444),(BASE/ARCHIVE,0o400),(BASE/'grant-state.json',0o600),(EXEC,0o755),(POLICY,0o440)):need(stat.S_IMODE(path.stat().st_mode)==mode,'ORIGINAL_MODE_DRIFT')
    old,_,_=unpack(read(BASE/ARCHIVE));actual=snapshot(BASE/'candidate')
    need(set(actual)==set(old) and all(actual[p]['sha256']==sha(b) and actual[p]['mode']==0o400 for p,b in old.items()),'OLD_CANDIDATE_DRIFT')
    need(read(EXEC)==expected_wrapper() and read(POLICY)==expected_policy(),'UNCHANGED_FIXED_POLICY')
    new,_,_,_=bundle(expected_zip_sha256)
    return {'transaction':TXN,'new':new,'old':{'files':actual,'code_sha256':OLD_CODE,'tar_sha256':OLD_TAR,'wrapper_sha256':sha(read(EXEC)),'policy_sha256':sha(read(POLICY)),'grant_sha256':sha(read(BASE/'grant-state.json'))},'production_service_changes':0,'customer_install':'NOT_CALLED'}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('HOLD:APPROVAL_REDIRECT')
def fetch(comment):
    request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/issues/comments/'+str(comment),headers={'Accept':'application/vnd.github+json','User-Agent':'PR122-Owner-Channel-Rebind'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=20) as r:
        raw=r.read(2000001);need(len(raw)<=2000000,'APPROVAL_SIZE');return json.loads(raw)
def gate(p,get=fetch):
    t=json.loads(read(TRUST));need(stat.S_IMODE(TRUST.stat().st_mode)==0o600,'OWNER_TRUST_MODE')
    need(set(t)=={'source_writer_principal','reviewer_principal','custody_evidence_sha256','comment_id','body_sha256'} and all(type(t[k]) is str and bool(t[k]) for k in ('source_writer_principal','reviewer_principal')) and t['source_writer_principal']!=t['reviewer_principal'],'INDEPENDENT_OWNER_ANCHOR')
    import re
    need(all(type(t[k]) is str and re.fullmatch('[0-9a-f]{64}',t[k]) for k in ('custody_evidence_sha256','body_sha256')) and type(t['comment_id']) is int,'OWNER_CUSTODY_ANCHOR')
    c=get(t['comment_id']);need(c['id']==t['comment_id'] and c['user']['login']=='huhongchuan0422-creator' and c['issue_url']=='https://api.github.com/repos/'+REPO+'/issues/122' and sha(c['body'].encode())==t['body_sha256'],'EXACT_APPROVAL_COMMENT')
    need(c['body'].startswith('XUANJUN_CUSTOMER_CHANNEL_REBIND\n'),'APPROVAL_PURPOSE');a=json.loads(c['body'].split('\n',1)[1])
    need(a['decision']=='REBIND_APPROVED' and a['transaction']==TXN and a['plan_sha256']==sha(canonical(p)) and a['new']==p['new'] and a['upgrade_script_sha256']==sha(read(Path(__file__).absolute())) and a['max_executions']==1 and a['rollback_approved'] is True,'EXACT_APPROVAL_BINDING')
    need(type(a['issued_unix']) is int and type(a['expires_unix']) is int and a['issued_unix']<=time.time()<a['expires_unix'] and 0<a['expires_unix']-a['issued_unix']<=7200,'APPROVAL_EXPIRED')
    return {'id':c['id'],'body_sha256':t['body_sha256'],'expires_unix':a['expires_unix'],'rollback_approved':True,'trust_sha256':sha(read(TRUST))}

def tree_write(folder,files):
    folder.mkdir(mode=0o700)
    for name,raw in files.items():create(folder/name,raw,0o400)
    sync(folder)
from contextlib import contextmanager
@contextmanager
def owner_lock(create_allowed=False):
    owner();path=BASE/'.upgrade-lock'
    if not os.path.lexists(path):
        need(create_allowed,'UPGRADE_LOCK_REQUIRED')
        try:create(path,b'',0o600)
        except FileExistsError:pass
    secure(path)
    with path.open('rb') as held,secure(BASE/'channel.py').open('rb') as channel:
        fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(channel,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield

# Durable event records are append-only. Receipt is a derived latest view.
# No forward retry. Interrupted rollback requires fresh recovery authorization.
def event(r, phase, status):
    r['phase']=phase; r['step_status']=status
    folder=CONTROL/'events';folder.mkdir(mode=0o700,exist_ok=True);sync(CONTROL)
    entries=list(folder.iterdir())
    need(all(p.name.endswith('.json') for p in entries),'EVENT_DIRECTORY_DRIFT')
    seq=len(entries)+1
    create(folder/('%06d.json'%seq),canonical(r),0o400)
    receipt(r)

def step(r,phase,action,checkpoint):
    event(r,phase,'INTENT');checkpoint(phase+':INTENT')
    action();checkpoint(phase+':MUTATED')
    event(r,phase,'DONE');checkpoint(phase)

def contain(r):
    # Attempt the fence independently of journal/receipt health. Never mask errors.
    if r.get('activation_started'):
        try:replace(BASE/'grant-state.json',b'{"state":"HOLD_UPGRADE"}',0o600)
        except BaseException:pass
    r['state']='HOLD_PARTIAL'
    try:event(r,r.get('phase','PREPARING'),'UNKNOWN')
    except BaseException:pass

def verify_policy(p):
    need(sha(read(EXEC))==p['old']['wrapper_sha256'] and
         sha(read(POLICY))==p['old']['policy_sha256'],'UNRELATED_POLICY_DRIFT')

def verify_old(p,grant=True):
    verify_policy(p)
    need(snapshot(BASE/'candidate')==p['old']['files'] and
         sha(read(BASE/'channel.py'))==p['old']['code_sha256'] and
         sha(read(BASE/ARCHIVE))==p['old']['tar_sha256'],'OLD_OBJECT_VERIFY')
    if grant:need(sha(read(BASE/'grant-state.json'))==p['old']['grant_sha256'],'OLD_GRANT_VERIFY')

def backup_verify(p):
    previous=CONTROL/'previous'
    need(snapshot(previous/'candidate')==p['old']['files'] and
         sha(read(previous/'channel.py'))==p['old']['code_sha256'] and
         sha(read(previous/ARCHIVE))==p['old']['tar_sha256'] and
         sha(read(previous/'grant-state.json'))==p['old']['grant_sha256'],'BACKUP_VERIFY')

def _workflow_authority(lease,p):
    from scripts.pr122_customer_workflow import POLICY as WORKFLOW_POLICY
    lease.assert_active();lease.authority();lease.verify_inputs('CHANNEL_REBIND')
    need(lease.approval.get('attempt_policy')==WORKFLOW_POLICY,'WHOLE_WORKFLOW_PERMISSION_REQUIRED')
    inputs=lease.ops.input('CHANNEL_REBIND')
    need(type(inputs) is dict and set(inputs)=={'plan_sha256','zip_sha256'}
         and inputs['plan_sha256']==sha(canonical(p)) and inputs['zip_sha256']==p['new']['zip_sha256']
         and inputs['zip_sha256']==lease.approval.get('artifact_zip_sha256')
         and p['new']['binding']['source_commit']==lease.plan['source_commit']
         and p['new']['binding']['manifest_sha256']==lease.plan['manifest_sha256'],
         'WORKFLOW_CHANNEL_EXACT_INPUTS')
    need(sha(read(Path(__file__).absolute()))==lease.stage_contract('CHANNEL_REBIND')['implementation_sha256'],
         'WORKFLOW_CHANNEL_IMPLEMENTATION')
    # This grants only the fixed forward rebind stage. It cannot be used by the
    # old rollback/recovery CLI as a new rollback permission.
    return {'workflow_policy':WORKFLOW_POLICY,'workflow_approval_sha256':sha(canonical(lease.approval)),
            'expires_unix':lease.approval['expires_unix'],'rollback_approved':False}


def apply_for_workflow(lease,checkpoint=lambda stage:None):
    return apply(checkpoint=checkpoint,workflow_lease=lease)


def apply(get=fetch,checkpoint=lambda stage:None,workflow_lease=None):
    owner()
    pin=None
    if workflow_lease is not None:
        workflow_lease.assert_active();workflow_lease.authority();workflow_lease.verify_inputs('CHANNEL_REBIND')
        pin=workflow_lease.ops.input('CHANNEL_REBIND')['zip_sha256']
    read_plan=(lambda ignore=False:plan(ignore_transaction=ignore,expected_zip_sha256=pin)) if workflow_lease is not None else (lambda ignore=False:plan(ignore_transaction=ignore))
    p=read_plan()
    authorize=(lambda value:_workflow_authority(workflow_lease,value)) if workflow_lease is not None else (lambda value:gate(value,get))
    approved=authorize(p)
    original_checkpoint=checkpoint
    def checkpoint(stage):
        if workflow_lease is not None:
            workflow_lease.assert_active();workflow_lease.authority()
        original_checkpoint(stage)
        if workflow_lease is not None:
            workflow_lease.assert_active();workflow_lease.authority()
    def perform(r,phase,action,callback):
        if workflow_lease is not None:
            workflow_lease.assert_active();workflow_lease.authority()
        return step(r,phase,action,callback)
    with owner_lock(create_allowed=True):
        # Recheck all inputs and approval while holding both exclusion locks.
        need(read_plan()==p and authorize(p)==approved,'UNDER_LOCK_DRIFT')
        new,files,archive,code=bundle(pin);need(new==p['new'],'STAGING_DRIFT')
        if workflow_lease is not None:
            workflow_lease.assert_active();workflow_lease.authority()
        CONTROL.parent.mkdir(mode=0o700,exist_ok=True);secure(CONTROL.parent,directory=True)
        # Exclusive persistent directory consumes this transaction even if setup fails.
        CONTROL.mkdir(mode=0o700)
        r={'state':'PREPARING','plan':p,'approval':approved,'activation_started':False}
        try:
            sync(CONTROL.parent)
            create(CONTROL/'plan.json',canonical(p),0o400)
            create(CONTROL/'approval.json',canonical(approved),0o400)
            event(r,'PREPARING','DONE');checkpoint('PREPARING')
            previous=CONTROL/'previous'
            def backup():
                previous.mkdir(mode=0o700);sync(CONTROL)
                for name in ('channel.py',ARCHIVE,'grant-state.json'):
                    create(previous/name,read(BASE/name),stat.S_IMODE((BASE/name).stat().st_mode))
                tree_write(previous/'candidate',{name:read(BASE/'candidate'/name) for name in p['old']['files']})
                backup_verify(p)
            perform(r,'BACKUP_VERIFIED',backup,checkpoint)
            def stage():
                tree_write(CONTROL/'new-candidate',files)
                create(CONTROL/'new-channel.py',code,0o444)
                create(CONTROL/'new.tar.gz',archive,0o400)
            perform(r,'STAGED',stage,checkpoint)
            need(read_plan(True)==p and authorize(p)==approved,'PREACTIVATION_DRIFT')
            need(time.time()<approved['expires_unix'],'APPROVAL_EXPIRED')
            r['state']='ACTIVATING';r['activation_started']=True
            perform(r,'FENCED',lambda:replace(BASE/'grant-state.json',b'{"state":"UPGRADING"}',0o600),checkpoint)
            perform(r,'OLD_MOVED',lambda:move(BASE/'candidate',CONTROL/'parked-old-candidate'),checkpoint)
            perform(r,'CANDIDATE_MOVED',lambda:move(CONTROL/'new-candidate',BASE/'candidate'),checkpoint)
            perform(r,'CODE_REPLACED',lambda:replace(BASE/'channel.py',code,0o444),checkpoint)
            perform(r,'TAR_REPLACED',lambda:replace(BASE/ARCHIVE,archive,0o400),checkpoint)
            need(snapshot(BASE/'candidate')=={n:{'sha256':sha(b),'mode':0o400} for n,b in files.items()} and
                 sha(read(BASE/'channel.py'))==new['binding']['channel_sha256'] and
                 sha(read(BASE/ARCHIVE))==new['binding']['tar_sha256'],'NEW_OBJECTS_VERIFY')
            verify_policy(p);backup_verify(p)
            perform(r,'GRANTED',lambda:replace(BASE/'grant-state.json',b'{"state":"GRANTED"}',0o600),checkpoint)
            r['state']='BOUND';event(r,'BOUND','DONE');checkpoint('BOUND')
            return {'state':'BOUND','receipt':str(CONTROL/'receipt.json'),'customer_install':'NOT_CALLED','sudoers_changed':False}
        except BaseException:
            if workflow_lease is not None:workflow_lease.assert_active()
            contain(r);raise

def load_transaction():
    # A damaged/partial journal is UNKNOWN, never inferred safe or silently rebuilt.
    p=json.loads(read(CONTROL/'plan.json'));a=json.loads(read(CONTROL/'approval.json'))
    files=sorted((CONTROL/'events').iterdir())
    need(files and [x.name for x in files]==['%06d.json'%i for i in range(1,len(files)+1)],'EVENT_SEQUENCE')
    states=[json.loads(read(x)) for x in files]
    need(all(x['plan']==p and x['approval']==a for x in states),'EVENT_BINDING')
    r=states[-1]
    # Receipt may lag an fsynced event; events are authoritative, not wall clock.
    need(p['transaction']==TXN and a['rollback_approved'] is True,'TRANSACTION_BINDING')
    return r

def recovery_gate(r,get=fetch):
    # Fresh independently anchored decision, bound to the exact interrupted bytes.
    t=json.loads(read(TRUST));need(stat.S_IMODE(TRUST.stat().st_mode)==0o600,'OWNER_TRUST_MODE')
    need(set(t)=={'source_writer_principal','reviewer_principal','custody_evidence_sha256','comment_id','body_sha256'} and
         all(type(t[k]) is str and bool(t[k]) for k in ('source_writer_principal','reviewer_principal')) and
         type(t['comment_id']) is int and t['source_writer_principal']!=t['reviewer_principal'] and
         all(type(t[k]) is str and len(t[k])==64 and all(c in '0123456789abcdef' for c in t[k]) for k in ('custody_evidence_sha256','body_sha256')),'RECOVERY_CUSTODY')
    c=get(t['comment_id']);need(c['id']==t['comment_id'] and c['user']['login']=='huhongchuan0422-creator' and c['issue_url']=='https://api.github.com/repos/'+REPO+'/issues/122' and sha(c['body'].encode())==t['body_sha256'],'RECOVERY_COMMENT')
    need(c['body'].startswith('XUANJUN_CUSTOMER_CHANNEL_RECOVERY\n'),'RECOVERY_PURPOSE')
    a=json.loads(c['body'].split('\n',1)[1]);now=time.time()
    need(a['decision']=='RECOVERY_APPROVED' and a['transaction']==TXN and
         a['event_sha256']==sha(canonical(r)) and a['plan_sha256']==sha(canonical(r['plan'])) and
         a['upgrade_script_sha256']==sha(read(Path(__file__).absolute())) and
         a['max_executions']==1 and type(a['issued_unix']) is int and type(a['expires_unix']) is int and
         a['issued_unix']<=now<a['expires_unix'] and 0<a['expires_unix']-a['issued_unix']<=7200 and
         c['id']!=r['approval']['id'],'RECOVERY_SCOPE')
    use=CONTROL/('recovery-%s.json'%c['id'])
    create(use,canonical({'comment_id':c['id'],'body_sha256':t['body_sha256'],'event_sha256':a['event_sha256']}),0o400)
    return {'id':c['id'],'body_sha256':t['body_sha256']}

def rollback_impl(checkpoint=lambda stage:None,recover=False,get=fetch):
    owner();r=load_transaction();p=r['plan']
    need(r['state']!='ROLLED_BACK','ALREADY_ROLLED_BACK')
    started=os.path.lexists(CONTROL/'rollback-started.json')
    need(not started or recover,'FRESH_RECOVERY_APPROVAL_REQUIRED')
    need(not recover or started,'NO_INTERRUPTED_ROLLBACK')
    if recover:r['recovery']=recovery_gate(r,get)
    else:create(CONTROL/'rollback-started.json',canonical({'plan_sha256':sha(canonical(p)),'approval':r['approval']}),0o400)
    try:
        r['state']='ROLLING_BACK'
        if not r.get('activation_started'):
            verify_old(p)
            r['state']='ROLLED_BACK';r['rollback_verified']={'unmodified_old_channel':True,'customer_install_called':False}
            event(r,'ROLLED_BACK','DONE');return {'state':'ROLLED_BACK','verification':r['rollback_verified']}
        backup_verify(p);verify_policy(p)
        previous=CONTROL/'previous';new=p['new']['binding']
        need(sha(read(BASE/'channel.py')) in (p['old']['code_sha256'],new['channel_sha256']) and
             sha(read(BASE/ARCHIVE)) in (p['old']['tar_sha256'],new['tar_sha256']),'CURRENT_OBJECT_DRIFT')
        need(sha(read(CONTROL/'new.tar.gz'))==new['tar_sha256'],'STAGED_ARCHIVE_DRIFT')
        new_files,_,_=unpack(read(CONTROL/'new.tar.gz'))
        expected_new={n:{'sha256':sha(b),'mode':0o400} for n,b in new_files.items()}
        candidate=BASE/'candidate';parked=CONTROL/'parked-rollback-candidate';restored=CONTROL/'restored-candidate'
        if os.path.lexists(candidate):need(snapshot(candidate) in (p['old']['files'],expected_new),'CURRENT_CANDIDATE_DRIFT')
        if os.path.lexists(parked):need(snapshot(parked) in (p['old']['files'],expected_new),'PARKED_CANDIDATE_DRIFT')
        need(json.loads(read(BASE/'grant-state.json')).get('state') in ('GRANTED','UPGRADING','HOLD_UPGRADE'),'CURRENT_GRANT_DRIFT')
        step(r,'RB_FENCED',lambda:replace(BASE/'grant-state.json',b'{"state":"HOLD_UPGRADE"}',0o600),checkpoint)
        def prepare_restore():
            if not os.path.lexists(restored):restored.mkdir(mode=0o700);sync(CONTROL)
            actual=snapshot(restored)
            need(set(actual)<=set(p['old']['files']) and all(actual[n]==p['old']['files'][n] for n in actual),'RESTORE_PARTIAL_DRIFT')
            for n in p['old']['files']:
                if n not in actual:create(restored/n,read(previous/'candidate'/n),0o400)
            need(snapshot(restored)==p['old']['files'],'RESTORED_CANDIDATE_VERIFY')
        # A completed restore move need not be repeated; identity determines the action.
        old_in_place=os.path.lexists(candidate) and snapshot(candidate)==p['old']['files']
        if not old_in_place:
            step(r,'RB_PREPARED',prepare_restore,checkpoint)
            def park():
                if os.path.lexists(candidate):
                    need(not os.path.lexists(parked),'PARK_DESTINATION_DRIFT');move(candidate,parked)
            step(r,'RB_PARKED',park,checkpoint)
            step(r,'RB_CANDIDATE',lambda:move(restored,candidate),checkpoint)
        step(r,'RB_CODE',lambda:replace(BASE/'channel.py',read(previous/'channel.py'),0o444),checkpoint)
        step(r,'RB_TAR',lambda:replace(BASE/ARCHIVE,read(previous/ARCHIVE),0o400),checkpoint)
        verify_old(p,grant=False);backup_verify(p)
        step(r,'RB_GRANTED',lambda:replace(BASE/'grant-state.json',read(previous/'grant-state.json'),0o600),checkpoint)
        verify_old(p)
        r['state']='ROLLED_BACK';r['rollback_verified']={'old_code':True,'old_tar':True,'old_candidate':True,'fixed_policy_unchanged':True,'customer_install_called':False}
        event(r,'ROLLED_BACK','DONE');checkpoint('ROLLED_BACK')
        return {'state':'ROLLED_BACK','verification':r['rollback_verified']}
    except BaseException:
        contain(r);raise

def rollback(checkpoint=lambda stage:None,recover=False,get=fetch):
    with owner_lock():return rollback_impl(checkpoint,recover,get)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('plan','apply','rollback','recover-rollback'));a=ap.parse_args();os.umask(0o077)
    result=plan() if a.action=='plan' else apply() if a.action=='apply' else rollback(recover=a.action=='recover-rollback')
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':
    try:main()
    except BaseException:print('{"state":"HOLD","retry_allowed":false,"raw_error_redacted":true}');raise SystemExit(2) from None

