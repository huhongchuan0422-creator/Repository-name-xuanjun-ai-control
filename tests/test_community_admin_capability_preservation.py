"""Synthetic persisted ROOTs; no request self-attested legacy capability bypass."""
import json,unittest
from pathlib import Path
from types import SimpleNamespace
from scripts.community_admin_authority import CommunityAdminAuthority, CHANNEL
from scripts.community_admin_capability_preservation import readonly_original_root, unchanged_capabilities
from scripts.community_admin_policy import policy_intent,adopt_policy
from scripts.pr122_customer_core import Denied,canonical,digest
import test_community_admin_authority as fixture

LEGACY=json.loads((Path(__file__).parent/'fixtures/community_original_165_capabilities.json').read_text())

class Preservation(unittest.TestCase):
 def setUp(self):
  self.f=fixture.Tests();self.f.setUp();self.addCleanup(self.f.tearDown)
  self.c=self.f.c
  self.scopes=('/community/directory#local_donation','/merchant/onboarding#__community_onboarding__')
  self.api=CommunityAdminAuthority(self.c,'p','t',tuple(LEGACY),self.scopes,'a'*64)
  self.root=dict(uid='root',project='p',tenant='t',kind='ROOT',revision=3,parent=None,parent_revision=None,capabilities=list(LEGACY),workspace_scopes=list(self.scopes),scope_binding_sha=self.api.scope_binding_sha,manifest_sha=self.api.manifest_sha,request_id='original')
  self.save(self.root)
  self.next=CommunityAdminAuthority(self.c,'p','t',tuple(LEGACY),self.scopes+('/community/operations#platform_showcase',),'b'*64)
 def save(self,value,active=True):
  with self.c.tx():self.api._write(value,active)
 def read(self):return readonly_original_root(self.c.db,self.c.keys,'p','t')
 def test_exact_persisted165_scope_only_intent(self):
  before=self.c.db.total_changes;old=self.read();unchanged_capabilities(old['capabilities'],LEGACY)
  intent=policy_intent(self.next,'preserve165')
  self.assertEqual(intent['expected_revision'],3);self.assertEqual(intent['capabilities'],LEGACY)
  self.assertEqual(set(intent['workspace_scopes'])-set(self.scopes),{'/community/operations#platform_showcase'})
  self.assertEqual(self.c.db.total_changes,before)
 def test_changed_target_rejected_not_self_reported(self):
  for caps in (LEGACY[:-1],LEGACY+['/merchant/onboarding#donation_defaults'],LEGACY+['/community/operations#unknown']):
   with self.subTest(caps=len(caps)),self.assertRaises(Denied):
    target=CommunityAdminAuthority(self.c,'p','t',tuple(caps),tuple(self.next.workspace_scopes),'b'*64)
    policy_intent(target,'changed')
 def test_unknown_original_even_same_target_rejected(self):
  caps=LEGACY[:-1]+['/community/operations#unknown']
  api=CommunityAdminAuthority(self.c,'p','t',tuple(caps),self.scopes,'a'*64)
  self.save(dict(self.root,capabilities=caps,manifest_sha=api.manifest_sha))
  target=CommunityAdminAuthority(self.c,'p','t',tuple(caps),tuple(self.next.workspace_scopes),'b'*64)
  with self.assertRaisesRegex(Denied,'KNOWN_ORIGINAL'):policy_intent(target,'unknown')
 def test_revoked_or_ambiguous_original_rejected(self):
  self.save(self.root,False)
  with self.assertRaises(Denied):self.read()
  with self.assertRaises(Denied):policy_intent(self.next,'revoked')
  self.save(self.root)
  self.save(dict(self.root,uid='other'))
  with self.assertRaises(Denied):self.read()
  with self.assertRaises(Denied):policy_intent(self.next,'ambiguous')
 def test_manifest_realm_account_changes_rejected(self):
  self.save(dict(self.root,manifest_sha='0'*64))
  with self.assertRaises(Denied):self.read()
  self.save(self.root)
  with self.assertRaises(Denied):readonly_original_root(self.c.db,self.c.keys,'p','wrong')
  self.c.db.execute("UPDATE accounts SET verified=0 WHERE id='root'")
  with self.assertRaises(Denied):self.read()
  with self.assertRaises(Denied):policy_intent(self.next,'disabled')
 def test_original165_can_adopt_synthetically_but_confirmation_not_bypassed(self):
  intent=policy_intent(self.next,'synthetic-adoption')
  with self.assertRaises(Denied):adopt_policy(self.next,intent,'c'*64,lambda x:False)
  self.assertEqual(self.read()['revision'],3)
  result=adopt_policy(self.next,intent,'c'*64,lambda x:x==intent)
  self.assertEqual(result['revision'],4)
  self.assertEqual(self.read()['capabilities'],LEGACY)
  self.assertEqual(self.c.db.execute("SELECT count(*) FROM sessions WHERE user_id='root'").fetchone()[0],0)

class OriginalPreflight(unittest.TestCase):
 def setUp(self):
  from test_community_admin_preflight import Preflight
  self.f=Preflight();self.f.setUp();self.addCleanup(self.f.doCleanups);self.fx=self.f.fx
  a=self.fx.plan['community_admin_authority'];a['capabilities']=list(LEGACY)
  self.pin()
  with self.fx.open() as h:
   uid=h.center.db.execute('SELECT id FROM accounts WHERE verified=1 ORDER BY id LIMIT 1').fetchone()[0]
   api=h.center.community_admin_authority
   with h.center.tx():api._write(dict(uid=uid,project=a['project'],tenant=a['tenant'],kind='ROOT',revision=3,parent=None,parent_revision=None,capabilities=list(LEGACY),workspace_scopes=list(a['workspace_scopes']),scope_binding_sha=api.scope_binding_sha,manifest_sha=api.manifest_sha,request_id='original'),True)
  self.uid=uid
  key='/community/operations#platform_showcase'
  a['workspace_scopes'].append(key)
  a['workspace_bindings'][key]=dict(project=a['project'],tenant=a['tenant'],role='PLATFORM_SHOWCASE_ROOT',operator_uid=uid,operations=['community.item','community.merchant_settings'])
  self.pin()
 def pin(self):
  from scripts.community_platform_host import _configuration
  from scripts.community_admin_route_gate import binding_digest
  a=self.fx.plan['community_admin_authority'];_,p,b,_=_configuration(self.fx.plan,self.fx.key_material,self.fx.wechat)
  a['manifest_sha']=digest(canonical(dict(capabilities=sorted(a['capabilities']),workspace_scopes=sorted(a['workspace_scopes']),scope_binding_sha=binding_digest(a['workspace_bindings'],SimpleNamespace(bindings=b),p))))
  self.fx.write('host.json',self.fx.plan)
 def call(self,preserve=True):
  from scripts.community_admin_preflight import build_plan
  return build_plan(str(self.fx.plan_path),str(self.fx.keys_path),str(self.fx.wechat_path),str(self.fx.root/'backup.sqlite'),str(self.fx.root/'policy-execution.json'),'preserve165',policy_preservation=preserve)
 def test_readonly_original_preflight_and_inspect(self):
  result=self.call();self.assertEqual(len(result['plan']['capabilities']),165)
  self.assertFalse((self.fx.root/'backup.sqlite').exists())
  from scripts.community_admin_policy_maintenance import run
  inspected=run(result['plan'],'--inspect')
  self.assertEqual(inspected['intent']['expected_revision'],3)
  self.assertEqual(inspected['intent']['capabilities'],LEGACY)
  self.assertFalse((self.fx.root/'policy-execution.json').exists())
 def test_showcase_mount_only_after_original_policy_adoption(self):
  import importlib.util
  # Frozen quantity artifact is loaded separately by runtime runner; source test
  # reuses its mount contract through an explicit path supplied by the delivery.
  import os
  path=os.environ.get('FROZEN_SHOWCASE_PATH')
  if path is None:self.skipTest('frozen artifact path is supplied by runtime runner')
  import hashlib
  self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),'066999cfe06ed65dbdc244643ad7db525dc8a52cd3d40a5935569ac8f85967ad')
  spec=importlib.util.spec_from_file_location('frozen_showcase_for_policy_test',path)
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with self.fx.open() as h:
   config=dict(project='project1',tenant='tenant1',operator_uid=self.uid,workspace='platform_showcase')
   with self.assertRaises(Denied):module.mount(h.application.operations,config)
   api=h.center.community_admin_authority;intent=policy_intent(api,'synthetic-mount-phase')
   adopt_policy(api,intent,'d'*64,lambda value:value==intent)
   mounted=module.mount(h.application.operations,config)
   self.assertEqual(mounted.workspace,'platform_showcase')
   self.assertEqual(api.authority(self.uid)['capabilities'],LEGACY)
 def test_bootstrap_default_stays_full_inventory(self):
  with self.assertRaisesRegex(Denied,'COMPLETE_COMMUNITY_CAPABILITY'):self.call(False)
  from scripts.community_admin_bootstrap import run
  with self.assertRaisesRegex(Denied,'COMPLETE_COMMUNITY_CAPABILITY'):run(self.call()['plan'],'--bootstrap')
 def test_modified_target_and_revoked_root_do_not_use_flag_as_authority(self):
  a=self.fx.plan['community_admin_authority'];a['capabilities'].append('/merchant/onboarding#donation_defaults');self.pin()
  with self.assertRaises(Denied):self.call()
  a['capabilities']=list(LEGACY);self.pin()
  with self.fx.open() as h:h.center.db.execute('UPDATE links SET active=0 WHERE channel=? AND subject_idx=?',(CHANNEL,self.uid))
  with self.assertRaises(Denied):self.call()

if __name__=='__main__':unittest.main()
