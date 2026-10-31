import os, tempfile, unittest, sqlite3
from pathlib import Path
from unittest.mock import patch
from scripts.community_admin_bootstrap import _binding, _backup, _record_identity
from scripts.pr122_customer_core import Center, Denied
class Tests(unittest.TestCase):
 def test_unbound_before_any_writes(self):
  with self.assertRaisesRegex(Denied,'NOT_BOUND'):_binding()
 def test_consistent_backup_and_no_overwrite(self):
  with tempfile.TemporaryDirectory() as directory:
   c=Center(Path(directory)/'center',{'k':b'y'*32},'k')
   try:
    with c.tx():c.db.execute("INSERT INTO settings VALUES('synthetic','retained')")
    target=str(Path(directory)/'snapshot.sqlite');sha=_backup(c,target,os.geteuid());self.assertEqual(len(sha),64)
    db=sqlite3.connect(target)
    try:self.assertEqual(db.execute("SELECT v FROM settings WHERE k='synthetic'").fetchone()[0],'retained')
    finally:db.close()
    self.assertEqual(os.stat(target).st_mode&0o777,0o600)
    with self.assertRaises(Denied):_backup(c,target,os.geteuid())
   finally:c.db.close()
 def test_backup_refuses_symlink(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);(p/'target').touch();(p/'link').symlink_to(p/'target')
   with self.assertRaises(Denied):_backup(None,str(p/'link'),os.geteuid())
 def test_exact_tty_identity_record_idempotent(self):
  with tempfile.TemporaryDirectory() as directory:
   path=str(Path(directory)/'intent.json');value=dict(email='fixture@test.invalid',project='synthetic',role='COMMUNITY_SUPERADMIN',request_id='test')
   a=_record_identity(path,value,os.geteuid());self.assertEqual(_record_identity(path,value,os.geteuid()),a)
   self.assertEqual(os.stat(path).st_mode&0o777,0o600)
   with self.assertRaises(Denied):_record_identity(path,dict(value,email='different@test.invalid'),os.geteuid())
 def test_identity_record_never_follows_symlink(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);(p/'target').write_text('{}');(p/'link').symlink_to(p/'target')
   with self.assertRaises(Denied):_record_identity(str(p/'link'),{},os.geteuid())
if __name__=='__main__':unittest.main()
