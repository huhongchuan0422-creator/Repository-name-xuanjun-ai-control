import importlib.util,os,pathlib,shutil,subprocess,sys,tempfile,unittest,errno
from unittest.mock import patch
ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT']);sys.path.insert(0,str(ROOT/'stage1'))
spec=importlib.util.spec_from_file_location('publisher_test',os.environ.get('P2_PUBLISHER_MODULE',str(ROOT/'stage1/p2_publisher_bootstrap.py')))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Publisher(unittest.TestCase):
 def setUp(self):
  if os.getuid()!=0:self.skipTest('Root suite is invoked with sudo')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
  self.tx=self.root/'transaction';self.tx.mkdir(mode=0o700)
  self.parent=self.root/'targets';self.parent.mkdir(mode=0o755)
  self.home=self.root/'config';self.home.mkdir(mode=0o700)
  try:os.chown(str(self.home),1003,1003)
  except OSError as error:
   if error.errno==errno.EINVAL:self.skipTest('Local UID mapping unavailable; hosted CI/UK numeric UID suite required')
   raise
  self.targets=(str(self.parent/'control.git'),str(self.home/'gh'))
  p=patch.object(m,'TARGETS',self.targets);p.start();self.addCleanup(p.stop)
  work=self.root/'work';work.mkdir();subprocess.run(['/usr/bin/git','init','--quiet',str(work)],check=True)
  (work/'file').write_text('SYNTHETIC=1\n')
  subprocess.run(['/usr/bin/git','-C',str(work),'add','file'],check=True)
  subprocess.run(['/usr/bin/git','-C',str(work),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','fixture'],check=True)
  def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(work)]+list(args)).decode().strip()
  commit=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}');ref='refs/xuanjun-preparation/'+commit;git('update-ref',ref,commit)
  bundle=self.root/'fixture.bundle';git('bundle','create',str(bundle),ref);bundle.chmod(0o600)
  self.data={'source_commit':commit,'source_tree':tree,'bundle':{'path':str(bundle)}}
  self.bp=m.PublisherBootstrap(str(self.tx));self.real_prepare=self.bp.prepare
  self.bp.prepare=lambda ref:(self.data,b'SYNTHETIC_CREDENTIAL_NOT_A_SECRET\n')
 def test_apply_rollback_replay(self):
  self.bp.apply({});self.assertTrue(all(os.path.isdir(p) for p in self.targets));self.bp.rollback();self.bp.rollback()
  self.assertTrue(all(not os.path.lexists(p) for p in self.targets))
 def test_crash_after_rename_before_ack(self):
  rename=m.rename_absent
  def crash(a,b):rename(a,b);raise RuntimeError('INJECTED')
  with patch.object(m,'rename_absent',side_effect=crash):
   with self.assertRaises(RuntimeError):self.bp.apply({})
  m.PublisherBootstrap(str(self.tx)).rollback();self.assertFalse(os.path.lexists(self.targets[0]))
 def test_unknown_content_holds_both(self):
  self.bp.apply({});pathlib.Path(self.targets[1]+'/hosts.yml').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'HOLD_PUBLISHER_DIRECTORY_CHANGED'):self.bp.rollback()
  self.assertTrue(all(os.path.isdir(p) for p in self.targets))
 def test_extra_hardlink_rejected(self):
  self.bp.apply({});os.link(self.targets[1]+'/hosts.yml',str(self.root/'extra'))
  with self.assertRaises(ValueError):self.bp.rollback()
 def test_directory_symlink_rejected(self):
  self.bp.apply({});os.symlink('/tmp',self.targets[0]+'/untracked-directory')
  with self.assertRaisesRegex(ValueError,'PUBLISHER_DIRECTORY_SYMLINK'):self.bp.rollback()
  self.assertTrue(all(os.path.isdir(p) for p in self.targets))
 def test_same_bytes_replacement_rejected(self):
  self.bp.apply({});p=pathlib.Path(self.targets[1]+'/hosts.yml');raw=p.read_bytes();p.unlink();p.write_bytes(raw);os.chown(str(p),1003,1003);p.chmod(0o600)
  with self.assertRaisesRegex(ValueError,'HOLD_PUBLISHER_DIRECTORY_CHANGED'):self.bp.rollback()
 def test_missing_reference(self):
  with self.assertRaisesRegex(ValueError,'PUBLISHER_EXACT_REFERENCE'):self.real_prepare(None)
 def test_rename_never_overwrites(self):
  a=self.root/'a';b=self.root/'b';a.mkdir();b.mkdir()
  with self.assertRaises(OSError):m.rename_absent(str(a),str(b))
  self.assertTrue(a.exists());self.assertTrue(b.exists())
if __name__=='__main__':unittest.main(verbosity=2)
