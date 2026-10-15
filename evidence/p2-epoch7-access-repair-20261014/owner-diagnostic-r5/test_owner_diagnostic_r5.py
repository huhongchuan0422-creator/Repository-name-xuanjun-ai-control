"""Synthetic receipts, disposable directories and mocked host boundaries only."""
import ast,contextlib,copy,errno,hashlib,io,json,os,pathlib,signal,stat,tempfile,types,unittest
from unittest import mock
import owner_diagnostic_r5 as d

@contextlib.contextmanager
def no_alarm(unused):yield

def fixtures():
 after={p:dict(dev=1,ino=i+20,uid=1002,gid=1002,mode=0o755,nlink=2,size=4096,mtime_ns=100,ctime_ns=200) for i,p in enumerate(d.TARGETS)}
 before={p:dict(row,mode=0o775,ctime_ns=150) for p,row in after.items()}
 observation={'schema':1,'kind':'EPOCH7_OBSERVATION_ONLY_HOLD','finite_probe':{'schema':1,'nonce':d.PRIOR_NONCE,'stage':'HOLD_NOT_EXECUTED','resume_authority':False}}
 receipt={'schema':1,'kind':'OWNER_R3_PREREQUISITE_DIAGNOSTIC','stage':'HOLD_RECORDED','kit_source_commit':d.PRIOR_SOURCE,'kit_manifest_sha256':d.PRIOR_MANIFEST,'production_resume':'NOT_EXECUTED','install_admission':'NOT_GRANTED',
  'exact_uid_acl':{'case':d.UK_CASE,'source_sha256':d.UK_TEST_SHA,'success':True,'state':'PASS_OBSERVED_FIXTURE_ONLY','scope':'TWO_DISPOSABLE_TARGET_ACLS_NOT_PRODUCTION_DAC_ACCEPTANCE','tests':1,'failures':0,'errors':0,'skipped':0},
  'observation':{'private_file_sha256':'SET_IN_PACK','kit_manifest_sha256':d.PRIOR_MANIFEST,'kind':'EPOCH7_OBSERVATION_ONLY_HOLD','probe_stage':'HOLD_NOT_EXECUTED','probe_observations_complete':False},
  'prerequisite':{'kind':'EPOCH7_OWNER_PREREQUISITE','stage':'COMPLETE_PREREQUISITES_ONLY','cleanup_failed':False,'automatic_retry':False,'permission_widening_rollback':False,'production_admission':'NOT_GRANTED','service_actions':0,'database_writes':0,'authorized_targets':list(d.TARGETS),'attempted':list(d.TARGETS),'completed':list(d.TARGETS),'guard_before':{'epoch':7,'state':'PREPARED'},'guard_after':{'epoch':7,'state':'PREPARED'},'before':before,'after':after}}
 return receipt,observation,after

def packed(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()

class PublicationTests(unittest.TestCase):
 def test_not_ready_before_any_host_or_network(self):
  with mock.patch.object(d,'READY',False),mock.patch.object(d,'host_boundary') as host,mock.patch.object(d,'download') as download:
   result=d.run('a'*16,'b'*32,True,True)
  self.assertEqual(result['failure_code'],'IMMUTABLE_R5_PUBLICATION_NOT_READY');host.assert_not_called();download.assert_not_called()
 def test_exact_published_pins(self):
  self.assertIs(d.READY,True);d.publication_gate()
  expected={'SOURCE': '9c40fc811947112df579b293fb4d54c61d9ce37b', 'TREE': '75dde36eb35524838fd2748ebe07fbba3d82da5e', 'PUBLICATION': 'd5ed9f17ad9ef09d430aa6011f86449d227f0f1c', 'ARCHIVE_PATH': 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-9c40fc81.tar.gz', 'ARCHIVE_SHA': 'e0fbc766d53a961f180a9ddfcdd1a40bdc6f8d809236f1b9bfb9cf4d3a929776', 'EXTRACTOR_SHA': 'a5c283dfa297983617d5fca20c8453cd4766d765ba53ec9326e6c5645493202c', 'ENTRY_SHA': '1565e2f1e7e771f33e0895ffcaf8f38caddee9e02811a11b6a2318334af6075a', 'MANIFEST_SHA': 'd8c36ad208994a3314f6b0c0598ad2e4ea8641c75f2610f9749784f834244d49', 'ARCHIVE_SIZE': 1028165, 'EXTRACTOR_SIZE': 9582, 'KIT_SOURCE_FILES': 249, 'READY': True, 'ARCHIVE_URL': 'https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/d5ed9f17ad9ef09d430aa6011f86449d227f0f1c/evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-9c40fc81.tar.gz', 'EXTRACTOR_URL': 'https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/9c40fc811947112df579b293fb4d54c61d9ce37b/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py'}
  for name,value in expected.items():self.assertEqual(getattr(d,name),value)
 def test_only_r5_path(self):self.assertEqual(d.KIT,d.BASE+'/epoch7-recovery-candidate-r5')
 def test_no_repair_or_fixture_entrypoint(self):
  for name in ('exact_uid_test','load_exact_uid_suite','exact_uk_imports','prerequisite','apply_reviewed_prerequisites'):self.assertFalse(hasattr(d,name))
  source=pathlib.Path(d.__file__).read_text();tree=ast.parse(source)
  self.assertFalse(any(isinstance(n,ast.Import) and any(x.name=='unittest' for x in n.names) for n in ast.walk(tree)))
 def test_old_repair_flag_refused(self):
  with mock.patch.object(d,'run') as run,contextlib.redirect_stdout(io.StringIO()):code=d.main(['--observation-id','a'*16,'--execute-reviewed-prerequisites'])
  self.assertEqual(code,2);run.assert_not_called()
 def test_resume_flag_refused_without_leaking_argument(self):
  out=io.StringIO()
  with mock.patch.object(d,'run') as run,contextlib.redirect_stdout(out):code=d.main(['--resume','PRIVATE'])
  self.assertEqual(code,2);run.assert_not_called();self.assertNotIn('PRIVATE',out.getvalue())

class PriorTests(unittest.TestCase):
 def setUp(self):self.receipt,self.observation,self.after=fixtures();self.entry=types.SimpleNamespace(decode=lambda raw:json.loads(raw.decode()))
 def buffers(self):
  obs=packed(self.observation);self.receipt['observation']['private_file_sha256']=d.sha(obs);return packed(self.receipt),obs
 def validate(self):
  receipt,obs=self.buffers()
  with mock.patch.object(d,'PRIOR_RECEIPT_SHA',d.sha(receipt)),mock.patch.object(d,'PRIOR_OBSERVATION_SHA',d.sha(obs)):return d.validate_prior(self.entry,receipt,obs)
 def reject(self,label):
  with self.assertRaisesRegex(d.DiagnosticHold,label):self.validate()
 def test_exact_prior_fixture(self):self.assertEqual(self.validate(),self.after)
 def test_prior_receipt_hash_required(self):
  r,o=self.buffers()
  with self.assertRaisesRegex(d.DiagnosticHold,'PRIOR_RECEIPT_HASH'):d.validate_prior(self.entry,r,o)
 def test_prior_observation_hash_required(self):
  r,o=self.buffers()
  with mock.patch.object(d,'PRIOR_RECEIPT_SHA',d.sha(r)):
   with self.assertRaisesRegex(d.DiagnosticHold,'PRIOR_OBSERVATION_HASH'):d.validate_prior(self.entry,r,o)
 def test_wrong_source(self):self.receipt['kit_source_commit']='0'*40;self.reject('PRIOR_DIAGNOSTIC_BINDING')
 def test_wrong_manifest(self):self.receipt['kit_manifest_sha256']='0'*64;self.reject('PRIOR_DIAGNOSTIC_BINDING')
 def test_prior_cleanup_uncertainty(self):self.receipt['timer_cleanup']='FAILED_OR_INTERRUPTED';self.reject('PRIOR_CLEANUP_UNCERTAINTY')
 def test_failed_uid_test(self):self.receipt['exact_uid_acl']['success']=False;self.reject('PRIOR_UID_PROOF')
 def test_skipped_uid_test(self):self.receipt['exact_uid_acl']['skipped']=1;self.reject('PRIOR_UID_PROOF')
 def test_bool_test_count_is_not_one(self):self.receipt['exact_uid_acl']['tests']=True;self.reject('PRIOR_UID_PROOF')
 def test_other_uid_source(self):self.receipt['exact_uid_acl']['source_sha256']='0'*64;self.reject('PRIOR_UID_PROOF')
 def test_probe_attempted(self):self.observation['finite_probe']['stage']='HOLD_AFTER_ATTEMPT';self.reject('PRIOR_PROBE_NOT_STARTED')
 def test_prior_probe_result_present(self):self.observation['finite_probe']['result']={};self.reject('PRIOR_PROBE_NOT_STARTED')
 def test_prior_probe_policy_present(self):self.observation['finite_probe']['policy']={};self.reject('PRIOR_PROBE_NOT_STARTED')
 def test_other_nonce(self):self.observation['finite_probe']['nonce']='f'*32;self.reject('PRIOR_PROBE_NOT_STARTED')
 def test_partial_permission_repair(self):self.receipt['prerequisite']['completed']=list(d.TARGETS[:2]);self.reject('PRIOR_COMPLETED_PREREQUISITE_REQUIRED')
 def test_prior_cleanup_failed(self):self.receipt['prerequisite']['cleanup_failed']=True;self.reject('PRIOR_COMPLETED_PREREQUISITE_REQUIRED')
 def test_old_epoch(self):self.receipt['prerequisite']['guard_after']['epoch']=6;self.reject('PRIOR_PREPARED_EPOCH')
 def test_not_prepared(self):self.receipt['prerequisite']['guard_after']['state']='ACTIVE';self.reject('PRIOR_PREPARED_EPOCH')
 def test_extra_target(self):self.receipt['prerequisite']['after']['/other']={};self.reject('PRIOR_EXACT_TARGET_ROWS')
 def test_target_remains_group_writable(self):self.after[d.TARGETS[0]]['mode']=0o775;self.reject('PRIOR_NARROWING_METADATA')
 def test_uid_changed_in_prior_repair(self):self.after[d.TARGETS[0]]['uid']=0;self.reject('PRIOR_NARROWING_METADATA')
 def test_inode_changed_in_prior_repair(self):self.after[d.TARGETS[0]]['ino']+=1;self.reject('PRIOR_NARROWING_METADATA')
 def test_stat_boolean_refused(self):self.after[d.TARGETS[0]]['dev']=True;self.reject('PRIOR_NARROWING_METADATA')
 def test_fixed_private_paths_and_limits(self):
  r,o=self.buffers();entry=mock.MagicMock();entry.decode=self.entry.decode;tree=entry.DescriptorTree.return_value.__enter__.return_value;tree.read.side_effect=[r,o]
  with mock.patch.object(d,'PRIOR_RECEIPT_SHA',d.sha(r)),mock.patch.object(d,'PRIOR_OBSERVATION_SHA',d.sha(o)):result=d.prior_files(entry)
  self.assertEqual(result,self.after);entry.DescriptorTree.assert_called_once_with(d.BASE)
  self.assertEqual(tree.read.call_args_list,[mock.call(d.PRIOR_RECEIPT,16384,private=True),mock.call(d.PRIOR_OBSERVATION,67108864,private=True)]);tree.recheck.assert_called_once()

class DirectoryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  for path,mode in [('/home',0o755),(d.HOME,0o700),(d.OPENCLAW,0o700)]+[(p,0o755) for p in d.TARGETS]:
   p=self.path(path);p.mkdir();p.chmod(mode)
  self.root.chmod(0o700);self.expected={p:d.metadata(os.lstat(str(self.path(p)))) for p in d.TARGETS}
 def path(self,path):return self.root/path.lstrip('/')
 def manager(self):return d.CompletedDirectories(self.expected,_root=str(self.root),_owner=(os.getuid(),os.getgid()),_root_owner=(os.getuid(),os.getgid()),_root_mode=0o700)
 def test_real_matching_metadata_no_mutation(self):
  with mock.patch.object(d.os,'fchmod') as chmod,mock.patch.object(d.os,'chown') as chown:
   with self.manager() as held:self.assertEqual(held.check(),self.expected)
  chmod.assert_not_called();chown.assert_not_called()
 def test_already_drifted_mode(self):
  self.path(d.TARGETS[0]).chmod(0o775)
  with self.assertRaisesRegex(d.DiagnosticHold,'AUTHORITY'):
   with self.manager():pass
 def test_prior_metadata_drift(self):
  self.expected[d.TARGETS[0]]['ino']+=1
  with self.assertRaisesRegex(d.DiagnosticHold,'PRIOR_POSTCONDITION'):
   with self.manager():pass
 def test_target_symlink(self):
  path=self.path(d.TARGETS[0]);path.rmdir();path.symlink_to(self.path(d.TARGETS[1]),target_is_directory=True)
  with self.assertRaises(OSError):
   with self.manager():pass
 def test_parent_symlink(self):
  path=self.path(d.HOME);renamed=path.with_name('saved');path.rename(renamed);path.symlink_to(renamed,target_is_directory=True)
  with self.assertRaises(OSError):
   with self.manager():pass
 def test_acl_refused(self):
  with mock.patch.object(d.os,'getxattr',return_value=b'not-empty'):
   with self.assertRaisesRegex(d.DiagnosticHold,'ATTRIBUTE'):
    with self.manager():pass
 def test_capability_refused(self):
  original=d.os.getxattr
  def attr(fd,key):return b'x' if key=='security.capability' else original(fd,key)
  with mock.patch.object(d.os,'getxattr',side_effect=attr):
   with self.assertRaisesRegex(d.DiagnosticHold,'ATTRIBUTE'):
    with self.manager():pass
 def test_later_mode_drift(self):
  with self.manager() as held:
   self.path(d.TARGETS[0]).chmod(0o775)
   with self.assertRaisesRegex(d.DiagnosticHold,'AUTHORITY'):held.check()
 def test_later_path_replacement(self):
  with self.manager() as held:
   path=self.path(d.TARGETS[0]);path.rename(path.with_name('saved'));path.mkdir(mode=0o755);path.chmod(0o755)
   with self.assertRaises(d.DiagnosticHold):held.check()
 def test_close_all_once_after_first_interrupt(self):
  held=self.manager();held.__enter__();fds=list(held.held);real=d.os.close;calls=[]
  def close(fd):
   calls.append(fd);real(fd)
   if len(calls)==1:raise KeyboardInterrupt()
  with mock.patch.object(d.os,'close',side_effect=close):
   with self.assertRaises(KeyboardInterrupt):held.close()
  self.assertEqual(calls,list(reversed(fds)));self.assertEqual(held.held,[])
 def test_setup_error_preserves_primary_when_cleanup_fails(self):
  held=self.manager();primary=d.DiagnosticHold('PRIMARY');real=held.close
  def close():real();raise KeyboardInterrupt()
  with mock.patch.object(held,'check',side_effect=primary),mock.patch.object(held,'close',side_effect=close):
   with self.assertRaises(d.DiagnosticHold) as caught:held.__enter__()
  self.assertIs(caught.exception,primary);self.assertTrue(primary.diagnostic_directory_cleanup_failed)
 def test_timer_setup_refusal_still_closes_each_fd_once(self):
  held=self.manager();held.__enter__();fds=list(held.held)
  with mock.patch.object(d.signal,'getitimer',return_value=(1.0,0.0)):
   with self.assertRaises(d.DiagnosticHold):held.__exit__(None,None,None)
  self.assertEqual(held.held,[])
  for fd in fds:
   with self.assertRaises(OSError):os.fstat(fd)

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
  for name in ('publication_gate','host_boundary','check_outputs'):self.stack.enter_context(mock.patch.object(d,name))
  self.stack.enter_context(mock.patch.object(d,'bounded_stage',no_alarm));self.stack.enter_context(mock.patch.object(d,'MANIFEST_SHA','e'*64))
  self.download=self.stack.enter_context(mock.patch.object(d,'download',return_value=b'fixed'))
  self.extractor=mock.Mock();self.stack.enter_context(mock.patch.object(d,'authenticated_module',return_value=self.extractor))
  self.entry=mock.Mock();self.kit=mock.Mock();self.stack.enter_context(mock.patch.object(d,'stage_kit',return_value=(self.entry,self.kit,'VERIFIED_EXISTING')))
  self.expected=fixtures()[2];self.prior=self.stack.enter_context(mock.patch.object(d,'prior_files',return_value=self.expected))
  self.manager=mock.MagicMock();self.held=self.manager.__enter__.return_value;self.held.check.return_value=self.expected
  self.guard=self.stack.enter_context(mock.patch.object(d,'CompletedDirectories',return_value=self.manager))
  self.write=self.stack.enter_context(mock.patch.object(d,'write_receipt',return_value='f'*64))
  self.kit.observe.return_value={'operation':'observe-and-probe','kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','probe_stage':'RESULT_RECORDED','independent_acceptance':'PENDING','install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED','private_file_sha256':'1'*64,'snapshot_sha256':'2'*64,'policy_sha256':'3'*64,'kit_manifest_sha256':d.MANIFEST_SHA,'success':True,'probe_observations_complete':True}
 def call(self,**kw):
  args=dict(identifier='a'*16,nonce='b'*32,execute_reviewed_diagnostic=True,execute_reviewed_probe=True);args.update(kw);return d.run(**args)
 def test_success_calls_observe_once_after_prior_and_current_checks(self):
  def observe(*args):
   self.prior.assert_called_once();self.manager.__enter__.assert_called_once();self.held.check.assert_called_once();return self.observed
  self.observed=self.kit.observe.return_value;self.kit.observe.side_effect=observe;result=self.call()
  self.assertTrue(result['success']);self.kit.observe.assert_called_once_with(d.BASE+'/epoch7-observation-'+'a'*16+'.private.json','b'*32,True)
  self.assertEqual(self.prior.call_count,2);self.assertEqual(self.held.check.call_count,2);self.manager.__exit__.assert_called_once();self.entry.verify_kit.assert_called_once();self.write.assert_called_once()
 def test_no_ack_before_download(self):self.call(execute_reviewed_diagnostic=False);self.download.assert_not_called()
 def test_prior_identifier_refused(self):self.call(identifier=d.PRIOR_ID);self.download.assert_not_called()
 def test_prior_nonce_refused(self):self.call(nonce=d.PRIOR_NONCE);self.download.assert_not_called()
 def test_bad_nonce_refused(self):self.call(nonce='bad');self.download.assert_not_called()
 def test_prior_hash_failure_prevents_observe(self):self.prior.side_effect=d.DiagnosticHold('PRIOR_RECEIPT_HASH');result=self.call();self.assertFalse(result['success']);self.guard.assert_not_called();self.kit.observe.assert_not_called()
 def test_directory_failure_prevents_observe(self):self.manager.__enter__.side_effect=d.DiagnosticHold('COMPLETED_DIRECTORY_PRIOR_POSTCONDITION');result=self.call();self.assertFalse(result['success']);self.kit.observe.assert_not_called()
 def test_observe_hold_preserved_without_repeat(self):
  self.kit.observe.return_value.update(kind='EPOCH7_OBSERVATION_ONLY_HOLD',success=False,probe_stage='HOLD_NOT_EXECUTED',probe_observations_complete=False)
  result=self.call();self.assertFalse(result['success']);self.assertEqual(result['stage'],'HOLD_RECORDED');self.kit.observe.assert_called_once()
 def test_observe_only_has_no_probe_flag(self):
  self.kit.observe.return_value.update(operation='observe-only',probe_stage='NOT_REQUESTED',probe_observations_complete=False)
  self.call(nonce=None,execute_reviewed_probe=False);self.kit.observe.assert_called_once_with(d.BASE+'/epoch7-observation-'+'a'*16+'.private.json',None,False)
 def test_post_receipt_failure_retains_observation(self):
  self.prior.side_effect=[self.expected,d.DiagnosticHold('PRIOR_RECEIPT_HASH')];result=self.call();self.assertFalse(result['success']);self.assertIn('observation',result);self.kit.observe.assert_called_once()
 def test_post_directory_drift_retains_observation(self):
  self.held.check.side_effect=[self.expected,d.DiagnosticHold('COMPLETED_DIRECTORY_CHANGED')];result=self.call();self.assertFalse(result['success']);self.assertIn('observation',result)
 def test_post_kit_verify_failure_retains_observation(self):
  self.entry.verify_kit.side_effect=ValueError('PRIVATE');result=self.call();self.assertFalse(result['success']);self.assertIn('observation',result);self.assertEqual(result['reverification'],'FAILED_OR_INTERRUPTED');self.assertNotIn('PRIVATE',str(result))
 def test_interrupt_preserves_primary_despite_final_receipt_failure(self):
  self.kit.observe.side_effect=KeyboardInterrupt();self.prior.side_effect=[self.expected,ValueError('PRIVATE')];result=self.call();self.assertEqual(result['failure_code'],'INTERRUPTED');self.assertEqual(result['continuation_reverification'],'FAILED_OR_INTERRUPTED');self.assertNotIn('PRIVATE',str(result))
 def test_directory_cleanup_failure_preserves_observation(self):
  self.manager.__exit__.side_effect=ValueError('PRIVATE');result=self.call();self.assertFalse(result['success']);self.assertIn('observation',result);self.assertNotIn('PRIVATE',str(result))
 def test_receipt_write_error_no_retry(self):self.write.side_effect=ValueError('PRIVATE');result=self.call();self.assertFalse(result['success']);self.write.assert_called_once();self.kit.observe.assert_called_once()
 def test_timer_cleanup_failure_after_enter_closes_registered_owner(self):
  stages=[]
  @contextlib.contextmanager
  def timer(seconds):
   stages.append(seconds)
   yield
   if len(stages)==2:raise d.DiagnosticHold('TIMER_CLEANUP_FAILED')
  with mock.patch.object(d,'bounded_stage',timer):result=self.call()
  self.manager.__enter__.assert_called_once();self.manager.__exit__.assert_called_once()
  self.kit.observe.assert_not_called();self.assertFalse(result['success'])
  self.assertEqual(result['failure_code'],'TIMER_CLEANUP_FAILED')
 def test_shared_parent_cleanup_unknown_preserves_hold_and_primary(self):
  error=KeyboardInterrupt();error.__cause__=ValueError('READER_PARENT_CLEANUP_UNKNOWN')
  self.kit.observe.side_effect=error;result=self.call()
  self.assertFalse(result['success']);self.assertEqual(result['failure_code'],'INTERRUPTED')
  self.assertIs(result['cleanup_uncertainty'],True);self.kit.observe.assert_called_once()
 def test_arbitrary_cause_text_remains_private(self):
  error=ValueError('PRIVATE');error.__cause__=ValueError('PRIVATE_CAUSE')
  self.kit.observe.side_effect=error;result=self.call()
  self.assertFalse(result['success']);self.assertNotIn('PRIVATE',str(result));self.assertNotIn('cleanup_uncertainty',result)
 def test_no_timer_around_observe(self):
  armed=[]
  @contextlib.contextmanager
  def timer(seconds):
   armed.append(seconds)
   try:yield
   finally:armed.pop()
  def observe(*unused):self.assertEqual(armed,[]);return self.value
  self.value=self.kit.observe.return_value;self.kit.observe.side_effect=observe
  with mock.patch.object(d,'bounded_stage',timer):self.assertTrue(self.call()['success'])

if __name__=='__main__':unittest.main()
