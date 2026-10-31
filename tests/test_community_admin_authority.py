"""Isolated synthetic fixtures, never a production bootstrap/authority source."""
import tempfile, unittest, secrets
from pathlib import Path
from scripts.pr122_customer_core import Center, canonical, digest, Denied, Conflict
from scripts.community_admin_authority import CommunityAdminAuthority, community_login, ACCOUNT_INDEX

CAPS=('/community/admin#grant','/community/operations#read','/merchant/onboarding#review','/community/admin#catalog','/community/admin#list','/community/admin#create','/community/admin#revoke')
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.c=Center(Path(self.tmp.name)/'identity',{'k':b'x'*32},'k',clock=lambda:1000)
  c=self.c; realm=dict(kind='COMMUNITY_PLATFORM_REALM',title='SYNTHETIC TEST',requirements=[],source='OWNER_APPROVED_FIRST_INSTALL',authority_ref='fixture')
  with c.tx():
   c.db.execute('INSERT INTO projects VALUES(?,?,?,?,?,1,?,?,1)',('p','t','c','system_community_platform','fixture',9999,c.encrypt(canonical(realm),'project:p')))
   for uid in ('root','child','other'):
    salt=secrets.token_bytes(16)
    c.db.execute('INSERT INTO accounts(id,email_idx,email_enc,salt,password,verified) VALUES(?,?,?,?,?,1)',(uid,c.idx(uid+'@test.invalid'),c.encrypt((uid+'@test.invalid').encode(),uid),salt,c.password('synthetic-password',salt)))
  self.api=CommunityAdminAuthority(c,'p','t',CAPS)
  with c.tx():self.api._write(dict(uid='root',project='p',tenant='t',kind='ROOT',revision=1,parent=None,parent_revision=None,capabilities=sorted(CAPS),workspace_scopes=[],scope_binding_sha=self.api.scope_binding_sha,manifest_sha=self.api.manifest_sha,request_id='fixture'),True)
  self.r=c.login('root@test.invalid','synthetic-password');self.child=c.login('child@test.invalid','synthetic-password')
 def tearDown(self):self.c.db.close();self.tmp.cleanup()
 def grant(self):return self.api.delegate(self.r['token'],self.r['csrf'],'child',[CAPS[1]],'request1',0)
 def test_root(self):self.assertEqual(self.api.authorize(self.r['token'],self.r['csrf'],'/merchant/onboarding','review')['uid'],'root')
 def test_subset(self):
  self.grant();self.assertEqual(self.api.authorize(self.child['token'],self.child['csrf'],'/community/operations','read')['uid'],'child')
  with self.assertRaises(Denied):self.api.authorize(self.child['token'],self.child['csrf'],'/merchant/onboarding','review')
 def test_child_cannot_grant(self):
  self.grant()
  with self.assertRaises(Denied):self.api.delegate(self.child['token'],self.child['csrf'],'other',[CAPS[1]],'request2',0)
 def test_no_management_delegation(self):
  with self.assertRaises(Denied):self.api.delegate(self.r['token'],self.r['csrf'],'child',[CAPS[0]],'request1',0)
 def test_no_self_change(self):
  with self.assertRaises(Denied):self.api.delegate(self.r['token'],self.r['csrf'],'root',[CAPS[1]],'request1',1)
 def test_revoke_immediate(self):
  self.grant();self.api.revoke(self.r['token'],self.r['csrf'],'child',1)
  with self.assertRaises(Denied):self.api.authorize(self.child['token'],self.child['csrf'],'/community/operations','read')
 def test_wrong_project(self):
  api=CommunityAdminAuthority(self.c,'other','t',CAPS)
  with self.assertRaises(Denied):api.authorize(self.r['token'],self.r['csrf'],'/community/operations','read')
 def test_stale_revision(self):
  self.grant()
  with self.assertRaises(Conflict):self.api.delegate(self.r['token'],self.r['csrf'],'child',[CAPS[1]],'request2',0)
 def test_csrf_required(self):
  with self.assertRaises(Denied):self.api.delegate(self.r['token'],None,'child',[CAPS[1]],'request1',0)
 def test_parent_revoke(self):
  self.grant()
  with self.c.tx():self.c.db.execute("UPDATE links SET active=0 WHERE subject_idx='root' AND channel='COMMUNITY_ADMIN_AUTHORITY_V1'")
  with self.assertRaises(Denied):self.api.authorize(self.child['token'],self.child['csrf'],'/community/operations','read')
 def test_unknown_capability(self):
  with self.assertRaises(Denied):self.api.authorize(self.r['token'],self.r['csrf'],'/community/unknown','read')
 def test_core_unchanged_members(self):
  self.grant();self.assertEqual(self.c.db.execute('SELECT count(*) FROM members').fetchone()[0],0)
 def test_delegate_idempotent(self):
  first=self.grant(); second=self.grant();self.assertEqual(first['revision'],second['revision']);self.assertTrue(second['replayed'])
 def bootstrap_args(self):
  with self.c.tx():self.c.db.execute("DELETE FROM links WHERE channel='COMMUNITY_ADMIN_AUTHORITY_V1'")
  return dict(owner_message_id='synthetic',owner_body_sha256='a'*64,project='p',tenant='t',email='fixed@test.invalid',manifest_sha=self.api.manifest_sha,request_id='bootstrap1',action='BOOTSTRAP_COMMUNITY_SUPERADMIN')
 def test_bootstrap_real_hash_login(self):
  binding=self.bootstrap_args();result=self.api.bootstrap('fixed@test.invalid','synthetic-secret-password','bootstrap1',binding,lambda b:b==binding)
  login=community_login(self.c,'fixed@test.invalid','synthetic-secret-password');self.assertEqual(login['user_id'],result['uid'])
  self.assertFalse(result['mailbox_verified']);self.assertEqual(self.c.db.execute("SELECT count(*) FROM audit WHERE event='EMAIL_VERIFIED' AND actor=?",(result['uid'],)).fetchone()[0],0)
  self.assertEqual(self.api.authorize(login['token'],login['csrf'],'/merchant/onboarding','review')['uid'],result['uid'])
 def test_bootstrap_replay_no_password_reset(self):
  b=self.bootstrap_args();a=self.api.bootstrap('fixed@test.invalid','synthetic-secret-password','bootstrap1',b,lambda x:True)
  r=self.api.bootstrap('fixed@test.invalid','different-password','bootstrap1',b,lambda x:True);self.assertEqual(a['uid'],r['uid']);self.assertTrue(r['replayed'])
  community_login(self.c,'fixed@test.invalid','synthetic-secret-password')
  with self.assertRaises(Denied):community_login(self.c,'fixed@test.invalid','different-password')
 def test_bootstrap_wrong_owner(self):
  b=self.bootstrap_args()
  with self.assertRaises(Denied):self.api.bootstrap('fixed@test.invalid','synthetic-secret-password','bootstrap1',b,lambda x:False)
  self.assertIsNone(self.c.db.execute('SELECT id FROM accounts WHERE email_idx=?',(self.c.idx('fixed@test.invalid'),)).fetchone())
 def test_bootstrap_collision(self):
  b=self.bootstrap_args();b['email']='child@test.invalid'
  with self.assertRaises(Conflict):self.api.bootstrap(b['email'],'synthetic-secret-password','bootstrap1',b,lambda x:True)
 def test_bootstrap_transaction_rollback(self):
  from unittest.mock import patch
  b=self.bootstrap_args()
  with patch.object(self.c,'audit',side_effect=RuntimeError('synthetic failure')):
   with self.assertRaises(RuntimeError):self.api.bootstrap('fixed@test.invalid','synthetic-secret-password','bootstrap1',b,lambda x:True)
  self.assertIsNone(self.c.db.execute('SELECT id FROM accounts WHERE email_idx=?',(self.c.idx('fixed@test.invalid'),)).fetchone())
  self.assertEqual(self.c.db.execute("SELECT count(*) FROM links WHERE channel='COMMUNITY_ADMIN_AUTHORITY_V1'").fetchone()[0],0)
 def test_provisioned_not_email_verified_lookup(self):
  b=self.bootstrap_args();r=self.api.bootstrap('fixed@test.invalid','synthetic-secret-password','bootstrap1',b,lambda x:True)
  self.assertIsNone(self.c.db.execute('SELECT id FROM accounts WHERE email_idx=? AND verified=1',(self.c.idx('fixed@test.invalid'),)).fetchone())
  with self.assertRaises(Denied):self.c.login('fixed@test.invalid','synthetic-secret-password')
  self.assertEqual(community_login(self.c,'fixed@test.invalid','synthetic-secret-password')['user_id'],r['uid'])
 def test_revoke_revision_types(self):
  self.grant()
  for invalid in (True,1.0,'1',None):
   with self.assertRaises(Denied):self.api.revoke(self.r['token'],self.r['csrf'],'child',invalid)
  self.assertEqual(self.api.authority('child')['revision'],1)
 def provision_root(self):
  b=self.bootstrap_args();self.api.bootstrap('fixed@test.invalid','synthetic-secret-password','bootstrap1',b,lambda x:True)
  return community_login(self.c,'fixed@test.invalid','synthetic-secret-password')
 def test_create_child_and_revoke_existing_session(self):
  r=self.provision_root();child=self.api.create_subadmin(r['token'],r['csrf'],'staff@test.invalid','synthetic-child-password',[CAPS[1]],'childcreate')
  login=community_login(self.c,'staff@test.invalid','synthetic-child-password')
  self.assertEqual(self.api.authorize(login['token'],login['csrf'],'/community/operations','read')['uid'],child['uid'])
  self.api.revoke(r['token'],r['csrf'],child['uid'],1)
  with self.assertRaises(Denied):self.api.authorize(login['token'],login['csrf'],'/community/operations','read')
  with self.assertRaises(Denied):community_login(self.c,'staff@test.invalid','synthetic-child-password')
 def test_identity_revoke_existing_session(self):
  r=self.provision_root()
  with self.c.tx():self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ADMIN_AUTHORITY_V1_IDENTITY'")
  with self.assertRaises(Denied):self.api.authorize(r['token'],r['csrf'],'/community/operations','read')
  with self.assertRaises(Denied):community_login(self.c,'fixed@test.invalid','synthetic-secret-password')
 def test_namespace_collision_deny_not_pick_user(self):
  r=self.provision_root()
  with self.c.tx():self.c.db.execute('UPDATE accounts SET email_idx=? WHERE id=?',(self.c.idx('fixed@test.invalid'),'other'))
  with self.assertRaises(Denied):community_login(self.c,'fixed@test.invalid','synthetic-secret-password')
 def test_child_account_cannot_create_account(self):
  r=self.provision_root();self.api.create_subadmin(r['token'],r['csrf'],'staff@test.invalid','synthetic-child-password',[CAPS[1]],'childcreate')
  c=community_login(self.c,'staff@test.invalid','synthetic-child-password')
  with self.assertRaises(Denied):self.api.create_subadmin(c['token'],c['csrf'],'new@test.invalid','synthetic-new-password',[CAPS[1]],'escalate')
 def test_subadmin_create_idempotent(self):
  r=self.provision_root();a=self.api.create_subadmin(r['token'],r['csrf'],'staff@test.invalid','synthetic-child-password',[CAPS[1]],'childcreate')
  b=self.api.create_subadmin(r['token'],r['csrf'],'staff@test.invalid','changed-child-password',[CAPS[1]],'childcreate');self.assertEqual(a['uid'],b['uid']);self.assertTrue(b['replayed'])
  community_login(self.c,'staff@test.invalid','synthetic-child-password')
 def test_original_web_login_and_management(self):
  from email.message import Message
  from scripts.community_web_session import WebSession,COOKIE
  from scripts.community_admin_management import dispatch
  b=self.bootstrap_args();self.api.bootstrap('fixed@test.invalid','synthetic-secret-password','bootstrap1',b,lambda x:True)
  self.c.community_admin_authority=self.api;web=WebSession(self.c)
  result,cookie=web.dispatch('/community/session/login',Message(),{'email':'fixed@test.invalid','password':'synthetic-secret-password'},'fixture-source')
  headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=result['csrf']
  check,_=web.dispatch('/community/session/check',headers,{},'fixture-source');self.assertEqual(check['community_admin']['kind'],'ROOT')
  catalog,_=web.dispatch('/community/admin',headers,dict(operation='catalog',params={}),'fixture-source');self.assertEqual(catalog['manifest_sha'],self.api.manifest_sha)
  created,_=web.dispatch('/community/admin',headers,dict(operation='create',params=dict(email='scoped@test.invalid',password='synthetic-child-password',capabilities=[CAPS[1]],workspace_scopes=[],request_id='webcreate')),'fixture-source')
  login=community_login(self.c,'scoped@test.invalid','synthetic-child-password')
  with self.assertRaises(Denied):dispatch(self.c,login['token'],login['csrf'],dict(operation='list',params={'after_uid':''}))
 def test_scope_subset_real_authority(self):
  self.api=CommunityAdminAuthority(self.c,'p','t',CAPS,('/community/operations#store1','/community/operations#store2'))
  r=self.provision_root()
  child=self.api.create_subadmin(r['token'],r['csrf'],'scoped@test.invalid','synthetic-child-password',[CAPS[1]],'scoped', ['/community/operations#store1'])
  login=community_login(self.c,'scoped@test.invalid','synthetic-child-password')
  self.api.authorize(login['token'],login['csrf'],'/community/operations','read','store1')
  with self.assertRaises(Denied):self.api.authorize(login['token'],login['csrf'],'/community/operations','read','store2')
 def test_revoke_same_key_readback(self):
  self.grant();a=self.api.revoke(self.r['token'],self.r['csrf'],'child',1,'revoke1');b=self.api.revoke(self.r['token'],self.r['csrf'],'child',1,'revoke1');self.assertEqual(a['revision'],b['revision']);self.assertTrue(b['replayed'])
if __name__=='__main__':unittest.main()
