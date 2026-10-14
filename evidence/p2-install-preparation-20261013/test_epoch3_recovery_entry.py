import hashlib,json,os,pathlib,shutil,tempfile,unittest
from unittest import mock
import epoch3_recovery_entry as s
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.kit=pathlib.Path(self.tmp.name)/'kit';self.kit.mkdir(mode=0o700)
  helpers=self.kit/'helpers';helpers.mkdir(mode=0o700)
  tests=self.kit/'tests';tests.mkdir(mode=0o700);(tests/'test_epoch3_fixture.py').write_bytes(b'# fixture')
  source=pathlib.Path(__file__).resolve().parent
  files={}
  for name in s.HELPERS:
   origin=source/name
   if not origin.exists():origin=pathlib.Path(os.environ['P2_REVIEWED_HELPERS'])/name
   data=origin.read_bytes();(helpers/name).write_bytes(data);files[name]=hashlib.sha256(data).hexdigest()
  shutil.copytree(os.environ['P2_NEW_ROOT'],str(self.kit/'xuanjun-p2-package'))
  entry_path=source/'epoch3_recovery_entry.py'
  if not entry_path.exists():entry_path=pathlib.Path(os.environ['P2_ENTRY_PATH'])
  entry=entry_path.read_bytes();self.entry=self.kit/'epoch3_recovery_entry.py';self.entry.write_bytes(entry)
  value={'schema':1,'runtime_manifest_sha256':s.MANIFEST,'helper_files':files,'entry_sha256':hashlib.sha256(entry).hexdigest(),'test_files':{'test_epoch3_fixture.py':hashlib.sha256(b'# fixture').hexdigest()}}
  raw=json.dumps(value).encode();(self.kit/'recovery-kit-manifest.json').write_bytes(raw);self.digest=hashlib.sha256(raw).hexdigest()
  self.patches=[mock.patch.object(s,'KIT',str(self.kit)),mock.patch.object(s,'__file__',str(self.entry)),
                mock.patch.object(s.socket,'gethostname',return_value='iZd7oeikknn1z21sq6ji6zZ')]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def execute(self):return s.verify_kit(self.digest)
 def test_exact_actual_runtime_and_helpers(self):self.assertEqual(self.execute(),str(self.kit/'xuanjun-p2-package'))
 def test_modified_helper_rejected(self):
  (self.kit/'helpers/epoch3_plan.py').write_bytes(b'bad')
  with self.assertRaises(ValueError):self.execute()
 def test_extra_helper_rejected(self):
  (self.kit/'helpers/evil.py').write_bytes(b'bad')
  with self.assertRaises(ValueError):self.execute()
 def test_extra_runtime_module_rejected(self):
  (self.kit/'xuanjun-p2-package/stage1/evil.py').write_bytes(b'bad')
  with self.assertRaises(ValueError):self.execute()
 def test_bytecode_rejected(self):
  p=self.kit/'helpers/__pycache__';p.mkdir()
  with self.assertRaises(ValueError):self.execute()
 def test_manifest_mismatch_rejected(self):
  with self.assertRaises(ValueError):s.verify_kit('0'*64)
 def test_wrong_host_rejected(self):
  with mock.patch.object(s.socket,'gethostname',return_value='wrong'):
   with self.assertRaises(ValueError):self.execute()
 def test_loose_helpers_rejected(self):
  os.chmod(str(self.kit/'helpers'),0o777)
  with self.assertRaises(ValueError):self.execute()
if __name__=='__main__':unittest.main()
