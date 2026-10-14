import os,sys,pathlib,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import inspect_epoch3 as r
class InspectionTests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.p=pathlib.Path(self.t.name)/'x'
 def tearDown(self):self.t.cleanup()
 def test_absence(self):self.assertEqual(r.metadata(str(self.p)),{'state':'ABSENT'})
 def test_file_metadata_no_content(self):
  self.p.write_bytes(b'private value');v=r.metadata(str(self.p));self.assertEqual(v['sha256'],r.sha(b'private value'));self.assertNotIn('private value',str(v))
 def test_mask_metadata_only(self):
  self.p.symlink_to('/dev/null');self.assertEqual(r.metadata(str(self.p)),{'state':'SYMLINK','target':'/dev/null'})
 def test_file_alias_rejected(self):
  self.p.symlink_to('/etc/passwd')
  with self.assertRaises(ValueError):r.file_data(str(self.p))
 def test_fifo_rejected(self):
  os.mkfifo(str(self.p))
  with self.assertRaises(ValueError):r.file_data(str(self.p))
 def test_file_bound(self):
  self.p.write_bytes(b'x'*2097153)
  with self.assertRaisesRegex(ValueError,'BOUND'):r.file_data(str(self.p))
if __name__=='__main__':unittest.main(verbosity=2)
