import hashlib,importlib.util,json,os,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
server=load('server',ROOT/'scripts/p2_b5_shutdown_member.py')
class ServerMember(unittest.TestCase):
 def setUp(self):
  self.original=server.PIN;self.raw=b'x'*3884;server.PIN=hashlib.sha256(self.raw).hexdigest();self.rows={'root/'+server.TARGET:{'bytes':3884,'sha256':server.PIN}};self.calls=[]
 def tearDown(self):server.PIN=self.original
 def get(self,n):self.calls.append(n);return self.raw
 def run_analyze(self):return server.analyze(self.rows,self.get,'root/',None,None)
 def test_only_one_no_recursive_reads(self):
  self.rows['root/other.mjs']={'bytes':1,'sha256':'0'*64};report,files=self.run_analyze();self.assertEqual(self.calls,['root/'+server.TARGET]);self.assertEqual(set(files),{server.TARGET});self.assertEqual(report['owner_binding'],'UNBOUND')
 def test_missing_member(self):
  self.rows.clear()
  with self.assertRaisesRegex(ValueError,'SERVER_MEMBER_ABSENT'):self.run_analyze()
  self.assertEqual(self.calls,[])
 def test_size_and_hash_before_read(self):
  for k,v in [('bytes',3885),('sha256','0'*64)]:
   row=self.rows['root/'+server.TARGET];old=row[k];row[k]=v
   with self.assertRaisesRegex(ValueError,'MANIFEST_FIXED_PIN'):self.run_analyze()
   row[k]=old
  self.assertEqual(self.calls,[])
 def test_content_tamper(self):
  self.raw=b'y'*3884
  with self.assertRaisesRegex(ValueError,'CONTENT_SHA'):self.run_analyze()
 def test_bundle_and_complete_command_binding(self):
  boot=load('bootstrap',ROOT/'scripts/p2_b5_shutdown_bootstrap.py');rows=boot.unpack();self.assertEqual(rows['scripts/p2_b5_shutdown_member.py'],(ROOT/'scripts/p2_b5_shutdown_member.py').read_bytes())
  self.assertNotIn('scripts/p2_b5_ws_anchors.py',rows)
  self.assertEqual(server.load_base().OUTPUT,'p2-b5-shutdown-member-v1-20261021')
  meta=json.loads((ROOT/'docs/p2-b5-20261020/shutdown-member-candidate.json').read_text());raw=(ROOT/'scripts/p2_b5_shutdown_bootstrap.py').read_bytes();command=(ROOT/'docs/p2-b5-20261020/shutdown-member.command').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),meta['bootstrap_sha256']);self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),meta['bootstrap_git_blob']);self.assertEqual(hashlib.sha256(command).hexdigest(),meta['command_sha256'])
 def test_full_verifier_failure_preserves_partial(self):
  base=server.load_base()
  class Reader:
   PINS={};ROOT='root/';Hold=ValueError
   @staticmethod
   def select_files(*a):raise ValueError('FULL_SOURCE_HASH_FAILURE')
  with tempfile.TemporaryDirectory() as d:
   fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
   try:
    p=Path(d,'materials.tar');p.write_bytes(b'prior partial')
    self.assertEqual(base.run(-1,-1,fd,Reader,[],None),2);self.assertEqual(p.read_bytes(),b'prior partial');self.assertEqual(json.loads(Path(d,'child-receipt.json').read_text())['state'],'HOLD')
    with self.assertRaises(FileExistsError):base.write_new(fd,'materials.tar',b'overwrite')
   finally:os.close(fd)
 def test_fixed_target_and_unchanged_resource_limits(self):
  self.assertEqual(server.TARGET,'dist/server-shutdown-6hlRrMSx.mjs')
  self.assertEqual(server.SIZE,3884)
  self.assertEqual(self.original,'4fd5792f6c4dbd7dd3e257edd085866578eaf7ee0bafe3d9ab6cd77357a5df36')
  base=server.load_base()
  self.assertEqual(base.MAX_SELECTED,16*1024*1024)
  self.assertEqual(base.MAX_REPORT,2*1024*1024)
  boot=load('core_boot',ROOT/'scripts/p2_b5_shutdown_bootstrap.py')
  self.assertEqual(boot.NAME,'p2-b5-shutdown-candidate-v1-20261021')
  self.assertEqual(boot.unpack()['scripts/p2_b5_retained_materials.py'],(ROOT/'scripts/p2_b5_retained_materials.py').read_bytes())
 def test_existing_source_directory_preserved(self):
  boot=load('core_boot_collision',ROOT/'scripts/p2_b5_shutdown_bootstrap.py')
  with tempfile.TemporaryDirectory() as d:
   path=Path(d,boot.NAME);path.mkdir();p=path/'bootstrap-result.json';p.write_bytes(b'prior failure')
   fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
   try:
    with self.assertRaises(FileExistsError):os.mkdir(boot.NAME,0o700,dir_fd=fd)
    self.assertEqual(p.read_bytes(),b'prior failure')
   finally:os.close(fd)
if __name__=='__main__':unittest.main()
