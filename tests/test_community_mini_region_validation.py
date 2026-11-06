"""Synthetic real HTTP mini admission; no provider execution or real documents."""
import copy
import unittest
from unittest.mock import patch
import test_community_mini_contact_validation as contact
from scripts import community_merchant_onboarding as onboarding_module


class MiniRegionValidation(unittest.TestCase):
    setUp=contact.MiniContactValidation.setUp
    tearDown=contact.MiniContactValidation.tearDown
    http=contact.MiniContactValidation.http
    draft=contact.MiniContactValidation.draft
    complete_platform_materials=contact.MiniContactValidation.complete_platform_materials

    def store_draft(self,address='广东省深圳市南山区合成路1号',code='440305',scene='shop1'):
        app,record,profile=self.draft('13800138000',scene)
        status,result=self.http('save',dict(application=app['application'],revision=app['revision'],entity_type='ENTERPRISE',category='GENERAL',delegated=False,sales_scenes_type=['SALES_SCENES_STORE'],declarations=dict(scene='store',ubos=0),fields=app['fields']),scene)
        self.assertEqual(status,200,result)
        profile['subject_info']['business_license_info']['license_address']=address
        profile['business_info']['sales_info']=dict(sales_scenes_type=['SALES_SCENES_STORE'],biz_store_info=dict(biz_store_name='SYNTHETIC SHOP',biz_address_code=code,biz_store_address=address,store_entrance_pic=['synthetic-storefront'],indoor_pic=['synthetic-interior']))
        status,result=self.http('wechat_save',dict(application=app['application'],expected_version=record['version'],profile=profile),scene)
        self.assertEqual(status,200,result);record=result['result']
        status,result=self.http('read',dict(application=app['application']),scene);self.assertEqual(status,200,result)
        return result['result'],record,profile

    def assert_both_reject(self,address,code,reason,scene='shop1'):
        app,record,profile=self.store_draft(address,code,scene)
        before=copy.deepcopy(self.onboarding._load(app['application'],self.fx.uid1))
        for op,key,version in [('submit','revision',app['revision']),('wechat_submit_review','expected_version',record['version'])]:
            status,result=self.http(op,dict(application=app['application'],**{key:version}),scene)
            self.assertEqual(status,400,result);self.assertEqual(result['error'],'MINI_LICENSE_REGION_INVALID')
            self.assertEqual(result['reason'],reason);self.assertEqual(result['correction_step'],0)
            self.assertNotIn('合成路',str(result))
        self.assertEqual(self.onboarding._load(app['application'],self.fx.uid1),before)
        self.assertEqual(self.provider._read(app['application']),record)
        self.assertEqual(record['profile'],profile)

    def test_fake_code_rejected_on_both_submits(self):self.assert_both_reject('广东省深圳市南山区合成路1号','999999','INVALID_REGION_CODE')
    def test_missing_code_draft_preserved_sceneless(self):self.assert_both_reject('广东省深圳市南山区合成路1号','','INVALID_REGION_CODE','')
    def test_existing_other_valid_code_not_silently_overwritten(self):self.assert_both_reject('广东省深圳市南山区合成路1号','110105','REGION_CODE_MISMATCH')
    def test_omitted_alternative_district_ambiguity(self):self.assert_both_reject('广东省深圳市南山区或福田区合成路1号','440305','AMBIGUOUS_ADDRESS')
    def test_missing_modern_directory_name_preserves_real_address(self):self.assert_both_reject('河北省唐山市滦州市合成路1号','440305','DIRECTORY_MISMATCH')
    def test_incomplete_address_does_not_reuse_old_code(self):self.assert_both_reject('南山区','440305','INCOMPLETE_ADDRESS')

    def test_valid_same_version_store_reaches_both_original_reviews_under_platform_lock(self):
        app,record,profile=self.store_draft('深圳市南山区合成路1号');app=self.complete_platform_materials(app)
        observed=[];original=onboarding_module.validate_mini_license_region
        def checked(meta,profile):
            observed.append(self.fx.center.db.in_transaction)
            return original(meta,profile)
        with patch.object(onboarding_module,'validate_mini_license_region',side_effect=checked):
            status,result=self.http('submit',dict(application=app['application'],revision=app['revision']))
        self.assertEqual(status,200,result);self.assertEqual(result['result']['status'],'SUBMITTED');self.assertEqual(observed,[True])
        status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=record['version']))
        self.assertEqual(status,200,result);self.assertEqual(result['result']['state'],'PENDING_INTERNAL_REVIEW')

    def test_platform_rechecks_current_provider_region_after_precheck_without_platform_revision_change(self):
        app,record,profile=self.store_draft();app=self.complete_platform_materials(app)
        original=self.onboarding.dispatch;observed={}
        def changed(token,csrf,body,**kwargs):
            if body['operation']=='submit':
                profile['business_info']['sales_info']['biz_store_info']['biz_address_code']='110105'
                self.provider.dispatch(token,csrf,dict(operation='wechat_save',params=dict(application=app['application'],expected_version=record['version'],profile=profile)))
                observed['revision']=self.onboarding._load(app['application'],self.fx.uid1)[2]['revision']
            return original(token,csrf,body,**kwargs)
        materials=copy.deepcopy(app['materials'])
        with patch.object(self.onboarding,'dispatch',side_effect=changed):
            status,result=self.http('submit',dict(application=app['application'],revision=app['revision']))
        self.assertEqual(observed['revision'],app['revision']);self.assertEqual(status,400,result);self.assertEqual(result['reason'],'REGION_CODE_MISMATCH')
        status,result=self.http('read',dict(application=app['application']));self.assertEqual(result['result']['status'],'DRAFT');self.assertEqual(result['result']['materials'],materials)

    def test_provider_expected_version_stops_region_change_after_precheck(self):
        app,record,profile=self.store_draft();original=self.onboarding.dispatch
        def changed(token,csrf,body,**kwargs):
            profile['business_info']['sales_info']['biz_store_info']['biz_address_code']='110105'
            self.provider.dispatch(token,csrf,dict(operation='wechat_save',params=dict(application=app['application'],expected_version=record['version'],profile=profile)))
            return original(token,csrf,body,**kwargs)
        with patch.object(self.onboarding,'dispatch',side_effect=changed):
            status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=record['version']))
        self.assertEqual(status,400,result);self.assertEqual(self.provider._read(app['application'])['state'],'DRAFT')

    def test_other_owner_and_body_bypass_denied(self):
        app,record,_=self.store_draft(code='999999');other=self.fx.token('other-region','openid2')
        status,result=self.http('submit',dict(application=app['application'],revision=app['revision']),token=other);self.assertEqual(status,403,result)
        for key in ('_mini_submission','mini_submission','validate_region'):
            status,result=self.http('submit',dict(application=app['application'],revision=app['revision'],**{key:False}))
            self.assertEqual(status,400,result)
        self.assertEqual(self.onboarding._load(app['application'],self.fx.uid1)[2]['status'],'DRAFT')

    def test_mini_only_and_existing_web_operating_address_contract_unchanged(self):
        app,record,_=self.draft('13800138000')
        status,result=self.http('wechat_submit_review',dict(application=app['application'],expected_version=record['version']))
        self.assertEqual(status,200,result)
        app,record,profile=self.store_draft(code='110105')
        # Original Web intentionally accepts a different operating region. Do not
        # impose mini's reused-license relationship on that separate workflow.
        self.provider._validate(profile,'ENTERPRISE')
        _,csrf=self.fx.identity.applicant_context(self.token)
        result=self.onboarding.dispatch(self.token,csrf,dict(operation='wechat_submit_review',params=dict(application=app['application'],expected_version=record['version'])))
        self.assertEqual(result['state'],'PENDING_INTERNAL_REVIEW')


if __name__=='__main__':unittest.main()
