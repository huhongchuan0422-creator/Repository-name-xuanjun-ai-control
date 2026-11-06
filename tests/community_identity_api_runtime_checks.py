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
    def test_runtime_is_exact_pinned_successor_and_immutable_core_store(self):
        from scripts import community_ocr_bridge
        lock=json.loads(Path(community_ocr_bridge.__file__).with_name('community_ocr_dependency.json').read_text())
        self.assertEqual(lock['files']['api.py'],'32cf647f56f9f1fbed9d0c7d15bb50a0f60a9cd5124bd5ff835129196766636e')
        for name,digest in lock['files'].items():
            self.assertEqual(hashlib.sha256((Path(api.__file__).parent/name).read_bytes()).hexdigest(),digest)
        for name in ('secure_store.py','ocr_core.py'):self.assertEqual(lock['files'][name],lock['upstream_files'][name])
        self.assertEqual(api.ALLOWED_HINTS,{'business_license','id_front','id_back'})
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
