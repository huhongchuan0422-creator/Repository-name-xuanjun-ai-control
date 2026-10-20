"""Bounded real filesystem snapshots; no SDK or UK acceptance."""
import ast,hashlib,importlib.util,io,json,os,struct,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[2]/'scripts/p2_b5_snapshot.py'
spec=importlib.util.spec_from_file_location('snapshot',str(P));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SnapshotTests(unittest.TestCase):
 def tree(self):
  t=tempfile.TemporaryDirectory(dir="/root",prefix="b5-snapshot-test-");self.addCleanup(t.cleanup);p=Path(t.name);os.chmod(str(p),0o700);return p
 def test_python36_grammar_and_no_runtime_calls(self):
  source=P.read_text();ast.parse(source,feature_version=(3,6));self.assertNotIn('subprocess',source);self.assertNotIn('os.system',source)
 def test_wrong_target_stops_before_writes(self):
  r=subprocess.run([sys.executable,'-I','-B','-S',str(P)],stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,2);self.assertIn(b'FIXED_HOST_UID_REQUIRED',r.stdout)
 def test_data_policy(self):
  for n in ['auth.json','config.json','secrets.env','a.sqlite3','a.db-wal','.env','credentials/a.json','x.key','secrets.json','password.json','config/runtime.json','auth/profile.json'] :self.assertFalse(m.permitted(n),n)
  for n in ['dist/auth-code.mjs','node_modules/a/package.json','dist/context.mjs']:self.assertTrue(m.permitted(n),n)
 def test_elf_non_elf_and_truncation_hold(self):
  for raw in [b'',b'NOTELF',b'\x7fELF\x02\x01']:
   with self.assertRaises(ValueError):m.elf_needs(raw)
 def test_real_elf_static_names_only(self):
  raw=Path("/usr/bin/true").resolve().read_bytes();info=m.elf_needs(raw);self.assertIsInstance(info['needed'],list);self.assertTrue(info['interpreter'].startswith('/'))
 def test_snapshot_exact_bytes_and_excluded_data_not_copied(self):
  root=self.tree();(root/'package.json').write_text('{}');(root/'auth.json').write_text('NEVER_COPY');(root/'entry.mjs').write_text('export{}');buffer=io.BytesIO()
  with tarfile.open(fileobj=buffer,mode='w|') as tar:
   c=m.Collector(tar);c.tree(str(root))
  with tarfile.open(fileobj=io.BytesIO(buffer.getvalue())) as tar:
   self.assertEqual(len(tar.getmembers()),2);self.assertFalse(any('auth.json' in n for n in tar.getnames()))
  self.assertEqual(c.files,2);self.assertEqual(c.holds[0]['reason'],'EXCLUDED_MEMBER')
 def test_symlink_fifo_never_opened(self):
  root=self.tree();(root/'external').symlink_to('/etc/shadow');os.mkfifo(str(root/'fifo'));buffer=io.BytesIO()
  with tarfile.open(fileobj=buffer,mode='w|') as tar:c=m.Collector(tar);c.tree(str(root))
  self.assertEqual(c.files,0);self.assertEqual(len(c.holds),2)
 def test_limits_and_existing_output_retained(self):
  root=self.tree();p=root/'large.mjs';p.write_bytes(b'1234')
  with tarfile.open(fileobj=io.BytesIO(),mode='w|') as tar:
   c=m.Collector(tar)
   with patch.object(m,'MAX_FILE',3):
    with self.assertRaisesRegex(ValueError,'SOURCE_FILE'):c.file(str(p),'fixture')
  target=root/'receipt';m.write_new(str(target),b'original')
  with self.assertRaises(FileExistsError):m.write_new(str(target),b'overwrite')
  self.assertEqual(target.read_bytes(),b'original')
 def test_partial_failure_result_persistent_no_success(self):
  out=self.tree();node=self.tree()/'node';node.write_bytes(b'NOTELF');sdk=self.tree();(sdk/'package.json').write_text('{}')
  with patch.object(m,'NODE',str(node)),patch.object(m,'SDK',str(sdk)),patch.object(m,'PINS',{str(sdk/'package.json'):'0'*64}):
   code=m.collect(str(out))
  self.assertEqual(code,2);manifest=json.loads((out/'manifest.json').read_text());self.assertEqual(manifest['files_count'],len(manifest['files']));self.assertEqual(manifest['bytes'],sum(r['bytes'] for r in manifest['files']));result=json.loads((out/'result.json').read_text());self.assertEqual(result['state'],'HOLD');self.assertEqual(result['capture'],'STOPPED_RETAINED');self.assertEqual(result['error'],'HISTORICAL_PIN_CHANGED');self.assertTrue((out/'source-tree.tar.pending').exists());self.assertEqual(result['cp11'],'NOT_EXECUTED')
 def test_output_fd_retained_across_process(self):
  out=self.tree();sdk=self.tree();node=sdk/'node';node.write_bytes(b'NOTELF');(sdk/'package.json').write_text('{}')
  fd=os.open(str(out),os.O_RDONLY|os.O_DIRECTORY)
  code="import runpy; m=runpy.run_path(%r); g=m['collect'].__globals__; g.update(NODE=%r,SDK=%r,PINS={}); raise SystemExit(m['collect'](%d))"%(str(P),str(node),str(sdk),fd)
  try:r=subprocess.run([sys.executable,'-I','-B','-S','-c',code],pass_fds=(fd,),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  finally:os.close(fd)
  self.assertEqual(r.returncode,2,r.stderr);value=json.loads((out/'result.json').read_text());self.assertEqual(value['capture'],'BOUNDED_SOURCE_CAPTURED');self.assertEqual(value['dependency_closure'],'UNKNOWN');self.assertEqual(value['state'],'HOLD');self.assertTrue((out/'manifest.json').exists())
 def test_wrapper_source_pin_grammar_and_wrong_host(self):
  wrapper=P.parents[1]/'docs/p2-b5-20261020/SNAPSHOT_CANDIDATE.sh'
  code=wrapper.read_text().split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
  tree=ast.parse(code,feature_version=(3,6));values={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('SOURCE_SHA','SOURCE_COMMIT')}
  self.assertEqual(values['SOURCE_SHA'],hashlib.sha256(P.read_bytes()).hexdigest())
  r=subprocess.run([sys.executable,'-I','-B','-S','-'],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.assertNotEqual(r.returncode,0);self.assertIn(b'HOLD_HOST_ROOT',r.stderr)
 def test_elf_missing_and_ambiguous_candidates_hold(self):
  first=self.tree();second=self.tree()
  with tarfile.open(fileobj=io.BytesIO(),mode='w|') as tar:
   c=m.Collector(tar);c.elf=[{'path':'node','dependencies':{'interpreter':None,'needed':['a.so']}}]
   with patch.object(m,'SYSROOTS',(str(first),str(second))):m.capture_libraries(c)
   self.assertEqual(c.holds[0]['reason'],'ELF_LIBRARY_MISSING_OR_AMBIGUOUS')
   (first/'a.so').write_bytes(b'x');(second/'a.so').write_bytes(b'y');c.holds=[]
   with patch.object(m,'SYSROOTS',(str(first),str(second))):m.capture_libraries(c)
   self.assertEqual(c.holds[0]['reason'],'ELF_LIBRARY_MISSING_OR_AMBIGUOUS');self.assertEqual(c.files,0)
 def test_uid1002_writes_by_fd_without_private_parent_access(self):
  parent=self.tree();out=parent/'uid1002';out.mkdir(mode=0o700)
  try:os.chown(str(out),1002,1002)
  except OSError:
   if os.environ.get('B5_REQUIRE_UID1002')=='1':raise
   self.skipTest('local chown unavailable; Hosted sudo test required')
  fd=os.open(str(out),os.O_RDONLY|os.O_DIRECTORY)
  code=P.read_text()+"\nNODE='/root/nonexistent-b5-source';SDK='/root/nonexistent-b5-sdk';PINS={};raise SystemExit(collect(%d))\n"%fd
  # Rename main guard so this fixture exercises collect, not UK identity acceptance.
  code=code.replace("if __name__=='__main__':", "if False:")
  def drop():os.setgroups([]);os.setgid(1002);os.setuid(1002)
  try:
   try:r=subprocess.run([sys.executable,'-I','-B','-S','-'],input=code.encode(),pass_fds=(fd,),preexec_fn=drop,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   except subprocess.SubprocessError:
    if os.environ.get('B5_REQUIRE_UID1002')=='1':raise
    self.skipTest('local setuid unavailable; Hosted sudo test required')
  finally:os.close(fd)
  self.assertEqual(r.returncode,2,r.stderr);result=json.loads((out/'result.json').read_text());self.assertEqual(result['state'],'HOLD');self.assertEqual((out/'result.json').stat().st_uid,1002);self.assertEqual(parent.stat().st_mode&0o777,0o700)
 def test_depth_and_time_fail_closed(self):
  root=self.tree()
  with tarfile.open(fileobj=io.BytesIO(),mode='w|') as tar:
   c=m.Collector(tar)
   with self.assertRaisesRegex(ValueError,'DEPTH_BOUND'):c.tree(str(root),depth=m.MAX_DEPTH+1)
   c.start-=m.MAX_SECONDS+1
   with self.assertRaisesRegex(ValueError,'TIME_BOUND'):c.bound()
if __name__=='__main__':unittest.main()
