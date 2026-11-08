"""Real API successor + original encrypted store/source, synthetic documents only.

Inference fields are controlled synthetic data. This does not claim real-image accuracy.
"""
import hashlib
import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import test_community_ocr_bridge as fixture
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader

VALUES = {
    'business_license': {'company_name': 'SYNTHETIC COMPANY'},
    'id_front': {'id_name': 'SYNTHETIC PERSON', 'id_number': 'SYNTHETIC NOT AN ID', 'registered_address': 'SYNTHETIC ADDRESS'},
    'id_back': {'issuing_authority': 'SYNTHETIC ISSUING AUTHORITY', 'valid_from': '2020-01-02', 'valid_to': '长期'},
}
RAW = {kind:b'\x89PNG\r\n\x1a\nSYNTHETIC ONLY '+kind.encode() for kind in VALUES}


class IdentityBackContract(unittest.TestCase):
    setUpClass=classmethod(fixture.OcrComposition.setUpClass.__func__)
    tearDownClass=classmethod(fixture.OcrComposition.tearDownClass.__func__)
    tearDown=fixture.OcrComposition.tearDown
    def setUp(self):
        fixture.OcrComposition.setUp(self)
        for kind,material in [('business_license','business_license'),('id_front','identity_front'),('id_back','identity_back')]:
            self.app=self.fx.material(self.app,kind=material,raw=RAW[kind])
        self.calls=[]
        def synthetic(raw,kind,**_):
            self.assertEqual(raw,RAW[kind]);self.calls.append(kind)
            return {'document_type':kind,'fields':{k:{'value':v,'requires_review':True} for k,v in VALUES[kind].items()}}
        self.infer=synthetic
        self.client.close()
        self.client=fixture.OwnerHttp(TestClient(self.api.create_app(authenticate=self.auth,store=self.store,infer=self.infer,
            authorize_application=self.bridge.authorize_application,authorize_attachment=self.bridge.authorize_attachment)),self.owner)
        self.sources={kind:self.bridge.source(self.auth(self.fx.token),self.app['application'],kind) for kind in VALUES}
    def submit(self,kind='id_back',*,source_kind=None,key=None):
        source=self.sources[source_kind or kind]
        return self.client.post('/api/v1/ocr/jobs',headers={**self.headers,'Idempotency-Key':key or 'synthetic-submit-'+kind},
            data=dict(document_type=kind,onboarding_application_id=self.app['application'],attachment_id=source['attachment_id']),
            files={'file':('synthetic.png',RAW[source_kind or kind],'image/png')})
    def job(self,kind='id_back'):
        response=self.submit(kind);self.assertEqual(response.status_code,202,response.text)
        return '/api/v1/ocr/jobs/'+response.json()['job_id']
    def read(self,path):return self.client.get(path,headers=self.headers)
    def confirm(self,path,fields=None,*,revision=1,key='synthetic-confirm-back-01'):
        seen=self.read(path).json()
        return self.client.post(path+'/confirm',headers={**self.headers,'Idempotency-Key':key},json=dict(
            revision=revision,application_revision=seen['application_revision'],provider_version=seen['provider_version'],
            fields=fields or VALUES[seen['document_type']]))
    def test_actual_successor_hash_and_unchanged_core(self):
        lock=json.loads(Path('scripts/community_ocr_dependency.json').read_text())
        self.assertEqual(self.api.ALLOWED_HINTS,{'business_license','id_front','id_back','bank_card'})
        self.assertEqual(set(self.api.CONFIRM_KEYS),{'business_license','id_front','id_back','bank_card'})
        self.assertEqual(set(self.api.CONFIRM_KEYS['bank_card']),{'account_number','account_bank'})
        self.assertEqual(set(self.api.CONFIRM_KEYS['id_front']),set(VALUES['id_front']))
        for name,digest in lock['files'].items():
            self.assertEqual(hashlib.sha256((Path(self.api.__file__).parent/name).read_bytes()).hexdigest(),digest)
        self.assertEqual(lock['files']['ocr_core.py'],lock['upstream_files']['ocr_core.py'])
        self.assertEqual(set(lock['local_successor']['source_files']),{'api.py','secure_store.py'})
        for name,relative in lock['local_successor']['source_files'].items():
            self.assertEqual(hashlib.sha256(Path(relative).read_bytes()).hexdigest(),lock['files'][name])
        self.assertEqual(set(self.api.CONFIRM_KEYS['id_back']),set(VALUES['id_back']))
    def test_successor_patch_matches_original_ref_bytes_exactly(self):
        import os,subprocess,difflib
        lock=json.loads(Path('scripts/community_ocr_dependency.json').read_text())
        root=os.environ.get('COMMUNITY_TEST_PINNED_OCR_DIR')
        patches=[]
        for name,relative in sorted(lock['local_successor']['source_files'].items()):
            original_path='services/ocr_engine/'+name
            raw=(Path(root)/name).read_bytes() if root else subprocess.check_output(['git','show',lock['source_sha']+':'+original_path])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),lock['upstream_files'][name])
            candidate=Path(relative).read_text()
            patches.append(''.join(difflib.unified_diff(raw.decode().splitlines(True),candidate.splitlines(True),fromfile='a/'+original_path,tofile='b/'+original_path)))
        patch=''.join(patches)
        self.assertEqual(Path(lock['local_successor']['patch_path']).read_text(),patch)
        self.assertEqual(hashlib.sha256(patch.encode()).hexdigest(),lock['local_successor']['patch_sha256'])
        self.assertEqual(lock['local_successor']['status'],'UNPUBLISHED_LOCAL_CANDIDATE')

    def test_three_document_lifecycles_preserve_type_and_separate_material(self):
        paths=[]
        for kind in VALUES:
            path=self.job(kind);paths.append(path)
            seen=self.read(path).json();self.assertEqual(seen['document_type'],kind)
            self.assertEqual(set(seen['fields']),set(VALUES[kind]))
            ack=self.confirm(path,key='synthetic-confirm-'+kind)
            self.assertEqual(ack.status_code,200,ack.text)
            self.assertEqual(self.read(path).json()['confirmed_fields'],VALUES[kind])
            job=self.store.get(path.rsplit('/',1)[1],self.sources[kind]['tenant_id'])
            self.assertEqual(job['attachment_id'],self.sources[kind]['attachment_id'])
            self.assertEqual(job['confirmed_binding']['document_type'],kind)
        self.assertEqual(len(set(paths)),3);self.assertEqual(self.calls,list(VALUES))
    def test_confirmed_back_is_durable_encrypted_and_retry_never_reinfers(self):
        path=self.job();ack=self.confirm(path);self.assertEqual(ack.status_code,200,ack.text)
        reopened=self.api.SecureSQLiteJobStore(self.store.db_path,self.store_key)
        job=reopened.get(path.rsplit('/',1)[1],self.sources['id_back']['tenant_id'])
        self.assertEqual(job['confirmed_fields'],VALUES['id_back'])
        self.assertNotIn(b'SYNTHETIC ISSUING AUTHORITY',Path(self.store.db_path).read_bytes())
        self.assertEqual(self.submit().json()['job_id'],path.rsplit('/',1)[1]);self.assertEqual(self.calls,['id_back'])
        self.assertEqual(self.read(path).json()['status'],'confirmed')
    def test_wrong_side_material_never_reaches_inference(self):
        for kind,other in [('id_back','id_front'),('id_front','id_back'),('id_back','business_license')]:
            response=self.submit(kind,source_kind=other,key='wrong-side-'+kind+'-'+other)
            self.assertEqual(response.status_code,403,response.text)
        self.assertEqual(self.calls,[])
    def test_front_keys_cannot_confirm_back_and_reverse(self):
        back=self.job();front=self.job('id_front')
        self.assertEqual(self.confirm(back,VALUES['id_front']).status_code,400)
        self.assertEqual(self.confirm(front,VALUES['id_back']).status_code,400)
        self.assertEqual(self.read(back).json()['status'],'needs_review')
    def test_real_original_api_front_confirmation_survives_successor_read_and_retry(self):
        import os,subprocess,importlib.util,sys
        lock=json.loads(Path('scripts/community_ocr_dependency.json').read_text())
        original=os.environ.get('COMMUNITY_TEST_PINNED_OCR_DIR')
        raw=(Path(original)/'api.py').read_bytes() if original else subprocess.check_output(['git','show',lock['source_sha']+':services/ocr_engine/api.py'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),lock['upstream_files']['api.py'])
        path=Path(self.dep.name)/'legacy_api.py';path.write_bytes(raw)
        name=self.api.__package__+'.legacy_api';spec=importlib.util.spec_from_file_location(name,path)
        legacy=importlib.util.module_from_spec(spec);sys.modules[name]=legacy;spec.loader.exec_module(legacy)
        old=fixture.OwnerHttp(TestClient(legacy.create_app(authenticate=self.auth,store=self.store,infer=self.infer,
            authorize_application=self.bridge.authorize_application,authorize_attachment=self.bridge.authorize_attachment)),self.owner)
        source=self.sources['id_front'];headers={**self.headers,'Idempotency-Key':'synthetic-submit-id_front'}
        try:
            response=old.post('/api/v1/ocr/jobs',headers=headers,data=dict(document_type='id_front',onboarding_application_id=self.app['application'],attachment_id=source['attachment_id']),files={'file':('synthetic.png',RAW['id_front'],'image/png')})
            self.assertEqual(response.status_code,202,response.text);url='/api/v1/ocr/jobs/'+response.json()['job_id']
            ack=old.post(url+'/confirm',headers={**headers,'Idempotency-Key':'synthetic-legacy-confirm'},json=dict(revision=1,application_revision=source['application_revision'],provider_version=None,fields={'id_name':'LEGACY HUMAN CONFIRMED'}))
            self.assertEqual(ack.status_code,200,ack.text)
        finally:old.close()
        self.assertEqual(self.read(url).json()['confirmed_fields'],{'id_name':'LEGACY HUMAN CONFIRMED'})
        self.assertEqual(self.submit('id_front').json()['job_id'],url.rsplit('/',1)[1])
        self.assertEqual(self.calls,['id_front'])
        self.assertEqual(self.read(url).json()['confirmed_fields'],{'id_name':'LEGACY HUMAN CONFIRMED'})

    def test_legacy_license_scope_history_survives_visible_only_new_confirmation(self):
        path=self.job('business_license');job_id=path.rsplit('/',1)[1]
        legacy_raw={'company_name':{'value':'OLD OCR COMPANY'},'business_scope':{'value':'OLD OCR SCOPE'}}
        self.store.update(job_id,fields=legacy_raw)
        old={'company_name':'OLD HUMAN COMPANY','business_scope':'OLD HUMAN SCOPE'}
        first=self.confirm(path,old,revision=1,key='synthetic-legacy-scope-key')
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.read(path).json()['confirmed_fields'],old)
        current={'company_name':'NEW HUMAN COMPANY'}
        self.assertEqual(self.confirm(path,current,revision=2,key='synthetic-visible-only-key').status_code,200)
        self.assertEqual(self.read(path).json()['confirmed_fields'],current)
        self.assertEqual(self.read(path).json()['fields'],legacy_raw)
        reopened=self.api.SecureSQLiteJobStore(self.store.db_path,self.store_key)
        stored=reopened.get(job_id,self.sources['business_license']['tenant_id'])
        self.assertEqual(stored['fields'],legacy_raw)
        replay=self.confirm(path,old,revision=1,key='synthetic-legacy-scope-key')
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['confirmed_fields'],old)
        self.assertEqual(replay.json()['revision'],1)
        self.assertEqual(self.read(path).json()['confirmed_fields'],current)
        self.assertEqual(self.calls,['business_license'])

    def test_human_correction_preserved_across_original_submit_replay(self):
        path=self.job();corrected={**VALUES['id_back'],'issuing_authority':'HUMAN CORRECTED','valid_to':'2030-01-02'}
        self.assertEqual(self.confirm(path,corrected).status_code,200)
        self.submit();self.assertEqual(self.read(path).json()['confirmed_fields'],corrected)
        self.assertEqual(self.calls,['id_back'])
    def test_material_replacement_revokes_both_historical_side_jobs(self):
        front=self.job('id_front');back=self.job();self.assertEqual(self.confirm(back).status_code,200)
        self.app=self.fx.material(self.app,kind='identity_back',raw=RAW['id_back']+b'REPLACED')
        for path in (front,back):self.assertEqual(self.read(path).status_code,403)
    def test_non_idcard_original_selection_rejects_both_sides(self):
        c=self.fx.fx.center;owner,meta,_=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)
        meta['identity_type']='IDENTIFICATION_TYPE_OVERSEA_PASSPORT'
        with c.tx():self.fx.onboarding._meta(self.app['application'],owner,meta)
        for kind in ('id_front','id_back'):
            with self.assertRaisesRegex(PermissionError,'OCR_DOCUMENT_NOT_SUPPORTED'):
                self.bridge.source(self.auth(self.fx.token),self.app['application'],kind)
    def test_confirm_does_not_write_provider_and_explicit_fill_only_empty_dates(self):
        service=WechatApplyment(self.fx.onboarding,PartnerOrderReader.__new__(PartnerOrderReader));self.fx.onboarding.wechat_applyment=service
        profile={'subject_info':{'identity_info':{'id_doc_type':'IDENTIFICATION_TYPE_IDCARD','id_card_info':{'id_card_name':'MANUAL NAME','card_period_begin':'2018-03-04'}}}}
        self.fx.call('onboarding',{'operation':'wechat_save','params':dict(application=self.app['application'],expected_version=0,profile=profile)})
        self.sources={kind:self.bridge.source(self.auth(self.fx.token),self.app['application'],kind) for kind in VALUES}
        before=service._read(self.app['application']);path=self.job();self.assertEqual(self.confirm(path).status_code,200)
        self.assertEqual(service._read(self.app['application']),before)
        result=self.bridge.apply_confirmed(self.auth(self.fx.token),path.rsplit('/',1)[1],expected_confirmation_revision=1)
        self.assertTrue(result['written']);self.assertEqual(result['applied'],['valid_to']);self.assertEqual(result['skipped'],['valid_from'])
        card=service._read(self.app['application'])['profile']['subject_info']['identity_info']['id_card_info']
        self.assertEqual(card,{'id_card_name':'MANUAL NAME','card_period_begin':'2018-03-04','card_period_end':'长期'})
        self.assertNotIn('issuing_authority',json.dumps(service._read(self.app['application'])))
        self.assertEqual(self.store.get(path.rsplit('/',1)[1],self.sources['id_back']['tenant_id'])['confirmed_fields']['issuing_authority'],VALUES['id_back']['issuing_authority'])

if __name__=='__main__':unittest.main()
