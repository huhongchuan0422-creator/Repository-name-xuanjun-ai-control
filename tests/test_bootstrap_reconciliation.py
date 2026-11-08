import json,os,sqlite3,sys,tempfile,unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'))
import controller as c
import secure_bootstrap as b

class ReconcileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.getcwd());self.home=self.tmp.name;self.root=os.path.join(self.home,'root');os.mkdir(self.root,0o700)
  self.db=os.path.join(self.home,'ledger');db=sqlite3.connect(self.db);db.execute('pragma journal_mode=wal');db.execute('create table operations(nonce text primary key,task text,attempt text,state text,prestate_target text,prestate_hash text,staging_target text,manifest_hash text,intended_target text,receipt_hash text)');db.close();os.chmod(self.db,0o600)
  self.audit=os.path.join(self.home,'audit');fd=os.open(self.audit,os.O_CREAT|os.O_WRONLY|os.O_APPEND,0o600);self.log=fd
  self.mk_target('base',b'base');os.symlink('base',os.path.join(self.root,'current'))
 def tearDown(self):os.close(self.log);self.tmp.cleanup()
 def mk_target(self,name,data):
  path=os.path.join(self.root,name);os.mkdir(path,0o700)
  fd=os.open(os.path.join(path,'.bootstrap-manifest.json'),os.O_CREAT|os.O_WRONLY,0o600);os.write(fd,data);os.close(fd)
 def row(self,state='RUNNING',receipt_hash=None):
  with sqlite3.connect(self.db) as db:db.execute('insert into operations values(?,?,?,?,?,?,?,?,?,?)',('n','t','a',state,'base',b.sha(b'base'),'stage-n',b.sha(b'new'),'release-n',receipt_hash))
 def state(self):
  with sqlite3.connect(self.db) as db:return db.execute('select state from operations').fetchone()[0]
 def go(self):return c.reconcile_pending(self.db,os.getuid(),self.root,self.log)
 def switch(self,target):os.unlink(os.path.join(self.root,'current'));os.symlink(target,os.path.join(self.root,'current'))
 def receipt(self):
  raw=b.canonical({'nonce':'n','target':'release-n','manifest_sha256':b.sha(b'new'),'outcome':'SUCCEEDED'})
  fd=os.open(os.path.join(self.root,'receipt-n.json'),os.O_CREAT|os.O_WRONLY,0o600);os.write(fd,raw);os.close(fd);return b.sha(raw)
 def test_no_stage_is_failed_and_repeat_is_idempotent(self):
  for state in ('RESERVED','RUNNING','UNKNOWN'):
   with self.subTest(state=state):
    self.row(state);self.assertEqual(self.go(),0);self.assertEqual(self.state(),'FAILED');size=os.stat(self.audit).st_size;self.assertEqual(self.go(),0);self.assertEqual(os.stat(self.audit).st_size,size)
    with sqlite3.connect(self.db) as db:db.execute('delete from operations')
 def test_complete_stage_is_removed_and_failed(self):
  self.mk_target('stage-n',b'new');self.row();self.assertEqual(self.go(),0);self.assertEqual(self.state(),'FAILED');self.assertFalse(os.path.exists(os.path.join(self.root,'stage-n')))
 def test_unsigned_legacy_receipt_stays_unknown(self):
  self.mk_target('release-n',b'new');self.switch('release-n');rh=self.receipt();self.row(receipt_hash=rh);self.assertEqual(self.go(),1);self.assertEqual(self.state(),'UNKNOWN')
 def test_receipt_missing_and_tampered_remain_unknown(self):
  for mode in ('missing','tampered','wrong_binding'):
   with self.subTest(mode=mode):
    self.mk_target('release-n',b'new');self.switch('release-n');rh=b.sha(b'bad') if mode=='missing' else self.receipt();self.row(receipt_hash=rh)
    if mode=='tampered':
     with open(os.path.join(self.root,'receipt-n.json'),'wb') as f:f.write(b'tampered')
    if mode=='wrong_binding':
     raw=b.canonical({'nonce':'other','target':'release-n','manifest_sha256':b.sha(b'new'),'outcome':'SUCCEEDED'})
     with open(os.path.join(self.root,'receipt-n.json'),'wb') as f:f.write(raw)
     with sqlite3.connect(self.db) as db:db.execute('update operations set receipt_hash=?',(b.sha(raw),))
    self.assertEqual(self.go(),1);self.assertEqual(self.state(),'UNKNOWN');self.assertEqual(self.go(),1)
    with sqlite3.connect(self.db) as db:db.execute('delete from operations')
    self.switch('base');os.unlink(os.path.join(self.root,'release-n','.bootstrap-manifest.json'));os.rmdir(os.path.join(self.root,'release-n'))
    try:os.unlink(os.path.join(self.root,'receipt-n.json'))
    except FileNotFoundError:pass
 def test_evidence_conflicts_hold(self):
  for mode in ('wrong_stage','link_stage','wrong_pre','wrong_current','target_without_switch','missing_fields'):
   with self.subTest(mode=mode):
    self.row()
    if mode=='wrong_stage':self.mk_target('stage-n',b'wrong')
    if mode=='link_stage':os.symlink('base',os.path.join(self.root,'stage-n'))
    if mode=='wrong_pre':
     with sqlite3.connect(self.db) as db:db.execute("update operations set prestate_hash=?",('0'*64,))
    if mode=='wrong_current':self.switch('other')
    if mode=='target_without_switch':self.mk_target('release-n',b'new')
    if mode=='missing_fields':
     with sqlite3.connect(self.db) as db:db.execute('update operations set manifest_hash=NULL')
    self.assertEqual(self.go(),1);self.assertEqual(self.state(),'UNKNOWN')
    with sqlite3.connect(self.db) as db:db.execute('delete from operations')
    if mode=='wrong_stage':os.unlink(os.path.join(self.root,'stage-n','.bootstrap-manifest.json'));os.rmdir(os.path.join(self.root,'stage-n'))
    if mode=='link_stage':os.unlink(os.path.join(self.root,'stage-n'))
    if mode=='wrong_current':self.switch('base')
    if mode=='target_without_switch':os.unlink(os.path.join(self.root,'release-n','.bootstrap-manifest.json'));os.rmdir(os.path.join(self.root,'release-n'))
 def test_untrusted_stage_entry_cannot_be_deleted(self):
  self.mk_target('stage-n',b'new');os.symlink('/etc/passwd',os.path.join(self.root,'stage-n','evil'));self.row()
  self.assertEqual(self.go(),1);self.assertEqual(self.state(),'UNKNOWN');self.assertTrue(os.path.lexists(os.path.join(self.root,'stage-n','evil')))
 def test_log_failure_rolls_back_state(self):
  self.row();os.close(self.log);self.log=os.open(self.audit,os.O_RDONLY)
  with self.assertRaises(OSError):self.go()
  self.assertEqual(self.state(),'RUNNING')
if __name__=='__main__':unittest.main()
