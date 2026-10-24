"""Real Center source -> existing dual CAS; NOT OCR confirmation integration.

All material and manually supplied confirmation values are synthetic. No HTTP,
OCR dependency replacement, production grant or shared bridge HOLD removal.
"""
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch
import test_community_mini_merchant as fixture
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader


class SharedSourcePreparation(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.OcrSourceBoundary();self.fx.setUp()
        self.c=self.fx.fx.center;self.merchant=self.fx.service
        self.service=WechatApplyment(self.fx.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
        self.fx.onboarding.wechat_applyment=self.service
        app=self.fx.draft()
        self.app=self.fx.call('onboarding',{'operation':'save','params':dict(application=app['application'],revision=app['revision'],
            entity_type='ENTERPRISE',category='GENERAL',delegated=False,
            fields=dict(legal_name='',address='',store_name='SYNTHETIC STORE',contact='SYNTHETIC CONTACT'))})
        self.app=self.fx.material(self.app)
        self.fx.call('onboarding',{'operation':'wechat_save','params':dict(application=self.app['application'],expected_version=0,
            profile={'subject_info':{'business_license_info':{}}})})
    def tearDown(self):self.fx.tearDown()
    def snapshot(self):return '\n'.join(self.c.db.iterdump())
    def source(self,kind='business_license',token=None):
        return self.merchant.ocr_shared_source(token or self.fx.token,'shop1',self.app['application'],kind)
    def fill_fixture(self,source):
        # This is a test-only manually frozen confirmation, not an OCR binding.
        return self.service.fill_confirmed_license_draft(self.fx.token,self.merchant.context(self.fx.token,'shop1')[2],self.app['application'],
            expected_application_revision=source['application_revision'],expected_wechat_version=source['wechat_version'],
            confirmed_fields={'company_name':'SYNTHETIC HUMAN','registered_address':'SYNTHETIC ADDRESS'})
    def test_original_subject_business_tenant_bytes_and_versions_no_writes(self):
        before=self.snapshot();s=self.source()
        self.assertEqual(s['subject'],self.fx.fx.uid1)
        self.assertEqual(s['tenant_id'],self.fx.fx.stage.customer.tenant_id)
        self.assertNotEqual(s['subject'],s['tenant_id'])
        self.assertEqual(s['wechat_version'],1);self.assertIs(type(s['wechat_version']),int)
        self.assertEqual(s['application_revision'],self.fx.onboarding._load(self.app['application'],s['subject'])[2]['revision'])
        self.assertEqual(s['data'],b'\x89PNG\r\n\x1a\nSynthetic document, not a real credential')
        self.assertEqual(self.snapshot(),before);self.assertFalse(self.c.db.in_transaction)
    def test_frozen_source_versions_feed_original_cas_once(self):
        s=self.source();r=self.fill_fixture(s)
        self.assertEqual((r['application_revision'],r['wechat_version']),(s['application_revision']+1,s['wechat_version']+1))
        before=self.snapshot()
        with self.assertRaises(ValueError):self.fill_fixture(s)
        self.assertEqual(self.snapshot(),before)
    def test_provider_edit_after_observation_not_replaced_by_latest(self):
        s=self.source();r=self.service._read(self.app['application']);r['version']+=1
        r['profile']['subject_info']['business_license_info']['merchant_name']='MANUAL LATER'
        with self.c.tx():self.service._save(self.app['application'],s['subject'],r)
        before=self.snapshot()
        with self.assertRaises(ValueError):self.fill_fixture(s)
        self.assertEqual(self.snapshot(),before)
    def test_application_edit_after_observation_rejected(self):
        s=self.source();self.c.db.execute('UPDATE onboarding SET revision=revision+1 WHERE application=?',(self.app['application'],))
        before=self.snapshot()
        with self.assertRaises(ValueError):self.fill_fixture(s)
        self.assertEqual(self.snapshot(),before)
    def test_absent_provider_is_original_zero_not_a_new_record(self):
        self.c.db.execute("DELETE FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(self.app['application'],))
        before=self.snapshot();self.assertEqual(self.source()['wechat_version'],0);self.assertEqual(self.snapshot(),before)
    def test_provider_versions_reject_bool_string_float_negative(self):
        r=self.service._read(self.app['application'])
        for value in (True,False,'1',1.0,-1,0,None):
            r['version']=value
            with self.c.tx():self.service._save(self.app['application'],self.fx.fx.uid1,r)
            before=self.snapshot()
            with self.assertRaises(PermissionError):self.source()
            self.assertEqual(self.snapshot(),before)
    def test_revoked_provider_or_different_owner_not_absent_zero(self):
        for column,value in (('active',0),('user_id',self.fx.fx.uid2)):
            original=1 if column=='active' else self.fx.fx.uid1
            self.c.db.execute('UPDATE links SET '+column+"=? WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(value,self.app['application']))
            before=self.snapshot()
            with self.assertRaises(PermissionError):self.source()
            self.assertEqual(self.snapshot(),before)
            self.c.db.execute('UPDATE links SET '+column+"=? WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(original,self.app['application']))
    def test_original_session_tenant_and_application_origin_required(self):
        other=self.fx.fx.token('othercode','openid2')
        with self.assertRaises(PermissionError):self.source(token=other)
        principal=self.fx.fx.stage.customer;bindings=self.fx.fx.identity.runtime.bindings
        old=bindings[principal];bindings[principal]={**old,'tenant_id':'OTHER'}
        with self.assertRaises(PermissionError):self.source()
        bindings[principal]=old
        self.c.logout(self.fx.token)
        with self.assertRaises(PermissionError):self.source()
    def test_provider_and_platform_edit_states_required(self):
        r=self.service._read(self.app['application']);r['state']='SUBMITTED'
        with self.c.tx():self.service._save(self.app['application'],self.fx.fx.uid1,r)
        with self.assertRaises(PermissionError):self.source()
        r['state']='DRAFT'
        with self.c.tx():self.service._save(self.app['application'],self.fx.fx.uid1,r)
        self.c.db.execute("UPDATE onboarding SET status='SUBMITTED' WHERE application=?",(self.app['application'],))
        with self.assertRaises(PermissionError):self.source()
    def test_provider_decrypt_mutation_rolls_back_and_does_not_release(self):
        original=self.service._read;before=self.snapshot()
        def read(application):
            r=original(application)
            self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(application,))
            return r
        with patch.object(self.service,'_read',side_effect=read):
            with self.assertRaises(PermissionError):self.source()
        self.assertEqual(self.snapshot(),before)
    def test_transaction_blocks_concurrent_provider_writer(self):
        original=self.service._read;blocked=[]
        def read(application):
            def writer():
                db=sqlite3.connect(self.c.root/'center.sqlite',timeout=.01,isolation_level=None)
                try:db.execute('BEGIN IMMEDIATE');db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(application,));db.commit()
                except sqlite3.OperationalError:blocked.append(True)
                finally:db.close()
            t=threading.Thread(target=writer);t.start();t.join(2);self.assertFalse(t.is_alive())
            return original(application)
        with patch.object(self.service,'_read',side_effect=read):self.source()
        self.assertTrue(blocked)
    def test_mid_read_platform_change_same_revision_rolls_back(self):
        original=self.service._read;before=self.snapshot()
        def read(application):
            r=original(application)
            self.c.db.execute("UPDATE onboarding SET status='SUBMITTED' WHERE application=?",(application,))
            return r
        with patch.object(self.service,'_read',side_effect=read):
            with self.assertRaises(PermissionError):self.source()
        self.assertEqual(self.snapshot(),before)
    def test_second_source_read_provider_change_rejects_and_rolls_back(self):
        original=self.merchant.ocr_source;calls=[];before=self.snapshot()
        def source(*args):
            result=original(*args);calls.append(True)
            if len(calls)==2:
                self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(self.app['application'],))
            return result
        with patch.object(self.merchant,'ocr_source',side_effect=source):
            with self.assertRaises(PermissionError):self.source()
        self.assertEqual(self.snapshot(),before)
    def test_photos_no_source_idcard_only_existing_front_target(self):
        for kind in ('storefront_photo','interior_photo','cashier_photo'):
            with self.assertRaises(PermissionError):self.source(kind)
        self.app=self.fx.material(self.app,kind='identity_front')
        s=self.source('identity_front');self.assertEqual(s['document_type'],'id_front')
        before=self.snapshot()
        with self.assertRaises(ValueError):self.service.fill_confirmed_license_draft(self.fx.token,self.merchant.context(self.fx.token,'shop1')[2],self.app['application'],
            expected_application_revision=s['application_revision'],expected_wechat_version=s['wechat_version'],confirmed_fields={'id_name':'SYNTHETIC'})
        self.assertEqual(self.snapshot(),before)
    def test_no_external_transaction_no_http_and_bridge_hold_unchanged(self):
        with self.c.tx():
            with self.assertRaises(ValueError):self.source()
        from pathlib import Path
        self.assertIn('OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED',Path('scripts/community_ocr_bridge.py').read_text())
        with self.assertRaises(PermissionError):self.fx.call('onboarding',{'operation':'ocr_shared_source','params':{}})
