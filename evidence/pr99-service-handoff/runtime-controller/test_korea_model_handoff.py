import ast,hashlib,io,json,os,socket,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import korea_model_handoff as m

class HandoffTests(unittest.TestCase):
 def stub(self):
  source=Path(m.__file__).read_text();return source.split('\n# TARGET_PROGRAM_BEGIN\n',1)[1].split('\n# TARGET_PROGRAM_END\n',1)[0]
 def test_exact_remote_program_compiles(self):compile(self.stub(),'remote','exec')
 def test_launcher_compiles_and_execs_only_declared_roles(self):
  tree=ast.parse(self.stub());launcher=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='LAUNCHER' for t in n.targets))
  compile(launcher,'launcher','exec');self.assertIn("('gateway','tunnel','gateway_tunnel','bridge_tunnel')",launcher)
 def test_gateway_fixed_version_entry_and_no_shell_expansion(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'gateway.service';p.write_text('ExecStart=/opt/node-v24.16.0-linux-x64/bin/node /opt/node-v24.16.0-linux-x64/lib/node_modules/openclaw/dist/index.js gateway --port 11505\n')
   self.assertEqual(m.gateway_argv(p,{} )[-1],'11505')
   p.write_text('ExecStart=/bin/sh -c anything\n')
   with self.assertRaises(RuntimeError):m.gateway_argv(p,{})
 def test_capture_hashes_files_and_keeps_internal_links(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'tree';root.mkdir();(root/'file').write_bytes(b'content');(root/'link').symlink_to('file');out=io.BytesIO();manifest={}
   with tarfile.open(fileobj=out,mode='w:') as t:m.archive_tree(t,root,manifest,[root])
   self.assertEqual(manifest[str(root/'file').lstrip('/')]['sha256'],hashlib.sha256(b'content').hexdigest())
   self.assertEqual(manifest[str(root/'link').lstrip('/')]['target'],'file')
 def test_capture_refuses_external_link(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'tree';root.mkdir();(root/'link').symlink_to('/etc/shadow')
   with tarfile.open(fileobj=io.BytesIO(),mode='w:') as t:
    with self.assertRaisesRegex(RuntimeError,'EXTERNAL_LINK'):m.archive_tree(t,root,{},[root])
 def test_runtime_sockets_are_not_archived_as_data(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'tree';root.mkdir();
   try:sock=socket.socket(socket.AF_UNIX)
   except PermissionError:self.skipTest('native Unix sockets unavailable in this test runtime')
   sock.bind(str(root/'socket'))
   try:
    manifest={}
    with tarfile.open(fileobj=io.BytesIO(),mode='w:') as t:m.archive_tree(t,root,manifest,[root])
    self.assertEqual(manifest[str(root/'socket').lstrip('/')]['kind'],'ephemeral_socket_not_copied')
   finally:sock.close()
 def test_generated_units_keep_programs_readonly_and_runtime_private(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);units=root/'units';units.mkdir()
   tree=ast.parse(self.stub())
   selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('install_unit','write')]
   def paths(value):return units if value=='/etc/systemd/system' else Path(value)
   namespace={'Path':paths,'ROOT':root/'release','BASELINE':root/'old','NAMES':m.NAMES,'need':m.require,'os':os}
   exec(compile(ast.Module(body=selected,type_ignores=[]),'unit-functions','exec'),namespace)
   old=os.umask(0o077)
   try:
    for role in m.NAMES:namespace['install_unit'](role,{'ssh_files':['known_hosts','model_key']})
   finally:os.umask(old)
   rpc=(units/m.NAMES['rpc']).read_text()
   self.assertIn('BindReadOnlyPaths='+str(root/'release/app')+':/opt/trading-system',rpc)
   self.assertIn('BindPaths='+str(root/'release/app/runtime')+':/opt/trading-system/runtime',rpc)
   self.assertIn('ProtectHome=tmpfs',rpc);self.assertIn('Slice=pr99koreamodel.slice',rpc)
   self.assertIn('Requires='+m.NAMES['gateway'],rpc)
   self.assertEqual((units/m.NAMES['rpc']).stat().st_mode&0o777,0o644)
   with self.assertRaisesRegex(RuntimeError,'UNIT_CONFLICT'):namespace['install_unit']('rpc',{'ssh_files':[]})
 def remote_receive(self,malicious=False):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'release';lock=Path(d)/'lock';blob=b'data';member='rootfs/opt/node-v24.16.0-linux-x64/file'
   manifest={'opt/node-v24.16.0-linux-x64/file':{'kind':'file','bytes':4,'sha256':hashlib.sha256(blob).hexdigest(),'mode':0o600}}
   output=io.BytesIO()
   with tarfile.open(fileobj=output,mode='w:gz') as t:
    for name,body in [('manifest.json',json.dumps(manifest).encode()),(member,blob)]:
     n=tarfile.TarInfo(name);n.size=len(body);n.mode=0o600;t.addfile(n,io.BytesIO(body))
    if malicious:
     n=tarfile.TarInfo('../escape');n.size=1;t.addfile(n,io.BytesIO(b'x'))
   data=output.getvalue();payload={'action':'receive','payload':{'segment':'static','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}}
   code=self.stub().replace('os.chown(dest,1000,1000)','None').replace('os.chown(p,1000,1000)','None').replace("os.uname().nodename.split('.')[0]==TARGET",'True')
   code=code.replace("ROOT=Path('/opt/xuanjun-migration-s07/releases/korea-model-handoff-v1')",'ROOT=Path('+repr(str(root))+')')
   code=code.replace("'/root/pr99-korea-project-install.lock'",repr(str(lock)))
   # Replace just external inventory reads; extraction and disk I/O are real.
   a=code.index('listed=cmd(');b=code.index("need(action in",a);code=code[:a]+code[b:]
   a=code.index('def states(');b=code.index('\ndef write(',a);code=code[:a]+"def states(units):return {}\n"+code[b:]
   r=subprocess.run([sys.executable,'-I','-B','-S','-c',code,json.dumps(payload)],input=data,capture_output=True)
   if malicious:
    self.assertNotEqual(r.returncode,0);self.assertFalse((Path(d)/'escape').exists());self.assertFalse((root/'received-static.json').exists())
   else:
    self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'PASS');self.assertEqual((root/member).read_bytes(),blob)
    # Same receive is rejected; a completed segment is not overwritten.
    again=subprocess.run([sys.executable,'-I','-B','-S','-c',code,json.dumps(payload)],input=data,capture_output=True)
    self.assertNotEqual(again.returncode,0);self.assertEqual((root/member).read_bytes(),blob)
 def test_actual_receive_and_duplicate_preservation(self):self.remote_receive()
 def test_actual_receiver_rejects_traversal(self):self.remote_receive(malicious=True)
 def test_checkpoint_does_not_repeat_uncertain_mutation(self):
  with tempfile.TemporaryDirectory() as d:
   j=m.Checkpoint(d);calls=[]
   def fail():calls.append(1);raise RuntimeError('interrupted')
   with self.assertRaises(RuntimeError):j.perform('switch',fail)
   with self.assertRaises(RuntimeError):j.perform('switch',lambda:calls.append(2))
   self.assertEqual(calls,[1]);self.assertTrue((Path(d)/'switch.intent.json').is_file());self.assertFalse((Path(d)/'switch.result.json').exists())

if __name__=='__main__':unittest.main()

class ShimHealthRouteTests(unittest.TestCase):
 def test_literal_and_constant_routes_bind_without_executing_module(self):
  tree=ast.parse(Path(m.__file__).read_text())
  main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  block=main.body[-1].body
  start=next(i for i,n in enumerate(block) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='constants' for t in n.targets))
  code=compile(ast.Module(body=block[start:start+3],type_ignores=[]),'health-discovery','exec')
  for source,expected in [("HEALTHZ_PATH='/healthz'\nclass Handler:\n def do_GET(self):\n  return self.path == HEALTHZ_PATH",{'/healthz'}),("def do_GET(self):\n return self.path == '/health'",{'/health'}),("DANGEROUS=__import__('os').system('false')\ndef do_GET(self):\n return None",set())]:
   env={'ast':ast,'shim_tree':ast.parse(source)};exec(code,env);self.assertEqual(env['health_paths'],expected)

class GatewayHeapFlagTests(unittest.TestCase):
 def test_preserve_actual_heap_flag_and_reject_other_entries(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'gateway.service'
   prefix='/opt/node-v24.16.0-linux-x64/'
   for flag in ('','--max-old-space-size=1536 '):
    p.write_text('ExecStart='+prefix+'bin/node '+flag+prefix+'lib/node_modules/openclaw/dist/index.js gateway --port 11505\n')
    argv=m.gateway_argv(p,{})
    self.assertEqual('--max-old-space-size=1536' in argv,bool(flag))
   for flag in ('--require=/tmp/other.js ','--max-old-space-size=abc '):
    p.write_text('ExecStart='+prefix+'bin/node '+flag+prefix+'lib/node_modules/openclaw/dist/index.js gateway --port 11505\n')
    with self.assertRaises(RuntimeError):m.gateway_argv(p,{})

class AutomaticSliceTests(unittest.TestCase):
 def test_only_empty_automatic_inactive_slice_is_reusable(self):
  stub=Path(m.__file__).read_text().split('\n# TARGET_PROGRAM_BEGIN\n',1)[1].split('\n# TARGET_PROGRAM_END\n',1)[0]
  fn=next(n for n in ast.parse(stub).body if isinstance(n,ast.FunctionDef) and n.name=='validate_initial_slice')
  env={'need':m.require};exec(compile(ast.Module(body=[fn],type_ignores=[]),'slice-check','exec'),env)
  base={'LoadState':'loaded','ActiveState':'inactive','FragmentPath':'','DropInPaths':''}
  env['validate_initial_slice'](base,False)
  for change in ({'ActiveState':'active'},{'FragmentPath':'/etc/systemd/system/pr99koreamodel.slice'},{'DropInPaths':'/run/systemd/system/pr99koreamodel.slice.d/other.conf'},{'LoadState':'masked'}):
   with self.assertRaises(RuntimeError):env['validate_initial_slice'](dict(base,**change),False)
  with self.assertRaises(RuntimeError):env['validate_initial_slice'](base,True)

class AuthorizedDrainTests(unittest.TestCase):
 def test_no_authorization_never_signals(self):
  with patch.object(sys,'argv',['controller']),patch.object(m.signal,'pidfd_send_signal') as send:
   with self.assertRaisesRegex(RuntimeError,'OWNER_TASK_DRAIN_AUTHORIZATION_REQUIRED'):m.drain_gateway_tasks(123)
   send.assert_not_called()
 def test_pid_identity_change_never_signals_replacement(self):
  item={'pid':999,'start':'old','exe':'/bin/node'}
  with patch.object(sys,'argv',['controller','--owner-drain-gateway-tasks']),patch.object(m,'gateway_tasks',side_effect=[[item],[],[],[]]),patch.object(m.time,'sleep'),patch.object(m.signal,'pidfd_send_signal') as send:
   self.assertEqual(m.drain_gateway_tasks(123)['status'],'PASS');send.assert_not_called()
 def test_repeated_new_tasks_drain_in_same_controller(self):
  item={'pid':999,'start':'old','exe':'/bin/node'}
  sequence=[[item],[item],[item],[item],[item],[]]
  with patch.object(sys,'argv',['controller','--owner-drain-gateway-tasks']),patch.object(m,'gateway_tasks',side_effect=sequence),patch.object(m.os,'pidfd_open',return_value=45),patch.object(m.os,'close'),patch.object(m.time,'sleep'),patch.object(m.signal,'pidfd_send_signal') as send:
   self.assertEqual(m.drain_gateway_tasks(123)['status'],'PASS');self.assertEqual(send.call_count,2)
