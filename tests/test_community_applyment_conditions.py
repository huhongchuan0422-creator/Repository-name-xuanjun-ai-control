"""Synthetic official conditional fields; no merchant application submitted."""
import copy
import unittest
from types import SimpleNamespace
from scripts.community_applyment_conditions import validate
from scripts.community_wechat_applyment import WechatApplyment

NOW=1792231200

def profile():
    return dict(contact_info=dict(contact_type='LEGAL',contact_name='Fixture Owner',mobile_phone='13800000000',contact_email='owner@example.org'),
        subject_info=dict(subject_type='SUBJECT_TYPE_ENTERPRISE',business_license_info=dict(license_copy='media-license',license_number='911100000000000000',merchant_name='Fixture Company',legal_person='Fixture Owner'),identity_info=dict(id_doc_type='IDENTIFICATION_TYPE_IDCARD',id_card_info=dict(id_card_copy='media-front',id_card_national='media-back',id_card_name='Fixture Owner',id_card_number='110000200001010000',id_card_address='Fixture Address',card_period_begin='2020-01-01',card_period_end='长期'))),
        business_info=dict(merchant_shortname='Fixture Shop',service_phone='13800000000',sales_info=dict(sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'],mini_program_info=dict(mini_program_appid='wx1234567890abcdef'))),
        settlement_info=dict(settlement_id='fixture',qualification_type='fixture-industry'),bank_account_info=dict(bank_account_type='BANK_ACCOUNT_TYPE_CORPORATE',account_name='Fixture Company',account_bank='Fixture Bank',account_number='123456789'))

class ConditionalFields(unittest.TestCase):
    def test_domestic_and_optional_not_deprecated_mandatory(self):validate(profile(),'ENTERPRISE',NOW)
    def test_super_contact_requires_own_documents_but_not_deprecated_letter(self):
        p=profile();c=p['contact_info'];c['contact_type']='SUPER'
        with self.assertRaisesRegex(ValueError,'contact_id_doc_type'):validate(p,'ENTERPRISE',NOW)
        c.update(contact_id_doc_type='IDENTIFICATION_TYPE_OVERSEA_PASSPORT',contact_id_number='FIXT-1234',contact_id_doc_copy='media-operator',contact_period_begin='2020-01-01',contact_period_end='2030-01-01')
        validate(p,'ENTERPRISE',NOW)
        c['contact_id_doc_type']='IDENTIFICATION_TYPE_IDCARD';c['contact_id_number']='110000200001010000'
        with self.assertRaisesRegex(ValueError,'copy_back'):validate(p,'ENTERPRISE',NOW)
    def test_foreign_legal_document_and_bank_holder_matching(self):
        p=profile();i=p['subject_info']['identity_info'];i.pop('id_card_info');i['id_doc_type']='IDENTIFICATION_TYPE_OVERSEA_PASSPORT';i['id_doc_info']=dict(id_doc_copy='media-passport',id_doc_name='Fixture Owner',id_doc_number='FIXT-1234',id_doc_address='Fixture Address',doc_period_begin='2020-01-01',doc_period_end='2030-01-01')
        service=WechatApplyment.__new__(WechatApplyment);service.center=SimpleNamespace(now=lambda:NOW)
        service._validate(p,'ENTERPRISE')
        i['id_doc_info'].pop('id_doc_address')
        with self.assertRaisesRegex(ValueError,'id_doc_address'):service._validate(p,'ENTERPRISE')
    def test_complete_ubo_list_max_four_and_no_sensitive_error_content(self):
        p=profile();ubo=dict(ubo_id_doc_type='IDENTIFICATION_TYPE_IDCARD',ubo_id_doc_copy='media-ubo',ubo_id_doc_copy_back='media-ubo-back',ubo_id_doc_name='Fixture Beneficiary',ubo_id_doc_number='110000200001010000',ubo_id_doc_address='Private Fixture Address',ubo_period_begin='2020-01-01',ubo_period_end='长期')
        p['subject_info']['ubo_info_list']=[ubo];validate(p,'ENTERPRISE',NOW)
        ubo['ubo_id_doc_number']='secret-invalid-number'
        with self.assertRaises(ValueError) as error:validate(p,'ENTERPRISE',NOW)
        self.assertNotIn('secret-invalid',str(error.exception))
        p['subject_info']['ubo_info_list']=[copy.deepcopy(ubo)]*5
        with self.assertRaisesRegex(ValueError,'UBO_LIST'):validate(p,'ENTERPRISE',NOW)
    def test_duplicate_ubo_documents_fail_closed_without_leaking_private_number(self):
        p=profile()
        ubo=dict(ubo_id_doc_type='IDENTIFICATION_TYPE_OVERSEA_PASSPORT',
            ubo_id_doc_copy='media-front',ubo_id_doc_name='Synthetic',
            ubo_id_doc_number='TEST-1234',ubo_id_doc_address='Fixture',
            ubo_period_begin='2020-01-01',ubo_period_end='2030-01-01')
        p['subject_info']['ubo_info_list']=[copy.deepcopy(ubo),copy.deepcopy(ubo)]
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OFFICIAL_UBO_DOCUMENT') as err:
            validate(p,'ENTERPRISE',NOW)
        self.assertNotIn(ubo['ubo_id_doc_number'],str(err.exception))
        p['subject_info']['ubo_info_list'][1]['ubo_id_doc_number']='TEST-5678'
        validate(p,'ENTERPRISE',NOW)

    def test_expired_period_other_bank_store_scenes_and_activity_rates(self):
        for path,value in [('expiry','2021-01-01'),('bank','其他银行'),('scene','SALES_SCENES_MP'),('activity','fixture')]:
            p=profile()
            if path=='expiry':p['subject_info']['identity_info']['id_card_info']['card_period_end']=value
            elif path=='bank':p['bank_account_info']['account_bank']=value
            elif path=='scene':p['business_info']['sales_info']['sales_scenes_type']=[value]
            else:p['settlement_info']['activities_id']=value
            with self.assertRaises(ValueError):validate(p,'ENTERPRISE',NOW)
    def test_foreign_media_reverse_is_not_accepted_without_current_application_upload(self):
        service=WechatApplyment.__new__(WechatApplyment)
        class DB:
            def execute(self,*args):return SimpleNamespace(fetchall=lambda:[])
        service.center=SimpleNamespace(db=DB())
        with self.assertRaises(PermissionError):service._validate_media(dict(id_doc_copy_back='foreign-media'),'application',dict(materials={}))

class PlatformPassportAdmission(unittest.TestCase):
    def test_platform_draft_requires_passport_front_without_invented_back(self):
        import test_community_merchant_onboarding as fixtures
        fx=fixtures.MerchantAdmissionJourney();fx.setUp()
        try:
            app=fx.draft(identity_type='IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
            self.assertEqual(app['identity_type'],'IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
            self.assertIn('identity_front',app['required_materials']);self.assertNotIn('identity_back',app['required_materials'])
            for kind in app['required_materials']:app=fx.upload(app,kind)
            submitted=fx.call('submit',dict(application=app['application'],revision=app['revision']))
            self.assertEqual(submitted['status'],'SUBMITTED')
        finally:fx.tearDown()
