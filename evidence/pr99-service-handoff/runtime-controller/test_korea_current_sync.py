import io,json,sqlite3,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
import korea_current_sync as m

class CurrentSyncTests(unittest.TestCase):
 def test_paths(self):
  for path in ('/etc/shadow','../x','a/../b','a//b','a\\b'):
   with self.assertRaises(RuntimeError):m.relative(path)
 def test_committed_wal_and_uncommitted_are_distinguished(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);src=p/'live.db';out=p/'copy.db'
   c=sqlite3.connect(src);c.execute('PRAGMA journal_mode=WAL');c.execute('CREATE TABLE t(x)');c.execute('INSERT INTO t VALUES(1)');c.commit();c.execute('INSERT INTO t VALUES(2)')
   m.sqlite_copy(src,out)
   with sqlite3.connect(out) as read:self.assertEqual(read.execute('SELECT x FROM t').fetchall(),[(1,)])
   c.rollback();c.close()
 def test_collect_reuses_unchanged_and_preserves_link_metadata(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);base=p/'src';work=p/'work';base.mkdir();work.mkdir()
   (base/'same').write_bytes(b'old');(base/'changed').write_bytes(b'new');(base/'link').symlink_to('/outside')
   result=m.collect(base,work,{'same':m.digest(base/'same')})
   self.assertFalse((work/'files/same').exists());self.assertEqual((work/'files/changed').read_bytes(),b'new')
   self.assertEqual(result['symlinks_not_activated'],{'link':'/outside'})
 def remote_fixture(self,extra=False,tamper=False):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);baseline=p/'baseline';baseline.mkdir();root=p/'releases';root.mkdir()
   (baseline/'same').write_bytes(b'old')
   manifest={'source':m.existing.SOURCE,'target':m.existing.TARGET,'baseline_sha256':m.SHA,'directories':[],
    'files':{'same':{'sha256':m.digest(baseline/'same'),'bytes':3}},'sqlite_backups':[],'symlinks_not_activated':{}}
   if tamper:(baseline/'same').write_bytes(b'bad')
   package=p/'in.tar.gz'
   with tarfile.open(package,'w:gz') as t:
    data=json.dumps(manifest).encode();member=tarfile.TarInfo('manifest.json');member.size=len(data);t.addfile(member,io.BytesIO(data))
    if extra:
     member=tarfile.TarInfo('../escape');member.size=1;t.addfile(member,io.BytesIO(b'x'))
   code=m.REMOTE.replace("if os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZmj7a5kwr75qc1tul4kf9Z': raise SystemExit('HOST_OR_ROOT')",'pass')
   code=code.replace("root=Path('/opt/xuanjun-migration-s07/releases')",'root=Path('+repr(str(root))+')')
   code=code.replace("baseline=root/'korea-project-precopy-f4db2e4e5f20/opt/trading-system'",'baseline=Path('+repr(str(baseline))+')')
   code=code.replace("'/root/pr99-korea-project-install.lock'",repr(str(p/'lock')))
   result=subprocess.run([sys.executable,'-I','-B','-S','-c',code,m.digest(package)],input=package.read_bytes(),capture_output=True)
   if extra or tamper:
    self.assertNotEqual(result.returncode,0);self.assertEqual(list(root.glob('korea-current-recovery-*')),[])
   else:
    self.assertEqual(result.returncode,0,result.stderr);receipt=json.loads(result.stdout)
    self.assertFalse(receipt['production_cutover']);self.assertEqual((Path(receipt['directory'])/'project/same').read_bytes(),b'old')
    query=subprocess.run([sys.executable,'-I','-B','-S','-c',code,m.digest(package),'query'],input=b'',capture_output=True)
    self.assertEqual(query.returncode,0,query.stderr);self.assertEqual(json.loads(query.stdout),receipt)
    (Path(receipt['directory'])/'project/same').write_bytes(b'drift')
    changed=subprocess.run([sys.executable,'-I','-B','-S','-c',code,m.digest(package),'query'],input=b'',capture_output=True)
    self.assertNotEqual(changed.returncode,0)
 def test_remote_materializes_from_existing_baseline(self):self.remote_fixture()
 def test_remote_rejects_traversal(self):self.remote_fixture(extra=True)
 def test_remote_rejects_baseline_tampering(self):self.remote_fixture(tamper=True)

if __name__=='__main__':unittest.main()
