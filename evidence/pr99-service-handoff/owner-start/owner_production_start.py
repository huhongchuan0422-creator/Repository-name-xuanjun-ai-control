"""PR99 Owner-direct domestic production entry. No reviewer or permit wait.
Requires a real final checkpoint, prepared dedicated identity, and root-held exact technical start inputs. Never starts from the preliminary r1/r2 copied data. No route edits.
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
INPUTS=Path('/etc/xuanjun-pr99/domestic-final.start-inputs.json')
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
 if r.returncode!=0:
  values=dict(l.split('=',1) for l in r.stdout.decode('utf-8','strict').splitlines() if '=' in l)
  missing=(len(args)==4 and args[0]=='show' and args[-1]=='--no-pager' and r.returncode==1 and values.get('ActiveState')=='inactive' and values.get('MainPID')=='0' and values.get('LoadState','not-found')=='not-found')
  if not missing:raise KnownEffectFailure('SYSTEMCTL_FAILED')
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
 # These technical proof bytes must match the exact root-held start inputs.
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


def load_final_receipts(p,now):
 # Read each exact proof once; match the source HeldProof capacities.
 # Large complete manifests are allowed; truncation and drift remain HOLD.
 fence=read(RELEASE/'source-writer-fence.receipt.json',16384)
 checkpoint=read(RELEASE/'final-checkpoint.receipt.json',2097152)
 assignment=read(RELEASE/'canonical-writer-assignment.json',16384)
 return validate_final_receipts(p,fence,checkpoint,assignment,now)

def admit():
 require(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 require(stat.S_IMODE(INPUTS.lstat().st_mode)==0o600,'PRIVATE_ADMISSION')
 p=json.loads(read(INPUTS,2000000));now=int(time.time())
 require(p['action']=='PR99_FINAL_DOMESTIC_START_V1' and p['host']==HOST and p['source_sha256']==sha(read(Path(__file__))), 'EXACT_START_ADMISSION')
 require(type(p['issued_at']) is int and type(p['expires_at']) is int and p['issued_at']<=now<p['expires_at']<=p['issued_at']+7200,'ADMISSION_EXPIRED')
 validate_owner_authority(p)
 require(p['release']==str(RELEASE) and p['checkpoint_class']=='FINAL_CANONICAL_CHECKPOINT','NO_PRELIMINARY_DATA')
 load_final_receipts(p,now)
 # Owner removed the review/permit wait; the remaining inputs bind actual data and effects.
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
 if operations and operations[0]['operation']=='retire-stopped-candidate':
  require(operations[0]['status']=='SUCCEEDED' or len(operations)==1,'OPERATION_AFTER_UNRESOLVED_RETIREMENT')
  operations=operations[1:]
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

def _start():
 # Owner authority is explicit; exact final files/Fence/assignment remain required facts.
 p,payload=admit();candidate=inspect_stopped_candidate();STATE.mkdir(mode=0o700)
 d=os.open(STATE.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(d)
 finally:os.close(d)
 fd=os.open(STATE/'lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  require(inspect_stopped_candidate()['kind']==candidate['kind'],'CANDIDATE_CHANGED')
  require(ports_available() and all(health(port) is None for _,port in UNITS.values()),'PORT_ALREADY_OCCUPIED')
  create(STATE/'intent.json',canonical({'start_inputs_sha256':sha(read(INPUTS)),'source_sha256':sha(read(Path(__file__))),
      'unit_hashes':p['unit_hashes'],'source_writer_fence_receipt_sha256':p['source_writer_fence_receipt_sha256']}))
  created={};journal=EffectJournal()
  journal.effect('retire-stopped-candidate',lambda:retire_stopped_candidate(p,candidate))
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


FROZEN_STOPPED='"""PR99 exact-byte, stopped-unit installation and conflict-safe rollback.\nNo start/enable/restart, route edit, data restore, user creation or cloud call.\nHost execution requires a separate root-held, independently issued admission.\n"""\nimport argparse\nimport fcntl\nimport hashlib\nimport json\nimport os\nimport re\nimport stat\nimport subprocess\nimport time\nfrom pathlib import Path\n\nHOST = \'iZvt5t8tlrm8oiZ\'\nRELEASE = \'/opt/xuanjun-migration-s07/releases/domestic-r2\'\nSTATE = \'/var/lib/xuanjun-pr99-s09-stopped-install-v1\'\nADMISSION = \'/etc/xuanjun-pr99/s09-stopped-install.admission.json\'\nNAMES = tuple(\'xuanjun-pr99-domestic-\' + r + \'.service\' for r in (\'portal\', \'contact\', \'customer-service\'))\nORIGINAL = (\'secure-secrets-portal.service\', \'xuanjun-wecom-customer-contact.service\', \'xuanjun-wecom-customer-service.service\')\nPROTECTED = ORIGINAL + (\'provider-neutral-domestic-bridge.service\', \'winctl.service\', \'nginx.service\')\n\n\ndef require(ok, code):\n    if not ok:\n        raise RuntimeError(code)\n\n\ndef digest(data):\n    return hashlib.sha256(data).hexdigest()\n\n\ndef encode(value):\n    return (json.dumps(value, sort_keys=True, indent=2) + \'\\n\').encode()\n\n\ndef read_regular(path, limit=100000, private=False):\n    path = Path(path)\n    for parent in reversed(path.parents):\n        require(not parent.is_symlink(), \'SYMLINK_PARENT\')\n    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)\n    try:\n        before = os.fstat(fd)\n        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1, \'FILE_IDENTITY\')\n        require(not before.st_mode & 0o022, \'WRITABLE_INPUT\')\n        if private:\n            require(not before.st_mode & 0o077, \'PRIVATE_INPUT_MODE\')\n        data = os.read(fd, limit + 1)\n        after = os.fstat(fd)\n        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)\n        require(len(data) <= limit and identity(before) == identity(after), \'INPUT_CHANGED_OR_OVERSIZE\')\n        return data\n    finally:\n        os.close(fd)\n\n\ndef write_exclusive(path, data, mode=0o600):\n    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)\n    try:\n        with os.fdopen(fd, \'wb\', closefd=False) as stream:\n            stream.write(data)\n            stream.flush()\n            os.fsync(fd)\n    finally:\n        os.close(fd)\n    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)\n    try:\n        os.fsync(directory)\n    finally:\n        os.close(directory)\n\n\ndef unit_bytes():\n    commands = (\n        \'scripts/secure_secrets_portal_server.py serve --host 127.0.0.1 --port 18080\',\n        \'-m ai_service.wecom_customer_contact_service\',\n        \'-m ai_service.wecom_customer_service\',\n    )\n    result = {}\n    for name, command in zip(NAMES, commands):\n        # Quarantine is mandatory. These units cannot reach the real bridge.\n        result[name] = (\'\'\'[Unit]\nDescription=PR99 quarantined domestic candidate\nConditionPathExists={release}/callback-restart-acceptance-v1/receipt.json\n\n[Service]\nType=simple\nUser=65534\nGroup=65534\nRootDirectory={release}/rootfs\nWorkingDirectory=/opt/trading-system\nExecStart=/venv/bin/python {command}\nEnvironment=PYTHONPATH=/opt/trading-system PYTHONDONTWRITEBYTECODE=1\nEnvironment=WECOM_CONTACT_HOST=127.0.0.1 WECOM_CONTACT_PORT=18781\nEnvironment=WECOM_KF_HOST=127.0.0.1 WECOM_KF_PORT=18780\nBindReadOnlyPaths=/usr /lib /lib64\nPrivateDevices=yes\nPrivateNetwork=yes\nPrivateTmp=yes\nProtectSystem=strict\nReadWritePaths=/opt/trading-system/runtime /home /tmp\nNoNewPrivileges=yes\nCapabilityBoundingSet=\nRestrictSUIDSGID=yes\nUMask=0077\nRestart=no\nTimeoutStopSec=15\nKillMode=control-group\nStandardOutput=null\nStandardError=null\n\'\'\'.format(release=RELEASE, command=command)).encode()\n    return result\n\n\ndef manifest():\n    return {\'schema\': 1, \'action\': \'INSTALL_STOPPED_QUARANTINE_ONLY\', \'host\': HOST,\n            \'release\': RELEASE, \'unit_hashes\': {n: digest(b) for n, b in unit_bytes().items()},\n            \'activation_supported\': False, \'production_cutover\': False}\n\n\ndef systemctl(*args):\n    result = subprocess.run([\'/usr/bin/systemctl\', *args], capture_output=True, timeout=20)\n    require(result.returncode == 0, \'SYSTEMCTL_FAILED_PRESERVE\')\n    return result.stdout.decode()\n\n\ndef snapshot():\n    result = {u: systemctl(\'show\', u, \'--property=LoadState,ActiveState,SubState,MainPID,FragmentPath\', \'--no-pager\') for u in PROTECTED}\n    for name in (\'/var/www/wenwenwenyiyiyi.work/current\', \'/opt/trading-system\'):\n        p = Path(name)\n        if p.is_symlink():\n            result[name] = {\'link\': os.readlink(p)}\n        elif p.exists():\n            s = p.stat()\n            result[name] = {\'dev\': s.st_dev, \'ino\': s.st_ino, \'mode\': s.st_mode, \'uid\': s.st_uid, \'gid\': s.st_gid}\n        else:\n            result[name] = None\n    return result\n\n\ndef stopped(name):\n    value = systemctl(\'show\', name, \'--property=ActiveState,MainPID\', \'--no-pager\')\n    fields = dict(line.split(\'=\', 1) for line in value.splitlines() if \'=\' in line)\n    return fields.get(\'MainPID\') == \'0\' and fields.get(\'ActiveState\') in (\'inactive\', \'failed\')\n\n\ndef admission(action, source):\n    raw = read_regular(ADMISSION, private=True)\n    permit = json.loads(raw)\n    require(permit[\'schema\'] == 1 and permit[\'host\'] == HOST, \'ADMISSION_HOST\')\n    require(permit[\'action\'] == action and permit[\'source_sha256\'] == digest(source), \'ADMISSION_ACTION_SOURCE\')\n    require(permit[\'manifest_sha256\'] == digest(encode(manifest())), \'ADMISSION_MANIFEST\')\n    now = int(time.time())\n    require(type(permit[\'issued_at\']) is int and type(permit[\'expires_at\']) is int, \'ADMISSION_TIME_TYPE\')\n    require(permit[\'issued_at\'] <= now < permit[\'expires_at\'] <= permit[\'issued_at\'] + 7200, \'ADMISSION_EXPIRED\')\n    require(re.fullmatch(r\'[a-zA-Z0-9_-]{16,80}\', permit[\'nonce\']) is not None, \'ADMISSION_NONCE\')\n    require(type(permit[\'independent_review_comment_id\']) is int and permit[\'independent_review_comment_id\'] > 0, \'INDEPENDENT_REVIEW_REFERENCE\')\n    # A local file is not itself independent review evidence. Its provisioning\n    # through the original reviewed authority is a separate mandatory host gate.\n    return permit, digest(raw)\n\n\ndef install(units_dir, state, permit, permit_hash):\n    units = unit_bytes()\n    before = snapshot()\n    for original in ORIGINAL:\n        require(\'LoadState=not-found\' in before[original], \'ORIGINAL_UNIT_PRESENT\')\n    for name in NAMES:\n        require(not os.path.lexists(units_dir / name), \'TARGET_UNIT_PRESENT\')\n        require(stopped(name), \'TARGET_NOT_STOPPED\')\n    receipt = json.loads(read_regular(Path(RELEASE) / \'callback-restart-acceptance-v1/receipt.json\', private=True))\n    require(receipt[\'status\'] == \'R2_CALLBACK_REJECTION_RESTART_CLEANUP_PASS_NOT_PRODUCTION\' and receipt[\'application_processes_stopped\'] is True, \'COPY_ACCEPTANCE_MISSING\')\n    write_exclusive(state / \'before.json\', encode(before))\n    write_exclusive(state / \'intent.json\', encode({\'permit_sha256\': permit_hash, \'nonce\': permit[\'nonce\'], \'manifest\': manifest()}))\n    created = []\n    try:\n        for name, data in units.items():\n            write_exclusive(units_dir / name, data, 0o644)\n            created.append(name)\n            write_exclusive(state / (name + \'.created\'), encode({\'sha256\': digest(data)}))\n        systemctl(\'daemon-reload\')\n        require(all(stopped(n) for n in NAMES), \'UNIT_NOT_STOPPED\')\n        require(snapshot() == before, \'PROTECTED_CHANGED\')\n        write_exclusive(state / \'receipt.json\', encode({\'status\': \'QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION\', \'manifest\': manifest(), \'protected_state_unchanged\': True, \'starts\': 0, \'enables\': 0}))\n    except BaseException:\n        # Never delete an unrecognised or running unit, even after partial failure.\n        write_exclusive(state / \'failure.json\', encode({\'status\': \'HOLD_PRESERVE\', \'created\': created}))\n        raise\n\n\ndef rollback(units_dir, state, permit, permit_hash):\n    intent = json.loads(read_regular(state / \'intent.json\', private=True))\n    require(intent[\'manifest\'] == manifest(), \'ROLLBACK_MANIFEST\')\n    require(not (state / \'rollback.intent.json\').exists(), \'ROLLBACK_ALREADY_CONSUMED\')\n    before = snapshot()\n    targets = []\n    for name, data in unit_bytes().items():\n        p = units_dir / name\n        if os.path.lexists(p):\n            require(read_regular(p) == data and stopped(name), \'ROLLBACK_CONFLICT_OR_RUNNING\')\n            # Only units whose transaction intent predates creation may be removed.\n            marker = json.loads(read_regular(state / (name + \'.created\'), private=True))\n            require(marker[\'sha256\'] == digest(data), \'ROLLBACK_OWNERSHIP\')\n            targets.append(name)\n    write_exclusive(state / \'rollback.intent.json\', encode({\'nonce\': permit[\'nonce\'], \'permit_sha256\': permit_hash, \'targets\': targets}))\n    for name in targets:\n        require(read_regular(units_dir / name) == unit_bytes()[name] and stopped(name), \'ROLLBACK_CHANGED\')\n        (units_dir / name).unlink()\n    systemctl(\'daemon-reload\')\n    require(snapshot() == before, \'PROTECTED_CHANGED\')\n    write_exclusive(state / \'rollback.receipt.json\', encode({\'status\': \'OWNED_STOPPED_UNITS_REMOVED\', \'removed\': targets, \'production_cutover\': False}))\n\n\ndef main():\n    parser = argparse.ArgumentParser()\n    parser.add_argument(\'action\', choices=(\'manifest\', \'install-stopped\', \'rollback-stopped\'))\n    args = parser.parse_args()\n    if args.action == \'manifest\':\n        print(encode(manifest()).decode(), end=\'\')\n        return\n    require(os.geteuid() == 0 and os.uname().nodename == HOST, \'HOST_ROOT\')\n    os.umask(0o077)\n    source = read_regular(Path(__file__), 100000)\n    permit, permit_hash = admission(args.action, source)\n    state = Path(STATE)\n    if args.action == \'install-stopped\':\n        state.mkdir(mode=0o700)  # one attempt; never replay or merge state\n    require(stat.S_IMODE(state.lstat().st_mode) == 0o700 and state.lstat().st_uid == 0 and not state.is_symlink(), \'STATE_IDENTITY\')\n    lock = os.open(state / \'lock\', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)\n    try:\n        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)\n        if args.action == \'install-stopped\':\n            install(Path(\'/etc/systemd/system\'), state, permit, permit_hash)\n        else:\n            rollback(Path(\'/etc/systemd/system\'), state, permit, permit_hash)\n    finally:\n        os.close(lock)\n\n\nif __name__ == \'__main__\':\n    main()\n'

OWNER_AUTHORITY={'mode':'OWNER_DIRECT','instruction_at':'2026-10-19T00:29:13+08:00','scope':'PR99_DOMESTIC_MIGRATION'}

def validate_owner_authority(p):
 require(p.get('owner_authority')==OWNER_AUTHORITY,'OWNER_AUTHORITY_BINDING')
 require(type(p.get('nonce'))is str and re.fullmatch('[A-Za-z0-9_-]{16,80}',p['nonce']),'OWNER_INPUT_NONCE')
 # A reviewer ID cannot replace Owner authority and is not required.
 return True

def stopped_library():
 require(sha(FROZEN_STOPPED.encode())=='99225aacc11cae6dc9d190015c95c9883e13d8e2691da864fb026f8afdfee315','ORIGINAL_STOPPED_SOURCE')
 n={'__name__':'original_stopped_definitions'}
 exec(compile(FROZEN_STOPPED,'original_stopped_definitions','exec'),n)
 n['PROTECTED']=tuple(sorted(set(n['PROTECTED'])|{'windows-interaction-http.service'}))
 n['systemctl']=ctl
 return n

def inspect_stopped_candidate():
 n=stopped_library();names=n['NAMES'];state=Path(n['STATE'])
 present=[os.path.lexists(SYSTEMD/name) for name in names]
 if not any(present):
  if os.path.lexists(state):
   # Previously installed candidates may only be absent after the exact
   # original terminal rollback; unexplained deletion is never adopted.
   receipt=json.loads(n['read_regular'](state/'rollback.receipt.json',private=True))
   require(receipt.get('status')=='OWNED_STOPPED_UNITS_REMOVED' and set(receipt.get('removed',[]))==set(names),'ORIGINAL_REMOVAL_UNKNOWN')
  require(all(stopped(name) for name in names),'TARGET_STILL_RUNNING')
  return {'kind':'NO_CANDIDATE','library':n}
 require(all(present),'PARTIAL_OR_FOREIGN_CANDIDATE')
 receipt=json.loads(n['read_regular'](state/'receipt.json',private=True))
 require(receipt.get('status')=='QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION' and receipt.get('manifest')==n['manifest']() and receipt.get('starts')==receipt.get('enables')==0,'ORIGINAL_STOPPED_RECEIPT')
 require(not os.path.lexists(state/'rollback.intent.json'),'ORIGINAL_RETIREMENT_ALREADY_CONSUMED')
 for name,data in n['unit_bytes']().items():
  require(n['read_regular'](SYSTEMD/name)==data and stopped(name),'FOREIGN_OR_RUNNING_CANDIDATE')
  marker=json.loads(n['read_regular'](state/(name+'.created'),private=True))
  require(marker.get('sha256')==n['digest'](data),'ORIGINAL_CANDIDATE_OWNERSHIP')
 return {'kind':'EXACT_OWNED_STOPPED_CANDIDATE','library':n}

def retire_stopped_candidate(p,candidate):
 require(inspect_stopped_candidate()['kind']==candidate['kind'],'CANDIDATE_CHANGED_BEFORE_RETIREMENT')
 if candidate['kind']=='NO_CANDIDATE':return {'status':'NO_CANDIDATE_TO_RETIRE'}
 require(candidate['kind']=='EXACT_OWNED_STOPPED_CANDIDATE','CANDIDATE_KIND')
 n=candidate['library'];state=Path(n['STATE'])
 # The original rollback removes ONLY its exact stopped bytes and records
 # its own before/after protected snapshots. It does not stop any service.
 n['rollback'](SYSTEMD,state,{'nonce':p['nonce']},sha(canonical(p['owner_authority'])))
 receipt=json.loads(n['read_regular'](state/'rollback.receipt.json',private=True))
 require(receipt.get('status')=='OWNED_STOPPED_UNITS_REMOVED' and set(receipt.get('removed',[]))==set(n['NAMES']),'ORIGINAL_RETIREMENT_TERMINAL_RECEIPT')
 return receipt

def start():
 from contextlib import ExitStack
 require(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 n=stopped_library();state=Path(n['STATE'])
 # Borrow the exact existing stopped-install lock across final admission,
 # removal and production installation. No second candidate claim is made.
 with ExitStack() as stack:
  if os.path.lexists(state):
   s=state.lstat();require(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'ORIGINAL_STOPPED_STATE')
   fd=os.open(state/'lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
   stack.callback(os.close,fd)
   s=os.fstat(fd);require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'ORIGINAL_STOPPED_LOCK')
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  return _start()

if __name__=='__main__':
 import sys
 os.umask(0o077)
 if sys.argv[1:]==['query-only']:result=query_only()
 elif sys.argv[1:]==['start']:result=start()
 else:raise SystemExit('EXPECTED_START_OR_QUERY_ONLY')
 print(json.dumps(result,sort_keys=True))
