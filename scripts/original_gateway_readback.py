"""Fixed original Git source readback; no code execution, publish or acceptance.
Uses original contract and candidate reader. Not an execution adapter/sandbox.
"""
import hashlib,json,re,subprocess,os,stat
from development_entry_intake import _controlled_candidate_files
from original_gateway_transport import WORKSPACE,REPOSITORY,BRANCH
def _git(*args):
 # Fixed read-only callers below only. Disable optional locks, network protocols,
 # fsmonitor/external diffs, and lazy object fetching; never run generated tests.
 argv=['git','--no-replace-objects','--no-optional-locks','-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','-c','protocol.allow=never','-c','submodule.recurse=false','-C',WORKSPACE]+list(args)
 import os
 env={'PATH':os.defpath,'LC_ALL':'C','GIT_NO_LAZY_FETCH':'1','GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
 return subprocess.check_output(argv,stderr=subprocess.DEVNULL,env=env)
def _raw_worktree_status():
 """No status/diff-files/hash-object: those can execute clean filters.
 Compare HEAD/index metadata and raw working-tree bytes without Git filters.
 A smudged/CRLF checkout is not silently normalized: it stays unverifiable.
 """
 def records(raw, index=False):
  out={}
  for record in raw.split(b'\0'):
   if not record:continue
   meta,path=record.split(b'\t',1);parts=meta.decode('ascii').split()
   path=path.decode('utf-8','strict')
   if path in out or any(x in ('','.','..') for x in path.split('/')):raise ValueError('UNIQUE_SOURCE_PATH_REQUIRED')
   if index:
    mode,oid,stage=parts
    if stage!='0':raise ValueError('UNMERGED_SOURCE_INDEX')
   else:
    mode,kind,oid=parts
    if kind!='blob':raise ValueError('SUBMODULE_READBACK_UNSUPPORTED_NO_EXECUTION')
   if mode not in ('100644','100755','120000') or not re.fullmatch('[0-9a-f]{40}',oid):raise ValueError('REGULAR_SOURCE_INDEX_REQUIRED')
   out[path]=(mode,oid)
  return out
 head=records(_git('ls-tree','-r','-z','--full-tree','HEAD'))
 index=records(_git('ls-files','--stage','-z'),True)
 if head!=index:return b'DIRTY_INDEX'
 if _git('ls-files','--others','--exclude-standard','-z'):return b'UNTRACKED_FILES'
 dirs=[]
 try:
  fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY);dirs.append(fd)
  for name in WORKSPACE.strip('/').split('/'):
   fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);dirs.append(fd)
  root_fd=fd
  for path,(mode,expected) in head.items():
   children=[]
   try:
    parent=root_fd
    for name in path.split('/')[:-1]:
     parent=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);children.append(parent)
    name=path.split('/')[-1];before=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if mode=='120000':
     if not stat.S_ISLNK(before.st_mode):return b'CHANGED_FILE_KIND'
     raw=os.fsencode(os.readlink(name,dir_fd=parent));digest=hashlib.sha1(('blob %d\0'%len(raw)).encode()+raw).hexdigest()
    else:
     if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:return b'UNVERIFIABLE_SOURCE_FILE'
     file_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
     try:
      opened=os.fstat(file_fd)
      if not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1:return b'UNVERIFIABLE_SOURCE_FILE'
      if (opened.st_dev,opened.st_ino)!=(before.st_dev,before.st_ino):return b'CHANGED_FILE_IDENTITY'
      if bool(opened.st_mode&0o111)!=(mode=='100755'):return b'CHANGED_FILE_MODE'
      h=hashlib.sha1(('blob %d\0'%opened.st_size).encode());size=0
      while True:
       chunk=os.read(file_fd,65536)
       if not chunk:break
       h.update(chunk);size+=len(chunk)
      if size!=opened.st_size:return b'CHANGED_FILE_SIZE'
      digest=h.hexdigest()
     finally:os.close(file_fd)
    after=os.stat(name,dir_fd=parent,follow_symlinks=False)
    sig=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns,x.st_mode)
    if sig(before)!=sig(after) or digest!=expected:return b'DIRTY_WORKTREE'
   finally:
    for fd in reversed(children):os.close(fd)
 finally:
  for fd in reversed(dirs):os.close(fd)
 return b''
def _candidate_git(*args):
 if args==('status','--porcelain=v1','--untracked-files=all'):return _raw_worktree_status()
 return _git(*args)
def read_source(supervisor,task_id,attempt_id,operation_id):
 import os
 row=supervisor.db.execute('SELECT * FROM writer_operations WHERE operation_id=? AND task_id=? AND attempt_id=?',(operation_id,task_id,attempt_id)).fetchone()
 if row is None or row['state'] not in ('DISPATCHING','UNKNOWN'):raise ValueError('ORIGINAL_PENDING_GATEWAY_OPERATION_REQUIRED')
 operation=json.loads(row['payload_json']);contract=supervisor.development_contract(task_id)
 before=operation.get('expected_before',{})
 if (operation.get('operation_kind')!='OPENCLAW_DEVELOPMENT_TURN' or before.get('repo')!=REPOSITORY or before.get('branch')!=BRANCH
     or before.get('head')!=contract['target_base_sha'] or contract['target_repository']!=REPOSITORY):raise ValueError('ORIGINAL_SOURCE_CONTRACT_BINDING_REQUIRED')
 if operation.get('requested_after',{}).get('contract_sha256')!=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest():raise ValueError('CURRENT_SOURCE_CONTRACT_REQUIRED')
 if not os.path.isdir(WORKSPACE) or os.path.realpath(WORKSPACE)!=os.path.abspath(WORKSPACE):raise ValueError('ORIGINAL_SOURCE_WORKSPACE_REQUIRED')
 base=contract['target_base_sha']
 if not re.fullmatch('[0-9a-f]{40}',base):raise ValueError('EXACT_BASE_REQUIRED')
 head=_git('rev-parse','--verify','HEAD').decode().strip()
 if not re.fullmatch('[0-9a-f]{40}',head):raise ValueError('EXACT_HEAD_REQUIRED')
 if _git('symbolic-ref','--quiet','HEAD').decode().strip()!='refs/heads/'+BRANCH:raise ValueError('ORIGINAL_SOURCE_BRANCH_REQUIRED')
 if head==base:return {'state':'SOURCE_HEAD_UNCHANGED_EFFECTS_UNKNOWN','operation_id':operation_id,'source_effect_state':row['state'],'development_complete':False}
 _git('merge-base','--is-ancestor',base,head)
 marker=operation['operation_marker']
 message=_git('show','-s','--format=%B',head).decode('utf-8','strict')
 if message.splitlines().count(marker)!=1:raise ValueError('EXACT_OPERATION_COMMIT_MARKER_REQUIRED')
 changed=_git('diff','--no-ext-diff','--no-textconv','--name-only','-z',base,head,'--').decode('utf-8','strict').split('\0')
 changed=[p for p in changed if p]
 allowed=contract['allowed_files']
 if not changed or not set(changed)<=set(allowed):raise ValueError('SOURCE_CHANGED_OUTSIDE_CONTRACT')
 for path in allowed:
  if not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or any(p in ('','.','..') for p in path.split('/')):raise ValueError('CANONICAL_CANDIDATE_PATH_REQUIRED')
  entry=_git('ls-tree',head,'--',path).decode('utf-8','strict')
  if not re.fullmatch(r'100(?:644|755) blob [0-9a-f]{40}\t'+re.escape(path)+r'\n',entry):raise ValueError('REGULAR_SOURCE_BLOB_REQUIRED')
 # Reuse original checkout/remote/clean-worktree and per-file/aggregate bounds.
 # No source manifest or commit supplied by a model is trusted.
 files=_controlled_candidate_files(supervisor,{'task_id':task_id,'target_repository':REPOSITORY,'code_commit':head},WORKSPACE,git_reader=_candidate_git)
 tree=_git('rev-parse','--verify',head+'^{tree}').decode().strip()
 if not re.fullmatch('[0-9a-f]{40}',tree):raise ValueError('EXACT_TREE_REQUIRED')
 if _git('rev-parse','--verify','HEAD').decode().strip()!=head:raise ValueError('SOURCE_CHANGED_DURING_READBACK')
 return {'state':'LOCAL_SOURCE_READ_BACK_NOT_ACCEPTED','task_id':task_id,'attempt_id':attempt_id,'operation_id':operation_id,
  'repository':REPOSITORY,'branch':BRANCH,'base':base,'code_commit':head,'tree':tree,'changed_files':sorted(changed),
  'files':{k:hashlib.sha256(v).hexdigest() for k,v in sorted(files.items())},'source_effect_state':row['state'],
  'tests':'NOT_VERIFIED','publication':'NOT_PROVEN','development_complete':False,'all_changes_attributed_to_task':False,'marker_semantics':'CORRELATION_ONLY_NOT_EXCLUSIVE_AUTHORSHIP',
  'remaining':'Original Gateway source-effect reconciliation and real supported test/publisher evidence; not CHATGPT_NATIVE or fake GIT_CAS'}
