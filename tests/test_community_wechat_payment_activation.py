"""Verified applyment -> existing MiniPayments startup projection; synthetic only."""
import json,unittest
import test_community_merchant_opening as opening_fixture
import test_community_wechat_sp_readonly as key_fixture
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_payment_activation import project_wechat_merchants
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
          'provider_sp_mchid':sp_mchid}
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
 def test_application_mapping_conflict_and_missing_admission_rejected(self):
  with self.assertRaises(PermissionError):self.project({})
  # A second scene pointing at the same opened application must not silently reuse it.
  self.identity.scenes['shop2']=dict(self.identity.scenes['shop1'])
  with self.assertRaises(PermissionError):
   project_wechat_merchants(self.identity,self.fx.fx.service,self.reader,
      dict(self.admissions,shop2=dict(self.admissions[self.scene])))

if __name__=='__main__':unittest.main()
