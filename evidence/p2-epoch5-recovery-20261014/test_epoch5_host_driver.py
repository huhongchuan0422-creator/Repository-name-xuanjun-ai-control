"""Actual driver/sequence/ActivationStore/journal composition in temp filesystem.

External host effects and GitHub are mocked. These are local integration tests,
not UK production admission or end-to-end acceptance.
"""
import copy,json,os,pathlib,sys,tempfile,unittest
from contextlib import contextmanager
from unittest import mock
sys.path.insert(0,str(pathlib.Path(os.environ['P2_NEW_ROOT'])/'stage1'))
import epoch5_host_driver as s
import epoch5_attempt_journal as journal
from epoch5_recovery_sequence import resume_once,RecoveryHold,PHASES
from activation_control import ActivationStore

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=self.tmp.name
  self.store=ActivationStore(root+'/active.json',root+'/epochs.jsonl',root+'/activation.lock',owner_uid=os.getuid())
  instance='12345678-1234-4234-8234-123456789abc'
  self.store.prepare('a'*64,'b'*64,'c'*64,instance,1,instance,root+'/db',root+'/sock')
  self.store.fence(1,instance);self.store.fence(2,instance);self.store.fence(3,instance);self.store.fence(4,instance);self.old=self.store.read()
  self.new=dict(self.old,epoch=6,release_sha256=s.MANIFEST,config_sha256='e'*64)
  self.plan={'artifact':{'releases':'/opt/xuanjun-control-releases','manifest':'manifest','source_commit':'source','source_tree':'tree'},
   'runtime':{'release_directory':'integration-'+s.MANIFEST[:16]},'activation_proposal':self.new,
   'cutover':{'legacy_bindings':{}},'tls_config_bytes':'{}'}
  proof={k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited')}
  self.obj=s.HostDriver.__new__(s.HostDriver);o=self.obj
  o.scanner=mock.Mock();o.kit_sha='b'*64;o.snapshot_sha='c'*64;o.review_body_sha='d'*64
  o.authorization={'body_sha256':'d'*64};o.plan=self.plan;o.lock_held=False;o.current=self.old;o.attempt_binding=None
  o.runtime=mock.Mock();o.containment=mock.Mock()
  o.containment.verify_all.return_value={'verified_stopped':True};o.containment.stop_all.return_value={'stop_results':[]}
  adapter=mock.Mock();adapter.measure_quiescence.return_value={'proof':proof}
  adapter.restore_legacy_files.return_value={'unit_files_restored':True,'services_restarted':False}
  o.context={'activation':self.store,'active':self.old,'adapter':adapter,'observation':{'proof':proof},
             'retained':{'native_binding_before':b'old','native_binding_after':b'new'}}
  o.installer={'install':mock.Mock(return_value='/opt/xuanjun-control-releases/integration-'+s.MANIFEST[:16])}
  o.postchecker={'post_install_checks':mock.Mock(return_value={'real_fixture_check':True})}
  o.runtime.restore_retained_owner_masks.return_value={'original_owner_masks_restored':True}
  o.runtime.provision.return_value={'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY','retained_resources_replayed':False}
  o.runtime.reopen_database.return_value={'database_reopened':True};o.runtime.activate.return_value={'services_active':True}
  self.patchdir=mock.patch.object(journal,'DIRECTORY',root);self.patchdir.start();o.journal=journal.AttemptJournal(root)
  self.patches=[mock.patch.object(s.HostDriver,'preserve_prior_receipts',return_value={'retained':True}),
                mock.patch.object(s,'update_native',return_value={'updated':True}),mock.patch.object(s,'exclusive_file')]
  for p in self.patches:p.start()
  o.verify_approval=mock.Mock();o.preflight=mock.Mock(return_value={'snapshot':True});o.verify_snapshot_binding=mock.Mock()
  @contextmanager
  def locked():
   o.lock_held=True
   try:yield
   finally:o.lock_held=False
  o.install_lock=locked
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.patchdir.stop();self.tmp.cleanup()
 def execute(self):return resume_once(self.obj,self.plan,7000000000)
 def real_tls_hold(self,diagnostic_failure=False):
  import time,p2_tls_lifecycle as tls
  root=self.tmp.name+'/tls';os.mkdir(root,0o700);os.mkdir(root+'/logs',0o700)
  code="import os,time\np=os.fork()\nif p==0:\n os.setsid()\n time.sleep(1.8)\n os._exit(0)\ntime.sleep(5)"
  self.obj.runtime.provision.side_effect=lambda *a:tls.command([sys.executable,'-I','-B','-c',code],timeout=.15)
  start=time.monotonic()
  with mock.patch.object(tls,'ROOT',root),mock.patch.object(tls,'COMMAND_CLEANUP_SECONDS',.15):
   if diagnostic_failure:
    with mock.patch.object(tls,'command_failure',side_effect=PermissionError('diagnostic denied')):
     with self.assertRaises(RecoveryHold):self.execute()
   else:
    with self.assertRaises(RecoveryHold):self.execute()
  elapsed=time.monotonic()-start;self.assertLess(elapsed,1.2)
  self.assert_all_cleanup_attempted();self.obj.containment.stop_all.assert_called_once()
  self.assertEqual(self.store.read()['state'],'PREPARED');self.assertEqual(self.store.read()['epoch'],7)
  value=json.loads(pathlib.Path(self.obj.journal.path).read_text())
  self.assertEqual(value['stage'],'HOLD');self.assertFalse(value['automatic_retry'])
  self.assertEqual(len(value['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['operations']),6)
  print('REAL_TLS_TO_HOLD cleanup_groups=6 diagnostic_failure=%s elapsed=%.3f' % (diagnostic_failure,elapsed))
 def test_real_escaped_pipe_timeout_reaches_all_containment(self):self.real_tls_hold()
 def test_real_tls_diagnostic_failure_reaches_all_containment(self):self.real_tls_hold(diagnostic_failure=True)
 def test_real_epoch_and_journal_success(self):
  result=self.execute();self.assertEqual(self.store.read()['state'],'ACTIVE');self.assertEqual(self.store.read()['epoch'],6)
  self.assertEqual(result['completed'],list(PHASES));self.assertEqual(result['production_acceptance'],'PENDING')
  saved=json.loads(pathlib.Path(self.obj.journal.path).read_text());self.assertIn('authorization',saved)
  self.obj.runtime.restore.assert_not_called();self.obj.containment.stop_all.assert_not_called()
 def test_tls_failure_fences_before_stops(self):
  self.obj.runtime.provision.side_effect=ValueError('TLS')
  with self.assertRaises(RecoveryHold):self.execute()
  self.assertEqual(self.store.read()['state'],'PREPARED');self.assertEqual(self.store.read()['epoch'],7)
  self.obj.containment.stop_all.assert_called_once();self.obj.runtime.restore.assert_not_called()
 def test_postcheck_failure_fences_active(self):
  self.obj.postchecker['post_install_checks'].side_effect=ValueError('HTTPS')
  with self.assertRaises(RecoveryHold):self.execute()
  self.assertEqual(self.store.read()['epoch'],7);self.assertEqual(self.store.read()['state'],'PREPARED')
 def test_staging_failure_fences_old_epoch(self):
  self.obj.installer['install'].side_effect=ValueError('stage')
  with self.assertRaises(RecoveryHold):self.execute()
  self.assertEqual(self.store.read()['epoch'],6)
  self.obj.runtime.provision.assert_not_called();self.obj.containment.stop_all.assert_called_once()
 def test_native_binding_failure_holds_new_epoch(self):
  with mock.patch.object(s,'update_native',side_effect=ValueError('CAS')):
   with self.assertRaises(RecoveryHold):self.execute()
  self.assertEqual(self.store.read()['epoch'],7);self.obj.runtime.provision.assert_not_called()
 def test_database_reopen_failure_no_activate(self):
  self.obj.runtime.reopen_database.side_effect=ValueError('DB')
  with self.assertRaises(RecoveryHold):self.execute()
  self.obj.runtime.activate.assert_not_called()
 def test_existing_attempt_prevents_effects(self):
  self.obj.journal.create({'old':True})
  with self.assertRaises(FileExistsError):self.execute()
  self.obj.installer['install'].assert_not_called()
 def test_stop_failure_recorded_unknown(self):
  self.obj.runtime.provision.side_effect=ValueError('TLS');self.obj.containment.stop_all.side_effect=OSError('stop')
  with self.assertRaises(RecoveryHold):self.execute()
  saved=json.loads(pathlib.Path(self.obj.journal.path).read_text())
  self.assertEqual(saved['containment']['stop_exact_new_services']['status'],'UNKNOWN')
 def test_failure_restores_boot_and_owner_masks(self):
  self.obj.runtime.activate.side_effect=ValueError('partial start')
  with self.assertRaises(RecoveryHold):self.execute()
  self.obj.runtime._restore_boot.assert_called_once()
  self.obj.runtime.restore_retained_owner_masks.assert_called_once_with(self.plan)
 def test_boot_restore_failure_still_restores_both_masks(self):
  self.obj.runtime.provision.side_effect=ValueError('TLS')
  self.obj.runtime._restore_boot.side_effect=OSError('boot')
  with self.assertRaises(RecoveryHold):self.execute()
  self.obj.runtime.restore_retained_owner_masks.assert_called_once()
  self.obj.context['adapter'].restore_legacy_files.assert_called_with(preserve_mask=True)
  saved=json.loads(pathlib.Path(self.obj.journal.path).read_text())
  self.assertEqual(saved['containment']['verify_stopped_and_preserve_legacy_masks']['status'],'UNKNOWN')
 def test_postchecker_receives_new_identity(self):
  self.execute();args=self.obj.postchecker['post_install_checks'].call_args[0]
  self.assertEqual(args[0]['activation']['release_sha256'],s.MANIFEST);self.assertEqual(args[2],{'epoch':6})
 def assert_all_cleanup_attempted(self):
  self.obj.runtime._restore_boot.assert_called_once()
  self.obj.runtime.restore_retained_owner_masks.assert_called_once_with(self.plan)
  self.obj.context['adapter'].restore_legacy_files.assert_called_with(preserve_mask=True)
  self.assertEqual(self.obj.containment.verify_all.call_count,3)
  self.assertGreaterEqual(self.obj.context['adapter'].measure_quiescence.call_count,1)
 def fail_and_saved(self):
  self.obj.runtime.activate.side_effect=ValueError('partial activation')
  with self.assertRaises(RecoveryHold):self.execute()
  return json.loads(pathlib.Path(self.obj.journal.path).read_text())
 def test_first_stopped_observation_failure_keeps_every_cleanup(self):
  self.obj.containment.verify_all.side_effect=[{'pre_rebind':True},OSError('cgroup unreadable'),{'verified_stopped':True}]
  saved=self.fail_and_saved();self.assert_all_cleanup_attempted()
  row=saved['containment']['verify_stopped_and_preserve_legacy_masks']
  self.assertEqual(row['status'],'UNKNOWN')
  self.assertEqual(row['evidence']['failed_operations'],['stopped_before'])
  self.assertEqual(row['evidence']['operations']['stopped_after']['status'],'OBSERVED')
 def test_both_stopped_observations_fail_keep_every_cleanup(self):
  self.obj.containment.verify_all.side_effect=[{'pre_rebind':True},OSError('before'),OSError('after')]
  saved=self.fail_and_saved();self.assert_all_cleanup_attempted()
  self.assertEqual(saved['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['failed_operations'],['stopped_before','stopped_after'])
 def test_owner_mask_failure_still_attempts_legacy_and_remeasurement(self):
  self.obj.runtime.restore_retained_owner_masks.side_effect=PermissionError('owner')
  saved=self.fail_and_saved();self.assert_all_cleanup_attempted()
  self.assertIn('owner_masks',saved['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['failed_operations'])
 def test_legacy_mask_failure_still_attempts_remeasurement(self):
  self.obj.context['adapter'].restore_legacy_files.side_effect=PermissionError('legacy')
  self.obj.runtime.provision.side_effect=ValueError('tls')
  with self.assertRaises(RecoveryHold):self.execute()
  self.assert_all_cleanup_attempted()
  saved=json.loads(pathlib.Path(self.obj.journal.path).read_text())
  self.assertIn('legacy_masks',saved['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['failed_operations'])
 def test_post_cleanup_observation_failure_is_durable_unknown(self):
  self.obj.containment.verify_all.side_effect=[{'pre_rebind':True},{'verified_stopped':True},OSError('after')]
  saved=self.fail_and_saved();self.assert_all_cleanup_attempted()
  self.assertEqual(saved['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['failed_operations'],['stopped_after'])
 def test_post_cleanup_legacy_measurement_failure_is_durable_unknown(self):
  original=self.obj.context['adapter'].measure_quiescence.return_value
  self.obj.context['adapter'].measure_quiescence.side_effect=[original,OSError('after')]
  saved=self.fail_and_saved();self.assert_all_cleanup_attempted()
  self.assertEqual(saved['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['failed_operations'],['legacy_after'])
 def test_boot_failure_preserves_each_cleanup_status(self):
  self.obj.runtime._restore_boot.side_effect=PermissionError('boot')
  saved=self.fail_and_saved();self.assert_all_cleanup_attempted()
  ops=saved['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['operations']
  self.assertEqual(ops['boot']['status'],'UNKNOWN')
  self.assertTrue(all(ops[k]['status']=='OBSERVED' for k in ('owner_masks','legacy_masks','stopped_after','legacy_after')))
 def test_multiple_failures_preserved_and_no_retry(self):
  self.obj.containment.verify_all.side_effect=[{'pre_rebind':True},OSError('before'),OSError('after')]
  self.obj.runtime._restore_boot.side_effect=PermissionError('boot')
  self.obj.runtime.restore_retained_owner_masks.side_effect=KeyboardInterrupt()
  saved=self.fail_and_saved();self.assert_all_cleanup_attempted()
  self.assertEqual(saved['stage'],'HOLD');self.assertFalse(saved['automatic_retry'])
  self.assertEqual(saved['containment']['verify_stopped_and_preserve_legacy_masks']['evidence']['failed_operations'],['stopped_before','boot','owner_masks','stopped_after'])
if __name__=='__main__':unittest.main()
