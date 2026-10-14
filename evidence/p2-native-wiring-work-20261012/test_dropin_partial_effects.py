import ast,hashlib,os,stat,tempfile,pathlib,types,unittest
# Test the exact shipped helper AST, without importing unrelated runtime ctypes.
p=pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1/p2_fixed_host_runtime.py'
node=next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='_dropin_rollback_present')
mod=ast.parse('');mod.body=[node];ast.fix_missing_locations(mod)
class DropinTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.tmp.name);self.path=str(self.base/'dropin');self.target=str(self.base/'target')
  def read(path):
   fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
   with os.fdopen(fd,'rb') as f:return f.read(),os.fstat(f.fileno())
  self.ns={'os':os,'stat':stat,'GATEWAY_DROPIN_DIR':self.path,'_read_regular':read,'_digest_bytes':lambda b:hashlib.sha256(b).hexdigest(),'Auxiliary':types.SimpleNamespace(is_mask=lambda p:os.path.islink(p) and os.readlink(p)=='/dev/null')}
  exec(compile(mod,str(p),'exec'),self.ns);self.check=self.ns['_dropin_rollback_present']
 def tearDown(self):self.tmp.cleanup()
 def row(self,previous):return [({'target':self.target,'previous':previous},None)]
 def test_missing_intent_and_absent_targets_is_no_effect(self):self.assertFalse(self.check({'dropin_parent_created':True},self.row(None)))
 def test_missing_directory_with_written_target_holds(self):
  pathlib.Path(self.target).write_bytes(b'installed')
  with self.assertRaisesRegex(ValueError,'TARGET_EFFECT'):self.check({'dropin_parent_created':True},self.row(None))
 def test_original_file_accepted(self):
  pathlib.Path(self.target).write_bytes(b'original');os.chmod(self.target,0o600)
  old={'sha256':hashlib.sha256(b'original').hexdigest(),'mode':0o600,'uid':os.getuid(),'gid':os.getgid()}
  self.assertFalse(self.check({'dropin_parent_created':True},self.row(old)))
 def test_changed_original_file_holds(self):
  pathlib.Path(self.target).write_bytes(b'changed');os.chmod(self.target,0o600)
  old={'sha256':hashlib.sha256(b'original').hexdigest(),'mode':0o600,'uid':os.getuid(),'gid':os.getgid()}
  with self.assertRaisesRegex(ValueError,'DRIFT'):self.check({'dropin_parent_created':True},self.row(old))
 def test_missing_previous_file_holds(self):
  with self.assertRaises(FileNotFoundError):self.check({'dropin_parent_created':True},self.row({'sha256':'a'*64}))
 def test_original_mask_accepted(self):
  os.symlink('/dev/null',self.target)
  self.assertFalse(self.check({'dropin_parent_created':True},self.row({'masked':True})))
 def test_missing_mask_holds(self):
  with self.assertRaisesRegex(ValueError,'MASK_EFFECT'):self.check({'dropin_parent_created':True},self.row({'masked':True}))
 def test_existing_owned_directory_requires_removal(self):
  os.mkdir(self.path,0o755)
  self.assertTrue(self.check({'dropin_parent_created':True},[]))
 def test_existing_alias_holds(self):
  os.symlink(self.base,self.path)
  with self.assertRaises(ValueError):self.check({'dropin_parent_created':True},[])
 def test_existing_wrong_mode_holds(self):
  os.mkdir(self.path,0o700)
  with self.assertRaises(ValueError):self.check({'dropin_parent_created':True},[])
 def test_preexisting_unowned_directory_not_removed(self):self.assertFalse(self.check({'dropin_parent_created':False},[]))
 def test_no_directory_created_to_pass(self):
  self.check({'dropin_parent_created':True},[]);self.assertFalse(os.path.lexists(self.path))

if __name__=='__main__':unittest.main(verbosity=2)
