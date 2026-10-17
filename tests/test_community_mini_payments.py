"""Original Mini login -> original owned order -> signed prepay/query fixtures."""
import base64
import concurrent.futures
import json
import unittest
import urllib.request
import urllib.error
from unittest.mock import Mock
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import test_community_mini_center_identity as identity_fixture
import test_community_wechat_sp_readonly as key_fixture
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_sp_prepay import PartnerPrepay,PrepayUnknown
from scripts.community_mini_payments import MiniPayments
from scripts.community_mini_http import serve

class MiniPaymentJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):key_fixture.SignedOrderQuery.setUpClass();cls.keys=key_fixture.SignedOrderQuery
    def setUp(self):
        self.fx=identity_fixture.ExistingCenterComposition();self.fx.setUp();self.token=self.fx.token();self.fx.checkout(self.token)
        self.reader=PartnerOrderReader('1234567890','ABC',self.keys.private,'PUB_KEY_ID_fixture',self.keys.public,lambda:self.fx.stage.now)
        self.binding=dict(user_id=self.fx.uid1,project='project1',sp_appid=self.fx.identity.appid,sub_mchid='1234567891',out_trade_no='provider_order1',amount_minor=101,description='Fixture',notify_url='https://example.org/notify',sp_openid='openid1',profit_sharing=True)
        self.prepay=PartnerPrepay(self.fx.center,self.reader,{'order1':self.binding});self.payments=MiniPayments(self.fx.identity,self.prepay)
    def tearDown(self):self.fx.tearDown()
    def call(self,operation,token=None):return self.payments.dispatch(token or self.token,dict(scene='shop1',operation=operation,reference='order1'))
    def signed(self,data):
        raw=json.dumps(data).encode();at=str(self.fx.stage.now)
        signature=self.keys.provider.sign((at+'\nnonce\n').encode()+raw+b'\n',padding.PKCS1v15(),hashes.SHA256())
        return {'Wechatpay-Serial':'PUB_KEY_ID_fixture','Wechatpay-Timestamp':at,'Wechatpay-Nonce':'nonce','Wechatpay-Signature':base64.b64encode(signature).decode()},raw
    def paid(self):return self.signed(dict(sp_mchid='1234567890',sub_mchid=self.binding['sub_mchid'],sp_appid=self.binding['sp_appid'],out_trade_no=self.binding['out_trade_no'],amount={'total':101,'currency':'CNY'},trade_state='SUCCESS',transaction_id='123456789'))
    def test_prepare_recover_and_signed_query_do_not_turn_simulation_into_finance(self):
        self.reader._fetch=Mock(return_value=self.signed({'prepay_id':'fixture_prepay'}))
        first=self.call('prepare');again=self.call('recover');self.assertEqual(first['package'],again['package']);self.reader._fetch.assert_called_once()
        self.reader._fetch=Mock(return_value=self.paid());result=self.call('query')
        self.assertEqual(result['provider_state'],'SUCCESS');self.assertTrue(result['provider_signature_verified']);self.assertEqual(result['finance_status'],'UNCONFIRMED')
        self.assertEqual(self.fx.call(self.token,'community.receipt',{'reference':'order1'})['order']['state'],'PENDING')
    def test_foreign_customer_payer_amount_and_project_revoke_before_io(self):
        self.reader._fetch=Mock();second=self.fx.token('other_code','openid2')
        with self.assertRaises(PermissionError):self.call('prepare',second)
        for patch in (dict(sp_openid='openid2'),dict(amount_minor=102)):
            bad=MiniPayments(self.fx.identity,PartnerPrepay(self.fx.center,self.reader,{'order1':dict(self.binding,**patch)}))
            with self.assertRaises(PermissionError):bad.dispatch(self.token,dict(scene='shop1',operation='prepare',reference='order1'))
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.call('query')
        self.reader._fetch.assert_not_called()
    def test_query_revocation_during_network_and_unknown_prepare_are_not_success(self):
        def provider(request):
            self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,));return self.paid()
        self.reader._fetch=Mock(side_effect=provider)
        with self.assertRaises(PermissionError):self.call('query')
        self.fx.center.db.execute('UPDATE members SET active=1 WHERE user_id=?',(self.fx.uid1,))
        self.reader._fetch=Mock(side_effect=TimeoutError())
        with self.assertRaises(PrepayUnknown):self.call('prepare')
        with self.assertRaises(PrepayUnknown):self.call('prepare')
        self.reader._fetch.assert_called_once()
    def test_protected_merchant_config_builds_owned_order_binding_and_survives_reopen(self):
        merchants={'shop1':{k:self.binding[k] for k in ('sp_appid','sub_mchid','description','notify_url','profit_sharing')}}
        client=MiniPayments(self.fx.identity,PartnerPrepay(self.fx.center,self.reader,{}),merchants)
        self.reader._fetch=Mock(return_value=self.signed({'prepay_id':'dynamic_prepay'}))
        body=dict(scene='shop1',operation='prepare',reference='order1')
        result=client.dispatch(self.token,body);request=self.reader._fetch.call_args.args[0];payload=json.loads(request.data)
        self.assertEqual(payload['amount']['total'],101);self.assertEqual(payload['payer']['sp_openid'],'openid1')
        self.assertEqual(len(payload['out_trade_no']),32);self.assertTrue(payload['out_trade_no'].startswith('cm'))
        self.fx.reopen()
        again=MiniPayments(self.fx.identity,PartnerPrepay(self.fx.center,self.reader,{}),merchants)
        recovered=again.dispatch(self.token,dict(body,operation='recover'))
        self.assertEqual(recovered['package'],result['package']);self.reader._fetch.assert_called_once()
        with self.assertRaises(PrepayUnknown):again.dispatch(self.token,body)
    def test_dynamic_payment_binding_rejects_amount_change_after_provider_io(self):
        merchants={'shop1':{k:self.binding[k] for k in ('sp_appid','sub_mchid','description','notify_url','profit_sharing')}}
        client=MiniPayments(self.fx.identity,PartnerPrepay(self.fx.center,self.reader,{}),merchants)
        def provider(request):
            self.fx.stage.demo.db.execute("UPDATE orders SET amount_minor=102 WHERE reference='order1'");self.fx.stage.demo.db.commit()
            return self.signed({'prepay_id':'stale_amount'})
        self.reader._fetch=Mock(side_effect=provider)
        with self.assertRaises(PrepayUnknown):client.dispatch(self.token,dict(scene='shop1',operation='prepare',reference='order1'))
        self.assertIsNone(self.fx.center.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_PREPAY_RESULT'").fetchone())
    def test_explicit_http_route_default_closed_and_owned_bearer_only(self):
        for enabled in (False,True):
            self.fx.gateway.payments=self.payments if enabled else None;server=serve(self.fx.gateway)
            self.reader._fetch=Mock(return_value=self.paid())
            def request(extra=None):
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/payment',data=json.dumps(dict(scene='shop1',operation='query',reference='order1')).encode(),headers={'Content-Type':'application/json','X-Community-Session':self.token,**(extra or {})})
                try:
                    with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
                except urllib.error.HTTPError as e:return e.code,json.load(e)
            try:
                for headers,expected in [({},200 if enabled else 404),({'Cookie':'__Host-xj_customer=x'},403 if enabled else 404)]:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        f=pool.submit(request,headers);server.handle_request();code,result=f.result()
                    self.assertEqual(code,expected)
                    if code==200:self.assertTrue(result['payment_enabled'])
            finally:server.server_close()

if __name__=='__main__':unittest.main()
