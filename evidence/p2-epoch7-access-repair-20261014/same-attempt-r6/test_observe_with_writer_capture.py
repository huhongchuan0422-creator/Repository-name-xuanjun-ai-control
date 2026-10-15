"""Public-cache synthetic tests. No host observation, services or probe execution."""
import ast,contextlib,copy,hashlib,io,json,pathlib,signal,sys,types,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
BASE=HERE.parents[1]
d=types.ModuleType('same_attempt_under_test');d.__file__=str(HERE/'observe_with_writer_capture.py')
exec(compile(pathlib.Path(d.__file__).read_bytes(),d.__file__,'exec'),d.__dict__)
OLD=HERE.parent/'writer-observation-readback-r5-candidate'
oldtests=types.ModuleType('old_tests');oldtests.__file__=str(OLD/'test_diagnose_writer_pair.py')
exec(compile(pathlib.Path(oldtests.__file__).read_bytes(),oldtests.__file__,'exec'),oldtests.__dict__)

@contextlib.contextmanager
def nullcontext(value=None):yield value

def fake_capture():
 c=d.SameAttemptCapture(types.SimpleNamespace());c.functions={'validate':lambda row:row,'digest':d.digest};c.raw_pair=[oldtests.row(),oldtests.row()];c.units=('test.service',);c.masks=('/etc/systemd/system/test.service',);c.calls=2;return c

class ProjectionTests(unittest.TestCase):
 def test_equal(self):self.assertEqual(fake_capture().projection()['pair_state'],'EQUAL')
 def test_typed_difference(self):
  c=fake_capture();c.raw_pair[0]['manager']['fixture']=True;c.raw_pair[1]['manager']['fixture']=1;p=c.projection();self.assertFalse(p['exact_pair_equal']);self.assertIn('manager',p['changed_sections'])
 def test_before_only_unknown(self):
  c=fake_capture();c.raw_pair.pop();self.assertEqual(c.projection()['capture_state'],'UNKNOWN_NOT_REACHED')
 def test_invalid_pair_unknown(self):
  c=fake_capture();c.functions['validate']=lambda r:(_ for _ in ()).throw(ValueError('PRIVATE'));p=c.projection();self.assertEqual(p['capture_state'],'UNKNOWN');self.assertNotIn('PRIVATE',repr(p))
 def test_original_hold_never_success(self):
  text,code=d.envelope({'success':False},fake_capture(),'a'*16,'b'*32,{});self.assertEqual(code,2);self.assertFalse(json.loads(text)['success'])
 def test_original_success_preserved(self):
  o={'success':True,'diagnostic_receipt_sha256':'a'*64,'observation':{'private_file_sha256':'b'*64}};text,code=d.envelope(o,fake_capture(),'a'*16,'b'*32,{});self.assertEqual(json.loads(text)['original_result'],o);self.assertEqual(code,0)
 def test_missing_artifact_is_not_invented(self):
  text,code=d.envelope({'success':False,'diagnostic_receipt':'FAILED_OR_INTERRUPTED'},fake_capture(),'a'*16,'b'*32,{});self.assertIsNone(json.loads(text)['durable_bindings']['diagnostic_receipt_sha256'])
 def test_cleanup_uncertainty_nonzero_preserves_original(self):
  c=fake_capture();c.cleanup_unknown=True;text,code=d.envelope({'success':True},c,'a'*16,'b'*32,{});self.assertEqual(code,2);self.assertTrue(json.loads(text)['original_result']['success'])
 def test_no_private_evidence_output(self):
  text,unused=d.envelope({'success':False},fake_capture(),'a'*16,'b'*32,{});self.assertNotIn('SECRET',text)
 def test_byte_bound(self):
  with self.assertRaises(ValueError):d.canonical({'x':'a'*100},50)
 def test_raw_references_cleared(self):
  c=fake_capture();c.projection();self.assertEqual(c.raw_pair,[]);self.assertEqual(c.raw_process,[])

class ProfileBoundaryTests(unittest.TestCase):
 def test_preexisting_profile_refused(self):
  c=d.SameAttemptCapture(types.SimpleNamespace(run=mock.Mock()))
  with mock.patch.object(d.sys,'getprofile',return_value=lambda:None):
   with self.assertRaisesRegex(ValueError,'PROCESS_CAPTURE_PROFILE_PRESENT'):c.invoke('a'*16,'b'*32)
  c.outer.run.assert_not_called()
 def test_preexisting_trace_refused(self):
  c=d.SameAttemptCapture(types.SimpleNamespace(run=mock.Mock()))
  with mock.patch.object(d.sys,'gettrace',return_value=lambda:None):
   with self.assertRaises(ValueError):c.invoke('a'*16,'b'*32)
 def test_interruption_preserved_and_hook_cleared(self):
  error=KeyboardInterrupt()
  def run(identifier,nonce,a,b):raise error
  def stage_kit(extractor):pass
  c=d.SameAttemptCapture(types.SimpleNamespace(run=run,stage_kit=stage_kit))
  with self.assertRaises(KeyboardInterrupt) as got:c.invoke('a'*16,'b'*32)
  self.assertIs(got.exception,error);self.assertIsNone(sys.getprofile())
 def test_setup_failure_preserves_primary(self):
  def run(*a):raise AssertionError('not run')
  c=d.SameAttemptCapture(types.SimpleNamespace(run=run));error=OSError('private')
  with mock.patch.object(d.sys,'setprofile',side_effect=[error,None]):
   with self.assertRaises(OSError) as got:c.invoke('a'*16,'b'*32)
  self.assertIs(got.exception,error);self.assertTrue(c.cleanup_unknown)
 def test_disarm_failure_is_base_exception_before_probe(self):
  c=fake_capture();c.profile_hook=lambda:None
  with mock.patch.object(d.sys,'getprofile',return_value=c.profile_hook),mock.patch.object(d.sys,'setprofile',side_effect=OSError()):
   with self.assertRaises(d.CaptureAbort) as got:c.disarm()
  self.assertTrue(c.cleanup_unknown);self.assertTrue(got.exception.diagnostic_cleanup_failed)
 def test_capture_validation_error_does_not_raise(self):
  c=fake_capture();c.event=mock.Mock(side_effect=ValueError('PRIVATE'));c.disarm=mock.Mock();c.hook(None,'return',None);self.assertEqual(c.reason,'CAPTURE_SCHEMA')
 def test_interrupt_hook_is_not_swallowed(self):
  c=fake_capture();c.event=mock.Mock(side_effect=KeyboardInterrupt())
  with self.assertRaises(KeyboardInterrupt):c.hook(None,'return',None)

class EmissionTests(unittest.TestCase):
 def run_main(self,envelope_error=None,printing=None):
  c=fake_capture();c.invoke=mock.Mock(return_value={'success':True,'diagnostic_receipt_sha256':'a'*64})
  stack=contextlib.ExitStack();self.addCleanup(stack.close)
  for owner,name,value in ((d.os,'geteuid',0),(d.os,'getegid',0),(d.socket,'gethostname',d.HOST)):
   stack.enter_context(mock.patch.object(owner,name,return_value=value))
  stack.enter_context(mock.patch.object(d,'prior_hold',return_value={}));stack.enter_context(mock.patch.object(d,'frozen_outer',return_value=object()));stack.enter_context(mock.patch.object(d,'SameAttemptCapture',return_value=c))
  if envelope_error:stack.enter_context(mock.patch.object(d,'envelope',side_effect=envelope_error))
  if printing:stack.enter_context(mock.patch('builtins.print',side_effect=printing))
  output=io.StringIO()
  with contextlib.redirect_stdout(output):code=d.main(['--observation-id','a'*16,'--nonce','b'*32,'--execute-reviewed-diagnostic','--execute-reviewed-probe'])
  return code,output.getvalue(),c
 def test_projection_overflow_retains_original(self):
  code,text,c=self.run_main(ValueError('WRITER_CAPTURE_SIZE_BOUND'));self.assertEqual(code,2);self.assertTrue(json.loads(text)['original_result']['success']);c.invoke.assert_called_once()
 def test_projection_deadline_retains_original(self):
  code,text,c=self.run_main(d.Deadline());self.assertEqual(code,2);self.assertTrue(json.loads(text)['original_result']['success'])
 def test_output_deadline_no_retry(self):
  calls=[]
  def output(*a,**kw):calls.append(a);raise d.Deadline()
  code,text,c=self.run_main(printing=output);self.assertEqual(code,2);self.assertEqual(len(calls),1)

class FrozenPipelineTests(unittest.TestCase):
 def setUp(self):
  self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
  package=BASE/'r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6'
  manifest_raw=(package/'recovery-kit-manifest.json').read_bytes() if (package/'recovery-kit-manifest.json').exists() else None
  if manifest_raw is None:
   names=[p for p in package.iterdir() if p.name.endswith('.json')];raise AssertionError([p.name for p in names])
  self.manifest=json.loads(manifest_raw);self.cache={name:(package/name).read_bytes() for name in self.manifest['files']}
  self.assertEqual(d.sha(manifest_raw),d.MANIFEST_SHA)
  for name,raw in self.cache.items():self.assertEqual(d.sha(raw),self.manifest['files'][name])
  self.entry=types.ModuleType('actual_r6_entry');self.entry.__file__=d.KIT+'/epoch7_recovery_entry.py'
  raw=self.cache['epoch7_recovery_entry.py'];self.assertEqual(d.sha(raw),d.ENTRY_SHA);exec(compile(raw,self.entry.__file__,'exec'),self.entry.__dict__)
  self.kit=self.entry.VerifiedKit(d.KIT,self.manifest,self.cache,d.MANIFEST_SHA,raw_manifest=manifest_raw)
  self.outer=types.ModuleType('actual_r6_outer');self.outer.__file__='<actual-frozen-r6-outer>'
  raw=(BASE/'kit-candidate/owner-prerequisite-candidate/owner_diagnostic_r6.py').read_bytes();self.assertEqual(d.sha(raw),d.OUTER_SHA);exec(compile(raw,self.outer.__file__,'exec'),self.outer.__dict__)
  self.persisted=[];self.probes=[];self.mode='equal';self.fail_persist=False;self.disarm_failure=False
 def install_fixture(self,capture,module):
  name=module.__name__
  if name=='observe_epoch7':
   f=types.ModuleType('actual_public_snapshot_fixture');f.__file__=d.KIT+'/tests/snapshot/test_snapshot.py';before=list(sys.path)
   try:exec(compile(self.cache['tests/snapshot/test_snapshot.py'],f.__file__,'exec'),f.__dict__)
   finally:sys.path[:]=before
   policy,backend=f.fixture();self.stack.enter_context(f.native_pin_context(f.native_raws(backend)))
   owner=self
   class Backend(type(backend)):
    def __init__(self,*a):self.__dict__.update(copy.deepcopy(backend.__dict__));self.pins={};self.observed_metadata={};self.n=0
    def writers(self,p,paths):
     row=super(Backend,self).writers(p,paths);self.n+=1
     if owner.mode=='interrupt':raise KeyboardInterrupt()
     if owner.mode=='deadline':raise d.Deadline()
     if owner.mode=='different' and self.n==2:row['processes']['process_identity_sha256']='9'*64
     if owner.mode=='before_only' and self.n==2:raise ValueError('WRITER_ACCOUNT_PROCESS')
     return row
   class Reader:
    def __init__(self,*a):self.pins={}
    def read(self,name):return b'',{'uid':0,'gid':0,'mode':0o600 if name==module.c.INSTALL_LOCK else 0o644,'sha256':'a'*64}
    @contextlib.contextmanager
    def parent(self,path):yield 11,path.rsplit('/',1)[-1]
   self.stack.enter_context(mock.patch.object(module,'ObservationIO',Backend));self.stack.enter_context(mock.patch.object(module,'ObservationReader',Reader));self.stack.enter_context(mock.patch.object(module,'measured_policy',return_value=policy))
   self.stack.enter_context(mock.patch.object(module.concrete,'existing_locks',side_effect=lambda *a:nullcontext([])))
   def persist(path,value):
    if self.fail_persist:raise ValueError('PERSIST_FAILURE')
    self.persisted.append(copy.deepcopy(value));return d.sha(module.d.canonical(value))
   self.stack.enter_context(mock.patch.object(module,'persist_private',side_effect=persist))
  elif name=='probe_metadata':
   def meta(*a,**kw):
    __import__('probe_driver');__import__('node_sqlite_probe')
    paths=('stage1/ledger_service.py','stage1/ledger_server_identity.py','stage1/activation_control.py')
    return {'ingredient_state':'COMPLETE_UNREVIEWED','ingredients':{},'candidate_source_evidence':{'root':d.KIT+'/xuanjun-p2-package','runtime_manifest_sha256':self.manifest['runtime_manifest_sha256'],'candidate_sources':{p:d.sha(self.cache['xuanjun-p2-package/'+p]) for p in paths}}}
   self.stack.enter_context(mock.patch.object(module,'collect_probe_ingredients',side_effect=meta))
  elif name=='unit_metadata':
   for attr in ('collect_unit_facts','collect_source_review_inputs'):self.stack.enter_context(mock.patch.object(module,attr,return_value={}))
  elif name=='openclaw_metadata':
   self.stack.enter_context(mock.patch.object(module,'prime_profile_scope',return_value=None));self.stack.enter_context(mock.patch.object(module,'collect_openclaw_profile',return_value={}))
  elif name=='probe_driver':
   self.stack.enter_context(mock.patch.object(module,'compile_policy',return_value={'node_sqlite':{'node':{},'probe_input_sha256':'1'*64}}))
   def probe(*a):
    self.assertIsNone(sys.getprofile());self.probes.append(True);return {'resume_authority':False,'failure':None,'incomplete_case':None,'cases':[{}]*8,'cleanup':[{'state':'REMOVED'}],'node_sqlite':{}}
   self.stack.enter_context(mock.patch.object(module,'execute_reviewed_probe',side_effect=probe))
  elif name=='node_sqlite_probe':self.stack.enter_context(mock.patch.object(module,'validate_node_sqlite_proof',return_value=None))
 def run_fixture(self):
  test=self
  class Capture(d.SameAttemptCapture):
   def imported(self,frame):
    super(Capture,self).imported(frame);test.install_fixture(self,frame.f_locals['module'])
  capture=Capture(self.outer)
  class PD:
   fd=10
   def __init__(self,*a):pass
   def __enter__(self):return self
   def __exit__(self,*a):return False
   def check(self):pass
  extractor=types.SimpleNamespace(ProtectedDirectory=PD,read_archive=lambda *a:self.cache['epoch7_recovery_entry.py'])
  self.stack.enter_context(mock.patch.object(self.outer,'host_boundary'))
  self.stack.enter_context(mock.patch.object(self.outer,'download',return_value=b''))
  self.stack.enter_context(mock.patch.object(self.outer,'authenticated_module',side_effect=lambda raw,digest,*a:extractor if digest==self.outer.EXTRACTOR_SHA else self.entry))
  self.stack.enter_context(mock.patch.object(self.outer,'check_outputs'))
  self.stack.enter_context(mock.patch.object(self.entry,'verify_kit',return_value=self.kit));self.stack.enter_context(mock.patch.object(self.entry,'_verify',return_value=self.kit))
  self.stack.enter_context(mock.patch.object(self.outer,'prior_files',return_value={}))
  class Directories(PD):
   def check(self):return {}
  self.stack.enter_context(mock.patch.object(self.outer,'CompletedDirectories',Directories))
  self.stack.enter_context(mock.patch.object(self.outer,'continuation_recheck',side_effect=lambda *a:nullcontext()))
  self.stack.enter_context(mock.patch.object(self.outer,'reverify_after',side_effect=lambda *a:nullcontext()))
  self.stack.enter_context(mock.patch.object(self.outer,'write_receipt',return_value='a'*64))
  realstat=d.os.stat
  def stat(path,*a,**kw):
   if type(path) is str and path.startswith('epoch7-observation-'):raise FileNotFoundError()
   if path=='epoch7-recovery-candidate-r6':return object()
   return realstat(path,*a,**kw)
  self.stack.enter_context(mock.patch.object(d.os,'stat',side_effect=stat));self.stack.enter_context(mock.patch.object(d.os,'geteuid',return_value=0));self.stack.enter_context(mock.patch.object(d.socket,'gethostname',return_value=d.HOST))
  if self.disarm_failure:
   actual=sys.setprofile;failed=[False]
   def setting(hook):
    if hook is None and not failed[0]:failed[0]=True;raise OSError('synthetic close failure')
    return actual(hook)
   self.stack.enter_context(mock.patch.object(d.sys,'setprofile',side_effect=setting))
  result=capture.invoke('a'*16,'b'*32);projection=capture.projection();return result,projection,capture
 def test_actual_loader_collect_mismatch_same_attempt(self):
  self.mode='different';result,p,c=self.run_fixture();self.assertEqual(p.get('capture_state'),'COMPLETE',repr(p));self.assertFalse(p['collector_returned']);self.assertEqual(p['original_core_status']['failure_code'],'WRITER_OBSERVATION_CHANGED');self.assertFalse(result['success']);self.assertEqual(len(self.persisted),1);self.assertEqual(self.persisted[0]['failure_code'],'WRITER_OBSERVATION_CHANGED');self.assertEqual(self.probes,[]);self.assertIsNone(sys.getprofile())
 def test_actual_loader_collect_equal_pass_and_disarm(self):
  result,p,c=self.run_fixture();self.assertEqual(p.get('capture_state'),'COMPLETE',repr(p));self.assertTrue(p['collector_returned']);self.assertEqual(p['pair_state'],'EQUAL');self.assertEqual(len(self.persisted),1);self.assertEqual(p['original_core_status']['kind'],'EPOCH7_OBSERVATION_ONLY_UNREVIEWED');self.assertTrue(c.disarmed);self.assertTrue(result['success'],repr(result));self.assertEqual(self.probes,[True]);self.assertTrue(result['observation']['probe_observations_complete']);self.assertEqual(self.persisted[0]['finite_probe']['stage'],'RESULT_RECORDED')
 def test_actual_before_only_unknown(self):
  self.mode='before_only';result,p,c=self.run_fixture();self.assertEqual(p['capture_state'],'UNKNOWN_NOT_REACHED');self.assertEqual(p['successful_validated_samples'],1);self.assertFalse(result['success'])
 def test_actual_persistence_failure_retains_pair(self):
  self.fail_persist=True;result,p,c=self.run_fixture();self.assertFalse(result['success']);self.assertEqual(p['capture_state'],'COMPLETE');self.assertNotIn('observation',result)



 def test_actual_disarm_failure_stops_before_probe(self):
  self.disarm_failure=True;result,p,c=self.run_fixture();self.assertFalse(result['success']);self.assertTrue(c.cleanup_unknown);self.assertEqual(self.probes,[]);self.assertIsNone(sys.getprofile())
 def test_actual_interrupt_plus_disarm_failure_preserves_primary(self):
  self.mode='interrupt';self.disarm_failure=True;result,p,c=self.run_fixture();self.assertEqual(result['failure_code'],'INTERRUPTED');self.assertTrue(c.cleanup_unknown);self.assertEqual(self.probes,[]);self.assertIsNone(sys.getprofile())
 def test_actual_deadline_plus_disarm_failure_preserves_primary(self):
  self.mode='deadline';self.disarm_failure=True;result,p,c=self.run_fixture();self.assertEqual(result['failure_code'],'INTERRUPTED');self.assertTrue(c.cleanup_unknown);self.assertEqual(self.probes,[]);self.assertIsNone(sys.getprofile())

class ProcessTests(unittest.TestCase):
 def call(self,scan=None):
  scan=scan or oldtests.SyntheticScan()
  def stage_kit(a):pass
  def run(*a):pass
  cap=d.SameAttemptCapture(types.SimpleNamespace(stage_kit=stage_kit,run=run));cap.entry=object();cap.backend=scan;cap.started=d.time.monotonic()
  cap.codes['scan']=oldtests.SyntheticScan._process_scan.__code__;cap.codes['procfile']=[x for x in cap.codes['scan'].co_consts if isinstance(x,types.CodeType) and x.co_name=='procfile'][0]
  cap.profile_hook=cap.hook
  def parent():
   cap.ids['writers']=id(sys._getframe());return scan._process_scan([])
  try:
   sys.setprofile(cap.profile_hook);value=parent()
  finally:sys.setprofile(None)
  self.assertIsNone(cap.reason,cap.reason);self.assertEqual(len(cap.raw_process),1)
  return d.validate_process(cap.raw_process[0],d.digest),cap,value
 def test_exact_original_numeric_and_classification(self):
  r,c,v=self.call();self.assertEqual(r['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND');self.assertEqual(r['details']['10']['fd_count'],3)
 def test_zero_boot_tick(self):
  s=oldtests.SyntheticScan();s.rows['10']['starttime']=0;r,c,v=self.call(s);self.assertEqual(r['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND')
 def test_kernel_bit(self):
  s=oldtests.SyntheticScan();s.rows['10']['kernel']=True;r,c,v=self.call(s);self.assertTrue(r['details']['10']['kernel_thread'])
 def test_indirect_ssh_read_ignored(self):
  s=oldtests.SyntheticScan();s.indirect=True;r,c,v=self.call(s);self.assertEqual(r['details_state'],'EXACT_ORIGINAL_STAT_COMM_FD_BOUND')
 def test_digest_mismatch_unknown(self):
  s=oldtests.SyntheticScan();s.bad_digest=True;r,c,v=self.call(s);self.assertEqual(r['state'],'UNKNOWN')
 def test_count_mismatch_unknown(self):
  s=oldtests.SyntheticScan();s.bad_count=True;r,c,v=self.call(s);self.assertEqual(r['state'],'UNKNOWN')
 def test_changed_start_unknown(self):
  s=oldtests.SyntheticScan();s.rows['10']['stat2']=oldtests.proc_stat(10,101);r,c,v=self.call(s);self.assertEqual(r['details_state'],'UNKNOWN')
 def test_changed_kernel_unknown(self):
  s=oldtests.SyntheticScan();s.rows['10']['stat2']=oldtests.proc_stat(10,100,True);r,c,v=self.call(s);self.assertEqual(r['details_state'],'UNKNOWN')
 def test_duplicate_stat_unknown(self):
  s=oldtests.SyntheticScan();s.extra_stat=True;r,c,v=self.call(s);self.assertEqual(r['details_state'],'UNKNOWN')
 def test_raw_detail_bound(self):
  with mock.patch.object(d,'MAX_PROC_CAPTURE',1):r,c,v=self.call()
  self.assertEqual(r['details_state'],'UNKNOWN')
 def test_census_bound(self):
  with mock.patch.object(d,'MAX_CENSUS',1):r,c,v=self.call()
  self.assertEqual(r['state'],'UNKNOWN')
 def test_comm_secret_hashed_only(self):
  s=oldtests.SyntheticScan();s.rows['10']['comm']=b'SECRET';r,c,v=self.call(s);self.assertNotIn('SECRET',json.dumps(r));self.assertEqual(r['details']['10']['comm_label'],'UNLISTED_COMM_HASH_ONLY')
 def test_wrong_stat_pid_unknown(self):
  s=oldtests.SyntheticScan();s.rows['10']['stat2']=oldtests.proc_stat(11,100);r,c,v=self.call(s);self.assertEqual(r['details_state'],'UNKNOWN')
 def test_comm_oversize_unknown(self):
  s=oldtests.SyntheticScan();s.rows['10']['comm']=b'SECRET'*100;r,c,v=self.call(s);self.assertEqual(r['details_state'],'UNKNOWN')



class AuthenticationTests(unittest.TestCase):
 def test_bad_stage_authentication_disarms_before_original_would_probe(self):
  calls=[]
  def stage_kit(extractor):return (None,None,None)
  def run(identifier,nonce,a,b):stage_kit(None);calls.append(sys.getprofile());return {'success':True}
  c=d.SameAttemptCapture(types.SimpleNamespace(run=run,stage_kit=stage_kit));result=c.invoke('a'*16,'b'*32)
  self.assertTrue(result['success']);self.assertEqual(calls,[None]);self.assertEqual(c.projection()['capture_state'],'UNKNOWN')
 def fixture(self):
  def run(*a):pass
  def stage_kit(*a):pass
  c=d.SameAttemptCapture(types.SimpleNamespace(run=run,stage_kit=stage_kit));c.entry=types.SimpleNamespace()
  class Loader:pass
  c.entry.CachedSources=Loader;c.kit=types.SimpleNamespace(root=d.KIT,cache={'helpers/epoch7_snapshot.py':b'x'},manifest={'modules':dict(d.MODULES),'files':{'helpers/epoch7_snapshot.py':d.sha(b'x')}})
  loader=Loader();loader.root=d.KIT;loader.cache=c.kit.cache;loader.modules=dict(d.MODULES);loader.loaded={'epoch7_snapshot'}
  module=types.ModuleType('epoch7_snapshot');module.__loader__=loader;module.__file__=d.KIT+'/helpers/epoch7_snapshot.py'
  frame=types.SimpleNamespace(f_locals={'self':loader,'module':module});return c,loader,module,frame
 def test_foreign_cache_rejected(self):
  c,l,m,f=self.fixture();l.cache=dict(l.cache)
  with self.assertRaisesRegex(ValueError,'CAPTURE_AUTHENTICATION'):c.imported(f)
 def test_foreign_module_map_rejected(self):
  c,l,m,f=self.fixture();l.modules['extra']='x.py'
  with self.assertRaisesRegex(ValueError,'CAPTURE_AUTHENTICATION'):c.imported(f)
 def test_wrong_root_rejected(self):
  c,l,m,f=self.fixture();l.root='/private/other'
  with self.assertRaises(ValueError):c.imported(f)
 def test_wrong_module_loader_rejected(self):
  c,l,m,f=self.fixture();m.__loader__=object()
  with self.assertRaises(ValueError):c.imported(f)
 def test_wrong_source_bytes_rejected(self):
  c,l,m,f=self.fixture();l.cache['helpers/epoch7_snapshot.py']=b'changed'
  with self.assertRaises(ValueError):c.imported(f)
 def test_wrong_same_named_code_not_observed(self):
  def stage_kit(*a):pass
  def run(*a):pass
  c=d.SameAttemptCapture(types.SimpleNamespace(stage_kit=stage_kit,run=run))
  def observe_host():pass
  frame=types.SimpleNamespace(f_code=observe_host.__code__,f_back=None,f_locals={})
  c.event(frame,'call',None);self.assertEqual(c.host_calls,0)
 def test_backend_identity_mismatch_rejected(self):
  def run(*a):pass
  def stage_kit(*a):pass
  def collect(*a):pass
  c=d.SameAttemptCapture(types.SimpleNamespace(stage_kit=stage_kit,run=run));c.entry=object();c.codes['collect']=collect.__code__;c.started=d.time.monotonic();parent=object();c.ids['observe']=id(parent);c.backend=object()
  frame=types.SimpleNamespace(f_code=collect.__code__,f_back=parent,f_locals={'io':object()})
  with self.assertRaisesRegex(ValueError,'CAPTURE_LINEAGE'):c.event(frame,'call',None)
 def test_cooperative_time_bound_disarms(self):
  def run(*a):pass
  def stage_kit(*a):pass
  c=d.SameAttemptCapture(types.SimpleNamespace(stage_kit=stage_kit,run=run));c.entry=object();c.started=0;c.disarm=mock.Mock()
  frame=types.SimpleNamespace(f_code=(lambda:None).__code__,f_back=None,f_locals={})
  with mock.patch.object(d.time,'monotonic',return_value=601):
   with self.assertRaises(d.Deadline):c.event(frame,'call',None)
  c.disarm.assert_called_once()



class TerminalAndBoundsTests(unittest.TestCase):
 def test_late_host_return_marks_unknown_but_keeps_original_value(self):
  def run(*a):pass
  def stage_kit(*a):pass
  def observe_host():pass
  c=d.SameAttemptCapture(types.SimpleNamespace(stage_kit=stage_kit,run=run));c.entry=object();c.codes['host']=observe_host.__code__;c.started=0;c.disarm=mock.Mock()
  frame=types.SimpleNamespace(f_code=observe_host.__code__,f_back=None,f_locals={});c.ids['host']=id(frame);value={'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED'}
  with mock.patch.object(d.time,'monotonic',return_value=601):c.event(frame,'return',value)
  self.assertEqual(c.reason,'CAPTURE_TIME_BOUND');self.assertEqual(c.observation_status['kind'],value['kind']);c.disarm.assert_called_once()
 def test_transition_requires_exact_parent_objects(self):
  def run(*a):pass
  def stage_kit(*a):pass
  def compare(*a):pass
  c=d.SameAttemptCapture(types.SimpleNamespace(stage_kit=stage_kit,run=run));c.entry=object();c.codes['compare']=compare.__code__;c.started=d.time.monotonic();parent=types.SimpleNamespace(f_locals={'before_writers':{},'after_writers':{}});c.ids['collect']=id(parent)
  frame=types.SimpleNamespace(f_code=compare.__code__,f_back=parent,f_locals={'before':{},'after':{}})
  with self.assertRaisesRegex(ValueError,'CAPTURE_LINEAGE'):c.event(frame,'call',None)
 def test_two_pair_bound(self):
  c=fake_capture();c.raw_pair.append(oldtests.row());self.assertEqual(c.projection()['capture_state'],'UNKNOWN')
 def test_64_rows_and_total_output_bound(self):
  c=fake_capture();sample={str(i):{'starttime':2**64-1,'uids':[2**32-1]*4} for i in range(1,66)}
  detail={pid:{'kernel_thread':False,'comm_sha256':'c'*64,'comm_label':'UNLISTED_COMM_HASH_ONLY','fd_count':999999} for pid in sample}
  first={'state':'CAPTURED_FROM_ORIGINAL_RETURN','sample':sample,'details_state':'EXACT_ORIGINAL_STAT_COMM_FD_BOUND','details':detail,'process_identity_sha256':d.digest(sample),'fd_count':1}
  last=copy.deepcopy(first)
  for row in last['details'].values():row['fd_count']-=1
  for row in c.raw_pair:row['processes']['process_identity_sha256']=first['process_identity_sha256'];row['processes']['fd_count']=1
  c.processes.records=[first,last];c.processes.calls=2
  text,code=d.envelope({'success':False,'synthetic_public_receipt_padding':'x'*16000},c,'a'*16,'b'*32,{})
  value=json.loads(text);p=value['same_attempt_writer_capture']['process_attribution'];self.assertEqual(len(p['changed_pid_rows']),64);self.assertTrue(p['truncated']);self.assertEqual(p['omitted_changed_pid_count'],1);self.assertLess(len(text),65536)
 def test_reader_functions_are_exact_reviewed_source(self):
  source=pathlib.Path(d.__file__).read_text();baseline=(HERE.parent/'owner-hold-readback-candidate/r6-stored/read_existing_r6_hold.py').read_text()
  def chunks(raw):
   nodes=ast.parse(raw).body;rows=raw.splitlines(True);out={}
   for i,node in enumerate(nodes):
    if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
     end=nodes[i+1].lineno-1 if i+1<len(nodes) else len(rows);out[node.name]=''.join(rows[node.lineno-1:end]).strip()
   return out
  a,b=chunks(source),chunks(baseline)
  for name in ('authority','entry_bytes','read_pair'):self.assertEqual(a[name],b[name])

if __name__=='__main__':unittest.main(verbosity=2)
