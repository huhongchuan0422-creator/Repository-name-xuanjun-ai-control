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
