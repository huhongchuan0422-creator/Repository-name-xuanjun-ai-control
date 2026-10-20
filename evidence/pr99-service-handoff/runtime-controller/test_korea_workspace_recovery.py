import ast,json,unittest
from pathlib import Path
import korea_workspace_recovery as r
class WorkspaceRecoveryTests(unittest.TestCase):
 def test_remote_program_and_doctor_launcher_compile(self):
  compile(r.TARGET,'target','exec')
  tree=ast.parse(r.TARGET)
  launcher=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='launcher' for t in n.targets))
  compile(launcher,'doctor-launcher','exec')
  self.assertIn("a[:i+1]+['doctor','--fix']",launcher)
  self.assertIn("'/srv/pr99-doctor.log'",launcher)
 def clone(self,text):
  tree=ast.parse(r.TARGET);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='doctor_unit_text')
  def need(ok,reason):
   if not ok:raise RuntimeError(reason)
  env={'need':need};exec(compile(ast.Module(body=[fn],type_ignores=[]),'clone','exec'),env)
  return env['doctor_unit_text'](text,Path('/private/doctor.py'),Path('/private/doctor.log'))
 def test_preserve_mounts_and_disable_restart_for_single_doctor(self):
  old='[Unit]\nRequires=pr99-korea-gateway-tunnel.service\n[Service]\nType=simple\nRestart=on-failure\nUser=admin\nProtectHome=tmpfs\nProtectSystem=strict\nBindPaths=/private/state:/home/admin/.openclaw\nBindReadOnlyPaths=/private/node:/opt/node-v24.16.0-linux-x64\nExecStart=/bin/python3.11 -I -B -S /srv/pr99-model-launcher.py gateway\n[Install]\nWantedBy=multi-user.target\n'
  new=self.clone(old)
  for value in ('User=admin','ProtectHome=tmpfs','ProtectSystem=strict','BindPaths=/private/state:/home/admin/.openclaw','BindReadOnlyPaths=/private/node:/opt/node-v24.16.0-linux-x64','Type=oneshot','Restart=no','StandardInput=null','TimeoutStartSec=300'):
   self.assertIn(value,new)
  self.assertNotIn('[Install]',new);self.assertNotIn('Restart=on-failure',new)
  self.assertEqual(sum(x.startswith('ExecStart=') for x in new.splitlines()),1)
 def test_changed_entry_refused(self):
  with self.assertRaisesRegex(RuntimeError,'GATEWAY_EXEC_CHANGED'):
   self.clone('[Service]\nExecStart=/bin/sh -c arbitrary\n')
 def test_original_unknown_not_removed_and_no_source_resume(self):
  source=Path(r.__file__).read_text()
  self.assertNotIn('.unlink(',source)
  self.assertNotIn("'unmask'",source)
  self.assertIn("'original_start_unknown_preserved':True",source)

class SourceStoppedStateTests(unittest.TestCase):
 def test_failed_empty_masked_service_is_stopped(self):
  self.assertTrue(r.gateway_is_stopped({'ActiveState':'failed','MainPID':'0'},False,True))
  self.assertTrue(r.gateway_is_stopped({'ActiveState':'inactive','MainPID':'0'},False,True))
 def test_live_children_or_missing_mask_still_refused(self):
  for state,children,masked in [({'ActiveState':'active','MainPID':'10'},False,True),({'ActiveState':'failed','MainPID':'0'},True,True),({'ActiveState':'failed','MainPID':'0'},False,False)]:
   self.assertFalse(r.gateway_is_stopped(state,children,masked))
