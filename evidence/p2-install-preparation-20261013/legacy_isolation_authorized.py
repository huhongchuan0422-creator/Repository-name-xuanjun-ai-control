"""Owner authorized isolation only: PR17 scope6149913707. No install/fence."""
import os,sys,socket,stat,json,hashlib,subprocess,fcntl,time
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
ROOT='/tmp/p2pkg-38420216343-1/xuanjun-p2-package'
def read(p,mode=0o600):
 assert os.path.realpath(p)==p
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());r=f.read(1048577)
  assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and (stat.S_IMODE(s.st_mode)==mode if mode is not None else not s.st_mode&0o022) and len(r)<=1048576
 return r
raw=read(BASE+'/plan-p2pkg-38420216343-1/protected-core-install-plan.json')
assert hashlib.sha256(raw).hexdigest()=='6a7789a023d0cbb265663275ee7442fdd026eaaee0fc4ee4a0f237ec5a62e970'
plan=json.loads(raw.decode())
manifest=read(ROOT+'/deploy/integration-manifest.json',None)
assert hashlib.sha256(manifest).hexdigest()=='2b49066f37742dedd41657fb445c91f4204fd4a2a257f921dd9fd514e5b25f0e'
for rel,digest in json.loads(manifest.decode())['files'].items():
 assert rel and not rel.startswith('/') and '..' not in rel.split('/')
 p=ROOT+'/'+rel
 assert os.path.realpath(p)==p
 with open(p,'rb') as f:
  s=os.fstat(f.fileno());assert s.st_uid==0 and not s.st_mode&0o022
  assert hashlib.sha256(f.read()).hexdigest()==digest
sys.path.insert(0,ROOT+'/stage1')
from legacy_host_adapter import LegacyHostAdapter
from ledger_cutover_transaction import _atomic_receipt
d=BASE+'/legacy-isolation-'+plan['transaction_id']
# Stable transaction path and existing-journal refusal prevent duplicate effects.
os.mkdir(d,0o700)
lock=os.open(BASE+'/legacy-isolation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
a=LegacyHostAdapter(d);receipt=d+'/owner-isolation-receipt.json'
value={'schema':1,'state':'PRECHECK','authorization_scope':'PR17:6149913707; explicit Owner approval in Work thread 2026-10-14','core_plan_sha256':hashlib.sha256(raw).hexdigest(),'transaction_id':plan['transaction_id'],'install':False,'writer_admission':False,'fence_mutation':False,'ledger_migration':False,'model_calls':0}
try:
 a.preflight(plan['cutover'])
 states={}
 for unit in sorted(plan['cutover']['legacy_bindings']):
  r=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=Id,ActiveState,SubState,MainPID,ControlGroup,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
  assert r.returncode==0
  states[unit]=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
  assert states[unit]['ActiveState']=='active' and states[unit]['SubState']=='running' and int(states[unit]['MainPID'])>1
  with open('/proc/'+states[unit]['MainPID']+'/status') as f:status=f.read()
  assert next(x for x in status.splitlines() if x.startswith('Uid:')).split()[1:]==['1002']*4
 value['prior_unit_states']=states;value['state']='STOP_AND_MASK_INTENT';_atomic_receipt(receipt,value)
 a.stop_and_inhibit(plan['cutover']['legacy_bindings'])
 value['state']='STOP_AND_MASK_RETURNED';_atomic_receipt(receipt,value)
 value['adapter_quiescence']=a.measure_quiescence(plan['cutover']['legacy_bindings'])
 after={}
 for unit in sorted(states):
  r=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=Id,ActiveState,SubState,MainPID,ControlGroup,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
  assert r.returncode==0
  x=dict(line.split('=',1) for line in r.stdout.decode().splitlines() if '=' in line)
  assert x['ActiveState']=='inactive' and x['SubState']=='dead' and x['MainPID']=='0' and x['UnitFileState']=='masked'
  root='/sys/fs/cgroup/systemd/system.slice/'+unit;members=set()
  for directory,children,files in os.walk(root,followlinks=False):
   if 'cgroup.procs' in files:
    with open(directory+'/cgroup.procs') as f:members.update(f.read().split())
  assert not members
  x['all_cgroup_pids']=[];after[unit]=x
 db=plan['cutover']['source'];holders=[];races=0
 for name in os.listdir('/proc'):
  if not name.isdigit():continue
  try:files=os.listdir('/proc/'+name+'/fd')
  except FileNotFoundError:races+=1;continue
  for n in files:
   try:target=os.readlink('/proc/'+name+'/fd/'+n)
   except FileNotFoundError:races+=1;continue
   if target.replace(' (deleted)','') in (db,db+'-wal',db+'-shm'):holders.append(int(name))
 assert not holders
 value.update(state='AUTHORIZED_OLD_SERVICES_ISOLATED',after_unit_states=after,old_database_handle_holders=[],process_races=races,other_writers='UNKNOWN_RECONCILIATION_REQUIRED',fence_status='NOT_READ_NOT_CHANGED')
 _atomic_receipt(receipt,value)
except Exception as e:
 value['state']='HOLD_ISOLATION';value['error_type']=type(e).__name__;value['error']=str(e)[:256]
 _atomic_receipt(receipt,value);print(json.dumps(value,sort_keys=True));raise
print(json.dumps(value,sort_keys=True))
print('ISOLATION_RECEIPT_PATH='+receipt)
print('ISOLATION_RECEIPT_SHA256='+hashlib.sha256(read(receipt)).hexdigest())
print('INSTALL=NO; NEW_WRITER=NO; FENCE_MUTATION=NO; AUTO_RESTART=NO')
