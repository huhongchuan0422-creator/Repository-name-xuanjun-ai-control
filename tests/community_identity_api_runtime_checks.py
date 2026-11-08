"""Assert deployed successor bytes and real HTTP/store schema using synthetic data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from services.ocr_engine import api


class IdentityApiRuntime(unittest.TestCase):
    def test_runtime_is_exact_pinned_recovery_successor_and_immutable_core(self):
        from scripts import community_ocr_bridge
        lock=json.loads(Path(community_ocr_bridge.__file__).with_name('community_ocr_dependency.json').read_text())
        self.assertEqual(lock['files']['api.py'],'65f7bc31e43d0104297aa574f4d42754288faab3c2d0e02fd37ab334742a877d')
        self.assertEqual(lock['files']['secure_store.py'],'30ae4cafdd2749a4f24092a2c17f9465b429351ef6c5bf4831ce999e576b7d25')
        self.assertEqual(lock['local_successor']['source_files'],{'api.py':'services/ocr_engine/api.py','secure_store.py':'services/ocr_engine/secure_store.py'})
        self.assertEqual(lock['local_successor']['patch_path'],'deploy/community-preview/ocr-bank-card-successor.patch')
        self.assertEqual(lock['local_successor']['patch_sha256'],'636230f82b27afa1cf88412698a78f244eeb207d2b08bee7fbf1173bf35b9e21')
        for name,digest in lock['files'].items():
            self.assertEqual(hashlib.sha256((Path(api.__file__).parent/name).read_bytes()).hexdigest(),digest)
        self.assertEqual(lock['files']['ocr_core.py'],lock['upstream_files']['ocr_core.py'])
        self.assertEqual(lock['files']['ocr_core.py'],'bbc99d7e5bc606fc0f069b5a26babc4b87a5f7b4e0726cd71acab231933bc308')
        self.assertNotEqual(lock['files']['secure_store.py'],lock['upstream_files']['secure_store.py'])
        self.assertEqual(api.ALLOWED_HINTS,{'business_license','id_front','id_back','bank_card'})
    def test_real_api_persists_confirms_and_reopens_back_fields(self):
        fields={'issuing_authority':{'value':'SYNTHETIC ONLY','source':'ocr','requires_review':True,'source_boxes':[[[0,0],[1,0],[1,1],[0,1]]]},'valid_from':{'value':'2020-01-02'},'valid_to':{'value':'长期'}}
        evidence={'orientation':{'ambiguous':False,'clockwise_rotation_to_upright_degrees':90,'inference_calls':4},'correction_counterclockwise_degrees':270,'input_dimensions':{'width':100,'height':50},'source_coordinate_space':'input_image_pixels','extraction_after_pixel_rotation':True,'unresolved_validity_candidates':[{'value':'2020.01.02-长期','source_lines':[3]}],'warnings':['SYNTHETIC_REVIEW_REQUIRED']}
        raw=b'SYNTHETIC TRANSPORT FIXTURE';digest=hashlib.sha256(raw).hexdigest()
        p=api.Principal(subject='synthetic-owner',tenant_id='synthetic-tenant',permissions={'ocr:use'})
        def attachment(owner,app,file,sha,kind,revision):
            if (owner.subject,app,file,sha,kind)!=('synthetic-owner','synthetic-app','synthetic-back',digest,'id_back'):return None
            return {'authorized':True,'content_sha256':digest,'document_type':'id_back','application_revision':'1','provider_version':1}
        with tempfile.TemporaryDirectory() as tmp:
            key=Fernet.generate_key();path=str(Path(tmp)/'store.sqlite');store=api.SecureSQLiteJobStore(path,key)
            app=api.create_app(authenticate=lambda token:p,store=store,infer=lambda *a,**k:{'fields':fields,**evidence,'raw_image':'NEVER PERSIST'},authorize_application=lambda p,a:a=='synthetic-app',authorize_attachment=attachment)
            headers={'Authorization':'Bearer synthetic-token','Idempotency-Key':'synthetic-runtime-submit'}
            with TestClient(app) as client:
                r=client.post('/api/v1/ocr/jobs',headers=headers,data={'document_type':'id_back','onboarding_application_id':'synthetic-app','attachment_id':'synthetic-back'},files={'file':('synthetic.png',raw,'image/png')})
                self.assertEqual(r.status_code,202,r.text);jobid=r.json()['job_id'];url='/api/v1/ocr/jobs/'+jobid
                r=client.get(url,headers=headers);self.assertEqual(r.status_code,200);self.assertEqual(r.json()['fields'],fields)
                for name,value in evidence.items():self.assertEqual(r.json()[name],value)
                self.assertNotIn('raw_image',r.json())
                body={'revision':1,'application_revision':'1','provider_version':1,'fields':{k:v['value'] for k,v in fields.items()}}
                r=client.post(url+'/confirm',headers={**headers,'Idempotency-Key':'synthetic-runtime-confirm'},json=body)
                self.assertEqual(r.status_code,200,r.text)
                self.assertEqual(client.get(url,headers=headers).json()['confirmed_fields'],body['fields'])
            reopened=api.SecureSQLiteJobStore(path,key);record=reopened.get(jobid,p.tenant_id)
            self.assertEqual(record['confirmed_fields'],body['fields']);self.assertEqual(record['confirmed_binding']['document_type'],'id_back')
            self.assertNotIn(b'SYNTHETIC ONLY',Path(path).read_bytes())
            for name,value in evidence.items():self.assertEqual(record[name],value)

if __name__=='__main__':unittest.main()
