"""Existing STORE contract only. Offline HTTP; provider transport must never run."""
import concurrent.futures
import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
import test_community_merchant_onboarding as fixture
from test_community_applyment_conditions import profile
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_mini_http import serve

ROOT=Path(__file__).resolve().parents[1]

class StoreScenes(unittest.TestCase):
    def test_dom_roundtrip_media_arrays_scene_and_identity_races(self):
        subprocess.run(['node',str(ROOT/'tests/community_onboarding_store_dom.cjs'),str(ROOT/'demos/community-stage/onboarding.js')],check=True,capture_output=True,text=True)

    def test_original_http_draft_validation_independent_review_and_closed_gate(self):
        f=fixture.MerchantAdmissionJourney();f.setUp()
        server=None
        try:
            service=WechatApplyment(f.service,PartnerOrderReader.__new__(PartnerOrderReader),submission_enabled=False)
            f.service.wechat_applyment=service
            app=f.draft()
            app=f.upload(app,'storefront_photo');app=f.upload(app,'interior_photo')
            server=serve(f.fx.gateway,onboarding=f.service)
            def call(op,params,review=False,csrf=True):
                who=f.reviewer if review else f.applicant
                def send():
                    req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/merchant/onboarding',data=json.dumps(dict(operation=op,params=params)).encode(),headers={'Content-Type':'application/json','Cookie':'__Host-xj_customer='+who['token'],'X-CSRF-Token':who['csrf'] if csrf else ''})
                    try:
                        with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
                    except urllib.error.HTTPError as error:return error.code,json.load(error)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(send);server.handle_request();return future.result()
            p=profile();p['business_info']['sales_info']={'sales_scenes_type':['SALES_SCENES_STORE'],'biz_store_info':dict(biz_store_name='Synthetic Store',biz_address_code='fixture-verified-code',biz_store_address='Synthetic Address',store_entrance_pic=['fixture-front'],indoor_pic=['fixture-interior'])}
            with patch('scripts.community_wechat_applyment.request',side_effect=AssertionError('Provider forbidden')) as provider:
                code,saved=call('wechat_save',dict(application=app['application'],expected_version=0,profile=p));self.assertEqual(code,200)
                code,read=call('wechat_read',dict(application=app['application']));self.assertEqual(code,200);self.assertEqual(read['result']['profile'],p)
                code,_=call('wechat_submit_review',dict(application=app['application'],expected_version=1));self.assertEqual(code,200)
                code,_=call('wechat_review',dict(application=app['application'],expected_version=2,decision='INTERNAL_APPROVED',opinion='Synthetic review'),True);self.assertEqual(code,200)
                code,_=call('wechat_execute',dict(application=app['application'],expected_version=3),True);self.assertEqual(code,403)
                code,_=call('wechat_media',dict(application=app['application'],kind='storefront_photo'));self.assertEqual(code,403)
                code,_=call('wechat_read',dict(application=app['application']),csrf=False);self.assertEqual(code,403)
                f.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(f.fx.uid2,))
                code,_=call('wechat_review_read',dict(application=app['application']),True);self.assertEqual(code,403)
                provider.assert_not_called()
            # Existing contract remains authoritative. Neither guessed catalogs nor new channels.
            for change in ('missing_address','missing_front','empty_inside','unknown_scene','mini_without_appid'):
                invalid=copy.deepcopy(p);sales=invalid['business_info']['sales_info']
                if change=='missing_address':del sales['biz_store_info']['biz_address_code']
                elif change=='missing_front':del sales['biz_store_info']['store_entrance_pic']
                elif change=='empty_inside':sales['biz_store_info']['indoor_pic']=[]
                elif change=='unknown_scene':sales['sales_scenes_type']=['SALES_SCENES_UNREGISTERED']
                else:sales['sales_scenes_type'].append('SALES_SCENES_MINI_PROGRAM')
                with self.assertRaises(ValueError,msg=change):service._validate(invalid,'ENTERPRISE')
            service._validate(p,'ENTERPRISE')
            with self.assertRaises(PermissionError):service._validate_media(p,app['application'],{'materials':{}})
        finally:
            if server:server.server_close()
            f.tearDown()

if __name__=='__main__':unittest.main()
