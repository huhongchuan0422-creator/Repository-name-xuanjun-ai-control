"""Read-only legacy process and database-handle inventory. No ledger reads/writes."""
import os,sys,socket,subprocess,json,hashlib,stat
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
units={}
for unit in ('xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service'):
 r=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=Id,ActiveState,SubState,MainPID,ControlGroup,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 assert r.returncode==0
 v=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
 cg=v.get('ControlGroup','');assert cg in ('','/system.slice/'+unit)
 fragment='/etc/systemd/system/'+unit
 fd=os.open(fragment,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  info=os.fstat(f.fileno());raw=f.read(65537);assert stat.S_ISREG(info.st_mode) and len(raw)<=65536
 v['fragment_sha256']=hashlib.sha256(raw).hexdigest()
 members=set()
 if cg:
  root='/sys/fs/cgroup/systemd'+cg
  for directory,children,files in os.walk(root,followlinks=False):
   if 'cgroup.procs' in files:
    with open(directory+'/cgroup.procs') as f:members.update(int(x) for x in f.read(65537).split())
 v['all_cgroup_pids']=sorted(members);v['cgroups_empty']=not members
 units[unit]=v
db='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
holders=[];races=0;denied=0;checked=0
for name in os.listdir('/proc'):
 if not name.isdigit():continue
 directory='/proc/'+name+'/fd'
 try:fds=os.listdir(directory)
 except FileNotFoundError:races+=1;continue
 except PermissionError:denied+=1;continue
 matched=[]
 for f in fds:
  checked+=1;assert checked<=1000000
  try:target=os.readlink(directory+'/'+f)
  except FileNotFoundError:races+=1;continue
  except PermissionError:denied+=1;continue
  if target.replace(' (deleted)','') in (db,db+'-wal',db+'-shm'):matched.append(target)
 if matched:
  try:
   with open('/proc/'+name+'/status') as f:status=f.read(65537)
   uid=next(x for x in status.splitlines() if x.startswith('Uid:')).split()[1:]
   exe=os.readlink('/proc/'+name+'/exe')
   with open('/proc/'+name+'/cgroup') as f:cg=f.read(65537)
   holders.append({'pid':int(name),'uids':uid,'exe':exe,'cgroup':cg,'database_handles':sorted(set(matched))})
  except (FileNotFoundError,ProcessLookupError):races+=1
result={'schema':1,'units':units,'old_db_handle_holders':holders,'fd_checked':checked,'process_races':races,'permission_denials':denied,'ledger_opened':False,'ledger_changed':False,'service_changes':False,'writer_admission':False,'fence_status':'NOT_READ_NOT_CHANGED','other_writers':'UNKNOWN_NOT_PROVEN_BY_HANDLE_SNAPSHOT','model_calls':0}
print(json.dumps(result,sort_keys=True))
print('READ_ONLY=YES; INSTALL=NO; STOP=NO; FENCE_MUTATION=NO')
