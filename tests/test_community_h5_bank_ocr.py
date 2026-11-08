"""Synthetic bank image/inference, real original source/confirmation/writeback boundaries."""
import unittest,base64
from unittest.mock import patch
from test_community_h5_ocr import H5Ocr
class BankOcr(unittest.TestCase):
 @classmethod
 def setUpClass(cls):H5Ocr.setUpClass()
 @classmethod
 def tearDownClass(cls):H5Ocr.tearDownClass()
 def setUp(self):
  self.p=patch('test_community_h5_ocr.synthetic_inference',return_value={'fields':{'account_number':{'value':'SYNTHETIC ACCOUNT','confidence':.5},'account_bank':{'value':'SYNTHETIC BANK','confidence':.5}}});self.p.start();self.addCleanup(self.p.stop)
  self.f=H5Ocr();self.f.setUp();self.addCleanup(self.f.tearDown)
  self.f.h5.onboarding.center.scanner=lambda raw:True
  app=self.f.fx.app
  self.merchant('upload',application=app['application'],revision=app['revision'],kind='bank_card',content_base64=base64.b64encode(b'\x89PNG\r\n\x1a\nSynthetic bank only').decode(),expires_at=None)
 def merchant(self,operation,**kw):
  return self.f.h5.dispatch('/h5/merchant',self.f.headers,{'scene':'shop1','operation':'onboarding','params':{'operation':operation,'params':kw}})[0]
 def job(self):return self.f.call('submit',document_type='bank_card',idempotency_key='synthetic-bank-01')['job_id']
 def test_confirm_fill_and_cross_account_denial(self):
  j=self.job();seen=self.f.call('read',job_id=j)
  self.assertNotIn('bank_account_info',self.f.fx.wechat._read(self.f.fx.app['application'])['profile'])
  with self.assertRaises(PermissionError):self.f.call('apply_confirmed',job_id=j,confirmation_revision=1)
  self.f.call('confirm',job_id=j,revision=1,fields={'account_number':'SYNTHETIC HUMAN','account_bank':'SYNTHETIC BANK'},application_revision=seen['application_revision'],provider_version=seen['provider_version'],idempotency_key='synthetic-bank-confirm')
  self.assertTrue(self.f.call('apply_confirmed',job_id=j,confirmation_revision=1)['written'])
  profile=self.f.fx.wechat._read(self.f.fx.app['application'])['profile'];self.assertEqual(profile['bank_account_info'],{'account_number':'SYNTHETIC HUMAN','account_bank':'SYNTHETIC BANK'})
  other=self.f.login('two@example.org')
  with self.assertRaises(PermissionError):self.f.call('read',headers=other,job_id=j)
 def test_media_stays_closed(self):
  with self.assertRaisesRegex(PermissionError,'BANK_CARD_PRIVATE_PREVIEW_ONLY'):self.merchant('wechat_media',application=self.f.fx.app['application'],kind='bank_card')
 def test_existing_bank_fields_are_not_overwritten(self):
  app=self.f.fx.app['application'];record=self.f.fx.wechat._read(app);record['profile']['bank_account_info']={'account_number':'ORIGINAL MANUAL','account_bank':'ORIGINAL BANK','account_name':'ORIGINAL HOLDER'}
  self.f.fx.wechat._save(app,self.f.fx.fx.fx.uid1,record)
  j=self.job();seen=self.f.call('read',job_id=j)
  self.f.call('confirm',job_id=j,revision=1,fields={'account_number':'NEW SUGGESTION','account_bank':'NEW BANK'},application_revision=seen['application_revision'],provider_version=seen['provider_version'],idempotency_key='synthetic-existing-confirm')
  result=self.f.call('apply_confirmed',job_id=j,confirmation_revision=1);self.assertFalse(result['written']);self.assertEqual(self.f.fx.wechat._read(app)['profile']['bank_account_info'],record['profile']['bank_account_info'])
