import os,pathlib,tempfile,unittest,fcntl
from unittest import mock
import epoch3_install_lock as s
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=self.tmp.name+'/lock'
  pathlib.Path(self.path).write_bytes(b'');os.chmod(self.path,0o600)
  self.patch=mock.patch.object(s,'PATH',self.path);self.patch.start()
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def test_reuses_and_releases(self):
  ino=os.stat(self.path).st_ino
  with s.held():self.assertEqual(os.stat(self.path).st_ino,ino)
  with s.held():pass
 def test_busy_rejected(self):
  fd=os.open(self.path,os.O_RDONLY);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:
   with self.assertRaises(OSError):
    with s.held():self.fail('entered')
  finally:os.close(fd)
 def test_missing_not_created(self):
  os.unlink(self.path)
  with self.assertRaises(OSError):
   with s.held():self.fail('entered')
  self.assertFalse(os.path.exists(self.path))
 def test_loose_mode_rejected(self):
  os.chmod(self.path,0o644)
  with self.assertRaises(ValueError):
   with s.held():self.fail('entered')
if __name__=='__main__':unittest.main()
