"""Ordinary temporary-file tests; no M99, native service or production data."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('owner_production_start',Path(__file__).with_name('owner_production_start.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class OwnerStartTests(unittest.TestCase):
 def inputs(self):return {'owner_authority':copy.deepcopy(m.OWNER_AUTHORITY),'nonce':'owner-original-transaction-20261019'}
 def test_owner_authority_needs_no_reviewer(self):
  self.assertTrue(m.validate_owner_authority(self.inputs()))
 def test_reviewer_does_not_substitute_owner(self):
  with self.assertRaisesRegex(RuntimeError,'OWNER_AUTHORITY_BINDING'):m.validate_owner_authority({'independent_review_comment_id':1,'nonce':'a'*32})
 def test_changed_scope_rejected(self):
  p=self.inputs();p['owner_authority']['scope']='UK_P2'
  with self.assertRaisesRegex(RuntimeError,'OWNER_AUTHORITY_BINDING'):m.validate_owner_authority(p)
 def test_nonce_required(self):
  p=self.inputs();p['nonce']='new'
  with self.assertRaisesRegex(RuntimeError,'OWNER_INPUT_NONCE'):m.validate_owner_authority(p)
 def test_final_units_dedicated_identity(self):
  self.assertEqual(len(m.units('xuanjun-s07')),3)
  for b in m.units('xuanjun-s07').values():
   self.assertIn(b'User=xuanjun-s07',b);self.assertIn(b'domestic-final-v1/rootfs',b)
   self.assertNotIn(b'domestic-r2',b);self.assertNotIn(b'[Install]',b)
 def test_wrong_identity_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'DEDICATED_IDENTITY_NAME'):m.units('nobody')
 def test_original_state_and_published_bytes_preserved(self):
  n=m.stopped_library()
  self.assertEqual(n['STATE'],'/var/lib/xuanjun-pr99-s09-stopped-install-v1')
  self.assertEqual(m.sha(m.FROZEN_STOPPED.encode()),'99225aacc11cae6dc9d190015c95c9883e13d8e2691da864fb026f8afdfee315')
  self.assertIn('windows-interaction-http.service',n['PROTECTED'])
 def fixture(self,root):
  n=m.stopped_library();state=root/'old-state';state.mkdir();units=root/'units';units.mkdir()
  n['STATE']=str(state)
  n['read_regular']=lambda p,**kw:Path(p).read_bytes()
  n['snapshot']=lambda:{'protected':'UNCHANGED'}
  n['stopped']=lambda name:True
  operations=[];n['systemctl']=lambda *a:operations.append(a) or ''
  (state/'receipt.json').write_bytes(n['encode']({'status':'QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION','manifest':n['manifest'](),'starts':0,'enables':0}))
  (state/'intent.json').write_bytes(n['encode']({'manifest':n['manifest']()}))
  for name,data in n['unit_bytes']().items():
   (units/name).write_bytes(data)
   (state/(name+'.created')).write_bytes(n['encode']({'sha256':n['digest'](data)}))
  return n,state,units,operations
 def test_exact_original_stopped_retirement(self):
  with tempfile.TemporaryDirectory() as d:
   n,state,units,operations=self.fixture(Path(d))
   with patch.object(m,'SYSTEMD',units),patch.object(m,'stopped_library',lambda:n),patch.object(m,'stopped',lambda name:True):
    c=m.inspect_stopped_candidate();self.assertEqual(c['kind'],'EXACT_OWNED_STOPPED_CANDIDATE')
    r=m.retire_stopped_candidate(self.inputs(),c)
    self.assertEqual(r['status'],'OWNED_STOPPED_UNITS_REMOVED')
    self.assertFalse(list(units.iterdir()));self.assertEqual(operations,[('daemon-reload',)])
    self.assertEqual(m.inspect_stopped_candidate()['kind'],'NO_CANDIDATE')
 def test_foreign_bytes_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   n,state,units,operations=self.fixture(Path(d));p=units/n['NAMES'][0];p.write_bytes(b'foreign')
   with patch.object(m,'SYSTEMD',units),patch.object(m,'stopped_library',lambda:n),patch.object(m,'stopped',lambda name:True):
    with self.assertRaisesRegex(RuntimeError,'FOREIGN_OR_RUNNING_CANDIDATE'):m.inspect_stopped_candidate()
   self.assertEqual(p.read_bytes(),b'foreign');self.assertFalse(operations)
 def test_running_candidate_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   n,state,units,operations=self.fixture(Path(d))
   with patch.object(m,'SYSTEMD',units),patch.object(m,'stopped_library',lambda:n),patch.object(m,'stopped',lambda name:False):
    with self.assertRaisesRegex(RuntimeError,'FOREIGN_OR_RUNNING_CANDIDATE'):m.inspect_stopped_candidate()
   self.assertEqual(len(list(units.iterdir())),3);self.assertFalse(operations)
 def test_partial_candidate_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   n,state,units,operations=self.fixture(Path(d));(units/n['NAMES'][0]).unlink()
   with patch.object(m,'SYSTEMD',units),patch.object(m,'stopped_library',lambda:n):
    with self.assertRaisesRegex(RuntimeError,'PARTIAL_OR_FOREIGN_CANDIDATE'):m.inspect_stopped_candidate()
   self.assertEqual(len(list(units.iterdir())),2);self.assertFalse(operations)
 def test_unknown_prior_retirement_not_replayed(self):
  with tempfile.TemporaryDirectory() as d:
   n,state,units,operations=self.fixture(Path(d));(state/'rollback.intent.json').write_text('{}')
   with patch.object(m,'SYSTEMD',units),patch.object(m,'stopped_library',lambda:n):
    with self.assertRaisesRegex(RuntimeError,'ORIGINAL_RETIREMENT_ALREADY_CONSUMED'):m.inspect_stopped_candidate()
   self.assertFalse(operations);self.assertEqual(len(list(units.iterdir())),3)
 def test_retirement_has_to_precede_creation(self):
  units=m.units('xuanjun-s07')
  ops=[{'operation':'retire-stopped-candidate','status':'SUCCEEDED'}]+[{'operation':'create:'+n,'status':'SUCCEEDED'} for n in units]
  m.validate_effect_sequence(ops,units)
  ops[0]['status']='UNKNOWN'
  with self.assertRaisesRegex(RuntimeError,'OPERATION_AFTER_UNRESOLVED_RETIREMENT'):m.validate_effect_sequence(ops,units)
  m.validate_effect_sequence(ops[:1],units)
 def test_final_data_proofs_still_mandatory(self):
  with self.assertRaisesRegex(RuntimeError,'SOURCE_FENCE_PROOF'):
   m.validate_final_receipts(self.inputs(),b'{}',b'{}',b'{}',1)
 def test_no_native_action_without_inputs(self):
  with patch.object(m.os,'geteuid',lambda:0),patch.object(m.os,'uname') as uname,patch.object(m.os.path,'lexists',lambda p:False),patch.object(m,'admit',side_effect=RuntimeError('FINAL_INPUTS_MISSING')),patch.object(m,'ctl') as native:
   uname.return_value.nodename=m.HOST
   with self.assertRaisesRegex(RuntimeError,'FINAL_INPUTS_MISSING'):m.start()
   native.assert_not_called()


if __name__=='__main__':unittest.main()
