import importlib.util,os,tempfile,unittest
spec=importlib.util.spec_from_file_location('path_guard',os.path.join(os.path.dirname(__file__),'..','bootstrap','path_guard.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class PathGuardTests(unittest.TestCase):
 def setUp(self):
  # Workspace parent is private and trusted, unlike shared /tmp.
  self.tmp=tempfile.TemporaryDirectory(dir=os.getcwd());self.d=self.tmp.name
  self.p=os.path.join(self.d,'ledger')
  fd=os.open(self.p,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
 def tearDown(self):self.tmp.cleanup()
 def test_valid_and_swap_detected(self):
  with g.Guard(self.p,os.getuid()) as guard:
   fd=guard.open_file()
   try:
    self.assertTrue(guard.matches(fd));os.rename(self.p,self.p+'.old')
    f=os.open(self.p,os.O_CREAT|os.O_WRONLY,0o600);os.close(f)
    self.assertFalse(guard.matches(fd))
   finally:os.close(fd)
 def test_final_symlink_rejected(self):
  os.unlink(self.p);os.symlink('/etc/passwd',self.p)
  with g.Guard(self.p,os.getuid()) as guard:
   with self.assertRaises(OSError):guard.open_file()
 def test_directory_symlink_rejected(self):
  link=os.path.join(self.d,'link');os.symlink(self.d,link)
  with self.assertRaises(OSError):g.Guard(os.path.join(link,'ledger'),os.getuid())
 def test_group_writable_ancestor_rejected(self):
  os.chmod(self.d,0o770)
  try:
   with self.assertRaises(g.PathHold):g.Guard(self.p,os.getuid())
  finally:os.chmod(self.d,0o700)
 def test_hardlink_rejected(self):
  os.link(self.p,self.p+'.link')
  with g.Guard(self.p,os.getuid()) as guard:
   with self.assertRaises(g.PathHold):guard.open_file()
 def test_relative_and_dotdot_rejected(self):
  for path in ('relative',self.d+'/../ledger'):
   with self.assertRaises(g.PathHold):g.Guard(path,os.getuid())
if __name__=='__main__':unittest.main()

class GuardIntegrationTests(unittest.TestCase):
 def setUp(self):
  import sqlite3
  self.tmp=tempfile.TemporaryDirectory(dir=os.getcwd());self.d=self.tmp.name;self.p=os.path.join(self.d,'ledger');self.audit=os.path.join(self.d,'audit')
  db=sqlite3.connect(self.p);db.execute('pragma journal_mode=wal');db.execute('create table operations (nonce text primary key,task text,attempt text,state text)');db.close();os.chmod(self.p,0o600)
  fd=os.open(self.audit,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
 def tearDown(self):self.tmp.cleanup()
 def test_db_replacement_refused(self):
  with g.GuardedLedger(self.p,os.getuid()) as ledger:
   os.rename(self.p,self.p+'.old');fd=os.open(self.p,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
   with self.assertRaises(g.PathHold):ledger.check()
 def test_audit_replacement_refused(self):
  with g.GuardedAudit(self.audit,os.getuid()) as audit:
   os.rename(self.audit,self.audit+'.old');fd=os.open(self.audit,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
   with self.assertRaises(g.PathHold):audit.write(b'not-written')
   self.assertEqual(os.stat(self.audit).st_size,0)
 def test_sidecar_link_rejected(self):
  for suffix in ('-wal','-shm','-journal'):
   os.symlink(self.audit,self.p+suffix)
   try:
    with self.assertRaises(g.PathHold):g.GuardedLedger(self.p,os.getuid())
   finally:os.unlink(self.p+suffix)
 def test_sidecar_hardlink_rejected(self):
  os.link(self.audit,self.p+'-wal')
  try:
   with self.assertRaises(g.PathHold):g.GuardedLedger(self.p,os.getuid())
  finally:os.unlink(self.p+'-wal')
 def test_renamed_ancestor_fd_stays_original(self):
  with g.GuardedAudit(self.audit,os.getuid()) as audit:
   old=self.d+'-old';os.rename(self.d,old);os.mkdir(self.d,0o700)
   fd=os.open(self.audit,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
   try:
    audit.write(b'original\n')
    self.assertEqual(os.stat(self.audit).st_size,0)
    with open(os.path.join(old,'audit'),'rb') as f:self.assertEqual(f.read(),b'original\n')
   finally:
    os.unlink(self.audit);os.rmdir(self.d);os.rename(old,self.d)
