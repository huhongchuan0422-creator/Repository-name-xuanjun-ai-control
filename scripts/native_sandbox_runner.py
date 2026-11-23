"""Host-only fixed native-intake plan on existing bubblewrap. No shell/queue.

Candidate bytes come from exact Git objects; other paths must equal the pinned
base. Receipt/process facts live in the original canonical events, never a file
registry. An unknown start is queried, never executed a second time.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import tempfile
import time
from task_supervisor import Supervisor, canonical

REPOSITORY='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
CANDIDATE_FILES=('scripts/development_entry_intake.py','tests/test_development_entry_intake.py')
SUPPORT_FILES=('scripts/native_syntax_intake.py','scripts/native_syntax_gate.py','scripts/task_supervisor.py')
CASES=('WORK_RECEIPT','CHATGPT_RECEIPT','DOTS_RECEIPT','WRONG_SENDER','WRONG_AUTHOR',
       'HIDDEN_CODEX','INVALID_SPEC_HASH','HOST_DESTINATION','WRONG_HOST_PR','STOP_IS_NOT_AUTHORITY')

def challenges():
    # Fixed host-owned behavioral vectors from original intake contract tests.
    import copy
    payload=dict(schema=1,entry='WORK',execution_path='WORK_NATIVE',task_id='XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1',
        spec_sha256='a'*64,checkpoint_sha256='b'*64,target_repository='owner/business',target_base_sha='c'*40,code_commit='d'*40,
        event='CODE_READY',attempt_id='a1',lease_id='lease1',fence=1,epoch=1,caller_id='writer',run_id='run1',session_id='session1',gateway_id='gateway1',lock_provider_id='provider1')
    def case(value,expected,destination=None):
        event=dict(action='created',repository={'full_name':'owner/control'},sender={'login':'owner'},
            issue={'number':27 if destination else 17,'pull_request':{}},comment={'id':123,'user':{'login':'owner'},'body':'<!-- XJ_DEV_ENTRY '+canonical(value)+' -->'})
        args={'event':event,'control_repository':'owner/control','trusted_owner':'owner'}
        if destination:args['destination']=destination
        return {'arguments':args,'expected':expected}
    result=[]
    for entry in ('WORK','CHATGPT','DOTS'):
        result.append(case(dict(payload,entry=entry,execution_path=entry+'_NATIVE'),{'entry':entry,'authority_effect':'NONE','status':'RECEIPT_VALIDATED_NOT_ADMITTED','target_repository':'owner/business'}))
    for who in ('sender','author'):
        row=case(payload,None)
        if who=='sender':row['arguments']['event']['sender']['login']='intruder'
        else:row['arguments']['event']['comment']['user']['login']='intruder'
        result.append(row)
    result.append(case(dict(payload,execution_path='CODEX'),None))
    result.append(case(dict(payload,spec_sha256='x'),None))
    destination={'task_id':'existing-development-task','pull_request_number':27}
    result.append(case(dict(payload,task_id=destination['task_id']),{'task_id':destination['task_id'],'authority_effect':'NONE'},destination))
    row=copy.deepcopy(result[-1]);row['expected']=None;row['arguments']['event']['issue']['number']=28;result.append(row)
    result.append(case(dict(payload,event='STOPPED'),{'event':'STOPPED','authority_effect':'NONE'}))
    return result

# Wall budget is the existing intake workflow's three minutes. Memory follows
# existing supervisor MemoryMax=256M; output follows canonical event 64KiB bound.
TIMEOUT=180
HARNESS=r'''import ctypes,errno,io,json,os,resource,sys,unittest
resource.setrlimit(resource.RLIMIT_AS,(268435456,268435456))
resource.setrlimit(resource.RLIMIT_CPU,(180,180))
resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
requests=json.load(sys.stdin)
lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
if not ctx:raise RuntimeError('SECCOMP_INIT_REQUIRED')
try:
 for name in ('fork','vfork','clone','clone3','execve','execveat','socket','socketpair','connect','mount','umount2','unshare','setns','ptrace','process_vm_readv','process_vm_writev'):
  nr=lib.seccomp_syscall_resolve_name(name.encode())
  if nr>=0 and lib.seccomp_rule_add(ctx,0x00050000|errno.EPERM,nr,0)!=0:raise RuntimeError('SECCOMP_RULE_REQUIRED')
 if lib.seccomp_load(ctx)!=0:raise RuntimeError('SECCOMP_LOAD_REQUIRED')
finally:lib.seccomp_release(ctx)
# These are enforcement probes, not simulated claims/receipts.
import socket
for action in (lambda:open('/tmp/unapproved-write','w'),lambda:open('/home/xuanjun_dev/.secrets/no-access'),lambda:socket.socket()):
 try:
  action();raise RuntimeError('SANDBOX_BOUNDARY_NOT_ENFORCED')
 except (OSError,IOError):pass
try:
 os.fork();raise RuntimeError('SUBPROCESS_BOUNDARY_NOT_ENFORCED')
except OSError:pass
sys.path[:0]=['/work/scripts','/work/tests']
print('XJ_SANDBOX_BOUNDARIES_ENFORCED',flush=True)
from development_entry_intake import validate_event
# Authored test bytes are syntax checked, not trusted to declare a verdict.
compile(open('/work/tests/test_development_entry_intake.py').read(),'candidate-tests','exec')
responses=[]
for index,args in enumerate(requests):
 try:responses.append({'index':index,'result':validate_event(**args)})
 except Exception:responses.append({'index':index,'rejected':True})
print('XJ_SANDBOX_RESPONSE '+json.dumps(responses,sort_keys=True),flush=True)
'''


def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(canonical(value).encode())
def _git(root,*args):
    result=subprocess.run(['/usr/bin/git','--no-replace-objects','-C',root]+list(args),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','LANG':'C.UTF-8'})
    if result.returncode:raise ValueError('HOLD_FIXED_REPOSITORY_GIT_OBJECT_REQUIRED')
    return result.stdout


def _blob(root,commit,path):
    row=_git(root,'ls-tree','-z',commit,'--',path).rstrip(b'\0')
    if not row or b'\t' not in row:raise ValueError('REGULAR_PINNED_GIT_BLOB_REQUIRED')
    metadata,name=row.split(b'\t',1)
    if name.decode()!=path or metadata.split()[0] not in (b'100644',b'100755'):
        raise ValueError('REGULAR_PINNED_GIT_BLOB_REQUIRED')
    return _git(root,'show',commit+':'+path)


def plan_manifest(root,base_commit):
    if not isinstance(base_commit,str) or re.fullmatch('[0-9a-f]{40}',base_commit) is None:
        raise ValueError('PINNED_PLAN_BASE_REQUIRED')
    _git(root,'cat-file','-e',base_commit+'^{commit}')
    support={p:sha(_blob(root,base_commit,p)) for p in SUPPORT_FILES}
    return {'schema':1,'plan':'TC_NATIVE_INTAKE_READONLY_V1','repository':REPOSITORY,'base_commit':base_commit,
        'candidate_files':list(CANDIDATE_FILES),'support':support,'cases':list(CASES),'behavior_vectors_sha256':digest(challenges()),'harness_sha256':sha(HARNESS.encode()),
        'timeout_seconds':TIMEOUT,'memory_bytes':268435456,'output_bytes':65536,
        'filesystem':'READ_ONLY','network':'NONE','subprocesses':'DENIED'}


def process_identity(pid):
    try:
        stat=Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].split()
        if stat[0] in ('Z','X'):return None
        return {'pid':pid,'uid':os.stat('/proc/%d'%pid).st_uid,'start_ticks':stat[19],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError,IndexError):return None


class BubblewrapNativeRunner:
    def __init__(self,db_path,repository_root,base_commit,test_plan_sha256):
        if not isinstance(repository_root,str) or os.path.realpath(repository_root)!=repository_root:
            raise ValueError('CANONICAL_PLAN_REPOSITORY_REQUIRED')
        origin=_git(repository_root,'remote','get-url','origin').decode().strip()
        if origin not in ('https://github.com/'+REPOSITORY+'.git','https://github.com/'+REPOSITORY):
            raise ValueError('FIXED_PLAN_REPOSITORY_IDENTITY_REQUIRED')
        if not isinstance(db_path,str) or os.path.realpath(db_path)!=db_path or not os.path.isfile(db_path):
            raise ValueError('EXISTING_CANONICAL_RUNNER_LEDGER_REQUIRED')
        self.root=repository_root;self.base=base_commit;self.db_path=db_path
        self.manifest=plan_manifest(repository_root,base_commit);self.plan=digest(self.manifest)
        if self.plan!=test_plan_sha256:raise ValueError('PINNED_FIXED_PLAN_DIGEST_REQUIRED')
        self.python=os.path.realpath('/usr/bin/python3.6')
        if not self.python.startswith('/usr/'):raise ValueError('FIXED_SYSTEM_PYTHON_REQUIRED')
    def _db(self):
        db=sqlite3.connect('file:'+self.db_path+'?mode=rw',uri=True,timeout=5)
        db.row_factory=sqlite3.Row
        return db
    def _request(self,db,cid,current=False):
        if not isinstance(cid,str) or re.fullmatch('[0-9a-f]{64}',cid) is None:raise ValueError('EXACT_EXECUTION_ID_REQUIRED')
        eid='development-execution:'+cid+':intent'
        row=db.execute("SELECT * FROM events WHERE event_id=? AND kind='DEVELOPMENT_EXECUTION_INTENT'",(eid,)).fetchall()
        if len(row)!=1:raise ValueError('EXISTING_CANONICAL_EXECUTION_INTENT_REQUIRED')
        request=json.loads(row[0]['payload_json'])
        if request.get('execution_id')!=cid or request.get('candidate_sha256')!=cid or row[0]['evidence_ref']!=digest(request):
            raise ValueError('CANONICAL_EXECUTION_INTENT_MISMATCH')
        if row[0]['task_id']!=request['task_id'] or row[0]['attempt_id']!=request['attempt_id']:
            raise ValueError('CANONICAL_EXECUTION_GENERATION_REQUIRED')
        candidate_rows=db.execute("SELECT * FROM events WHERE task_id=? AND attempt_id=? AND kind='DEVELOPMENT_CANDIDATE' AND evidence_ref=?",
            (request['task_id'],request['attempt_id'],cid)).fetchall()
        if len(candidate_rows)!=1:raise ValueError('EXISTING_CANONICAL_CANDIDATE_REQUIRED')
        candidate=json.loads(candidate_rows[0]['payload_json'])
        if digest(candidate)!=cid or any(candidate.get(k)!=request.get(k) for k in ('schema','task_id','attempt_id','lease_id','fence','epoch','target_repository','code_commit','files')):
            raise ValueError('EXACT_CANONICAL_CANDIDATE_REQUIRED')
        if current:
            task=db.execute('SELECT * FROM tasks WHERE task_id=?',(request['task_id'],)).fetchone()
            if (task is None or any(task[k]!=request[k] for k in ('attempt_id','lease_id','fence','epoch'))
                    or task['authority_state']!='VALID' or task['authority_valid_until'] is None
                    or time.time()>=task['authority_valid_until'] or task['state'] not in ('RECEIVED','STARTED','RUNNING')):
                raise ValueError('CURRENT_SANDBOX_WRITER_REQUIRED')
        return request
    def _event(self,db,request,suffix,kind,payload):
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
            (request['task_id'],request['attempt_id'],'development-execution:'+request['execution_id']+suffix,
             kind,time.time(),'ISOLATED_EXECUTION',digest(payload),canonical(payload)))
    def status(self,cid):
        with self._db() as db:
            request=self._request(db,cid)
            rows=list(db.execute("SELECT event_id,kind,payload_json,evidence_ref FROM events WHERE task_id=? AND attempt_id=? AND event_id IN (?,?,?)",
                (request['task_id'],request['attempt_id'])+tuple('development-execution:'+cid+x for x in (':sandbox-intent',':sandbox-started',':sandbox-result'))))
        events={}
        for row in rows:
            payload=json.loads(row['payload_json'])
            if row['evidence_ref']!=digest(payload):raise ValueError('CANONICAL_SANDBOX_EVIDENCE_MISMATCH')
            events[row['kind']]=payload
        done=events.get('SANDBOX_RESULT');started=events.get('SANDBOX_STARTED')
        if done:state=done['state']
        elif started:state='RUNNING' if process_identity(started['process']['pid'])==started['process'] else 'STOPPED_WITHOUT_RECEIPT'
        else:state='UNKNOWN' if events else 'NOT_SENT'
        return {'execution_id':cid,'task_id':request['task_id'],'attempt_id':request['attempt_id'],'state':state,
            'process':started['process'] if started else None,'result':done,'wake_supported':False,'unknown_effects_policy':'QUERY_ONLY_NO_REPLAY'}
    def lookup(self,cid):
        result=self.status(cid)['result']
        return result.get('receipt') if result else None
    def _lifecycle(self,request,phase,payload):
        supervisor=Supervisor(self.db_path)
        try:
            task=supervisor._task(request['task_id'])
            if any(task[k]!=request[k] for k in ('attempt_id','lease_id','fence','epoch')):
                return 'STALE_GENERATION_NO_PROGRESS_WRITE'
            if phase=='started' and task['state']=='RECEIVED':
                supervisor.record(request['task_id'],request['attempt_id'],'sandbox-start:'+request['execution_id'],
                    'STARTED',time.time(),'PHASE_EXECUTION',digest(payload),payload)
            supervisor.record(request['task_id'],request['attempt_id'],'sandbox-progress:'+phase+':'+request['execution_id'],
                'PROGRESS',time.time(),'PHASE_EXECUTION' if phase=='started' else 'TEST_RUN',digest(payload),payload)
            return 'RECORDED'
        except ValueError as error:
            return str(error)
        finally:supervisor.close()
    def execute(self,request,files):
        cid=request.get('execution_id')
        with self._db() as db:
            if self._request(db,cid,current=True)!=request:raise ValueError('EXACT_CANONICAL_EXECUTION_REQUEST_REQUIRED')
        if request['target_repository']!=REPOSITORY or request['test_plan_sha256']!=self.plan or set(request['files'])!=set(CANDIDATE_FILES):
            raise ValueError('FIXED_ORIGINAL_PLAN_SCOPE_REQUIRED')
        if not isinstance(request['code_commit'],str) or re.fullmatch('[0-9a-f]{40}',request['code_commit']) is None:
            raise ValueError('EXACT_SANDBOX_COMMIT_REQUIRED')
        if {p:sha(raw) for p,raw in files.items()}!=request['files']:raise ValueError('SAME_COMMIT_EXECUTION_BYTES_REQUIRED')
        with self._db() as db:
            contract=db.execute("SELECT payload_json FROM events WHERE task_id=? AND kind='DEVELOPMENT_CONTRACT'",(request['task_id'],)).fetchone()
            if contract is None or json.loads(contract[0])['target_base_sha']!=self.base:raise ValueError('PINNED_CANONICAL_PLAN_BASE_REQUIRED')
        changed=_git(self.root,'diff','--name-only','--no-ext-diff',self.base,request['code_commit'],'--').decode().splitlines()
        if set(changed)-set(CANDIDATE_FILES):raise ValueError('NON_ALLOWED_BASE_BYTES_CHANGED')
        for p in CANDIDATE_FILES:
            mode=_git(self.root,'ls-tree',request['code_commit'],'--',p).decode().split()[0]
            if mode not in ('100644','100755'):raise ValueError('REGULAR_CANDIDATE_GIT_BLOB_REQUIRED')
        material={p:_blob(self.root,request['code_commit'],p) for p in CANDIDATE_FILES}
        if material!=files or any(len(v)>131072 for v in material.values()):raise ValueError('EXACT_COMMIT_CANDIDATE_BYTES_REQUIRED')
        for p,expected in self.manifest['support'].items():
            raw=_blob(self.root,self.base,p)
            if len(raw)>1048576 or sha(raw)!=expected:raise ValueError('PINNED_SUPPORT_BYTES_REQUIRED')
            material[p]=raw
        # Commit send intent BEFORE spawning. Its existence forbids a second run.
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE');self._request(db,cid,current=True)
            prior=db.execute('SELECT 1 FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',
                (request['task_id'],request['attempt_id'],'development-execution:'+cid+':sandbox-intent')).fetchone()
            if prior:return self.lookup(cid)
            self._event(db,request,':sandbox-intent','SANDBOX_INTENT',{'request_sha256':digest(request),'test_plan_sha256':self.plan})
        done=None
        with tempfile.TemporaryDirectory(prefix='tc-native-sandbox-') as tmp:
            root=Path(tmp);work=root/'work';work.mkdir()
            for p,raw in material.items():
                target=work/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            (root/'harness.py').write_text(HARNESS)
            command=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL',
                '--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--symlink','usr/bin','/bin',
                '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(work),'/work',
                '--ro-bind',str(root/'harness.py'),'/harness.py',
                '--remount-ro','/proc','--remount-ro','/dev','--remount-ro','/tmp','--remount-ro','/',
                '--chdir','/work','--',self.python,'-I','-B','/harness.py']
            with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
                proc=None
                try:
                    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},start_new_session=True)
                    identity=process_identity(proc.pid)
                    if identity is None:raise ValueError('PROCESS_IDENTITY_UNAVAILABLE')
                    with self._db() as db:
                        self._request(db,cid,current=True)
                        self._event(db,request,':sandbox-started','SANDBOX_STARTED',{'execution_id':cid,'process':identity,'controller_pid':os.getpid()})
                    self._lifecycle(request,'started',{'execution_id':cid,'process':identity})
                    vectors=challenges()
                    proc.communicate(canonical([row['arguments'] for row in vectors]).encode(),timeout=TIMEOUT)
                    stdout.seek(0);stderr.seek(0);out=stdout.read(65537);err=stderr.read(65537)
                    messages=[line[len(b'XJ_SANDBOX_RESPONSE '):] for line in out.splitlines() if line.startswith(b'XJ_SANDBOX_RESPONSE ')]
                    responses=json.loads(messages[-1]) if messages else []
                    checks=[]
                    for index,vector in enumerate(vectors):
                        found=[r for r in responses if isinstance(r,dict) and r.get('index')==index] if isinstance(responses,list) else []
                        row=found[0] if len(found)==1 else {}
                        expected=vector['expected']
                        checks.append(row.get('rejected') is True if expected is None else
                            isinstance(row.get('result'),dict) and all(row['result'].get(k)==v for k,v in expected.items()))
                    boundaries=b'XJ_SANDBOX_BOUNDARIES_ENFORCED' in out.splitlines()
                    state='PASSED' if proc.returncode==0 and boundaries and all(checks) else 'FAILED'
                    detail={'exit_code':proc.returncode,'stdout_sha256':sha(out),'stderr_sha256':sha(err),
                        'host_checks':checks,'boundaries_enforced':boundaries}
                    receipt={k:request[k] for k in ('schema','execution_id','candidate_sha256','code_commit','test_plan_sha256')}
                    receipt.update(state=state,isolation='ISOLATED',tests_executed=len(checks),result_sha256=digest(detail))
                    done={'state':state,'detail':detail,'receipt':receipt}

                except subprocess.TimeoutExpired:
                    detail={'reason':'FIXED_PLAN_TIMEOUT','host_checks':[False]*len(CASES),'timeout_seconds':TIMEOUT}
                    receipt={k:request[k] for k in ('schema','execution_id','candidate_sha256','code_commit','test_plan_sha256')}
                    receipt.update(state='FAILED',isolation='ISOLATED',tests_executed=len(CASES),result_sha256=digest(detail))
                    done={'state':'FAILED','detail':detail,'receipt':receipt}
                except Exception as exc:
                    done={'state':'FAILED','reason':type(exc).__name__,'receipt':None}
                finally:
                    if proc is not None and proc.poll() is None:
                        proc.kill();proc.wait()
        with self._db() as db:self._event(db,request,':sandbox-result','SANDBOX_RESULT',done)
        self._lifecycle(request,'finished',{'execution_id':cid,'state':done['state'],'result_sha256':digest(done)})
        return done['receipt']
