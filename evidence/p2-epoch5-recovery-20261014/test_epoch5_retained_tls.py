import os,sys,pathlib,tempfile,json,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'))
import p2_tls_lifecycle as tls
import epoch5_retained_tls as retained
from ledger_cutover_transaction import _atomic_receipt
class RetainedTlsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.base=self.tmp.name;self.root=self.base+'/tls';os.mkdir(self.root,0o700)
  self.directory=self.base+'/legacy-isolation-'+tls.TX;os.mkdir(self.directory,0o700)
  for obj,key,val in ((tls,'ROOT',self.root),(tls,'BASE',self.base)):
   p=patch.object(obj,key,val);p.start();self.addCleanup(p.stop)
  tls.client_config(create=True)
  os.makedirs(self.root+'/config/renewal',mode=0o700)
  pathlib.Path(self.root+'/config/renewal/'+tls.DOMAIN+'.conf').write_bytes(b'fixture')
  self.config={'schema':1,'domain':tls.DOMAIN,'root':self.root,'transaction_directory':self.directory,'transaction_id':tls.TX,'instance':'12345678-1234-4234-8234-123456789abc','generation':1,'ledger_uuid':'12345678-1234-4234-8234-123456789abc','release_sha256':retained.OLD_RELEASE,'accept_acme_terms':True}
  self.manager=retained.RetainedCertificateLifecycle(self.directory);self.manager.authority=lambda:None
  self.old={'schema':1,'config':self.config,'state':'HOLD','certificate_sha256':retained.CERT_SHA,'fingerprint':tls.fingerprint(self.root)}
  _atomic_receipt(self.manager.journal,self.old)
  self.old_raw=pathlib.Path(self.manager.journal).read_bytes()
  p=patch.object(retained,'OLD_JOURNAL_SHA',retained.sha(self.old_raw));p.start();self.addCleanup(p.stop)
  self.new=dict(self.config,release_sha256='b'*64);self.refpath=self.directory+'/new-config.json'
  self.write_config(self.new)
 def write_config(self,value):
  _atomic_receipt(self.refpath,value);self.ref={'path':self.refpath,'sha256':retained.sha(pathlib.Path(self.refpath).read_bytes())}
 def invoke(self,error=None,certs=None):
  calls=[];self.calls=calls
  def command(args,**kwargs):
   calls.append((args,kwargs))
   if error:raise error
   return b''
  with patch.object(tls,'certificate_check',side_effect=certs or [retained.CERT_SHA,retained.CERT_SHA]),patch.object(tls,'available_port'),patch.object(tls,'command',side_effect=command):
   result=self.manager.apply(self.ref)
  return result,calls
 def test_success_reuses_certificate_and_never_reissues(self):
  result,calls=self.invoke();self.assertEqual(result['state'],'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED')
  self.assertFalse(result['issuance_replayed']);self.assertEqual(len(calls),1)
  args,kw=calls[0];self.assertIn('--dry-run',args);self.assertIn('--no-random-sleep-on-renew',args)
  self.assertNotIn('certonly',args);self.assertNotIn('--force-renewal',args);self.assertEqual(kw,{'timeout':240})
  self.assertEqual(pathlib.Path(self.directory+'/epoch5-prior-tls-lifecycle.json').read_bytes(),self.old_raw)
 def test_prepare_has_no_journal_write(self):
  self.assertEqual(self.manager.prepare(self.ref),self.new)
  self.assertEqual(pathlib.Path(self.manager.journal).read_bytes(),self.old_raw)
  self.assertFalse(os.path.exists(self.directory+'/epoch5-prior-tls-lifecycle.json'))
 def test_failure_holds_and_preserves_prior(self):
  with self.assertRaisesRegex(ValueError,'timeout'):self.invoke(ValueError('timeout'))
  self.assertEqual(json.loads(pathlib.Path(self.manager.journal).read_text())['state'],'HOLD')
  self.assertEqual(pathlib.Path(self.directory+'/epoch5-prior-tls-lifecycle.json').read_bytes(),self.old_raw)
  with self.assertRaises(ValueError):self.manager.prepare(self.ref)
 def test_keyboard_interrupt_is_hold(self):
  with self.assertRaises(KeyboardInterrupt):self.invoke(KeyboardInterrupt())
  self.assertEqual(json.loads(pathlib.Path(self.manager.journal).read_text())['state'],'HOLD')
 def test_changed_certificate_does_not_request_renewal(self):
  with self.assertRaisesRegex(ValueError,'CERTIFICATE_CHANGED'):self.invoke(certs=['c'*64])
  self.assertEqual(self.calls,[])
 def test_dryrun_must_preserve_original_certificate(self):
  with self.assertRaisesRegex(ValueError,'REPLACED_CERTIFICATE'):self.invoke(certs=[retained.CERT_SHA,'c'*64])
  self.assertEqual(json.loads(pathlib.Path(self.manager.journal).read_text())['state'],'HOLD')
 def test_unknown_tree_change_refused(self):
  pathlib.Path(self.root+'/unexpected').write_bytes(b'change')
  with self.assertRaisesRegex(ValueError,'TREE_CHANGED'):self.manager.prepare(self.ref)
  self.assertEqual(pathlib.Path(self.manager.journal).read_bytes(),self.old_raw)
 def test_config_identity_change_refused(self):
  self.write_config(dict(self.new,generation=2))
  with self.assertRaisesRegex(ValueError,'IDENTITY_CHANGED'):self.manager.prepare(self.ref)
 def test_existing_backup_refused_without_overwrite(self):
  p=pathlib.Path(self.directory+'/epoch5-prior-tls-lifecycle.json');p.write_bytes(b'prior attempt')
  with self.assertRaisesRegex(ValueError,'ALREADY_ATTEMPTED'):self.manager.prepare(self.ref)
  self.assertEqual(p.read_bytes(),b'prior attempt')
if __name__=='__main__':unittest.main(verbosity=2)
