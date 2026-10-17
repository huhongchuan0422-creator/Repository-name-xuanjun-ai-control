"""Fixed PR122 readonly permit gate. No enrollment, signing, or registry creation.
Reuse R4 root-private exact-comment pin + existing durable authorization registry.
Missing protected runner integration is HOLD, never a workspace/env fallback.
"""
import base64, datetime, hashlib, json, os, re, stat, time
from pathlib import Path

PERMIT_REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
PERMIT_PATH = '.github/workflows/aliyun-account-readonly-admission-once-20261017.yml'
PERMIT_ANCHOR = Path('/etc/xuanjun-pr122-release/readonly-admission.json')
PERMIT_REGISTRY = Path('/var/lib/xuanjun-pr122-authorizations')
# Historical R4 protected-source location only; NOT an instruction to use this host.
# No relocation to Hosted, no provisioning, and no deployment is authorized here.
PERMIT_EXECUTOR_HOST = 'iZ6wee8q9z4t03hvqumwfhZ'
PERMIT_KIND = 'PR122_ROOT_READONLY_ADMISSION_V1'
PERMIT_BEGIN = '<!-- '+PERMIT_KIND+'\n'
PERMIT_END = '\n'+PERMIT_KIND+' -->'
PERMIT_ACTIONS = ['STS:AssumeRole', 'SWAS:RunCommand:READONLY_FIXED_PAYLOAD', 'SWAS:DescribeInvocationResult:SAME_INVOKE_ID']
PERMIT_BRANCH = 'feature/stage5-next25-integration-20261015'
PERMIT_BASE = 'feature/stage5-merchant-platform-storefront-ui-20261014'
PERMIT_BUNDLE = '2880d718ed848e055f2945da79a1b8f6bec0aeb3368b50fbf29dcb71550dad62'
PERMIT_CALLER = '118e3e972fd94a34647c1a289f449caf4eef40dbb444611d99f53d155cd148ba'

class PermitDenied(Exception): pass

def permit_need(ok, code):
    if not ok: raise PermitDenied(code)

def permit_json(raw):
    def pairs(items):
        out={}
        for k,v in items:
            permit_need(k not in out,'DUPLICATE_JSON_KEY');out[k]=v
        return out
    def invalid(_):raise PermitDenied('NONFINITE_JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

def permit_hash(raw):return hashlib.sha256(raw).hexdigest()
def permit_hex(v,n):return type(v) is str and re.fullmatch('[0-9a-f]{'+str(n)+'}',v) is not None

def permit_secure(path, directory=False):
    path=Path(path);permit_need(path.is_absolute(),'FIXED_ABSOLUTE_PATH')
    for item in reversed((path,*path.parents)):
        s=os.lstat(item)
        permit_need(s.st_uid==0 and not stat.S_ISLNK(s.st_mode) and not stat.S_IMODE(s.st_mode)&0o022,'ROOT_PRIVATE_PARENT')
        if item!=path or directory:permit_need(stat.S_ISDIR(s.st_mode),'ROOT_DIRECTORY')
    s=os.lstat(path)
    if directory:permit_need(stat.S_IMODE(s.st_mode)==0o700,'REGISTRY_NOT_PROTECTED')
    else:permit_need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'ROOT_PRIVATE_FILE')

def permit_read(path):
    permit_secure(path)
    before=os.lstat(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        permit_need((s.st_dev,s.st_ino)==(before.st_dev,before.st_ino),'PIN_INODE_DRIFT')
        raw=f.read(65537);after=os.fstat(f.fileno())
        permit_need(len(raw)<=65536 and (s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),'PIN_READ_DRIFT')
    named=os.lstat(path)
    permit_need((named.st_dev,named.st_ino,named.st_mtime_ns,named.st_ctime_ns)==(s.st_dev,s.st_ino,s.st_mtime_ns,s.st_ctime_ns),'PIN_NAME_DRIFT')
    return raw

def permit_write_once(path, value):
    # Existing protected registry only. Partial files permanently consume this attempt.
    permit_secure(path.parent,directory=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write((json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode());f.flush();os.fsync(f.fileno())
    for directory in (path.parent,path.parent.parent):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

class ReadonlyPermit:
    def __init__(self, fetch, env=None, clock=None):
        self.fetch=fetch;self.env=os.environ if env is None else env;self.clock=time.time if clock is None else clock
        self.anchor=PERMIT_ANCHOR;self.registry=PERMIT_REGISTRY;self.proof=None;self.pin_hash=None
    def get(self,path):return self.fetch('/repos/'+PERMIT_REPO+path)
    def validate(self):
        # Before cloud credential access. Hosted default has no enrollment and fails here.
        permit_need(os.geteuid()==0 and os.uname().nodename==PERMIT_EXECUTOR_HOST,'EXISTING_PROTECTED_SOURCE_UNAVAILABLE')
        permit_secure(self.registry,directory=True)
        raw=permit_read(self.anchor);pin=permit_json(raw)
        fields={'schema','action','approval_comment_id','approval_body_sha256','reviewer_principal','source_writer_principal','custody_evidence_sha256','owner_attests_independent_review','runner_hostname','registry_persistent','revoked'}
        permit_need(type(pin) is dict and set(pin)==fields and type(pin['schema']) is int and pin['schema']==1,'PIN_SCHEMA')
        permit_need(pin['action']==PERMIT_KIND and pin['owner_attests_independent_review'] is True and pin['registry_persistent'] is True and pin['revoked'] is False,'PROTECTED_INDEPENDENT_PIN_REQUIRED')
        permit_need(type(pin['reviewer_principal']) is str and bool(pin['reviewer_principal']) and type(pin['source_writer_principal']) is str and bool(pin['source_writer_principal']) and pin['reviewer_principal']!=pin['source_writer_principal'] and permit_hex(pin['custody_evidence_sha256'],64),'INDEPENDENT_CUSTODY_REQUIRED')
        permit_need(pin['runner_hostname']==os.uname().nodename,'PROTECTED_EXECUTOR_IDENTITY')
        cid=pin['approval_comment_id'];permit_need(type(cid) is int and cid>0 and permit_hex(pin['approval_body_sha256'],64),'EXACT_PIN_REQUIRED')
        c=self.get('/issues/comments/'+str(cid));body=c.get('body')
        permit_need(c.get('id')==cid and c.get('issue_url')=='https://api.github.com/repos/'+PERMIT_REPO+'/issues/122' and c.get('user',{}).get('id')==332398908 and (c.get('performed_via_github_app') or {}).get('id')==1144995,'COMMENT_PROVENANCE')
        permit_need(type(body) is str and permit_hash(body.encode())==pin['approval_body_sha256'],'COMMENT_BODY_HASH')
        permit_need(body.count(PERMIT_BEGIN)==body.count(PERMIT_END)==1,'FORMAL_PERMIT_BLOCK')
        p=permit_json(body.split(PERMIT_BEGIN,1)[1].split(PERMIT_END,1)[0])
        keys={'schema','kind','decision','repository','pr_number','head_sha','base_sha','merge_sha','workflow_ref','workflow_blob_sha','workflow_sha256','payload_sha256','caller_sha256','reviewer_principal','source_writer_principal','custody_evidence_sha256','approval_nonce','issued_unix','expires_unix','max_attempts','region','instance_id','hostname','role_arn','actions','max_run_commands','query_same_invoke_only'}
        permit_need(type(p) is dict and set(p)==keys,'PERMIT_SCHEMA')
        permit_need(type(p['schema']) is int and p['schema']==1 and p['kind']==PERMIT_KIND and p['decision']=='APPROVED_EXACT_ONE_ATTEMPT' and p['repository']==PERMIT_REPO and type(p['pr_number']) is int and p['pr_number']==122,'PERMIT_DECISION')
        for k in ('reviewer_principal','source_writer_principal','custody_evidence_sha256'):permit_need(p[k]==pin[k],'INDEPENDENT_PIN_BINDING')
        permit_need(all(permit_hex(p[k],40) for k in ('head_sha','base_sha','merge_sha','workflow_blob_sha')) and all(permit_hex(p[k],64) for k in ('workflow_sha256','payload_sha256','caller_sha256')) and permit_hex(p['approval_nonce'],32),'BINDING_FORMAT')
        permit_need(p['payload_sha256']==PERMIT_BUNDLE and p['caller_sha256']==PERMIT_CALLER,'FIXED_READONLY_PAYLOAD')
        permit_need(type(p['max_attempts']) is int and p['max_attempts']==1 and type(p['max_run_commands']) is int and p['max_run_commands']==1 and p['query_same_invoke_only'] is True and p['actions']==PERMIT_ACTIONS,'RUN_QUERY_SCOPE')
        permit_need(p['region']=='cn-shanghai' and p['instance_id']=='3a22c458934142eea89ec6e3bf481a57' and p['hostname']=='iZvt5t8tlrm8oiZ' and p['role_arn']=='acs:ram::1384884686754410:role/xuanjun-automation','FIXED_TARGET')
        now=self.clock();start=p['issued_unix'];end=p['expires_unix']
        permit_need(type(start) is int and type(end) is int and start<=now<end and 0<end-start<=1800,'PERMIT_EXPIRED')
        created=datetime.datetime.fromisoformat(c['created_at'].replace('Z','+00:00')).timestamp()
        permit_need(abs(created-start)<=60,'ISSUANCE_TIME')
        pr=self.get('/pulls/122')
        permit_need(pr.get('state')=='open' and pr.get('mergeable') is True and pr['head']['repo']['full_name']==PERMIT_REPO and pr['head']['ref']==PERMIT_BRANCH and pr['base']['ref']==PERMIT_BASE,'PR_IDENTITY')
        permit_need((pr['head']['sha'],pr['base']['sha'],pr['merge_commit_sha'])==(p['head_sha'],p['base_sha'],p['merge_sha']),'FINAL_BINDING_DRIFT')
        ref=PERMIT_REPO+'/'+PERMIT_PATH+'@refs/pull/122/merge'
        permit_need(p['workflow_ref']==ref and self.env.get('GITHUB_WORKFLOW_REF')==ref and self.env.get('GITHUB_WORKFLOW_SHA')==p['merge_sha'] and self.env.get('GITHUB_RUN_ATTEMPT')=='1','EXECUTABLE_WORKFLOW_IDENTITY')
        for rev in (p['head_sha'],p['merge_sha']):
            entry=self.get('/contents/'+PERMIT_PATH+'?ref='+rev)
            permit_need(entry.get('type')=='file' and entry.get('path')==PERMIT_PATH and entry.get('sha')==p['workflow_blob_sha'] and entry.get('encoding')=='base64','WORKFLOW_BLOB_BINDING')
            data=base64.b64decode(''.join(entry['content'].split()),validate=True)
            permit_need(permit_hash(data)==p['workflow_sha256'] and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==p['workflow_blob_sha'],'WORKFLOW_BYTES')
        permit_need(self.clock()<end,'EXPIRY_DURING_VALIDATION')
        p=dict(p,approval_comment_id=cid,approval_body_sha256=pin['approval_body_sha256'])
        pin_hash=permit_hash(raw)
        if self.proof is not None:permit_need(p==self.proof and pin_hash==self.pin_hash,'PERMIT_OR_ANCHOR_DRIFT')
        self.proof=p;self.pin_hash=pin_hash
        return p
    def record(self):
        permit_need(self.proof is not None,'VALIDATED_PERMIT_REQUIRED')
        run=self.env.get('GITHUB_RUN_ID','');permit_need(re.fullmatch('[1-9][0-9]*',run) is not None,'RUN_ID')
        return {'schema':1,'kind':PERMIT_KIND,'pin_sha256':self.pin_hash,'approval_comment_id':self.proof['approval_comment_id'],'approval_body_sha256':self.proof['approval_body_sha256'],'approval_nonce':self.proof['approval_nonce'],'head_sha':self.proof['head_sha'],'merge_sha':self.proof['merge_sha'],'workflow_sha256':self.proof['workflow_sha256'],'run_id':run,'run_attempt':1,'expires_unix':self.proof['expires_unix'],'retry_allowed':False}
    def marker(self):return self.registry/('approval-'+str(self.proof['approval_comment_id'])+'.consumed.json')
    def reserve(self):
        self.validate();record=self.record()
        # Same existing registry; second nonce marker rejects new comment-ID reuse.
        permit_write_once(self.registry/('readonly-nonce-'+self.proof['approval_nonce']+'.consumed.json'),record)
        permit_write_once(self.marker(),record)
        self.validate()
        return record
    def owned(self):
        self.validate();record=self.record()
        permit_need(permit_json(permit_read(self.marker()))==record and permit_json(permit_read(self.registry/('readonly-nonce-'+self.proof['approval_nonce']+'.consumed.json')))==record,'CONSUMED_BY_OTHER_ATTEMPT')
        return record
    def claim_dispatch(self):
        record=self.owned();permit_write_once(self.registry/('approval-'+str(self.proof['approval_comment_id'])+'.dispatch.json'),record)
        self.validate();return record
    def bind_invoke(self,invoke):
        permit_need(type(invoke) is str and re.fullmatch('[A-Za-z0-9_-]{1,180}',invoke) is not None,'INVOKE_ID')
        record=self.owned();permit_write_once(self.registry/('approval-'+str(self.proof['approval_comment_id'])+'.invoke.json'),dict(record,invoke_id=invoke))
    def query(self,invoke):
        record=self.owned();saved=permit_json(permit_read(self.registry/('approval-'+str(self.proof['approval_comment_id'])+'.invoke.json')))
        permit_need(saved==dict(record,invoke_id=invoke),'QUERY_INVOKE_SCOPE')
