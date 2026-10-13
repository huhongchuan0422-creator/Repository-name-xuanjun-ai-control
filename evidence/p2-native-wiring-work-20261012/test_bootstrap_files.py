import importlib.util,json,os,pathlib,shutil,sys,tempfile,unittest,subprocess
from unittest.mock import patch
ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT']);sys.path.insert(0,str(ROOT/'stage1'))
spec=importlib.util.spec_from_file_location('bootstrap_test_module',os.environ.get('P2_BOOTSTRAP_MODULE',str(ROOT/'stage1/p2_bootstrap_files.py')))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Bootstrap(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.temp.name);self.tx=self.base/'transaction';self.tx.mkdir(mode=0o700)
  self.parent=self.base/'targets';self.parent.mkdir(mode=0o700);self.sources=self.base/'private-bootstrap';self.sources.mkdir(mode=0o700)
  uk=os.environ.get('P2_BOOTSTRAP_UK_IDS')=='1'
  self.targets={str(self.parent/('file-'+str(i))):((1004,1006,0o600) if i<5 else (1003,1003,0o600) if i==5 else (0,0,0o644)) if uk else (os.getuid(),os.getgid(),0o600) for i in range(7)}
  if uk:os.chmod(self.base,0o711);os.chmod(self.parent,0o755)
  self.mapping=patch.dict(m.TARGETS,self.targets,clear=True);self.mapping.start()
  self.files=[]
  for i,target in enumerate(self.targets):
   data=('SYNTHETIC_'+str(i)+'\n').encode();source=self.sources/str(i);source.write_bytes(data);source.chmod(0o600)
   uid,gid,mode=self.targets[target]
   self.files.append({'source':str(source),'sha256':m.hash_bytes(data),'target':target,'owner_uid':uid,'group_gid':gid,'mode':mode,'applied':False,'requires_approved_bootstrap':True})
  self.boot=self.base/'receipt.json';self.boot.write_text(json.dumps({'files':self.files}));self.boot.chmod(0o600)
  self.ref={'path':'/var/lib/xuanjun-p2-preparation/fixture/receipt.json','sha256':m.hash_bytes(self.boot.read_bytes())}
  self.real_read=m.private_read
  def read(path):
   if path==self.ref['path']:return self.boot.read_bytes()
   return self.real_read(path)
  self.reader=patch.object(m,'private_read',side_effect=read);self.reader.start()
  self.bp=m.BootstrapFiles(str(self.tx))
  if os.getuid()!=0:self.skipTest('Root syscall cases require root; hosted CI invokes this suite with sudo')
  self.original_prepare=self.bp.prepare
  self.bp.prepare=lambda ref,release:[dict(item,data=self.real_read(item['source'])) for item in self.files]
 def tearDown(self):
  self.mapping.stop()
  try:self.reader.stop()
  except RuntimeError:pass
  self.temp.cleanup()
 def test_apply_rollback_replay(self):
  self.bp.apply(self.ref,'integration-'+'a'*16);self.assertEqual(len(list(self.parent.iterdir())),7)
  self.bp.rollback();self.bp.rollback();self.assertEqual(list(self.parent.iterdir()),[])
 def test_changed_target_holds_all(self):
  self.bp.apply(self.ref,'integration-'+'a'*16);pathlib.Path(next(iter(self.targets))).write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'HOLD_BOOTSTRAP_TARGET_CHANGED'):self.bp.rollback()
  self.assertEqual(len(list(self.parent.iterdir())),7)
 def test_replaced_inode_holds_all(self):
  self.bp.apply(self.ref,'integration-'+'a'*16);path=pathlib.Path(next(iter(self.targets)));data=path.read_bytes();path.unlink();path.write_bytes(data)
  with self.assertRaisesRegex(ValueError,'HOLD_BOOTSTRAP_TARGET_CHANGED'):self.bp.rollback()
 def test_crash_between_link_and_ack(self):
  link=os.link
  def crash(*args,**kw):link(*args,**kw);raise RuntimeError('INJECTED')
  with patch.object(m.os,'link',side_effect=crash):
   with self.assertRaises(RuntimeError):self.bp.apply(self.ref,'integration-'+'a'*16)
  m.BootstrapFiles(str(self.tx)).rollback();self.assertEqual(list(self.parent.iterdir()),[])
 def test_missing_reference_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'BOOTSTRAP_EXACT_REFERENCE'):self.original_prepare(None,'integration-'+'a'*16)
 def test_runtime_missing_reference_is_rejected(self):
  import p2_fixed_host_runtime as runtime
  host=runtime.FixedHostRuntime(str(self.tx));host._authority=lambda:None;host.prerequisites.preflight=lambda plan:None
  with self.assertRaisesRegex(ValueError,'BOOTSTRAP_EXACT_REFERENCE'):
   host.preflight({'services':list(runtime.ALLOWED_SERVICES),'prerequisites':{},'release_directory':'integration-'+'a'*16},{},{})
 def test_extra_hardlink_blocks_rollback(self):
  self.bp.apply(self.ref,'integration-'+'a'*16);path=next(iter(self.targets));os.link(path,str(self.base/'untracked-link'))
  with self.assertRaisesRegex(ValueError,'HOLD_BOOTSTRAP_TARGET_CHANGED'):self.bp.rollback()
  self.assertEqual(len(list(self.parent.iterdir())),7)
 def test_numeric_actor_secret_access(self):
  if os.environ.get('P2_BOOTSTRAP_UK_IDS')!='1':self.skipTest('Real numeric UID access is tested on UK')
  self.bp.apply(self.ref,'integration-'+'a'*16);target=next(iter(self.targets))
  code="import os,sys;u=int(sys.argv[1]);os.setgroups([]);os.setgid(u);os.setuid(u);\ntry:\n f=open(sys.argv[2],'rb');f.close();print('ALLOWED')\nexcept PermissionError:print('DENIED')"
  for uid,expected in [(1004,'ALLOWED'),(1002,'DENIED'),(1005,'DENIED')]:
   p=subprocess.run(['/usr/bin/python3','-I','-B','-c',code,str(uid),target],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5)
   self.assertEqual(p.returncode,0);self.assertEqual(p.stdout.decode().strip(),expected)
if __name__=='__main__':unittest.main(verbosity=2)
