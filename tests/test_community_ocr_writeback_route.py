"""Real pinned encrypted OCR store/Center CAS; synthetic admission and images only."""
import unittest
import sqlite3
from unittest.mock import patch
from test_community_ocr_shared_composition import SharedOcrComposition
from scripts.community_ocr_host import HostOcr
class Writeback(unittest.TestCase):
 setUpClass=classmethod(SharedOcrComposition.setUpClass.__func__)
 tearDownClass=classmethod(SharedOcrComposition.tearDownClass.__func__)
 setUp=SharedOcrComposition.setUp;tearDown=SharedOcrComposition.tearDown
 submit=SharedOcrComposition.submit;job=SharedOcrComposition.job;read=SharedOcrComposition.read;confirm=SharedOcrComposition.confirm;snapshot=SharedOcrComposition.snapshot;apply=SharedOcrComposition.apply
 def id_job(self,existing=None,doctype='IDENTIFICATION_TYPE_IDCARD'):
  provider=self.wechat._read(self.app['application']);profile=provider['profile'];profile['subject_info']['identity_info']={'id_doc_type':doctype,'id_card_info':existing or {}}
  self.fx.call('onboarding',{'operation':'wechat_save','params':dict(application=self.app['application'],expected_version=provider['version'],profile=profile)})
  current=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]
  self.app=self.fx.material({'application':self.app['application'],'revision':current['revision']},kind='identity_front')
  self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'id_front')
  response=self.submit(document_type='id_front');self.assertEqual(response.status_code,202,response.text)
  path='/api/v1/ocr/jobs/'+response.json()['job_id'];reply=self.confirm(path,fields={'id_name':'SYNTHETIC NAME','id_number':'SYNTHETIC NUMBER','registered_address':'SYNTHETIC ADDRESS'});self.assertEqual(reply.status_code,200,reply.text)
  return path
 def test_identity_fills_exact_original_encrypted_target(self):
  path=self.id_job();out=self.apply(path);self.assertTrue(out['written'])
  card=self.wechat._read(self.app['application'])['profile']['subject_info']['identity_info']['id_card_info'];self.assertEqual(card,{'id_card_name':'SYNTHETIC NAME','id_card_number':'SYNTHETIC NUMBER','id_card_address':'SYNTHETIC ADDRESS'})
  before=self.snapshot()
  with self.assertRaises((PermissionError,ValueError)):self.apply(path)
  self.assertEqual(self.snapshot(),before)
 def test_manual_identity_never_overwritten(self):
  path=self.id_job({'id_card_name':'MANUAL NAME','id_card_number':'MANUAL NUMBER','id_card_address':'MANUAL ADDRESS'});before=self.snapshot();self.assertFalse(self.apply(path)['written']);self.assertEqual(self.snapshot(),before)
 def test_other_identity_type_not_silently_changed(self):
  path=self.id_job(doctype='IDENTIFICATION_TYPE_OVERSEA_PASSPORT');before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'IDCARD_TYPE_SELECTION'):self.apply(path)
  self.assertEqual(self.snapshot(),before)
 def test_host_explicit_apply_persisted_confirmation_only(self):
  path=self.id_job();host=HostOcr(self.fx.service,'shop1',self.api,self.store);host.bridge=self.bridge
  original_auth=self.bridge.authenticate
  def test_admission(token):
   p=original_auth(token);p.permissions={'ocr:use'};return p
  try:
   with patch.object(self.bridge,'authenticate',side_effect=test_admission):
    out=host.dispatch(self.fx.token,'shop1',{'action':'apply_confirmed','application':self.app['application'],'job_id':path.rsplit('/',1)[1],'confirmation_revision':1})
   self.assertEqual(out['writeback'],'WRITTEN');self.assertTrue(out['result']['written'])
  finally:host.close()
 def test_host_same_owner_wrong_application_rejected_before_apply(self):
  path=self.id_job();other=self.fx.draft();host=HostOcr(self.fx.service,'shop1',self.api,self.store);host.bridge=self.bridge
  def ocr_snapshot():
   with sqlite3.connect(self.store.db_path) as db:return '\n'.join(db.iterdump())
  before=self.snapshot();ocr_before=ocr_snapshot()
  try:
   with patch.object(self.bridge,'apply_confirmed',wraps=self.bridge.apply_confirmed) as apply:
    with self.assertRaisesRegex(PermissionError,'OCR_JOB_NOT_FOUND'):
     host.dispatch(self.fx.token,'shop1',{'action':'apply_confirmed','application':other['application'],'job_id':path.rsplit('/',1)[1],'confirmation_revision':1})
    apply.assert_not_called()
   self.assertEqual(self.snapshot(),before)
   self.assertEqual(ocr_snapshot(),ocr_before)
  finally:host.close()
 def test_host_caller_fields_cannot_bypass_persisted_snapshot(self):
  path=self.id_job();host=HostOcr(self.fx.service,'shop1',self.api,self.store);host.bridge=self.bridge;before=self.snapshot()
  try:
   with self.assertRaisesRegex(ValueError,'EXACT_REQUEST'):host.dispatch(self.fx.token,'shop1',{'action':'apply_confirmed','application':self.app['application'],'job_id':path.rsplit('/',1)[1],'confirmation_revision':1,'fields':{'id_name':'ATTACK'}})
   self.assertEqual(self.snapshot(),before)
  finally:host.close()
if __name__=='__main__':unittest.main()
