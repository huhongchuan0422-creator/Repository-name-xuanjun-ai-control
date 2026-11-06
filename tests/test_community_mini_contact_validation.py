"""Mini-only phone contract over real HTTP and original encrypted draft storage.

All identities, documents and values are synthetic. No provider network calls.
"""
import base64
import json
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_community_mini_center_identity as fixture
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_mini_merchant import MiniMerchant
from scripts.community_mini_http import serve
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader


class MiniContactValidation(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ExistingCenterComposition();self.fx.setUp()
        self.onboarding=MerchantOnboarding(self.fx.center,{self.fx.uid2:'project1'})
        self.provider=WechatApplyment(self.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
        self.onboarding.wechat_applyment=self.provider
        self.merchant=MiniMerchant(self.fx.identity,self.onboarding)
        self.token=self.fx.token()
        self.server=serve(self.fx.gateway,onboarding=self.onboarding)
        self.server.timeout=3
        self.pool=ThreadPoolExecutor(1)

    def tearDown(self):
        self.pool.shutdown(wait=True);self.server.server_close();self.fx.tearDown()

    def http(self,operation,params,scene='shop1',token=None):
        body=json.dumps({'operation':'onboarding','params':{'operation':operation,'params':params}}).encode()
        headers={'Content-Type':'application/json','X-Community-Session':token or self.token}
        if scene:headers['X-Community-Scene']=scene
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/mini/merchant',data=body,headers=headers)
        def client():
            try:
                with urllib.request.urlopen(req,timeout=5) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        future=self.pool.submit(client);self.server.handle_request();return future.result(timeout=6)

    def draft(self,mobile,scene='shop1',contact='LEGAL'):
        status,result=self.http('save',dict(application=None,revision=0,entity_type='ENTERPRISE',category='GENERAL',delegated=contact=='SUPER',sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'],declarations=dict(scene='mini',ubos=0),fields=dict(legal_name='SYNTHETIC COMPANY',store_name='SYNTHETIC SHOP',address='SYNTHETIC ADDRESS',contact=mobile)),scene)
        self.assertEqual(status,200,result);app=result['result']
        profile=dict(contact_info=dict(contact_type=contact,contact_name='SYNTHETIC LEGAL' if contact=='LEGAL' else 'SYNTHETIC OPERATOR',mobile_phone=mobile,contact_email='synthetic@example.invalid'),subject_info=dict(subject_type='SUBJECT_TYPE_ENTERPRISE',business_license_info=dict(license_copy='synthetic-license',license_number='SYNTHETIC12345',merchant_name='SYNTHETIC COMPANY',legal_person='SYNTHETIC LEGAL',license_address='SYNTHETIC ADDRESS'),identity_info=dict(id_doc_type='IDENTIFICATION_TYPE_IDCARD',id_card_info=dict(id_card_copy='synthetic-front',id_card_national='synthetic-back',id_card_name='SYNTHETIC LEGAL',id_card_number='110101199001010010',id_card_address='SYNTHETIC ADDRESS',card_period_begin='2020-01-01',card_period_end='2039-01-01'))),business_info=dict(merchant_shortname='SYNTHETIC SHOP',service_phone='555-0100',sales_info=dict(sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'],mini_program_info=dict(mini_program_appid=self.fx.identity.appid,mini_program_pics=['synthetic-mini']))),settlement_info=dict(settlement_id='716',qualification_type='零售'),bank_account_info=dict(bank_account_type='BANK_ACCOUNT_TYPE_CORPORATE',account_name='SYNTHETIC COMPANY',account_bank='SYNTHETIC BANK',account_number='6222000000000000'))
        if contact=='SUPER':profile['contact_info'].update(contact_id_doc_type='IDENTIFICATION_TYPE_IDCARD',contact_id_number='110101199101010010',contact_id_doc_copy='synthetic-operator-front',contact_id_doc_copy_back='synthetic-operator-back',contact_period_begin='2020-01-01',contact_period_end='2039-01-01')
        status,result=self.http('wechat_save',dict(application=app['application'],expected_version=0,profile=profile),scene)
        self.assertEqual(status,200,result)
        status,read=self.http('read',dict(application=app['application']),scene);self.assertEqual(status,200,read)
        return read['result'],result['result'],profile

    def invalid_case(self,value,scene='shop1'):
        app,record,profile=self.draft(value,scene)
        status,read=self.http('wechat_read',dict(application=app['application']),scene)
        self.assertEqual(status,200,read);self.assertEqual(read['result']['profile']['contact_info']['mobile_phone'],value)
        self.assertEqual(read['result']['profile']['business_info']['service_phone'],'555-0100')
        for op,key,version in [('submit','revision',app['revision']),('wechat_submit_review','expected_version',record['version'])]:
            status,result=self.http(op,{'application':app['application'],key:version},scene)
            self.assertEqual(status,400,result);self.assertEqual(result['error'],'INVALID_REQUEST')
            with self.assertRaisesRegex(ValueError,'INVALID_MINI_CONTACT_MOBILE'):
                self.merchant.dispatch(self.token,scene,dict(operation='onboarding',params=dict(operation=op,params={'application':app['application'],key:version})))
        self.assertEqual(self.provider._read(app['application'])['state'],'DRAFT')
        self.assertEqual(self.onboarding._load(app['application'],self.fx.uid1)[2]['status'],'DRAFT')
        self.assertEqual(self.provider._read(app['application'])['profile'],profile)

    def test_short_rejected_only_on_both_formal_submits(self):self.invalid_case('1380013800')
    def test_long_rejected_and_saved_reopened_without_truncation(self):self.invalid_case('1380013800012345678901')
    def test_plus_rejected_in_sceneless_owner_route(self):self.invalid_case('+13800138000','')
    def test_non_numeric_rejected(self):self.invalid_case('13800138x00')
    def test_empty_draft_preserved_but_not_submitted(self):self.invalid_case('')

    def test_valid_eleven_digits_reach_original_wechat_review_and_preserve_service_phone(self):
        app,record,profile=self.draft('00123456789',contact='SUPER')
        status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=record['version']))
        self.assertEqual(status,200,result);self.assertEqual(result['result']['state'],'PENDING_INTERNAL_REVIEW')
        self.assertEqual(result['result']['profile']['contact_info']['contact_name'],'SYNTHETIC OPERATOR')
        self.assertEqual(result['result']['profile']['business_info']['service_phone'],'555-0100')

    def test_web_validation_contract_remains_unchanged(self):
        app,record,profile=self.draft('+44-123456789')
        self.provider._validate(profile,'ENTERPRISE')
        self.assertEqual(profile['business_info']['service_phone'],'555-0100')

    def test_other_owner_cannot_probe_invalid_phone(self):
        app,record,_=self.draft('123')
        other=self.fx.token('different-login','openid2')
        for op,key,version in [('submit','revision',app['revision']),('wechat_submit_review','expected_version',record['version'])]:
            status,result=self.http(op,{'application':app['application'],key:version},token=other)
            self.assertEqual(status,403,result)

    def test_body_cannot_supply_a_valid_phone_to_override_stored_invalid_value(self):
        app,record,_=self.draft('123')
        status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=record['version'],mobile_phone='13800138000'))
        self.assertEqual(status,400,result);self.assertEqual(self.provider._read(app['application'])['state'],'DRAFT')

    def test_stale_provider_version_cannot_validate_a_newer_draft(self):
        app,record,profile=self.draft('13800138000')
        profile['contact_info']['mobile_phone']='123'
        status,result=self.http('wechat_save',dict(application=app['application'],expected_version=record['version'],profile=profile));self.assertEqual(status,200,result)
        status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=record['version']));self.assertEqual(status,400,result)
        self.assertEqual(self.provider._read(app['application'])['state'],'DRAFT')

    def test_enterprise_personal_draft_is_preserved_without_changing_original_submit_contract(self):
        app,record,profile=self.draft('13800138000')
        profile['bank_account_info'].update(bank_account_type='BANK_ACCOUNT_TYPE_PERSONAL',account_name='SYNTHETIC LEGAL')
        status,result=self.http('wechat_save',dict(application=app['application'],expected_version=record['version'],profile=profile))
        self.assertEqual(status,200,result)
        self.assertEqual(result['result']['profile']['bank_account_info']['bank_account_type'],'BANK_ACCOUNT_TYPE_PERSONAL')
        status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=result['result']['version']))
        self.assertEqual(status,400,result)
        with self.assertRaisesRegex(ValueError,'OFFICIAL_BANK_ACCOUNT_TYPE_MISMATCH'):self.provider._validate(profile,'ENTERPRISE')

    def test_original_revision_checks_stop_a_contact_change_after_mini_validation(self):
        app,record,profile=self.draft('13800138000')
        original=self.onboarding.dispatch
        def changed(token,csrf,body,**kwargs):
            profile['contact_info']['mobile_phone']='123'
            self.provider.dispatch(token,csrf,dict(operation='wechat_save',params=dict(application=app['application'],expected_version=record['version'],profile=profile)))
            return original(token,csrf,body,**kwargs)
        with patch.object(self.onboarding,'dispatch',side_effect=changed):
            status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=record['version']))
        self.assertEqual(status,400,result);self.assertEqual(self.provider._read(app['application'])['state'],'DRAFT')

    def test_native_reuse_uses_real_save_read_and_reopen(self):
        import os,subprocess,time
        from pathlib import Path
        child=subprocess.Popen(['node','tests/community_mini_contact_reuse_http.cjs'],cwd=Path(__file__).resolve().parents[1],env=dict(os.environ,COMMUNITY_TEST_ORIGIN='http://127.0.0.1:'+str(self.server.server_port)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.server.timeout=.05;deadline=time.monotonic()+15
        try:
            while child.poll() is None and time.monotonic()<deadline:
                self.server.handle_request()
                self.fx.stage.now+=4  # Advance the synthetic clock, not service limits.
            if child.poll() is None:child.kill();child.wait();self.fail('CONTACT_NATIVE_HTTP_TIMEOUT')
            output,error=child.communicate();self.assertEqual(child.returncode,0,error)
            receipt=json.loads(output);self.assertTrue(receipt['saved_reopened']);self.assertTrue(receipt['historical_conflicts_preserved']);self.assertEqual(receipt['formal_submissions'],0)
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdout.close();child.stderr.close()

    def complete_platform_materials(self,app):
        self.fx.center.scanner=lambda raw:True
        raw=base64.b64encode(b'\x89PNG\r\n\x1a\nSynthetic contact race document').decode()
        for kind in app['required_materials']:
            status,result=self.http('upload',dict(application=app['application'],revision=app['revision'],kind=kind,content_base64=raw,expires_at=None))
            self.assertEqual(status,200,result);app=result['result']
        return app

    def test_platform_submit_uses_its_own_revision_bound_phone_when_provider_mobile_disappears_after_check(self):
        app,record,profile=self.draft('13800138000');app=self.complete_platform_materials(app)
        original=self.onboarding.dispatch;observed={}
        def changed(token,csrf,body,**kwargs):
            if body['operation']=='submit':
                before=self.onboarding._load(app['application'],self.fx.uid1)[2]
                del profile['contact_info']['mobile_phone']
                self.provider.dispatch(token,csrf,dict(operation='wechat_save',params=dict(application=app['application'],expected_version=record['version'],profile=profile)))
                after=self.onboarding._load(app['application'],self.fx.uid1)[2]
                observed.update(before_revision=before['revision'],after_revision=after['revision'],contact=after['fields']['contact'])
            return original(token,csrf,body,**kwargs)
        with patch.object(self.onboarding,'dispatch',side_effect=changed):
            status,result=self.http('submit',dict(application=app['application'],revision=app['revision']))
        self.assertEqual(status,200,result);self.assertEqual(result['result']['status'],'SUBMITTED')
        self.assertEqual(observed,dict(before_revision=app['revision'],after_revision=app['revision'],contact='13800138000'))
        self.assertNotIn('mobile_phone',self.provider._read(app['application'])['profile']['contact_info'])
        self.assertEqual(self.onboarding._load(app['application'],self.fx.uid1)[2]['fields']['contact'],'13800138000')

    def test_invalid_platform_phone_cannot_borrow_valid_provider_phone(self):
        from scripts import community_onboarding_offline as workflow
        app,record,profile=self.draft('13800138000')
        fields=dict(app['fields'],contact='123',license_ref='PRIVATE_ONBOARDING_MATERIALS')
        workflow.save_draft(self.fx.center.db,self.fx.uid1,app['application'],self.fx.uid1,fields,app['revision'],encode=lambda value:self.onboarding._encode(value,'onboarding-fields:'+app['application']))
        current=self.onboarding._load(app['application'],self.fx.uid1)[2]
        self.assertEqual(current['fields']['contact'],'123');self.assertEqual(self.provider._read(app['application'])['profile']['contact_info']['mobile_phone'],'13800138000')
        status,result=self.http('submit',dict(application=app['application'],revision=current['revision']))
        self.assertEqual(status,400,result)
        with self.assertRaisesRegex(ValueError,'INVALID_MINI_CONTACT_MOBILE'):
            self.merchant.dispatch(self.token,'shop1',dict(operation='onboarding',params=dict(operation='submit',params=dict(application=app['application'],revision=current['revision']))))
        self.assertEqual(self.onboarding._load(app['application'],self.fx.uid1)[2]['status'],'DRAFT')

    def test_platform_review_does_not_require_a_provider_draft(self):
        status,result=self.http('save',dict(application=None,revision=0,entity_type='ENTERPRISE',category='GENERAL',delegated=False,sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'],declarations=dict(scene='mini',ubos=0),fields=dict(legal_name='SYNTHETIC COMPANY',store_name='SYNTHETIC SHOP',address='SYNTHETIC ADDRESS',contact='13800138000')))
        self.assertEqual(status,200,result);app=self.complete_platform_materials(result['result'])
        self.assertIsNone(self.provider._read(app['application']))
        status,result=self.http('submit',dict(application=app['application'],revision=app['revision']))
        self.assertEqual(status,200,result);self.assertEqual(result['result']['status'],'SUBMITTED');self.assertIsNone(self.provider._read(app['application']))


if __name__=='__main__':unittest.main()
