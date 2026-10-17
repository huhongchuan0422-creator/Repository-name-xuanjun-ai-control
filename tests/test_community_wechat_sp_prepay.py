"""New prepay implementation: real RSA/SQLite, explicitly synthetic provider IO."""
import base64
import json
import re
import unittest
from unittest.mock import Mock
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import test_community_center_operations as center_fixture
import test_community_wechat_sp_readonly as crypto_fixture
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_sp_prepay import PartnerPrepay,PrepayUnknown

class PrepayFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        crypto_fixture.SignedOrderQuery.setUpClass()
        cls.keys=crypto_fixture.SignedOrderQuery
    def setUp(self):
        self.fx=center_fixture.ExistingCenterOperations();self.fx.setUp()
        self.reader=PartnerOrderReader('1234567890','ABC',self.keys.private,'PUB_KEY_ID_fixture',self.keys.public,lambda:1700000000)
        self.binding=dict(user_id=self.fx.fx.uid1,project='project1',sp_appid='wx1d5f8873eaea5392',sub_mchid='1234567891',out_trade_no='payorder1',amount_minor=101,description='Fixture order',notify_url='https://example.org/payment/notify',sp_openid='fixture_openid',profit_sharing=True)
        self.client=PartnerPrepay(self.fx.fx.center,self.reader,{'ref1':self.binding})
    def tearDown(self):self.fx.tearDown()
    def signed(self,raw=None):
        raw=raw if raw is not None else b'{"prepay_id":"fixture_prepay"}'
        signature=self.keys.provider.sign(b'1700000000\nnonce\n'+raw+b'\n',padding.PKCS1v15(),hashes.SHA256())
        return {'Wechatpay-Serial':'PUB_KEY_ID_fixture','Wechatpay-Timestamp':'1700000000','Wechatpay-Nonce':'nonce','Wechatpay-Signature':base64.b64encode(signature).decode()},raw
    def create(self):return self.client.create(self.fx.web['token'],self.fx.web['csrf'],'ref1')
    def test_request_and_client_signature_existing_result_without_second_request(self):
        self.reader._fetch=Mock(return_value=self.signed());result=self.create()
        request=self.reader._fetch.call_args.args[0];self.assertEqual(request.method,'POST')
        body=json.loads(request.data);self.assertEqual(body['amount'],{'total':101,'currency':'CNY'});self.assertTrue(body['settle_info']['profit_sharing'])
        fields=dict(re.findall(r'([a-z_]+)="([^"]*)"',request.get_header('Authorization')))
        message=('POST\n/v3/pay/partner/transactions/jsapi\n'+fields['timestamp']+'\n'+fields['nonce_str']+'\n').encode()+request.data+b'\n'
        self.keys.merchant.public_key().verify(base64.b64decode(fields['signature']),message,padding.PKCS1v15(),hashes.SHA256())
        client_message=('wx1d5f8873eaea5392\n'+result['timeStamp']+'\n'+result['nonceStr']+'\n'+result['package']+'\n').encode()
        self.keys.merchant.public_key().verify(base64.b64decode(result['paySign']),client_message,padding.PKCS1v15(),hashes.SHA256())
        self.assertNotIn('fixture_openid',json.dumps(result));self.assertFalse(result['provider_settlement_verified'])
        again=PartnerPrepay(self.fx.fx.center,self.reader,{'ref1':self.binding})
        self.assertEqual(again.existing(self.fx.web['token'],self.fx.web['csrf'],'ref1')['package'],result['package'])
        with self.assertRaises(PrepayUnknown):self.create()
        self.reader._fetch.assert_called_once()
    def test_unknown_network_consumed_across_new_composition(self):
        self.reader._fetch=Mock(side_effect=TimeoutError('secret URL'))
        with self.assertRaises(PrepayUnknown) as caught:self.create()
        self.assertNotIn('secret',str(caught.exception))
        again=PartnerPrepay(self.fx.fx.center,self.reader,{'ref1':self.binding})
        with self.assertRaises(PrepayUnknown):again.create(self.fx.web['token'],self.fx.web['csrf'],'ref1')
        with self.assertRaises(PrepayUnknown):again.existing(self.fx.web['token'],self.fx.web['csrf'],'ref1')
        self.reader._fetch.assert_called_once()
    def test_wrong_owner_and_csrf_never_reach_provider(self):
        self.reader._fetch=Mock()
        for web in (self.fx.other,dict(self.fx.web,csrf='wrong')):
            with self.assertRaises(PermissionError):self.client.create(web['token'],web['csrf'],'ref1')
        self.reader._fetch.assert_not_called()
    def test_invalid_response_signature_never_persists_payment_parameters(self):
        h,b=self.signed();self.reader._fetch=Mock(return_value=(h,b+b' '))
        with self.assertRaises(PrepayUnknown):self.create()
        with self.assertRaises(PrepayUnknown):self.client.existing(self.fx.web['token'],self.fx.web['csrf'],'ref1')
    def test_project_revocation_during_io_prevents_client_payment_signature(self):
        def provider(request):
            self.fx.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid1,));return self.signed()
        self.reader._fetch=Mock(side_effect=provider)
        with self.assertRaises(PrepayUnknown):self.create()
        self.assertIsNone(self.fx.fx.center.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_PREPAY_RESULT'").fetchone())
    def test_configuration_binding_changes_and_duplicate_order_numbers(self):
        self.reader._fetch=Mock(return_value=self.signed());self.create()
        changed=PartnerPrepay(self.fx.fx.center,self.reader,{'ref1':dict(self.binding,amount_minor=102)})
        with self.assertRaises(PermissionError):changed.existing(self.fx.web['token'],self.fx.web['csrf'],'ref1')
        with self.assertRaises(ValueError):PartnerPrepay(self.fx.fx.center,self.reader,{'ref1':self.binding,'ref2':self.binding})
        for patch in (dict(amount_minor=True),dict(notify_url='http://example.org/x'),dict(sp_openid='x\n'),dict(out_trade_no='../x')):
            with self.assertRaises(ValueError):PartnerPrepay(self.fx.fx.center,self.reader,{'ref1':dict(self.binding,**patch)})

if __name__=='__main__':unittest.main()
