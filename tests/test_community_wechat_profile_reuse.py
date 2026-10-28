"""Same original application/profile reuse; synthetic private materials only."""
import copy
import unittest
from scripts.community_merchant_onboarding import shared_application_fields
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts import community_onboarding_offline as workflow
from test_community_applyment_conditions import profile
import test_community_merchant_onboarding as fixture

class SameProfileReuse(unittest.TestCase):
 def setUp(self):
  self.fx=fixture.MerchantAdmissionJourney();self.fx.setUp()
  self.service=WechatApplyment(self.fx.service,PartnerOrderReader.__new__(PartnerOrderReader),submission_enabled=False)
  self.fx.service.wechat_applyment=self.service
 def tearDown(self):self.fx.tearDown()
 def save(self,p):
  app=self.fx.draft(fields=dict(legal_name='',store_name='',address='',contact=''),sales_scenes_type=p['business_info']['sales_info']['sales_scenes_type'])
  self.fx.call('wechat_save',dict(application=app['application'],expected_version=0,profile=p))
  return self.fx.call('read',dict(application=app['application']))
 def complete_materials(self,app):
  for kind in app['required_materials']:app=self.fx.upload(app,kind)
  return app
 def test_mini_only_same_official_profile_no_extra_address(self):
  p=profile();app=self.save(p)
  self.assertEqual(app['fields'],dict(legal_name='Fixture Company',store_name='Fixture Shop',address='',contact='13800000000'))
  self.service._validate(p,'ENTERPRISE') # original complete official validation
  app=self.complete_materials(app)
  result=self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
  self.assertEqual(result['status'],'SUBMITTED')
  self.assertFalse(result['payment_enabled'])
  self.assertEqual(self.fx.fx.center.check_integrity()['integrity'],'PASS')
 def test_store_uses_only_official_store_fields(self):
  p=profile();p['business_info']['sales_info'].update(sales_scenes_type=['SALES_SCENES_MINI_PROGRAM','SALES_SCENES_STORE'],biz_store_info=dict(biz_store_name='Actual Store',biz_store_address='Actual Store Address'))
  app=self.save(p);self.assertEqual(app['fields']['store_name'],'Actual Store');self.assertEqual(app['fields']['address'],'Actual Store Address')
 def test_store_missing_address_still_rejected(self):
  p=profile();p['business_info']['sales_info'].update(sales_scenes_type=['SALES_SCENES_MINI_PROGRAM','SALES_SCENES_STORE'],biz_store_info=dict(biz_store_name='Actual Store'))
  app=self.complete_materials(self.save(p))
  with self.assertRaisesRegex(ValueError,'MISSING_REQUIRED'):self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
 def test_mini_missing_contact_or_name_still_rejected(self):
  for section,key in [('contact_info','mobile_phone'),('business_info','merchant_shortname')]:
   p=profile();p[section].pop(key);app=self.complete_materials(self.save(p))
   with self.assertRaisesRegex(ValueError,'MISSING_REQUIRED'):self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
 def test_no_wechat_draft_cannot_omit_legacy_address(self):
  app=self.complete_materials(self.fx.draft(fields=dict(self.fx.fields,address=''),sales_scenes_type=['SALES_SCENES_MINI_PROGRAM']))
  with self.assertRaisesRegex(ValueError,'MISSING_REQUIRED'):self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
 def test_missing_scanned_material_still_rejected(self):
  app=self.save(profile())
  with self.assertRaisesRegex(ValueError,'MATERIAL_MISSING'):self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
 def test_cross_account_and_stale_revision_still_denied(self):
  app=self.complete_materials(self.save(profile()))
  with self.assertRaises(PermissionError):self.fx.call('submit',dict(application=app['application'],revision=app['revision']),review=True)
  with self.assertRaisesRegex(ValueError,'REVISION_CONFLICT'):self.fx.call('submit',dict(application=app['application'],revision=app['revision']-1))
 def test_invalid_source_types_and_unknown_scene_rejected(self):
  p=profile();p['business_info']['merchant_shortname']={'bad':'shape'}
  with self.assertRaisesRegex(ValueError,'INVALID_SHARED'):shared_application_fields(p,self.fx.fields)
  p=profile();p['business_info']['sales_info']['sales_scenes_type']=['made-up']
  with self.assertRaises(ValueError):shared_application_fields(p,self.fx.fields)
 def test_old_draft_without_scene_does_not_lose_fields(self):
  self.assertEqual(shared_application_fields({},self.fx.fields),self.fx.fields)
 def test_client_cannot_supply_required_field_policy(self):
  app=self.save(profile())
  with self.assertRaises(ValueError):self.fx.call('submit',dict(application=app['application'],revision=app['revision'],required_fields=[]))
 def test_low_level_policy_cannot_remove_other_required_fields(self):
  app=self.save(profile())
  with self.assertRaisesRegex(ValueError,'INVALID_REQUIRED_FIELDS'):
   workflow.transition(self.fx.fx.center.db,self.fx.fx.uid1,app['application'],self.fx.fx.uid1,'MERCHANT','SUBMIT',app['revision'],required_fields=())

if __name__=='__main__':unittest.main()
