"""Original UK serial maintenance successor. Local candidate; not site-bound.
No account logic here: calls exact installed original bootstrap inside same image.
"""
import hashlib,json,os,pwd,re,stat,subprocess,sys
from pathlib import Path
import types
_support_path=Path(__file__).resolve().with_name('original_manual_support.py')
_fd=os.open(str(_support_path),os.O_RDONLY|os.O_NOFOLLOW)
try:
 _st=os.fstat(_fd);_raw=os.read(_fd,65537)
 if not stat.S_ISREG(_st.st_mode) or _st.st_nlink!=1 or _st.st_size!=len(_raw) or len(_raw)>65536 or hashlib.sha256(_raw).hexdigest()!='ef9917bd9adb09a4f0ffb531c0d6a98d39f804a3fd282fc6696b3ec5a7ad32ad':raise RuntimeError('ORIGINAL_SUPPORT_PIN_CHANGED')
finally:os.close(_fd)
original=types.ModuleType('original_manual_support');original.__file__=str(_support_path)
exec(compile(_raw,str(_support_path),'exec'),original.__dict__)
IMAGE='sha256:2068eb13af3252332cb4716931ce01f1f5506f83ab615d772eeb9ba84a999261'
SOURCE='e23e1868b16f6c4c3f30f158418e6557037df28e'
IMAGE_ENV=['PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG=C.UTF-8', 'GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D', 'PYTHON_VERSION=3.11.17', 'PYTHON_SHA256=bfb74ad39efae27cda510f134ab408e00f9992c56851cfc0b1cdb5646da11599', 'PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'HOME=/home/community', 'OCR_DET_MODEL_PATH=/opt/ocr-bundle/models/PP-OCRv6_det_small.onnx', 'OCR_REC_MODEL_PATH=/opt/ocr-bundle/models/PP-OCRv6_rec_small.onnx', 'OCR_CLS_MODEL_PATH=/opt/ocr-bundle/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx', 'OCR_MODEL_SHA256={"det":"090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f","rec":"6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884","cls":"e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c"}', 'COMMUNITY_SOURCE_SHA=e23e1868b16f6c4c3f30f158418e6557037df28e']
BASE=original.BASE; RUN='/run/xuanjun-community-preview'; D=original.DOCKER
# Actual committed new container and current host configuration not received yet.
REVIEWED_SITE_BINDING=None
class Hold(RuntimeError):pass
def need(v,code):
 if not v:raise Hold(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def operator():
 need(os.getuid()==os.geteuid()==0 and os.uname().nodename.split('.')[0]==original.HOST,'EXACT_ROOT_HOST')
 a=pwd.getpwnam('admin');need(a.pw_uid>0 and os.environ.get('SUDO_USER')=='admin' and os.environ.get('SUDO_UID')==str(a.pw_uid) and os.environ.get('SUDO_GID')==str(a.pw_gid),'REAL_ADMIN_SUDO_REQUIRED')
 with open('/proc/self/loginuid','rb') as f:need(f.read(32).strip()==str(a.pw_uid).encode(),'REAL_ADMIN_KERNEL_LOGIN_REQUIRED')

def mounts(rows):
 expected={BASE+'/config':False,BASE+'/data':True,RUN:True}
 need(type(rows)is list and len(rows)==3,'EXACT_ORIGINAL_MOUNTS')
 for m in rows:need(m.get('Type')=='bind' and m.get('Source')==m.get('Destination') and m.get('Destination') in expected and m.get('RW') is expected[m['Destination']],'EXACT_ORIGINAL_MOUNTS')
 need({m['Destination'] for m in rows}==set(expected),'EXACT_ORIGINAL_MOUNTS')

def inspect_app(capture):
 fmt='{{json .Id}}\n{{json .Image}}\n{{json .State.Running}}\n{{json .Config.User}}\n{{json .Mounts}}\n{{json .HostConfig.ReadonlyRootfs}}\n{{json .State.Paused}}\n{{json .State.Restarting}}\n{{json (index .Config.Labels "community.source")}}'
 lines=capture(D+['container','inspect','--format',fmt,original.NAME]).splitlines();need(len(lines)==9,'INSTANCE_SHAPE')
 cid,img,running,user,ms,ro,paused,restarting,source=[json.loads(s) for s in lines]
 need(re.fullmatch('[a-f0-9]{64}',cid) and img==IMAGE and user=='10001:1008' and type(running)is bool and ro is True and paused is False and restarting is False and source==SOURCE,'EXACT_INSTALLED_E23E_INSTANCE')
 mounts(ms);return dict(container_id=cid,image_id=img,running=running,user=user,mounts=ms,source=source)

# Fixed code uses only original image modules. It never outputs password/key data.
# A protected per-request directory is created by the existing app UID only.
BOOTSTRAP_CODE=r'''
import os,sys,json,stat
sys.path.insert(0,'/app')
from pathlib import Path
from scripts.community_admin_preflight import build_plan
from scripts.community_admin_bootstrap import run
from scripts.pr122_customer_core import canonical
request=sys.argv[1]
expected_host_sha=sys.argv[2]
base=Path('/var/lib/xuanjun-community-preview/data')
directory=base/('admin-maintenance-'+request)
if os.path.lexists(str(directory)):
 s=directory.lstat()
 if not stat.S_ISDIR(s.st_mode) or stat.S_ISLNK(s.st_mode) or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o700:raise SystemExit('HOLD_PRIVATE_REQUEST_DIRECTORY')
else:
 directory.mkdir(mode=0o700)
 fd=os.open(str(base),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(fd);os.close(fd)
plan=build_plan('/var/lib/xuanjun-community-preview/config/host.json','/var/lib/xuanjun-community-preview/config/center-keys.json','/var/lib/xuanjun-community-preview/config/wechat.json',str(directory/'center-backup.sqlite'),str(directory/'owner-identity.json'),request)
if plan['plan']['host_sha256']!=expected_host_sha:raise SystemExit('HOLD_CONFIRMED_HOST_CONFIG_CHANGED')
# --inspect recovers the exact same request without setting any password.
observed=run(plan['plan'],'--inspect')
if observed.get('recovery',{}).get('phase')=='EXISTING_DATABASE_COMMIT_READBACK':
 print(json.dumps(dict(status='EXISTING_DATABASE_COMMIT_READBACK',account_written=False,complete_delivery=False),sort_keys=True))
else:
 result=run(plan['plan'],'--bootstrap')
 print(json.dumps(result,sort_keys=True))
'''
# No original parser/provider exception text can expose secrets on the TTY.
BOOTSTRAP_CODE = 'try:\n' + ''.join(' '+line+'\n' for line in BOOTSTRAP_CODE.splitlines()) + \
 "except BaseException:\n print('HOLD_ORIGINAL_BOOTSTRAP_QUERY_SAME_REQUEST')\n raise SystemExit(1) from None\n"


def maintenance_argv(plan):
 need(re.fullmatch('admin-[a-f0-9]{24}',plan['request_id']),'FIXED_REQUEST')
 need(plan['runtime']['image_id']==IMAGE,'IMAGE_PIN')
 # All mounts and user are independently validated against the actual app.
 mounts(plan['runtime']['mounts'])
 name='xuanjun-community-admin-'+plan['request_id'][6:]
 return D+['container','create','--pull','never','--name',name,'--interactive','--tty','--restart','no','--ipc','private','--network','none','--read-only','--user','10001:1008','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64','--cpus','0.5','--memory','512m','--memory-swap','512m','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777','--log-driver','none','--mount','type=bind,src='+BASE+'/config,dst='+BASE+'/config,readonly','--mount','type=bind,src='+BASE+'/data,dst='+BASE+'/data','--mount','type=bind,src='+RUN+',dst='+RUN,'--workdir','/app','--entrypoint','python',IMAGE,'-I','-B','-c',BOOTSTRAP_CODE,plan['request_id'],plan['host_sha256']]

class Serial:
 """One original global lock held outside; original Host owns Center/runtime.
 io.save is durable CAS, io.observe and io.maintenance are read-only.
 No wrapper Center flock: that would deadlock the sole original Host.
 """
 def __init__(self,io):self.io=io
 def same(self,r):
  self.io.boundary()
  self.io.committed(r['plan']['binding']) if 'binding' in r['plan'] else None
  now=self.io.observe();p=r['plan'];need(now['container_id']==p['runtime']['container_id'] and now['image_id']==IMAGE,'INSTANCE_CHANGED');need(self.io.config_sha()==p['host_sha256'],'HOST_CONFIG_CHANGED')
  if 'mount_root_identity' in p:need(self.io.source_dirs()==p['mount_root_identity'],'MOUNT_ROOT_IDENTITY_CHANGED')
  return now
 def phase(self,r,name):self.io.boundary();r['phase']=name;self.io.save(r)
 def advance(self,r):
  p=r['plan'];now=self.same(r)
  need(r['confirmation_sha']==sha(enc(p)),'EXACT_TTY_PLAN_CONFIRMATION')
  if r['phase']=='CONFIRMED':
   need(now['running']==p['runtime']['running'],'INITIAL_STATE_CHANGED')
   if now['running']:
    self.phase(r,'STOP_INTENT');self.io.stop(now['container_id'])
   need(not self.same(r)['running'],'NOT_STOPPED');self.phase(r,'STOPPED')
  elif r['phase']=='STOP_INTENT':
   # Never stop twice after lost response. Only observed stopped can progress.
   need(not now['running'],'STOP_RESULT_UNKNOWN');self.phase(r,'STOPPED')
  if r['phase']=='STOPPED':
   need(not self.same(r)['running'],'APP_RESTARTED')
   need(self.io.maintenance(p) is None,'MAINTENANCE_ALREADY_EXISTS')
   self.phase(r,'CREATE_INTENT');self.io.create(maintenance_argv(p))
  if r['phase']=='CREATE_INTENT':
   m=self.io.maintenance(p);need(m is not None and m['exact'] is True and m['status']=='created','CREATE_RESULT_UNKNOWN')
   r['maintenance_id']=m['id'];self.phase(r,'CREATED')
  if r['phase']=='CREATED':
   need(not self.same(r)['running'],'APP_RESTARTED');m=self.io.maintenance(p)
   need(m['id']==r['maintenance_id'] and m['exact'] and m['status']=='created','MAINTENANCE_CHANGED')
   # Start once with inherited real /dev/tty: getpass never in env/argv/logs.
   self.phase(r,'BOOTSTRAP_INTENT');self.io.interactive_start(m['id'])
  if r['phase']=='BOOTSTRAP_INTENT':
   m=self.io.maintenance(p)
   need(m is not None and m['id']==r['maintenance_id'] and m['exact'],'MAINTENANCE_CHANGED')
   need(m['status']=='exited','BOOTSTRAP_IN_PROGRESS_OR_UNKNOWN')
   r['maintenance_exit']=m['exit_code'];self.phase(r,'MAINTENANCE_EXITED')
  if r['phase']=='MAINTENANCE_EXITED':
   # Nonzero/cancelled bootstrap still restores original availability, never retries account creation.
   need(not self.same(r)['running'],'APP_RESTARTED')
   m=self.io.maintenance(p);need(m and m['id']==r['maintenance_id'] and m['status']=='exited' and m['exact'],'MAINTENANCE_NOT_TERMINAL')
   if p['runtime']['running']:
    self.phase(r,'START_INTENT');self.io.start(p['runtime']['container_id'])
   else:self.phase(r,'RESTORED')
  if r['phase']=='START_INTENT':
   # Lost start response: observation only, not implicit retry.
   need(self.same(r)['running'],'START_RESULT_UNKNOWN');self.phase(r,'RESTORED')
  if r['phase']=='RESTORED':
   need(self.same(r)['running']==p['runtime']['running'],'ORIGINAL_RUNNING_STATE_NOT_RESTORED')
   return dict(state='ORIGINAL_RUNNING_STATE_RESTORED',account_result='BOOTSTRAP_EXIT_ZERO_NEEDS_REAL_LOGIN_READBACK' if r['maintenance_exit']==0 else 'BOOTSTRAP_NOT_SUCCESS_NEEDS_ORIGINAL_REQUEST_INSPECT',complete_delivery=False)
  raise Hold('UNKNOWN_PHASE')

def disabled_entry():
 # This is not yet a site-bound executable wrapper. Never infer new container.
 print(json.dumps({'state':'HOLD_REAL_NEW_INSTANCE_AND_ORIGINAL_MAINTENANCE_BINDING_REQUIRED','site_executed':False}))
 raise SystemExit(2)

class OriginalIO:
 """Original stdlib host I/O, original protected journal and same Docker socket.
 Only selected metadata is captured. Interactive child never uses PIPE/log driver.
 """
 def __init__(self,request):
  need(re.fullmatch('admin-[a-f0-9]{24}',request),'FIXED_REQUEST')
  self.request=request;self.path=original.JOURNAL+'/'+request+'-maintenance.json';self.last=None;self.locks=None
 def boundary(self):
  operator();need(self.locks is not None,'GLOBAL_LOCK_REQUIRED');self.locks.check()
 def committed(self,binding):
  root='/opt/xuanjun-community-preview/update-journal-211a9-to-e23e186-first-v1'
  raw=original.read(root+'/'+binding['committed_attempt']+'/checkpoint.json',0)
  cp=original.parse(raw);active=original.parse(original.read(root+'/active-attempt.json',0))
  need(sha(raw)==binding['committed_checkpoint_sha256'] and cp.get('phase')=='COMMITTED' and cp.get('new_id')==binding['container_id'] and cp.get('sequence')==7 and active.get('attempt')==binding['committed_attempt'] and active.get('plan_sha256')==cp.get('plan_sha256'),'ACTUAL_COMMITTED_CHECKPOINT_REQUIRED')
 def observe(self):return inspect_app(original.command)
 def config_sha(self):return sha(original.read(original.HOST_FILE,10001))
 def save(self,r):
  self.boundary()
  need(r['plan']['request_id']==self.request,'REQUEST_CHANGED')
  if self.last is None:
   original.write(self.path,enc(r),0)
  else:
   need(original.metadata(self.path,0)==self.last,'JOURNAL_CHANGED')
   original.write(self.path,enc(r),0,replace=True,expected=self.last)
  self.last=original.metadata(self.path,0)
 def load(self):
  raw=original.read(self.path,0);self.last=original.metadata(self.path,0);r=original.parse(raw)
  need(r['plan']['request_id']==self.request,'REQUEST_CHANGED');return r
 def stop(self,cid):self.boundary();original.command(D+['container','stop','--time','20',cid])
 def start(self,cid):self.boundary();original.command(D+['container','start',cid])
 def create(self,argv):self.boundary();original.command(argv)
 def maintenance(self,p):
  name='xuanjun-community-admin-'+p['request_id'][6:]
  rows=original.command(D+['container','ls','--all','--filter','name=^/'+name+'$','--format','{{.ID}}']).splitlines()
  if not rows:return None
  need(len(rows)==1,'MULTIPLE_MAINTENANCE_CONTAINERS')
  fmt='{{json .Id}}\n{{json .Image}}\n{{json .State.Status}}\n{{json .State.ExitCode}}\n{{json .Config.User}}\n{{json .Config.Entrypoint}}\n{{json .Config.Cmd}}\n{{json .Mounts}}\n{{json .HostConfig.ReadonlyRootfs}}\n{{json .HostConfig.NetworkMode}}\n{{json .HostConfig.LogConfig.Type}}\n{{json .HostConfig.Privileged}}\n{{json .HostConfig.CapDrop}}\n{{json .HostConfig.SecurityOpt}}\n{{json .HostConfig.PidMode}}\n{{json .HostConfig.Binds}}\n{{json .HostConfig.CapAdd}}\n{{json .HostConfig.Devices}}\n{{json .HostConfig.DeviceRequests}}\n{{json .HostConfig.RestartPolicy.Name}}\n{{json .Config.Tty}}\n{{json .Config.OpenStdin}}\n{{json .HostConfig.Init}}\n{{json .HostConfig.IpcMode}}\n{{json .Config.Env}}\n{{json .Config.WorkingDir}}\n{{json .HostConfig.Tmpfs}}\n{{json .HostConfig.PidsLimit}}\n{{json .HostConfig.NanoCpus}}\n{{json .HostConfig.Memory}}\n{{json .HostConfig.MemorySwap}}'
  lines=original.command(D+['container','inspect','--format',fmt,name]).splitlines();need(len(lines)==31,'MAINTENANCE_SHAPE')
  cid,image,status,exitcode,user,entry,cmd,ms,ro,network,log,privileged,drop,security,pidmode,binds,capadd,devices,device_requests,restart,tty,stdin,init,ipcmode,env,workdir,tmpfs,pids,cpu,memory,swap=[json.loads(x) for x in lines]
  mounts(ms);exact=(image==IMAGE and user=='10001:1008' and entry==['python'] and cmd==['-I','-B','-c',BOOTSTRAP_CODE,p['request_id'],p['host_sha256']] and ro is True and network=='none' and log=='none' and privileged is False and drop==['ALL'] and security in (['no-new-privileges'],['no-new-privileges:true']) and pidmode=='' and not binds and not capadd and not devices and not device_requests and restart=='no' and tty is True and stdin is True and init in (False,None) and ipcmode=='private' and env==IMAGE_ENV and workdir=='/app' and tmpfs=={'/tmp':'rw,noexec,nosuid,nodev,size=16777216,mode=1777'} and pids==64 and cpu==500000000 and memory==swap==536870912)
  need(re.fullmatch('[a-f0-9]{64}',cid) and status in ('created','running','exited') and type(exitcode)is int,'MAINTENANCE_ID_STATUS')
  return dict(id=cid,status=status,exit_code=exitcode,exact=exact)
 def source_dirs(self):
  values={}
  for path in (BASE+'/config',BASE+'/data',RUN):
   fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
   try:
    for part in path.split('/')[1:]:
     nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
    st=os.fstat(fd);need(not st.st_mode&0o002,'WRITABLE_MOUNT_ROOT');values[path]=[st.st_dev,st.st_ino,st.st_uid,st.st_gid,st.st_mode]
   finally:os.close(fd)
  return values
 def interactive_start(self,cid):
  self.boundary()
  # getpass is handled only by original bootstrap on this real controlling TTY.
  with open('/dev/tty','r+b',buffering=0) as tty:
   need(os.isatty(tty.fileno()),'REAL_TTY_REQUIRED')
   result=subprocess.run(D+['container','start','--attach','--interactive',cid],stdin=tty,stdout=tty,stderr=tty,check=False)
   # Exit code is observed from the exact container; never retried on this result.
   return result.returncode

def prepared_plan(binding,request,io):
 need(type(binding)is dict and set(binding)=={'container_id','image_id','host_sha256','committed_attempt','committed_checkpoint_sha256'},'REAL_COMMITTED_BINDING_REQUIRED')
 need(binding['image_id']==IMAGE and re.fullmatch('[a-f0-9]{64}',binding['container_id']) and re.fullmatch('[a-f0-9]{64}',binding['host_sha256']) and re.fullmatch('[a-f0-9]{64}',binding['committed_checkpoint_sha256']),'REAL_COMMITTED_BINDING_REQUIRED')
 need(binding['committed_attempt']=='community-update-e23e1868b16f-2d8090633c61-stopped-v1-e23e186-first-v1','ORIGINAL_ATTEMPT_REQUIRED')
 need(re.fullmatch('admin-[a-f0-9]{24}',request),'FIXED_REQUEST')
 io.committed(binding)
 now=io.observe();need(now['container_id']==binding['container_id'] and io.config_sha()==binding['host_sha256'],'FRESH_INSTANCE_CONFIG_REQUIRED')
 return dict(request_id=request,runtime=now,mount_root_identity=io.source_dirs(),host_sha256=binding['host_sha256'],binding=dict(binding),maintenance_code_sha256=sha(BOOTSTRAP_CODE.encode()),capability_goal='ALL_153_COMMUNITY_BUSINESS_PLUS_5_ADMIN_CAPABILITIES_WITH_REAL_SCOPE_BINDINGS',intermediate_only='CORE_FIRST_ENABLE_NOT_FULL_BUSINESS_ACCEPTANCE')

def execute_prepared(binding,request,operation,io=None):
 """Only original reviewed application/credentials scope; no authority token issued.
 Actual binding must be supplied by the fixed reviewed successor, not arbitrary CLI.
 """
 need(binding is not None,'REAL_COMMITTED_BINDING_REQUIRED');operator()
 need(operation in ('plan','query','apply','recover'),'FIXED_OPERATION')
 io=io or OriginalIO(request)
 if operation=='query':
  r=io.load();need(r['plan']['binding']==binding and r['plan']['maintenance_code_sha256']==sha(BOOTSTRAP_CODE.encode()),'QUERY_BINDING_CHANGED');return dict(phase=r['phase'],runtime=io.observe(),maintenance=io.maintenance(r['plan']),account_readback='NOT_PERFORMED',no_retry=True)
 if operation=='plan':return prepared_plan(binding,request,io)
 locks=original.Locks()
 try:
  locks.acquire(original.GLOBAL_LOCK,0,original.metadata(original.GLOBAL_LOCK,0));io.locks=locks
  with open('/dev/tty','r+') as tty:
   need(os.isatty(tty.fileno()),'REAL_TTY_REQUIRED')
   if operation=='apply':p=prepared_plan(binding,request,io)
   else:
    r=io.load();p=r['plan'];need(p['binding']==binding,'RECOVERY_BINDING_CHANGED');need(p['maintenance_code_sha256']==sha(BOOTSTRAP_CODE.encode()),'MAINTENANCE_CODE_CHANGED')
   tty.write(json.dumps({'operation':operation,'plan':p,'scope':'Stop only original instance; original nonroot bootstrap; restore same instance; first core account is intermediate, full business scopes remain required'},ensure_ascii=False,indent=2)+'\n')
   phrase='CONFIRM COMMUNITY ADMIN MAINTENANCE '+sha(enc(p));tty.write(phrase+'\n');tty.flush();need(tty.readline().strip()==phrase,'EXACT_OWNER_TTY_CONFIRMATION_REQUIRED')
   if operation=='apply':
    r=dict(plan=p,phase='CONFIRMED',confirmation_sha=sha(enc(p)));io.save(r)
   if operation=='recover' and r['phase']=='START_INTENT' and not Serial(io).same(r)['running']:
    child=io.maintenance(p);need(child and child['exact'] and child['id']==r['maintenance_id'] and child['status']=='exited','MAINTENANCE_NOT_TERMINAL')
    need(not r.get('start_recovery_attempted'),'START_RECOVERY_RESULT_UNKNOWN')
    r['start_recovery_attempted']=True;io.save(r)
    io.start(p['runtime']['container_id'])
   # recover observes original phase; it never creates another account request,
   # force-kills a child, rewrites passwords, or retries unknown stop/start.
   return Serial(io).advance(r)
 finally:locks.close()

def observe_inputs():
 """Original post-install input projection only; no container create/stop/DB host."""
 operator();locks=original.Locks()
 try:
  locks.acquire(original.GLOBAL_LOCK,0,original.metadata(original.GLOBAL_LOCK,0));locks.check()
  io=OriginalIO('admin-'+'0'*24);io.locks=locks
  attempt='community-update-e23e1868b16f-2d8090633c61-stopped-v1-e23e186-first-v1'
  root='/opt/xuanjun-community-preview/update-journal-211a9-to-e23e186-first-v1'
  raw=original.read(root+'/'+attempt+'/checkpoint.json',0)
  state=io.observe();need(state['container_id']=='3efa731a127bed49a2c07690dad4e25d7e0c1a6f28765f49631d6346cd2b378d','ACTUAL_OWNER_APPLY_INSTANCE_REQUIRED')
  binding=dict(container_id=state['container_id'],image_id=IMAGE,host_sha256=io.config_sha(),committed_attempt=attempt,committed_checkpoint_sha256=sha(raw))
  io.committed(binding);dirs=io.source_dirs();locks.check()
  need(io.observe()==state and io.config_sha()==binding['host_sha256'] and original.read(root+'/'+attempt+'/checkpoint.json',0)==raw,'OBSERVATION_CHANGED')
  need(io.source_dirs()==dirs,'MOUNT_ROOT_IDENTITY_CHANGED');io.committed(binding);locks.check()
  return dict(state='READ_ONLY_MAINTENANCE_INPUTS',candidate_binding=binding,runtime=state,mount_root_identity=dirs,site_executed=False,account_written=False,binding_requires_review=True)
 finally:locks.close()

def main(argv=None):
 import argparse
 parser=argparse.ArgumentParser(allow_abbrev=False)
 parser.add_argument('operation',choices=('observe','plan','query','apply','recover'))
 parser.add_argument('--request')
 args=parser.parse_args(argv)
 if args.operation!='observe' and REVIEWED_SITE_BINDING is None:return disabled_entry()
 try:
  if args.operation=='observe':
   print(json.dumps(observe_inputs(),sort_keys=True));return 0
  need(args.request is not None,'FIXED_REQUEST')
  result=execute_prepared(REVIEWED_SITE_BINDING,args.request,args.operation)
  print(json.dumps(result,sort_keys=True));return 0
 except BaseException as error:
  code=str(error) if type(error)is Hold and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',str(error)) else 'QUERY_ORIGINAL_MAINTENANCE_REQUEST_REQUIRED'
  print(json.dumps({'state':'HOLD','code':code,'complete_delivery':False}));return 2

if __name__=='__main__':raise SystemExit(main())
