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
        members=t.getmembers();need(1<len(members)<=100,'TAR_COUNT')
        for m in members:
            need(m.isfile() and m.name.startswith('customer-center/') and '..' not in Path(m.name).parts and m.name not in out and m.size<=8000000,'TAR_PATH_TYPE')
            out[m.name]=t.extractfile(m).read()
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

def bundle():
    raw=read(INPUT)
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
def plan(ignore_transaction=False):
    owner();need(ignore_transaction or not os.path.lexists(CONTROL),'TRANSACTION_EXISTS_DO_NOT_RETRY')
    need(json.loads(read(BASE/'grant-state.json'))=={'state':'GRANTED'},'ORIGINAL_GRANTED_REQUIRED')
    need(sha(read(BASE/'channel.py'))==OLD_CODE and sha(read(BASE/ARCHIVE))==OLD_TAR,'ORIGINAL_CHANNEL_BASELINE')
    for path,mode in ((BASE/'channel.py',0o444),(BASE/ARCHIVE,0o400),(BASE/'grant-state.json',0o600),(EXEC,0o755),(POLICY,0o440)):need(stat.S_IMODE(path.stat().st_mode)==mode,'ORIGINAL_MODE_DRIFT')
    old,_,_=unpack(read(BASE/ARCHIVE));actual=snapshot(BASE/'candidate')
    need(set(actual)==set(old) and all(actual[p]['sha256']==sha(b) and actual[p]['mode']==0o400 for p,b in old.items()),'OLD_CANDIDATE_DRIFT')
    need(read(EXEC)==expected_wrapper() and read(POLICY)==expected_policy(),'UNCHANGED_FIXED_POLICY')
    new,_,_,_=bundle()
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
    return {'id':c['id'],'body_sha256':t['body_sha256'],'expires_unix':a['expires_unix'],'rollback_approved':True}

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

def apply(get=fetch,checkpoint=lambda stage:None):
    owner();p=plan();approval=gate(p,get)
    with owner_lock(create_allowed=True):
        new,files,archive,code=bundle();need(new==p['new'],'STAGING_DRIFT')
        CONTROL.parent.mkdir(mode=0o700,exist_ok=True);CONTROL.mkdir(mode=0o700);sync(CONTROL.parent)
        r={'state':'PREPARING','plan':p,'approval':approval,'completed':[]};receipt(r)
        try:
            need(plan(ignore_transaction=True)==p,'ACTIVATION_BASELINE_DRIFT')
            previous=CONTROL/'previous';previous.mkdir(mode=0o700)
            for name in ('channel.py',ARCHIVE,'grant-state.json'):create(previous/name,read(BASE/name),stat.S_IMODE((BASE/name).stat().st_mode))
            tree_write(previous/'candidate',{name:read(BASE/'candidate'/name) for name in p['old']['files']})
            need({name:v['sha256'] for name,v in snapshot(previous/'candidate').items()}=={name:v['sha256'] for name,v in p['old']['files'].items()},'BACKUP_HASH')
            need(sha(read(previous/'channel.py'))==p['old']['code_sha256'] and sha(read(previous/ARCHIVE))==p['old']['tar_sha256'] and sha(read(previous/'grant-state.json'))==p['old']['grant_sha256'],'BACKUP_OBJECT_HASH')
            r['completed'].append('BACKUP_VERIFIED');receipt(r);checkpoint('BACKUP_VERIFIED')
            tree_write(CONTROL/'new-candidate',files);create(CONTROL/'new-channel.py',code,0o444);create(CONTROL/'new.tar.gz',archive,0o400)
            r['state']='ACTIVATING';receipt(r);checkpoint('STAGED')
            need(time.time()<approval['expires_unix'] and snapshot(BASE/'candidate')==p['old']['files'] and sha(read(EXEC))==p['old']['wrapper_sha256'] and sha(read(POLICY))==p['old']['policy_sha256'],'PREACTIVATION_DRIFT_OR_EXPIRY')
            r['activation_started']=True;receipt(r)
            replace(BASE/'grant-state.json',b'{"state":"UPGRADING"}',0o600);checkpoint('FENCED')
            move(BASE/'candidate',CONTROL/'parked-old-candidate');checkpoint('OLD_MOVED')
            move(CONTROL/'new-candidate',BASE/'candidate');checkpoint('CANDIDATE_MOVED')
            replace(BASE/'channel.py',code,0o444);checkpoint('CODE_REPLACED')
            replace(BASE/ARCHIVE,archive,0o400);checkpoint('TAR_REPLACED')
            need(snapshot(BASE/'candidate')=={name:{'sha256':sha(raw),'mode':0o400} for name,raw in files.items()} and sha(read(BASE/'channel.py'))==new['binding']['channel_sha256'] and sha(read(BASE/ARCHIVE))==new['binding']['tar_sha256'],'NEW_OBJECTS_VERIFY')
            replace(BASE/'grant-state.json',b'{"state":"GRANTED"}',0o600);checkpoint('GRANTED')
            r['state']='BOUND';r['completed'].append('REBIND_VERIFIED');receipt(r)
            return {'state':'BOUND','receipt':str(CONTROL/'receipt.json'),'customer_install':'NOT_CALLED','sudoers_changed':False}
        except BaseException:
            r['state']='HOLD_PARTIAL'
            if r.get('activation_started'):
                try:
                    if json.loads(read(BASE/'grant-state.json')).get('state') in ('GRANTED','UPGRADING'):
                        replace(BASE/'grant-state.json',b'{"state":"HOLD_UPGRADE"}',0o600)
                except BaseException:r['fence']='UNKNOWN'
            receipt(r);raise

def rollback_impl():
    owner();r=json.loads(read(CONTROL/'receipt.json'));need(r['state'] in ('PREPARING','ACTIVATING','HOLD_PARTIAL','BOUND') and r['approval']['rollback_approved'] is True,'ROLLBACK_STATE')
    previous=CONTROL/'previous';p=r['plan'];new=p['new']['binding']
    if not r.get('activation_started'):
        need(sha(read(BASE/'channel.py'))==OLD_CODE and sha(read(BASE/ARCHIVE))==OLD_TAR and sha(read(BASE/'grant-state.json'))==p['old']['grant_sha256'] and snapshot(BASE/'candidate')==p['old']['files'] and sha(read(EXEC))==p['old']['wrapper_sha256'] and sha(read(POLICY))==p['old']['policy_sha256'],'UNMODIFIED_BASELINE_REQUIRED')
        r['state']='ROLLED_BACK';r['rollback_verified']={'unmodified_old_channel':True,'customer_install_called':False};receipt(r)
        return {'state':'ROLLED_BACK','verification':r['rollback_verified']}

    need(sha(read(EXEC))==p['old']['wrapper_sha256'] and sha(read(POLICY))==p['old']['policy_sha256'],'UNRELATED_POLICY_DRIFT')
    need(sha(read(previous/'channel.py'))==OLD_CODE and sha(read(previous/ARCHIVE))==OLD_TAR and sha(read(previous/'grant-state.json'))==p['old']['grant_sha256'],'BACKUP_IDENTITY')
    backup=snapshot(previous/'candidate');need({k:v['sha256'] for k,v in backup.items()}=={k:v['sha256'] for k,v in p['old']['files'].items()},'BACKUP_TREE_IDENTITY')
    need(sha(read(BASE/'channel.py')) in (OLD_CODE,new['channel_sha256']) and sha(read(BASE/ARCHIVE)) in (OLD_TAR,new['tar_sha256']),'CURRENT_CHANNEL_DRIFT')
    new_files,_,_=unpack(read(CONTROL/'new.tar.gz'))
    if (BASE/'candidate').exists():
        actual={k:v['sha256'] for k,v in snapshot(BASE/'candidate').items()}
        need(actual in ({k:v['sha256'] for k,v in p['old']['files'].items()},{k:sha(v) for k,v in new_files.items()}),'CURRENT_CANDIDATE_DRIFT')
    need(json.loads(read(BASE/'grant-state.json')).get('state') in ('GRANTED','UPGRADING','HOLD_UPGRADE'),'CURRENT_GRANT_DRIFT')
    replace(BASE/'grant-state.json',b'{"state":"UPGRADING"}',0o600)
    if (BASE/'candidate').exists():move(BASE/'candidate',CONTROL/'parked-rollback-candidate')
    tree_write(CONTROL/'restored-candidate',{k:read(previous/'candidate'/k) for k in p['old']['files']});move(CONTROL/'restored-candidate',BASE/'candidate')
    replace(BASE/'channel.py',read(previous/'channel.py'),0o444);replace(BASE/ARCHIVE,read(previous/ARCHIVE),0o400);replace(BASE/'grant-state.json',read(previous/'grant-state.json'),0o600)
    need({k:v['sha256'] for k,v in snapshot(BASE/'candidate').items()}=={k:v['sha256'] for k,v in p['old']['files'].items()},'ROLLBACK_VERIFY')
    r['state']='ROLLED_BACK';r['rollback_verified']={'old_code':sha(read(BASE/'channel.py'))==OLD_CODE,'old_tar':sha(read(BASE/ARCHIVE))==OLD_TAR,'old_candidate':True,'fixed_policy_unchanged':True,'customer_install_called':False};receipt(r)
    return {'state':'ROLLED_BACK','verification':r['rollback_verified']}

def rollback():
    with owner_lock():return rollback_impl()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('plan','apply','rollback'));a=ap.parse_args();os.umask(0o077)
    result=plan() if a.action=='plan' else apply() if a.action=='apply' else rollback()
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':
    try:main()
    except BaseException:print('{"state":"HOLD","retry_allowed":false,"raw_error_redacted":true}');raise SystemExit(2) from None
