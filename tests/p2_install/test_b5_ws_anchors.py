import hashlib,importlib.util,json,os,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ws=load('ws',ROOT/'scripts/p2_b5_ws_anchors.py')
class Anchors(unittest.TestCase):
 def setUp(self):
  self.raw={n:b'export const content = "data only";' for n in ws.TARGETS}
  self.raw[ws.TARGETS[0]]=b'x'*122958
  self.old=ws.RUN_SHA;ws.RUN_SHA=hashlib.sha256(self.raw[ws.TARGETS[0]]).hexdigest()
  self.rows={'root/'+n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in self.raw.items()}
 def tearDown(self):ws.RUN_SHA=self.old
 def call(self):return ws.analyze(self.rows,lambda n:self.raw[n[5:]],'root/',[],None)
 def test_exact_three_no_recursion(self):
  self.rows['root/not-selected.mjs']={'bytes':1,'sha256':'0'*64}
  report,selected=self.call();self.assertEqual(set(selected),set(ws.TARGETS));self.assertEqual(report['dispatcher_binding'],'UNBOUND')
 def test_absent_preserves_fail_closed(self):
  del self.rows['root/'+ws.TARGETS[1]]
  with self.assertRaisesRegex(ValueError,'EXACT_ANCHOR_ABSENT'):self.call()
 def test_run_fixed_hash(self):
  ws.RUN_SHA='0'*64
  with self.assertRaisesRegex(ValueError,'RUN_FIXED_PIN'):self.call()
 def test_other_hash_not_self_asserted(self):
  self.raw[ws.TARGETS[1]]=b'tamper'
  with self.assertRaisesRegex(ValueError,'ANCHOR_CONTENT_SHA'):self.call()
 def test_member_bound_before_read(self):
  self.rows['root/'+ws.TARGETS[2]]['bytes']=2097153
  with self.assertRaisesRegex(ValueError,'ANCHOR_SIZE_BOUND'):self.call()
 def test_frozen_base_and_bootstrap(self):
  b=ws.load_base();self.assertIs(b.analyze,ws.analyze)
  boot=load('boot',ROOT/'scripts/p2_b5_ws_bootstrap.py');rows=boot.unpack()
  self.assertEqual(rows['scripts/p2_b5_ws_anchors.py'],(ROOT/'scripts/p2_b5_ws_anchors.py').read_bytes())
 def test_failure_receipt_and_existing_file_unchanged(self):
  b=ws.load_base()
  class Reader:
   PINS={};ROOT='root/';Hold=ValueError
   @staticmethod
   def select_files(*a):raise ValueError('ORIGINAL_HASH_MISMATCH')
  with tempfile.TemporaryDirectory() as d:
   fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
   try:
    Path(d,'materials.tar').write_bytes(b'previous partial output')
    self.assertEqual(b.run(-1,-1,fd,Reader,[],None),2)
    self.assertEqual(Path(d,'materials.tar').read_bytes(),b'previous partial output')
    receipt=json.loads(Path(d,'child-receipt.json').read_text())
    self.assertEqual(receipt['state'],'HOLD');self.assertEqual(receipt['error'],'ORIGINAL_HASH_MISMATCH')
    with self.assertRaises(FileExistsError):b.write_new(fd,'materials.tar',b'replace')
   finally:os.close(fd)
if __name__=='__main__':unittest.main()
