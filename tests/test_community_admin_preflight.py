"""Read-only plan from original host synthetic fixture; no server credentials."""
import os, unittest
from types import SimpleNamespace
from unittest.mock import patch
from scripts.community_admin_preflight import build_plan
from scripts.community_admin_route_inventory import BUSINESS_CAPABILITIES
from scripts.community_admin_route_gate import binding_digest
from scripts.community_platform_host import _configuration
from scripts.community_admin_authority import CommunityAdminAuthority
from scripts.pr122_customer_core import Denied
import test_community_platform_host as fixture
class Preflight(unittest.TestCase):
 def setUp(self):
  self.fx=fixture.FormalHost();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
  with self.fx.open() as host:host.center.db.execute("UPDATE projects SET owner='system_community_platform' WHERE id='project1'")
  cap=sorted(set(BUSINESS_CAPABILITIES)|{'/community/admin#'+x for x in ('catalog','list','create','grant','revoke')})
  scopes=['/community/operations#merchant']
  templates={scopes[0]:dict(project='project1',project_roles=['OWNER'],principal='merchant',onboarding_required=False)}
  keys,principals,bindings,_=_configuration(self.fx.plan,self.fx.key_material,self.fx.wechat)
  api=CommunityAdminAuthority(self.fx.fx.center,'project1','tenant1',tuple(cap),tuple(scopes),binding_digest(templates,SimpleNamespace(bindings=bindings),principals))
  self.fx.plan['community_admin_authority']=dict(project='project1',tenant='tenant1',capabilities=cap,workspace_scopes=scopes,workspace_bindings=templates,manifest_sha=api.manifest_sha)
  self.fx.write('host.json',self.fx.plan)
 def call(self):
  # Root CI uses synthetic fixture-specific _configuration/file owners; test
  # cannot authorize a production root process. Runtime gate remains intact.
  if os.geteuid()==0:self.skipTest('nonroot preflight contract requires nonroot CI')
  return build_plan(str(self.fx.plan_path),str(self.fx.keys_path),str(self.fx.wechat_path),str(self.fx.root/'backup.sqlite'),str(self.fx.root/'identity-record.json'),'fixture_bootstrap')
 def test_readonly_plan_real_source_and_identity(self):
  with self.fx.open() as host:
   before=host.center.db.total_changes;count=host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
   result=self.call();self.assertEqual(result['plan']['project'],'project1');self.assertEqual(result['plan']['identity_mode'],'OWNER_TTY_CHOICE')
   self.assertEqual(host.center.db.total_changes,before);self.assertEqual(host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],count)
  self.assertFalse((self.fx.root/'backup.sqlite').exists());self.assertFalse((self.fx.root/'identity-record.json').exists())
  self.assertNotIn('app_secret',str(result));self.assertNotIn('private_key_pem',str(result))
 def test_missing_optional_admin_configuration_is_core_plan(self):
  del self.fx.plan['community_admin_authority'];self.fx.write('host.json',self.fx.plan)
  result=self.call();self.assertEqual(result['plan']['bootstrap_mode'],'CORE_FIRST_ENABLE');self.assertEqual(result['plan']['workspace_scopes'],[])
  self.assertGreater(len(result['plan']['capabilities']),150)
 def test_scope_retarget_without_new_manifest_rejected(self):
  self.fx.plan['bindings']['merchant']['store_id']='retarget';self.fx.write('host.json',self.fx.plan)
  with self.assertRaisesRegex(Denied,'MANIFEST_PIN_CHANGED'):self.call()
 def test_core_first_enable_no_provider_then_login_admin(self):
  import io
  from contextlib import redirect_stdout
  from email.message import Message
  from scripts.community_admin_bootstrap import run
  from scripts.community_web_session import WebSession
  del self.fx.plan['community_admin_authority'];self.fx.plan['reviewers']={};self.fx.plan['operations']={};self.fx.plan.pop('provider_reader_config',None)
  self.fx.write('host.json',self.fx.plan)
  result=self.call();plan=result['plan'];self.assertEqual(plan['bootstrap_mode'],'CORE_FIRST_ENABLE')
  output=io.StringIO()
  with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',side_effect=['super@test.invalid','CONFIRM super@test.invalid project1 SUPERADMIN']),patch('getpass.getpass',return_value='synthetic-secure-password'),redirect_stdout(output):
   created=run(plan,'--bootstrap')
  self.assertEqual(created['kind'],'ROOT');self.assertNotIn('synthetic-secure-password',output.getvalue())
  with self.fx.open() as host:
   self.assertIsNotNone(host.center.community_admin_authority)
   self.assertIsNone(host.application.onboarding)
   self.assertIsNone(host.application.provider_actions)
   web=WebSession(host.center,host.application.operations)
   login,cookie=web.dispatch('/community/session/login',Message(),{'email':'super@test.invalid','password':'synthetic-secure-password'},'fixture')
   headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=login['csrf']
   state,_=web.dispatch('/community/session/check',headers,{},'fixture');self.assertEqual(state['community_admin']['kind'],'ROOT');self.assertGreater(len(state['community_admin']['capabilities']),150)
   child,_=web.dispatch('/community/admin',headers,dict(operation='create',params=dict(email='sub@test.invalid',password='synthetic-child-password',capabilities=['/community/operations#community.orders'],workspace_scopes=[],request_id='sub1')),'fixture')
   self.assertEqual(child['kind'],'DELEGATE')
if __name__=='__main__':unittest.main()
