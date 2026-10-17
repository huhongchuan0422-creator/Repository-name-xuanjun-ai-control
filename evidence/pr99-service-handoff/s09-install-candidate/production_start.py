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
import subprocess
import time
from pathlib import Path

HOST='iZvt5t8tlrm8oiZ'
RELEASE=Path('/opt/xuanjun-migration-s07/releases/domestic-final-v1')
ROOT=RELEASE/'rootfs'
PERMIT=Path('/etc/xuanjun-pr99/s09-production-start.admission.json')
STATE=Path('/var/lib/xuanjun-pr99-s09-production-start-v1')
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
def ctl(*args):
 r=subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,timeout=20);require(r.returncode==0,'SYSTEMCTL_FAILED');return r.stdout.decode()
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
def rollback_owned(payload):
 # Stop only own, exact-byte units. Data is never restored or deleted, and the
 # source writer is never resumed: its reconciliation authority is external.
 for name,b in payload.items():
  path=Path('/etc/systemd/system')/name
  if os.path.lexists(path):require(read(path)==b,'ROLLBACK_FOREIGN_UNIT')
 for name in payload:
  if (Path('/etc/systemd/system')/name).exists():ctl('stop',name);require(stopped(name),'ROLLBACK_STILL_RUNNING')
 require(all(health(port) is None for _,port in UNITS.values()),'ROLLBACK_LISTENER_REMAINS')
 return {'status':'OWNED_APPS_STOPPED_DATA_PRESERVED','source_writer_resumed':False,'route_changed':False}
def start():
 p,payload=admit();STATE.mkdir(mode=0o700)
 fd=os.open(STATE/'lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for n in payload:require(not os.path.lexists(Path('/etc/systemd/system')/n) and stopped(n),'UNIT_ALREADY_OWNED')
  require(all(health(port) is None for _,port in UNITS.values()),'PORT_ALREADY_OCCUPIED')
  create(STATE/'intent.json',canonical({'permit_sha256':sha(read(PERMIT)),'unit_hashes':p['unit_hashes'],'source_writer_fence_receipt_sha256':p['source_writer_fence_receipt_sha256']}))
  created={}
  try:
   for n,b in payload.items():create(Path('/etc/systemd/system')/n,b,0o644);created[n]=b
   ctl('daemon-reload')
   subprocess.run(['/usr/bin/systemd-analyze','verify',*[str(Path('/etc/systemd/system')/n) for n in payload]],check=True,capture_output=True,timeout=30)
   require(int(time.time())<p['expires_at'],'ADMISSION_EXPIRED_BEFORE_START')
   # Re-validate authority and final bytes immediately before the first start.
   require(admit()[0]==p,'PRESTART_DRIFT')
   for n in payload:ctl('start',n)
   deadline=time.monotonic()+30
   while time.monotonic()<deadline:
    statuses={role:health(port) for role,(_,port) in UNITS.items()}
    if all(v==200 for v in statuses.values()):break
    time.sleep(.5)
   require(all(v==200 for v in statuses.values()),'START_HEALTH_FAILED')
   result={'status':'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER','health':statuses,'services_installed':True,'production_cutover':False,'upstream_auth_acceptance':'PENDING','final_data_restored_on_failure':False}
   create(STATE/'receipt.json',canonical(result));return result
  except BaseException:
   # A stop/ownership failure must remain explicit, not be masked as rollback PASS.
   try:r=rollback_owned(created)
   except BaseException:r={'status':'ROLLBACK_UNKNOWN_PRESERVE_NO_RETRY'}
   create(STATE/'failure.json',canonical(r));raise
if __name__=='__main__':
 os.umask(0o077);print(json.dumps(start(),sort_keys=True))
