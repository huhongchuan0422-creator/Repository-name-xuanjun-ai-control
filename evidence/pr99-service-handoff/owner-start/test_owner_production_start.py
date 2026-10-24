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
 def run_start_fixture(self,unknown=False):
  import time
  from contextlib import ExitStack
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);n,oldstate,units,oldops=self.fixture(root);state=root/'production-state'
   p=self.inputs();p.update(unit_hashes={name:m.sha(b) for name,b in m.units('xuanjun-s07').items()},source_writer_fence_receipt_sha256='a'*64,expires_at=int(time.time())+3600)
   active=set();native=[]
   def ctl(*args):
    native.append(args)
    if args[0]=='start':
     if unknown and len(active)==1:raise TimeoutError('native-result-unknown')
     active.add(args[1])
    return ''
   with ExitStack() as stack:
    replacements={'SYSTEMD':units,'STATE':state,'stopped_library':lambda:n,'stopped':lambda name:name not in active,
     'admit':lambda:(p,m.units('xuanjun-s07')),'ports_available':lambda:True,'ctl':ctl,
     'verify_units':lambda payload:None,'supervised':lambda name:name in active,
     'health':lambda port:200 if len(active)==3 else None,
     'read':lambda path,*a,**k:b'fixed-owner-start-inputs' if path==m.INPUTS else Path(path).read_bytes()}
    for key,value in replacements.items():stack.enter_context(patch.object(m,key,value))
    if unknown:
     with self.assertRaises(m.EffectUnknown):m._start()
     self.assertEqual(len(active),1)
     failure=json.loads((state/'failure.json').read_text())
     self.assertEqual(failure['status'],'EFFECT_UNKNOWN_QUERY_ONLY_NO_REPLAY')
     self.assertFalse(any(a[0]=='stop' for a in native))
    else:
     r=m._start();self.assertEqual(r['status'],'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER')
     self.assertEqual(len(active),3);self.assertFalse(r['production_cutover'])
    records=[json.loads(p.read_text()) for p in sorted(state.glob('effect-*.intent.json'))]
    self.assertEqual(records[0],{'operation':'retire-stopped-candidate'})
    self.assertEqual(oldops,[('daemon-reload',)])
    self.assertTrue((oldstate/'rollback.receipt.json').is_file())
    self.assertEqual({p.name:p.read_bytes() for p in units.iterdir()},m.units('xuanjun-s07'))
 def test_start_core_retires_exact_candidate_before_production_creation(self):self.run_start_fixture()
 def test_unknown_start_preserves_state_without_compensating_replay(self):self.run_start_fixture(unknown=True)


class CheckpointCapacityTests(unittest.TestCase):
 def materials(self):
  now=1000000
  files={'opt/trading-system/runtime/ordinary-state-'+str(i).zfill(5)+'.json':'a'*64 for i in range(3000)}
  fence={'action':'PR99_SOURCE_WRITER_FENCE_V1','source_host':'iZ6wee8q9z4t03hvqumwfhZ',
    'writer_inventory_sha256':'b'*64,'writer_epoch':1,'writers_stopped':True,'inflight_drained':True,
    'unresolved_shared_writers':[],'observed_at':now-10}
  rawf=m.canonical(fence)
  checkpoint={'class':'FINAL_CANONICAL_CHECKPOINT','source_fence_sha256':m.sha(rawf),'files':files,
    'database_integrity':'PASS','database_schema_sha256':'c'*64,'captured_at':now-1}
  rawc=m.canonical(checkpoint)
  assignment={'action':'PR99_CANONICAL_WRITER_ASSIGNMENT_V1','target_host':m.HOST,'release':str(m.RELEASE),
    'checkpoint_sha256':m.sha(rawc),'writer_inventory_sha256':'b'*64,'writer_epoch':1,
    'target_identity':'xuanjun-s07','source_writer_resumed':False,'scope':list(m.UNITS)}
  rawa=m.canonical(assignment)
  p={'source_writer_fence_receipt_sha256':m.sha(rawf),'final_checkpoint_receipt_sha256':m.sha(rawc),
    'canonical_writer_assignment_sha256':m.sha(rawa),'writer_inventory_sha256':'b'*64,'writer_epoch':1,
    'final_data_file_hashes':files,'file_hashes':files,'database_schema_sha256':'c'*64}
  return now,p,{'source-writer-fence.receipt.json':rawf,'final-checkpoint.receipt.json':rawc,'canonical-writer-assignment.json':rawa}
 def run_files(self,p,materials,now):
  # Real files and strict byte limits; path ownership is fixture-only.
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name,raw in materials.items():(root/name).write_bytes(raw)
   calls=[]
   def bounded(path,limit):
    raw=Path(path).read_bytes();calls.append(Path(path).name)
    if len(raw)>limit:raise RuntimeError('FILE_TYPE_SIZE')
    return raw
   with patch.object(m,'RELEASE',root),patch.object(m,'read',side_effect=bounded):
    # Keep assignment binding in this ordinary temporary fixture.
    assignment=json.loads(materials['canonical-writer-assignment.json'])
    assignment['release']=str(root);raw=m.canonical(assignment)
    (root/'canonical-writer-assignment.json').write_bytes(raw)
    p=copy.deepcopy(p);p['canonical_writer_assignment_sha256']=m.sha(raw)
    result=m.load_final_receipts(p,now)
   self.assertEqual(len(calls),3);self.assertEqual(len(set(calls)),3)
   return result
 def test_complete_3000_file_checkpoint_larger_than_old_limit(self):
  now,p,materials=self.materials()
  self.assertGreater(len(materials['final-checkpoint.receipt.json']),200000)
  self.assertLess(len(materials['final-checkpoint.receipt.json']),2097152)
  self.assertTrue(self.run_files(p,materials,now))
 def test_oversized_checkpoint_retained_not_truncated(self):
  now,p,materials=self.materials();materials['final-checkpoint.receipt.json']=b'x'*2097153
  with self.assertRaisesRegex(RuntimeError,'FILE_TYPE_SIZE'):self.run_files(p,materials,now)
 def test_large_checkpoint_wrong_hash_still_rejected(self):
  now,p,materials=self.materials();p['final_checkpoint_receipt_sha256']='0'*64
  with self.assertRaisesRegex(RuntimeError,'FINAL_CHECKPOINT_PROOF'):self.run_files(p,materials,now)
 def test_large_checkpoint_wrong_data_membership_still_rejected(self):
  now,p,materials=self.materials();p['final_data_file_hashes'].pop(next(iter(p['final_data_file_hashes'])))
  with self.assertRaisesRegex(RuntimeError,'FINAL_CHECKPOINT_SEMANTICS'):self.run_files(p,materials,now)


if __name__=='__main__':unittest.main()
