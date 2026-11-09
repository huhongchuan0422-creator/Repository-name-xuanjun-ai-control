"""Original encrypted application only; synthetic values, no provider requests."""
import unittest
from unittest.mock import patch
from test_community_shared_license_cas import SharedLicenseCas

class PrivateDraftIntegration(SharedLicenseCas):
 def setUp(self):
  super().setUp()
  self.app=self.fx.upload(self.app,'business_license')
  self.rev=self.app['revision']
 def save_private(self,**changes):
  p=dict(application=self.app['application'],expected_version=self.version,profile=self.service._read(self.app['application'])['profile'],application_revision=self.rev,ocr_drafts={'business_license':{'fields':{'company_name':'SYNTHETIC CONFIRMED','registered_address':'SYNTHETIC ADDRESS'}}})
  p.update(changes)
  return self.fx.call('wechat_save',p)
 def test_private_roundtrip_and_legacy_omission_preserves(self):
  r=self.save_private();self.version=r['version']
  self.assertNotIn('merchant_name',r['profile']['subject_info']['business_license_info'])
  self.assertTrue(r['ocr_drafts']['business_license']['needs_confirmation'])
  read=self.fx.call('wechat_read',{'application':self.app['application']})
  self.assertEqual(read['ocr_drafts'],r['ocr_drafts'])
  saved=self.fx.call('wechat_save',dict(application=self.app['application'],expected_version=self.version,profile=r['profile']))
  self.assertEqual(saved['ocr_drafts'],r['ocr_drafts'])
 def test_unconfirmed_cannot_upload_or_apply(self):
  r=self.save_private()
  with patch('scripts.community_wechat_applyment.request',side_effect=AssertionError('NO NETWORK')) as network:
   for op,params in [('wechat_media',{'kind':'business_license'}),('wechat_apply',{'expected_version':r['version']})]:
    with self.assertRaisesRegex(ValueError,'OCR_DRAFT_CONFIRMATION_REQUIRED'):
     self.fx.call(op,dict(application=self.app['application'],**params))
   network.assert_not_called()
 def test_stale_application_no_draft_write(self):
  before=self.service._read(self.app['application'])
  with self.assertRaisesRegex(ValueError,'PRIVATE_OCR_DRAFT_APPLICATION_CHANGED'):self.save_private(application_revision=self.rev-1)
  self.assertEqual(before,self.service._read(self.app['application']))
 def test_server_confirmed_writeback_atomically_clears_matching_private_fields(self):
  r=self.save_private();self.version=r['version']
  self.rev=self.platform()['revision']
  result=self.call()
  self.assertTrue(result['written'])
  saved=self.service._read(self.app['application'])
  self.assertEqual({},saved['ocr_drafts'])
  self.assertEqual('SYNTHETIC CONFIRMED',saved['profile']['subject_info']['business_license_info']['merchant_name'])
 def test_partial_human_confirmation_keeps_other_material_and_unconfirmed_fields(self):
  self.app=self.fx.upload(self.app,'identity_front')
  self.rev=self.app['revision']
  drafts={'business_license':{'fields':{'company_name':'SYNTHETIC CONFIRMED','registered_address':'SYNTHETIC ADDRESS'}},'id_front':{'fields':{'id_name':'SYNTHETIC PERSON'}}}
  r=self.save_private(ocr_drafts=drafts);self.version=r['version']
  self.rev=self.platform()['revision']
  self.call(confirmed_fields={'company_name':'SYNTHETIC CONFIRMED'})
  saved=self.fx.call('wechat_read',{'application':self.app['application']})
  self.assertEqual(saved['ocr_drafts']['business_license']['fields'],{'registered_address':'SYNTHETIC ADDRESS'})
  self.assertEqual(saved['ocr_drafts']['id_front']['fields'],{'id_name':'SYNTHETIC PERSON'})
  self.assertEqual(saved['profile']['subject_info']['business_license_info']['merchant_name'],'SYNTHETIC CONFIRMED')
  again=self.fx.call('wechat_save',dict(application=self.app['application'],expected_version=saved['version'],profile=saved['profile']))
  self.assertEqual(again['ocr_drafts'],saved['ocr_drafts'])

 def test_corrected_confirmation_resolves_old_suggestion_and_survives_reread(self):
  r=self.save_private();self.version=r['version'];self.rev=self.platform()['revision']
  self.call(confirmed_fields={'company_name':'NEW HUMAN CORRECTION'})
  saved=self.fx.call('wechat_read',{'application':self.app['application']})
  self.assertEqual(saved['profile']['subject_info']['business_license_info']['merchant_name'],'NEW HUMAN CORRECTION')
  self.assertEqual(saved['ocr_drafts']['business_license']['fields'],{'registered_address':'SYNTHETIC ADDRESS'})
  again=self.fx.call('wechat_save',dict(application=self.app['application'],expected_version=saved['version'],profile=saved['profile']))
  self.assertEqual(again['ocr_drafts'],saved['ocr_drafts'])

 def test_newer_private_edit_cannot_be_cleared_by_old_confirmation_version(self):
  r=self.save_private();self.version=r['version'];self.rev=self.platform()['revision']
  newer=self.save_private(ocr_drafts={'business_license':{'fields':{'company_name':'NEWER UNSUBMITTED EDIT'}}})
  before=self.snapshot()
  with self.assertRaises(ValueError):self.call(confirmed_fields={'company_name':'OLDER CONFIRMATION'})
  self.assertEqual(before,self.snapshot())
  self.assertEqual(self.service._read(self.app['application'])['ocr_drafts'],newer['ocr_drafts'])

 def test_replaced_material_not_reused(self):
  self.save_private()
  self.app=self.fx.upload(self.app,'business_license',raw=b'%PDF-replacement synthetic')
  read=self.fx.call('wechat_read',{'application':self.app['application']})
  self.assertEqual({},read['ocr_drafts'])

if __name__=='__main__':unittest.main()
