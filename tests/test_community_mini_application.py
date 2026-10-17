"""Existing Center + protected binding + real loopback HTTP, synthetic provider IO."""
import concurrent.futures
import json
import tempfile
import unittest
import urllib.request
import urllib.error
from unittest.mock import Mock
import test_community_mini_center_identity as center_fixture
from scripts.community_mini_application import MiniApplication
from scripts.community_mini_http import serve
from scripts.community_mini_login import LoginUnavailable

class AdmittedMiniApplication(unittest.TestCase):
    def setUp(self):
        self.fixture=center_fixture.ExistingCenterComposition('test_core_bytes_are_identical_to_pinned_original')
        self.fixture.setUp()
        self.fx=self.fixture
        self.web=self.fx.center.login('one@example.org','FixturePassword123!')
        self.fx.provider.exchange.return_value={'appid':self.fx.identity.appid,'openid':'new_openid'}
    def tearDown(self):self.fixture.tearDown()
    def bind(self,code='bind_code',csrf=None):
        return self.fx.gateway.bind(self.web['token'],self.web['csrf'] if csrf is None else csrf,{'code':code})
    def test_verified_center_binding_then_login_uses_same_original_account(self):
        before=self.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        self.assertEqual(self.bind(),{'bound':True})
        token=self.fx.gateway.login({'code':'fresh_login_code'})['session_token']
        self.assertEqual(self.fx.center.session(token),self.fx.uid1)
        self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
    def test_missing_or_wrong_csrf_does_not_contact_provider_or_consume_code(self):
        for csrf in ('','wrong'):
            with self.assertRaises(PermissionError):self.bind(csrf=csrf)
        self.fx.provider.exchange.assert_not_called()
        self.assertEqual(self.bind(),{'bound':True})
    def test_anonymous_binding_rejected_before_provider(self):
        with self.assertRaises(PermissionError):self.fx.gateway.bind('unknown',self.web['csrf'],{'code':'bind_code'})
        self.fx.provider.exchange.assert_not_called()
    def test_failed_binding_code_stays_consumed_after_restart(self):
        self.fx.provider.exchange.side_effect=TimeoutError('credential bearing provider failure')
        with self.assertRaises(LoginUnavailable):self.bind()
        self.fx.reopen();self.fx.provider.exchange.side_effect=None;self.fx.provider.exchange.reset_mock()
        with self.assertRaises(PermissionError):self.bind()
        self.fx.provider.exchange.assert_not_called()
    def test_revoked_web_session_during_exchange_cannot_bind(self):
        def exchange(code):
            self.fx.center.logout(self.web['token'])
            return {'appid':self.fx.identity.appid,'openid':'new_openid'}
        self.fx.provider.exchange.side_effect=exchange
        with self.assertRaises(LoginUnavailable):self.bind()
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?",(self.fx.identity._subject(self.fx.identity.appid,'new_openid'),)).fetchone()[0],0)
    def test_existing_provider_subject_cannot_be_taken_over(self):
        self.fx.provider.exchange.return_value={'appid':self.fx.identity.appid,'openid':'openid2'}
        with self.assertRaises(LoginUnavailable):self.bind()
    def test_real_exchange_duration_uses_current_clock_for_session_issue(self):
        def exchange(code):
            self.fx.stage.now+=3
            return {'appid':self.fx.identity.appid,'openid':'openid1'}
        self.fx.provider.exchange.side_effect=exchange
        result=self.fx.gateway.login({'code':'delayed_provider_code'})
        self.assertEqual(result['expires_at'],self.fx.stage.now+3600)
        self.assertEqual(self.fx.center.session(result['session_token']),self.fx.uid1)
    def test_binding_rate_limit_is_original_persistent_center_limit(self):
        for i in range(5):self.bind('code_'+str(i))
        self.fx.provider.exchange.reset_mock()
        with self.assertRaises(PermissionError):self.bind('code_six')
        self.fx.provider.exchange.assert_not_called()
    def test_http_binding_requires_original_center_session_and_csrf(self):
        server=serve(self.fx.gateway)
        try:
            def request():
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/bind',
                    data=json.dumps({'code':'http_bind'}).encode(),headers={'Content-Type':'application/json',
                    'X-Center-Session':self.web['token'],'X-Center-CSRF':self.web['csrf']})
                with urllib.request.urlopen(req,timeout=3) as r:return json.load(r)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(request);server.handle_request();result=future.result()
            self.assertEqual(result,{'result':{'bound':True},'payment_enabled':False})
        finally:server.server_close()
    def test_composed_listener_reuses_center_and_does_not_seed_or_close_it(self):
        with tempfile.TemporaryDirectory() as root:
            with MiniApplication(self.fx.center,root,self.fx.stage.api.bindings,
                    self.fx.stage.api.bindings[self.fx.stage.customer],self.fx.scenes,
                    self.fx.identity.appid,'a'*32) as app:
                app.gateway.provider.exchange=Mock(return_value={'appid':app.identity.appid,'openid':'new_openid'})
                self.assertEqual(app.gateway.bind(self.web['token'],self.web['csrf'],{'code':'composition_bind'}),{'bound':True})
                self.assertEqual(app.stage.demo.db.execute('SELECT count(*) FROM orders').fetchone()[0],0)
                self.assertEqual(app.listen().server_address[0],'127.0.0.1')
                with self.assertRaises(ValueError):app.listen()
                token=app.gateway.login({'code':'composition_login'})['session_token']
                self.assertEqual(self.fx.center.session(token),self.fx.uid1)
            self.assertEqual(self.fx.center.session(self.web['token']),self.fx.uid1)
            with MiniApplication(self.fx.center,root,self.fx.stage.api.bindings,
                    self.fx.stage.api.bindings[self.fx.stage.customer],self.fx.scenes,
                    self.fx.identity.appid,'a'*32) as reopened:
                self.assertEqual(reopened.identity.resolve(token,'shop1',self.fx.stage.now),self.fx.stage.customer)

if __name__=='__main__':unittest.main()
