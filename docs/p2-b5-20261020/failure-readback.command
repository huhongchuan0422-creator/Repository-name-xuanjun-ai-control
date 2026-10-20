sudo -n /usr/bin/python3 -I -B -S - <<'B5_FIXED_FAILURE_READBACK'
"""Fixed two-directory failure readback candidate. No directory enumeration/writes."""
import hashlib,json,os,pwd,re,signal,stat,sys
ROOTS=('/home/admin/p2-b5-ws-anchor-candidate-v1-20261021','/home/admin/p2-b5-ws-anchors-v1-20261021')
RECEIPTS=('bootstrap-result.json','host-result.json','child-receipt.json')
METADATA=('report.json','materials.tar')
LIMIT=65536
class Hold(Exception):pass
class Deadline(Hold):pass
def identity(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def metadata(s):return dict(device=s.st_dev,inode=s.st_ino,mode=oct(stat.S_IMODE(s.st_mode)),uid=s.st_uid,gid=s.st_gid,nlink=s.st_nlink,bytes=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,type='DIRECTORY' if stat.S_ISDIR(s.st_mode) else 'REGULAR' if stat.S_ISREG(s.st_mode) else 'SPECIAL_OR_LINK')
def pairs(rows):
 out={}
 for k,v in rows:
  if k in out:raise Hold('DUPLICATE_JSON_KEY')
  out[k]=v
 return out
def summary(obj):
 # Never emit arbitrary receipt text, paths, config, credentials or raw exceptions.
 if not isinstance(obj,dict):raise Hold('RECEIPT_NOT_OBJECT')
 out={}
 enums={'state':{'HOLD','HOLD_RETAIN_OUTPUT','HOLD_INPUT_OR_OUTPUT_UNKNOWN','RETURNED','MATERIALS_WRITTEN_AWAIT_PARENT','MATERIALS_ONLY_NOT_CLOSURE'},'stage':{'FULL_INPUT_VERIFY','RETAINED_ANALYSIS','WRITE_OUTPUTS','OUTPUTS_WRITTEN'},'sdk':{'NOT_EXECUTED'},'cp11':{'NOT_EXECUTED'},'dependency_closure':{'UNKNOWN'},'original_inputs':{'UNCHANGED'},'error_type':{'FileExistsError','ValueError','Hold','PermissionError','OSError','TimeoutError','FileNotFoundError'}}
 for k,allowed in enums.items():
  if k in obj:out[k]=obj[k] if isinstance(obj[k],str) and obj[k] in allowed else 'REDACTED_UNRECOGNIZED'
 for k in ('exit_code','errno','child_wait_status','materials_bytes','selected_bytes'):
  if k in obj and type(obj[k]) is int and abs(obj[k])<=1073741824:out[k]=obj[k]
 for k in ('materials_sha256','report_sha256'):
  if isinstance(obj.get(k),str) and re.fullmatch('[0-9a-f]{64}',obj[k]):out[k]=obj[k]
 return out

def inspect_file(parent,name,read):
 try:before=os.stat(name,dir_fd=parent,follow_symlinks=False)
 except FileNotFoundError:return {'status':'ABSENT'}
 result={'status':'METADATA_ONLY','metadata':metadata(before)}
 if not read:return result
 if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:raise Hold('RECEIPT_TYPE_OR_LINK')
 if before.st_size>LIMIT:raise Hold('RECEIPT_SIZE_BOUND')
 fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
 try:
  opened=os.fstat(fd)
  if identity(before)!=identity(opened):raise Hold('RECEIPT_CHANGED_BEFORE_READ')
  chunks=[];left=LIMIT+1
  while left:
   raw=os.read(fd,min(left,8192))
   if not raw:break
   chunks.append(raw);left-=len(raw)
  raw=b''.join(chunks)
  after=os.fstat(fd);path_after=os.stat(name,dir_fd=parent,follow_symlinks=False)
  if len(raw)>LIMIT:raise Hold('RECEIPT_SIZE_BOUND')
  if len(raw)!=before.st_size or identity(before)!=identity(after) or identity(after)!=identity(path_after):raise Hold('RECEIPT_CHANGED_DURING_READ')
  result.update(status='READ_STABLE',sha256=hashlib.sha256(raw).hexdigest(),read_bytes=len(raw),identity_before_after='MATCH')
  try:result['receipt_summary']=summary(json.loads(raw.decode('utf8'),object_pairs_hook=pairs))
  except (ValueError,UnicodeError,Hold,RecursionError) as exc:
   if isinstance(exc,Deadline):raise
   result['json']='INVALID_OR_UNSAFE';result['status']='READ_STABLE_JSON_INVALID'
  return result
 finally:os.close(fd)

def inspect_root(path,allowed):
 fds=[];bindings=[];result={'path':path,'status':'QUERY_INCOMPLETE','files':{}}
 try:
  fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);fds.append(fd)
  for part in path.strip('/').split('/'):
   try:s=os.stat(part,dir_fd=fd,follow_symlinks=False)
   except FileNotFoundError:result['status']='ABSENT';return result
   if not stat.S_ISDIR(s.st_mode):raise Hold('PATH_NOT_DIRECTORY_OR_SYMLINK')
   if s.st_uid not in allowed or stat.S_IMODE(s.st_mode)&0o022:raise Hold('PATH_OWNER_OR_WRITE_PROTECTION')
   nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);fds.append(nxt)
   if identity(s)!=identity(os.fstat(nxt)):raise Hold('DIRECTORY_CHANGED_BEFORE_OPEN')
   bindings.append((fd,part,nxt,s));fd=nxt
  result['metadata']=metadata(os.fstat(fd))
  for name in RECEIPTS+METADATA:
   try:
    result['files'][name]=inspect_file(fd,name,name in RECEIPTS)
   except (OSError,Hold) as exc:
    if isinstance(exc,Deadline):raise
    result['files'][name]={'status':'UNAVAILABLE_OR_UNSAFE','error_type':type(exc).__name__,'errno':getattr(exc,'errno',None)}
    result['status']='QUERY_INCOMPLETE'
  for parent,name,child,before in bindings:
   if identity(before)!=identity(os.fstat(child)) or identity(before)!=identity(os.stat(name,dir_fd=parent,follow_symlinks=False)):raise Hold('DIRECTORY_CHANGED_DURING_QUERY')
  if all(v['status'] in ('ABSENT','METADATA_ONLY','READ_STABLE') for v in result['files'].values()):result['status']='READBACK_COMPLETE_NOT_INSTALL_SUCCESS'
 except (OSError,Hold) as exc:
  if isinstance(exc,Deadline):raise
  result.update(error_type=type(exc).__name__,errno=getattr(exc,'errno',None))
 finally:
  for fd in reversed(fds):os.close(fd)
 return result

def main():
 if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or sys.version_info[:3]!=(3,6,8):raise Hold('FIXED_HOST_ROOT_PYTHON368')
 admin=pwd.getpwnam('admin')
 def timeout(signum,frame):raise Deadline('QUERY_TIME_BOUND')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(15)
 results=[]
 try:
  for path in ROOTS:results.append(inspect_root(path,(0,admin.pw_uid)))
  code=2 if any(r['status']=='QUERY_INCOMPLETE' for r in results) else 0
  print(json.dumps({'scope':'FIXED_B5_FAILURE_READBACK_ONLY','directories':results,'installation_state':'UNKNOWN','sdk':'NOT_EXECUTED','recovery':'HOLD_NO_RETRY_NO_CLEANUP'},sort_keys=True));return code
 finally:signal.alarm(0)
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as exc:
  print(json.dumps({'state':'QUERY_INCOMPLETE','error_type':type(exc).__name__,'errno':getattr(exc,'errno',None),'installation_state':'UNKNOWN','sdk':'NOT_EXECUTED'}));sys.exit(2)
B5_FIXED_FAILURE_READBACK
