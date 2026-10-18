"""Mock-only orchestration; no host target path or vendor code is accessed."""
import ast,copy,hashlib,importlib.util,json, pathlib,types,unittest
from unittest.mock import patch,Mock
P=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runtime_candidate',P/'scripts/pr122_customer_runtime.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RuntimeTests(unittest.TestCase):
 def test_existing_build_still_refuses_root(self):
  with patch.object(m.os,'geteuid',return_value=0),self.assertRaises(m.Denied):m.build('unused','unused')
 def test_members_reject_escape(self):
  for s in ('','../x','/x','a//b','a/./b','a\\b','a\x00b'):
   with self.subTest(s=s),self.assertRaises(m.Denied):m._relative_runtime_path(s)
 def test_member_normal(self):self.assertEqual(str(m._relative_runtime_path('cryptography/x.py')),'cryptography/x.py')
 def contract(self):
  return {'account_uid':2001,'account_gid':2001,'schema':1,'host':m.FIXED_HOST,'source_commit':'a'*40,'runtime_module_sha256':m.digest(b'module'),
   'wheel_directory':'/approved/wheels','interpreter_sha256':m.INTERPRETER_SHA256,
   'stdlib_trees':{'/usr/lib/python3.11':{'x':'b'*64}},'native_files':{'/usr/lib/libc.so.6':'c'*64},
   'abi':{'python':'3.11','machine':'x86_64','glibc_min':'2.34'},
   'expected_venv_tree':{'venv/bin/python':{'kind':'file','mode':0o755,'sha256':m.INTERPRETER_SHA256},
    'venv/pyvenv.cfg':{'kind':'file','mode':0o644,'sha256':m.digest(b'include-system-site-packages = false')}}}
 def fixture(self,contract=None):
  import contextlib
  stack=contextlib.ExitStack();self.addCleanup(stack.close)
  for name in ('getuid','geteuid','getgid','getegid'):stack.enter_context(patch.object(m.os,name,return_value=0))
  stack.enter_context(patch.object(m.os,'uname',return_value=types.SimpleNamespace(nodename=m.FIXED_HOST,machine='x86_64')))
  import pwd,grp
  stack.enter_context(patch.object(pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=2001,pw_gid=2001,pw_dir='/nonexistent',pw_shell='/usr/sbin/nologin',pw_name='xuanjun-customer')))
  stack.enter_context(patch.object(grp,'getgrnam',return_value=types.SimpleNamespace(gr_gid=2001)))
  stack.enter_context(patch.object(grp,'getgrall',return_value=[]))
  stack.enter_context(patch.object(m,'_root_chain'))
  stack.enter_context(patch.object(m.os.path,'lexists',return_value=False))
  stack.enter_context(patch.object(m,'_source_identity',return_value='sourceclosure'))
  stack.enter_context(patch.object(m,'WHEELS',{}));stack.enter_context(patch.object(m,'wheel_files',return_value={}))
  stack.enter_context(patch.object(m,'_protected_bytes',side_effect=lambda p,*a:b'include-system-site-packages = false' if str(p).endswith('pyvenv.cfg') else b'module'))
  c=contract or self.contract();tree=stack.enter_context(patch.object(m,'_runtime_tree',return_value=c['expected_venv_tree']))
  mkdir=stack.enter_context(patch.object(m.Path,'mkdir'));stack.enter_context(patch.object(m,'_sync_runtime'))
  stack.enter_context(patch.object(m.os,'umask',return_value=0o022))
  stack.enter_context(patch.object(m,'_durable_runtime'))
  stack.enter_context(patch.object(m.os,'lstat',return_value=types.SimpleNamespace(st_dev=1,st_ino=2,st_uid=0,st_gid=0,st_mode=0o40755)))
  versions={'cryptography':'46.0.3','cffi':'2.0.0','pycparser':'2.23','aes_gcm':'PASS','ed25519':'PASS'}
  run=stack.enter_context(patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(stdout=json.dumps(versions),stderr='')))
  self.verify=stack.enter_context(patch.object(m,'_bounded_runtime_verify',return_value=versions))
  co=Mock(spec=['authorize_runtime','assert_locked','record_runtime']);return c,co,run,mkdir,tree
 def test_mock_success_real_order_and_nonroot_verify(self):
  c,co,run,mkdir,tree=self.fixture();report=m.protected_rebuild(c,co)
  self.assertEqual(report['state'],'PROTECTED_RUNTIME_REBUILT_VERIFIED');self.assertEqual(run.call_count,1)
  self.assertEqual(self.verify.call_args.args[1:3],(2001,2001));self.assertFalse(report['service_started'])
  self.assertIn('-S',run.call_args.args[0]);self.assertEqual(run.call_args.kwargs['stdout'],m.subprocess.DEVNULL)
  self.assertEqual([x.args[0] for x in co.record_runtime.call_args_list],['RUNTIME_CREATE_INTENT','RUNTIME_VERIFIED'])
  self.assertEqual(mkdir.call_count,1)
 def test_authority_denial_before_write(self):
  c,co,run,mkdir,tree=self.fixture();co.authorize_runtime.side_effect=m.Denied('AUTH')
  with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  mkdir.assert_not_called();run.assert_not_called();co.record_runtime.assert_not_called()
 def test_missing_lock_before_write(self):
  c,co,run,mkdir,tree=self.fixture();co.assert_locked.side_effect=m.Denied('LOCK')
  with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  mkdir.assert_not_called();run.assert_not_called()
 def test_existing_target_preserved(self):
  c,co,run,mkdir,tree=self.fixture()
  with patch.object(m.os.path,'lexists',return_value=True),self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  mkdir.assert_not_called();run.assert_not_called()
 def test_module_drift_blocks(self):
  c,co,run,mkdir,tree=self.fixture();c['runtime_module_sha256']='f'*64
  with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  mkdir.assert_not_called()
 def test_missing_source_closure_blocks(self):
  c,co,run,mkdir,tree=self.fixture()
  with patch.object(m,'_source_identity',side_effect=m.Denied('CLOSURE')),self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  mkdir.assert_not_called();run.assert_not_called()
 def test_invalid_schema_blocks(self):
  for value in (True,2,'1'):
   c,co,run,mkdir,tree=self.fixture();c['schema']=value
   with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
   run.assert_not_called();co.authorize_runtime.assert_not_called()
 def test_account_identity_must_match_original_checkpoint(self):
  for key,value in [('account_uid',2002),('account_gid',2002),('account_uid',True)]:
   c,co,run,mkdir,tree=self.fixture();c[key]=value
   with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
   mkdir.assert_not_called();run.assert_not_called()
 def test_account_drift_before_nonroot_verify_stops(self):
  c,co,run,mkdir,tree=self.fixture()
  import pwd
  a=types.SimpleNamespace(pw_uid=2001,pw_gid=2001,pw_dir='/nonexistent',pw_shell='/usr/sbin/nologin',pw_name='xuanjun-customer')
  b=types.SimpleNamespace(pw_uid=2002,pw_gid=2001,pw_dir='/nonexistent',pw_shell='/usr/sbin/nologin',pw_name='xuanjun-customer')
  with patch.object(pwd,'getpwnam',side_effect=[a,b]),self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  self.verify.assert_not_called();self.assertEqual(co.record_runtime.call_args.args[0],'RUNTIME_UNKNOWN_PRESERVE')
 def test_bad_generated_tree_preserves(self):
  c,co,run,mkdir,tree=self.fixture();tree.return_value={}
  with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  self.assertEqual(run.call_count,1);self.assertEqual(co.record_runtime.call_args.args[0],'RUNTIME_UNKNOWN_PRESERVE')
 def test_vendor_exception_preserves(self):
  c,co,run,mkdir,tree=self.fixture();run.side_effect=RuntimeError('not emitted raw')
  with self.assertRaises(RuntimeError):m.protected_rebuild(c,co)
  self.assertEqual(co.record_runtime.call_args.args,('RUNTIME_UNKNOWN_PRESERVE',{'retry_allowed':False}))
 def test_nonroot_verify_failure_preserves(self):
  c,co,run,mkdir,tree=self.fixture();self.verify.side_effect=RuntimeError('failure')
  with self.assertRaises(RuntimeError):m.protected_rebuild(c,co)
  self.assertEqual(co.record_runtime.call_args.args[0],'RUNTIME_UNKNOWN_PRESERVE')
 def test_lease_lost_after_intent_blocks_first_runtime_mutation(self):
  c,co,run,mkdir,tree=self.fixture()
  def recorded(phase,metadata):
   if phase=='RUNTIME_CREATE_INTENT':co.assert_locked.side_effect=m.Denied('HOLD:WORKFLOW_FENCE_LOST')
  co.record_runtime.side_effect=recorded
  with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
  mkdir.assert_not_called();run.assert_not_called()
 def test_lease_lost_after_venv_blocks_vendor_write(self):
  c,co,run,mkdir,tree=self.fixture()
  def invoked(*a,**kw):
   co.assert_locked.side_effect=m.Denied('HOLD:WORKFLOW_LEASE_EXPIRED')
   return types.SimpleNamespace(returncode=0)
  run.side_effect=invoked
  with patch.object(m,'wheel_files',return_value={'pkg/x.py':b'x'}),patch.object(m,'_create_runtime_member') as write:
   with self.assertRaises(m.Denied):m.protected_rebuild(c,co)
   write.assert_not_called()
 def test_no_new_cli_or_cleanup(self):
  tree=ast.parse((P/'scripts/pr122_customer_runtime.py').read_text())
  calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
  self.assertFalse(calls & {'unlink','remove','rmtree','rmdir','rename','replace','connect','urlopen'})
if __name__=='__main__':unittest.main()
