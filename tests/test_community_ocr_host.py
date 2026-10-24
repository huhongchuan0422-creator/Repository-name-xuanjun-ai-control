"""Only new lifecycle/owner admission scope; original 38 tests are reused."""
import concurrent.futures
import threading
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
import test_community_platform_host as fixture
from test_community_ocr_bridge import load_pinned
from scripts.community_ocr_host import OwnerCalls
from scripts.community_ocr_bridge import compose


class OwnerLifecycle(unittest.TestCase):
    def test_same_thread_and_wrong_thread_pump(self):
        owner=OwnerCalls();self.assertEqual(owner(threading.get_ident),threading.get_ident())
        with concurrent.futures.ThreadPoolExecutor(1) as worker:
            with self.assertRaises(PermissionError):worker.submit(owner.pump).result()
        owner.close()
        with self.assertRaises(PermissionError):owner(lambda:True)
    def test_pending_shutdown_denies_without_execution(self):
        owner=OwnerCalls();called=[]
        with concurrent.futures.ThreadPoolExecutor(1) as worker:
            future=worker.submit(owner,lambda:called.append(True))
            for _ in range(100):
                if not owner.pending.empty():break
                time.sleep(.001)
            owner.close()
            with self.assertRaises(PermissionError):future.result(timeout=1)
        self.assertEqual(called,[])
    def test_bounded_queue_and_timeout_never_execute_cancelled_work(self):
        owner=OwnerCalls(capacity=1,timeout=.05);called=[]
        with concurrent.futures.ThreadPoolExecutor(2) as worker:
            first=worker.submit(owner,lambda:called.append(True))
            for _ in range(100):
                if not owner.pending.empty():break
                time.sleep(.001)
            with self.assertRaisesRegex(PermissionError,'QUEUE_FULL'):worker.submit(owner,lambda:True).result()
            with self.assertRaisesRegex(PermissionError,'TIMEOUT'):first.result()
        owner.pump();owner.close();self.assertEqual(called,[])


class HostComposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.dep,cls.api=load_pinned()
    @classmethod
    def tearDownClass(cls):cls.dep.cleanup()
    def setUp(self):
        self.fx=fixture.FormalHost();self.fx.setUp();self.host=self.fx.open()
        self.store=self.api.SecureSQLiteJobStore(str(self.fx.root/'existing-ocr.sqlite'),Fernet.generate_key())
    def tearDown(self):self.host.close();self.fx.doCleanups()
    def service(self):return self.host.configure_ocr('shop1',self.api,self.store)
    def test_default_disabled_and_original_single_center(self):
        self.assertIsNone(self.host.ocr)
        service=self.service()
        self.assertIs(service.merchant.identity.center,self.host.center)
        self.assertIs(service.merchant.onboarding.center,self.host.center)
        self.assertIs(self.host.application.gateway.ocr,service)
        with self.assertRaises(PermissionError):self.service()
        service.close()
        with self.assertRaises(PermissionError):service.dispatch('invalid','shop1',{})
    def test_wrong_store_rejected(self):
        with self.assertRaises(PermissionError):self.host.configure_ocr('shop1',self.api,self.api.JobStore())
        self.assertIsNone(self.host.ocr)
    def test_original_center_cannot_be_reused_as_ocr_store(self):
        self.store.db_path=str(Path(self.host.plan['center_root'])/'center.sqlite')
        with self.assertRaisesRegex(PermissionError,'SEPARATE_STORE'):self.service()
        self.assertIsNone(self.host.ocr)
    def test_dependency_tampering_rejected(self):
        path=Path(self.api.__file__);raw=path.read_bytes()
        try:
            path.write_bytes(raw+b'\n# tampered')
            with self.assertRaisesRegex(PermissionError,'PINNED_DEPENDENCY'):self.service()
            self.assertIsNone(self.host.ocr)
        finally:path.write_bytes(raw)
    def test_wrong_dispatcher_cannot_run_center_callback_on_worker(self):
        from scripts.community_mini_merchant import MiniMerchant
        app=self.host.application
        with concurrent.futures.ThreadPoolExecutor(1) as worker:
            bridge,_=compose(MiniMerchant(app.identity,app.onboarding,app.operations),'shop1',self.api,self.store,
                             lambda op:worker.submit(op).result())
            with self.assertRaisesRegex(PermissionError,'OWNER_THREAD'):bridge.authenticate('invalid')
    def test_host_asgi_permission_denied_and_close(self):
        app=self.host.application
        from unittest.mock import Mock
        app.gateway.provider.exchange=Mock(return_value={'appid':app.identity.appid,'openid':'openid1'})
        token=app.gateway.login({'code':'ocr-host-code'})['session_token']
        service=self.service()
        def request():
            with TestClient(service.app) as client:
                return client.post('/api/v1/ocr/jobs',headers={'Authorization':'Bearer '+token,'Idempotency-Key':'synthetic-host-key-01'},data={'document_type':'business_license','onboarding_application_id':'not-used','attachment_id':'not-used'},files={'file':('fixture.png',b'synthetic','image/png')})
        with concurrent.futures.ThreadPoolExecutor(1) as worker:
            future=worker.submit(request)
            while not future.done():service.owner.pump();time.sleep(.002)
            response=future.result()
        self.assertEqual(response.status_code,403,response.text)
        self.assertEqual(response.json()['detail'],'OCR_PERMISSION_DENIED')
        self.host.close()
        with self.assertRaises(PermissionError):service.owner(lambda:True)

    def test_mini_source_submit_uses_host_and_remains_403(self):
        from unittest.mock import Mock
        import base64
        app=self.host.application
        app.gateway.provider.exchange=Mock(return_value={'appid':app.identity.appid,'openid':'openid1'})
        token=app.gateway.login({'code':'ocr-mini-source'})['session_token']
        service=self.service();merchant=service.merchant
        draft=merchant.dispatch(token,'shop1',{'operation':'onboarding','params':{'operation':'save','params':dict(application=None,revision=0,entity_type='ENTERPRISE',category='GENERAL',delegated=False,fields=dict(legal_name='SYNTHETIC',store_name='SYNTHETIC',address='SYNTHETIC',contact='SYNTHETIC'))}})
        self.host.center.scanner=lambda raw:True
        uploaded=merchant.dispatch(token,'shop1',{'operation':'onboarding','params':{'operation':'upload','params':dict(application=draft['application'],revision=draft['revision'],kind='business_license',expires_at=None,content_base64=base64.b64encode(b'\x89PNG\r\n\x1a\nSYNTHETIC ONLY').decode())}})
        from scripts.community_mini_merchant import MiniMerchant
        mini=MiniMerchant(app.identity,app.onboarding,app.operations,ocr=service)
        import json,urllib.request,urllib.error
        from scripts.community_mini_http import serve
        server=serve(app.gateway,onboarding=app.onboarding,operations=app.operations)
        payload={'operation':'ocr','params':dict(action='submit',application=uploaded['application'],document_type='business_license',idempotency_key='synthetic-mini-key-01')}
        request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Community-Session':token,'X-Community-Scene':'shop1'})
        def call():
            try:urllib.request.urlopen(request,timeout=5)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
            raise AssertionError('OCR_MUST_REMAIN_DENIED')
        try:
            with concurrent.futures.ThreadPoolExecutor(1) as worker:
                future=worker.submit(call);server.handle_request();status,body=future.result()
            self.assertEqual(status,403)
            self.assertEqual(body,{'error':'OCR_AUTH_DENIED'})
        finally:server.server_close()
