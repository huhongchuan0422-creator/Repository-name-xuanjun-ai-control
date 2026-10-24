"""Real original Center/SQLite dual-version writeback, synthetic values only.

No OCR permission, HTTP entry, provider transport or production confirmation.
"""
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as fixture
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader


class SharedLicenseCas(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.MerchantAdmissionJourney();self.fx.setUp()
        self.c=self.fx.fx.center;self.onboarding=self.fx.service
        self.service=WechatApplyment(self.onboarding,PartnerOrderReader.__new__(PartnerOrderReader),submission_enabled=False)
        self.onboarding.wechat_applyment=self.service
        self.app=self.fx.draft(fields=dict(legal_name='',address='',store_name='SYNTHETIC STORE',contact='SYNTHETIC CONTACT'))
        self.fx.call('wechat_save',dict(application=self.app['application'],expected_version=0,profile={'subject_info':{'business_license_info':{}}}))
        self.rev=self.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]['revision'];self.version=self.service._read(self.app['application'])['version']
    def tearDown(self):self.fx.tearDown()
    def snapshot(self):return '\n'.join(self.c.db.iterdump())
    def call(self,**changes):
        values=dict(expected_application_revision=self.rev,expected_wechat_version=self.version,
                    confirmed_fields={'company_name':'SYNTHETIC CONFIRMED','registered_address':'SYNTHETIC ADDRESS'})
        values.update(changes)
        return self.service.fill_confirmed_license_draft(self.fx.applicant['token'],self.fx.applicant['csrf'],self.app['application'],**values)
    def platform(self):return self.onboarding._load(self.app['application'],self.fx.fx.uid1)[2]
    def test_same_versions_commit_both_and_only_defined_targets(self):
        r=self.call();self.assertTrue(r['written']);self.assertEqual(r['application_revision'],self.rev+1);self.assertEqual(r['wechat_version'],self.version+1)
        self.assertEqual(self.platform()['fields']['legal_name'],'SYNTHETIC CONFIRMED');self.assertEqual(self.platform()['fields']['address'],'SYNTHETIC ADDRESS')
        record=self.service._read(self.app['application'])
        self.assertEqual(record['profile'],{'subject_info':{'business_license_info':{'merchant_name':'SYNTHETIC CONFIRMED'}}})
        self.assertFalse(self.service.enabled);self.assertEqual(self.c.check_integrity()['integrity'],'PASS')
    def test_each_stale_version_and_replay_make_zero_writes(self):
        for change in ({'expected_application_revision':self.rev-1 or 99},{'expected_wechat_version':self.version-1}):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.call(**change)
            self.assertEqual(self.snapshot(),before)
        self.call();before=self.snapshot()
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.snapshot(),before)
    def test_explicit_versions_required_and_bool_rejected(self):
        for key in ('expected_application_revision','expected_wechat_version'):
            for value in (True,False,'1',1.0,None):
                before=self.snapshot()
                with self.assertRaises(ValueError):self.call(**{key:value})
                self.assertEqual(self.snapshot(),before)
        with self.assertRaises(TypeError):self.service.fill_confirmed_license_draft(self.fx.applicant['token'],self.fx.applicant['csrf'],self.app['application'],confirmed_fields={'company_name':'SYNTHETIC'})
    def test_existing_manual_values_on_either_side_are_preserved(self):
        self.fx.call('save',dict(application=self.app['application'],revision=self.rev,fields=dict(legal_name='MANUAL PLATFORM',address='MANUAL ADDRESS',store_name='SYNTHETIC STORE',contact='SYNTHETIC CONTACT'),entity_type='ENTERPRISE',category='GENERAL',delegated=False))
        self.rev=self.platform()['revision'];before=self.snapshot();r=self.call()
        self.assertFalse(r['written']);self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.service._read(self.app['application'])['profile']['subject_info']['business_license_info'],{})
    def test_manual_provider_name_never_masks_raw_manual_platform_field(self):
        record=self.service._read(self.app['application']);record['profile']['subject_info']['business_license_info']['merchant_name']='MANUAL PROVIDER'
        with self.c.tx():self.service._save(self.app['application'],self.fx.fx.uid1,record)
        r=self.call();self.assertEqual(r['applied'],['registered_address']);self.assertEqual(self.platform()['fields']['legal_name'],'')
        self.assertEqual(self.service._read(self.app['application'])['profile']['subject_info']['business_license_info']['merchant_name'],'MANUAL PROVIDER')
    def test_concurrent_commit_before_call_invalidates_snapshot(self):
        record=self.service._read(self.app['application']);record['version']+=1
        payload=self.c.encrypt(json.dumps(record).encode(),'wechat-applyment:'+self.app['application'])
        errors=[]
        def writer():
            db=sqlite3.connect(self.c.root/'center.sqlite',isolation_level=None)
            try:
                db.execute('BEGIN IMMEDIATE');db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(payload,self.app['application']));db.commit()
            except Exception as e:errors.append(e)
            finally:db.close()
        t=threading.Thread(target=writer);t.start();t.join(2);self.assertFalse(t.is_alive());self.assertFalse(errors)
        before=self.snapshot()
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.snapshot(),before)
    def test_original_begin_immediate_excludes_second_writer(self):
        blocked=[];original=self.onboarding._encode
        def encode(value,aad):
            def writer():
                db=sqlite3.connect(self.c.root/'center.sqlite',timeout=.01,isolation_level=None)
                try:db.execute('BEGIN IMMEDIATE');db.execute('UPDATE onboarding SET revision=revision+1 WHERE application=?',(self.app['application'],));db.commit()
                except sqlite3.OperationalError:blocked.append(True)
                finally:db.close()
            t=threading.Thread(target=writer);t.start();t.join(2);self.assertFalse(t.is_alive())
            return original(value,aad)
        with patch.object(self.onboarding,'_encode',side_effect=encode):r=self.call()
        self.assertTrue(r['written']);self.assertTrue(blocked)
    def test_first_second_metadata_or_audit_failure_rolls_back_both(self):
        for target,name in ((self.onboarding,'_encode'),(self.onboarding,'_meta'),(self.service,'_save'),(self.c,'audit')):
            before=self.snapshot()
            with patch.object(target,name,side_effect=RuntimeError('ISOLATED FAILURE')):
                with self.assertRaises(RuntimeError):self.call()
            self.assertEqual(self.snapshot(),before)
    def test_failure_after_real_first_second_write_or_audit_rolls_back_all(self):
        from scripts import community_onboarding_offline as workflow
        for target,name in ((workflow,'save_draft'),(self.onboarding,'_meta'),(self.service,'_save'),(self.c,'audit')):
            before=self.snapshot();original=getattr(target,name)
            def partial(*args,**kwargs):
                original(*args,**kwargs)
                raise RuntimeError('AFTER REAL WRITE')
            with patch.object(target,name,side_effect=partial):
                with self.assertRaises(RuntimeError):self.call()
            self.assertEqual(self.snapshot(),before)

    def test_session_application_provider_revocation_and_other_owner(self):
        for sql,params in [("UPDATE accounts SET verified=0 WHERE id=?",(self.fx.fx.uid1,)),
                           ("UPDATE links SET active=0 WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=?",(self.app['application'],)),
                           ("UPDATE links SET active=0 WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(self.app['application'],)),
                           ("UPDATE links SET user_id=? WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(self.fx.fx.uid2,self.app['application']))]:
            self.c.db.execute('SAVEPOINT synthetic_revoke');self.c.db.execute(sql,params);self.c.db.execute('RELEASE synthetic_revoke');before=self.snapshot()
            try:
                with self.assertRaises(PermissionError):self.call()
                self.assertEqual(self.snapshot(),before)
            finally:
                if 'verified=0' in sql:self.c.db.execute('UPDATE accounts SET verified=1 WHERE id=?',(self.fx.fx.uid1,))
                elif 'user_id=' in sql:self.c.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=?",(self.fx.fx.uid1,self.app['application']))
                else:self.c.db.execute(sql.replace('active=0','active=1'),params)
        with self.assertRaises(PermissionError):self.service.fill_confirmed_license_draft(self.fx.reviewer['token'],self.fx.reviewer['csrf'],self.app['application'],expected_application_revision=self.rev,expected_wechat_version=self.version,confirmed_fields={'company_name':'SYNTHETIC'})
    def test_both_edit_states_checked_under_transaction(self):
        for target in ('platform','provider'):
            if target=='platform':self.c.db.execute("UPDATE onboarding SET status='SUBMITTED' WHERE application=?",(self.app['application'],))
            else:
                self.c.db.execute("UPDATE onboarding SET status='DRAFT' WHERE application=?",(self.app['application'],));record=self.service._read(self.app['application']);record['state']='PENDING_INTERNAL_REVIEW'
                with self.c.tx():self.service._save(self.app['application'],self.fx.fx.uid1,record)
            before=self.snapshot()
            with self.assertRaises(PermissionError):self.call()
            self.assertEqual(self.snapshot(),before)
    def test_audit_time_revocation_and_midwrite_version_change_roll_back(self):
        audit=self.c.audit
        for action in ('revoke','version'):
            before=self.snapshot()
            def injected(*args):
                audit(*args)
                if action=='revoke':self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.fx.uid1,))
                else:self.c.db.execute('UPDATE onboarding SET revision=revision+1 WHERE application=?',(self.app['application'],))
            with patch.object(self.c,'audit',side_effect=injected):
                with self.assertRaises(PermissionError):self.call()
            self.assertEqual(self.snapshot(),before)
    def test_idcard_and_unknown_fields_not_writable_and_no_http_or_bridge_release(self):
        for fields in ({'id_name':'SYNTHETIC'},{'id_number':'SYNTHETIC'},{'company_name':False},{'registered_address':''}):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.call(confirmed_fields=fields)
            self.assertEqual(self.snapshot(),before)
        from pathlib import Path
        self.assertIn('OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED',Path('scripts/community_ocr_bridge.py').read_text())
        before=self.snapshot()
        with self.assertRaises((ValueError,PermissionError)):self.fx.call('fill_confirmed_license_draft',{})
        self.assertEqual(self.snapshot(),before)
