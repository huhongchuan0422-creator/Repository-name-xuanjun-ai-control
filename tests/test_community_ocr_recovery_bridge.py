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
if __name__=='__main__':unittest.main()
