"""Synthetic text/API contract checks; no model or real document invocation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.community_license_layout import extract_license_fields,normalize_layout
from scripts.community_license_inference import run_license_layout_ocr
from services.ocr_engine import api,ocr_core
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

class ApiContract(unittest.TestCase):
    def test_original_api_encrypted_store_roundtrips_field_metadata(self):
        rows=normalize_layout({'txts':['法定代表人 合成甲','法定代表人 合成乙'],'scores':[.99,.98]})
        result=extract_license_fields(rows)
        with tempfile.TemporaryDirectory() as directory:
            store=api.SecureSQLiteJobStore(str(Path(directory)/'synthetic.sqlite'),Fernet.generate_key())
            principal=api.Principal(subject='synthetic-owner',tenant_id='synthetic-tenant',permissions={'ocr:use'})
            def binding(p,a,f,d,t,revision):
                return {'authorized':True,'content_sha256':d,'document_type':t,'application_revision':'1','provider_version':None}
            app=api.create_app(authenticate=lambda token:principal,store=store,
                infer=lambda *args,**kw:result,authorize_application=lambda *args:True,authorize_attachment=binding)
            with TestClient(app) as client:
                headers={'Authorization':'Bearer synthetic-test-token','Idempotency-Key':'synthetic-key-12345'}
                response=client.post('/api/v1/ocr/jobs',headers=headers,
                    data={'document_type':'business_license','onboarding_application_id':'synthetic-application','attachment_id':'synthetic-file'},
                    files={'file':('synthetic.png',b'SYNTHETIC ONLY: infer callback is text fixture','image/png')})
                self.assertEqual(response.status_code,202,response.text)
                received=client.get('/api/v1/ocr/jobs/'+response.json()['job_id'],headers=headers)
                self.assertEqual(received.status_code,200,received.text)
                job=received.json();self.assertEqual(job['fields'],result['fields'])
                self.assertEqual(job['fields']['legal_representative']['value'],'')
                self.assertEqual(len(job['fields']['legal_representative']['candidates']),2)
                self.assertEqual(job['warnings'],[])  # Original API drops top-level warnings.
                self.assertTrue(job['requires_human_confirmation'])
                self.assertNotIn('confirmed_fields',job)
    def test_id_front_explicitly_delegates_original_callback(self):
        expected={'document_type':'id_front','fields':{},'requires_human_confirmation':True}
        with patch.object(ocr_core,'run_local_ocr',return_value=expected) as original:
            self.assertIs(run_license_layout_ocr(b'synthetic','id_front',max_bytes=123,max_pixels=456),expected)
            original.assert_called_once_with(b'synthetic','id_front',max_bytes=123,max_pixels=456)
    def test_license_calls_original_models_once_with_unchanged_parameters(self):
        import cv2
        import rapidocr
        import numpy as np
        raw={'txts':['法定代表人 合成甲'],'scores':[.99],'boxes':[[[0,0],[200,0],[200,20],[0,20]]]}
        from unittest.mock import Mock
        engine=Mock(return_value=raw)
        models={'det':'/synthetic/det','cls':'/synthetic/cls','rec':'/synthetic/rec'}
        with patch.object(ocr_core,'_verified_model_paths',return_value=models), patch.object(cv2,'imdecode',return_value=np.zeros((50,200,3),dtype=np.uint8)), patch.object(rapidocr,'RapidOCR',return_value=engine) as factory:
            result=run_license_layout_ocr(b'\xff\xd8\xffsynthetic','business_license')
            factory.assert_called_once_with(params={'Det.model_path':models['det'],'Cls.model_path':models['cls'],'Rec.model_path':models['rec']})
            engine.assert_called_once()
            self.assertEqual(result['fields']['legal_representative']['value'],'合成甲')

    def test_inference_references_released_before_geometry_mapping(self):
        import cv2, rapidocr, numpy as np, weakref
        from scripts import community_license_inference as adapter
        from scripts.community_license_layout import extract_license_fields
        refs=[]
        class Output:
            txts=['法定代表人 合成甲'];scores=[.99];boxes=[[[0,0],[200,0],[200,20],[0,20]]]
        class Engine:
            def __init__(self,params):refs.append(weakref.ref(self))
            def __call__(self,decoded):
                raw=Output();raw.img=decoded;refs.append(weakref.ref(raw));return raw
        def decode(*args):
            decoded=np.zeros((50,200,3),dtype=np.uint8);refs.append(weakref.ref(decoded));return decoded
        def mapped(rows):
            self.assertEqual(len(refs),3)
            self.assertTrue(all(ref() is None for ref in refs))
            return extract_license_fields(rows)
        with patch.object(ocr_core,'_verified_model_paths',return_value={'det':'x','cls':'x','rec':'x'}), patch.object(cv2,'imdecode',side_effect=decode), patch.object(rapidocr,'RapidOCR',Engine), patch.object(adapter,'extract_license_fields',side_effect=mapped):
            result=run_license_layout_ocr(b'\xff\xd8\xffsynthetic','business_license')
            self.assertEqual(result['fields']['legal_representative']['value'],'合成甲')

    def test_real_pinned_models_single_call_on_embedded_synthetic_image(self):
        import base64,hashlib,json,sys,socket
        from scripts.community_uploaded_image_scanner import UploadedImageScanner
        fixture=json.loads((Path(__file__).parent/'fixtures/community_license_columns90_image.json').read_text())
        self.assertEqual(fixture['scope'],'SYNTHETIC_TEST_ONLY_NOT_REAL_LICENSE')
        raw=base64.b64decode(fixture['png_base64'],validate=True)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),fixture['png_sha256'])
        cleaned=UploadedImageScanner().sanitize(raw)
        calls=[]
        def profile(frame,event,arg):
            if event=='call' and frame.f_code.co_name=='__call__' and frame.f_globals.get('__name__')=='rapidocr.main':calls.append(1)
        previous=sys.getprofile()
        try:
            sys.setprofile(profile)
            with patch.object(socket,'socket',side_effect=AssertionError('SYNTHETIC_NETWORK_FORBIDDEN')), patch.object(socket,'getaddrinfo',side_effect=AssertionError('SYNTHETIC_NETWORK_FORBIDDEN')):
                result=run_license_layout_ocr(cleaned,'business_license')
        finally:sys.setprofile(previous)
        self.assertEqual(len(calls),1)
        for key,value in fixture['expected'].items():
            self.assertEqual(result['fields'][key]['value'],value)
            self.assertTrue(result['fields'][key]['requires_review'])
        self.assertTrue(result['requires_human_confirmation'])
        self.assertFalse(result['authenticity_verified'])

    def test_host_fixed_callback_is_wired_without_new_flag(self):
        from scripts.community_ocr_host import HostOcr
        import sys
        from types import ModuleType
        from unittest.mock import Mock
        fake=ModuleType('scripts.community_ocr_bridge')
        compose=fake.compose=Mock(return_value=(object(),object()))
        with patch.dict(sys.modules, {'scripts.community_ocr_bridge':fake}):
            host=HostOcr(object(),'synthetic-scene',api,object())
            try:
                self.assertIs(compose.call_args.kwargs['infer'],run_license_layout_ocr)
            finally:host.close()
    def test_source_pin_mismatch_fails_before_inference(self):
        original=Path.read_bytes
        def read(path):
            return b'tampered-synthetic' if path.name=='ocr_core.py' else original(path)
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(PermissionError,'^LICENSE_OCR_UPSTREAM_PIN_MISMATCH$'):
                run_license_layout_ocr(b'synthetic','business_license')
    def test_existing_pixel_limit_is_not_reduced_or_bypassed(self):
        import cv2
        import rapidocr
        from types import SimpleNamespace
        with patch.object(ocr_core,'_verified_model_paths',return_value={'det':'x','cls':'x','rec':'x'}), patch.object(cv2,'imdecode',return_value=SimpleNamespace(shape=(4001,5000,3))), patch.object(rapidocr,'RapidOCR') as factory:
            with self.assertRaisesRegex(ValueError,'^IMAGE_PIXEL_LIMIT$'):
                run_license_layout_ocr(b'\xff\xd8\xffsynthetic','business_license')
            factory.assert_not_called()

    def test_unknown_type_rejected_not_misrouted_to_id(self):
        with self.assertRaisesRegex(ValueError,'^UNSUPPORTED_DOCUMENT_TYPE$'):
            run_license_layout_ocr(b'synthetic','bank_card')
    def test_license_original_byte_and_magic_checks(self):
        for data,error in [(b'','INVALID_IMAGE_SIZE'),(b'wrong','UNSUPPORTED_IMAGE_MAGIC')]:
            with self.assertRaisesRegex(ValueError,'^'+error+'$'):
                run_license_layout_ocr(data,'business_license')

if __name__=='__main__':unittest.main()
