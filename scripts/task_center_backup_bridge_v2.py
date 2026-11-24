"""Two-phase candidate for existing task-center host; not installed.

Trusted host calls execute outside its SQLite transaction. Remote readback
precedes BEGIN; nonblocking original producer lock spans the host transaction.
No request may supply an attestation or verified boolean.
"""
import fcntl,hashlib,json,math,threading,time
import backup_component_hostcycle as cm

class PreparedBackupAssessment:
 def __init__(self,component,tenant_id,required_context,db,clock=time.time):
  if type(component) is not cm.BackupComponent:raise ValueError('component required')
  self.component=component;self.tenant_id=tenant_id;self.required_context=frozenset(required_context);self.db=db;self.clock=clock
  self._guard=threading.Lock();self._prepared=None
 def _binding(self,binding):
  checks=binding['applicability']['required_checks']
  if not isinstance(checks,list) or not checks or checks!=sorted(set(checks)) or not set(checks)<=self.required_context:raise ValueError('invalid checks')
  resolved,_=self.component.plan(binding)
  if resolved['tenant_id']!=self.tenant_id:raise ValueError('tenant mismatch')
  for k in cm.BINDING:
   if k!='tenant_id' and resolved[k]!=binding.get(k):raise ValueError('binding mismatch')
  return resolved,list(checks)
 def _reservation(self,host,value,binding):
  # Read the original issued reference, not a caller-provided reference claim.
  ref=host._reference(value['task_id'],value['attempt_id'],value['event_id'])
  task=host._current_task(value['task_id'],value['attempt_id'],self.clock())
  for k in ('task_id','attempt_id','handoff_id','handoff_version','backup_cycle_id'):
   if ref.get(k)!=value.get(k) or binding.get(k)!=value.get(k):raise ValueError('reference mismatch')
  if ref.get('fence')!=task['fence'] or ref.get('epoch')!=task['epoch']:raise ValueError('stale writer')
 def _snapshot(self,binding,resolved):
  home=self.component.home;p=self.component.cyclepath(binding['backup_cycle_id'])
  if (home/'active.json').exists() or (home/'pending.json').exists():raise ValueError('unresolved effects')
  marker_bytes=(home/'settlement.json').read_bytes();marker=json.loads(marker_bytes)
  if marker!={'cycle_id':binding['backup_cycle_id'],'state':'settled'}:raise ValueError('settlement mismatch')
  record_bytes=(p/'record.json').read_bytes();record=json.loads(record_bytes);manifest=(p/'manifest.json').read_bytes()
  if (record.get('state')!='verified' or record.get('cycle_id')!=binding['backup_cycle_id'] or record.get('binding')!=resolved or
      record.get('manifest_sha256')!=binding['backup_manifest_sha256'] or hashlib.sha256(manifest).hexdigest()!=binding['backup_manifest_sha256']):raise ValueError('version mismatch')
  return hashlib.sha256(marker_bytes+b'\0'+record_bytes+b'\0'+manifest).hexdigest(),record
 def execute(self,host,session,value,preflight_binding):
  """Readback outside transaction, then run existing host.record under lock.

  preflight_binding is only a selector; HostContract must independently resolve
  trusted current reservation and contract. Caller cannot supply evidence.
  """
  if host.db is not self.db or self.db.in_transaction:raise RuntimeError('outside-transaction host required')
  if not self._guard.acquire(False):raise RuntimeError('assessment busy')
  lock=None
  try:
   self._prepared=None
   try:
    self._reservation(host,value,preflight_binding)
    resolved,checks=self._binding(preflight_binding)
    result=self.component.assess(preflight_binding,preflight_binding['backup_cycle_id'],preflight_binding['backup_manifest_sha256'],self.clock())
    if self.db.in_transaction:raise RuntimeError('readback entered transaction')
    if result is not None:
     lock=(self.component.home/'run.lock').open('r')
     try:fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
     except BlockingIOError:lock.close();lock=None;result=None
     if result is not None:
      version,record=self._snapshot(preflight_binding,resolved)
      if result['result']!=record.get('result') or result['cycle_at']!=record.get('cycle_at'):raise ValueError('readback mismatch')
      key=json.dumps(preflight_binding,sort_keys=True,separators=(',',':'))
      self._prepared=(key,version,result,checks)
   except Exception:
    self._prepared=None
    if lock is not None:
     fcntl.flock(lock,fcntl.LOCK_UN);lock.close();lock=None
    if self.db.in_transaction:raise RuntimeError('preflight left transaction open')
   return host.record(session,value)
  finally:
   self._prepared=None
   if lock is not None:
    fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
   self._guard.release()
 def __call__(self,binding):
  unknown={'state':'UNKNOWN','missing':[],'cycle_at':None}
  if not self.db.in_transaction or self._prepared is None:return unknown
  try:
   key,version,result,checks=self._prepared
   if json.dumps(binding,sort_keys=True,separators=(',',':'))!=key:return unknown
   resolved,current=self._binding(binding)
   if current!=checks:return unknown
   current_version,record=self._snapshot(binding,resolved)
   if current_version!=version or result['result']!=record.get('result'):return unknown
   now=self.clock();stamp=result['cycle_at']
   if type(now) not in (int,float) or type(stamp) not in (int,float) or not math.isfinite(now) or not math.isfinite(stamp) or not 0<=now-stamp<=300:return unknown
   missing=set(checks)
   if 'SOURCE' in result['artifact_categories']:missing.discard('SOURCE')
   if not missing:return unknown
   return {'state':'INCOMPLETE','missing':sorted(missing),'cycle_at':stamp}
  except Exception:return unknown
