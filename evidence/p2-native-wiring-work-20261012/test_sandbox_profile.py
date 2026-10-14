import copy,json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'))
import p2_sandbox_profile as m
class Profile(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.tx=self.root/'tx';self.tx.mkdir(mode=0o700)
  self.profile=self.root/'openclaw.json';self.source=self.root/'candidate.json'
  self.old={'agents':{'entries':{'developer':{'model':'unchanged'},'platform-engineer':{}}},'credentials':{'reference':'SYNTHETIC_ONLY'}}
  self.new=copy.deepcopy(self.old)
  for name,access in (('developer','rw'),('platform-engineer','ro')):
   self.new['agents']['entries'][name]['sandbox']={'mode':'all','scope':'agent','workspaceAccess':access,'docker':{'image':m.IMAGE,'user':'1002:1002','network':'none','readOnlyRoot':True,'capDrop':['ALL'],'binds':[],'tmpfs':[]}}
  self.before=json.dumps(self.old).encode();self.after=json.dumps(self.new).encode()
  self.profile.write_bytes(self.before);self.profile.chmod(0o600);self.source.write_bytes(self.after);self.source.chmod(0o600)
  self.patches=[patch.object(m,'PROFILE',str(self.profile)),patch.object(m,'IDENTITY',(os.getuid(),os.getgid(),0o600))]
  for p in self.patches:p.start()
  self.ref={'path':'/var/lib/xuanjun-p2-preparation/synthetic/candidate.json','sha256':m.hash_bytes(self.after),'original_sha256':m.hash_bytes(self.before)}
  reader=m.private_read
  self.reader=patch.object(m,'private_read',side_effect=lambda p:self.source.read_bytes() if p==self.ref['path'] else reader(p));self.reader.start()
  self.obj=m.SandboxProfile(str(self.tx))
 def tearDown(self):
  self.reader.stop()
  for p in self.patches:p.stop()
  self.temp.cleanup()
 def test_apply_restore_exact_bytes_replay(self):
  self.obj.apply(self.ref);self.assertEqual(self.profile.read_bytes(),self.after)
  self.obj.rollback();self.obj.rollback();self.assertEqual(self.profile.read_bytes(),self.before)
 def test_unknown_change_holds_without_overwrite(self):
  self.obj.apply(self.ref);self.profile.write_bytes(b'{"unknown":true}')
  with self.assertRaisesRegex(ValueError,'HOLD_PROFILE_CHANGED'):self.obj.rollback()
  self.assertEqual(self.profile.read_bytes(),b'{"unknown":true}')
 def test_capture_plugin_changes_then_restore(self):
  self.obj.apply(self.ref);value=copy.deepcopy(self.new)
  value['plugins']={'entries':{m.PLUGIN:{'enabled':True}},'allow':[m.PLUGIN]};value['meta']={'lastTouchedAt':'synthetic'}
  self.profile.write_text(json.dumps(value));self.obj.capture();self.obj.rollback();self.assertEqual(self.profile.read_bytes(),self.before)
 def test_capture_foreign_plugin_denied(self):
  self.obj.apply(self.ref);value=copy.deepcopy(self.new);value['plugins']={'entries':{'foreign':{'enabled':True}}};self.profile.write_text(json.dumps(value))
  with self.assertRaisesRegex(ValueError,'UNEXPECTED_CONFIG_CHANGE'):self.obj.capture()
 def test_model_change_denied(self):
  changed=copy.deepcopy(self.new);changed['agents']['entries']['developer']['model']='changed'
  with self.assertRaisesRegex(ValueError,'POLICY_SCOPE'):m.policy(self.old,changed)
 def test_policy_escape_denied(self):
  changed=copy.deepcopy(self.new);changed['agents']['entries']['developer']['sandbox']['docker']['network']='host'
  with self.assertRaisesRegex(ValueError,'POLICY_SCOPE'):m.policy(self.old,changed)
 def test_duplicate_key_denied(self):
  with self.assertRaisesRegex(ValueError,'DUPLICATE_KEY'):m.decode(b'{"agents":{},"agents":{}}')
 def test_preflight_stale_original_denied(self):
  self.profile.write_text(json.dumps({'different':True}))
  with self.assertRaisesRegex(ValueError,'REFERENCE_HASH'):self.obj.prepare(self.ref)
 def test_hardlink_denied(self):
  self.obj.apply(self.ref);os.link(str(self.profile),str(self.root/'extra'))
  with self.assertRaisesRegex(ValueError,'PROFILE_IDENTITY'):self.obj.rollback()
 def test_apply_intent_crash_restores(self):
  with patch.object(m,'publish',side_effect=RuntimeError('synthetic crash')):
   with self.assertRaises(RuntimeError):self.obj.apply(self.ref)
  self.obj.rollback();self.assertEqual(self.profile.read_bytes(),self.before)
if __name__=='__main__':unittest.main()
