import hashlib,os,pathlib,tempfile,unittest
from unittest import mock
import epoch3_preserve as subject
class PreserveTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();r=self.temp.name
  self.t=r+'/transaction';self.c=r+'/candidate';self.tls=r+'/tls'
  for p in (self.t,self.c,self.tls):os.mkdir(p,0o700)
  for n in ('config','logs','work'):os.mkdir(self.tls+'/'+n,0o700)
  self.pins={};self.data={}
  for p in (self.c+'/install-receipt.json',)+tuple(self.t+'/'+n+'.json' for n in ('runtime-provisioning','recovery-execution','bootstrap-files','publisher-bootstrap','tls-lifecycle')):
   raw=b'{"fixture":true}\n';pathlib.Path(p).write_bytes(raw);os.chmod(p,0o600);self.pins[p]=hashlib.sha256(raw).hexdigest();self.data[p]=raw
  self.archive=self.t+'/epoch3-prior-receipts'
  self.patch=mock.patch.multiple(subject,T=self.t,C=self.c,TLS=self.tls,PINS=self.pins,ARCHIVE=self.archive);self.patch.start()
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def test_preserves_all_prior_bytes(self):
  result=subject.preserve_prior_receipts();self.assertFalse(result['historical_receipts_deleted'])
  for p,data in self.data.items():self.assertEqual(pathlib.Path(self.archive,os.path.basename(p)).read_bytes(),data)
  self.assertFalse(os.path.lexists(self.tls));self.assertTrue(os.path.isdir(self.archive+'/tls-root'))
  self.assertFalse(os.path.lexists(self.t+'/tls-lifecycle.json'))
  self.assertTrue(os.path.isfile(self.archive+'/tls-original.json'))
 def test_repeat_rejected(self):
  subject.preserve_prior_receipts()
  with self.assertRaises((ValueError,FileNotFoundError)):subject.preserve_prior_receipts()
 def test_nonempty_tls_rejected_without_mutation(self):
  pathlib.Path(self.tls,'config','unexpected').write_bytes(b'x')
  with self.assertRaises(ValueError):subject.preserve_prior_receipts()
  self.assertFalse(os.path.lexists(self.archive))
 def test_receipt_change_rejected_without_mutation(self):
  pathlib.Path(self.t,'recovery-execution.json').write_bytes(b'changed')
  with self.assertRaises(ValueError):subject.preserve_prior_receipts()
  self.assertFalse(os.path.lexists(self.archive))
 def test_existing_archive_not_overwritten(self):
  os.mkdir(self.archive,0o700)
  with self.assertRaises(ValueError):subject.preserve_prior_receipts()
  self.assertEqual(os.listdir(self.archive),[])
 def test_receipt_copy_failure_keeps_originals(self):
  with mock.patch.object(subject,'exclusive_file',side_effect=OSError('disk')):
   with self.assertRaises(OSError):subject.preserve_prior_receipts()
  for p,data in self.data.items():self.assertEqual(pathlib.Path(p).read_bytes(),data)
  self.assertTrue(os.path.isdir(self.archive))
 def test_second_move_failure_keeps_tls_evidence(self):
  original=os.rename;calls=[0]
  def fail_second(a,b):
   calls[0]+=1
   if calls[0]==2:raise OSError('simulated move failure')
   return original(a,b)
  with mock.patch.object(subject.os,'rename',side_effect=fail_second):
   with self.assertRaises(OSError):subject.preserve_prior_receipts()
  self.assertTrue(os.path.isdir(self.archive+'/tls-root'))
  self.assertTrue(os.path.isfile(self.t+'/tls-lifecycle.json'))
  self.assertTrue(os.path.isfile(self.archive+'/tls-lifecycle.json'))
 def test_symlink_tls_rejected(self):
  os.rmdir(self.tls+'/config');os.symlink(self.tls+'/logs',self.tls+'/config')
  with self.assertRaises(ValueError):subject.preserve_prior_receipts()
if __name__=='__main__':unittest.main()
