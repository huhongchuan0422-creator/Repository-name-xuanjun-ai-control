"""Explicit, read-only adoption of an already authorized legacy isolation."""
import hashlib,json,os,stat
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
UNIT_ROOT='/etc/systemd/system'
PROOF=frozenset(('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited'))
def read(path,digest=None):
 if os.path.realpath(path)!=path:raise ValueError('ADOPTION_SYMLINK')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(1048577)
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=0o600 or len(raw)>1048576:raise ValueError('ADOPTION_REFERENCE_AUTHORITY')
 if digest is not None and hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('ADOPTION_REFERENCE_CHANGED')
 return raw
def bind(adapter,plan):
 ref=plan.get('legacy_isolation')
 keys={'directory','receipt_sha256','original_plan_path','original_plan_sha256','database_sha256','legacy_state_sha256'}
 if not isinstance(ref,dict) or set(ref)!=keys:raise ValueError('EXACT_ISOLATION_ADOPTION_REFERENCE')
 for k in ('receipt_sha256','original_plan_sha256','database_sha256','legacy_state_sha256'):
  v=ref[k]
  if not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v):raise ValueError('ADOPTION_DIGEST')
 d=ref['directory'];expected=BASE+'/legacy-isolation-'+plan['transaction_id']
 if d!=expected or os.path.realpath(d)!=d:raise ValueError('ADOPTION_TRANSACTION_DIRECTORY')
 s=os.lstat(d)
 if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700:raise ValueError('ADOPTION_DIRECTORY_AUTHORITY')
 original_path=ref['original_plan_path']
 if not isinstance(original_path,str) or not original_path.startswith(BASE+'/plan-p2pkg-'):raise ValueError('ADOPTION_ORIGINAL_PLAN_SCOPE')
 original=json.loads(read(original_path,ref['original_plan_sha256']).decode())
 clean=dict(plan);del clean['legacy_isolation']
 if original.get('transaction_id')!=plan['transaction_id'] or original.get('cutover')!=clean:raise ValueError('ADOPTION_PLAN_MISMATCH')
 receipt=json.loads(read(d+'/owner-isolation-receipt.json',ref['receipt_sha256']).decode())
 if (receipt.get('state')!='AUTHORIZED_OLD_SERVICES_ISOLATED' or receipt.get('transaction_id')!=plan['transaction_id']
     or receipt.get('core_plan_sha256')!=ref['original_plan_sha256'] or receipt.get('install') is not False
     or receipt.get('fence_mutation') is not False or receipt.get('writer_admission') is not False):raise ValueError('ADOPTION_RECEIPT_MISMATCH')
 state=json.loads(read(d+'/legacy-units.json',ref['legacy_state_sha256']).decode())
 if set(state)!= {'schema','units','source_before'} or state['schema']!=1 or set(state['units'])!=set(clean['legacy_bindings']):raise ValueError('ADOPTION_STATE_SCHEMA')
 for unit,binding in clean['legacy_bindings'].items():
  x=state['units'][unit];path=UNIT_ROOT+'/'+unit
  if set(x)!= {'path','backup','sha256','mode','uid','gid','was_active'} or x['path']!=path or x['backup']!=d+'/'+unit+'.backup' or x['uid']!=0 or x['gid']!=0 or x['mode']!=0o644 or type(x['was_active']) is not bool or x['sha256']!=binding['sha256'] or binding['fragment_path']!=path or binding['cgroup']!='/system.slice/'+unit:raise ValueError('ADOPTION_BACKUP_BINDING')
  read(x['backup'],x['sha256'])
  if not os.path.islink(path) or os.readlink(path)!='/dev/null':raise ValueError('ADOPTION_MASK_CHANGED')
 source=clean['source']
 if source!=original['cutover']['source'] or os.path.realpath(source)!=source:raise ValueError('ADOPTION_DATABASE_PATH')
 if os.path.exists(source+'-wal') and os.stat(source+'-wal').st_size:raise ValueError('ADOPTION_NONEMPTY_WAL')
 fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());h=hashlib.sha256()
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=1002:raise ValueError('ADOPTION_DATABASE_AUTHORITY')
  for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
  end=os.fstat(f.fileno())
  if (s.st_size,s.st_mtime_ns)!=(end.st_size,end.st_mtime_ns) or h.hexdigest()!=ref['database_sha256']:raise ValueError('ADOPTION_DATABASE_CHANGED')
 for k in ('rollback_snapshot','staged_generation'):
  p=clean[k]
  if not p.startswith('/var/lib/xuanjun-development/') or os.path.realpath(p)!=p or os.path.lexists(p):raise ValueError('ADOPTION_DATABASE_EFFECT_ALREADY_PRESENT')
 # Switch only in-memory adapter scope; never copy or replace original journal.
 previous=(adapter.directory,adapter.state_path)
 adapter.directory=d;adapter.state_path=d+'/legacy-units.json'
 try:
  measured=adapter.measure_quiescence(clean['legacy_bindings']);proof=measured.get('proof')
  if not isinstance(proof,dict) or set(proof)!=PROOF or any(proof[k] is not True for k in PROOF):raise ValueError('ADOPTION_LIVE_QUIESCENCE_FAILED')
 except Exception:
  adapter.directory,adapter.state_path=previous;raise
 adapter._adoption_plan=plan
 return True
