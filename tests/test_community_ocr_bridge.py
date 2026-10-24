"""Actual pinned OCR HTTP + encrypted store + original Center composition.

Only inference and permission admission are synthetic fixtures. Production
ocr:use mapping is deliberately absent and covered by a denial test.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_community_mini_merchant import OcrSourceBoundary
from scripts.community_ocr_bridge import compose, application_revision


def load_pinned():
    lock = json.loads(Path('scripts/community_ocr_dependency.json').read_text())
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for name, digest in lock['files'].items():
        raw = subprocess.check_output(['git','show',lock['source_sha']+':services/ocr_engine/'+name])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise AssertionError('PINNED_OCR_HASH_MISMATCH')
        (root/name).write_bytes(raw)
    (root/'__init__.py').write_text('')
    # Each class owns a fresh temporary dependency root. Do not reuse imported
    # child modules pointing at a previous class's already removed directory.
    for name in list(sys.modules):
        if name=='community_pinned_ocr' or name.startswith('community_pinned_ocr.'):
            del sys.modules[name]
    spec = importlib.util.spec_from_file_location('community_pinned_ocr',root/'__init__.py',submodule_search_locations=[str(root)])
    package = importlib.util.module_from_spec(spec);sys.modules[spec.name]=package;spec.loader.exec_module(package)
    from community_pinned_ocr import api
    return tmp, api


class OriginalOwner:
    """Pump the actual serial Center owner; never relax SQLite thread safety."""
    def __init__(self):self.owner=threading.get_ident();self.queue=queue.Queue()
    def __call__(self, operation):
        if threading.get_ident()==self.owner:return operation()
        from concurrent.futures import Future
        future=Future();self.queue.put((operation,future));return future.result(timeout=10)
    def request(self, client, method, *args, **kwargs):
        with ThreadPoolExecutor(1) as pool:
            result=pool.submit(getattr(client,method),*args,**kwargs)
            while not result.done():
                try:op,future=self.queue.get(timeout=.01)
                except queue.Empty:continue
                try:future.set_result(op())
                except Exception as error:future.set_exception(error)
            return result.result()


class OwnerHttp:
    def __init__(self,client,owner):self.client,self.owner=client,owner
    def __getattr__(self,name):
        if name=='close':return self.client.close
        def request(*args,**kwargs):return self.owner.request(self.client,name,*args,**kwargs)
        return request


class TestAdmission:
    """Test-only explicit permission; never wired into production compose()."""
    def __init__(self, bridge): self.bridge=bridge
    def __call__(self, token):
        p=self.bridge.authenticate(token)
        p.permissions={'ocr:use'}
        return p


def synthetic_inference(data, document_type, max_bytes):
    return {'fields':{'company_name':{'value':'SYNTHETIC ONLY','confidence':.9}}}


class OcrComposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.dep,cls.api=load_pinned()
    @classmethod
    def tearDownClass(cls):cls.dep.cleanup()
    def setUp(self):
        self.fx=OcrSourceBoundary();self.fx.setUp()
        self.app=self.fx.material();self.raw=b'\x89PNG\r\n\x1a\nSynthetic document, not a real credential'
        self.tmp=tempfile.TemporaryDirectory()
        self.store_key=Fernet.generate_key()
        self.store=self.api.SecureSQLiteJobStore(str(Path(self.tmp.name)/'ocr.sqlite'),self.store_key)
        self.owner=OriginalOwner()
        self.bridge,closed=compose(self.fx.service,'shop1',self.api,self.store,self.owner,synthetic_inference)
        self.closed=OwnerHttp(TestClient(closed),self.owner)
        self.auth=TestAdmission(self.bridge)
        self.client=OwnerHttp(TestClient(self.api.create_app(authenticate=self.auth,store=self.store,infer=synthetic_inference,
            authorize_application=self.bridge.authorize_application,authorize_attachment=self.bridge.authorize_attachment)),self.owner)
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'business_license')
        self.headers={'Authorization':'Bearer '+self.fx.token,'Idempotency-Key':'synthetic-key-00001'}
    def tearDown(self):self.client.close();self.closed.close();self.tmp.cleanup();self.fx.tearDown()
    def submit(self,client=None,**changes):
        data=dict(document_type='business_license',onboarding_application_id=self.app['application'],attachment_id=self.source['attachment_id']);data.update(changes)
        return (client or self.client).post('/api/v1/ocr/jobs',headers=self.headers,data=data,files={'file':('synthetic.png',self.raw,'image/png')})
    def job(self):
        response=self.submit();self.assertEqual(response.status_code,202,response.text)
        return '/api/v1/ocr/jobs/'+response.json()['job_id']
    def denied_all(self,path):
        for method,kwargs in [('get',{}),('delete',{}),('post',{'json':{'revision':1,'application_revision':self.source['application_revision'],'provider_version':self.source.get('wechat_version'),'fields':{'company_name':'SYNTHETIC ONLY'}}})]:
            response=getattr(self.client,method)(path+('/confirm' if method=='post' else ''),headers=self.headers,**kwargs)
            self.assertIn(response.status_code,(401,403),response.text)
    def test_production_permission_remains_closed(self):self.assertEqual(self.submit(self.closed).status_code,403)
    def test_actual_http_encrypted_store_idempotency_and_no_manual_overwrite(self):
        path=self.job();again=self.submit();self.assertEqual(path.rsplit('/',1)[1],again.json()['job_id'])
        result=self.client.get(path,headers=self.headers);self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['application_revision'],str(self.app['revision']))
        self.assertNotIn(b'SYNTHETIC ONLY',(Path(self.tmp.name)/'ocr.sqlite').read_bytes())
        response=self.client.post(path+'/confirm',headers=self.headers,json={'revision':1,'application_revision':self.source['application_revision'],'provider_version':self.source.get('wechat_version'),'fields':{'company_name':'SYNTHETIC ONLY'}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(self.bridge.apply_confirmed(self.auth(self.fx.token),path.rsplit('/',1)[1],expected_confirmation_revision=1)['written'])
        self.assertEqual(self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]['fields']['legal_name'],'Fixture')
    def test_wrong_type_same_sha(self):self.assertEqual(self.submit(document_type='id_front').status_code,403)
    def test_other_application(self):self.assertEqual(self.submit(onboarding_application_id=self.fx.draft()['application']).status_code,403)
    def test_other_subject_http(self):
        path=self.job();other=self.fx.fx.token('othercode','openid2')
        self.assertEqual(self.client.get(path,headers={'Authorization':'Bearer '+other}).status_code,404)
    def test_changed_principal_subject_and_tenant(self):
        for field in ('subject','tenant_id'):
            p=self.auth(self.fx.token);setattr(p,field,'different')
            self.assertFalse(self.bridge.authorize_application(p,self.app['application']))
            with self.assertRaises(PermissionError):self.bridge.source(p,self.app['application'],'business_license')
    def test_scan_revocation_get_confirm_delete(self):
        path=self.job();self.fx.fx.center.db.execute("UPDATE objects SET scan='BLOCKED' WHERE id=?",(self.source['attachment_id'],));self.denied_all(path)
    def test_attachment_replacement_get_confirm_delete(self):
        path=self.job();self.fx.material(self.app,raw=self.raw+b'replaced');self.denied_all(path)
    def test_revision_change_get_confirm_delete_and_writeback(self):
        path=self.job();self.fx.fx.center.db.execute('UPDATE onboarding SET revision=revision+1 WHERE application=?',(self.app['application'],));self.denied_all(path)
    def test_session_revocation(self):
        path=self.job();self.fx.fx.center.logout(self.fx.token);self.denied_all(path)
    def test_scene_photos_rejected(self):
        for kind in ('storefront_photo','interior_photo','cashier_photo'):
            self.assertEqual(self.submit(document_type=kind).status_code,400)
    def test_decimal_revision_rules(self):
        self.assertEqual(application_revision(12),'12')
        for value in (True,0,-1,'12',' 12',12.0,None):
            with self.assertRaises(PermissionError):application_revision(value)
    def test_confirmed_writeback_revision_changed(self):
        path=self.job();self.assertEqual(self.client.post(path+'/confirm',headers=self.headers,json={'revision':1,'application_revision':self.source['application_revision'],'provider_version':self.source.get('wechat_version'),'fields':{'company_name':'SYNTHETIC ONLY'}}).status_code,200)
        self.fx.fx.center.db.execute('UPDATE onboarding SET revision=revision+1 WHERE application=?',(self.app['application'],))
        with self.assertRaises(PermissionError):self.bridge.apply_confirmed(self.auth(self.fx.token),path.rsplit('/',1)[1],expected_confirmation_revision=1)

    def test_identity_front_actual_http_positive(self):
        self.app=self.fx.material(self.app,kind='identity_front')
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'id_front')
        response=self.submit(document_type='id_front')
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(self.client.get('/api/v1/ocr/jobs/'+response.json()['job_id'],headers=self.headers).status_code,200)
    def test_human_confirmation_fills_only_empty_fields_with_original_cas(self):
        self.app=self.fx.call('onboarding',{'operation':'save','params':dict(application=self.app['application'],revision=self.app['revision'],entity_type='ENTERPRISE',category='GENERAL',delegated=False,fields=dict(legal_name='',store_name='Fixture Shop',address='Fixture Address',contact='Fixture'))})
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'business_license')
        path=self.job()
        self.assertEqual(self.client.post(path+'/confirm',headers=self.headers,json={'revision':1,'application_revision':self.source['application_revision'],'provider_version':self.source.get('wechat_version'),'fields':{'company_name':'SYNTHETIC ONLY','registered_address':'never overwrite'}}).status_code,200)
        result=self.bridge.apply_confirmed(self.auth(self.fx.token),path.rsplit('/',1)[1],expected_confirmation_revision=1)
        self.assertTrue(result['written'])
        current=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]
        self.assertEqual(current['fields']['legal_name'],'SYNTHETIC ONLY')
        self.assertEqual(current['fields']['address'],'Fixture Address')
        self.assertEqual(current['revision'],self.app['revision']+1)
        self.denied_all(path)

    def test_shared_wechat_draft_writeback_is_not_guessed(self):
        self.app=self.fx.call('onboarding',{'operation':'save','params':dict(application=self.app['application'],revision=self.app['revision'],entity_type='ENTERPRISE',category='GENERAL',delegated=False,fields=dict(legal_name='',store_name='Fixture Shop',address='Fixture Address',contact='Fixture'))})
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'business_license')
        path=self.job()
        self.assertEqual(self.client.post(path+'/confirm',headers=self.headers,json={'revision':1,'application_revision':self.source['application_revision'],'provider_version':self.source.get('wechat_version'),'fields':{'company_name':'SYNTHETIC ONLY'}}).status_code,200)
        from scripts.community_wechat_applyment import WechatApplyment
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        self.fx.onboarding.wechat_applyment=WechatApplyment(self.fx.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
        with self.assertRaisesRegex(PermissionError,'SHARED_DRAFT_WRITEBACK_VERSION_BINDING'):
            self.bridge.apply_confirmed(self.auth(self.fx.token),path.rsplit('/',1)[1],expected_confirmation_revision=1)
        self.assertEqual(self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]['fields']['legal_name'],'')
