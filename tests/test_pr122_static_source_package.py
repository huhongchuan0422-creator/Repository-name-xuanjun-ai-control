"""Offline deterministic source packaging; no release execution."""
import ast,hashlib,io,json,tarfile,tempfile,unittest
from pathlib import Path
from scripts import pr122_static_source_package as package
class PackageTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name);(self.root/'scripts').mkdir()
  for n in package.MODULES:(self.root/'scripts'/(n+'.py')).write_text('# fixture '+n)
 def test_exact_closure_and_determinism(self):
  raw,report=package.build(self.root,'a'*40);self.assertEqual(raw,package.build(self.root,'a'*40)[0]);self.assertEqual(report['installation_permission'],'NOT_ISSUED')
  with tarfile.open(fileobj=io.BytesIO(raw)) as t:files={m.name.removeprefix('pr122-static-controlled/'):t.extractfile(m).read() for m in t}
  m=json.loads(files.pop('STATIC_SOURCE_MANIFEST.json'));self.assertEqual(len(files),23);self.assertEqual(set(files),{'scripts/'+n+'.py' for n in package.MODULES})
  for r in m['files']:self.assertEqual(hashlib.sha256(files[r['path']]).hexdigest(),r['sha256'])
 def test_private_files_not_collected(self):
  (self.root/'PRIVATE.json').write_text('must not be packaged');(self.root/'scripts/unreviewed.py').write_text('not collected')
  raw,_=package.build(self.root,'a'*40)
  with tarfile.open(fileobj=io.BytesIO(raw)) as t:self.assertEqual(len(t.getmembers()),24)
 def test_no_source_substitution(self):
  p=self.root/'scripts'/(package.MODULES[0]+'.py');p.unlink();p.symlink_to(self.root/'outside')
  with self.assertRaises(ValueError):package.build(self.root,'a'*40)
 def test_exact_commit_required(self):
  for value in (None,'main','a'*39,'G'*40):
   with self.assertRaises(ValueError):package.build(self.root,value)
 def test_manifest_binds_source_change(self):
  _,before=package.build(self.root,'a'*40);(self.root/'scripts'/(package.MODULES[0]+'.py')).write_text('changed');_,after=package.build(self.root,'a'*40);self.assertNotEqual(before['manifest_sha256'],after['manifest_sha256'])
 def test_real_top_level_import_closure(self):
  root=Path(__file__).resolve().parents[1]
  for module in package.MODULES:
   for node in ast.parse((root/'scripts'/(module+'.py')).read_text()).body:
    if isinstance(node,ast.ImportFrom) and node.module:
     names=[x.name for x in node.names] if node.module=='scripts' else [node.module.split('.')[1]] if node.module.startswith('scripts.') else []
     for name in names:self.assertIn(name,package.MODULES)
if __name__=='__main__':unittest.main()
