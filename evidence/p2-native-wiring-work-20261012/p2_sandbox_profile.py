"""Protected, narrow sandbox profile transaction; unknown profile changes hold rollback."""
import copy,json,os,stat,tempfile
from ledger_cutover_transaction import _atomic_receipt
from p2_bootstrap_files import private_read,hash_bytes
PROFILE='/home/xuanjun_dev/.openclaw/openclaw.json'
IDENTITY=(1002,1002,0o600)
IMAGE='sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d'
PLUGIN='xuanjun-p2-native-controller'
def decode(raw):
 def pairs(items):
  value={}
  for key,item in items:
   if key in value:raise ValueError('PROFILE_DUPLICATE_KEY')
   value[key]=item
  return value
 value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
 if not isinstance(value,dict):raise ValueError('PROFILE_OBJECT')
 return value
def policy(old,new):
 expected=copy.deepcopy(old)
 entries=expected.get('agents',{}).get('entries')
 if not isinstance(entries,dict):raise ValueError('PROFILE_EXACT_AGENT_ENTRIES')
 for name,access in (('developer','rw'),('platform-engineer','ro')):
  item=entries.get(name)
  if not isinstance(item,dict):raise ValueError('PROFILE_ROLE_MISSING')
  sandbox=item.setdefault('sandbox',{})
  if not isinstance(sandbox,dict):raise ValueError('PROFILE_SANDBOX_OBJECT')
  sandbox.update(mode='all',workspaceAccess=access,scope='agent')
  docker=sandbox.setdefault('docker',{})
  if not isinstance(docker,dict):raise ValueError('PROFILE_DOCKER_OBJECT')
  docker.update(image=IMAGE,user='1002:1002',network='none',readOnlyRoot=True,capDrop=['ALL'],binds=[],tmpfs=[])
 if expected!=new:raise ValueError('PROFILE_POLICY_SCOPE')
 return expected
def stable(raw):
 value=decode(raw)
 plugins=value.get('plugins')
 if isinstance(plugins,dict):
  for name in ('entries','installs'):
   section=plugins.get(name)
   if isinstance(section,dict):
    section.pop(PLUGIN,None)
    if not section:plugins.pop(name,None)
  if isinstance(plugins.get('allow'),list):
   plugins['allow']=[p for p in plugins['allow'] if p!=PLUGIN]
   if not plugins['allow']:plugins.pop('allow')
  if not plugins:value.pop('plugins',None)
 meta=value.get('meta')
 if isinstance(meta,dict):
  for name in ('lastTouchedVersion','lastTouchedAt'):meta.pop(name,None)
  if not meta:value.pop('meta',None)
 return value
def read_profile():
 if os.path.realpath(PROFILE)!=PROFILE:raise ValueError('PROFILE_SYMLINK')
 fd=os.open(PROFILE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(1048577);end=os.fstat(f.fileno())
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=IDENTITY or len(raw)>1048576 or (s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(end.st_size,end.st_mtime_ns,end.st_ctime_ns):raise ValueError('PROFILE_IDENTITY')
 decode(raw);return raw
def publish(raw):
 parent=os.path.dirname(PROFILE);s=os.lstat(parent)
 if not stat.S_ISDIR(s.st_mode) or s.st_uid!=IDENTITY[0] or s.st_mode&0o022 or os.path.realpath(parent)!=parent:raise ValueError('PROFILE_PARENT')
 fd,path=tempfile.mkstemp(prefix='.p2-profile-',dir=parent)
 try:
  with os.fdopen(fd,'wb') as f:
   f.write(raw);f.flush();os.fchown(f.fileno(),IDENTITY[0],IDENTITY[1]);os.fchmod(f.fileno(),IDENTITY[2]);os.fsync(f.fileno())
  os.replace(path,PROFILE)
  fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(fd)
  finally:os.close(fd)
 finally:
  if os.path.lexists(path):os.unlink(path)
class SandboxProfile:
 def __init__(self,directory):self.directory=directory;self.journal=directory+'/sandbox-profile.json';self.backup=directory+'/sandbox-profile-original.json';self.candidate=directory+'/sandbox-profile-candidate.json'
 def authority(self):
  s=os.lstat(self.directory)
  if os.geteuid()!=0 or not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700 or os.path.realpath(self.directory)!=self.directory:raise ValueError('PROFILE_ROOT_AUTHORITY')
 def prepare(self,ref):
  self.authority()
  if not isinstance(ref,dict) or set(ref)!={'path','sha256','original_sha256'} or not isinstance(ref['path'],str) or not ref['path'].startswith('/var/lib/xuanjun-p2-preparation/'):raise ValueError('PROFILE_EXACT_REFERENCE')
  old=read_profile();new=private_read(ref['path'])
  if hash_bytes(old)!=ref['original_sha256'] or hash_bytes(new)!=ref['sha256']:raise ValueError('PROFILE_REFERENCE_HASH')
  policy(decode(old),decode(new));return old,new
 def apply(self,ref):
  if any(os.path.lexists(p) for p in (self.journal,self.backup,self.candidate)):raise ValueError('PROFILE_JOURNAL_PRESENT')
  old,new=self.prepare(ref)
  for path,raw in ((self.backup,old),(self.candidate,new)):
   fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  row={'schema':1,'original_sha256':hash_bytes(old),'candidate_sha256':hash_bytes(new),'current_sha256':hash_bytes(new),'state':'APPLY_INTENT'}
  _atomic_receipt(self.journal,row)
  if read_profile()!=old:raise ValueError('HOLD_PROFILE_CHANGED_BEFORE_APPLY')
  publish(new);row['state']='APPLIED';_atomic_receipt(self.journal,row)
 def row(self):
  self.authority();row=decode(private_read(self.journal))
  old=private_read(self.backup);candidate=private_read(self.candidate)
  if row.get('schema')!=1 or hash_bytes(old)!=row['original_sha256'] or hash_bytes(candidate)!=row['candidate_sha256']:raise ValueError('PROFILE_JOURNAL_HASH')
  policy(decode(old),decode(candidate));return row,old,candidate
 def capture(self):
  if not os.path.lexists(self.journal):return
  row,old,candidate=self.row();raw=read_profile()
  if row['state']=='APPLY_INTENT' and raw==old:return
  if row['state']=='RESTORED':
   if raw!=old:raise ValueError('HOLD_PROFILE_RESTORED_CHANGED')
   return
  if stable(raw)!=stable(candidate):raise ValueError('HOLD_PROFILE_UNEXPECTED_CONFIG_CHANGE')
  row['current_sha256']=hash_bytes(raw);row['state']='CLI_CAPTURED';_atomic_receipt(self.journal,row)
 def rollback_check(self):
  if not os.path.lexists(self.journal):return None
  row,old,candidate=self.row();raw=read_profile()
  allowed={row['current_sha256']}
  if row['state']=='APPLY_INTENT':allowed.add(row['original_sha256'])
  if row['state']=='RESTORED':allowed={row['original_sha256']}
  if hash_bytes(raw) not in allowed:raise ValueError('HOLD_PROFILE_CHANGED')
  return row,old
 def rollback(self):
  checked=self.rollback_check()
  if checked is None:return
  row,old=checked
  if read_profile()!=old:publish(old)
  row['state']='RESTORED';row['current_sha256']=row['original_sha256'];_atomic_receipt(self.journal,row)
