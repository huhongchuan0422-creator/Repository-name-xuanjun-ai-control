"""Original protected merchant records -> authorized community member summary."""
import unittest,copy
from types import SimpleNamespace
from unittest.mock import Mock
import test_community_wechat_payment_activation as activation_fixture
from scripts.community_center_communities import CenterCommunities
from scripts.community_member_merchant_projection import project_member

class MemberProjection(unittest.TestCase):
 @classmethod
 def setUpClass(cls):activation_fixture.WechatPaymentActivation.setUpClass()
 def setUp(self):
  self.fx=activation_fixture.WechatPaymentActivation();self.fx.keys=activation_fixture.WechatPaymentActivation.keys;self.fx.setUp();self.addCleanup(self.fx.tearDown)
  self.g=dict(user_id=self.fx.fx.fx.fx.uid1,project='project1',tenant='tenant1',role='COMMUNITY_ADMIN')
  self.directory=CenterCommunities(self.fx.center,{'community':self.g})
  self.directory.commerce=SimpleNamespace(operations=self.fx.fx.operations)
  self.community=dict(id='co_'+'1'*32,tenant='tenant1',owner=self.g['user_id'])
  self.member=dict(community_id=self.community['id'],tenant='tenant1',user_id=self.g['user_id'],kind='MERCHANT',updated_at=1)
  self.fx.fx.db.execute("UPDATE merchant_profiles SET name='真实原表测试商家'");self.fx.fx.db.commit()
  self.fx.reader._fetch=Mock(side_effect=AssertionError('NO_PROVIDER_IO'))
 def call(self,member=None):return project_member(self.directory,self.g,self.community,self.member if member is None else member)
 def test_original_name_without_collecting_customer_private_fields(self):
  r=self.call();self.assertEqual(r['merchant_name'],'真实原表测试商家');self.assertEqual(r['merchant_name_status'],'MATCHED');self.assertEqual(r['wechat_status'],'UNKNOWN')
  self.assertEqual(set(r)-set(self.member),{'merchant_name','merchant_names','merchant_name_status','wechat_status','wechat_status_source','wechat_observed_at'})
  self.fx.reader._fetch.assert_not_called()
 def test_signed_observation_is_separate_from_membership(self):
  applyment=self.fx.applyment;application=self.fx.app['application'];record=applyment._read(application);record['provider_observed_at']=self.fx.center.now()
  with self.fx.center.tx():applyment._save(application,self.g['user_id'],record)
  r=self.call();self.assertEqual(r['wechat_status'],'APPLYMENT_STATE_FINISHED');self.assertEqual(r['wechat_status_source'],'SIGNED_PROVIDER_QUERY');self.assertEqual(r['wechat_observed_at'],self.fx.center.now())
  record['provider_query_signature_sha256']='bad'
  with self.fx.center.tx():applyment._save(application,self.g['user_id'],record)
  self.assertEqual(self.call()['wechat_status'],'UNKNOWN');self.fx.reader._fetch.assert_not_called()
 def test_current_submission_and_exact_recovery_boundary(self):
  a=self.fx.app['application'];r=self.fx.applyment._read(a);r['provider_observed_at']=self.fx.center.now()
  signed=r['provider_query_signed_at']
  def save(value):
   with self.fx.center.tx():self.fx.applyment._save(a,self.g['user_id'],value)
  for delta in ({'submission_response_signed_at':signed},{'state':'SUBMISSION_UNKNOWN'},
                {'consumed_rejections':[{'signature_sha256':r['provider_query_signature_sha256']}]},
                {'submission_recovery_receipt':[]},{'provider_query_signature_sha256':[]},
                {'provider_query_signature_sha256':{}}):
   save(dict(r,**delta));self.assertEqual(self.call()['wechat_status'],'UNKNOWN')
  recovery=dict(business_code=r['business_code'],applyment_id=r['applyment_id'],signed_at=signed,
      signature_sha256=r['provider_query_signature_sha256'],response_sha256=r['provider_response_sha256'])
  save(dict(r,submission_recovery_receipt=recovery));self.assertEqual(self.call()['wechat_status'],'APPLYMENT_STATE_FINISHED')
  for key in ('business_code','applyment_id','signature_sha256','response_sha256'):
   save(dict(r,submission_recovery_receipt=dict(recovery,**{key:'wrong'})));self.assertEqual(self.call()['wechat_status'],'UNKNOWN')
 def test_cross_tenant_community_or_reader_denied_without_profile(self):
  for delta in ({'tenant':'other'},{'community_id':'co_'+'2'*32}):
   with self.assertRaises(PermissionError):self.call(dict(self.member,**delta))
  g=dict(self.g,role='CUSTOMER')
  with self.assertRaises(PermissionError):project_member(self.directory,g,self.community,self.member)
 def test_other_member_does_not_inherit_name(self):
  r=self.call(dict(self.member,user_id=self.fx.fx.fx.fx.uid2));self.assertEqual(r['merchant_name_status'],'NO_ADMITTED_MAPPING');self.assertIsNone(r['merchant_name']);self.assertEqual(r['merchant_names'],[])
 def test_mapping_change_hides_name_and_signing(self):
  target=self.fx.fx.operations.grants['merchant'];target['scope']=dict(target['scope'],store_id='other')
  r=self.call();self.assertEqual(r['merchant_name_status'],'MAPPING_UNAVAILABLE');self.assertIsNone(r['merchant_name']);self.assertEqual(r['merchant_names'],[])
 def test_customer_relation_not_enriched(self):
  r=dict(self.member,kind='CUSTOMER');self.assertEqual(self.call(r),r)
if __name__=='__main__':unittest.main()
