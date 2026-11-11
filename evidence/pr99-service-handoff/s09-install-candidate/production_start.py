"""PR99 domestic production start candidate. Does not issue its own admission.
Requires a real final checkpoint, prepared dedicated identity, and exact root-held
admission. Never starts from the preliminary r1/r2 copied data. No route edits.
"""
import fcntl
import hashlib
import http.client
import json
import os
import pwd
import grp
import re
import stat
import socket
import subprocess
import time
from pathlib import Path

HOST='iZvt5t8tlrm8oiZ'
RELEASE=Path('/opt/xuanjun-migration-s07/releases/domestic-final-v1')
ROOT=RELEASE/'rootfs'
PERMIT=Path('/etc/xuanjun-pr99/s09-production-start.admission.json')
STATE=Path('/var/lib/xuanjun-pr99-s09-production-start-v1')
SYSTEMD=Path('/etc/systemd/system')
UNITS={'portal':('scripts/secure_secrets_portal_server.py serve --host 127.0.0.1 --port 18080',18080), 'contact':('-m ai_service.wecom_customer_contact_service',18781),'customer-service':('-m ai_service.wecom_customer_service',18780)}

def require(ok,code):
 if not ok:raise RuntimeError(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def read(p,limit=67108864,runtime_uid=None,runtime_gid=None):
 p=Path(p)
 for a in reversed((p,*p.parents)):
  s=a.lstat();require(not stat.S_ISLNK(s.st_mode),'INPUT_SYMLINK')
  if runtime_uid is not None and (a==ROOT or a.is_relative_to(ROOT)):
   require(s.st_uid in (0,runtime_uid) and not s.st_mode&0o002 and (not s.st_mode&0o020 or s.st_gid==runtime_gid),'RUNTIME_INPUT_OWNER_MODE')
  else:require(s.st_uid==0 and not s.st_mode&0o022,'ROOT_INPUT_PATH')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  before=os.fstat(fd);require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit,'FILE_TYPE_SIZE')
  with os.fdopen(os.dup(fd),'rb') as f:b=f.read(limit+1)
  after=os.fstat(fd);require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and len(b)==before.st_size,'FILE_DRIFT')
  return b
 finally:os.close(fd)
def create(p,b,mode=0o600):
 fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 d=os.open(Path(p).parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(d)
 finally:os.close(d)
class KnownEffectFailure(RuntimeError):
 pass
class EffectUnknown(RuntimeError):
 pass

def ctl(*args):
 r=subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,timeout=20)
 if r.returncode!=0:raise KnownEffectFailure('SYSTEMCTL_FAILED')
 return r.stdout.decode()
def stopped(name):
 v=dict(l.split('=',1) for l in ctl('show',name,'--property=ActiveState,MainPID','--no-pager').splitlines() if '=' in l)
 return v.get('MainPID')=='0' and v.get('ActiveState') in ('inactive','failed')
def unit_name(role):return 'xuanjun-pr99-domestic-'+role+'.service'
def units(account):
 require(account=='xuanjun-s07','DEDICATED_IDENTITY_NAME')
 common='''\nEnvironment=PYTHONPATH=/opt/trading-system PYTHONDONTWRITEBYTECODE=1
Environment=WECOM_CONTACT_HOST=127.0.0.1 WECOM_CONTACT_PORT=18781
Environment=WECOM_KF_HOST=127.0.0.1 WECOM_KF_PORT=18780
BindReadOnlyPaths=/usr /lib /lib64
PrivateDevices=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/trading-system/runtime
NoNewPrivileges=yes
CapabilityBoundingSet=
RestrictSUIDSGID=yes
UMask=0077
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
KillMode=control-group
StandardOutput=null
StandardError=null
'''
 return {unit_name(role):('[Unit]\nDescription=PR99 approved domestic '+role+'\nStartLimitIntervalSec=60\nStartLimitBurst=3\n\n[Service]\nType=simple\nUser='+account+'\nGroup='+account+'\nRootDirectory='+str(ROOT)+'\nWorkingDirectory=/opt/trading-system\nExecStart=/venv/bin/python '+cmd+common).encode() for role,(cmd,_) in UNITS.items()}
def validate_final_receipts(p,fence_raw,checkpoint_raw,assignment_raw,now):
 # These bytes must ALSO be pinned by the original independent root-held permit.
 # Structure alone is never evidence that a writer was actually fenced.
 require(p.get('source_writer_fence_receipt_sha256')==sha(fence_raw),'SOURCE_FENCE_PROOF')
 require(p.get('final_checkpoint_receipt_sha256')==sha(checkpoint_raw),'FINAL_CHECKPOINT_PROOF')
 require(p.get('canonical_writer_assignment_sha256')==sha(assignment_raw),'WRITER_ASSIGNMENT_PROOF')
 fence=json.loads(fence_raw);checkpoint=json.loads(checkpoint_raw);assignment=json.loads(assignment_raw)
 require(all(type(x) is dict for x in (fence,checkpoint,assignment)),'FINAL_RECEIPT_SCHEMA')
 inventory=p.get('writer_inventory_sha256');epoch=p.get('writer_epoch')
 require(type(inventory) is str and re.fullmatch('[0-9a-f]{64}',inventory) and type(epoch) is int and epoch>0,'WRITER_BINDING_REQUIRED')
 require(fence.get('action')=='PR99_SOURCE_WRITER_FENCE_V1' and
         fence.get('source_host')=='iZ6wee8q9z4t03hvqumwfhZ' and
         fence.get('writer_inventory_sha256')==inventory and fence.get('writer_epoch')==epoch and
         fence.get('writers_stopped') is True and fence.get('inflight_drained') is True and
         fence.get('unresolved_shared_writers')==[],'SOURCE_WRITER_NOT_FENCED')
 observed=fence.get('observed_at');captured=checkpoint.get('captured_at')
 require(type(observed) is int and type(captured) is int and now-7200<=observed<=captured<=now,'FINAL_RECEIPT_TIME')
 files=p.get('final_data_file_hashes');all_files=p.get('file_hashes',{})
 require(type(files) is dict and files and all(type(n) is str and type(v) is str and
         re.fullmatch('[0-9a-f]{64}',v) and all_files.get(n)==v for n,v in files.items()),'FINAL_DATA_BINDING')
 require(checkpoint.get('class')=='FINAL_CANONICAL_CHECKPOINT' and checkpoint.get('source_fence_sha256')==sha(fence_raw)
         and checkpoint.get('files')==files and checkpoint.get('database_integrity')=='PASS'
         and type(p.get('database_schema_sha256')) is str and re.fullmatch('[0-9a-f]{64}',p['database_schema_sha256'])
         and checkpoint.get('database_schema_sha256')==p['database_schema_sha256'],'FINAL_CHECKPOINT_SEMANTICS')
 require(assignment.get('action')=='PR99_CANONICAL_WRITER_ASSIGNMENT_V1' and assignment.get('target_host')==HOST
         and assignment.get('release')==str(RELEASE) and assignment.get('checkpoint_sha256')==sha(checkpoint_raw)
         and assignment.get('writer_inventory_sha256')==inventory and assignment.get('writer_epoch')==epoch
         and assignment.get('target_identity')=='xuanjun-s07' and assignment.get('source_writer_resumed') is False
         and assignment.get('scope')==list(UNITS),'WRITER_ASSIGNMENT_SEMANTICS')
 return True

def admit():
 require(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 require(stat.S_IMODE(PERMIT.lstat().st_mode)==0o600,'PRIVATE_ADMISSION')
 p=json.loads(read(PERMIT,2000000));now=int(time.time())
 require(p['action']=='PR99_FINAL_DOMESTIC_START_V1' and p['host']==HOST and p['source_sha256']==sha(read(Path(__file__))), 'EXACT_START_ADMISSION')
 require(type(p['issued_at']) is int and type(p['expires_at']) is int and p['issued_at']<=now<p['expires_at']<=p['issued_at']+7200,'ADMISSION_EXPIRED')
 require(type(p['independent_review_comment_id']) is int and p['independent_review_comment_id']>0,'INDEPENDENT_REVIEW_REQUIRED')
 require(p['release']==str(RELEASE) and p['checkpoint_class']=='FINAL_CANONICAL_CHECKPOINT','NO_PRELIMINARY_DATA')
 require(p['source_writer_fence_receipt_sha256']==sha(read(RELEASE/'source-writer-fence.receipt.json',200000)),'SOURCE_FENCE_PROOF')
 require(p['final_checkpoint_receipt_sha256']==sha(read(RELEASE/'final-checkpoint.receipt.json',200000)),'FINAL_CHECKPOINT_PROOF')
 require(p['canonical_writer_assignment_sha256']==sha(read(RELEASE/'canonical-writer-assignment.json',200000)),'WRITER_ASSIGNMENT_PROOF')
 validate_final_receipts(p,read(RELEASE/'source-writer-fence.receipt.json',200000),
                         read(RELEASE/'final-checkpoint.receipt.json',200000),
                         read(RELEASE/'canonical-writer-assignment.json',200000),now)
 # Root-held admission is supplied by the original independent host authority.
 # This controller never creates those receipts or treats fixture flags as proof.
 account=pwd.getpwnam('xuanjun-s07');group=grp.getgrnam('xuanjun-s07');require(account.pw_uid==p['uid'] and account.pw_gid==group.gr_gid==p['gid'] and p['uid'] not in (0,65534),'PREPARED_DEDICATED_IDENTITY')
 expected=p['file_hashes'];require(100<=len(expected)<=12000,'FINAL_FILE_SET')
 observed={};observed_links={};total=0
 for current,dirs,files in os.walk(ROOT,followlinks=False):
  for name in list(dirs):
   q=Path(current)/name
   if q.is_symlink():
    require(q.relative_to(ROOT).as_posix()=='venv/lib64' and os.readlink(q)=='lib','FINAL_DIRECTORY_LINK')
    observed_links['venv/lib64']='lib';dirs.remove(name)
  for name in files:
   path=Path(current)/name;rel=path.relative_to(ROOT).as_posix()
   if path.is_symlink():
    require(rel in ('venv/bin/python','venv/bin/python3','venv/bin/python3.11','venv/lib64'),'FINAL_LINK')
    require(p['links'].get(rel)==os.readlink(path),'FINAL_LINK_TARGET');observed_links[rel]=os.readlink(path);continue
   raw=read(path,runtime_uid=p['uid'],runtime_gid=p['gid']);total+=len(raw);require(total<=536870912,'FINAL_BYTE_BOUND');observed[rel]=sha(raw)
 require(observed==expected and observed_links==p['links'],'FINAL_EXACT_HASH_SET')
 payload=units('xuanjun-s07');require({n:sha(b) for n,b in payload.items()}==p['unit_hashes'],'EXACT_UNIT_HASHES')
 return p,payload

def health(port):
 c=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
 try:c.request('GET','/healthz');r=c.getresponse();r.read(65536);return r.status
 except (OSError,http.client.HTTPException):return None
 finally:c.close()
def rollback_owned(payload,effect=None):
 # Stop only own, exact-byte units. Data is never restored or deleted, and the
 # source writer is never resumed: its reconciliation authority is external.
 for name,b in payload.items():
  path=SYSTEMD/name
  require(os.path.lexists(path),'ROLLBACK_MISSING_OWNED_UNIT')
  require(read(path)==b,'ROLLBACK_FOREIGN_UNIT')
 for name in payload:
  if (SYSTEMD/name).exists():
   if effect is None:ctl('stop',name)
   else:effect('stop:'+name,lambda name=name:ctl('stop',name))
   require(stopped(name),'ROLLBACK_STILL_RUNNING')
 require(all(health(port) is None for _,port in UNITS.values()),'ROLLBACK_LISTENER_REMAINS')
 return {'status':'OWNED_APPS_STOPPED_DATA_PRESERVED','source_writer_resumed':False,'route_changed':False}
class EffectJournal:
 """Append-only operation records in the ORIGINAL one-use production STATE.
 A missing terminal result means UNKNOWN, including a crash before dispatch.
 This is not a new admission or migration progress ledger.
 """
 def __init__(self):self.sequence=0
 def effect(self,operation,action):
  stem='effect-'+str(self.sequence).zfill(4);self.sequence+=1
  create(STATE/(stem+'.intent.json'),canonical({'operation':operation}))
  try:result=action()
  except KnownEffectFailure:
   create(STATE/(stem+'.result.json'),canonical({'status':'FAILED'}));raise
  except BaseException:
   # Do not serialize raw exceptions, command output or private input.
   raise EffectUnknown('EFFECT_UNKNOWN_QUERY_ONLY_NO_REPLAY') from None
  try:create(STATE/(stem+'.result.json'),canonical({'status':'SUCCEEDED'}))
  except BaseException:raise EffectUnknown('RESULT_WRITE_UNKNOWN_QUERY_ONLY_NO_REPLAY') from None
  return result

def ports_available():
 handles=[]
 try:
  for _,port in UNITS.values():
   sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM);handles.append(sock)
   sock.bind(('127.0.0.1',port))
  return True
 except OSError:return False
 finally:
  for sock in handles:sock.close()

def supervised(name):
 values=dict(l.split('=',1) for l in ctl('show',name,'--property=ActiveState,MainPID','--no-pager').splitlines() if '=' in l)
 return values.get('ActiveState')=='active' and values.get('MainPID','').isdigit() and int(values['MainPID'])>0

def verify_units(payload):
 r=subprocess.run(['/usr/bin/systemd-analyze','verify',*[str(SYSTEMD/n) for n in payload]],capture_output=True,timeout=30)
 if r.returncode!=0:raise KnownEffectFailure('SYSTEMD_VERIFY_FAILED')

def validate_effect_sequence(operations,payload):
 """Validate the only sequence this helper can emit, including nested rollback.
 Read-only recovery never treats a filename sequence as semantic evidence.
 """
 forward=['create:'+n for n in payload]+['daemon-reload']+['start:'+n for n in payload]
 index=0
 while index<len(operations) and operations[index]['operation']!='rollback-owned':
  require(index<len(forward) and operations[index]['operation']==forward[index],'OPERATION_SEMANTIC_SEQUENCE')
  if index:require(operations[index-1]['status']=='SUCCEEDED','OPERATION_AFTER_UNRESOLVED')
  index+=1
 if index==len(operations):return
 if index:require(operations[index-1]['status']!='UNKNOWN','ROLLBACK_AFTER_UNKNOWN')
 rollback=operations[index];children=operations[index+1:]
 created=[row['operation'][len('create:'):] for row in operations[:index]
          if row['operation'].startswith('create:') and row['status']=='SUCCEEDED']
 expected=['stop:'+name for name in created]
 require(len(children)<=len(expected),'ROLLBACK_OPERATION_COUNT')
 for number,row in enumerate(children):
  require(row['operation']==expected[number],'ROLLBACK_OPERATION_SEQUENCE')
  if number:require(children[number-1]['status']=='SUCCEEDED','ROLLBACK_AFTER_UNRESOLVED')
 if rollback['status']=='SUCCEEDED':
  require(len(children)==len(expected) and all(row['status']=='SUCCEEDED' for row in children),'ROLLBACK_RESULT_CONFLICT')

def query_only():
 """Read-only original-state query; never starts, stops, repairs or deletes.
 Does not renew admission. All outputs exclude private data and raw command output.
 """
 require(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 # Require original root-owned private state before opening its existing lock.
 st=STATE.lstat();require(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and stat.S_IMODE(st.st_mode)==0o700,'STATE_IDENTITY')
 fd=os.open(STATE/'lock',os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
  intent=json.loads(read(STATE/'intent.json',2000000))
  payload=units('xuanjun-s07')
  require(intent['source_sha256']==sha(read(Path(__file__))),'QUERY_SOURCE_DRIFT')
  require(intent['unit_hashes']=={n:sha(b) for n,b in payload.items()},'QUERY_UNIT_BINDING')
  operations=[];unknown=False
  paths=sorted(STATE.glob('effect-*.intent.json'))
  require([p.name for p in paths]==['effect-'+str(i).zfill(4)+'.intent.json' for i in range(len(paths))],'OPERATION_SEQUENCE')
  allowed_results={p.name.replace('.intent.json','.result.json') for p in paths}
  require(all(p.name in allowed_results for p in STATE.glob('effect-*.result.json')),'ORPHAN_OPERATION_RESULT')
  for path in paths:
   record=json.loads(read(path,20000));require(type(record) is dict and set(record)=={'operation'},'OPERATION_INTENT_SCHEMA')
   operation=record['operation'];require(type(operation) is str,'OPERATION_NAME_TYPE')
   result_path=path.with_name(path.name.replace('.intent.json','.result.json'))
   status='UNKNOWN'
   if os.path.lexists(result_path):
    record=json.loads(read(result_path,20000));require(type(record) is dict and set(record)=={'status'},'OPERATION_RESULT_SCHEMA')
    status=record['status'];require(status in ('SUCCEEDED','FAILED'),'OPERATION_RESULT')
   unknown|=status=='UNKNOWN';operations.append({'operation':operation,'status':status})
  validate_effect_sequence(operations,payload)
  services={}
  for name,b in payload.items():
   path=SYSTEMD/name
   if os.path.lexists(path):require(read(path)==b,'QUERY_FOREIGN_UNIT')
   services[name]={'unit_present':os.path.lexists(path),'stopped':stopped(name)}
  return {'status':'UNKNOWN_QUERY_ONLY_NO_REPLAY' if unknown else 'OBSERVED_ONLY_NO_RESUME',
          'operations':operations,'services':services,'production_cutover':False,'retry_allowed':False}

def start():
 # A new source hash requires a NEW exact independently issued private admission.
 # Historical approval and stopped-only permits cannot admit these changed bytes.
 p,payload=admit();STATE.mkdir(mode=0o700)
 d=os.open(STATE.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(d)
 finally:os.close(d)
 fd=os.open(STATE/'lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for n in payload:require(not os.path.lexists(SYSTEMD/n) and stopped(n),'UNIT_ALREADY_OWNED')
  require(ports_available() and all(health(port) is None for _,port in UNITS.values()),'PORT_ALREADY_OCCUPIED')
  create(STATE/'intent.json',canonical({'permit_sha256':sha(read(PERMIT)),'source_sha256':sha(read(Path(__file__))),
      'unit_hashes':p['unit_hashes'],'source_writer_fence_receipt_sha256':p['source_writer_fence_receipt_sha256']}))
  created={};journal=EffectJournal()
  try:
   for n,b in payload.items():
    journal.effect('create:'+n,lambda n=n,b=b:create(SYSTEMD/n,b,0o644));created[n]=b
   journal.effect('daemon-reload',lambda:ctl('daemon-reload'))
   verify_units(payload)
   require(int(time.time())<p['expires_at'],'ADMISSION_EXPIRED_BEFORE_START')
   require(admit()[0]==p,'PRESTART_DRIFT')
   for n in payload:
    require(int(time.time())<p['expires_at'],'ADMISSION_EXPIRED_BEFORE_START')
    journal.effect('start:'+n,lambda n=n:ctl('start',n))
   deadline=time.monotonic()+30;statuses={}
   while time.monotonic()<deadline:
    statuses={role:health(port) for role,(_,port) in UNITS.items()}
    if all(v==200 for v in statuses.values()) and all(supervised(n) for n in payload):break
    time.sleep(.5)
   require(set(statuses)==set(UNITS) and all(v==200 for v in statuses.values()) and all(supervised(n) for n in payload),'START_HEALTH_OR_SUPERVISION_FAILED')
   result={'status':'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER','health':statuses,'services_installed':True,'production_cutover':False,'upstream_auth_acceptance':'PENDING','final_data_restored_on_failure':False}
   create(STATE/'receipt.json',canonical(result));return result
  except EffectUnknown:
   # In-flight start/stop/daemon actions must not race a compensating command.
   create(STATE/'failure.json',canonical({'status':'EFFECT_UNKNOWN_QUERY_ONLY_NO_REPLAY','retry_allowed':False}));raise
  except BaseException:
   # Known failure: journal containment too. Existing rollback only touches exact
   # owned unit bytes, never resumes a source writer or restores data.
   try:r=journal.effect('rollback-owned',lambda:rollback_owned(created,effect=journal.effect))
   except BaseException:r={'status':'ROLLBACK_UNKNOWN_PRESERVE_NO_RETRY'}
   create(STATE/'failure.json',canonical(r));raise

if __name__=='__main__':
 import sys
 os.umask(0o077)
 if sys.argv[1:]==['query-only']:print(json.dumps(query_only(),sort_keys=True))
 else:raise SystemExit('REVIEW_ONLY_CHANGED_HELPER_NO_PRODUCTION_ENTRY')
