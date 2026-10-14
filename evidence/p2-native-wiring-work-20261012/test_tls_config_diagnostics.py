import os,sys,json,stat,tempfile,pathlib,subprocess,unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'))
import p2_tls_lifecycle as tls

class ConfigTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=self.temp.name;os.chmod(self.root,0o700)
  self.patch=patch.object(tls,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop);self.addCleanup(self.temp.cleanup)
 def test_empty_regular_private_config(self):
  p=tls.client_config(create=True);self.assertEqual(pathlib.Path(p).read_bytes(),b'');self.assertEqual(stat.S_IMODE(os.stat(p).st_mode),0o600)
  args=tls.base_args();self.assertEqual(args[args.index('-c')+1],p);self.assertNotIn('/dev/null',args)
 def test_existing_config_not_overwritten(self):
  tls.client_config(create=True)
  with self.assertRaises(FileExistsError):tls.client_config(create=True)
 def test_missing_config_rejected(self):
  with self.assertRaises(FileNotFoundError):tls.base_args()
 def test_symlink_config_rejected(self):
  os.symlink('/dev/null',self.root+'/client.ini')
  with self.assertRaises(ValueError):tls.client_config()
 def test_nonempty_config_rejected(self):
  p=tls.client_config(create=True);pathlib.Path(p).write_bytes(b'server=other')
  with self.assertRaisesRegex(ValueError,'NOT_EMPTY'):tls.client_config()
 def test_loose_permissions_rejected(self):
  p=tls.client_config(create=True);os.chmod(p,0o644)
  with self.assertRaises(ValueError):tls.client_config()
 def test_hardlink_config_rejected(self):
  p=tls.client_config(create=True);os.link(p,self.root+'/copy')
  with self.assertRaises(ValueError):tls.client_config()
 def test_root_authority_rejected(self):
  os.chmod(self.root,0o755)
  with self.assertRaisesRegex(ValueError,'ROOT'):tls.client_config(create=True)
 def test_failure_diagnostic_retained_private(self):
  os.mkdir(self.root+'/logs',0o700);fake=Mock(returncode=2);fake.communicate.return_value=(b'',b'File not found: /dev/null')
  with patch.object(tls.subprocess,'Popen',return_value=fake):
   with self.assertRaisesRegex(ValueError,'RC_2'):tls.command(['certbot'])
  p=self.root+'/logs/command-failure.json';v=json.loads(pathlib.Path(p).read_text())
  self.assertEqual(v['stderr'],'File not found: /dev/null');self.assertEqual(v['returncode'],2);self.assertEqual(stat.S_IMODE(os.stat(p).st_mode),0o600)
 def test_fingerprint_scan_denied_is_not_empty(self):
  with patch.object(tls.os,'scandir',side_effect=PermissionError('scan denied')):
   with self.assertRaises(PermissionError):tls.fingerprint(self.root)
 def test_fingerprint_scan_disappearance_is_not_empty(self):
  with patch.object(tls.os,'scandir',side_effect=FileNotFoundError('scan raced')):
   with self.assertRaises(FileNotFoundError):tls.fingerprint(self.root)
 def test_success_does_not_create_failure_receipt(self):
  fake=Mock(returncode=0);fake.communicate.return_value=(b'ok',b'')
  with patch.object(tls.subprocess,'Popen',return_value=fake):self.assertEqual(tls.command(['certbot']),b'ok')
  self.assertFalse(os.path.exists(self.root+'/logs/command-failure.json'))
 def test_diagnostics_are_bounded(self):
  os.mkdir(self.root+'/logs',0o700);fake=Mock(returncode=2);fake.communicate.return_value=(b'x'*1048577,b'y'*1048577)
  with patch.object(tls.subprocess,'Popen',return_value=fake):
   with self.assertRaises(ValueError):tls.command(['certbot'])
  v=json.loads(pathlib.Path(self.root+'/logs/command-failure.json').read_text());self.assertTrue(v['truncated']);self.assertEqual(len(v['stderr']),1048576)

if __name__=='__main__':unittest.main(verbosity=2)
