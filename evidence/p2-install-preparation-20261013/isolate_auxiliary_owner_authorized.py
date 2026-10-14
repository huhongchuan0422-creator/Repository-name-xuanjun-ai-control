"""Explicit Owner-service isolation scope PR17:6151035332; no install."""
import os,sys,json,hashlib,stat,socket,subprocess,tempfile,fcntl
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
B='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
T='c529c379-9341-4510-8384-fc6be1e412e5';OLD=B+'/legacy-isolation-'+T
UNITS={'xuanjun-uk-owner-callback.service':{'sha256':'22928c11c1e4e3e56b2d17b9d8f8f292f705b52df41072c01a6cd767cae5fbc0','pid':'43049'},
'xuanjun-uk-owner-dashboard.service':{'sha256':'bd7b554a396951020d4d7216a7926f12afc26da53af87814d308439c1a954f61','pid':'66783'}}
CODE={'/home/xuanjun_dev/uk-stage1-minimal/owner-callback/serve_uk_callback.py':'4aa947db9ac37e445ec9e90d5f206eaeb8b6fa34406e21df825ca549ff906eb2','/home/xuanjun_dev/uk-stage1-minimal/owner-callback/uk_owner_callback.py':'351fd227e18304d44b8d95cf6727685ba08b828ea2cb60a71fa1947855b9bf0e','/opt/xuanjun-uk-control/release/owner_dashboard.py':'4c61b2fe8ccbdbdbeba70976580526f20d9dff8eb63d3f6d5739b499715b5faf'}
def h(p):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode)
  q=hashlib.sha256()
  for r in iter(lambda:f.read(65536),b''):q.update(r)
 return q.hexdigest()
def show(unit):
 r=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=Id,LoadState,FragmentPath,ActiveState,SubState,MainPID,ControlGroup,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 assert r.returncode==0
 return dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
def members(unit):
 root='/sys/fs/cgroup/systemd/system.slice/'+unit;out=set()
 for d,c,files in os.walk(root,followlinks=False):
  if 'cgroup.procs' in files:
   with open(d+'/cgroup.procs') as f:out.update(int(x) for x in f.read(65537).split())
 return sorted(out)
lock=os.open(B+'/legacy-isolation.lock',os.O_RDWR|os.O_NOFOLLOW)
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert h(OLD+'/owner-isolation-receipt.json')=='70d8e244f7f72c15a16299b9eef19670cd7cdee452b1913d864af93c2f4824bc'
assert h(OLD+'/legacy-units.json')=='fe57912b31e42665a895a1e0d7c64fde5cebaff6a99394d0183a3fe3d95ab7c1'
original_hashes={n:h(OLD+'/'+n) for n in os.listdir(OLD) if os.path.isfile(OLD+'/'+n)}
for unit in ('xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service'):
 x=show(unit);assert x['MainPID']=='0' and x['ActiveState']=='inactive' and x['UnitFileState']=='masked' and not members(unit)
for p,digest in CODE.items():assert os.path.realpath(p)==p and h(p)==digest
db='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite';db_before=h(db)
assert db_before=='a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60'
states={};payloads={}
for unit,wanted in UNITS.items():
 path='/etc/systemd/system/'+unit
 assert os.path.realpath(path)==path and h(path)==wanted['sha256']
 s=os.lstat(path);assert s.st_uid==0 and s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o644 and s.st_nlink==1
 x=show(unit);assert x['Id']==unit and x['LoadState']=='loaded' and x['FragmentPath']==path and x['ActiveState']=='active' and x['SubState']=='running' and x['MainPID']==wanted['pid'] and x['UnitFileState']=='enabled' and x['ControlGroup']=='/system.slice/'+unit
 x['all_cgroup_pids']=members(unit);assert x['all_cgroup_pids']==[int(wanted['pid'])]
 for pid in x['all_cgroup_pids']:
  with open('/proc/'+str(pid)+'/status') as f:status=f.read(65537)
  assert next(y for y in status.splitlines() if y.startswith('Uid:')).split()[1:]==['1002']*4
  assert os.path.realpath('/proc/'+str(pid)+'/exe')=='/usr/libexec/platform-python3.6'
 with open(path,'rb') as f:payloads[unit]=f.read(65537)
 states[unit]=x
D=OLD+'/auxiliary-owner';os.mkdir(D,0o700)
def atomic(v):
 fd,p=tempfile.mkstemp(prefix='.intent-',dir=D)
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'wb') as f:f.write((json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode());f.flush();os.fsync(f.fileno())
  os.replace(p,D+'/auxiliary-isolation-receipt.json')
  fd=os.open(D,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 finally:
  if os.path.exists(p):os.unlink(p)
value={'schema':1,'transaction_id':T,'authorization':'PR17:6151035332 plus explicit Work-thread approval','state':'BACKUPS_READY','before':states,'unit_hashes':{u:x['sha256'] for u,x in UNITS.items()},'code_hashes':CODE,'database_before_sha256':db_before,'install':False,'fence_mutation':False,'writer_admission':False,'model_calls':0}
for unit,data in payloads.items():
 fd=os.open(D+'/'+unit+'.backup',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
atomic(value)
try:
 for p,digest in CODE.items():assert h(p)==digest
 for unit,x in UNITS.items():assert h('/etc/systemd/system/'+unit)==x['sha256']
 value['state']='STOP_INTENT';atomic(value)
 r=subprocess.run(['/usr/bin/systemctl','stop']+sorted(UNITS),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45);assert r.returncode==0
 value['state']='MASK_INTENT';atomic(value)
 for unit,x in UNITS.items():
  path='/etc/systemd/system/'+unit;assert h(path)==x['sha256']
  assert not os.path.lexists(path+'.p2-aux-mask')
  os.symlink('/dev/null',path+'.p2-aux-mask');os.replace(path+'.p2-aux-mask',path)
  fd=os.open(os.path.dirname(path),os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 r=subprocess.run(['/usr/bin/systemctl','daemon-reload'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30);assert r.returncode==0
 after={}
 for unit in UNITS:
  x=show(unit);x['all_cgroup_pids']=members(unit)
  assert x['ActiveState']=='inactive' and x['SubState']=='dead' and x['MainPID']=='0' and x['UnitFileState']=='masked' and not x['all_cgroup_pids']
  after[unit]=x
 holders=[];races=0;denied=0;count=0
 for pid in os.listdir('/proc'):
  if not pid.isdigit():continue
  try:files=os.listdir('/proc/'+pid+'/fd')
  except FileNotFoundError:races+=1;continue
  except PermissionError:denied+=1;continue
  for n in files:
   count+=1;assert count<=1000000
   try:target=os.readlink('/proc/'+pid+'/fd/'+n).replace(' (deleted)','')
   except FileNotFoundError:races+=1;continue
   except PermissionError:denied+=1;continue
   if target in (db,db+'-wal',db+'-shm'):holders.append(int(pid))
 assert not holders and denied==0
 assert h(db)==db_before
 assert original_hashes=={n:h(OLD+'/'+n) for n in original_hashes}
 for unit,x in UNITS.items():assert h(D+'/'+unit+'.backup')==x['sha256']
 value.update(state='AUTHORIZED_AUXILIARY_OWNER_ISOLATED',after=after,old_database_handle_holders=[],fd_checked=count,process_races=races,permission_denials=denied,original_stage1_gateway_journal_unchanged=True,database_unchanged=True,other_writers_outside_scope='UNKNOWN')
 atomic(value)
except Exception as e:
 value.update(state='HOLD_AUXILIARY_ISOLATION',error_type=type(e).__name__,error=str(e)[:200]);atomic(value);print(json.dumps(value,sort_keys=True));raise
print(json.dumps(value,sort_keys=True))
print('AUXILIARY_ISOLATION_RECEIPT_PATH='+D+'/auxiliary-isolation-receipt.json')
print('AUXILIARY_ISOLATION_RECEIPT_SHA256='+h(D+'/auxiliary-isolation-receipt.json'))
print('INSTALL=NO; FENCE_MUTATION=NO; NEW_WRITER=NO; AUTO_RESTART=NO')
