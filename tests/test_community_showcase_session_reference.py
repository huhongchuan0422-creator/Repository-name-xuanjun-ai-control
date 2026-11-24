"""Synthetic original sessions; navigation metadata is never a new grant."""
import json,unittest
from types import SimpleNamespace
from email.message import Message
from scripts.community_admin_authority import CommunityAdminAuthority
from scripts.community_web_session import WebSession,COOKIE
import test_community_admin_authority as fixture

class ShowcaseReference(unittest.TestCase):
 def setUp(self):
  self.fx=fixture.Tests();self.fx.setUp();self.addCleanup(self.fx.tearDown)
  self.c=self.fx.c;self.scope='/community/operations#platform_showcase'
  caps=('/community/admin#grant','/community/operations#community.item','/community/operations#community.merchant_settings')
  self.api=CommunityAdminAuthority(self.c,'p','t',caps,(self.scope,),'a'*64)
  self.root=dict(uid='root',project='p',tenant='t',kind='ROOT',revision=4,parent=None,parent_revision=None,capabilities=sorted(caps),workspace_scopes=[self.scope],scope_binding_sha=self.api.scope_binding_sha,manifest_sha=self.api.manifest_sha,request_id='fixture')
  with self.c.tx():self.api._write(self.root,True)
  self.c.community_admin_authority=self.api
  self.showcase=SimpleNamespace(center=self.c,operator_uid='root',project='p',tenant='t',workspace='platform_showcase')
  self.ops=SimpleNamespace(center=self.c,grants={},platform_showcase=self.showcase)
  self.service=WebSession(self.c,self.ops)
 def check(self,login=None):
  value=login or self.fx.r;headers=Message();headers['Cookie']=COOKIE+'='+value['token'];headers['X-CSRF-Token']=value['csrf']
  return self.service.dispatch('/community/session/check',headers,{},'synthetic')[0]
 def test_original_root_gets_only_nonsecret_reference_no_writes(self):
  before=self.c.db.total_changes;result=self.check()
  self.assertEqual(result['platform_showcase'],dict(workspace='platform_showcase',display_only=True))
  self.assertEqual(self.c.db.total_changes,before)
  self.assertNotIn(self.fx.r['token'],json.dumps(result));self.assertNotIn(self.fx.r['csrf'],json.dumps(result))
  self.assertEqual(result['workspaces'],[])
 def test_unmounted_or_foreign_operator_realm_does_not_publish_reference(self):
  for change in (dict(operator_uid='other'),dict(project='foreign'),dict(tenant='foreign'),dict(workspace='owner_merchant'),dict(center=object())):
   with self.subTest(change=list(change)):
    self.ops.platform_showcase=SimpleNamespace(**{**vars(self.showcase),**change})
    self.assertNotIn('platform_showcase',self.check())
  self.ops.platform_showcase=None;self.assertNotIn('platform_showcase',self.check())
 def test_delegate_and_ordinary_user_cannot_use_reference_as_authority(self):
  self.api.delegate(self.fx.r['token'],self.fx.r['csrf'],'child',['/community/operations#community.item'],'child',0,workspace_scopes=[self.scope])
  self.assertNotIn('platform_showcase',self.check(self.fx.child))
  other=self.c.login('other@test.invalid','synthetic-password')
  self.assertNotIn('platform_showcase',self.check(other))
 def test_original_scope_revocation_still_rejects_session_check(self):
  self.c.db.execute("UPDATE links SET active=0 WHERE subject_idx='root' AND channel='COMMUNITY_ADMIN_AUTHORITY_V1'")
  with self.assertRaises(PermissionError):self.check()

if __name__=='__main__':unittest.main()
