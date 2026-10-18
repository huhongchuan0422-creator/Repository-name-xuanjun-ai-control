"""Static profile ledger tests: temporary local files, no publisher/host calls."""
import copy,fcntl,json,os,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_customer_release as r,pr122_customer_workflow as w,pr122_static_workflow as s
from scripts.pr122_customer_core import canonical,digest,Denied
from tests import test_pr122_customer_workflow as old
class StaticTests(unittest.TestCase):
 inventory=old.WorkflowTests.inventory
 patches=old.WorkflowTests.patches
 fake_run=old.WorkflowTests.fake_run
 def setUp(self):
  old.WorkflowTests.setUp(self)
  self.ops.inputs={k:{'stage':k} for k in s.STAGES};self.ops.implementations={k:k.encode() for k in s.STAGES};self.ops.receipts={k:dict(state='COMPLETE',receipt_sha256=digest(k.encode()),effect_sha256=digest(('effect'+k).encode()),source_commit=self.base['source_commit']) for k in s.STAGES}
  self.base.update(deployment_profile=s.PROFILE,permit_window_seconds=18000,static_baseline_sha256='b'*64,host_pins_sha256='c'*64)
  self.base['workflow_contract']={'schema':1,'stages':[dict(stage=k,input_sha256=digest(canonical(self.ops.input(k))),implementation_sha256=digest(self.ops.implementation(k)),adopt_receipt_sha256=None,recovery_actions=['RECONCILE_STATIC']) for k in s.STAGES]}
  self.approval.update(attempt_policy=s.POLICY,deployment_profile=s.PROFILE,permit_window_seconds=18000,static_baseline_sha256='b'*64,host_pins_sha256='c'*64,expires_unix=self.approval['issued_unix']+18000)
  self.bind_contract()
  self.ops.proof=lambda stage,status=None:dict(status=status or self.ops.proof_status,action='RECONCILE_STATIC',evidence_sha256=digest(b'fixture evidence'),checkpoint=copy.deepcopy(self.ops.receipts[stage]) if (status or self.ops.proof_status)=='COMPLETE' else None)
 bind_contract=old.WorkflowTests.bind_contract
 def apply(self):
  fd=os.open(r.LOCK,os.O_RDWR|os.O_CREAT,0o600)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   with patch.object(r,'gate',return_value=self.approval):return s.StaticCoordinator(r,self.source,4,self.base,self.approval,self.ops,fd).run()
  finally:os.close(fd)
 def test_one_ledger_success_stop(self):
  with self.patches():
   result=self.apply();self.assertEqual(result['attempts_used'],1)
   with self.assertRaisesRegex(Denied,'FINISHED'):self.apply()
  self.assertEqual(len(self.ops.executed),10)
 def test_safe_retry_no_repeat_completed(self):
  calls=[];self.ops.proof_status='SAFE_TO_RETRY'
  def fail(stage,lease):
   if stage=='STATIC_PREPARED' and len(calls)<2:calls.append(1);raise RuntimeError('fixture')
  self.ops.execute_hook=fail
  with self.patches():result=self.apply()
  self.assertEqual(result['attempts_used'],3);self.assertEqual(sum(x[0]=='BACKUP_VERIFIED' for x in self.ops.executed),1)
 def test_five_failures_no_six(self):
  self.ops.proof_status='SAFE_TO_RETRY';self.ops.execute_hook=lambda stage,lease:(_ for _ in ()).throw(RuntimeError('fixture'))
  with self.patches():
   for _ in range(2):
    with self.assertRaises(w.WorkflowStopped) as c:self.apply()
    self.assertEqual(c.exception.summary['attempts_used'],5)
  self.assertEqual(len(self.ops.executed),5)
 def test_unknown_then_readonly_complete_same_attempt(self):
  def fail(stage,lease):
   if stage==s.STAGES[-1]:raise KeyboardInterrupt()
  self.ops.execute_hook=fail
  with self.patches():
   with self.assertRaises(KeyboardInterrupt):self.apply()
   before=list(self.ops.executed);self.ops.proof_status='COMPLETE';result=self.apply()
  self.assertEqual(result['attempts_used'],1);self.assertEqual(self.ops.executed,before)
 def test_old_scope_no_upgrade(self):
  self.approval['attempt_policy']=w.POLICY
  with self.patches(),self.assertRaisesRegex(Denied,'EXPLICIT_NEW_PERMISSION'):self.apply()
 def test_exact_window(self):
  self.approval['expires_unix']-=1
  with self.patches(),self.assertRaisesRegex(Denied,'EXACT_WINDOW'):self.apply()
 def test_source_change_seals_old_ledger(self):
  self.ops.execute_hook=lambda stage,lease:(_ for _ in ()).throw(RuntimeError('fixture'))
  with self.patches():
   with self.assertRaises(w.WorkflowStopped):self.apply()
   self.base['other_changed_field']=True
   with self.assertRaisesRegex(Denied,'CHANGED_SCOPE'):self.apply()
 def test_fixed_stage_contract_no_injection(self):
  self.base['workflow_contract']['stages'][0]['stage']='SHELL'
  self.bind_contract()
  with self.patches(),self.assertRaisesRegex(Denied,'STAGE_SCHEMA'):self.apply()

 def test_verification_crosses_expiry_keeps_pending_intent(self):
  now=[self.approval['issued_unix']+1]
  self.ops.verify_hook=lambda stage,value:now.__setitem__(0,self.approval['expires_unix']+1)
  with self.patches(),patch.object(w.time,'time',side_effect=lambda:now[0]):
   with self.assertRaises(Exception):self.apply()
  ledger=json.loads((r.STATE/(r.TXN+'.attempts.json')).read_text())
  self.assertEqual(ledger['intent']['stage'],s.STAGES[0]);self.assertEqual(ledger['checkpoints'],{})
  self.assertEqual(ledger['state'],'HOLD')
 def test_recovery_verification_crosses_expiry_does_not_commit(self):
  self.ops.execute_hook=lambda stage,lease:(_ for _ in ()).throw(KeyboardInterrupt())
  with self.patches():
   with self.assertRaises(KeyboardInterrupt):self.apply()
  before=(r.STATE/(r.TXN+'.attempts.json')).read_bytes();now=[self.approval['issued_unix']+1]
  self.ops.proof_status='COMPLETE';self.ops.verify_hook=lambda stage,value:now.__setitem__(0,self.approval['expires_unix']+1)
  with self.patches(),patch.object(w.time,'time',side_effect=lambda:now[0]):
   with self.assertRaises(Exception):self.apply()
  self.assertEqual((r.STATE/(r.TXN+'.attempts.json')).read_bytes(),before)
