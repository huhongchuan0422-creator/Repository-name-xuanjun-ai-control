import json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'))
import p2_tls_lifecycle as tls
from ledger_cutover_transaction import _atomic_receipt

class LifecycleTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.base=self.t.name;self.root=self.base+'/acme';self.txdir=self.base+'/legacy-isolation-'+tls.TX;os.mkdir(self.txdir,0o700)
  self.patches=[patch.object(tls,'BASE',self.base),patch.object(tls,'ROOT',self.root)]
  for p in self.patches:p.start()
  self.manager=tls.TlsLifecycle(self.txdir);self.manager.authority=lambda:None
  self.config={'schema':1,'root':self.root,'domain':tls.DOMAIN,'transaction_directory':self.txdir,'transaction_id':tls.TX,'instance':'12345678-1234-4234-8234-123456789abc','ledger_uuid':'12345678-1234-4234-8234-123456789abc','generation':1,'release_sha256':'a'*64,'accept_acme_terms':True}
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.t.cleanup()
 def create(self,state='HOLD'):
  os.mkdir(self.root,0o700);pathlib.Path(self.root,'account').write_bytes(b'private-fixture');os.chmod(self.root+'/account',0o600)
  _atomic_receipt(self.manager.journal,{'schema':1,'config':self.config,'state':state,'fingerprint':tls.fingerprint(self.root)})
 def test_exact_scope_and_terms_required(self):
  self.assertEqual(tls.validate(self.config),self.config)
  for key,value in [('domain','other.example'),('root','/tmp/else'),('accept_acme_terms',False),('transaction_id','other')]:
   v=dict(self.config);v[key]=value
   with self.assertRaises(ValueError):tls.validate(v)
 def test_unknown_account_change_holds_without_rename(self):
  self.create();pathlib.Path(self.root,'account').write_bytes(b'drift')
  with self.assertRaisesRegex(ValueError,'UNKNOWN_FILE_CHANGE'):self.manager.rollback()
  self.assertTrue(os.path.isdir(self.root));self.assertFalse(os.path.lexists(self.txdir+'/retained-tls-acme'))
 def test_partial_issuance_evidence_retained_and_repeat_rollback_safe(self):
  self.create();self.manager.rollback();self.assertFalse(os.path.lexists(self.root));self.assertTrue(os.path.isfile(self.txdir+'/retained-tls-acme/account'))
  self.manager.rollback();self.assertEqual(json.loads(pathlib.Path(self.manager.journal).read_text())['state'],'RETAINED_OFFLINE')
 def test_retained_evidence_drift_detected(self):
  self.create();self.manager.rollback();pathlib.Path(self.txdir+'/retained-tls-acme/account').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'RETAINED_EVIDENCE_CHANGED'):self.manager.rollback()
 def test_internal_certificate_symlink_accepted_external_refused(self):
  os.mkdir(self.root,0o700);pathlib.Path(self.root,'cert').write_bytes(b'public');os.symlink('cert',self.root+'/live.pem');tls.fingerprint(self.root)
  os.symlink('/etc/passwd',self.root+'/escape')
  with self.assertRaisesRegex(ValueError,'SYMLINK_ESCAPE'):tls.fingerprint(self.root)
 def test_issuance_failure_is_journaled_before_rollback(self):
  self.manager.prepare=lambda ref:self.config
  with patch.object(tls,'command',side_effect=ValueError('simulated-acme-failure')):
   with self.assertRaises(ValueError):self.manager.apply({})
  value=json.loads(pathlib.Path(self.manager.journal).read_text());self.assertEqual(value['state'],'HOLD');self.assertIsNotNone(value['fingerprint'])
  self.manager.rollback();self.assertFalse(os.path.lexists(self.root))
 def test_unjournaled_root_cannot_be_removed(self):
  os.mkdir(self.root,0o700)
  with self.assertRaisesRegex(ValueError,'UNJOURNALED_ROOT'):self.manager.rollback()
 def test_missing_requested_root_is_zero_effect_rollback(self):
  _atomic_receipt(self.manager.journal,{'schema':1,'config':self.config,'state':'REQUESTED','fingerprint':None})
  self.manager.rollback();self.manager.rollback();self.assertFalse(os.path.lexists(self.root))

if __name__=='__main__':unittest.main(verbosity=2)
