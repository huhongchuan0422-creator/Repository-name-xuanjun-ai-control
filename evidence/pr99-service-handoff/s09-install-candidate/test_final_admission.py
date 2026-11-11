import copy
import unittest
import production_start as m


class AdmissionTests(unittest.TestCase):
 def setUp(self):
  self.p={'writer_inventory_sha256':'a'*64,'writer_epoch':3,'final_data_file_hashes':{'opt/trading-system/runtime/fixture':'b'*64},
          'file_hashes':{'opt/trading-system/runtime/fixture':'b'*64},'database_schema_sha256':'c'*64}
  self.f={'action':'PR99_SOURCE_WRITER_FENCE_V1','source_host':'iZ6wee8q9z4t03hvqumwfhZ',
          'writer_inventory_sha256':'a'*64,'writer_epoch':3,'writers_stopped':True,'inflight_drained':True,
          'unresolved_shared_writers':[],'observed_at':100}
  self.c={'class':'FINAL_CANONICAL_CHECKPOINT','files':self.p['final_data_file_hashes'],
          'captured_at':110,'database_integrity':'PASS','database_schema_sha256':'c'*64}
  self.a={'action':'PR99_CANONICAL_WRITER_ASSIGNMENT_V1','target_host':m.HOST,'release':str(m.RELEASE),
          'writer_inventory_sha256':'a'*64,'writer_epoch':3,'target_identity':'xuanjun-s07',
          'source_writer_resumed':False,'scope':list(m.UNITS)}
 def inputs(self):
  f=m.canonical(self.f);self.c['source_fence_sha256']=m.sha(f);c=m.canonical(self.c)
  self.a['checkpoint_sha256']=m.sha(c);a=m.canonical(self.a)
  self.p.update(source_writer_fence_receipt_sha256=m.sha(f),final_checkpoint_receipt_sha256=m.sha(c),canonical_writer_assignment_sha256=m.sha(a))
  return f,c,a
 def check(self):return m.validate_final_receipts(self.p,*self.inputs(),now=120)
 def test_exact_chain_validates_structure_only(self):self.assertTrue(self.check())
 def test_preliminary_checkpoint_rejected(self):
  self.c['class']='PRELIMINARY'
  with self.assertRaisesRegex(RuntimeError,'CHECKPOINT_SEMANTICS'):self.check()
 def test_source_not_fenced_rejected(self):
  for key,value in [('writers_stopped',False),('inflight_drained',False),('unresolved_shared_writers',['unresolved'])]:
   old=self.f[key];self.f[key]=value
   with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'NOT_FENCED'):self.check()
   self.f[key]=old
 def test_boolean_epoch_rejected(self):
  self.p['writer_epoch']=True
  with self.assertRaisesRegex(RuntimeError,'WRITER_BINDING_REQUIRED'):self.check()
 def test_snapshot_before_fence_or_future_rejected(self):
  for captured in (99,121):
   self.c['captured_at']=captured
   with self.subTest(captured=captured),self.assertRaisesRegex(RuntimeError,'RECEIPT_TIME'):self.check()
 def test_data_not_in_final_exact_files_rejected(self):
  self.p['file_hashes']={}
  with self.assertRaisesRegex(RuntimeError,'FINAL_DATA_BINDING'):self.check()
 def test_bad_database_integrity_rejected(self):
  self.c['database_integrity']='UNKNOWN'
  with self.assertRaisesRegex(RuntimeError,'CHECKPOINT_SEMANTICS'):self.check()
 def test_foreign_target_rejected(self):
  self.a['target_host']='other'
  with self.assertRaisesRegex(RuntimeError,'ASSIGNMENT_SEMANTICS'):self.check()
 def test_source_resume_rejected(self):
  self.a['source_writer_resumed']=True
  with self.assertRaisesRegex(RuntimeError,'ASSIGNMENT_SEMANTICS'):self.check()
 def test_private_permit_hash_mismatch_rejected(self):
  raw=self.inputs();self.p['final_checkpoint_receipt_sha256']='d'*64
  with self.assertRaisesRegex(RuntimeError,'FINAL_CHECKPOINT_PROOF'):m.validate_final_receipts(self.p,*raw,now=120)

class LoaderTests(unittest.TestCase):
 def test_actual_admit_loads_and_validates_full_receipt_chain(self):
  import tempfile
  from pathlib import Path
  from types import SimpleNamespace
  from unittest.mock import patch
  from contextlib import ExitStack
  with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
   release=Path(directory)/'domestic-final-v1';root=release/'rootfs';root.mkdir(parents=True)
   for i in range(100):
    path=root/('fixture-'+str(i));path.write_bytes(('fixture-'+str(i)).encode())
   permit=Path(directory)/'admission.json'
   for name,value in [('RELEASE',release),('ROOT',root),('PERMIT',permit),('read',lambda p,*a,**k:Path(p).read_bytes())]:
    stack.enter_context(patch.object(m,name,value))
   stack.enter_context(patch.object(m.os,'geteuid',lambda:0))
   stack.enter_context(patch.object(m.os,'uname',lambda:SimpleNamespace(nodename=m.HOST)))
   stack.enter_context(patch.object(m.time,'time',lambda:150))
   stack.enter_context(patch.object(m.pwd,'getpwnam',lambda n:SimpleNamespace(pw_uid=1001,pw_gid=1001)))
   stack.enter_context(patch.object(m.grp,'getgrnam',lambda n:SimpleNamespace(gr_gid=1001)))
   fixture=AdmissionTests();fixture.setUp()
   fixture.p['file_hashes']={p.name:m.sha(p.read_bytes()) for p in root.iterdir()}
   fixture.p['final_data_file_hashes']={'fixture-0':fixture.p['file_hashes']['fixture-0']}
   fixture.c['files']=fixture.p['final_data_file_hashes']
   p=fixture.p;p.update(action='PR99_FINAL_DOMESTIC_START_V1',host=m.HOST,source_sha256=m.sha(Path(m.__file__).read_bytes()),
     issued_at=100,expires_at=200,independent_review_comment_id=123,release=str(release),checkpoint_class='FINAL_CANONICAL_CHECKPOINT',
     uid=1001,gid=1001,links={},unit_hashes={n:m.sha(b) for n,b in m.units('xuanjun-s07').items()})
   def write_inputs():
    raw=fixture.inputs()
    for name,data in zip(('source-writer-fence.receipt.json','final-checkpoint.receipt.json','canonical-writer-assignment.json'),raw):
     (release/name).write_bytes(data)
    permit.write_bytes(m.canonical(p));permit.chmod(0o600)
   write_inputs();loaded,payload=m.admit();self.assertEqual(loaded,p);self.assertEqual(len(payload),3)
   fixture.c['class']='PRELIMINARY';write_inputs()
   with self.assertRaisesRegex(RuntimeError,'CHECKPOINT_SEMANTICS'):m.admit()

if __name__=='__main__':unittest.main()
