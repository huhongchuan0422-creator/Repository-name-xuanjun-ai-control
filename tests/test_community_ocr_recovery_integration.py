"""Actual pinned API/store + Center recovery, only synthetic inference/materials."""
import unittest
from test_community_ocr_shared_composition import SharedOcrComposition
class RecoveryIntegration(SharedOcrComposition):
 def setUp(self):
  super().setUp()
  from test_community_ocr_bridge import OwnerHttp,synthetic_inference
  from fastapi.testclient import TestClient
  self.client.close()
  def recovery(operation,p,body):return getattr(self.bridge,'recovery_'+operation)(p,**body)
  self.client=OwnerHttp(TestClient(self.api.create_app(authenticate=self.auth,store=self.store,infer=synthetic_inference,authorize_application=self.bridge.authorize_application,authorize_attachment=self.bridge.authorize_attachment,recovery=recovery)),self.owner)
 def recovery_call(self,operation,body):return self.client.post('/api/v1/ocr/recovery/'+operation,headers=self.headers,json=body)
 def test_current_view_confirm_writeback_original_job_unchanged(self):
  path=self.job();job_id=path.rsplit('/',1)[1];old=self.store.get(job_id,self.source['tenant_id'])
  self.provider_edit()
  self.assertEqual(self.read(path).status_code,403)
  view=self.recovery_call('view',dict(application=self.app['application'],document_type='business_license',locator={'job_id':job_id},recovery_key='recovery-one'))
  self.assertEqual(view.status_code,200,view.text);v=view.json();self.assertFalse(v['confirmed']);self.assertEqual(v['binding']['provider_version'],self.source['wechat_version']+1)
  confirm=self.recovery_call('confirm',dict(application=self.app['application'],recovery_id='recovery-one',revision=1,fields={'company_name':'CURRENT HUMAN','credit_code':'SYNTHETIC CODE','legal_representative':'SYNTHETIC PERSON','registered_address':'CURRENT ADDRESS'},confirmation_key='confirmation-one'))
  self.assertEqual(confirm.status_code,200,confirm.text)
  saved=self.recovery_call('apply',dict(application=self.app['application'],recovery_id='recovery-one',confirmation_id='confirmation-one',confirmation_revision=1,writeback_key='writeback-one'))
  self.assertEqual(saved.status_code,200,saved.text);self.assertTrue(saved.json()['written'])
  before=self.snapshot();replay=self.recovery_call('apply',dict(application=self.app['application'],recovery_id='recovery-one',confirmation_id='confirmation-one',confirmation_revision=1,writeback_key='writeback-one'))
  self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(saved.json(),replay.json());self.assertEqual(before,self.snapshot())
  self.assertEqual(old,self.store.get(job_id,self.source['tenant_id']))
 def test_saved_old_draft_corrected_by_real_recovery_http_clears_only_confirmed_key(self):
  path=self.job();job_id=path.rsplit('/',1)[1];old=self.store.get(job_id,self.source['tenant_id'])
  r=self.wechat._read(self.app['application'])
  self.fx.call('onboarding',{'operation':'wechat_save','params':dict(application=self.app['application'],expected_version=r['version'],profile=r['profile'],application_revision=int(self.source['application_revision']),ocr_drafts={'business_license':{'fields':{'company_name':'OLD SAVED SUGGESTION','registered_address':'UNCONFIRMED ADDRESS'}}})})
  view=self.recovery_call('view',dict(application=self.app['application'],document_type='business_license',locator={'current_material':True},recovery_key='corrected-draft-view'))
  self.assertEqual(view.status_code,200,view.text)
  confirm=self.recovery_call('confirm',dict(application=self.app['application'],recovery_id='corrected-draft-view',revision=1,fields={'company_name':'NEW HUMAN CORRECTION'},confirmation_key='corrected-draft-confirm'))
  self.assertEqual(confirm.status_code,200,confirm.text)
  payload=dict(application=self.app['application'],recovery_id='corrected-draft-view',confirmation_id='corrected-draft-confirm',confirmation_revision=1,writeback_key='corrected-draft-writeback')
  saved=self.recovery_call('apply',payload);self.assertEqual(saved.status_code,200,saved.text)
  record=self.wechat._read(self.app['application'])
  self.assertEqual(record['profile']['subject_info']['business_license_info']['merchant_name'],'NEW HUMAN CORRECTION')
  self.assertEqual(record['ocr_drafts']['business_license']['fields'],{'registered_address':'UNCONFIRMED ADDRESS'})
  before=self.snapshot();replay=self.recovery_call('apply',payload)
  self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(saved.json(),replay.json());self.assertEqual(before,self.snapshot())
  self.assertEqual(old,self.store.get(job_id,self.source['tenant_id']))

 def test_api_material_lookup_without_pointer_or_inference(self):
  path=self.job();job_id=path.rsplit('/',1)[1];old=self.store.get(job_id,self.source['tenant_id'])
  self.provider_edit()
  response=self.recovery_call('view',dict(application=self.app['application'],document_type='business_license',locator={'current_material':True},recovery_key='cold-view'))
  self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['job_id'],job_id)
  self.assertFalse(response.json()['confirmed']);self.assertEqual(old,self.store.get(job_id,self.source['tenant_id']))
  for field in ['subject','tenant_id','onboarding_application_id']:self.assertNotIn(field,response.json())
 def test_stale_recovery_confirmation_cannot_be_promoted(self):
  job_id=self.job().rsplit('/',1)[1]
  r=self.recovery_call('view',dict(application=self.app['application'],document_type='business_license',locator={'job_id':job_id},recovery_key='v2'));self.assertEqual(r.status_code,200,r.text)
  self.provider_edit()
  r=self.recovery_call('confirm',dict(application=self.app['application'],recovery_id='v2',revision=1,fields={'company_name':'HUMAN'},confirmation_key='c2'))
  self.assertEqual(r.status_code,403,r.text);self.assertIsNone(self.store.recovery_receipt(self.source['tenant_id'],self.source['subject'],'confirm','c2'))
 def test_host_dispatch_recovery_same_job_without_inference(self):
  from unittest.mock import patch
  from scripts.community_ocr_host import HostOcr
  from test_community_ocr_bridge import TestAdmission
  jobid=self.job().rsplit('/',1)[1];old=self.store.get(jobid,self.source['tenant_id']);self.provider_edit()
  create=self.api.create_app
  calls=[]
  def configured(**options):
   original=options['authenticate']
   def admitted(token):
    p=original(token);p.permissions={'ocr:use'};return p
   options['authenticate']=admitted
   def no_inference(*args,**kwargs):calls.append(True);raise AssertionError('RECOVERY_MUST_NOT_INFER')
   options['infer']=no_inference
   return create(**options)
  with patch.object(self.api,'create_app',side_effect=configured):host=HostOcr(self.fx.service,'shop1',self.api,self.store)
  original=host.bridge.authenticate
  def admitted(token):
   p=original(token);p.permissions={'ocr:use'};return p
  host.bridge.authenticate=admitted
  try:
   common=dict(application=self.app['application'])
   v=host.dispatch(self.fx.token,'shop1',dict(common,action='recover_view',document_type='business_license',locator={'current_material':True},recovery_key='host-view'))
   self.assertEqual(v['status_code'],200);self.assertEqual(v['result']['job_id'],jobid)
   c=host.dispatch(self.fx.token,'shop1',dict(common,action='recover_confirm',recovery_id='host-view',revision=1,fields={'company_name':'HOST HUMAN'},confirmation_key='host-confirm'))
   self.assertEqual(c['status_code'],200)
   a=host.dispatch(self.fx.token,'shop1',dict(common,action='recover_apply',recovery_id='host-view',confirmation_id='host-confirm',confirmation_revision=1,writeback_key='host-save'))
   self.assertTrue(a['result']['written']);self.assertEqual(calls,[])
   self.assertEqual(old,self.store.get(jobid,self.source['tenant_id']))
  finally:host.close()
 def test_host_cold_completed_future_rechecks_uniqueness(self):
  from unittest.mock import patch
  from scripts.community_ocr_host import HostOcr
  from test_community_ocr_bridge import TestAdmission
  jobid=self.job().rsplit('/',1)[1];old=self.store.get(jobid,self.source['tenant_id']);self.provider_edit()
  create=self.api.create_app
  calls=[]
  def configured(**options):
   original=options['authenticate']
   def admitted(token):
    p=original(token);p.permissions={'ocr:use'};return p
   options['authenticate']=admitted
   def no_inference(*args,**kwargs):calls.append(True);raise AssertionError('RECOVERY_MUST_NOT_INFER')
   options['infer']=no_inference
   return create(**options)
  with patch.object(self.api,'create_app',side_effect=configured):host=HostOcr(self.fx.service,'shop1',self.api,self.store)
  original=host.bridge.authenticate
  def admitted(token):
   p=original(token);p.permissions={'ocr:use'};return p
  host.bridge.authenticate=admitted
  try:
   import time
   from scripts.community_ocr_host import OcrPublicError
   params=dict(application=self.app['application'],action='recover_view',document_type='business_license',locator={'current_material':True},recovery_key='late-unique')
   submit=host.worker.submit;completed=[]
   def slow(fn,*args,**kwargs):
    def delayed():
     response=fn(*args,**kwargs);completed.append(response.status_code);time.sleep(6);return response
    return submit(delayed)
   with patch.object(host.worker,'submit',side_effect=slow),self.assertRaises(PermissionError) as cm:host.dispatch(self.fx.token,'shop1',params)
   self.assertEqual(str(cm.exception),'OCR_REQUEST_PENDING')
   deadline=time.monotonic()+8
   while time.monotonic()<deadline:host.service_actions();time.sleep(.05)
   self.assertEqual(completed,[200]);self.assertTrue(host.inflight.done())
   self.store.create(old['tenant_id'],old['subject'],old['onboarding_application_id'],old['document_type'],old['document_sha256'],'late-second-key',old['attachment_id'],old['application_revision'],old.get('provider_version'))
   with self.assertRaisesRegex(ValueError,'OCR_RECOVERY_MATERIAL_AMBIGUOUS') as cm:host.dispatch(self.fx.token,'shop1',params)
   self.assertEqual(cm.exception.ocr_diagnostic['reason'],'IDEMPOTENCY_CONFLICT')
   self.assertEqual(calls,[]);self.assertEqual(old,self.store.get(jobid,self.source['tenant_id']))
  finally:host.close()
if __name__=='__main__':unittest.main()
