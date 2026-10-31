import unittest
from unittest.mock import patch
import test_community_admin_authority as fixture
from scripts.community_admin_authority import CommunityAdminAuthority, full_community_capabilities
from scripts.community_admin_policy import policy_intent,adopt_policy
from scripts.pr122_customer_core import Denied,Conflict
class Policy(fixture.Tests):
 def setUp(self):
  super().setUp()
  self.api=CommunityAdminAuthority(self.c,'p','t',full_community_capabilities(),(),'a'*64)
  with self.c.tx():self.api._write(dict(uid='root',project='p',tenant='t',kind='ROOT',revision=1,parent=None,parent_revision=None,capabilities=sorted(self.api.capabilities),workspace_scopes=[],scope_binding_sha=self.api.scope_binding_sha,manifest_sha=self.api.manifest_sha,request_id='fixture'),True)
  self.api.delegate(self.r['token'],self.r['csrf'],'child',['/community/operations#community.orders'],'child-first',0)
  self.next=CommunityAdminAuthority(self.c,'p','t',full_community_capabilities(),('/community/operations#store1',),'b'*64)
  self.intent=policy_intent(self.next,'migration1')
 def test_policy_root_child_revoke_explicit_regrant(self):
  pw=self.c.db.execute("SELECT password FROM accounts WHERE id='root'").fetchone()[0]
  result=adopt_policy(self.next,self.intent,'c'*64,lambda x:x==self.intent)
  self.assertEqual(result['revision'],2);self.assertFalse(result['children_auto_expanded'])
  self.assertEqual(self.c.db.execute("SELECT password FROM accounts WHERE id='root'").fetchone()[0],pw)
  with self.assertRaises(Denied):self.c.session(self.r['token'],self.r['csrf'])
  with self.assertRaises(Denied):self.next.authority('child')
  r=self.c.login('root@test.invalid','synthetic-password')
  self.next.delegate(r['token'],r['csrf'],'child',['/community/operations#community.orders'],'child-regrant',1,workspace_scopes=['/community/operations#store1'])
  self.assertEqual(self.next.authority('child')['workspace_scopes'],['/community/operations#store1'])
 def test_policy_idempotence(self):
  a=adopt_policy(self.next,self.intent,'c'*64,lambda x:True);b=adopt_policy(self.next,self.intent,'c'*64,lambda x:True)
  self.assertEqual(a['revision'],b['revision']);self.assertTrue(b['replayed'])
  with self.assertRaises(Conflict):adopt_policy(self.next,self.intent,'d'*64,lambda x:True)
 def test_policy_denied_confirmation(self):
  with self.assertRaises(Denied):adopt_policy(self.next,self.intent,'c'*64,lambda x:False)
  self.assertEqual(self.api.authority('root')['revision'],1)
 def test_policy_stale_children(self):
  self.api.revoke(self.r['token'],self.r['csrf'],'child',1)
  with self.assertRaises(Conflict):adopt_policy(self.next,self.intent,'c'*64,lambda x:True)
 def test_policy_atomic(self):
  with patch.object(self.c,'audit',side_effect=RuntimeError('synthetic')):
   with self.assertRaises(RuntimeError):adopt_policy(self.next,self.intent,'c'*64,lambda x:True)
  self.assertEqual(self.api.authority('root')['revision'],1);self.api.authority('child');self.c.session(self.r['token'],self.r['csrf'])
 def test_policy_cross_tenant(self):
  other=CommunityAdminAuthority(self.c,'p','other',full_community_capabilities(),('/community/operations#store1',),'b'*64)
  with self.assertRaises(Denied):adopt_policy(other,self.intent,'c'*64,lambda x:True)
 def test_policy_full_inventory(self):
  other=CommunityAdminAuthority(self.c,'p','t',('/community/admin#list',),(),'b'*64)
  with self.assertRaises(Denied):policy_intent(other,'changed')
class OriginalHostPolicy(unittest.TestCase):
 def test_core_root_to_explicit_business_policy_and_recovery(self):
  import io
  from pathlib import Path
  from contextlib import redirect_stdout
  from test_community_admin_preflight import Preflight
  from scripts.community_admin_preflight import build_plan
  from scripts.community_admin_bootstrap import run as bootstrap
  from scripts.community_admin_policy_maintenance import run
  from scripts.community_admin_authority import community_login
  x=Preflight();x.setUp();self.addCleanup(x.doCleanups)
  target=x.fx.plan.pop('community_admin_authority');x.fx.write('host.json',x.fx.plan)
  core=x.call()['plan']
  with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',side_effect=['super@test.invalid','CONFIRM super@test.invalid project1 SUPERADMIN']),patch('getpass.getpass',return_value='synthetic-secure-password'),redirect_stdout(io.StringIO()):created=bootstrap(core,'--bootstrap')
  with x.fx.open() as host:
   login=community_login(host.center,'super@test.invalid','synthetic-secure-password')
   child=host.center.community_admin_authority.create_subadmin(login['token'],login['csrf'],'sub@test.invalid','synthetic-child-password',['/community/operations#community.orders'],'sub1',[])
  x.fx.plan['community_admin_authority']=target;x.fx.write('host.json',x.fx.plan)
  plan=build_plan(str(x.fx.plan_path),str(x.fx.keys_path),str(x.fx.wechat_path),str(x.fx.root/'policy-backup.sqlite'),str(x.fx.root/'policy-intent.json'),'policy1')['plan']
  observed=run(plan,'--inspect');self.assertEqual(observed['status'],'POLICY_NOT_COMMITTED')
  confirmation='ADOPT project1 '+observed['intent']['to_manifest']+' REVOKE CHILDREN'
  def apply():
   with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',return_value=confirmation),redirect_stdout(io.StringIO()):return run(plan,'--adopt')
  with patch('scripts.community_admin_policy_maintenance.adopt_policy',side_effect=RuntimeError('synthetic power loss')):
   with self.assertRaises(RuntimeError):apply()
  self.assertEqual(run(plan,'--query')['backup_state']['phase'],'VERIFIED_BACKUP_CURRENT_UNCHANGED_NOT_COMMITTED')
  result=apply();self.assertEqual(result['status'],'POLICY_COMMITTED_READBACK');self.assertEqual(result['children_affected'],1)
  replay=run(plan,'--query');self.assertTrue(replay['replayed']);self.assertEqual(replay['revision'],result['revision'])
  with x.fx.open() as host:
   root=community_login(host.center,'super@test.invalid','synthetic-secure-password')
   self.assertEqual(host.center.community_admin_authority.authority(root['user_id'])['workspace_scopes'],target['workspace_scopes'])
   with self.assertRaises(Denied):community_login(host.center,'sub@test.invalid','synthetic-child-password')
   with self.assertRaises(Denied):host.center.session(login['token'],login['csrf'])
def load_tests(loader,tests,pattern):return unittest.TestSuite([*(Policy(name) for name in Policy.__dict__ if name.startswith('test_policy_')),loader.loadTestsFromTestCase(OriginalHostPolicy)])
if __name__=='__main__':unittest.main()
