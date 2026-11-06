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
                self.assertEqual(job['warnings'],result.get('warnings', []))
                self.assertTrue(job['requires_human_confirmation'])
                self.assertNotIn('confirmed_fields',job)
    def test_id_front_uses_geometry_not_the_old_nextline_callback(self):
        import cv2, rapidocr, numpy as np
        from unittest.mock import Mock
        raw={'txts':['合成甲','姓名','性别 男'],'scores':[.99]*3,
             'boxes':[[[140,0],[240,0],[240,20],[140,20]],[[0,0],[100,0],[100,20],[0,20]],[[0,40],[100,40],[100,60],[0,60]]]}
        engine=Mock(return_value=raw)
        with patch.object(ocr_core,'run_local_ocr',side_effect=AssertionError('OLD_NEXTLINE_CALLBACK_FORBIDDEN')) as old, patch.object(ocr_core,'_verified_model_paths',return_value={'det':'x','cls':'x','rec':'x'}), patch.object(cv2,'imdecode',return_value=np.zeros((80,250,3),dtype=np.uint8)), patch.object(rapidocr,'RapidOCR',return_value=engine):
            result=run_license_layout_ocr(b'\xff\xd8\xffsynthetic','id_front')
            self.assertEqual(result['fields']['id_name']['value'],'合成甲')
            self.assertEqual(engine.call_count,4);old.assert_not_called()
    def test_license_uses_four_directions_one_original_engine_with_unchanged_parameters(self):
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
            self.assertEqual(engine.call_count,4)
            self.assertEqual(result['fields']['legal_representative']['value'],'合成甲')

    def test_raw_output_released_each_direction_and_single_engine_reused(self):
        import cv2, rapidocr, numpy as np, weakref
        from scripts import community_license_inference as adapter
        from scripts.community_license_layout import extract_license_fields
        refs=[];mapped_calls=[]
        class Output:
            txts=['法定代表人 合成甲'];scores=[.99];boxes=[[[0,0],[200,0],[200,20],[0,20]]]
        class Engine:
            def __init__(self,params):refs.append(('engine',weakref.ref(self)))
            def __call__(self,decoded):
                raw=Output();raw.img=decoded;refs.append(('raw',weakref.ref(raw)));return raw
        def decode(*args):
            decoded=np.zeros((50,200,3),dtype=np.uint8);refs.append(('decoded',weakref.ref(decoded)));return decoded
        def mapped(rows,coordinate_turns):
            mapped_calls.append(1)
            self.assertEqual(coordinate_turns,(0,))
            self.assertTrue(all(ref() is None for kind,ref in refs if kind=='raw'))
            self.assertTrue(all(ref() is not None for kind,ref in refs if kind in ('engine','decoded')))
            self.assertEqual(sum(kind=='engine' for kind,ref in refs),1)
            return extract_license_fields(rows,coordinate_turns)
        with patch.object(ocr_core,'_verified_model_paths',return_value={'det':'x','cls':'x','rec':'x'}), patch.object(cv2,'imdecode',side_effect=decode), patch.object(rapidocr,'RapidOCR',Engine), patch.object(adapter,'extract_license_fields',side_effect=mapped):
            result=run_license_layout_ocr(b'\xff\xd8\xffsynthetic','business_license')
            self.assertEqual(result['fields']['legal_representative']['value'],'合成甲')
        self.assertEqual(len(mapped_calls),4)
        self.assertTrue(all(ref() is None for kind,ref in refs))

    def test_real_pinned_models_four_calls_on_embedded_synthetic_image(self):
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
        self.assertEqual(len(calls),4)
        self.assertNotIn('business_scope',result['fields'])
        for key,value in fixture['expected'].items():
            if key=='business_scope':continue
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
                self.assertIs(compose.call_args.kwargs['infer'].__wrapped__,run_license_layout_ocr)
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
