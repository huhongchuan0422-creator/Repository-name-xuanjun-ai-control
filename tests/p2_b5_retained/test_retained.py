"""Synthetic retained GNU archive/filesystem; never actual UK or SDK execution."""
import ast,sys,hashlib,importlib.util,io,json,os,tarfile,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('retained',R/'scripts/p2_b5_retained_materials.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def sha(raw):return hashlib.sha256(raw).hexdigest()
class Tests(unittest.TestCase):
 def fixture(self):
  files={'package.json':b'{"version":"2026.9.9","dependencies":{"missing":"1.0"},"optionalDependencies":{"native":"2.0"},"exports":{".":"./dist/index.js"}}','openclaw.mjs':b'import "./dist/index.js";','dist/index.js':b'import "./child.mjs"; import(dynamic);','dist/child.mjs':b'export const x=1;','dist/loader-runtime-load-DpgEqnzx.mjs':b'export {x} from "./context-DyPstb2Q.mjs";','dist/context-DyPstb2Q.mjs':b'export const x=1;','node_modules/acorn/package.json':b'{"version":"8.18.0","main":"dist/acorn.js"}','node_modules/acorn/dist/acorn.js':b'export const parse=()=>{};','dist/gateway-auth-real.mjs':b'import "./child.mjs";'}
  reader=m.support('p2_b5_three_files.py');root=reader.ROOT;rows={root+n:dict(path='/'+root+n,bytes=len(raw),sha256=sha(raw),uid=os.getuid(),gid=os.getgid(),mode=0o600) for n,raw in files.items()}
  return reader,files,rows
 def test_recursive_materials_are_not_closure(self):
  reader,files,rows=self.fixture();report,selected=m.analyze(rows,lambda n:files[n[len(reader.ROOT):]],reader.ROOT,['dist/child.mjs','dist/absent.mjs'],lambda b:None)
  self.assertIn('dist/child.mjs',selected);self.assertIn('node_modules/acorn/dist/acorn.js',selected)
  self.assertEqual(report['first_frontier_missing'],['dist/absent.mjs']);self.assertEqual(report['dependency_closure'],'UNKNOWN');self.assertEqual(report['node']['state'],'ABSENT_FROM_RETAINED_MANIFEST')
  self.assertTrue(any(x.startswith('PACKAGE_MISSING:native@') for x in report['unresolved']));self.assertTrue(report['dynamic_resource_indicators']);self.assertEqual(report['authenticated_dispatch'],'NOT_EXECUTED')
 def test_no_guessing_extension_or_path_escape(self):
  self.assertIsNone(m.resolve_relative('dist/a.mjs','./child',{'dist/child.mjs':{}}));self.assertIsNone(m.resolve_relative('a.mjs','../escape',{'../escape':{}}));self.assertIsNone(m.resolve_relative('a.mjs','./ok?query',{'ok?query':{}}))
 def test_changed_member_rejected(self):
  reader,files,rows=self.fixture()
  with self.assertRaisesRegex(ValueError,'SELECTED_SOURCE_SHA'):m.analyze(rows,lambda n:b'changed',reader.ROOT,[],lambda b:None)
 def test_bounds_reported_not_silently_passed(self):
  reader,files,rows=self.fixture();old=m.MAX_FILES
  try:
   m.MAX_FILES=1;report,_=m.analyze(rows,lambda n:files[n[len(reader.ROOT):]],reader.ROOT,[],lambda b:None)
   self.assertIn('MAX_FILES',report['bounds_reached']);self.assertGreater(report['unprocessed_count'],0);self.assertEqual(report['dependency_closure'],'UNKNOWN')
  finally:m.MAX_FILES=old
 def test_real_gnu_archive_full_validation_and_output_retained(self):
  reader,files,rows=self.fixture();buf=io.BytesIO()
  with tarfile.open(fileobj=buf,mode='w',format=tarfile.GNU_FORMAT) as tar:
   for n,raw in files.items():
    item=tarfile.TarInfo(reader.ROOT+n);item.size=len(raw);item.mode=0o600;item.uid=os.getuid();item.gid=os.getgid();tar.addfile(item,io.BytesIO(raw))
  archive=buf.getvalue();manifest=json.dumps(dict(scope='ISOLATED_TEST_ONLY_SOURCE_SNAPSHOT',files=list(rows.values()),files_count=len(rows),bytes=sum(len(v) for v in files.values()))).encode()
  reader.PINS=dict(tar_bytes=len(archive),tar_sha256=sha(archive),manifest_bytes=len(manifest),manifest_sha256=sha(manifest),members=len(rows),targets={n:(len(files[n]),sha(files[n])) for n in ('package.json','dist/loader-runtime-load-DpgEqnzx.mjs','dist/context-DyPstb2Q.mjs')})
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'source.tar').write_bytes(archive);(p/'manifest.json').write_bytes(manifest);(p/'out').mkdir(mode=0o700)
   with (p/'source.tar').open('rb') as a,(p/'manifest.json').open('rb') as b:
    out=os.open(str(p/'out'),os.O_RDONLY|os.O_DIRECTORY)
    try:
     self.assertEqual(m.run(a.fileno(),b.fileno(),out,reader,['dist/child.mjs'],lambda b:None),0)
     report=json.loads((p/'out/report.json').read_text());self.assertTrue(report['source_validation']['all_members_content_sha_verified']);self.assertEqual(report['dependency_closure'],'UNKNOWN')
     verified=m.verify_outputs(out,os.getuid());self.assertEqual(verified['materials.tar']['sha256'],sha((p/'out/materials.tar').read_bytes()))
     first=(p/'out/materials.tar').read_bytes()
     with self.assertRaises(FileExistsError):m.run(a.fileno(),b.fileno(),out,reader,['dist/child.mjs'],lambda b:None)
     self.assertEqual((p/'out/materials.tar').read_bytes(),first)
    finally:os.close(out)
   self.assertEqual((p/'source.tar').read_bytes(),archive);self.assertEqual((p/'manifest.json').read_bytes(),manifest)
 def test_bootstrap_embedded_files_match_frozen_sources(self):
  spec=importlib.util.spec_from_file_location('bootstrap',R/'scripts/p2_b5_retained_bootstrap.py');bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
  files=bootstrap.unpack()
  for name,raw in files.items():self.assertEqual(raw,(R/name).read_bytes())
  self.assertIn('scripts/p2_b5_retained_materials.py',files)
  metadata=json.loads((R/'docs/p2-b5-20261020/retained-materials-candidate.json').read_text());command=(R/'docs/p2-b5-20261020/retained-materials.command').read_bytes();source=(R/'scripts/p2_b5_retained_bootstrap.py').read_bytes()
  self.assertEqual(sha(command),metadata['command_sha256']);self.assertEqual(sha(source),metadata['bootstrap_sha256']);self.assertIn(metadata['bootstrap_git_blob'].encode(),command)
  self.assertEqual(hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest(),metadata['bootstrap_git_blob'])
  old=bootstrap.BUNDLE
  try:
   bootstrap.BUNDLE='corrupt'
   with self.assertRaises(Exception):bootstrap.unpack()
  finally:bootstrap.BUNDLE=old
 def test_failed_input_retains_error_without_material_output(self):
  reader=m.support('p2_b5_three_files.py')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tar').write_bytes(b'unchanged-invalid-tar');(p/'manifest').write_bytes(b'unchanged-invalid-manifest');(p/'out').mkdir(mode=0o700)
   with (p/'tar').open('rb') as a,(p/'manifest').open('rb') as b:
    out=os.open(str(p/'out'),os.O_RDONLY|os.O_DIRECTORY)
    try:self.assertEqual(m.run(a.fileno(),b.fileno(),out,reader,[],lambda b:None),2)
    finally:os.close(out)
   receipt=json.loads((p/'out/child-receipt.json').read_text());self.assertEqual(receipt['state'],'HOLD');self.assertEqual(receipt['stage'],'FULL_INPUT_VERIFY');self.assertEqual(receipt['error'],'INPUT_SIZE');self.assertFalse((p/'out/materials.tar').exists());self.assertEqual((p/'tar').read_bytes(),b'unchanged-invalid-tar')
 def test_python36_syntax(self):
  for name in ('p2_b5_retained_materials.py','p2_b5_retained_bootstrap.py'):
   source=(R/'scripts'/name).read_text()
   if sys.version_info>=(3,8):ast.parse(source,feature_version=(3,6))
   else:ast.parse(source)
if __name__=='__main__':unittest.main()
