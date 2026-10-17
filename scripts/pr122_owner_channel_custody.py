"""Owner-only preparation of exact reviewed upgrader and custody evidence.
No target channel writes, no apply/rollback, no imports/exec of candidate code.
Requires a separately issued exact one-use PREPARE permit and actual Owner TTY.
"""
import argparse
import datetime
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

HOST='iZvt5t8tlrm8oiZ'
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
ATTEMPT='pr122-owner-channel-custody-20261017-r2'
STAGE=Path('/home/githubrunner/pr122-owner-inputs/channel-custody-20261017/REVIEW.zip')
OUT=Path('/root')/ATTEMPT
ZIP_SHA='9b59332f3806f215d2022c1510a74840f25cb84beec6a8d20e7026882d15b68d'
TAR_SHA='899ea35bae939101be4841d69fd36e5de3dc01f89f243ca5359a840a28eb08fa'
MANIFEST_SHA='c288d444789a4075d14a6d646c33514b47b179cf97b2e8f4c49b27d3a46038e2'
HELPER_SHA='832900dd64028233a19a9850b317648b552da19e4c588209692d0fdad26e3d4d'
RUNTIME_SHA='d03a09d3110cf372d5c6209da4514fffd77f8487c6a36532744e80557ac353d8'
AUDIT_ID=6227830181
AUDIT_SHA='d2f494bb8b3594dc8f7e5f26cb5cd51be1885a16d7c44612346775a20f36e339'
CONFIRM='CONFIRM_OWNER_CUSTODY_AND_SEPARATE_REVIEW'

def need(ok,msg):
    if not ok:raise RuntimeError('HOLD:'+msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def digest(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def read(path,uid=0,limit=12000000):
    path=Path(path);need(path.is_absolute(),'ABSOLUTE_PATH')
    for p in (path,*path.parents):
        s=p.lstat();need(not stat.S_ISLNK(s.st_mode) and not stat.S_IMODE(s.st_mode)&0o022,'PATH_MODE_OR_LINK')
        need(s.st_uid in ((0,uid) if p!=path else (uid,)),'PATH_OWNER')
        if p!=path:need(stat.S_ISDIR(s.st_mode),'PARENT_DIRECTORY')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno());need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=limit,'FILE_TYPE_SIZE')
        b=f.read(limit+1);a=os.fstat(f.fileno())
    need((s.st_ino,s.st_size,s.st_mtime_ns)==(a.st_ino,a.st_size,a.st_mtime_ns) and len(b)<=limit,'READ_DRIFT')
    return b

def write(path,b):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as f:
        os.fchmod(f.fileno(),0o400);f.write(b);f.flush();os.fsync(f.fileno())
    sync(path.parent)
def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise RuntimeError('HOLD:REDIRECT')
def fetch(comment):
    need(type(comment) is int and comment>0,'COMMENT_ID')
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/issues/comments/'+str(comment),headers={'Accept':'application/vnd.github+json','User-Agent':'PR122-Owner-Custody-Prepare'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=20) as r:b=r.read(30001)
    need(len(b)<=30000,'COMMENT_SIZE');return json.loads(b)
def comment_body(c,ident,expected):
    need(digest(expected) and c['id']==ident and c['user']['login']=='huhongchuan0422-creator' and c['issue_url']=='https://api.github.com/repos/'+REPO+'/issues/122' and sha(c['body'].encode())==expected,'COMMENT_IDENTITY')
    return c['body']

def permit(ident,expected,get=fetch):
    body=comment_body(get(ident),ident,expected)
    need(body.startswith('XUANJUN_PR122_OWNER_CUSTODY_PREPARE\n'),'PERMIT_PURPOSE')
    p=json.loads(body.split('\n',1)[1]);now=time.time()
    need(p['decision']=='OWNER_CUSTODY_PREPARE_APPROVED' and p['attempt_id']==ATTEMPT and p['host']==HOST and
         p['launcher_sha256']==sha(read(Path(__file__).absolute())) and p['review_zip_sha256']==ZIP_SHA and
         p['helper_sha256']==HELPER_SHA and p['audit_comment_id']==AUDIT_ID and p['audit_body_sha256']==AUDIT_SHA and
         p['max_attempts']==1 and p['channel_write_allowed'] is False and p['apply_allowed'] is False and
         type(p['issued_unix']) is int and type(p['expires_unix']) is int and
         p['issued_unix']<=now<p['expires_unix'] and 0<p['expires_unix']-p['issued_unix']<=7200,'PERMIT_SCOPE')
    return body

def decode(raw):
    need(sha(raw)==ZIP_SHA,'REVIEW_ZIP_HASH')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();need(set(names)=={'PR122_CHANNEL_RECOVERY_REVIEW_ONLY.tar.gz','pr122-recovery-review/REVIEW_MANIFEST.json'} and len(names)==2,'ZIP_MEMBERS')
        need(all(i.file_size<=10000000 for i in z.infolist()),'ZIP_SIZE')
        tar=z.read('PR122_CHANNEL_RECOVERY_REVIEW_ONLY.tar.gz');external=z.read('pr122-recovery-review/REVIEW_MANIFEST.json')
    need(sha(tar)==TAR_SHA and sha(external)==MANIFEST_SHA,'PACKAGE_HASH')
    with tarfile.open(fileobj=io.BytesIO(tar),mode='r:gz') as t:
        ms=t.getmembers();need(len(ms)==len({m.name for m in ms})==8 and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts and m.size<=10000000 for m in ms),'TAR_MEMBERS')
        manifest=t.extractfile('channel-recovery/REVIEW_MANIFEST.json').read();need(manifest==external,'MANIFEST_IDENTITY')
        m=json.loads(manifest);need(m['source_commit']=='70b261d6284391db382b4f876d74666892e63943' and len(m['files'])==7,'MANIFEST_SOURCE')
        need({x.name for x in ms}=={'channel-recovery/'+x['path'] for x in m['files']}|{'channel-recovery/REVIEW_MANIFEST.json'},'MANIFEST_SET')
        files={}
        for x in m['files']:
            b=t.extractfile('channel-recovery/'+x['path']).read();need(len(b)==x['size'] and sha(b)==x['sha256'],'MEMBER_HASH');files[x['path']]=b
    helper=files['scripts/pr122_customer_channel_upgrade.py'];runtime=files['REVIEW_ARTIFACT.zip']
    need(sha(helper)==HELPER_SHA and sha(runtime)==RUNTIME_SHA,'EXECUTION_PINS')
    return helper,runtime

def declaration(tty,audit_body):
    # This is an Owner attestation, not cryptographic proof of auditor independence.
    need(tty.isatty(),'OWNER_TTY_REQUIRED')
    tty.write('本步骤仅准备私有证据，不安装、不升级。\n请Owner核实实际独审来自与代码作者不同的审核主体；若不能确认，请Ctrl+C停止。\n')
    tty.write('独立审核原文如下：\n'+audit_body+'\n')
    values=[]
    for prompt in ('Owner保管主体标识：','源码作者主体标识：','实际独立审核主体标识：','上述独立审核原始证据的SHA256（不得编造）：','输入 '+CONFIRM+' 确认属实：'):
        while True:
            tty.write(prompt);tty.flush();line=tty.readline(513)
            need(line.endswith('\n') and len(line)<=512,'OWNER_INPUT_EOF_OR_OVERSIZE')
            if line.strip():
                values.append(line.strip());break
            tty.write('尚未填写，请在此项输入真实内容后回车；Ctrl+C可停止。\n')
    owner,writer,reviewer,proof,confirmation=values
    need(all(x and len(x)<=128 for x in (owner,writer,reviewer)) and writer!=reviewer and digest(proof) and confirmation==CONFIRM,'OWNER_CONFIRMATION')
    return {'owner_principal':owner,'source_writer_principal':writer,'reviewer_principal':reviewer,'external_evidence_sha256':proof,'attestation_kind':'OWNER_PROTECTED_TTY_STATEMENT_NOT_CRYPTOGRAPHIC_INDEPENDENCE_PROOF'}

def prepare(ident,body_sha,get=fetch,tty=None):
    need(os.getuid()==os.geteuid()==0 and os.uname().nodename==HOST and os.environ.get('SUDO_UID')!='1002','OWNER_ROOT_HOST')
    os.umask(0o077)
    approved=permit(ident,body_sha,get);audit=comment_body(get(AUDIT_ID),AUDIT_ID,AUDIT_SHA)
    need(not os.path.lexists(OUT),'ATTEMPT_EXISTS_NO_RETRY')
    # Consume before reading operator/staged input. All failures preserve evidence.
    OUT.mkdir(mode=0o700);sync(OUT.parent)
    write(OUT/'attempt.json',canonical({'attempt':ATTEMPT,'approval_id':ident,'approval_sha256':body_sha,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'STARTED_NO_RETRY'}))
    write(OUT/'approval.txt',approved.encode());write(OUT/'audit.txt',audit.encode())
    phase='INPUT_PACKAGE'
    try:
        helper,runtime=decode(read(STAGE,uid=1002))
        need(tty is not None,'OWNER_TTY_REQUIRED');phase='OWNER_CONFIRMATION';attest=declaration(tty,audit)
        phase='APPROVAL_RECHECK'
        need(permit(ident,body_sha,get)==approved,'PERMIT_CHANGED')
        need(comment_body(get(AUDIT_ID),AUDIT_ID,AUDIT_SHA)==audit,'AUDIT_CHANGED')
        phase='PRIVATE_EVIDENCE_SAVE'
        attest.update(host=HOST,uid=os.getuid(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),audit_comment_id=AUDIT_ID,audit_body_sha256=AUDIT_SHA)
        write(OUT/'OWNER_CUSTODY.json',canonical(attest))
        write(OUT/'approved-upgrade.py',helper);write(OUT/'REVIEW_ARTIFACT.zip',runtime)
        receipt={'state':'CUSTODY_PREPARED_AWAIT_INDEPENDENT_ACCEPTANCE','attempt':ATTEMPT,'host':HOST,'uid':0,'evidence_sha256':sha(read(OUT/'OWNER_CUSTODY.json')),'helper_sha256':sha(read(OUT/'approved-upgrade.py')),'runtime_sha256':sha(read(OUT/'REVIEW_ARTIFACT.zip')),'private_files_mode':'0400','private_directory_mode':'0700','trust_installed':False,'helper_executed':False,'apply_called':False,'channel_changes':0,'retry_allowed':False}
        receipt['objects']={}
        for path in sorted(OUT.iterdir()):
            info=path.lstat()
            need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o400 and info.st_nlink==1,'OUTPUT_METADATA')
            receipt['objects'][path.name]={'uid':info.st_uid,'gid':info.st_gid,'mode':oct(stat.S_IMODE(info.st_mode)),'sha256':sha(read(path))}
        info=OUT.lstat();need(info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o700,'OUTPUT_DIRECTORY')
        write(OUT/'receipt.json',canonical(receipt));return receipt
    except BaseException:
        write(OUT/'failure.json',canonical({'state':'HOLD','phase':phase,'retry_allowed':False,'channel_changes':0}));raise

def open_terminal(path='/dev/tty'):
    # BufferedRandom (open r+) requires seekability; terminals are non-seekable.
    import termios
    raw=io.FileIO(path,'r+')
    try:
        termios.tcflush(raw.fileno(),termios.TCIFLUSH)
        return io.TextIOWrapper(raw,encoding='utf-8',write_through=True)
    except BaseException:
        raw.close();raise

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('prepare',));ap.add_argument('--approval-id',type=int,required=True);ap.add_argument('--approval-body-sha256',required=True);a=ap.parse_args()
    with open_terminal() as tty:r=prepare(a.approval_id,a.approval_body_sha256,tty=tty)
    print(json.dumps(r,sort_keys=True))
if __name__=='__main__':
    try:main()
    except BaseException:print('{"state":"HOLD","retry_allowed":false,"channel_changes":0}');raise SystemExit(2) from None
