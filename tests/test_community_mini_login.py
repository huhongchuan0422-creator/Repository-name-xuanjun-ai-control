"""Adapter fixture tests, not live WeChat or production Identity acceptance."""
import base64
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock,patch
from scripts.community_mini_login import IdentityPort,MiniGateway,WechatCodeClient,LoginUnavailable
from scripts.community_mini_http import serve
from scripts.community_saas_phase2 import Principal

class FixtureIdentity(IdentityPort):
    def __init__(self,principal):self.principal=principal;self.used=set();self.sessions={};self.failures=[]
    def reserve_code(self,appid,digest,now):
        if digest in self.used:raise PermissionError('CODE_ALREADY_CONSUMED')
        self.used.add(digest);return digest
    def issue_session(self,attempt,appid,openid,now):
        if openid!='openid1':raise PermissionError('UNKNOWN_EXISTING_CUSTOMER')
        token='s'*32;self.sessions[token]=now+100;return {'session_token':token,'expires_at':now+100}
    def abandon_attempt(self,attempt,reason,now):self.failures.append(attempt)
    def resolve(self,token,scene,now):
        if self.sessions.get(token,0)<=now or scene!='shop1':raise PermissionError('INVALID_SESSION_OR_SCENE')
        return self.principal
    def revoke(self,token,now):self.sessions.pop(token,None)

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.principal=Principal('tenant1','CUSTOMER');self.identity=FixtureIdentity(self.principal)
        self.provider=WechatCodeClient('wx1d5f8873eaea5392','a'*32)
        self.provider.exchange=Mock(return_value={'appid':self.provider.appid,'openid':'openid1'})
        self.runtime=Mock();self.runtime.clock.return_value=100
        self.runtime.dispatch.return_value={'simulation_only':True}
        self.gateway=MiniGateway(self.runtime,self.identity,self.provider)
    def logged(self):return self.gateway.login({'code':'oncecode'})['session_token']
    def body(self):return {'scene':'shop1','operation':'community.storefront','params':{}}
    def test_login_resolves_existing_customer_and_leaks_no_provider_keys(self):
        result=self.gateway.login({'code':'oncecode'})
        self.assertEqual(set(result),{'session_token','expires_at','provider','payment_enabled'})
        self.assertFalse(result['payment_enabled']);self.assertNotIn('openid',json.dumps(result))
    def test_repeated_code_never_reaches_provider(self):
        self.logged()
        with self.assertRaises(PermissionError):self.gateway.login({'code':'oncecode'})
        self.assertEqual(self.provider.exchange.call_count,1)
    def test_unknown_provider_result_consumes_code_no_blind_retry(self):
        self.provider.exchange.side_effect=TimeoutError('secretcode')
        with self.assertRaisesRegex(LoginUnavailable,'LOGIN_RESULT_UNKNOWN') as caught:self.logged()
        self.assertNotIn('secretcode',str(caught.exception));self.assertIsNone(caught.exception.__cause__)
        with self.assertRaises(PermissionError):self.logged()
        self.assertEqual(len(self.identity.failures),1)
    def test_client_role_and_openid_injection_rejected(self):
        for field in ('role','openid','tenant_id','session_key'):
            with self.assertRaises(ValueError):self.gateway.login({'code':'oncecode',field:'bad'})
        self.provider.exchange.assert_not_called()
    def test_current_identity_authority_is_checked_every_request(self):
        token=self.logged();self.gateway.dispatch(token,self.body())
        self.identity.revoke(token,100)
        with self.assertRaises(PermissionError):self.gateway.dispatch(token,self.body())
        self.runtime.dispatch.assert_called_once_with(self.principal,'community.storefront',{},None)
    def test_expired_session_rejected(self):
        token=self.logged();self.runtime.clock.return_value=200
        with self.assertRaises(PermissionError):self.gateway.dispatch(token,self.body())
    def test_scene_cannot_select_arbitrary_tenant_or_admin(self):
        token=self.logged()
        for scene in ('shop2','../shop1','tenant1/shop1','x'*33):
            with self.assertRaises((PermissionError,ValueError)):self.gateway.dispatch(token,dict(self.body(),scene=scene))
        self.identity.principal=Principal('tenant1','PLATFORM_OWNER')
        with self.assertRaises(PermissionError):self.gateway.dispatch(token,self.body())
        self.runtime.dispatch.assert_not_called()
    def test_logout_revokes_existing_session(self):
        token=self.logged();self.assertTrue(self.gateway.logout(token)['logged_out'])
        with self.assertRaises(PermissionError):self.gateway.dispatch(token,self.body())
    def test_unknown_customer_not_auto_registered(self):
        self.provider.exchange.return_value={'appid':self.provider.appid,'openid':'unregistered'}
        with self.assertRaises(LoginUnavailable):self.logged()
        self.assertEqual(self.identity.sessions,{})
    def test_mismatched_provider_appid_rejected(self):
        self.provider.exchange.return_value={'appid':'wx0000000000000000','openid':'openid1'}
        with self.assertRaises(LoginUnavailable):self.logged()
        self.assertEqual(self.identity.sessions,{})
    def test_http_login_business_logout_no_secret_output(self):
        server=serve(self.gateway);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(path,body,token=''):
            req=urllib.request.Request('http://127.0.0.1:%s'%server.server_port+path,json.dumps(body).encode(),
                headers={'Content-Type':'application/json','X-Community-Session':token})
            with urllib.request.urlopen(req) as response:return json.load(response)
        try:
            result=post('/mini/login',{'code':'oncecode'});token=result['result']['session_token']
            self.assertFalse(post('/mini/api',self.body(),token)['payment_enabled'])
            self.assertTrue(post('/mini/logout',{},token)['result']['logged_out'])
            with self.assertRaises(urllib.error.HTTPError) as caught:post('/mini/api',self.body(),token)
            self.assertEqual(caught.exception.code,403)
        finally:server.shutdown();thread.join(3);server.server_close()
    def test_real_transport_contract_no_redirect_and_redacted_errors(self):
        client=WechatCodeClient('wx1d5f8873eaea5392','SECRET'*6)
        response=Mock();response.status=200
        response.read.return_value=json.dumps({'openid':'openid1','session_key':base64.b64encode(b'k'*16).decode()}).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with patch('urllib.request.build_opener',return_value=opener):
            self.assertEqual(client.exchange('oncecode'),{'appid':client.appid,'openid':'openid1'})
            self.assertTrue(opener.open.call_args.args[0].full_url.startswith('https://api.weixin.qq.com/sns/jscode2session?'))
        opener.open.side_effect=urllib.error.URLError('SECRETSECRET')
        with patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(LoginUnavailable) as caught:client.exchange('oncecode')
            self.assertNotIn('SECRET',str(caught.exception));self.assertIsNone(caught.exception.__cause__)

if __name__=='__main__':unittest.main()
