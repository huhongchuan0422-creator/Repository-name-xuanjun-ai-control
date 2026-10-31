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

class Recovery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.c=Center(Path(self.tmp.name)/'center',{'k':b'y'*32},'k');self.addCleanup(self.c.db.close)
  self.path=str(Path(self.tmp.name)/'snapshot.sqlite');self.uid=os.geteuid()
 def ensure(self,sha='a'*64,request='same-request'):
  from scripts.community_admin_recovery import ensure_backup
  return ensure_backup(self.c,self.path,self.uid,sha,request)
 def test_query_does_not_create_receipts(self):
  from scripts.community_admin_recovery import ensure_backup
  self.assertEqual(ensure_backup(self.c,self.path,self.uid,'a'*64,'same-request',True)['phase'],'NOT_STARTED')
  self.assertFalse(Path(self.path+'.recovery-intent.json').exists())
  self.ensure();before={p.name:p.read_bytes() for p in Path(self.tmp.name).glob('snapshot*')}
  self.assertEqual(ensure_backup(self.c,self.path,self.uid,'a'*64,'same-request',True)['phase'],'VERIFIED_BACKUP_CURRENT_UNCHANGED_NOT_COMMITTED')
  self.assertEqual(before,{p.name:p.read_bytes() for p in Path(self.tmp.name).glob('snapshot*')})
 def test_same_request_completed_backup_reused(self):
  sha=self.ensure();before=Path(self.path).read_bytes();inode=os.stat(self.path).st_ino
  self.assertEqual(self.ensure(),sha);self.assertEqual(Path(self.path).read_bytes(),before);self.assertEqual(os.stat(self.path).st_ino,inode)
 def test_after_backup_before_receipt_recovers(self):
  import scripts.community_admin_bootstrap as bootstrap
  original=bootstrap._record_identity
  def interrupted(path,value,uid):
   if path.endswith('.recovery-receipt.json'):raise RuntimeError('simulated power loss')
   return original(path,value,uid)
  with patch.object(bootstrap,'_record_identity',side_effect=interrupted):
   with self.assertRaises(RuntimeError):self.ensure()
  self.assertTrue(Path(self.path).exists());self.assertEqual(len(self.ensure()),64)
 def test_after_intent_before_backup_recovers(self):
  with patch('scripts.community_admin_bootstrap._backup',side_effect=RuntimeError('power loss')):
   with self.assertRaises(RuntimeError):self.ensure()
  self.assertFalse(Path(self.path).exists());self.assertEqual(len(self.ensure()),64)
 def test_new_request_and_identity_refused(self):
  self.ensure()
  for sha,req in [('a'*64,'other-request'),('b'*64,'same-request')]:
   with self.assertRaises(Denied):self.ensure(sha,req)
 def test_current_changed_refused_without_overwrite(self):
  self.ensure();before=Path(self.path).read_bytes()
  with self.c.tx():self.c.db.execute("INSERT INTO settings VALUES('new-state','retained')")
  with self.assertRaises(Denied):self.ensure()
  self.assertEqual(Path(self.path).read_bytes(),before)
 def test_replaced_or_legacy_backup_refused(self):
  _backup(self.c,self.path,self.uid)
  with self.assertRaisesRegex(Denied,'UNBOUND'):self.ensure()
 def test_changed_backup_refused(self):
  self.ensure();db=sqlite3.connect(self.path)
  db.execute("INSERT INTO settings VALUES('tampered','yes')");db.commit();db.close()
  with self.assertRaisesRegex(Denied,'BACKUP_OR_CURRENT_CHANGED'):self.ensure()
 def test_same_bytes_replaced_inode_refused(self):
  self.ensure();p=Path(self.path);data=p.read_bytes();q=Path(self.path+'.replacement');q.write_bytes(data);q.chmod(0o600);os.replace(str(q),self.path)
  with self.assertRaises(Denied):self.ensure()


class OriginalHostRecovery(unittest.TestCase):
 def test_precommit_interruption_query_recover_and_committed_query(self):
  from test_community_admin_preflight import Preflight
  from scripts.community_admin_bootstrap import run
  from scripts.community_admin_authority import CommunityAdminAuthority
  from contextlib import redirect_stdout
  import io
  x=Preflight();x.setUp();self.addCleanup(x.doCleanups)
  del x.fx.plan['community_admin_authority'];x.fx.plan['reviewers']={};x.fx.plan['operations']={};x.fx.plan.pop('provider_reader_config',None);x.fx.write('host.json',x.fx.plan)
  p=x.call()['plan']
  def attempt():
   with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',side_effect=['super@test.invalid','CONFIRM super@test.invalid project1 SUPERADMIN']),patch('getpass.getpass',return_value='synthetic-secure-password'),redirect_stdout(io.StringIO()):return run(p,'--bootstrap')
  with patch.object(CommunityAdminAuthority,'bootstrap',side_effect=RuntimeError('simulated after durable backup')):
   with self.assertRaises(RuntimeError):attempt()
  self.assertEqual(run(p,'--inspect')['recovery']['phase'],'VERIFIED_BACKUP_CURRENT_UNCHANGED_NOT_COMMITTED')
  before=Path(p['backup_path']).read_bytes()
  result=attempt();self.assertEqual(result['status'],'DATABASE_COMMITTED_READBACK')
  self.assertEqual(run(p,'--inspect')['recovery']['phase'],'EXISTING_DATABASE_COMMIT_READBACK')
  replay=attempt();self.assertEqual(replay['status'],'EXISTING_DATABASE_COMMIT_READBACK');self.assertEqual(result['uid'],replay['uid'])
  self.assertEqual(before,Path(p['backup_path']).read_bytes())

if __name__=='__main__':unittest.main()
