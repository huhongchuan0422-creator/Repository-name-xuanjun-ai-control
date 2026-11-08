"""H5 -> original host -> pinned API/store -> Center. Synthetic test admission/inference only."""
import unittest
from unittest.mock import patch
from email.message import Message
from test_community_ocr_shared_composition import SharedOcrComposition
from test_community_ocr_bridge import synthetic_inference
from scripts.community_ocr_host import HostOcr
from scripts.community_mini_merchant import MiniMerchant
from scripts.community_h5 import H5
class H5Ocr(unittest.TestCase):
 @classmethod
 def setUpClass(cls):SharedOcrComposition.setUpClass();cls.api=SharedOcrComposition.api
 @classmethod
 def tearDownClass(cls):SharedOcrComposition.tearDownClass()
 def setUp(self):
  self.fx=SharedOcrComposition();self.fx.setUp();f=self.fx.fx;self.inferences=0
  create=self.api.create_app
  def configured(**options):
   original=options['authenticate']
   def admitted(token):
    p=original(token);p.permissions={'ocr:use'};return p
   def infer(*args,**kwargs):self.inferences+=1;return synthetic_inference(*args,**kwargs)
   options.update(authenticate=admitted,infer=infer);return create(**options)
  with patch.object(self.api,'create_app',side_effect=configured):self.host=HostOcr(f.service,'shop1',self.api,self.fx.store)
  original=self.host.bridge.authenticate
  def admitted(token):
   p=original(token);p.permissions={'ocr:use'};return p
  self.host.bridge.authenticate=admitted
  self.h5=H5(f.fx.gateway,f.onboarding,MiniMerchant(f.fx.identity,f.onboarding,f.operations,ocr=self.host))
  self.headers=self.login('one@example.org')
 def login(self,email):
  r,c=self.h5.dispatch('/h5/session/login',Message(),{'email':email,'password':'FixturePassword123!'})
  h=Message();h['Cookie']=c.split(';')[0];h['X-CSRF-Token']=r['csrf'];return h
 def tearDown(self):self.host.close();self.fx.tearDown()
 def call(self,action,headers=None,**kw):
  r,_=self.h5.dispatch('/h5/merchant',headers or self.headers,{'scene':'shop1','operation':'ocr','params':{'action':action,'application':self.fx.app['application'],**kw}});return r['result']
 def job(self):
  r=self.call('submit',document_type='business_license',idempotency_key='synthetic-h5-ocr-01');return r['job_id']
 def test_submit_confirm_writeback_and_other_account_denial(self):
  job=self.job();seen=self.call('read',job_id=job)
  self.call('confirm',job_id=job,revision=1,fields={'company_name':'H5 HUMAN','registered_address':'H5 ADDRESS'},application_revision=seen['application_revision'],provider_version=seen['provider_version'],idempotency_key='synthetic-h5-confirm-01')
  saved=self.call('apply_confirmed',job_id=job,confirmation_revision=1);self.assertTrue(saved['written'])
  data=self.fx.fx.onboarding._load(self.fx.app['application'],self.fx.fx.fx.uid1)[2];self.assertEqual(data['fields']['legal_name'],'H5 HUMAN')
  other=self.login('two@example.org')
  for action,params in [('read',{'job_id':job}),('apply_confirmed',{'job_id':job,'confirmation_revision':1}),('recover_view',{'document_type':'business_license','locator':{'job_id':job},'recovery_key':'other-view'})]:
   with self.assertRaises(PermissionError):self.call(action,headers=other,**params)
  self.assertEqual(self.inferences,1)
 def test_recovery_confirm_writeback_without_reinference(self):
  job=self.job();old=self.fx.store.get(job,self.fx.source['tenant_id']);self.fx.provider_edit()
  view=self.call('recover_view',document_type='business_license',locator={'current_material':True},recovery_key='h5-view');self.assertEqual(view['job_id'],job)
  self.call('recover_confirm',recovery_id='h5-view',revision=1,fields={'company_name':'H5 RECOVERY'},confirmation_key='h5-confirm')
  result=self.call('recover_apply',recovery_id='h5-view',confirmation_id='h5-confirm',confirmation_revision=1,writeback_key='h5-save');self.assertTrue(result['written'])
  replay=self.call('recover_apply',recovery_id='h5-view',confirmation_id='h5-confirm',confirmation_revision=1,writeback_key='h5-save');self.assertEqual(result,replay)
  self.assertEqual(old,self.fx.store.get(job,self.fx.source['tenant_id']));self.assertEqual(self.inferences,1)
