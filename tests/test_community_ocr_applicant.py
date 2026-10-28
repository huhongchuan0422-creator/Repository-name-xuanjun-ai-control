"""Real original identity/store/API; inference is explicit synthetic test-only.

Actual model inference is a separate offline image check, not claimed here.
"""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_community_ocr_bridge import load_pinned,OriginalOwner,OwnerHttp,synthetic_inference
from test_community_mini_merchant import ApplicantWithoutStore
from scripts.community_ocr_bridge import compose
from scripts.community_ocr_host import HostOcr

class ApplicantOcr(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.dep,cls.api=load_pinned()
 @classmethod
 def tearDownClass(cls):cls.dep.cleanup()
 def setUp(self):
  self.fx=ApplicantWithoutStore();self.fx.setUp();self.app=self.fx.create();self.raw=b'\x89PNG\r\n\x1a\nSYNTHETIC OCR TRANSPORT TEST ONLY'
  self.fx.fx.center.scanner=lambda raw:True
  self.app=self.fx.applicant('upload',dict(application=self.app['application'],revision=self.app['revision'],kind='business_license',content_base64=base64.b64encode(self.raw).decode(),expires_at=None))
  self.tmp=tempfile.TemporaryDirectory();self.store=self.api.SecureSQLiteJobStore(str(Path(self.tmp.name)/'ocr.sqlite'),Fernet.generate_key())
  self.owner=OriginalOwner();self.bridge,app=compose(self.fx.service,'',self.api,self.store,self.owner,synthetic_inference,applicant_mode=True)
  self.client=OwnerHttp(TestClient(app),self.owner);self.headers={'Authorization':'Bearer '+self.fx.token,'Idempotency-Key':'applicant-test-original-001'}
  self.principal=self.bridge.authenticate(self.fx.token);self.source=self.bridge.source(self.principal,self.app['application'],'business_license')
 def tearDown(self):self.client.close();self.tmp.cleanup();self.fx.tearDown()
 def submit(self):
  return self.client.post('/api/v1/ocr/jobs',headers=self.headers,data=dict(document_type='business_license',onboarding_application_id=self.app['application'],attachment_id=self.source['attachment_id']),files={'file':('synthetic.png',self.raw,'image/png')})
 def job(self):
  r=self.submit();self.assertEqual(r.status_code,202,r.text);return '/api/v1/ocr/jobs/'+r.json()['job_id']
 def test_admitted_applicant_no_fake_merchant_origin_or_grant(self):
  self.assertEqual(self.principal.permissions,{'ocr:use'});self.assertEqual(self.source['tenant_id'],'community-applicant:'+self.fx.fx.uid1)
  self.assertIsNone(self.source['project']);self.assertIsNone(self.source['scope']);self.assertEqual(self.source['scene'],'')
  _,meta,_=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1);self.assertNotIn('ocr_origin',meta)
  self.assertEqual(self.fx.operations.grants.keys(),{'merchant'});self.assertEqual(self.submit().status_code,202)
 def test_real_api_confirmation_bound_to_current_attachment_and_revision(self):
  path=self.job();r=self.client.post(path+'/confirm',headers=self.headers,json=dict(revision=1,application_revision=self.source['application_revision'],provider_version=None,fields={'company_name':'HUMAN CHECKED SYNTHETIC'}))
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.client.get(path,headers=self.headers).json()['status'],'confirmed')
  self.assertNotIn(b'HUMAN CHECKED SYNTHETIC',(Path(self.tmp.name)/'ocr.sqlite').read_bytes())
 def test_other_account_read_confirm_delete_denied(self):
  path=self.job();other=self.fx.fx.token('other-applicant-code','openid2');headers={**self.headers,'Authorization':'Bearer '+other}
  for method,kwargs in [('get',{}),('delete',{}),('post',{'json':dict(revision=1,application_revision=self.source['application_revision'],provider_version=None,fields={'company_name':'WRONG'})})]:
   r=getattr(self.client,method)(path+('/confirm' if method=='post' else ''),headers=headers,**kwargs);self.assertEqual(r.status_code,404,'separate applicant partition must not disclose job existence')
 def test_logout_revokes_read_and_delete(self):
  path=self.job();self.fx.fx.center.logout(self.fx.token)
  for method in ('get','delete'):self.assertEqual(getattr(self.client,method)(path,headers=self.headers).status_code,401)
 def test_epoch_change_revokes_source(self):
  self.fx.fx.center.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.fx.uid1,))
  with self.assertRaises(PermissionError):self.bridge.source(self.principal,self.app['application'],'business_license')
 def test_provider_link_revocation_denied(self):
  self.fx.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(self.fx.fx.uid1,))
  with self.assertRaises(PermissionError):self.bridge.authenticate(self.fx.token)
 def test_plain_web_session_is_not_admitted(self):
  with self.assertRaises(PermissionError):self.bridge.authenticate(self.fx.fx.web1)
 def test_replace_material_rejects_old_job(self):
  path=self.job();self.fx.applicant('upload',dict(application=self.app['application'],revision=self.app['revision'],kind='business_license',content_base64=base64.b64encode(self.raw+b'new').decode(),expires_at=None))
  self.assertEqual(self.client.get(path,headers=self.headers).status_code,403)
 def test_scene_photos_and_unknown_document_never_inferred(self):
  for kind in ('storefront_photo','interior_photo','cashier_photo','passport','id_back'):
   with self.subTest(kind=kind),self.assertRaises(PermissionError):self.bridge.source(self.principal,self.app['application'],kind)
 def test_expiry_and_unclean_scanned_attachment_denied(self):
  c=self.fx.fx.center;c.db.execute("UPDATE objects SET scan='UNKNOWN' WHERE id=?",(self.source['attachment_id'],))
  with self.assertRaises(PermissionError):self.bridge.source(self.principal,self.app['application'],'business_license')
  c.db.execute("UPDATE objects SET scan='CLEAN' WHERE id=?",(self.source['attachment_id'],));_,meta,_=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1);meta['materials']['business_license']['expires_at']=c.now()-1
  with c.tx():self.fx.onboarding._meta(self.app['application'],self.fx.fx.uid1,meta)
  with self.assertRaises(PermissionError):self.bridge.source(self.principal,self.app['application'],'business_license')
 def test_current_original_gateway_path_and_invalid_nonempty_scene(self):
  create=self.api.create_app
  def test_app(**kw):return create(**kw,infer=synthetic_inference)
  with patch.object(self.api,'create_app',side_effect=test_app):host=HostOcr(self.fx.service,'',self.api,self.store,applicant_mode=True)
  self.fx.service.ocr=host
  try:
   body=dict(operation='ocr',params=dict(action='submit',application=self.app['application'],document_type='business_license',idempotency_key='host-applicant-test-001'))
   self.assertEqual(self.fx.service.dispatch(self.fx.token,'',body)['status_code'],202)
   for scene in ('unknown','../invalid'):
    with self.assertRaises(PermissionError):self.fx.service.dispatch(self.fx.token,scene,body)
   for op in ('workspaces','read','write','collection_code'):
    with self.assertRaises(PermissionError):self.fx.service.dispatch(self.fx.token,'',dict(operation=op,params={}))
  finally:host.close()
 def test_default_mode_cannot_admit_projectless_applicant(self):
  with self.assertRaises(PermissionError):compose(self.fx.service,'',self.api,self.store,self.owner)
  for value in ('true',1,None):
   with self.assertRaises(PermissionError):compose(self.fx.service,'',self.api,self.store,self.owner,applicant_mode=value)


 def test_actual_mini_http_to_original_asgi_owned_application(self):
  import concurrent.futures,json,urllib.request
  from scripts.community_mini_http import serve
  create=self.api.create_app
  def test_app(**kw):return create(**kw,infer=synthetic_inference)
  with patch.object(self.api,'create_app',side_effect=test_app):host=HostOcr(self.fx.service,'',self.api,self.store,applicant_mode=True)
  self.fx.fx.gateway.ocr=host
  server=serve(self.fx.fx.gateway,onboarding=self.fx.onboarding,operations=self.fx.operations)
  try:
   raw=json.dumps(dict(operation='ocr',params=dict(action='submit',application=self.app['application'],document_type='business_license',idempotency_key='http-applicant-test-0001'))).encode()
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',data=raw,headers={'Content-Type':'application/json','X-Community-Session':self.fx.token})
   def read():
    with urllib.request.urlopen(req,timeout=4) as response:return response.status,json.load(response)
   with concurrent.futures.ThreadPoolExecutor(1) as pool:
    future=pool.submit(read);server.handle_request();code,body=future.result()
   self.assertEqual(code,200);self.assertIs(body['payment_enabled'],False);self.assertEqual(body['result']['status_code'],202)
   self.assertEqual(body['result']['result']['status'],'needs_review')
  finally:server.server_close();host.close();self.fx.fx.gateway.ocr=None

class ProtectedOriginalHostInputs(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.dep,cls.api=load_pinned()
 @classmethod
 def tearDownClass(cls):cls.dep.cleanup()
 def setUp(self):
  import test_community_platform_host as fixture
  self.fx=fixture.FormalHost();self.fx.setUp();self.host=self.fx.open()
  self.key=Fernet.generate_key();self.key_path=self.fx.write('test-only-ocr-key.json',{'ocr_encryption_key':self.key.decode()})
  self.db_path=self.fx.root/'test-only-ocr.sqlite'
  self.store=self.api.SecureSQLiteJobStore(str(self.db_path),self.key)
 def tearDown(self):self.host.close();self.fx.doCleanups()
 def test_missing_store_never_created(self):
  missing=self.fx.root/'absent-ocr.sqlite'
  with self.assertRaises((OSError,PermissionError)):self.host.configure_applicant_ocr(str(self.key_path),str(missing))
  self.assertFalse(missing.exists());self.assertIsNone(self.host.ocr)
 def test_center_database_never_reused(self):
  with self.assertRaisesRegex(PermissionError,'OCR_SEPARATE_STORE_REQUIRED'):
   self.host.configure_applicant_ocr(str(self.key_path),str(Path(self.host.plan['center_root'])/'center.sqlite'))
 def test_existing_center_key_shape_never_reused(self):
  with self.assertRaisesRegex(ValueError,'EXISTING_OCR_KEY_REFERENCE_REQUIRED'):
   self.host.configure_applicant_ocr(str(self.fx.keys_path),str(self.db_path))
 def test_symlink_key_denied_before_read(self):
  link=self.fx.root/'linked-key.json';link.symlink_to(self.key_path)
  with self.assertRaises(PermissionError):self.host.configure_applicant_ocr(str(link),str(self.db_path))
 def test_exact_existing_store_uses_original_api_and_host_lock(self):
  import types,sys,fcntl,os
  core=sys.modules[self.api.__package__+'.ocr_core'];package=types.ModuleType('services.ocr_engine');package.api=self.api;package.ocr_core=core
  # Only model availability is stubbed here; exact original core file pin is
  # still checked. Real model hashes/inference are the offline image check.
  with patch.dict(sys.modules,{'services':types.ModuleType('services'),'services.ocr_engine':package}),patch.object(core,'_verified_model_paths',return_value={}):
   service=self.host.configure_applicant_ocr(str(self.key_path),str(self.db_path))
  self.assertTrue(service.applicant_mode);self.assertEqual(service.scene,'')
  fd=os.open(self.db_path,os.O_RDWR)
  try:
   with self.assertRaises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.host.close();fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  finally:os.close(fd)
 def test_extra_key_fields_are_not_a_permission_channel(self):
  path=self.fx.write('wrong-ocr-key.json',dict(ocr_encryption_key=self.key.decode(),role='ADMIN'))
  with self.assertRaisesRegex(ValueError,'EXISTING_OCR_KEY_REFERENCE_REQUIRED'):self.host.configure_applicant_ocr(str(path),str(self.db_path))

if __name__=='__main__':unittest.main()
