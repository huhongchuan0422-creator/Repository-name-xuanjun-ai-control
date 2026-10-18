import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_customer_attempts as a, pr122_customer_release as r
from scripts.pr122_customer_core import canonical, digest, Denied
from tests import test_pr122_customer_release as release_tests

class AttemptsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.state=self.root/'state';self.config=self.root/'config';self.config.mkdir()
  self.approval={'max_executions':5,'attempt_policy':a.POLICY,'issued_unix':int(time.time())-5,'expires_unix':int(time.time())+500}
  for p in (patch.object(a,'protected_directory',lambda path:None),patch.object(a,'read_private',lambda path:json.loads(Path(path).read_bytes())),patch.object(a.os,'geteuid',return_value=0)):
   p.start();self.addCleanup(p.stop)
 def new(self):return a.Attempts(self.state,'original-txn',self.approval,4,{'source_commit':'a'*40},r.atomic_json,self.config)
 def recover(self,attempt):
  e={'schema':1,'previous_attempt_sha256':digest(canonical(attempt.row)),'binding_sha256':digest(canonical(attempt.binding)),'diagnosis':'Verified distinct fixture cause '+str(attempt.row['number']),'recovery':'Restored exact original bytes without installation effects','no_install_effects':True,'checked_unix':int(time.time())}
  (self.config/'INSTALL_RETRY_EVIDENCE.json').write_bytes(canonical(e));return e
 def test_five_admitted_attempts_persist_across_objects_and_sixth_denied(self):
  for number in range(1,6):
   item=self.new();self.assertEqual(item.row['number'],number);item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');self.recover(item)
  with self.assertRaisesRegex(Denied,'EXHAUSTED'):self.new()
 def test_old_single_use_permit_never_gains_extra_attempt(self):
  self.approval={'max_executions':1,'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+500}
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');self.recover(item)
  with self.assertRaisesRegex(Denied,'EXHAUSTED'):self.new()
 def test_explicit_policy_and_exact_integer_required(self):
  for limit in (True,False,0,6,1.0,'5',None):
   with self.subTest(limit=limit),self.assertRaises(Denied):a.validate_approval({'max_executions':limit,'attempt_policy':a.POLICY})
  with self.assertRaises(Denied):a.validate_approval({'max_executions':5})
 def test_crash_unknown_durable_no_retry(self):
  self.new()
  with self.assertRaisesRegex(Denied,'UNRESOLVED'):self.new()
 def test_success_and_partial_stay_closed(self):
  for state in ('HTTPS_SMOKE_PASS_AWAIT_14_REAL_ACCEPTANCE','HOLD_UNKNOWN_OR_PARTIAL'):
   with self.subTest(state=state):
    self.state=self.root/state;item=self.new();item.finish(state)
    with self.assertRaises(Denied):self.new()
 def test_previous_transaction_seals_legacy_partial_and_success(self):
  self.state.mkdir();(self.state/'original-txn').mkdir()
  with self.assertRaisesRegex(Denied,'SEALED'):self.new()
  self.assertFalse((self.state/'original-txn.attempts.json').exists())
 def test_changed_comment_scope_window_or_limit_cannot_reset_counter(self):
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');self.recover(item)
  for key,val in [('expires_unix',self.approval['expires_unix']+1),('max_executions',4),('source_commit','b'*40)]:
   old=dict(self.approval);self.approval[key]=val
   with self.assertRaisesRegex(Denied,'BINDING'):self.new()
   self.approval=old
 def test_no_recovery_evidence_no_retry(self):
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH')
  with self.assertRaises(FileNotFoundError):self.new()
  self.assertEqual(len(json.loads(item.path.read_bytes())['attempts']),1)
 def test_recovery_must_bind_predecessor_scope_time_and_explicit_attestation(self):
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');valid=self.recover(item)
  for key,val in [('previous_attempt_sha256','f'*64),('binding_sha256','f'*64),('checked_unix',0),('no_install_effects',False),('diagnosis',''),('recovery','')]:
   bad=dict(valid);bad[key]=val;(self.config/'INSTALL_RETRY_EVIDENCE.json').write_bytes(canonical(bad))
   with self.subTest(key=key),self.assertRaises(Denied):self.new()
 def test_stale_recovery_cannot_reuse_for_next_failure(self):
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');self.recover(item)
  second=self.new();second.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH')
  with self.assertRaisesRegex(Denied,'BINDING'):self.new()
 def test_finish_once_and_unknown_error_not_safe(self):
  item=self.new()
  with self.assertRaises(Denied):item.finish('SAFE_PREACTIVATION_FAILURE','unexpected')
  item.finish('HOLD_UNKNOWN_OR_PARTIAL')
  with self.assertRaises(Denied):item.finish('HOLD_UNKNOWN_OR_PARTIAL')
 def test_corrupt_history_not_reset(self):
  item=self.new();item.path.write_bytes(b'{}')
  with self.assertRaises(Denied):self.new()
 def test_chain_tamper_rejected(self):
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');self.recover(item)
  data=json.loads(item.path.read_bytes());data['attempts'][0]['previous_sha256']='bad';item.path.write_bytes(canonical(data))
  with self.assertRaisesRegex(Denied,'CHAIN'):self.new()
 def test_expiry_no_state_created(self):
  self.approval['expires_unix']=0
  with self.assertRaises(Denied):self.new()
  self.assertFalse(self.state.exists())

 def test_new_process_observes_consumed_unknown_attempt(self):
  import subprocess,sys
  self.new()
  code="""import json,sys
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_customer_attempts as a,pr122_customer_release as r
from scripts.pr122_customer_core import Denied
with patch.object(a,'protected_directory',lambda p:None),patch.object(a,'read_private',lambda p:json.loads(Path(p).read_bytes())),patch.object(a.os,'geteuid',return_value=0):
 try:a.Attempts(Path(sys.argv[1]),'original-txn',json.loads(sys.argv[2]),4,{'source_commit':'a'*40},r.atomic_json,Path(sys.argv[3]))
 except Denied as error:
  assert 'UNRESOLVED' in str(error);print('DURABLE_UNKNOWN_HOLD')
 else:raise AssertionError('replayed')
"""
  child=subprocess.run([sys.executable,'-B','-c',code,str(self.state),json.dumps(self.approval),str(self.config)],capture_output=True,text=True,timeout=10)
  self.assertEqual(child.returncode,0,child.stderr);self.assertIn('DURABLE_UNKNOWN_HOLD',child.stdout)
 def test_repeated_root_cause_blocks_even_with_new_recovery(self):
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');first=self.recover(item)
  item=self.new();item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH');second=self.recover(item)
  second['diagnosis']=first['diagnosis'];(self.config/'INSTALL_RETRY_EVIDENCE.json').write_bytes(canonical(second))
  with self.assertRaisesRegex(Denied,'REPEATED_ROOT_CAUSE'):self.new()
 def test_failed_finish_write_leaves_durable_unknown(self):
  item=self.new();item.save=lambda *args:(_ for _ in ()).throw(OSError('fixture disk failure'))
  with self.assertRaises(OSError):item.finish('SAFE_PREACTIVATION_FAILURE','HOLD:SOURCE_HASH')
  with self.assertRaisesRegex(Denied,'UNRESOLVED'):self.new()

class ApplyAttemptsTests(unittest.TestCase):
 setUp=release_tests.ReleaseTests.setUp
 fake_run=release_tests.ReleaseTests.fake_run
 inventory=release_tests.ReleaseTests.inventory
 patches=release_tests.ReleaseTests.patches
 def test_repeated_success_does_not_rerun_commands(self):
  with self.patches():
   r.apply(self.source,4);before=len(self.calls)
   with self.assertRaises(Denied):r.apply(self.source,4)
   self.assertEqual(before,len(self.calls))
 def test_partial_second_invocation_does_not_rerun_commands(self):
  self.fail=lambda args:'start' in args
  with self.patches():
   with self.assertRaises(Denied):r.apply(self.source,4)
   before=len(self.calls)
   with self.assertRaises(Denied):r.apply(self.source,4)
   self.assertEqual(before,len(self.calls))
 def test_unknown_exception_not_classified_safe(self):
  with self.patches(),patch.object(r,'source',side_effect=OSError('unknown')):
   with self.assertRaises(OSError):r.apply(self.source,4)
  ledger=json.loads((r.STATE/(r.TXN+'.attempts.json')).read_bytes())
  self.assertEqual(ledger['attempts'][0]['state'],'HOLD_UNKNOWN_OR_PARTIAL')
 def test_pre_activation_drift_no_install_mutation(self):
  with self.patches(),patch.object(r,'plan_without_absence',return_value={}):
   with self.assertRaises(Denied):r.apply(self.source,4)
  self.assertFalse(r.CODE.exists());self.assertFalse((r.STATE/r.TXN).exists());self.assertEqual(self.calls,[])
 def test_shared_lock_blocks_concurrent_invocation(self):
  import fcntl
  with r.LOCK.open('w') as stream,self.patches():
   fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
   with self.assertRaises(BlockingIOError):r.apply(self.source,4)
  self.assertFalse(r.CODE.exists());self.assertFalse((r.STATE/(r.TXN+'.attempts.json')).exists())

 def test_corrected_source_can_retry_once_with_bound_recovery_then_success_seals(self):
  self.approval['max_executions']=5;self.approval['attempt_policy']=a.POLICY
  original=(self.source/'boot.py').read_bytes();(self.source/'boot.py').write_bytes(b'drift')
  with self.patches():
   with self.assertRaisesRegex(Denied,'SOURCE_HASH'):r.apply(self.source,4)
   ledger_path=r.STATE/(r.TXN+'.attempts.json');ledger=json.loads(ledger_path.read_bytes());last=ledger['attempts'][-1]
   evidence={'schema':1,'previous_attempt_sha256':digest(canonical(last)),'binding_sha256':digest(canonical(ledger['binding'])),'diagnosis':'Fixture source drift before any install operation','recovery':'Exact original reviewed source bytes restored','no_install_effects':True,'checked_unix':int(time.time())}
   (r.CONFIG/'INSTALL_RETRY_EVIDENCE.json').write_bytes(canonical(evidence));(self.source/'boot.py').write_bytes(original)
   result=r.apply(self.source,4);self.assertEqual(result['attempt_number'],2)
   before=len(self.calls)
   with self.assertRaisesRegex(Denied,'SEALED'):r.apply(self.source,4)
   self.assertEqual(before,len(self.calls))

class FileTrustTests(unittest.TestCase):
 def test_actual_nonroot_directory_is_rejected(self):
  with tempfile.TemporaryDirectory() as td,self.assertRaises(Denied):a.protected_directory(Path(td))
 def test_symlink_path_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'real').mkdir();(root/'link').symlink_to(root/'real')
   with self.assertRaises(Denied):a.protected_directory(root/'link')
 def test_actual_nonroot_file_rejected_even_with_directory_fixture(self):
  with tempfile.TemporaryDirectory() as td,patch.object(a,'protected_directory',lambda path:None):
   p=Path(td)/'data';p.write_text('{}');p.chmod(0o600)
   with self.assertRaises(Denied):a.read_private(p)
 def test_symlink_file_not_followed(self):
  with tempfile.TemporaryDirectory() as td,patch.object(a,'protected_directory',lambda path:None):
   p=Path(td)/'data';p.write_text('{}');q=Path(td)/'link';q.symlink_to(p)
   with self.assertRaises((Denied,OSError)):a.read_private(q)
 def test_fifo_nonblocking_rejected(self):
  with tempfile.TemporaryDirectory() as td,patch.object(a,'protected_directory',lambda path:None):
   p=Path(td)/'fifo';os.mkfifo(p,0o600)
   with self.assertRaises(Denied):a.read_private(p)

if __name__=='__main__':unittest.main()
