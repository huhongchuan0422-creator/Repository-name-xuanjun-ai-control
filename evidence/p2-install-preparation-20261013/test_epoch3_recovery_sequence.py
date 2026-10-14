import copy,unittest
from contextlib import contextmanager
import epoch3_recovery_sequence as subject

class Driver:
 def __init__(self,fail=None):self.fail=fail;self.calls=[];self.exists=False;self.records=[]
 def call(self,name):
  self.calls.append(name)
  if self.fail==name:raise ValueError('fixture failure')
  return {'fixture_evidence':name}
 def verify_approval(self,*args):return self.call('verify_approval')
 @contextmanager
 def install_lock(self):
  self.call('lock')
  try:yield
  finally:self.call('unlock')
 def preflight(self,*args):return self.call('preflight')
 def verify_snapshot_binding(self,*args):return self.call('verify_snapshot_binding')
 def create_attempt(self,state,*args):
  self.call('create_attempt')
  if self.exists:raise FileExistsError('attempt consumed')
  self.exists=True;self.records.append(copy.deepcopy(state))
 def save_attempt(self,state):self.records.append(copy.deepcopy(state));self.call('save_attempt')
 def __getattr__(self,name):
  if name in subject.PHASES or name in ('fence_uncertain_activation','stop_exact_new_services','verify_stopped_and_preserve_legacy_masks'):
   return lambda plan:self.call(name)
  raise AttributeError(name)

class SequenceTests(unittest.TestCase):
 def test_success_order_and_not_final_acceptance(self):
  d=Driver();v=subject.resume_once(d,{},{});effects=[x for x in d.calls if x in subject.PHASES]
  self.assertEqual(effects,list(subject.PHASES));self.assertEqual(v['production_acceptance'],'PENDING')
  self.assertNotIn('fence_uncertain_activation',d.calls)
 def test_existing_attempt_prevents_all_effects(self):
  d=Driver();d.exists=True
  with self.assertRaises(FileExistsError):subject.resume_once(d,{},{})
  self.assertFalse(any(x in d.calls for x in subject.PHASES))
 def test_second_execution_rejected(self):
  d=Driver();subject.resume_once(d,{},{});before=len(d.calls)
  with self.assertRaises(FileExistsError):subject.resume_once(d,{},{})
  self.assertFalse(any(x in d.calls[before:] for x in subject.PHASES))
 def test_approval_failure_no_attempt(self):
  d=Driver('verify_approval')
  with self.assertRaises(ValueError):subject.resume_once(d,{},{})
  self.assertFalse(d.exists)
 def test_snapshot_failure_no_attempt(self):
  d=Driver('verify_snapshot_binding')
  with self.assertRaises(ValueError):subject.resume_once(d,{},{})
  self.assertFalse(d.exists)
 def test_preflight_failure_no_attempt(self):
  d=Driver('preflight')
  with self.assertRaises(ValueError):subject.resume_once(d,{},{})
  self.assertFalse(d.exists)
 def test_every_phase_failure_contains_and_never_retries(self):
  for phase in subject.PHASES:
   with self.subTest(phase=phase):
    d=Driver(phase)
    with self.assertRaises(subject.RecoveryHold):subject.resume_once(d,{},{})
    self.assertEqual(d.calls.count(phase),1)
    self.assertEqual(d.records[-1]['stage'],'HOLD')
    self.assertLess(d.calls.index('fence_uncertain_activation'),d.calls.index('stop_exact_new_services'))
    self.assertFalse(d.records[-1]['automatic_retry'])
 def test_containment_failure_keeps_other_containment(self):
  d=Driver('post_install_checks')
  d.fence_uncertain_activation=lambda plan:(_ for _ in ()).throw(OSError('fence failed'))
  with self.assertRaises(subject.RecoveryHold):subject.resume_once(d,{},{})
  self.assertIn('stop_exact_new_services',d.calls)
  self.assertEqual(d.records[-1]['containment']['fence_uncertain_activation']['status'],'UNKNOWN')
 def test_final_receipt_failure_reported_unknown(self):
  d=Driver('save_attempt')
  with self.assertRaisesRegex(subject.RecoveryHold,'FINAL_RECEIPT_UNAVAILABLE'):subject.resume_once(d,{},{})
  self.assertIn('stop_exact_new_services',d.calls)
 def test_empty_phase_evidence_not_success(self):
  d=Driver();d.stage_exact_release=lambda plan:{}
  with self.assertRaises(subject.RecoveryHold):subject.resume_once(d,{},{})
  self.assertEqual(d.records[-1]['completed'],[])
 def test_intent_written_before_each_effect(self):
  d=Driver()
  for phase in subject.PHASES:
   def effect(plan,phase=phase):
    self.assertEqual(d.records[-1]['stage'],phase+'_INTENT');return d.call(phase)
   setattr(d,phase,effect)
  subject.resume_once(d,{},{})
 def test_detailed_unknown_containment_evidence_saved(self):
  d=Driver('post_install_checks');evidence={'operations':{'stopped_before':{'status':'UNKNOWN','error_type':'OSError'}},'failed_operations':['stopped_before']}
  def incomplete(plan):raise subject.ContainmentIncomplete(evidence)
  d.verify_stopped_and_preserve_legacy_masks=incomplete
  with self.assertRaises(subject.RecoveryHold):subject.resume_once(d,{},{})
  row=d.records[-1]['containment']['verify_stopped_and_preserve_legacy_masks']
  self.assertEqual(row['status'],'UNKNOWN');self.assertEqual(row['evidence'],evidence)
if __name__=='__main__':unittest.main()
