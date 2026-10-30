"""Synthetic identity/Owner only; actual original host, admission, CAS and bridge."""
import unittest
from unittest.mock import Mock,patch
from email.message import Message
import test_community_reviewer_maintenance as admission_fixture
from scripts import community_reviewer_maintenance as maintenance
from scripts.community_reviewer_web_bridge import ReviewerWebBridge
from scripts.community_web_session import WebSession

class Composition(unittest.TestCase):
    def setUp(self):
        self.fx=admission_fixture.Maintenance();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
    def test_admission_cas_wechat_bridge_original_review_and_ocr_gate(self):
        f=self.fx
        with patch.object(maintenance,'OWNER_CONFIRMATION_PIN',f.pin):
            self.assertEqual(f.call()['config_status'],'CONFIG_APPLIED')
        with f.fx.open() as host:
            app=host.application
            app.gateway.provider.exchange=Mock(return_value=dict(appid=f.fx.wechat['appid'],openid='maintenance_fixture'))
            mini=app.gateway.login({'code':'composition_fixture'})['session_token']
            self.assertEqual(host.center.session(mini),f.uid)
            web=WebSession(host.center,onboarding=app.onboarding)
            bridge=ReviewerWebBridge(app.identity,web,'shop1','https://uk.wenwenwenyiyiyi.work')
            start,binding=bridge.begin(origin=bridge.origin,source='127.0.0.1')
            bridge.confirm(start['challenge'],mini,verification=start['verification'],action='CONFIRM_THIS_BROWSER')
            result,cookie=bridge.browser(start['challenge'],action='FINISH',browser=binding.split(';')[0].split('=',1)[1],csrf=start['csrf'],origin=bridge.origin)
            headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=result['csrf']
            check,_=web.dispatch('/community/session/check',headers,{},'127.0.0.1')
            self.assertTrue(check['reviewer']);self.assertEqual(check['user_id'],f.uid)
            app.onboarding._reviewer(f.uid)
            host.preflight_applicant_ocr()
            self.assertIsNone(host.ocr) # Preflight does not pretend a real provider/store exists.
            self.assertEqual(host.center.check_integrity()['integrity'],'PASS')
        self.assertIsNone(maintenance.OWNER_CONFIRMATION_PIN)
if __name__=='__main__':unittest.main()
