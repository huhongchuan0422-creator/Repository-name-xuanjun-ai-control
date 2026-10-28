"""Existing Center mini identity to original admission and workspace services."""
import unittest
import test_community_mini_center_identity as fixture
from scripts.community_center_operations import CenterOperations
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_mini_merchant import MiniMerchant

class SameMiniMerchant(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ExistingCenterComposition();self.fx.setUp()
        self.onboarding=MerchantOnboarding(self.fx.center,{self.fx.uid2:'project1'})
        self.grant={'user_id':self.fx.uid1,'project':'project1','project_roles':['OWNER'],'principal':self.fx.stage.merchant}
        self.operations=CenterOperations(self.fx.center,self.fx.stage.api,{'merchant':self.grant})
        self.service=MiniMerchant(self.fx.identity,self.onboarding,self.operations)
        self.token=self.fx.token()
    def tearDown(self):self.fx.tearDown()
    def call(self,operation,params=None,token=None):
        return self.service.dispatch(token or self.token,'shop1',{'operation':operation,'params':params or {}})
    def draft(self):
        return self.call('onboarding',{'operation':'save','params':dict(application=None,revision=0,entity_type='ENTERPRISE',category='GENERAL',delegated=False,sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'],fields=dict(legal_name='Fixture',store_name='Fixture Shop',address='Fixture Address',contact='Fixture'))})
    def test_original_admission_without_creating_merchant_grant(self):
        app=self.draft()
        self.assertEqual(app['status'],'DRAFT');self.assertFalse(app['payment_enabled'])
        self.assertEqual(self.call('onboarding',{'operation':'mine','params':{}})['applications'][0]['application'],app['application'])
        self.assertEqual(self.operations.grants.keys(),{'merchant'})
        self.assertNotIn('storefront_photo',app['required_materials'])
    def test_live_grant_required_even_for_original_customer(self):
        other=self.fx.token('othercode','openid2')
        self.assertEqual(self.call('workspaces',token=other),{'workspaces':[],'permissions':{}})
        with self.assertRaises(PermissionError):self.call('read',dict(workspace='merchant',operation='community.orders',params={}),other)
        with self.assertRaises(PermissionError):self.call('onboarding',{'operation':'read','params':{'application':self.draft()['application']}},other)
    def test_role_write_and_cross_scene_denials(self):
        self.assertEqual(self.call('read',dict(workspace='merchant',operation='community.orders',params={}))['orders'],[])
        for operation in ('community.profile','community.refund_record','community.ad_review'):
            with self.assertRaises(PermissionError):self.call('read',dict(workspace='merchant',operation=operation,params={}))
        for operation in ('review','open_workbench','wechat_execute','wechat_query'):
            with self.assertRaises(PermissionError):self.call('onboarding',dict(operation=operation,params={}))
        with self.assertRaises(PermissionError):self.service.dispatch(self.token,'unknown',dict(operation='workspaces',params={}))
        self.operations.grants['merchant']['scope']={**self.operations.grants['merchant']['scope'],'store_id':'another'}
        with self.assertRaises(PermissionError):self.call('read',dict(workspace='merchant',operation='community.summary',params={}))
    def test_revocation_and_legacy_session_fail_closed(self):
        self.fx.center.logout(self.token)
        with self.assertRaises(PermissionError):self.call('workspaces')
        token=self.fx.token('newcode');c=self.fx.center
        row=c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=?",(c.idx('wechat-session:'+token),)).fetchone()
        import json
        from scripts.pr122_customer_core import canonical
        meta=json.loads(c.decrypt(row['payload'],'wechat-mini-session'));meta.pop('merchant_csrf')
        c.db.execute("UPDATE links SET payload=? WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=?",(c.encrypt(canonical(meta),'wechat-mini-session'),row['subject_idx']))
        with self.assertRaisesRegex(PermissionError,'RELOGIN'):self.call('workspaces',token=token)
    def test_native_controllers_use_actual_http_and_same_original_record(self):
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        from scripts.community_wechat_applyment import WechatApplyment
        from scripts.community_mini_http import serve
        from pathlib import Path
        import subprocess,os,select,json
        reader=PartnerOrderReader.__new__(PartnerOrderReader)
        self.onboarding.wechat_applyment=WechatApplyment(self.onboarding,reader)
        server=serve(self.fx.gateway,onboarding=self.onboarding,operations=self.operations)
        server.timeout=.1
        log=open('/tmp/community-native-http-controller.log','w+')
        child=subprocess.Popen(['node','tests/community_mini_merchant_http.cjs'],cwd=Path(__file__).resolve().parents[1],
            env=dict(os.environ,COMMUNITY_TEST_ORIGIN='http://127.0.0.1:'+str(server.server_port)),stdout=log,stderr=log)
        import time
        deadline=time.monotonic()+15
        try:
            while child.poll() is None and time.monotonic()<deadline:server.handle_request()
            if child.poll() is None:child.kill();child.wait();self.fail('NATIVE_CONTROLLER_TIMEOUT')
            log.seek(0);output=log.read();self.assertEqual(child.returncode,0,output)
            result=json.loads(output);app=self.onboarding._load(result['application'],self.fx.uid1)[2]
            self.assertEqual(app['fields']['legal_name'],'HTTP Native Company')
            self.assertEqual(app['fields']['contact'],'13800000000')
            self.assertFalse(result['payment_enabled'])
        finally:
            if child.poll() is None:child.kill();child.wait()
            log.close();server.server_close()

    def test_http_bearer_session_and_body_guard(self):
        from scripts.community_mini_http import serve
        server=serve(self.fx.gateway,onboarding=self.onboarding,operations=self.operations)
        import threading,urllib.request,urllib.error,json
        
        body=json.dumps(dict(operation='onboarding',params=dict(operation='mine',params={}))).encode()
        req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',data=body,headers={'Content-Type':'application/json','X-Community-Session':self.token,'X-Community-Scene':'shop1'})
        def client():
            with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(1) as pool:
                result=pool.submit(client);server.handle_request()
                self.assertEqual(result.result()['result'],{'applications':[],'next_cursor':None})
        finally:server.server_close()


class SharedProfileAndSigning(unittest.TestCase):
    def test_shared_mapping_uses_this_profile_and_never_bank_or_other_application(self):
        from scripts.community_merchant_onboarding import shared_application_fields
        original=dict(legal_name='Old',contact='Old',store_name='Store',address='Address')
        result=shared_application_fields(dict(subject_info=dict(business_license_info=dict(merchant_name='Shared')),contact_info=dict(mobile_phone='13800000000'),bank_account_info=dict(account_number='not-copied')),original)
        self.assertEqual(result,dict(original,legal_name='Shared',contact='13800000000'))
        self.assertEqual(original['legal_name'],'Old')
        with self.assertRaises(ValueError):shared_application_fields({'contact_info':{'mobile_phone':[]}},original)
    def test_signing_link_fixed_official_origin_only(self):
        from scripts.community_wechat_applyment import official_signing_url
        url='https://pay.weixin.qq.com/public/apply4ec_sign/s?applymentId=123&sign=fixture'
        self.assertEqual(official_signing_url(url),url)
        for value in ('javascript:alert(1)',url.replace('pay.weixin.qq.com','pay.weixin.qq.com.evil.invalid'),url.replace('https:','http:'),url+'#fragment',url+'\n'):
            with self.assertRaises(ValueError):official_signing_url(value)

if __name__=='__main__':unittest.main()

class CashierMaterialJourney(unittest.TestCase):
    call=SameMiniMerchant.call
    draft=SameMiniMerchant.draft
    tearDown=SameMiniMerchant.tearDown
    # Reuse original identity, Center, tenant/scene and encrypted onboarding.
    # Synthetic admitted media records below are not provider upload evidence.
    def setUp(self):
        SameMiniMerchant.setUp(self)
        from scripts.community_wechat_applyment import WechatApplyment
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        self.fx.center.scanner=lambda raw:True
        self.onboarding.wechat_applyment=WechatApplyment(self.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
        self.app=self.draft()
    def op(self,name,**params):
        return self.call('onboarding',dict(operation=name,params=params))
    def upload_cashier(self,raw=b'\x89PNG\r\n\x1a\nsynthetic cashier'):
        import base64
        self.app=self.op('upload',application=self.app['application'],revision=self.app['revision'],kind='cashier_photo',content_base64=base64.b64encode(raw).decode(),expires_at=None)
        return self.app
    def draft_profile(self,values):
        return self.op('wechat_save',application=self.app['application'],expected_version=0,profile={'addition_info':{'business_addition_pics':values}})
    def admit_media(self,media):
        import hashlib
        from scripts.pr122_customer_core import canonical
        c=self.fx.center;application=self.app['application']
        _,meta,_=self.onboarding._load(application,self.fx.uid1)
        sha=meta['materials']['cashier_photo']['sha256'];key=hashlib.sha256((application+media).encode()).hexdigest()
        with c.tx():c.db.execute("INSERT INTO links VALUES('COMMUNITY_WECHAT_MEDIA',?,?,?,?,1)",(key,self.fx.uid1,application,c.encrypt(canonical(dict(kind='cashier_photo',sha256=sha,media_id=media)),'wechat-media:'+key)))
    def test_cashier_optional_upload_replace_delete_read_history_and_revoked_media(self):
        self.assertNotIn('cashier_photo',self.app['required_materials'])
        self.assertIn('cashier_photo',self.op('catalog')['optional_materials'])
        self.upload_cashier();self.draft_profile(['legacy-other'])
        self.admit_media('cashier-one')
        linked=self.op('wechat_cashier_link',application=self.app['application'],expected_version=1,media_id='cashier-one')
        self.assertEqual(linked['profile']['addition_info']['business_addition_pics'],['legacy-other','cashier-one'])
        self.upload_cashier(b'\x89PNG\r\n\x1a\nreplacement')
        record=self.op('wechat_read',application=self.app['application'])
        self.assertEqual(record['profile']['addition_info']['business_addition_pics'],['legacy-other'])
        self.assertNotIn('cashier_media_id',record)
        with self.assertRaisesRegex(PermissionError,'CURRENT_CASHIER_MEDIA_REQUIRED'):
            self.op('wechat_cashier_link',application=self.app['application'],expected_version=record['version'],media_id='cashier-one')
        self.admit_media('cashier-two')
        linked=self.op('wechat_cashier_link',application=self.app['application'],expected_version=record['version'],media_id='cashier-two')
        before=self.fx.center.db.execute('SELECT count(*) FROM objects').fetchone()[0]
        self.app=self.op('remove_material',application=self.app['application'],revision=self.app['revision'],kind='cashier_photo',expected_wechat_version=linked['version'])
        self.assertNotIn('cashier_photo',self.op('read',application=self.app['application'])['materials'])
        record=self.op('wechat_read',application=self.app['application'])
        self.assertEqual(record['profile']['addition_info']['business_addition_pics'],['legacy-other'])
        self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM objects').fetchone()[0],before)
        history=self.op('history',application=self.app['application'],after_revision=0)
        self.assertIn('REMOVE_MATERIAL',str(history))
    def test_cashier_full_array_unknown_binding_stale_versions_and_cross_tenant_denied(self):
        self.upload_cashier();record=self.draft_profile(['other-'+str(i) for i in range(5)])
        self.admit_media('cashier')
        with self.assertRaisesRegex(ValueError,'BUSINESS_ADDITION_PICS_LIMIT'):
            self.op('wechat_cashier_link',application=self.app['application'],expected_version=1,media_id='cashier')
        self.assertEqual(self.op('wechat_read',application=self.app['application']),record)
        for revision,version in [(self.app['revision']-1,1),(self.app['revision'],0)]:
            with self.assertRaises(ValueError):self.op('remove_material',application=self.app['application'],revision=revision,kind='cashier_photo',expected_wechat_version=version)
        other=self.fx.token('cashier-other','openid2')
        for operation,params in [('read',dict(application=self.app['application'])),('remove_material',dict(application=self.app['application'],revision=self.app['revision'],kind='cashier_photo',expected_wechat_version=1)),('wechat_cashier_link',dict(application=self.app['application'],expected_version=1,media_id='cashier'))]:
            with self.assertRaises(PermissionError):self.call('onboarding',dict(operation=operation,params=params),other)
        with self.assertRaises(PermissionError):self.service.dispatch(self.token,'unknown',dict(operation='onboarding',params=dict(operation='read',params=dict(application=self.app['application']))))
        # Reject a legacy cashier reference without a trusted slot binding.
        service=self.onboarding.wechat_applyment
        with self.fx.center.tx():service._save(self.app['application'],self.fx.uid1,dict(record,profile={'addition_info':{'business_addition_pics':['cashier','other']}}))
        with self.assertRaisesRegex(ValueError,'CASHIER_MEDIA_BINDING_UNKNOWN'):self.upload_cashier()
        self.assertIn('cashier_photo',self.op('read',application=self.app['application'])['materials'])
    def test_cashier_generic_save_cannot_remove_managed_slot_or_exceed_five(self):
        self.upload_cashier();self.draft_profile(['other']);self.admit_media('cashier')
        record=self.op('wechat_cashier_link',application=self.app['application'],expected_version=1,media_id='cashier')
        for values in [['other'],['other','cashier']+['extra'+str(i) for i in range(4)]]:
            with self.assertRaises(ValueError):self.op('wechat_save',application=self.app['application'],expected_version=2,profile={'addition_info':{'business_addition_pics':values}})
        self.assertEqual(self.op('wechat_read',application=self.app['application']),record)
        # Review state blocks both replacement and deletion, preserving objects.
        with self.fx.center.tx():self.onboarding.wechat_applyment._save(self.app['application'],self.fx.uid1,dict(record,state='PENDING_INTERNAL_REVIEW'))
        with self.assertRaisesRegex(PermissionError,'CASHIER_DRAFT_REQUIRED'):self.upload_cashier()
        with self.assertRaisesRegex(PermissionError,'CASHIER_DRAFT_REQUIRED'):self.op('remove_material',application=self.app['application'],revision=self.app['revision'],kind='cashier_photo',expected_wechat_version=2)
    def test_cashier_actual_http_upload_replace_remove_and_read(self):
        import base64,json,threading,urllib.request
        from scripts.community_mini_http import serve
        server=serve(self.fx.gateway,onboarding=self.onboarding,operations=self.operations)
        def http(operation,params):
            body=json.dumps(dict(operation='onboarding',params=dict(operation=operation,params=params))).encode()
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',data=body,headers={'Content-Type':'application/json','X-Community-Session':self.token,'X-Community-Scene':'shop1'})
            from concurrent.futures import ThreadPoolExecutor
            def client():
                with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)['result']
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(client);server.handle_request();return future.result()
        try:
            application=self.app['application']
            for suffix in ('first','replacement'):
                self.app=http('upload',dict(application=application,revision=self.app['revision'],kind='cashier_photo',content_base64=base64.b64encode(('\x89PNG\r\n\x1a\n'+suffix).encode('latin1')).decode(),expires_at=None))
                self.assertTrue(http('read',dict(application=application))['materials']['cashier_photo']['uploaded'])
            self.app=http('remove_material',dict(application=application,revision=self.app['revision'],kind='cashier_photo',expected_wechat_version=0))
            self.assertNotIn('cashier_photo',http('read',dict(application=application))['materials'])
        finally:server.server_close()
    def test_cashier_replace_full_shared_array_preserves_four_other_entries(self):
        self.upload_cashier();others=['other-'+str(i) for i in range(4)];self.draft_profile(others)
        self.admit_media('cashier-a')
        self.op('wechat_cashier_link',application=self.app['application'],expected_version=1,media_id='cashier-a')
        self.admit_media('cashier-b')
        record=self.op('wechat_cashier_link',application=self.app['application'],expected_version=2,media_id='cashier-b')
        self.assertEqual(record['profile']['addition_info']['business_addition_pics'],others+['cashier-b'])
        self.assertNotIn('cashier-a',record['profile']['addition_info']['business_addition_pics'])
    def test_cashier_failed_replacement_rolls_back_managed_unlink(self):
        self.upload_cashier();self.draft_profile(['other']);self.admit_media('cashier')
        record=self.op('wechat_cashier_link',application=self.app['application'],expected_version=1,media_id='cashier')
        self.fx.center.scanner=lambda raw:False
        with self.assertRaisesRegex(PermissionError,'SCAN_NOT_CLEAN'):self.upload_cashier(b'\x89PNG\r\n\x1a\nrejected replacement')
        self.assertEqual(self.op('wechat_read',application=self.app['application']),record)
        self.assertEqual(self.op('read',application=self.app['application'])['revision'],self.app['revision'])
        self.assertEqual(self.fx.center.check_integrity()['integrity'],'PASS')

class OcrSourceBoundary(unittest.TestCase):
    setUp=SameMiniMerchant.setUp
    tearDown=SameMiniMerchant.tearDown
    call=SameMiniMerchant.call
    draft=SameMiniMerchant.draft
    def material(self,app=None,kind='business_license',raw=b'\x89PNG\r\n\x1a\nSynthetic document, not a real credential'):
        import base64
        self.fx.center.scanner=lambda data:True
        app=app or self.draft()
        return self.call('onboarding',{'operation':'upload','params':{
            'application':app['application'],'revision':app['revision'],'kind':kind,
            'content_base64':base64.b64encode(raw).decode(),'expires_at':None}})
    def test_original_identity_application_and_encrypted_bytes_supply_source(self):
        import hashlib
        app=self.material()
        source=self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
        self.assertEqual(source['subject'],self.fx.uid1)
        self.assertEqual(source['tenant_id'],self.fx.stage.customer.tenant_id)
        self.assertEqual(source['project'],'project1')
        self.assertEqual(source['document_sha256'],hashlib.sha256(source['data']).hexdigest())
        self.assertEqual(source['document_type'],'business_license')
        self.assertFalse(self.fx.center.db.in_transaction)
    def test_other_owner_and_tenant_scope_cannot_reuse_application(self):
        app=self.material()
        other=self.fx.token('othercode','openid2')
        with self.assertRaises(PermissionError):
            self.service.ocr_source(other,'shop1',app['application'],'business_license')
        principal=self.fx.stage.customer
        original=self.fx.identity.runtime.bindings[principal]
        self.fx.identity.runtime.bindings[principal]={**original,'tenant_id':'other_tenant'}
        with self.assertRaisesRegex(PermissionError,'ORIGIN_UNVERIFIED'):
            self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
    def test_object_sha_mismatch_and_replacement_do_not_reuse_source(self):
        app=self.material()
        before=self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
        app=self.material(app,raw=b'\x89PNG\r\n\x1a\nSynthetic replacement')
        after=self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
        self.assertNotEqual(before['attachment_id'],after['attachment_id'])
        self.assertNotEqual(before['document_sha256'],after['document_sha256'])
        self.fx.center.db.execute('UPDATE objects SET sha=? WHERE id=?',('0'*64,after['attachment_id']))
        with self.assertRaisesRegex(PermissionError,'ATTACHMENT_INTEGRITY'):
            self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
    def test_revoked_session_and_provider_binding_fail(self):
        app=self.material()
        self.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(self.fx.uid1,))
        with self.assertRaises(PermissionError):
            self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
        self.fx.center.logout(self.token)
        with self.assertRaises(PermissionError):
            self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
    def test_legacy_origin_and_client_injected_origin_fail_closed(self):
        app=self.material()
        _,meta,_=self.onboarding._load(app['application'],self.fx.uid1)
        meta.pop('ocr_origin')
        with self.fx.center.tx():self.onboarding._meta(app['application'],self.fx.uid1,meta)
        with self.assertRaisesRegex(PermissionError,'ORIGIN_UNVERIFIED'):
            self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
        with self.assertRaises(ValueError):
            self.call('onboarding',{'operation':'save','params':{'ocr_origin':{},'application':None}})
    def test_scene_photos_and_non_image_documents_never_enter_ocr(self):
        app=self.material()
        for kind in ('storefront_photo','interior_photo','cashier_photo'):
            with self.subTest(kind=kind),self.assertRaisesRegex(PermissionError,'DOCUMENT_NOT_SUPPORTED'):
                self.service.ocr_source(self.token,'shop1',app['application'],kind)
        app=self.material(app,raw=b'%PDF-Synthetic existing supported upload')
        with self.assertRaisesRegex(PermissionError,'IMAGE_REQUIRED'):
            self.service.ocr_source(self.token,'shop1',app['application'],'business_license')

    def test_attachment_from_another_application_is_denied(self):
        first=self.material();second=self.material()
        _,second_meta,_=self.onboarding._load(second['application'],self.fx.uid1)
        _,first_meta,_=self.onboarding._load(first['application'],self.fx.uid1)
        first_meta['materials']['business_license']=second_meta['materials']['business_license']
        with self.fx.center.tx():self.onboarding._meta(first['application'],self.fx.uid1,first_meta)
        with self.assertRaisesRegex(PermissionError,'ATTACHMENT_INTEGRITY'):
            self.service.ocr_source(self.token,'shop1',first['application'],'business_license')

class OcrSourceReadRace(unittest.TestCase):
    setUp=SameMiniMerchant.setUp
    tearDown=SameMiniMerchant.tearDown
    call=SameMiniMerchant.call
    draft=SameMiniMerchant.draft
    material=OcrSourceBoundary.material
    def during_decrypt(self,app,change,kind='business_license'):
        from unittest.mock import patch
        c=self.fx.center
        _,meta,_=self.onboarding._load(app['application'],self.fx.uid1)
        oid=meta['materials'][kind]['object_id']
        original=c.decrypt
        invoked=[]
        def decrypt(raw,aad):
            result=original(raw,aad)
            if aad=='object:'+app['application']+':'+oid and not invoked:
                invoked.append(True)
                change(oid)
            return result
        with patch.object(c,'decrypt',side_effect=decrypt):
            with self.assertRaises(PermissionError):
                self.service.ocr_source(self.token,'shop1',app['application'],kind)
        self.assertEqual(invoked,[True])
    def test_current_object_fields_cannot_change_during_read(self):
        changes={'id':'o_other','project':'ma_other','scan':'BLOCKED','mime':'image/jpeg',
                 'size':999,'sha':'0'*64,'version':'v_other','key_id':'other-key'}
        for column,value in changes.items():
            with self.subTest(column=column):
                app=self.material()
                self.during_decrypt(app,lambda oid:self.fx.center.db.execute(
                    'UPDATE objects SET '+column+'=? WHERE id=?',(value,oid)))
    def test_object_deletion_during_read_is_denied(self):
        app=self.material()
        self.during_decrypt(app,lambda oid:self.fx.center.db.execute('DELETE FROM objects WHERE id=?',(oid,)))
    def test_clock_crossing_material_expiration_during_read_is_denied(self):
        app=self.material()
        _,meta,_=self.onboarding._load(app['application'],self.fx.uid1)
        meta['materials']['business_license']['expires_at']=self.fx.center.now()+1
        with self.fx.center.tx():self.onboarding._meta(app['application'],self.fx.uid1,meta)
        def advance(oid):self.fx.stage.now+=2
        self.during_decrypt(app,advance)
    def test_session_and_provider_revocation_during_read_are_denied(self):
        app=self.material()
        self.during_decrypt(app,lambda oid:self.fx.center.logout(self.token))
    def test_provider_binding_revocation_during_read_is_denied(self):
        app=self.material()
        self.during_decrypt(app,lambda oid:self.fx.center.db.execute(
            "UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(self.fx.uid1,)))
    def test_application_revision_change_during_read_is_denied(self):
        app=self.material()
        self.during_decrypt(app,lambda oid:self.fx.center.db.execute(
            'UPDATE onboarding SET revision=revision+1 WHERE application=?',(app['application'],)))
    def test_application_revocation_during_read_is_denied(self):
        app=self.material()
        self.during_decrypt(app,lambda oid:self.fx.center.db.execute(
            "UPDATE links SET active=0 WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=?",(app['application'],)))
    def test_application_material_replacement_during_read_is_denied(self):
        app=self.material()
        def replace(oid):
            _,meta,_=self.onboarding._load(app['application'],self.fx.uid1)
            meta['materials']['business_license']['object_id']='o_replaced'
            with self.fx.center.tx():self.onboarding._meta(app['application'],self.fx.uid1,meta)
        self.during_decrypt(app,replace)
    def test_identity_front_returns_verified_original_bytes(self):
        import hashlib
        app=self.material(kind='identity_front')
        result=self.service.ocr_source(self.token,'shop1',app['application'],'identity_front')
        self.assertEqual(result['document_type'],'id_front')
        self.assertEqual(result['document_sha256'],hashlib.sha256(result['data']).hexdigest())
        self.assertEqual(result['mime'],'image/png')


class ApplicantWithoutStore(unittest.TestCase):
    setUp=SameMiniMerchant.setUp
    tearDown=SameMiniMerchant.tearDown
    def applicant(self,op,params=None,token=None,scene=''):
        return self.service.dispatch(token or self.token,scene,dict(operation='onboarding',params=dict(operation=op,params=params or {})))
    def create(self):
        return self.applicant('save',dict(application=None,revision=0,entity_type='ENTERPRISE',category='GENERAL',delegated=False,sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'],fields=dict(legal_name='Applicant',store_name='New Store',address='Address',contact='13800000000')))
    def test_existing_verified_applicant_saves_same_draft_without_store_or_new_role(self):
        before=dict(self.operations.grants);app=self.create();owner,meta,_=self.onboarding._load(app['application'],self.fx.uid1)
        self.assertEqual(owner,self.fx.uid1);self.assertNotIn('ocr_origin',meta);self.assertEqual(self.operations.grants,before)
        self.assertEqual(self.applicant('mine')['applications'][0]['application'],app['application'])
        self.assertEqual(self.applicant('read',dict(application=app['application']))['status'],'DRAFT')
    def test_unknown_nonempty_scene_and_every_store_operation_still_denied(self):
        for scene in ('../bad','unknown',None):
            with self.subTest(scene=scene),self.assertRaises(PermissionError):self.applicant('mine',scene=scene)
        for op in ('workspaces','read','write','collection_code','ocr'):
            with self.subTest(op=op),self.assertRaises(PermissionError):self.service.dispatch(self.token,'',dict(operation=op,params={}))
        for op in ('review','review_list','open_workbench','wechat_execute','wechat_query'):
            with self.subTest(op=op),self.assertRaises(PermissionError):self.applicant(op)
    def test_no_web_session_and_live_provider_link_csrf_epoch_guards(self):
        with self.assertRaises(PermissionError):self.applicant('mine',token=self.fx.web1)
        c=self.fx.center;row=c.db.execute("SELECT subject_idx,project,payload FROM links WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=?",(c.idx('wechat-session:'+self.token),)).fetchone()
        import json
        from scripts.pr122_customer_core import canonical
        meta=json.loads(c.decrypt(row['payload'],'wechat-mini-session'));meta.pop('merchant_csrf')
        c.db.execute("UPDATE links SET payload=? WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=?",(c.encrypt(canonical(meta),'wechat-mini-session'),row['subject_idx']))
        with self.assertRaisesRegex(PermissionError,'RELOGIN'):self.applicant('mine')
        c.db.execute("UPDATE links SET payload=? WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=?",(row['payload'],row['subject_idx']))
        c.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(self.fx.uid1,))
        with self.assertRaisesRegex(PermissionError,'REVOKED'):self.applicant('mine')
        c.db.execute("UPDATE links SET active=1 WHERE channel='WECHAT_MINI' AND user_id=?",(self.fx.uid1,));c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.applicant('mine')
    def test_cross_owner_read_save_upload_and_wechat_read_still_rejected(self):
        from scripts.community_wechat_applyment import WechatApplyment
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        self.onboarding.wechat_applyment=WechatApplyment(self.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
        app=self.create();other=self.fx.token('another-login','openid2')
        cases=[('read',dict(application=app['application'])),('wechat_read',dict(application=app['application'])),
          ('save',dict(application=app['application'],revision=app['revision'],entity_type='ENTERPRISE',category='GENERAL',delegated=False,fields=app['fields'])),
          ('upload',dict(application=app['application'],revision=app['revision'],kind='business_license',content_base64='iVBORw0KGgpmaXh0dXJl',expires_at=None))]
        for op,params in cases:
            with self.subTest(op=op),self.assertRaises(PermissionError):self.applicant(op,params,token=other)
        self.assertEqual(self.applicant('mine',token=other)['applications'],[])
    def test_original_http_authenticates_before_body_and_supports_scene_less_owner(self):
        from scripts.community_mini_http import serve
        import urllib.request,json
        from concurrent.futures import ThreadPoolExecutor
        server=serve(self.fx.gateway,onboarding=self.onboarding,operations=self.operations)
        body=json.dumps(dict(operation='onboarding',params=dict(operation='mine',params={}))).encode()
        req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',data=body,headers={'Content-Type':'application/json','X-Community-Session':self.token})
        def call():
            with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
        try:
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(call);server.handle_request();self.assertEqual(future.result()['result']['applications'],[])
        finally:server.server_close()

    def test_real_http_native_first_registration_upload_before_fields_submit_and_read(self):
        from scripts.pr122_customer_core import canonical
        from scripts.community_wechat_applyment import WechatApplyment
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        from scripts.community_mini_http import serve
        from pathlib import Path
        import subprocess,os,json,time
        c=self.fx.center
        realm=dict(kind='COMMUNITY_PLATFORM_REALM',title='Synthetic platform',requirements=[],source='OWNER_APPROVED_FIRST_INSTALL',authority_ref='test_realm')
        c.db.execute("UPDATE projects SET authority_ref='test_realm',payload=? WHERE id='project1'",(c.encrypt(canonical(realm),'project:project1'),))
        self.fx.identity.configure_registration(['shop1'])
        self.fx.provider.exchange.return_value=dict(appid=self.fx.identity.appid,openid='new_applicant_without_store')
        c.scanner=lambda raw:True  # isolated scanner substitute, not production/OCR acceptance
        self.onboarding.wechat_applyment=WechatApplyment(self.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
        server=serve(self.fx.gateway,onboarding=self.onboarding,operations=self.operations);server.timeout=.1
        import tempfile
        with tempfile.TemporaryFile(mode='w+') as log:
            child=subprocess.Popen(['node','tests/community_mini_merchant_http.cjs'],cwd=Path(__file__).resolve().parents[1],env=dict(os.environ,COMMUNITY_TEST_ORIGIN='http://127.0.0.1:'+str(server.server_port),COMMUNITY_TEST_SCENELESS='true'),stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+25
                while child.poll() is None and time.monotonic()<deadline:server.handle_request()
                if child.poll() is None:child.kill();child.wait();self.fail('NATIVE_APPLICANT_HTTP_TIMEOUT')
                log.seek(0);output=log.read();self.assertEqual(child.returncode,0,output);result=json.loads(output)
                row=c.db.execute("SELECT user_id FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=?",(result['application'],)).fetchone();uid=row[0]
                self.assertNotIn(uid,(self.fx.uid1,self.fx.uid2));self.assertEqual(c.db.execute('SELECT count(*) FROM members WHERE user_id=?',(uid,)).fetchone()[0],0)
                _,meta,app=self.onboarding._load(result['application'],uid);self.assertEqual(app['status'],'SUBMITTED');self.assertNotIn('ocr_origin',meta)
                self.assertFalse(any(g['user_id']==uid for g in self.operations.grants.values()))
                self.assertTrue(result['upload_before_fields']);self.assertTrue(result['four_steps']);self.assertIsNone(result['scene'])
            finally:
                if child.poll() is None:child.kill();child.wait()
                server.server_close()

    def test_no_scene_session_expiry_logout_maintenance_and_origin_guards(self):
        c=self.fx.center;app=self.create()
        with self.assertRaisesRegex(PermissionError,'ORIGIN_UNVERIFIED'):
            self.service.ocr_source(self.token,'shop1',app['application'],'business_license')
        c.db.execute("UPDATE settings SET v='1' WHERE k='maintenance'")
        with self.assertRaises(PermissionError):self.applicant('mine')
        c.db.execute("UPDATE settings SET v='0' WHERE k='maintenance'")
        c.logout(self.token)
        with self.assertRaises(PermissionError):self.applicant('mine')
        self.token=self.fx.token('expiry-case');self.fx.stage.now+=3601
        with self.assertRaises(PermissionError):self.applicant('mine')
