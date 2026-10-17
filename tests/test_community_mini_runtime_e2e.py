"""Login/HTTP composition with original order DB; provider and Identity are fixtures."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock
import test_community_stage_runtime as stage_fixture
import test_community_mini_login as login_fixture
from scripts.community_mini_login import MiniGateway,WechatCodeClient
from scripts.community_mini_http import serve
from scripts.community_demo_api import server_database

class MiniRuntimeIntegration(unittest.TestCase):
    def setUp(self):
        self.stage=stage_fixture.RuntimeJourney();self.stage.setUp()
        self.stage.o.close();self.stage.o=server_database(self.stage.order_path);self.stage.demo.db=self.stage.o
        self.identity=login_fixture.FixtureIdentity(self.stage.customer)
        self.provider=WechatCodeClient('wx1d5f8873eaea5392','a'*32)
        self.provider.exchange=Mock(return_value={'appid':self.provider.appid,'openid':'openid1'})
        self.gateway=MiniGateway(self.stage.api,self.identity,self.provider)
        self.server=serve(self.gateway);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.thread.join(3);self.server.server_close();self.stage.tearDown()
    def post(self,path,body,token=''):
        request=urllib.request.Request('http://127.0.0.1:%s'%self.server.server_port+path,json.dumps(body).encode(),
            headers={'Content-Type':'application/json','X-Community-Session':token})
        with urllib.request.urlopen(request) as response:return json.load(response)['result']
    def call(self,token,operation,params=None):
        return self.post('/mini/api',{'scene':'shop1','operation':operation,'params':params or {}},token)
    def test_login_scene_qr_order_result_and_revoke_complete_chain(self):
        token=self.post('/mini/login',{'code':'oncecode'})['session_token']
        self.assertEqual(self.call(token,'community.storefront')['merchant']['name'],'Demo Merchant A')
        qr=self.call(token,'community.qr',{'context':'mini'})['token']
        self.call(token,'community.checkout',{'context':'mini','token':qr,'reference':'order1','amount_minor':101})
        pending=self.call(token,'community.receipt',{'reference':'order1'})
        self.assertEqual(pending['payment_state'],'MOCK_PENDING')
        self.stage.api.simulate_from_operator(self.stage.owner,'order1','event1','SUCCESS','tx1')
        result=self.call(token,'community.receipt',{'reference':'order1'})
        self.assertEqual(result['order']['amount_minor'],101);self.assertFalse(result['provider_settlement_verified'])
        self.assertIsNotNone(result['ads']['AD_SLOT_PAYMENT_SUCCESS'])
        self.post('/mini/logout',{},token)
        with self.assertRaises(urllib.error.HTTPError) as denied:self.call(token,'community.storefront')
        self.assertEqual(denied.exception.code,403)
        self.assertEqual(self.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0],1)
    def test_authenticated_consumer_cannot_inject_scope_or_enter_admin(self):
        token=self.post('/mini/login',{'code':'oncecode'})['session_token']
        for operation,params in [('community.storefront',{'tenant_id':'tenant2'}),('community.orders',{})]:
            with self.assertRaises(urllib.error.HTTPError):self.call(token,operation,params)
        self.assertEqual(self.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0],0)

if __name__=='__main__':unittest.main()
