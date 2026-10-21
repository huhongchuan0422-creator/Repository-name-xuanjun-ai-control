"""Verified applyment -> existing MiniPayments startup projection; synthetic only."""
import json,unittest
from unittest.mock import Mock
import test_community_merchant_opening as opening_fixture
import test_community_wechat_sp_readonly as key_fixture
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_payment_activation import project_wechat_merchants,project_wechat_scene
from scripts.community_mini_login import MiniGateway
from scripts.community_wechat_sp_prepay import PartnerPrepay
from scripts.community_mini_payments import MiniPayments

class WechatPaymentActivation(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  key_fixture.SignedOrderQuery.setUpClass();cls.keys=key_fixture.SignedOrderQuery
 def setUp(self):
  self.fx=opening_fixture.AdmittedMerchantOpening();self.fx.setUp()
  self.app=self.fx.approve()
  self.reader=PartnerOrderReader('1234567890','ABC',self.keys.private,'PUB_KEY_ID_fixture',self.keys.public,lambda:self.fx.fx.fx.stage.now)
  self.applyment=WechatApplyment(self.fx.fx.service,self.reader,submission_enabled=False)
  self.fx.fx.service.wechat_applyment=self.applyment
  self.scene='shop1'
  self.admissions={self.scene:{
   'channel':'WECHAT','description':'Fixture merchant order',
   'notify_url':'https://example.org/wechat/notify','profit_sharing':False,
   'jsapi_admitted':True,'profit_sharing_admitted':False}}
  self.seed('APPLYMENT_STATE_FINISHED','1234567891')
 def tearDown(self):self.fx.tearDown()
 @property
 def center(self):return self.fx.fx.fx.center
 @property
 def identity(self):return self.fx.fx.fx.identity
 def seed(self,state,sub_mchid=None,sp_mchid='1234567890'):
  appid=self.app['application']
  record={'version':1,'state':'SUBMITTED_TO_PROVIDER','provider_state':state,
          'business_code':'biz_fixture','applyment_id':'1001',
          'provider_sp_mchid':sp_mchid,'provider_query_signed_at':1700000000,
          'provider_query_signature_sha256':'1'*64,'provider_response_sha256':'2'*64}
  if sub_mchid is not None:record['provider_sub_mchid']=sub_mchid
  with self.center.tx():self.applyment._save(appid,self.fx.fx.fx.uid1,record)
 def project(self,admissions=None):
  return project_wechat_merchants(self.identity,self.fx.fx.service,self.reader,
      self.admissions if admissions is None else admissions)
 def test_finished_applyment_projects_existing_merchants_shape(self):
  result=self.project()
  self.assertEqual(result,{self.scene:{
   'sp_appid':self.identity.appid,'sub_mchid':'1234567891',
   'description':'Fixture merchant order','notify_url':'https://example.org/wechat/notify',
   'profit_sharing':False}})
  client=MiniPayments(self.identity,PartnerPrepay(self.center,self.reader,{}),merchants=result)
  self.assertEqual(client.merchants[self.scene]['project'],'project1')
 def test_nonfinished_missing_submerchant_wrong_provider_and_product_gate_fail_closed(self):
  for state,sub,sp in [('APPLYMENT_STATE_AUDITING','1234567891','1234567890'),
                       ('APPLYMENT_STATE_FINISHED',None,'1234567890'),
                       ('APPLYMENT_STATE_FINISHED','1234567891','9999999999')]:
   self.seed(state,sub,sp)
   with self.assertRaises(PermissionError):self.project()
  self.seed('APPLYMENT_STATE_FINISHED','1234567891')
  bad={self.scene:dict(self.admissions[self.scene],jsapi_admitted=False)}
  with self.assertRaises(PermissionError):self.project(bad)
  bad={self.scene:dict(self.admissions[self.scene],profit_sharing=True,profit_sharing_admitted=False)}
  with self.assertRaises(PermissionError):self.project(bad)
 def test_revoked_opening_or_scope_change_rejects_projection(self):
  self.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_MERCHANT_OPENING'")
  with self.assertRaises(PermissionError):self.project()
 def configured_client(self):
  result=self.project()
  client=MiniPayments(self.identity,PartnerPrepay(self.center,self.reader,{}),merchants=result)
  client.activation_guard=lambda scene:project_wechat_scene(
      self.identity,self.fx.fx.service,self.reader,scene,self.admissions[scene])['merchant']
  return client
 def test_runtime_guard_rejects_revoked_opening_through_payment_authorize(self):
  token=self.fx.fx.fx.token('activation_code')
  self.fx.fx.fx.checkout(token,'activation_order')
  client=self.configured_client()
  self.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_MERCHANT_OPENING'")
  with self.assertRaises(PermissionError):client._authorize(token,self.scene,'activation_order')
 def test_paused_merchant_denies_prepare_before_provider_io(self):
  token=self.fx.fx.fx.token('paused_code')
  self.fx.fx.fx.checkout(token,'paused_order')
  client=self.configured_client();self.reader._fetch=Mock()
  from scripts.community_platform_merchants import CHANNEL,merchant_key,assert_trading
  from scripts.pr122_customer_core import canonical
  scope=dict(self.identity.runtime.bindings[self.identity.scenes[self.scene]['principal']])
  key=merchant_key(scope)
  # Original platform lifecycle store, not the separate storefront profile status.
  value=dict(scope=scope,status='PAUSED',version=1,reason='Synthetic pause',
             updated_at=self.center.now(),actor=self.fx.fx.fx.uid1)
  with self.center.tx():
   self.center.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',
       (CHANNEL,key,self.fx.fx.fx.uid1,'project1',
        self.center.encrypt(canonical(value),'community-merchant-lifecycle:'+key)))
  with self.assertRaisesRegex(PermissionError,'PLATFORM_MERCHANT_TRADING_SUSPENDED'):
   assert_trading(self.center,scope)
  with self.assertRaisesRegex(PermissionError,'PLATFORM_MERCHANT_TRADING_SUSPENDED'):
   client.dispatch(token,{'scene':self.scene,'operation':'prepare','reference':'paused_order'})
  self.reader._fetch.assert_not_called()
 def test_wrong_applyment_owner_or_missing_signed_query_proof_is_rejected(self):
  appid=self.app['application']
  self.center.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",
      (self.fx.fx.fx.uid2,appid))
  with self.assertRaises(PermissionError):self.project()
  self.center.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",
      (self.fx.fx.fx.uid1,appid))
  record=self.applyment._read(appid);record.pop('provider_query_signature_sha256')
  with self.center.tx():self.applyment._save(appid,self.fx.fx.fx.uid1,record)
  with self.assertRaises(PermissionError):self.project()
 def test_cross_store_scope_change_rejects_current_projection(self):
  self.identity.runtime.bindings[self.identity.scenes[self.scene]['principal']]['store_id']='other_store'
  with self.assertRaises(PermissionError):self.project()
 def test_reopen_is_idempotent_and_client_never_supplies_submerchant(self):
  first=self.project()
  self.fx.fx.fx.reopen()
  from scripts.community_merchant_onboarding import MerchantOnboarding
  from scripts.community_center_operations import CenterOperations
  service=MerchantOnboarding(self.fx.fx.fx.center,{self.fx.fx.fx.uid2:'project1'})
  operations=CenterOperations(self.fx.fx.fx.center,self.fx.fx.fx.stage.api,self.fx.grants,onboarding=service)
  service.operations=operations
  applyment=WechatApplyment(service,self.reader,submission_enabled=False);service.wechat_applyment=applyment
  identity=self.fx.fx.fx.identity
  # Existing fixture rebuild supplies the same persistent Center identity after reopen.
  identity.center=self.fx.fx.fx.center
  second=project_wechat_merchants(identity,service,self.reader,self.admissions)
  self.assertEqual(first,second)
  self.assertNotIn('sub_mchid',json.dumps(self.admissions))
 def test_same_application_same_store_scene_replay_is_idempotent_and_missing_admission_rejected(self):
  with self.assertRaises(PermissionError):self.project({})
  self.identity.scenes['shop2']=dict(self.identity.scenes['shop1'])
  result=project_wechat_merchants(self.identity,self.fx.fx.service,self.reader,
      dict(self.admissions,shop2=dict(self.admissions[self.scene])))
  self.assertEqual(result['shop1'],result['shop2'])

if __name__=='__main__':unittest.main()
