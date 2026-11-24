"""Synthetic original-host composition; never real policy adoption or tokens."""
import unittest
from types import SimpleNamespace
from scripts.pr122_customer_core import Denied, canonical, digest
from scripts.community_admin_authority import CommunityAdminAuthority
from scripts.community_admin_route_gate import (binding_digest, configure_admin_routes,
    enforce_admin_route, community_route, resolve_admin_workspace, admin_workspace_catalog)
from scripts.community_platform_host import _configuration
from scripts.community_showcase_template import validate, OPS, ROLE
from test_community_admin_preflight import Preflight

class ShowcaseTemplate(unittest.TestCase):
 def setUp(self):
  self.f=Preflight();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.fx=self.f.fx
  self.key='/community/operations#platform_showcase'
  self.template=dict(project='project1',tenant='tenant1',role=ROLE,operator_uid='synthetic_root',operations=sorted(OPS))
  self.admin=self.fx.plan['community_admin_authority']
  self.admin['workspace_scopes'].append(self.key)
  self.admin['workspace_bindings'][self.key]=self.template
  self.pin()
 def pin(self):
  _,p,b,_=_configuration(self.fx.plan,self.fx.key_material,self.fx.wechat)
  self.binding=binding_digest(self.admin['workspace_bindings'],SimpleNamespace(bindings=b),p)
  self.admin['manifest_sha']=digest(canonical(dict(capabilities=sorted(self.admin['capabilities']),workspace_scopes=sorted(self.admin['workspace_scopes']),scope_binding_sha=self.binding)))
  self.fx.write('host.json',self.fx.plan)
 def test_preflight_no_principal_and_no_writes(self):
  plan=self.f.call()['plan']
  self.assertIn(self.key,plan['workspace_scopes'])
  self.assertFalse((self.fx.root/'identity-record.json').exists())
  with self.fx.open() as h:
   self.assertEqual(h.center.community_admin_workspace_bindings[self.key]['role'],ROLE)
   self.assertNotIn('principal',h.center.community_admin_workspace_bindings[self.key])
 def test_binding_pins_operator_and_operations(self):
  old=self.binding
  self.template['operator_uid']='different_root';self.pin()
  self.assertNotEqual(old,self.binding)
  self.template['operations']=['community.checkout','community.item']
  self.fx.write('host.json',self.fx.plan)
  with self.assertRaises(Denied):self.f.call()
 def test_shape_realm_route_principal_rejected(self):
  for change in (dict(tenant='wrong'),dict(project='wrong'),dict(principal='merchant'),dict(operations=['community.item']),dict(operations=['community.item','community.item'])):
   with self.subTest(change=change),self.assertRaises((Denied,ValueError)):
    validate(self.key,dict(self.template,**change),'project1','tenant1')
  with self.assertRaises(Denied):validate('/community/directory#platform_showcase',self.template,'project1','tenant1')
 def test_original_route_root_only_two_ops_and_no_merchant_fallback(self):
  with self.fx.open() as h:
   c=h.center;a=c.community_admin_authority
   # Existing fixture users are verified and can use original login.
   row=c.db.execute('SELECT id FROM accounts WHERE verified=1 ORDER BY id LIMIT 1').fetchone()
   uid=row[0]
   self.template['operator_uid']=uid;self.pin()
   p={'merchant':h.application.operations.grants['merchant']['principal']}
   a=configure_admin_routes(c,h.persistence.runtime,p,self.admin)
   with c.tx():
    a._write(dict(uid=uid,project='project1',tenant='tenant1',kind='ROOT',revision=1,parent=None,parent_revision=None,capabilities=sorted(a.capabilities),workspace_scopes=sorted(a.workspace_scopes),scope_binding_sha=a.scope_binding_sha,manifest_sha=a.manifest_sha,request_id='synthetic'),True)
   # Login using the fixture's actual known password; never patch Center.session.
   import secrets
   salt=secrets.token_bytes(16)
   with c.tx():c.db.execute('UPDATE accounts SET salt=?,password=? WHERE id=?',(salt,c.password('synthetic-password',salt),uid))
   email=c.decrypt(c.db.execute('SELECT email_enc FROM accounts WHERE id=?',(uid,)).fetchone()[0],uid).decode()
   login=c.login(email,'synthetic-password')
   body=dict(workspace='platform_showcase',operation='community.item',params={})
   self.assertEqual(enforce_admin_route(c,login['token'],login['csrf'],'/community/operations',body)['uid'],uid)
   with self.assertRaises(Denied):enforce_admin_route(c,login['token'],login['csrf'],'/community/operations',dict(body,operation='community.checkout'))
   @community_route('/community/operations')
   def catalog(obj,session,csrf,body):
    self.assertNotIn('platform_showcase',admin_workspace_catalog(c,{}))
    return resolve_admin_workspace(c,{},'platform_showcase',uid)
   with self.assertRaisesRegex(Denied,'NOT_MERCHANT_GRANT'):catalog(SimpleNamespace(center=c),login['token'],login['csrf'],body)
   # Another account cannot inherit this root-only workspace, even with delegated ops.
   other=c.db.execute('SELECT id FROM accounts WHERE verified=1 AND id!=? LIMIT 1',(uid,)).fetchone()[0]
   a.delegate(login['token'],login['csrf'],other,['/community/operations#community.item'],'synthetic-child',0,workspace_scopes=[self.key])
   import scripts.community_showcase_template as st
   proof=dict(uid=other,project='project1',tenant='tenant1',revision=1,capability='/community/operations#community.item')
   with self.assertRaisesRegex(Denied,'ROOT_OPERATION'):
    st.authorize(c,a,proof,'/community/operations','community.item','platform_showcase')
   c.community_admin_workspace_bindings[self.key]['operator_uid']='wrong_root'
   with self.assertRaisesRegex(Denied,'TEMPLATE_CHANGED'):enforce_admin_route(c,login['token'],login['csrf'],'/community/operations',body)

if __name__=='__main__':unittest.main()
