import json,os,pathlib,tempfile,unittest
from unittest import mock
import epoch5_attempt_journal as subject
class AttemptTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=self.temp.name
  self.patch=mock.patch.object(subject,'DIRECTORY',self.root);self.patch.start()
  self.journal=subject.AttemptJournal(self.root)
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def test_create_and_atomic_save(self):
  self.journal.create({'stage':'ADMITTED'});self.journal.save({'stage':'HOLD'})
  self.assertEqual(json.loads(self.journal.read().decode()),{'stage':'HOLD'})
 def test_second_creation_rejected(self):
  self.journal.create({})
  with self.assertRaises(FileExistsError):subject.AttemptJournal(self.root).create({})
 def test_unclaimed_existing_save_rejected(self):
  self.journal.create({})
  with self.assertRaisesRegex(ValueError,'UNCLAIMED'):subject.AttemptJournal(self.root).save({})
 def test_external_change_rejected(self):
  self.journal.create({});pathlib.Path(self.journal.path).write_bytes(b'{"changed":true}')
  with self.assertRaisesRegex(ValueError,'STALE'):self.journal.save({})
 def test_symlink_cannot_create(self):
  os.symlink('/dev/null',self.journal.path)
  with self.assertRaises(FileExistsError):self.journal.create({})
 def test_wrong_directory_rejected(self):
  with self.assertRaises(ValueError):subject.AttemptJournal('/tmp/other')
 def test_loose_parent_rejected(self):
  os.chmod(self.root,0o755)
  with self.assertRaises(ValueError):self.journal.create({})
 def test_nan_rejected_before_file(self):
  with self.assertRaises(ValueError):self.journal.create({'n':float('nan')})
  self.assertFalse(os.path.lexists(self.journal.path))
 def test_create_write_failure_keeps_attempt_consumed(self):
  def failed(fd,data):os.close(fd);raise OSError('disk')
  with mock.patch.object(self.journal,'write',side_effect=failed):
   with self.assertRaises(OSError):self.journal.create({})
  self.assertTrue(os.path.lexists(self.journal.path))
  with self.assertRaises(FileExistsError):self.journal.create({})
 def test_save_write_failure_keeps_old_state(self):
  self.journal.create({'stage':'ADMITTED'});before=self.journal.read()
  def failed(fd,data):os.close(fd);raise OSError('disk')
  with mock.patch.object(self.journal,'write',side_effect=failed):
   with self.assertRaises(OSError):self.journal.save({'stage':'COMPLETE'})
  self.assertEqual(self.journal.read(),before)
if __name__=='__main__':unittest.main()
