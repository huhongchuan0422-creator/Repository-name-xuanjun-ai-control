import os,pathlib,tempfile,unittest
from unittest import mock
import epoch3_native_binding as s
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=self.tmp.name
  self.archive=self.root+'/archive';os.mkdir(self.archive,0o700)
  self.path=self.root+'/binding.json';pathlib.Path(self.path).write_bytes(b'old');os.chmod(self.path,0o644)
  self.patches=[mock.patch.object(s,'NATIVE',self.path),mock.patch.object(s,'ARCHIVE',self.archive),
                mock.patch.object(s,'native_binding_delta',return_value=b'new')]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def execute(self):return s.update(b'old',b'new','a'*64)
 def test_preserve_and_replace(self):
  self.assertTrue(self.execute()['original_preserved'])
  self.assertEqual(pathlib.Path(self.path).read_bytes(),b'new')
  self.assertEqual(pathlib.Path(self.archive,'native-binding-original.json').read_bytes(),b'old')
  self.assertEqual(os.stat(self.path).st_mode&0o777,0o644)
 def test_drift_rejected(self):
  pathlib.Path(self.path).write_bytes(b'changed')
  with self.assertRaises(ValueError):self.execute()
 def test_repeat_rejected(self):
  self.execute()
  with self.assertRaises(ValueError):self.execute()
 def test_symlink_rejected(self):
  os.unlink(self.path);os.symlink(self.archive+'/other',self.path)
  with self.assertRaises((ValueError,OSError)):self.execute()
 def test_wrong_transform(self):
  with mock.patch.object(s,'native_binding_delta',return_value=b'different'):
   with self.assertRaises(ValueError):self.execute()
 def test_publish_failure_keeps_original(self):
  with mock.patch.object(s.os,'replace',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.execute()
  self.assertEqual(pathlib.Path(self.path).read_bytes(),b'old')
  self.assertEqual(pathlib.Path(self.archive,'native-binding-original.json').read_bytes(),b'old')
if __name__=='__main__':unittest.main()
