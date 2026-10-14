#!/usr/bin/env python3
"""Bounded nonce helpers. Never bind a socket, load SDK code, or open a DB.
Runtime CLI has no fixture bypass; tests call pure helpers with injected fakes.
"""
import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import signal
import selectors
import socket
import stat
import struct
import subprocess
import sys
import time

ROOT_PREFIX='/run/xj-p2-proof-'
MAX_FRAME=4096
SDK_MAX=8*1024*1024
OUTPUT=None
PROPS={
 'socket':('Id','LoadState','NeedDaemonReload','FragmentPath','DropInPaths','Listen','Accept','Triggers',
           'SocketUser','SocketGroup','SocketMode','DirectoryMode','RemoveOnStop','ActiveState','SubState'),
 'service':('Id','LoadState','NeedDaemonReload','FragmentPath','DropInPaths','User','Group','ExecStart',
            'WorkingDirectory','TriggeredBy','ActiveState','SubState','MainPID','InvocationID')}


def need(value,code):
 if not value:raise ValueError(code)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def emit(value):
 stream=OUTPUT or sys.stdout;stream.write(canonical(value).decode()+'\n');stream.flush()
def parse(raw):
 def pairs(items):
  value={}
  for key,item in items:need(key not in value,'DUPLICATE_KEY');value[key]=item
  return value
 return json.loads(raw.decode(),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('NONFINITE')))
def stamp(info):return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
def remaining(end):
 value=end-time.monotonic()
 if value<=0:raise TimeoutError('HELPER_DEADLINE')
 return value


def read_regular(path,maximum,root_owned=True,expected_uid=None,deadline=None):
 before=os.lstat(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  opened=os.fstat(fd)
  need(stat.S_ISREG(opened.st_mode) and opened.st_nlink==1 and stamp(before)==stamp(opened) and
       0<=opened.st_size<=maximum,'REGULAR_SIZE_IDENTITY')
  if root_owned:need(opened.st_uid==0 and not opened.st_mode&0o022,'ROOT_PROTECTED_FILE')
  if expected_uid is not None:need(opened.st_uid==expected_uid and not opened.st_mode&0o022,'EXACT_FILE_OWNER')
  parts=[];total=0
  while total<=maximum:
   if deadline is not None:remaining(deadline)
   part=os.read(fd,min(65536,maximum+1-total))
   if not part:break
   parts.append(part);total+=len(part)
  need(total<=maximum and stamp(opened)==stamp(os.fstat(fd)) and stamp(opened)==stamp(os.lstat(path)),
       'READ_RACE_OR_BOUND')
  return b''.join(parts),stamp(opened)
 finally:os.close(fd)


def read_proc(path,maximum):
 need(re.fullmatch(r'/proc/(?:[1-9][0-9]*/(?:stat|status|cgroup)|sys/kernel/random/boot_id)',path),'PROC_READ_SCOPE')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  raw=os.read(fd,maximum+1);need(len(raw)<=maximum,'PROC_BOUND');return raw
 finally:os.close(fd)

def process(pid):
 need(type(pid) is int and pid>0,'PID_REQUIRED');prefix='/proc/'+str(pid)+'/'
 before=read_proc(prefix+'stat',8192);status=read_proc(prefix+'status',65536)
 cgroup=read_proc(prefix+'cgroup',8192);after=read_proc(prefix+'stat',8192)
 start=int(before[before.rfind(b')')+2:].split()[19])
 need(start==int(after[after.rfind(b')')+2:].split()[19]),'PROCESS_CHANGED');fields={}
 for line in status.decode().splitlines():
  if ':' in line:
   k,v=line.split(':',1)
   if k in ('Uid','Gid','Groups','CapEff','CapBnd','CapAmb','NoNewPrivs','Seccomp'):fields[k]=v.strip()
 return {'pid':pid,'starttime':start,'status':fields,'cgroup_sha256':digest(cgroup)}


def ancestors(path,home_uid=None):
 parent=os.path.dirname(path)
 while True:
  info=os.lstat(parent)
  allowed=(0,home_uid) if home_uid is not None and parent.startswith('/home/xuanjun_dev') else (0,)
  need(stat.S_ISDIR(info.st_mode) and info.st_uid in allowed and not info.st_mode&0o022 and
       os.path.realpath(parent)==parent,'PROTECTED_ANCESTRY')
  if parent=='/':break
  parent=os.path.dirname(parent)


def acl(path):
 try:raw=os.getxattr(path,'system.posix_acl_access',follow_symlinks=False)
 except OSError as error:
  if error.errno in (errno.ENODATA,errno.ENOTSUP,errno.EOPNOTSUPP):raw=b''
  else:raise
 return digest(raw)


def validate_config(config,config_path):
 keys={'schema','purpose','nonce','case','role','mode','policy_sha256','operator_acknowledged',
       'expected_uid','expected_gid','sdk_bindings','public_files','systemctl','allowed_pids','python'}
 need(type(config) is dict and set(config)==keys,'CONFIG_SCHEMA')
 need(type(config['schema']) is int and config['schema']==1 and config['purpose']=='ISOLATED_P2_PROBE_HELPER','CONFIG_PURPOSE')
 need(type(config['nonce']) is str and re.fullmatch(r'[0-9a-f]{32}',config['nonce']),'CONFIG_NONCE')
 need(type(config['case']) is int and 1<=config['case']<=8,'CONFIG_CASE')
 need(config['role'] in ('ledger','broker','dashboard','callback','native') and config['mode'] in ('server','client'),'CONFIG_ROLE_MODE')
 root=ROOT_PREFIX+config['nonce']
 expected=root+'/helper-'+config['role']+'-'+config['mode']+'.json'
 need(config_path==expected and config['operator_acknowledged'] is True and
      re.fullmatch(r'[0-9a-f]{64}',config['policy_sha256']),'EXACT_CONFIG_BINDING')
 need(type(config['expected_uid']) is int and type(config['expected_gid']) is int,'CONFIG_IDENTITY')
 need(type(config['sdk_bindings']) is list and len(config['sdk_bindings'])<=5 and
      type(config['public_files']) is list and len(config['public_files'])<=20 and
      config['systemctl']=='/usr/bin/systemctl' and type(config['allowed_pids']) is dict,'CONFIG_READ_SCOPE')
 return root


def load_config(path):
 ancestors(path);raw,info=read_regular(path,65536)
 need(stat.S_IMODE(info[2])==0o644 and info[3:6]==(0,0,1),'CONFIG_ROOT_ROOT_0644')
 config=parse(raw);root=validate_config(config,path)
 need((os.geteuid(),os.getegid())==(config['expected_uid'],config['expected_gid']),'ACTUAL_HELPER_IDENTITY')
 return config,root

def wait_owned_child(process,end):
 while True:
  remaining(end);row=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
  if row is not None:
   need(row.si_pid==process.pid,'OWNED_CHILD_IDENTITY')
   return row.si_status if row.si_code==os.CLD_EXITED else -row.si_status
  time.sleep(.005)

def cleanup_owned_child(process):
 errors=[];lock=getattr(process,"_waitpid_lock",None);held=False
 try:
  need(lock is not None and lock.acquire(False),'CHILD_WAIT_LOCK_REQUIRED');held=True
  need(process.returncode is None,'CHILD_ALREADY_REAPED')
  row=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
  need(row is None or row.si_pid==process.pid,'OWNED_CHILD_IDENTITY')
  need(os.getpgid(process.pid)==process.pid and os.getsid(process.pid)==process.pid,'OWNED_CHILD_GROUP_SESSION')
  try:os.killpg(process.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  except BaseException:errors.append('CHILD_SIGNAL_UNCONFIRMED')
 except BaseException:errors.append('CHILD_OWNERSHIP_UNCONFIRMED')
 finally:
  if held:lock.release()
 for name in ('stdout','stderr'):
  try:
   stream=getattr(process,name,None)
   if stream is not None:stream.close()
  except BaseException:errors.append(name.upper()+'_CLOSE_UNCONFIRMED')
 try:process.wait(timeout=.2)
 except BaseException:errors.append('CHILD_REAP_UNCONFIRMED')
 return errors


def show(config,unit,suffix,end):
 stem='xj-p2-proof-'+config['nonce'];need(unit==stem+'.'+suffix,'EXACT_NONCE_MANAGER_UNIT')
 args=[config['systemctl'],'--system','show',unit,'--no-pager','--property='+','.join(PROPS[suffix])]
 stop=min(end,time.monotonic()+1)
 proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','SYSTEMD_COLORS':'0'},close_fds=True,start_new_session=True)
 sel=None;chunks={'out':b'','err':b''};completed=False
 try:
  sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ,'out');sel.register(proc.stderr,selectors.EVENT_READ,'err')
  while sel.get_map():
   for key,unused in sel.select(remaining(stop)):
    part=os.read(key.fd,4096)
    if not part:sel.unregister(key.fileobj);continue
    chunks[key.data]+=part;need(sum(len(x) for x in chunks.values())<=32768,'MANAGER_BOUND')
  need(wait_owned_child(proc,stop)==0,'MANAGER_READ_FAILED')
  result=dict(line.split('=',1) for line in chunks['out'].decode().splitlines() if '=' in line)
  need(set(result)==set(PROPS[suffix]) and all('[unprintable]' not in v for v in result.values()),'MANAGER_PROPERTIES_UNSUPPORTED')
  completed=True;return result
 finally:
  errors=[]
  try:
   if sel is not None:sel.close()
  except BaseException:errors.append('SELECTOR_CLOSE_UNCONFIRMED')
  errors+=cleanup_owned_child(proc)
  if errors:
   try:emit({'event':'MANAGER_CHILD_CLEANUP_UNCONFIRMED','errors':errors})
   except BaseException:pass
   if completed:raise RuntimeError('MANAGER_CHILD_CLEANUP_UNCONFIRMED')


def readpaths(config,root,end):
 results=[]
 def sample(label,fn):
  try: value=fn();results.append({'path_class':label,'status':'PASS_OBSERVED','evidence':value})
  except BaseException as exc:results.append({'path_class':label,'status':'NOT_VERIFIED','reason':type(exc).__name__})
 sample('manager-process',lambda:process(1))
 sample('boot-id',lambda:{'sha256':digest(read_proc('/proc/sys/kernel/random/boot_id',64))})
 sample('self-pid-namespace',lambda:{'link':os.readlink('/proc/self/ns/pid')})
 for row in config['public_files']:
  def read(row=row):
   need(set(row)=={'path','sha256','maximum'} and row['path'] in (
       '/usr/lib/systemd/systemd','/lib/systemd/systemd','/usr/bin/systemctl') or
       (set(row)=={'path','sha256','maximum'} and row['path'] in [root+'/candidate-'+x for x in
        ('ledger_service.py','ledger_server_identity.py','activation_control.py')]) or
       (set(row)=={'path','sha256','maximum'} and row['path'] in [root+'/'+x for x in
        ('probe-policy.json','fixture-activation.json','fixture-epochs.jsonl')]+
        ['/run/systemd/system/xj-p2-proof-'+config['nonce']+suffix for suffix in ('.socket','.service')]),
       'PUBLIC_SCOPE')
   ancestors(row['path']);raw,info=read_regular(row['path'],row['maximum'],deadline=end)
   need(digest(raw)==row['sha256'],'PUBLIC_HASH');return {'sha256':digest(raw),'size':len(raw)}
  sample('public:'+row['path'],read)
 for path in ('/run/dbus/system_bus_socket',)+ (('/run/systemd/private',) if os.geteuid()==0 else ()):
  def channel(path=path):
   ancestors(path);info=os.lstat(path);need(stat.S_ISSOCK(info.st_mode) and info.st_uid==0,'MANAGER_CHANNEL')
   return {'dev':info.st_dev,'ino':info.st_ino,'acl_sha256':acl(path)}
  sample('manager-channel:'+path,channel)
 for leaf in ('fixture-activation.lock','fixture-dispatcher.json'):
  def metadata_only(leaf=leaf):
   target=root+'/'+leaf;ancestors(target);info=os.lstat(target)
   need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022,'FIXTURE_METADATA')
   return {'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),'acl_sha256':acl(target),'content_opened':False}
  sample('metadata-only:'+leaf,metadata_only)
 for suffix in ('socket','service'):
  sample('manager-unit:'+suffix,lambda suffix=suffix:show(config,'xj-p2-proof-'+config['nonce']+'.'+suffix,suffix,end))
 return results


def sdk_checks(config,end):
 results=[]
 for row in config['sdk_bindings']:
  try:
   need(set(row)=={'path','sha256','uid','gid','size'} and row['path'].startswith('/home/xuanjun_dev/.openclaw/tools/'), 'SDK_SCOPE')
   ancestors(row['path'],1002);raw,info=read_regular(row['path'],SDK_MAX,False,row['uid'],end)
   need(info[4]==row['gid'] and len(raw)==row['size'] and digest(raw)==row['sha256'],'SDK_FIXED_BINDING')
   results.append({'path':row['path'],'status':'PASS_OBSERVED','size':len(raw),'sha256':digest(raw)})
  except BaseException as exc:results.append({'path':row.get('path'),'status':'NOT_VERIFIED','reason':type(exc).__name__})
 return results


def endpoint(path):
 info=os.lstat(path);need(stat.S_ISSOCK(info.st_mode),'NONCE_SOCKET_REQUIRED')
 return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
         'mode':stat.S_IMODE(info.st_mode),'acl_sha256':acl(path)}

def receive(sock,end):
 data=b''
 while b'\n' not in data:
  sock.settimeout(remaining(end));part=sock.recv(MAX_FRAME+1-len(data))
  need(part,'EARLY_EOF');data+=part;need(len(data)<=MAX_FRAME,'FRAME_BOUND')
 need(data.count(b'\n')==1 and data.endswith(b'\n'),'ONE_FRAME_REQUIRED')
 return parse(data[:-1])


def client(config,root):
 end=time.monotonic()+3;case=config['case'];release=root+'/release-%02d.json'%case
 need(not os.path.lexists(release),'RELEASE_ALREADY_PRESENT')
 before=endpoint(root+'/ledger.sock');manager=process(1)
 sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);bound=False
 try:
  sock.settimeout(remaining(end));sock.connect(root+'/ledger.sock')
  peer=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));bound=True
  need(peer[0]==1 and peer[1]==0,'MEASURED_CREATOR_NOT_SHARED_INIT_ROOT')
  emit({'event':'BOUND_PAUSED' if case in (6,8) else 'BOUND','case':case,'peer':list(peer),
        'endpoint':before,'own':process(os.getpid()),'manager':manager})
  if case in (6,8):
   while not os.path.lexists(release):remaining(end);time.sleep(.01)
   raw,unused=read_regular(release,4096)
   need(raw==canonical({'schema':1,'nonce':config['nonce'],'case':case,'policy_sha256':config['policy_sha256']})+b'\n','RELEASE_BINDING')
  request={'schema':1,'nonce':config['nonce'],'case':case,'challenge':'PUBLIC_INERT_PROBE'}
  sock.sendall(canonical(request)+b'\n');response=receive(sock,end)
  need(response==dict(request,reply='PUBLIC_INERT_REPLY'),'NONCE_RESPONSE')
  sock.settimeout(remaining(end));need(sock.recv(1)==b'','TRAILING_RESPONSE')
  after=endpoint(root+'/ledger.sock');peer_after=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
  need(before==after and peer==peer_after and manager==process(1),'SESSION_IDENTITY_CHANGED')
  result={'case':case,'status':'PASS_OBSERVED','mechanism':'INHERITED_MANAGER_CHALLENGE','peer':list(peer),
          'production_verifier_admission':'NOT_VERIFIED'}
 except BaseException as exc:
  result={'case':case,'status':'FAIL_OBSERVED' if bound else 'NOT_VERIFIED','reason':type(exc).__name__+':'+str(exc)[:100],
          'bound_before_failure':bound,'production_verifier_admission':'NOT_VERIFIED'}
 finally:sock.close()
 # Separate five-second read access budget; no further socket connections.
 check_end=time.monotonic()+5
 result['readpaths']=readpaths(config,root,check_end)
 if config['role']=='native':result['sdk']=sdk_checks(config,check_end)
 result['owner_process_gate']='NOT_VERIFIED_FIXED_PRODUCTION_PROCESS_PINS_NOT_REMAPPED'
 emit({'event':'RESULT','result':result});return result


def peer_executable(config,root,credentials,case):
 # Scope comes from the kernel-connected peer and an exact nonce command/cgroup.
 pid,uid,gid=credentials;need(pid>1 and uid in (0,1002,1004),'NONCE_PEER_SCOPE')
 before=process(pid);prefix='/proc/'+str(pid)+'/'
 fd=os.open(prefix+'cmdline',os.O_RDONLY|os.O_NOFOLLOW)
 try:cmdline=os.read(fd,8193);need(len(cmdline)<=8192,'ARGV_BOUND')
 finally:os.close(fd)
 role={1:'native',2:'broker',3:'dashboard',4:'callback',5:'native',6:'broker',7:'dashboard',8:'callback'}[case]
 expected=[config['python']['path'],'-B',root+'/probe_helpers.py','--config',
           root+'/helper-'+role+'-client.json','--mode','client']
 need(cmdline==b'\x00'.join(x.encode() for x in expected)+b'\x00','EXACT_NONCE_PEER_ARGV')
 cgroup=read_proc(prefix+'cgroup',8192)
 need(('/xj-p2-proof-'+config['nonce']+'-'+role+'.service').encode() in cgroup,'EXACT_NONCE_PEER_CGROUP')
 exe_fd=os.open(prefix+'exe',os.O_RDONLY|os.O_NONBLOCK)
 try:
  info=os.fstat(exe_fd);need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022,'PEER_EXE_PROTECTED')
  chunks=[];count=0
  while count<=32*1024*1024:
   part=os.read(exe_fd,min(65536,32*1024*1024+1-count))
   if not part:break
   chunks.append(part);count+=len(part)
  need(count<=32*1024*1024 and digest(b''.join(chunks))==config['python']['sha256'] and
       stamp(info)==stamp(os.fstat(exe_fd)) and os.readlink(prefix+'exe')==config['python']['path'],'PEER_EXE_HASH_PATH')
 finally:os.close(exe_fd)
 need(before==process(pid),'PEER_LIFETIME_CHANGED')
 return {'status':'PASS_OBSERVED','pid':pid,'uid':uid,'argv_sha256':digest(cmdline),
         'cgroup_sha256':digest(cgroup),'owner_fixture_criterion':role=='callback',
         'production_owner_verifier':'NOT_VERIFIED'}


def forbidden_call(name,libc,pid,left,right):
 ctypes.set_errno(0)
 if name=='ptrace':result=libc.ptrace(16,pid,None,None)
 else:result=getattr(libc,name)(pid,ctypes.byref(left),1,ctypes.byref(right),1,0)
 return {'return':int(result),'errno':ctypes.get_errno()}

def cleanup_fork_child(pid,fds,reaped=False):
 errors=[];owned=False
 if not reaped:
  try:
   row=os.waitid(os.P_PID,pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
   need(row is None or row.si_pid==pid,'OWNED_FORK_IDENTITY');owned=True
  except BaseException:errors.append('FORK_OWNERSHIP_UNCONFIRMED')
  if owned:
   try:os.kill(pid,signal.SIGKILL)
   except ProcessLookupError:pass
   except BaseException:errors.append('FORK_SIGNAL_UNCONFIRMED')
 for fd in fds:
  if fd is not None:
   try:os.close(fd)
   except BaseException:errors.append('FORK_FD_CLOSE_UNCONFIRMED')
 if not reaped:
  end=time.monotonic()+.2
  try:
   while time.monotonic()<end:
    found,unused=os.waitpid(pid,os.WNOHANG)
    if found==pid:reaped=True;break
    time.sleep(.005)
  except BaseException:pass
  if not reaped:errors.append('FORK_REAP_UNCONFIRMED')
 return errors


def isolated_syscall(name,libc,target,left,right,end):
 # The blacklist's default action is SIGSYS, not necessarily an errno. Keep
 # the observing server alive and execute each forbidden operation only in a
 # tracked fork child. The target remains the server's own synthetic child.
 if not hasattr(libc,name):return {'syscall':name,'status':'NOT_VERIFIED','reason':'LIBC_SYMBOL_ABSENT'}
 read_end,write_end=os.pipe();reaped=False;result=None
 try:worker=os.fork()
 except BaseException:
  for fd in (read_end,write_end):
   try:os.close(fd)
   except BaseException:pass
  raise
 if worker==0:
  try:
   os.close(read_end);raw=canonical(forbidden_call(name,libc,target,left,right))
   position=0
   while position<len(raw):
    count=os.write(write_end,raw[position:]);need(count>0,'SYSCALL_CHILD_SHORT_WRITE');position+=count
   os._exit(0)
  except BaseException:os._exit(3)
 try:
  os.close(write_end);write_end=None
  while True:
   remaining(end);found,status=os.waitpid(worker,os.WNOHANG)
   if found==worker:reaped=True;break
   time.sleep(.005)
  if os.WIFSIGNALED(status):
   sig=os.WTERMSIG(status)
   result={'syscall':name,'status':'PASS_OBSERVED' if sig==signal.SIGSYS else 'NOT_VERIFIED','signal':sig}
   return result
  need(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0,'SYSCALL_CHILD_EXIT')
  raw=os.read(read_end,4097);need(len(raw)<=4096,'SYSCALL_CHILD_BOUND');value=parse(raw)
  need(set(value)=={'return','errno'} and all(type(x) is int for x in value.values()),'SYSCALL_CHILD_SCHEMA')
  result=dict(value,syscall=name,status='PASS_OBSERVED' if value['return']==-1 and value['errno']==errno.EPERM else 'FAIL_OBSERVED')
  return result
 finally:
  errors=cleanup_fork_child(worker,[read_end,write_end],reaped)
  # An unexpectedly successful ATTACH must not leave our synthetic target
  # stopped after its tracer exits. This never names an external process.
  try:os.kill(target,signal.SIGCONT)
  except ProcessLookupError:pass
  except BaseException:errors.append('SYNTHETIC_TARGET_RESUME_UNCONFIRMED')
  if result is not None:
   result['cleanup_errors']=errors;result['cleanup_state']='UNKNOWN' if errors else 'REAPED'
   if errors:result['status']='NOT_VERIFIED'
  if errors:
   try:emit({'event':'SYSCALL_CHILD_CLEANUP_UNCONFIRMED','errors':errors})
   except BaseException:pass


def syscall_denials():
 # No production PID, memory or secret can be selected through configuration.
 libc=ctypes.CDLL(None,use_errno=True);buffer=ctypes.create_string_buffer(b'NONSECRET_PROBE_MEMORY')
 read_end,write_end=os.pipe()
 try:out_read,out_write=os.pipe()
 except BaseException:
  for fd in (read_end,write_end):
   try:os.close(fd)
   except BaseException:pass
  raise
 try:pid=os.fork()
 except BaseException:
  for fd in (read_end,write_end,out_read,out_write):
   try:os.close(fd)
   except BaseException:pass
  raise
 if pid==0:
  try:
   os.close(write_end);os.close(out_read);os.read(read_end,1)
   os.write(out_write,buffer.raw);os._exit(0)
  except BaseException:os._exit(3)
 results=[];cleanup=[];result=None;end=time.monotonic()+2
 try:
  os.close(read_end);read_end=None;os.close(out_write);out_write=None
  class IOVec(ctypes.Structure):_fields_=[('base',ctypes.c_void_p),('length',ctypes.c_size_t)]
  local=ctypes.create_string_buffer(len(buffer.raw));left=IOVec(ctypes.addressof(local),len(buffer.raw))
  right=IOVec(ctypes.addressof(buffer),len(buffer.raw))
  for name in ('ptrace','process_vm_readv','process_vm_writev'):
   row=isolated_syscall(name,libc,pid,left,right,end);results.append(row)
   cleanup.extend(row.get('cleanup_errors',[]))
  os.write(write_end,b'x');os.close(write_end);write_end=None
  sel=None
  try:
   sel=selectors.DefaultSelector();sel.register(out_read,selectors.EVENT_READ)
   need(sel.select(remaining(end)),'CHILD_SENTINEL_DEADLINE')
   observed=os.read(out_read,1024);unchanged=observed==buffer.raw
  finally:
   try:
    if sel is not None:sel.close()
   except BaseException:cleanup.append('FORK_SELECTOR_CLOSE_UNCONFIRMED')
  result={'results':results,'child_memory_unchanged':unchanged,'target':'OWN_NONSECRET_FORK_CHILD',
          'denied_callers':'THREE_TRACKED_FORK_CHILDREN','cleanup_errors':cleanup}
  return result
 finally:
  cleanup.extend(cleanup_fork_child(pid,[read_end,write_end,out_read,out_write]))
  if result is not None:result['cleanup_state']='UNKNOWN' if cleanup else 'REAPED'
  if cleanup:
   try:emit({'event':'SYNTHETIC_TARGET_CLEANUP_UNCONFIRMED','errors':cleanup})
   except BaseException:pass


def connection_budget(config,claim=False):
 # systemd opens this root:root0600 file on stdin/read and stdout/write. The
 # service has no pathname write grant, and other dispatcher processes cannot
 # reset it. One shared inode persists through all service/socket restarts.
 read_info=os.fstat(0);write_info=os.fstat(1)
 need(stat.S_ISREG(read_info.st_mode) and read_info.st_uid==read_info.st_gid==0 and
      stat.S_IMODE(read_info.st_mode)==0o600 and read_info.st_nlink==1 and
      stamp(read_info)==stamp(write_info),'INHERITED_ROOT_BUDGET_FDS')
 fcntl.flock(1,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  os.lseek(0,0,os.SEEK_SET);raw=os.read(0,4097);need(len(raw)<=4096,'BUDGET_BOUND')
  value=parse(raw)
  need(type(value) is dict and set(value)=={'schema','nonce','accepted'} and value['schema']==1 and
       value['nonce']==config['nonce'] and type(value['accepted']) is int and 0<=value['accepted']<=8,'EXACT_BUDGET')
  if claim:
   need(value['accepted']<8,'GLOBAL_EIGHT_CONNECTION_LIMIT');value['accepted']+=1
   raw=canonical(value)+b'\n';os.lseek(1,0,os.SEEK_SET);position=0
   while position<len(raw):
    count=os.write(1,raw[position:]);need(count>0,'BUDGET_SHORT_WRITE');position+=count
   os.ftruncate(1,len(raw));os.fsync(1)
  return value['accepted']
 finally:fcntl.flock(1,fcntl.LOCK_UN)


def server(config,root):
 need(config['role']=='ledger' and os.environ.get('LISTEN_PID')==str(os.getpid()) and
      os.environ.get('LISTEN_FDS')=='1','EXACT_SYSTEMD_INHERITED_FD')
 listener=socket.socket(fileno=3)
 need(listener.family==socket.AF_UNIX and listener.type&socket.SOCK_STREAM and
      listener.getsockname()==root+'/ledger.sock','EXACT_INHERITED_LISTENER')
 if connection_budget(config)>=8:listener.close();return
 end=time.monotonic()+20;seen=set();accepted=0
 emit({'event':'SERVER_READY','own':process(os.getpid()),'listener':endpoint(root+'/ledger.sock'),
       'syscall_denials':syscall_denials()})
 while accepted<8 and connection_budget(config)<8:
  listener.settimeout(remaining(end))
  connection,unused=listener.accept();accepted+=1
  try:
   connection_budget(config,claim=True)
   frame=receive(connection,min(end,time.monotonic()+3))
   need(type(frame) is dict and set(frame)=={'schema','nonce','case','challenge'} and
        frame['schema']==1 and frame['nonce']==config['nonce'] and
        type(frame['case']) is int and 1<=frame['case']<=8 and frame['case'] not in seen and
        frame['challenge']=='PUBLIC_INERT_PROBE','EXACT_NONCE_FRAME')
   seen.add(frame['case'])
   credentials=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
   try:proof=peer_executable(config,root,credentials,frame['case'])
   except BaseException as exc:proof={'status':'NOT_VERIFIED','reason':type(exc).__name__+':'+str(exc)[:100]}
   emit({'event':'PEER_ACCESS_PROOF','case':frame['case'],'proof':proof})
   connection.sendall(canonical(dict(frame,reply='PUBLIC_INERT_REPLY'))+b'\n')
  except BaseException as exc:emit({'event':'SERVER_REJECT','reason':type(exc).__name__})
  finally:connection.close()
 listener.close()


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
 parser.add_argument('--mode',required=True,choices=('server','client'));args=parser.parse_args(argv)
 config,root=load_config(args.config);need(config['mode']==args.mode,'EXACT_HELPER_MODE')
 if args.mode=='server':
  global OUTPUT
  OUTPUT=sys.stderr;server(config,root)
 else:client(config,root)

if __name__=='__main__':main()
