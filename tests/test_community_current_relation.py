"""Isolated original identity and relation store; no new permissions or network."""
import json,unittest
import test_community_mini_center_identity as fixture
from scripts.community_center_communities import CenterCommunities,MEMBERS
from scripts.pr122_customer_core import canonical
class CurrentRelation(unittest.TestCase):
 def setUp(self):
  self.fx=fixture.ExistingCenterComposition();self.fx.setUp();self.addCleanup(self.fx.tearDown);self.c=self.fx.center
  self.web=self.c.login('one@example.org','FixturePassword123!');self.other=self.c.login('two@example.org','FixturePassword123!')
  g={k:dict(user_id=u,project='project1',tenant='tenant1',role=r) for k,u,r in [('owner',self.fx.uid1,'COMMUNITY_ADMIN'),('customer',self.fx.uid1,'CUSTOMER'),('merchant',self.fx.uid1,'MERCHANT_ADMIN'),('platform',self.fx.uid1,'PLATFORM_OWNER'),('other',self.fx.uid2,'CUSTOMER')]}
  self.d=CenterCommunities(self.c,g);self.cid='co_'+'a'*32;self.cid2='co_'+'b'*32
  with self.c.tx():
   for cid in (self.cid,self.cid2):self.d.write(g['owner'],dict(id=cid,tenant='tenant1',owner=self.fx.uid1,name='Fixture',description='',contact='private',state='APPROVED',version=1,opinion='',updated_at=self.c.now()))
 def call(self,op='status',workspace='customer',cid=None,extra=None,web=None):return self.d.dispatch((web or self.web)['token'],(web or self.web)['csrf'],dict(workspace=workspace,operation=op,params=dict(community_id=cid or self.cid,**(extra or {}))))
 def relation(self,**kw):return self.call(**kw)['current_subject_relation']
 def join(self,workspace='customer',kind='CUSTOMER',cid=None):return self.call('join',workspace,cid,dict(kind=kind))
 def tamper(self,changes=None,uid=None):
  key=self.d.key('tenant1','CUSTOMER:'+self.fx.uid1);row=self.c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=?',(MEMBERS,key)).fetchone();r=json.loads(self.c.decrypt(row[0],'community-relation:'+key));r.update(changes or {})
  self.c.db.execute('UPDATE links SET payload=?,user_id=? WHERE channel=? AND subject_idx=?',(self.c.encrypt(canonical(r),'community-relation:'+key),uid or self.fx.uid1,MEMBERS,key));self.c.db.commit()
 def test_active_inactive_and_real_timestamp(self):
  self.assertEqual(self.relation(),dict(state='NOT_JOINED',kind='CUSTOMER',community_id=self.cid,updated_at=None));self.join();self.assertEqual(self.relation()['state'],'ACTIVE');self.assertEqual(self.relation()['updated_at'],self.c.now());self.call('leave',extra={'kind':'CUSTOMER'});self.assertEqual(self.relation()['state'],'INACTIVE')
 def test_kind_from_actual_grant_not_dropdown(self):
  self.join('merchant','MERCHANT');self.assertEqual(self.relation(workspace='merchant')['state'],'ACTIVE');self.assertEqual(self.relation()['state'],'NOT_JOINED')
  with self.assertRaises(ValueError):self.call(extra={'kind':'MERCHANT'})
 def test_nonmember_roles_not_applicable_even_same_uid_joined(self):
  self.join()
  for w in ('owner','platform'):self.assertEqual(self.relation(workspace=w),dict(state='NOT_APPLICABLE',kind=None,community_id=self.cid,updated_at=None))
 def test_other_selected_community_never_leaks_original_id_or_time(self):
  self.join();r=self.relation(cid=self.cid2);self.assertEqual(r,dict(state='NOT_JOINED',kind='CUSTOMER',community_id=self.cid2,updated_at=None));self.assertNotIn(self.cid,json.dumps(r))
 def test_other_subject_has_own_key(self):
  self.join();self.assertEqual(self.relation(workspace='other',web=self.other)['state'],'NOT_JOINED')
 def test_private_gate_before_relation_projection_and_old_public_fields(self):
  self.join();r=self.call();self.assertEqual(set(r),{'id','name','description','state','version','current_subject_relation'});g=self.d.grants['owner'];old=self.d.read(g,self.cid)
  with self.c.tx():self.d.write(g,dict(old,state='DRAFT'),old)
  with self.assertRaisesRegex(PermissionError,'COMMUNITY_PRIVATE'):self.relation()
 def test_cross_tenant_grant_denied(self):
  self.d.grants['customer']['tenant']='other'
  with self.assertRaises(PermissionError):self.relation()
 def test_stored_subject_column_mismatch_fails_closed(self):
  self.join();self.tamper(uid=self.fx.uid2)
  with self.assertRaisesRegex(ValueError,'INTEGRITY_CONFLICT'):self.relation()
 def test_cross_project_record_not_read(self):
  self.join();self.c.db.execute('UPDATE links SET project=? WHERE channel=?',('other',MEMBERS));self.c.db.commit();self.assertEqual(self.relation()['state'],'NOT_JOINED')
 def test_payload_binding_and_time_corruption_not_unjoined(self):
  for change in ({'tenant':'other'},{'user_id':self.fx.uid2},{'kind':'MERCHANT'},{'community_id':'invalid'},{'updated_at':True}):
   with self.subTest(change=change):
    self.c.db.execute('DELETE FROM links WHERE channel=?',(MEMBERS,));self.c.db.commit();self.join();self.tamper(change)
    with self.assertRaisesRegex(ValueError,'INTEGRITY_CONFLICT'):self.relation()
if __name__=='__main__':unittest.main()
