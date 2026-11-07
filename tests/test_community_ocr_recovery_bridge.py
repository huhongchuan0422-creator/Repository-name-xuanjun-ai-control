"""Synthetic review binding tests; no model, image, network or host account."""
import importlib.util
import pathlib
import sys
import tempfile
import threading
import types
import unittest
from cryptography.fernet import Fernet
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.community_ocr_bridge import CommunityOcrBridge
spec=importlib.util.spec_from_file_location('recovery_journal',ROOT/'services/ocr_engine/secure_store.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RecoveryBridge(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=m.SecureSQLiteJobStore(self.tmp.name+'/ocr.db',Fernet.generate_key())
  self.job=self.store.create('tenant','owner','app','id_front','digest','old-key','material','7',2)
  self.store.update(self.job['job_id'],status='needs_review',fields={'id_name':{'value':'Synthetic'}})
  self.original=self.store.get(self.job['job_id'],'tenant')
  self.p=types.SimpleNamespace(subject='owner',tenant_id='tenant',permissions={'ocr:use'})
  self.b=object.__new__(CommunityOcrBridge);self.b.owner_thread=threading.get_ident();self.b.owner_call=lambda f:f();self.b.store=self.store
  self.b._context=lambda p:None;self.b.authorize_application=lambda p,a:a=='app'
  self.source=dict(subject='owner',tenant_id='tenant',document_type='id_front',attachment_id='material',document_sha256='digest',application_revision='9',wechat_version=4)
  self.b.source=lambda p,a,d:dict(self.source)
 def tearDown(self):self.tmp.cleanup()
 def view(self):return self.b.recovery_view(self.p,'app','id_front',{'original_key':'old-key'},'view-key')
 def test_view_current_binding_without_inherited_confirmation(self):
  v=self.view();self.assertEqual(v['binding']['application_revision'],'9');self.assertFalse(v['confirmed'])
  c=self.b.recovery_confirm(self.p,'app','view-key',1,{'id_name':'Visible human value'},'confirmation-key')
  self.assertEqual(c['confirmed_fields'],{'id_name':'Visible human value'})
  self.assertEqual(self.store.get(self.job['job_id'],'tenant'),self.original)
 def test_change_after_view_refuses_confirmation(self):
  self.view();self.source['application_revision']='10'
  with self.assertRaises(PermissionError):self.b.recovery_confirm(self.p,'app','view-key',1,{'id_name':'Visible'},'confirmation-key')
  self.assertIsNone(self.store.recovery_receipt('tenant','owner','confirm','confirmation-key'))
 def test_material_replacement_and_revocation(self):
  self.source['attachment_id']='other'
  with self.assertRaises(PermissionError):self.view()
  self.source['attachment_id']='material';self.b.authorize_application=lambda p,a:False
  with self.assertRaises(PermissionError):self.view()
 def test_reused_view_key_never_rebinds(self):
  self.view();self.source['wechat_version']=5
  with self.assertRaises(ValueError):self.view()
  self.assertEqual(self.store.recovery_receipt('tenant','owner','view','view-key')['binding']['provider_version'],4)
class MaterialRecovery(unittest.TestCase):
 setUp=RecoveryBridge.setUp
 tearDown=RecoveryBridge.tearDown
 def view(self):return self.b.recovery_view(self.p,'app','id_front',{'current_material':True},'material-view')
 def test_unique_current_material_without_original_pointer(self):
  v=self.view();self.assertEqual(v['job_id'],self.job['job_id']);self.assertFalse(v['confirmed'])
  self.assertEqual(self.store.get(self.job['job_id'],'tenant'),self.original)
 def test_zero_does_not_create(self):
  self.source['attachment_id']='replacement'
  with self.assertRaisesRegex(ValueError,'MATERIAL_NOT_FOUND'):self.view()
  with self.store._connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ocr_jobs').fetchone()[0],1)
 def test_duplicate_all_states_not_newest_or_success_only(self):
  other=self.store.create('tenant','owner','app','id_front','digest','other-key','material','9',4)
  with self.assertRaisesRegex(ValueError,'MATERIAL_AMBIGUOUS'):self.view()
  self.store.update(other['job_id'],status='failed')
  with self.assertRaisesRegex(ValueError,'MATERIAL_AMBIGUOUS'):self.view()
 def test_lookup_cross_account_application_document_digest(self):
  for k,v in [('subject','other'),('tenant_id','other'),('document_type','id_back'),('document_sha256','changed')]:
   before=dict(self.source);self.source[k]=v
   with self.assertRaises((ValueError,PermissionError)):self.view()
   self.source=before
 def test_revision_changes_during_lookup_refuses_fields(self):
  original=self.store.resolve_material_recovery_job
  def changed(*a):
   job=original(*a);self.source['application_revision']='10';return job
  self.store.resolve_material_recovery_job=changed
  with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):self.view()
 def test_duplicate_created_during_record_refuses_release(self):
  original=self.store.recovery_record
  def changed(*a):
   v=original(*a);self.store.create('tenant','owner','app','id_front','digest','concurrent','material','9',4);return v
  self.store.recovery_record=changed
  with self.assertRaisesRegex(ValueError,'MATERIAL_AMBIGUOUS'):self.view()
 def test_cannot_supply_material_identifiers(self):
  for locator in ({'current_material':1},{'current_material':True,'attachment_id':'material'},{'current_material':True,'job_id':self.job['job_id']}):
   with self.assertRaisesRegex(ValueError,'EXACT_LOCATOR_REQUIRED'):self.b.recovery_view(self.p,'app','id_front',locator,'invalid')

if __name__=='__main__':unittest.main()
