import unittest,tempfile,hashlib,io,contextlib,sys,os
from pathlib import Path
from unittest.mock import patch
import korea_project_controller as c

class ReceiverTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.home=Path(self.tmp.name)
 def run_receiver(self,action,body=b'payload',digest=None):
  digest=digest or hashlib.sha256(body).hexdigest()
  source=c.REMOTE.replace("os.uname().nodename.split('.')[0]!='iZmj7a5kwr75qc1tul4kf9Z'",'False',1)
  with patch.object(sys,'argv',['receiver',action,digest,str(len(body))]),patch.object(sys,'stdin',type('Input',(),{'buffer':io.BytesIO(body)})()),patch.object(Path,'home',return_value=self.home),contextlib.redirect_stdout(io.StringIO()) as out:
   exec(compile(source,'receiver','exec'),{})
  return out.getvalue()
 def test_receive_and_independent_readback(self):
  self.assertIn('PASS_ARCHIVE_PRECOPY',self.run_receiver('receive'))
  self.assertIn('PASS_ARCHIVE_PRECOPY',self.run_receiver('verify'))
 def test_existing_archive_does_not_overwrite(self):
  self.run_receiver('receive')
  with self.assertRaisesRegex(SystemExit,'EXISTING_FINAL'):self.run_receiver('receive')
 def test_tampered_disk_is_rejected(self):
  self.run_receiver('receive')
  p=next((self.home/'pr99-tokyo-project-precopy').glob('*.tar.gz'));p.write_bytes(b'corrupt')
  with self.assertRaisesRegex(SystemExit,'DISK_SHA'):self.run_receiver('verify')
 def test_partial_conflict_is_preserved(self):
  base=self.home/'pr99-tokyo-project-precopy';base.mkdir(mode=0o700)
  p=base/(hashlib.sha256(b'payload').hexdigest()+'.partial');p.write_bytes(b'old')
  with self.assertRaises(FileExistsError):self.run_receiver('receive')
  self.assertEqual(p.read_bytes(),b'old')
 def test_bad_hash_cannot_escape_destination(self):
  with self.assertRaisesRegex(SystemExit,'PACKAGE_REQUEST'):self.run_receiver('receive',digest='../escape')
  self.assertEqual(list(self.home.iterdir()),[])
 def test_wrong_hostname_rejected_before_file_creation(self):
  with patch.object(sys,'argv',['receiver','receive']),contextlib.redirect_stdout(io.StringIO()):
   with self.assertRaisesRegex(SystemExit,'TARGET_HOST'):exec(compile(c.REMOTE,'receiver','exec'),{})

if __name__=='__main__':unittest.main()
