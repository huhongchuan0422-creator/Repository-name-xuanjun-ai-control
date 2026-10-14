import hashlib,json,os,pathlib,shutil,tempfile,unittest
import build_epoch5_runtime as subject

class RuntimeBuildTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
  self.original=pathlib.Path(os.environ['P2_ORIGINAL_ROOT'])
  self.fixes=pathlib.Path(os.environ['P2_FIXES_ROOT'])
 def tearDown(self):self.temp.cleanup()
 def build(self,name='out',original=None,fixes=None):
  return subject.build(str(original or self.original),str(fixes or self.fixes),str(self.root/name))
 def test_repeat_build_byte_exact(self):
  a=self.build('a');b=self.build('b')
  self.assertEqual(a,b)
  self.assertEqual((self.root/'a/epoch5-runtime-candidate.tar.gz').read_bytes(),(self.root/'b/epoch5-runtime-candidate.tar.gz').read_bytes())
 def test_only_two_runtime_files_change(self):
  result=self.build();r=self.root/'out/xuanjun-p2-package'
  old=json.loads((self.original/'deploy/integration-manifest.json').read_text())
  new=json.loads((r/'deploy/integration-manifest.json').read_text())
  self.assertEqual(set(old['files']),set(new['files']))
  self.assertEqual({p for p in old['files'] if old['files'][p]!=new['files'][p]},set(subject.REPAIRS))
  for path,digest in new['files'].items():self.assertEqual(hashlib.sha256((r/path).read_bytes()).hexdigest(),digest)
  self.assertEqual(result['runtime_files'],102)
 def test_does_not_overwrite_output(self):
  self.build()
  with self.assertRaisesRegex(ValueError,'OUTPUT_ALREADY_EXISTS'):self.build()
 def test_changed_patch_rejected(self):
  f=self.root/'fixes';f.mkdir()
  for name in subject.REPAIRS:
   (f/pathlib.Path(name).name).write_bytes((self.fixes/pathlib.Path(name).name).read_bytes()+b'\n')
  with self.assertRaisesRegex(ValueError,'REPAIR_SOURCE_CHANGED'):self.build(fixes=f)
  self.assertFalse((self.root/'out').exists())
 def test_changed_manifest_rejected(self):
  r=self.root/'old';(r/'deploy').mkdir(parents=True)
  (r/'deploy/integration-manifest.json').write_bytes(b'{}')
  with self.assertRaisesRegex(ValueError,'ORIGINAL_MANIFEST_CHANGED'):self.build(original=r)
 def test_original_runtime_drift_rejected(self):
  r=self.root/'old';shutil.copytree(str(self.original),str(r))
  path=r/'stage1/p2_tls_lifecycle.py';path.chmod(0o600);path.write_bytes(b'# drift')
  with self.assertRaisesRegex(ValueError,'RUNTIME_FILE_HASH_MISMATCH'):self.build(original=r)
 def test_no_install_authority_and_original_untouched(self):
  before=(self.original/'deploy/integration-manifest.json').read_bytes()
  v=self.build()
  self.assertFalse(v['old_install_or_resume_entrypoint_permitted'])
  self.assertEqual(v['epoch5_recovery_entrypoint'],'NOT_IMPLEMENTED')
  self.assertEqual(v['production_execution'],'NOT_RUN')
  self.assertEqual(before,(self.original/'deploy/integration-manifest.json').read_bytes())

if __name__=='__main__':unittest.main()
