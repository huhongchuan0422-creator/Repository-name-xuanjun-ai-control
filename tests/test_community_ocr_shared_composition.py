"""Pinned real OCR HTTP/store + original Center, synthetic admission/inference.

No engine mock, always-allow source resolver, real documents or production grant.
"""
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
import test_community_ocr_bridge as fixture
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader


class SharedOcrComposition(unittest.TestCase):
    setUpClass=classmethod(fixture.OcrComposition.setUpClass.__func__)
    tearDownClass=classmethod(fixture.OcrComposition.tearDownClass.__func__)
    tearDown=fixture.OcrComposition.tearDown
    submit=fixture.OcrComposition.submit
    job=fixture.OcrComposition.job
    def setUp(self):
        fixture.OcrComposition.setUp(self)
        self.wechat=WechatApplyment(self.fx.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
        self.fx.onboarding.wechat_applyment=self.wechat
        self.app=self.fx.call('onboarding',{'operation':'save','params':dict(application=self.app['application'],revision=self.app['revision'],
            entity_type='ENTERPRISE',category='GENERAL',delegated=False,fields=dict(legal_name='',address='',store_name='SYNTHETIC',contact='SYNTHETIC'))})
        self.fx.call('onboarding',{'operation':'wechat_save','params':dict(application=self.app['application'],expected_version=0,
            profile={'subject_info':{'business_license_info':{}}})})
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'business_license')
        self.c=self.fx.fx.center
    def snapshot(self):return '\n'.join(self.c.db.iterdump())
    def read(self,path):return self.client.get(path,headers=self.headers)
    def confirm(self,path,*,revision=1,key='synthetic-confirm-A01',fields=None,seen=None):
        seen=seen or self.read(path).json()
        return self.client.post(path+'/confirm',headers={**self.headers,'Idempotency-Key':key},json={
            'revision':revision,'fields':fields or {'company_name':'HUMAN FIRST','registered_address':'HUMAN ADDRESS'},
            'application_revision':seen['application_revision'],'provider_version':seen['provider_version']})
    def confirmed(self):
        path=self.job();seen=self.read(path).json();r=self.confirm(path,seen=seen)
        self.assertEqual(r.status_code,200,r.text);return path,r.json()
    def apply(self,path,revision=1,p=None):
        return self.bridge.apply_confirmed(p or self.auth(self.fx.token),path.rsplit('/',1)[1],expected_confirmation_revision=revision)
    def provider_edit(self):
        r=self.wechat._read(self.app['application']);r['version']+=1
        with self.c.tx():self.wechat._save(self.app['application'],self.fx.fx.uid1,r)
    def test_real_http_confirm_persists_exact_tuple_and_original_dual_cas(self):
        path,ack=self.confirmed();jobid=path.rsplit('/',1)[1]
        # A fresh store instance over the same existing encrypted DB/key.
        self.store=self.api.SecureSQLiteJobStore(self.store.db_path,self.store_key)
        self.bridge.store=self.store
        job=self.store.get(jobid,self.source['tenant_id'])
        self.assertEqual(job['confirmed_binding'],dict(application_revision=self.source['application_revision'],provider_version=self.source['wechat_version'],
            document_type='business_license',attachment_id=self.source['attachment_id'],content_sha256=self.source['document_sha256']))
        self.assertEqual(ack['confirmed_binding'],job['confirmed_binding'])
        self.assertNotIn(b'HUMAN FIRST',Path(self.store.db_path).read_bytes())
        r=self.apply(path);self.assertTrue(r['written'])
        self.assertEqual(r['application_revision'],int(self.source['application_revision'])+1);self.assertEqual(r['wechat_version'],self.source['wechat_version']+1)
        data=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]
        self.assertEqual(data['fields']['legal_name'],'HUMAN FIRST');self.assertEqual(data['fields']['address'],'HUMAN ADDRESS')
        self.assertEqual(self.wechat._read(self.app['application'])['profile'],{'subject_info':{'business_license_info':{'merchant_name':'HUMAN FIRST'}}})
        before=self.snapshot()
        with self.assertRaises((PermissionError,ValueError)):self.apply(path)
        self.assertEqual(self.snapshot(),before)
    def test_seen_versions_required_and_bool_or_wrong_versions_rejected(self):
        path=self.job();seen=self.read(path).json()
        for key in ('application_revision','provider_version'):
            for value in (True,False,1.0,'01',' 1',999):
                bad={**seen,key:value};before=self.snapshot();r=self.confirm(path,seen=bad)
                self.assertIn(r.status_code,(400,403,409),r.text);self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.store.get(path.rsplit('/',1)[1],self.source['tenant_id'])['status'],'needs_review')
    def test_stale_seen_provider_confirm_and_current_application_confirm_rejected(self):
        path=self.job();seen=self.read(path).json();self.provider_edit();before=self.snapshot()
        self.assertEqual(self.confirm(path,seen=seen).status_code,403);self.assertEqual(self.snapshot(),before)
    def test_both_current_versions_must_match_before_write(self):
        for target in ('provider','application'):
            with self.subTest(target=target):
                path,_=self.confirmed()
                if target=='provider':self.provider_edit()
                else:self.c.db.execute('UPDATE onboarding SET revision=revision+1 WHERE application=?',(self.app['application'],))
                before=self.snapshot()
                with self.assertRaises((PermissionError,ValueError)):self.apply(path)
                self.assertEqual(self.snapshot(),before)
                # New source/job uses a new payload after the independent edit.
                self.headers['Idempotency-Key']='synthetic-next-submit-'+target
                self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'business_license')
    def test_cross_subject_tenant_application_and_type_same_sha_refused(self):
        path,_=self.confirmed()
        for key in ('subject','tenant_id'):
            p=self.auth(self.fx.token);setattr(p,key,'OTHER');before=self.snapshot()
            with self.assertRaises(PermissionError):self.apply(path,p=p)
            self.assertEqual(self.snapshot(),before)
        other=self.fx.fx.token('othercode','openid2')
        self.assertIn(self.client.get(path,headers={'Authorization':'Bearer '+other}).status_code,(403,404))
        self.assertEqual(self.submit(document_type='id_front').status_code,403)
        self.assertEqual(self.submit(onboarding_application_id=self.fx.draft()['application']).status_code,403)
    def test_scan_revoke_or_attachment_replace_reject_http_and_write(self):
        path,_=self.confirmed();self.c.db.execute("UPDATE objects SET scan='BLOCKED' WHERE id=?",(self.source['attachment_id'],))
        before=self.snapshot();self.assertEqual(self.read(path).status_code,403)
        self.assertEqual(self.confirm(path,seen=self.source|{'provider_version':self.source['wechat_version']}).status_code,403)
        self.assertEqual(self.client.delete(path,headers=self.headers).status_code,403)
        with self.assertRaises(PermissionError):self.apply(path)
        self.assertEqual(self.snapshot(),before)
    def test_replaced_attachment_rejects_persisted_confirmation(self):
        path,_=self.confirmed()
        _,_,current=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)
        self.fx.material({'application':self.app['application'],'revision':current['revision']},raw=self.raw+b'REPLACED')
        before=self.snapshot()
        with self.assertRaises(PermissionError):self.apply(path)
        self.assertEqual(self.snapshot(),before)
    def test_permission_absent_and_revoked_original_session_remain_closed(self):
        self.assertEqual(self.submit(self.closed).status_code,403)
        path,_=self.confirmed();before=self.snapshot()
        with self.assertRaises(PermissionError):self.apply(path,p=self.bridge.authenticate(self.fx.token))
        self.assertEqual(self.snapshot(),before)
        self.c.logout(self.fx.token);before=self.snapshot()
        self.assertIn(self.read(path).status_code,(401,403))
        with self.assertRaises(PermissionError):self.apply(path)
        self.assertEqual(self.snapshot(),before)
    def test_old_key_snapshot_cannot_select_current_confirmation_or_fields(self):
        path=self.job();seen=self.read(path).json()
        a=self.confirm(path,seen=seen);b=self.confirm(path,seen=seen,revision=2,key='synthetic-confirm-B02',fields={'company_name':'HUMAN SECOND'})
        self.assertEqual(b.status_code,200,b.text)
        replay=self.confirm(path,seen=seen);self.assertEqual(replay.json(),a.json())
        self.assertEqual(replay.json()['confirmed_fields']['company_name'],'HUMAN FIRST')
        before=self.snapshot()
        with self.assertRaises(PermissionError):self.apply(path,revision=replay.json()['revision'])
        self.assertEqual(self.snapshot(),before)
        self.assertTrue(self.apply(path,revision=2)['written'])
        self.assertEqual(self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]['fields']['legal_name'],'HUMAN SECOND')
    def test_cas_race_after_cross_database_precheck_is_zero_application_write(self):
        path,_=self.confirmed();original=self.wechat.fill_confirmed_license_draft;after=[]
        def raced(*args,**kwargs):
            self.provider_edit();after.append(self.snapshot());return original(*args,**kwargs)
        with patch.object(self.wechat,'fill_confirmed_license_draft',side_effect=raced):
            with self.assertRaises(ValueError):self.apply(path)
        self.assertEqual(self.snapshot(),after[0]);self.assertEqual(self.read(path).status_code,403)
    def test_new_confirmation_between_precheck_and_transaction_refused(self):
        path,_=self.confirmed();original=self.wechat.fill_confirmed_license_draft;before=self.snapshot()
        def raced(*args,**kwargs):
            self.store.confirm(path.rsplit('/',1)[1],self.source['tenant_id'],2,{'company_name':'LATER CONFIRM'},'synthetic-later-key2',self.source['application_revision'],self.source['wechat_version'])
            return original(*args,**kwargs)
        with patch.object(self.wechat,'fill_confirmed_license_draft',side_effect=raced):
            with self.assertRaises(PermissionError):self.apply(path)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.store.get(path.rsplit('/',1)[1],self.source['tenant_id'])['confirmation_revision'],2)
    def test_source_revoked_during_second_write_rolls_back_both_center_drafts(self):
        path,_=self.confirmed();original=self.c.audit;before=self.snapshot()
        def audit(*args):
            original(*args)
            self.c.db.execute("UPDATE objects SET scan='BLOCKED' WHERE id=?",(self.source['attachment_id'],))
        with patch.object(self.c,'audit',side_effect=audit):
            with self.assertRaises(PermissionError):self.apply(path)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.store.get(path.rsplit('/',1)[1],self.source['tenant_id'])['status'],'confirmed')
    def test_real_second_write_and_audit_failure_preserve_center_and_confirmation(self):
        path,_=self.confirmed()
        for target,name in ((self.wechat,'_save'),(self.c,'audit')):
            before=self.snapshot();original=getattr(target,name)
            def failed(*args,**kwargs):
                original(*args,**kwargs)
                raise RuntimeError('SYNTHETIC AFTER REAL WRITE')
            with patch.object(target,name,side_effect=failed):
                with self.assertRaises(RuntimeError):self.apply(path)
            self.assertEqual(self.snapshot(),before)
            self.assertEqual(self.store.get(path.rsplit('/',1)[1],self.source['tenant_id'])['status'],'confirmed')
    def test_deleted_confirmation_during_center_transaction_rolls_back_center_only(self):
        path,_=self.confirmed();original=self.c.audit;before=self.snapshot()
        def audit(*args):
            original(*args)
            self.store.delete(path.rsplit('/',1)[1],self.source['tenant_id'])
        with patch.object(self.c,'audit',side_effect=audit):
            with self.assertRaises(PermissionError):self.apply(path)
        self.assertEqual(self.snapshot(),before)
        self.assertIsNone(self.store.get(path.rsplit('/',1)[1],self.source['tenant_id']))
    def test_manual_values_preserved_and_only_defined_license_fields_written(self):
        # Source is observed only after the manual edit; confirmation cannot overwrite it.
        _,_,current=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)
        self.fx.call('onboarding',{'operation':'save','params':dict(application=self.app['application'],revision=current['revision'],entity_type='ENTERPRISE',category='GENERAL',delegated=False,
            fields=dict(legal_name='MANUAL NAME',address='MANUAL ADDRESS',store_name='SYNTHETIC',contact='SYNTHETIC'))})
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'business_license')
        path,_=self.confirmed();before=self.snapshot();self.assertFalse(self.apply(path)['written']);self.assertEqual(self.snapshot(),before)
    def test_identity_has_no_destination_and_three_photos_make_zero_ocr_calls(self):
        _,_,current=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)
        self.app=self.fx.material({'application':self.app['application'],'revision':current['revision']},kind='identity_front')
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'id_front')
        r=self.submit(document_type='id_front');self.assertEqual(r.status_code,202,r.text)
        path='/api/v1/ocr/jobs/'+r.json()['job_id'];r=self.confirm(path,fields={'id_name':'SYNTHETIC HUMAN'})
        self.assertEqual(r.status_code,200,r.text);before=self.snapshot();self.assertFalse(self.apply(path)['written']);self.assertEqual(self.snapshot(),before)
        for kind in ('storefront_photo','interior_photo','cashier_photo'):
            with self.assertRaises(PermissionError):self.bridge.source(self.auth(self.fx.token),self.app['application'],kind)
    def test_shared_service_removal_cannot_fall_back_to_platform_only_write(self):
        path,_=self.confirmed();before=self.snapshot()
        self.fx.onboarding.wechat_applyment=None
        with self.assertRaisesRegex(PermissionError,'SHARED_DRAFT_WRITEBACK_VERSION_BINDING'):
            self.apply(path)
        self.assertEqual(self.snapshot(),before)
    def test_missing_or_mutated_confirmation_binding_not_qualified(self):
        path,_=self.confirmed();jobid=path.rsplit('/',1)[1]
        with self.assertRaises(ValueError):self.store.update(jobid,confirmed_binding={'provider_version':1})
        original=self.store.get
        for mutation in ({'confirmed_binding':None},{'provider_version':True},{'confirmation_revision':True},{'shared_writeback_eligible':True,'status':'needs_review'}):
            job=original(jobid,self.source['tenant_id']);job.update(mutation);before=self.snapshot()
            with patch.object(self.store,'get',return_value=job):
                with self.assertRaises(PermissionError):self.apply(path)
            self.assertEqual(self.snapshot(),before)
    def test_real_local_engine_output_through_original_source_confirm_restart_and_writeback(self):
        import importlib.util, io, os
        required_env=('OCR_DET_MODEL_PATH','OCR_CLS_MODEL_PATH','OCR_REC_MODEL_PATH','OCR_MODEL_SHA256')
        missing=[]
        if importlib.util.find_spec('rapidocr') is None:missing.append('rapidocr')
        if importlib.util.find_spec('PIL') is None:missing.append('PIL')
        for key in required_env:
            if not os.environ.get(key):missing.append(key)
        for key in required_env[:3]:
            value=os.environ.get(key)
            if value and (not os.path.isabs(value) or not os.path.isfile(value)):missing.append(key+'_FILE')
        fonts=['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc']
        font_path=next((value for value in fonts if os.path.isfile(value)),None)
        if font_path is None:missing.append('NotoSansCJK')
        if missing:self.skipTest('REAL_OCR_ENGINE_ENV_NOT_STAGED:'+','.join(missing))
        from PIL import Image,ImageDraw,ImageFont
        def image(kind):
            canvas=Image.new('RGB',(1800,1000),'white');draw=ImageDraw.Draw(canvas);font=ImageFont.truetype(font_path,48)
            if kind=='business_license':
                lines=['营业执照（合成测试，非真实证件）','名称：玄钧AI社区合成测试企业','统一社会信用代码：91350100M000100Y43','法定代表人：张测试','住所：重庆市测试区示例路一号','经营范围：软件开发测试']
            else:
                lines=['居民身份证（合成测试，非真实证件）','姓名：张测试','性别：男 民族：汉','出生：1990年01月01日','住址：重庆市测试区示例路一号','公民身份号码：110101199001010011']
            y=45
            for line in lines:draw.text((55,y),line,font=font,fill='black');y+=145
            out=io.BytesIO();canvas.save(out,format='PNG');return out.getvalue()
        def actual_client():
            return fixture.OwnerHttp(fixture.TestClient(self.api.create_app(authenticate=self.auth,store=self.store,
                infer=self.api.run_local_ocr,authorize_application=self.bridge.authorize_application,
                authorize_attachment=self.bridge.authorize_attachment)),self.owner)
        self.assertEqual(self.api.run_local_ocr.__module__,'community_pinned_ocr.ocr_core')
        # Business-license bytes originate from the original encrypted community attachment.
        license_bytes=image('business_license');self.raw=license_bytes
        self.app=self.fx.material(self.app,raw=license_bytes,kind='business_license')
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'business_license')
        self.assertEqual(self.source['data'],license_bytes)
        self.headers['Idempotency-Key']='real-community-license-submit-0001'
        real=actual_client()
        try:
            response=self.submit(real);self.assertEqual(response.status_code,202,response.text)
            path='/api/v1/ocr/jobs/'+response.json()['job_id'];seen=real.get(path,headers=self.headers);self.assertEqual(seen.status_code,200,seen.text)
            payload=seen.json();allowed={'company_name','registered_address'}
            confirmed={key:value['value'] for key,value in payload['fields'].items()
                       if key in allowed and type(value) is dict and type(value.get('value')) is str and value['value'].strip()}
            self.assertTrue(confirmed,'REAL_OCR_LICENSE_WRITEBACK_FIELD_REQUIRED')
            reply=real.post(path+'/confirm',headers={**self.headers,'Idempotency-Key':'real-community-license-confirm-0001'},json={
                'revision':1,'application_revision':payload['application_revision'],'provider_version':payload['provider_version'],'fields':confirmed})
            self.assertEqual(reply.status_code,200,reply.text)
        finally:real.close()
        # Reopen the encrypted store before applying the human-confirmed values.
        self.store=self.api.SecureSQLiteJobStore(self.store.db_path,self.store_key);self.bridge.store=self.store
        jobid=path.rsplit('/',1)[1];persisted=self.store.get(jobid,self.source['tenant_id']);self.assertEqual(persisted['status'],'confirmed')
        self.assertEqual(persisted['confirmed_fields'],confirmed)
        applied=self.apply(path);self.assertTrue(applied['written'])
        current=self.fx.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]
        mapping={'company_name':'legal_name','registered_address':'address'}
        for key,value in confirmed.items():self.assertEqual(current['fields'][mapping[key]],value)
        # ID-front uses the same real inference and confirmation path but has no community writeback target.
        id_bytes=image('id_front');self.raw=id_bytes
        self.app=self.fx.material({'application':self.app['application'],'revision':current['revision']},raw=id_bytes,kind='identity_front')
        self.source=self.bridge.source(self.auth(self.fx.token),self.app['application'],'id_front')
        self.headers['Idempotency-Key']='real-community-id-submit-00001'
        real=actual_client()
        try:
            response=self.submit(real,document_type='id_front');self.assertEqual(response.status_code,202,response.text)
            idpath='/api/v1/ocr/jobs/'+response.json()['job_id'];seen=real.get(idpath,headers=self.headers);self.assertEqual(seen.status_code,200,seen.text)
            payload=seen.json();allowed={'id_name','id_number','registered_address'}
            confirmed={key:value['value'] for key,value in payload['fields'].items()
                       if key in allowed and type(value) is dict and type(value.get('value')) is str and value['value'].strip()}
            self.assertTrue(confirmed,'REAL_OCR_ID_CONFIRM_FIELD_REQUIRED')
            reply=real.post(idpath+'/confirm',headers={**self.headers,'Idempotency-Key':'real-community-id-confirm-00001'},json={
                'revision':1,'application_revision':payload['application_revision'],'provider_version':payload['provider_version'],'fields':confirmed})
            self.assertEqual(reply.status_code,200,reply.text)
        finally:real.close()
        self.store=self.api.SecureSQLiteJobStore(self.store.db_path,self.store_key);self.bridge.store=self.store
        before=self.snapshot();result=self.apply(idpath);self.assertFalse(result['written']);self.assertEqual(result['reason'],'OCR_IDCARD_TARGET_UNDEFINED')
        self.assertEqual(self.snapshot(),before)

    def test_original_host_transport_echoes_seen_pair_without_auto_writeback(self):
        from scripts.community_ocr_host import HostOcr
        host=HostOcr(self.fx.service,'shop1',self.api,self.store)
        try:
            admission=fixture.TestAdmission(host.bridge)
            host.app=self.api.create_app(authenticate=admission,store=self.store,infer=fixture.synthetic_inference,
                authorize_application=host.bridge.authorize_application,authorize_attachment=host.bridge.authorize_attachment)
            def call(action,**values):
                return host.dispatch(self.fx.token,'shop1',dict(action=action,application=self.app['application'],**values))
            submitted=call('submit',document_type='business_license',idempotency_key='synthetic-host-submit')
            job=submitted['result']['job_id'];seen=call('read',job_id=job)['result'];before=self.snapshot()
            result=call('confirm',job_id=job,revision=1,fields={'company_name':'HOST HUMAN'},idempotency_key='synthetic-host-confirm',
                application_revision=seen['application_revision'],provider_version=seen['provider_version'])
            self.assertEqual(result['result']['confirmed_fields']['company_name'],'HOST HUMAN')
            self.assertEqual(result['result']['provider_version'],seen['provider_version'])
            self.assertEqual(result['writeback'],'NOT_REQUESTED_MANUAL_SUGGESTIONS_ONLY');self.assertEqual(self.snapshot(),before)
            with self.assertRaises(ValueError):call('confirm',job_id=job,revision=2,fields={'company_name':'NO SNAPSHOT'},idempotency_key='synthetic-host-missing')
        finally:host.close()
