"""Transactional publication of the private mirror and GH directory, without overwrites."""
import ctypes,errno,hashlib,json,os,pathlib,re,shutil,stat,subprocess,tempfile
from ledger_cutover_transaction import _atomic_receipt
from p2_bootstrap_files import private_read,hash_bytes
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
TARGETS=('/var/lib/xuanjun-development/control.git','/var/lib/xuanjun-development/service-home/.config/gh')
def rename_absent(source,target):
 libc=ctypes.CDLL(None,use_errno=True)
 fn=libc.renameat2;fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
 if fn(-100,os.fsencode(source),-100,os.fsencode(target),1)!=0:
  value=ctypes.get_errno();raise OSError(value,os.strerror(value))
class PublisherBootstrap:
 def __init__(self,directory):self.directory=directory;self.journal=directory+'/publisher-bootstrap.json'
 def authority(self):
  s=os.lstat(self.directory)
  if os.geteuid()!=0 or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700 or not stat.S_ISDIR(s.st_mode) or os.path.realpath(self.directory)!=self.directory:raise ValueError('PUBLISHER_ROOT_JOURNAL')
 def prepare(self,reference):
  self.authority()
  if not isinstance(reference,dict) or set(reference)!={'path','sha256','source_commit','source_tree'} or not reference['path'].startswith('/var/lib/xuanjun-p2-preparation/'):raise ValueError('PUBLISHER_EXACT_REFERENCE')
  raw=private_read(reference['path'])
  if hash_bytes(raw)!=reference['sha256']:raise ValueError('PUBLISHER_MANIFEST_HASH')
  data=json.loads(raw.decode())
  if not isinstance(data.get('source_commit'),str) or re.fullmatch(r'[0-9a-f]{40}',data['source_commit']) is None or not isinstance(data.get('source_tree'),str) or re.fullmatch(r'[0-9a-f]{40}',data['source_tree']) is None:raise ValueError('PUBLISHER_COMMIT_FORMAT')
  if data.get('schema')!=1 or data.get('repository')!=REPO or data.get('source_commit')!=reference['source_commit'] or data.get('source_tree')!=reference['source_tree'] or data.get('canonical_targets_applied') is not False:raise ValueError('PUBLISHER_SOURCE_BINDING')
  if (data.get('target_mirror'),data.get('target_gh_hosts'))!=(TARGETS[0],TARGETS[1]+'/hosts.yml'):raise ValueError('PUBLISHER_TARGET_SCOPE')
  root=os.path.dirname(reference['path'])
  for item in (data['bundle'],data['github_hosts']):
   if os.path.dirname(item['path'])!=root:raise ValueError('PUBLISHER_SOURCE_SCOPE')
   # Bundle is bounded separately; private_read's 1MiB cap is deliberate for credential files.
  config=private_read(data['github_hosts']['path'])
  if hash_bytes(config)!=data['github_hosts']['sha256'] or re.fullmatch(br'github.com:\n    user: huhongchuan0422-creator\n    git_protocol: https\n    oauth_token: github_pat_[A-Za-z0-9_]+\n',config) is None:raise ValueError('PUBLISHER_GH_CONFIG')
  bundle=data['bundle']['path'];s=os.lstat(bundle)
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or os.path.realpath(bundle)!=bundle or s.st_size!=data['bundle']['size'] or s.st_size>134217728:raise ValueError('PUBLISHER_BUNDLE_IDENTITY')
  with open(bundle,'rb') as f:
   h=hashlib.sha256()
   for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
  if h.hexdigest()!=data['bundle']['sha256']:raise ValueError('PUBLISHER_BUNDLE_HASH')
  if any(os.path.lexists(target) for target in TARGETS):raise ValueError('HOLD_PUBLISHER_TARGET_PRESENT')
  return data,config
 @staticmethod
 def sync(directory):
  fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(fd)
  finally:os.close(fd)
 @staticmethod
 def command(args):
  env={'PATH':'/usr/bin:/bin','LANG':'C','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_NO_REPLACE_OBJECTS':'1','GIT_TERMINAL_PROMPT':'0'}
  p=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
  if p.returncode:raise ValueError('PUBLISHER_GIT_SEED_FAILED')
  return p.stdout.decode().strip()
 @staticmethod
 def fingerprint(root):
  entries=[];total=0
  for parent,dirs,files in os.walk(root,followlinks=False):
   s=os.lstat(parent)
   if not stat.S_ISDIR(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(1003,1003,0o700) or os.path.realpath(parent)!=parent:raise ValueError('PUBLISHER_DIRECTORY_IDENTITY')
   entries.append([os.path.relpath(parent,root),'DIR'])
   for name in sorted(files):
    path=parent+'/'+name;fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
     s=os.fstat(f.fileno())
     if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(1003,1003,0o600):raise ValueError('PUBLISHER_FILE_IDENTITY')
     h=hashlib.sha256()
     for chunk in iter(lambda:f.read(65536),b''):
      total+=len(chunk)
      if total>134217728:raise ValueError('PUBLISHER_CONTENT_LIMIT')
      h.update(chunk)
     end=os.fstat(f.fileno())
     if (s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(end.st_size,end.st_mtime_ns,end.st_ctime_ns):raise ValueError('PUBLISHER_FILE_CHANGED')
    entries.append([os.path.relpath(path,root),h.hexdigest()])
   if len(entries)>10000:raise ValueError('PUBLISHER_ENTRY_LIMIT')
  return hash_bytes(json.dumps(sorted(entries),separators=(',',':')).encode())
 def apply(self,reference):
  if os.path.lexists(self.journal):raise ValueError('HOLD_PUBLISHER_JOURNAL_PRESENT')
  data,config=self.prepare(reference);rows=[]
  for index,target in enumerate(TARGETS):
   parent=os.path.dirname(target);s=os.lstat(parent)
   expected=(0,0,0o755) if index==0 else (1003,1003,0o700)
   if not stat.S_ISDIR(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=expected or os.path.realpath(parent)!=parent:raise ValueError('PUBLISHER_PARENT')
   stage=tempfile.mkdtemp(prefix='.p2-publisher-',dir=parent)
   if index==0:
    self.command(['/usr/bin/git','init','--bare','--quiet',stage])
    git=['/usr/bin/git','--git-dir='+stage,'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','credential.helper=']
    self.command(git+['-c','protocol.file.allow=always','fetch','--quiet','--no-tags',data['bundle']['path'],'refs/xuanjun-preparation/'+data['source_commit']+':refs/heads/bootstrap-source'])
    self.command(git+['symbolic-ref','HEAD','refs/heads/bootstrap-source'])
    self.command(git+['config','remote.origin.url','https://github.com/'+REPO+'.git'])
    self.command(git+['config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*'])
    if self.command(git+['rev-parse','HEAD^{tree}'])!=data['source_tree']:raise ValueError('PUBLISHER_SEED_TREE')
   else:
    fd=os.open(stage+'/hosts.yml',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(config);f.flush();os.fsync(f.fileno())
   for directory,dirs,files in os.walk(stage):
    for name in files:
     path=directory+'/'+name
     if '/hooks' in directory:os.unlink(path);continue
     os.chown(path,1003,1003);os.chmod(path,0o600)
    os.chown(directory,1003,1003);os.chmod(directory,0o700)
   fingerprint=self.fingerprint(stage);s=os.lstat(stage)
   row={'target':target,'stage':stage,'dev':s.st_dev,'ino':s.st_ino,'fingerprint':fingerprint,'state':'PUBLISH_INTENT'};rows.append(row)
   _atomic_receipt(self.journal,{'schema':1,'directories':rows})
   rename_absent(stage,target);self.sync(parent);row['state']='PUBLISHED';_atomic_receipt(self.journal,{'schema':1,'directories':rows})
 def rollback_rows(self):
  if not os.path.lexists(self.journal):return []
  self.authority();value=json.loads(private_read(self.journal).decode());rows=value['directories'];seen=set()
  if value.get('schema')!=1 or not isinstance(rows,list) or len(rows)>2:raise ValueError('PUBLISHER_ROLLBACK_SCHEMA')
  for row in rows:
   target=row['target'];stage=row['stage']
   if target not in TARGETS or target in seen or os.path.dirname(stage)!=os.path.dirname(target) or not os.path.basename(stage).startswith('.p2-publisher-'):raise ValueError('PUBLISHER_ROLLBACK_SCOPE')
   seen.add(target)
   for path in (target,stage):
    if not os.path.lexists(path):continue
    s=os.lstat(path)
    if (s.st_dev,s.st_ino)!=(row['dev'],row['ino']) or self.fingerprint(path)!=row['fingerprint']:raise ValueError('HOLD_PUBLISHER_DIRECTORY_CHANGED')
  return rows
 def rollback(self):
  rows=self.rollback_rows()
  for row in reversed(rows):
   for path in (row['target'],row['stage']):
    if os.path.lexists(path):shutil.rmtree(path)
   self.sync(os.path.dirname(row['target']));row['state']='RESTORED_ABSENT';_atomic_receipt(self.journal,{'schema':1,'directories':rows})
