import base64
import datetime
import json
import re
import unittest
from unittest.mock import Mock
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.x509.oid import NameOID
from scripts.community_wechat_sp_readonly import PartnerOrderReader,ReadOnlyUnknown,certificate_matches

class SignedOrderQuery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.merchant=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.provider=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.private=cls.merchant.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        cls.public=cls.provider.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    def setUp(self):
        self.reader=PartnerOrderReader('1234567890','ABC',self.private,'PUB_KEY_ID_fixture',self.public,lambda:1700000000)
        self.expected={'sp_mchid':'1234567890','sub_mchid':'1234567891','sp_appid':'wx1d5f8873eaea5392',
                       'out_trade_no':'order1','amount_minor':101,'currency':'CNY'}
    def signed(self,changes=None):
        data={k:self.expected[k] for k in ('sp_mchid','sub_mchid','sp_appid','out_trade_no')}
        data.update(amount={'total':101,'currency':'CNY'},trade_state='SUCCESS',transaction_id='123456789')
        data.update(changes or {});raw=json.dumps(data).encode()
        signature=self.provider.sign(b'1700000000\nnonce\n'+raw+b'\n',padding.PKCS1v15(),hashes.SHA256())
        return {'Wechatpay-Serial':'PUB_KEY_ID_fixture','Wechatpay-Timestamp':'1700000000',
                'Wechatpay-Nonce':'nonce','Wechatpay-Signature':base64.b64encode(signature).decode()},raw
    def test_exact_signed_get_and_no_financial_write(self):
        self.reader._fetch=Mock(return_value=self.signed())
        result=self.reader.read_order(self.expected);request=self.reader._fetch.call_args.args[0]
        self.assertEqual(request.method,'GET');self.assertIsNone(request.data)
        auth=request.get_header('Authorization');fields=dict(re.findall(r'([a-z_]+)="([^"]*)"',auth))
        target=request.full_url.removeprefix('https://api.mch.weixin.qq.com')
        message=('GET\n'+target+'\n'+fields['timestamp']+'\n'+fields['nonce_str']+'\n\n').encode()
        self.merchant.public_key().verify(base64.b64decode(fields['signature']),message,padding.PKCS1v15(),hashes.SHA256())
        self.assertEqual(result['provider_state'],'SUCCESS');self.assertFalse(result['finance_write'])
        self.assertFalse(result['provider_settlement_verified']);self.assertEqual(result['payment'],'HOLD')
    def test_absent_submerchant_or_injected_path_never_reaches_network(self):
        self.reader._fetch=Mock()
        for change in ({'sub_mchid':None},{'out_trade_no':'../order1'},{'amount_minor':True},{'sp_mchid':'9999999999'}):
            with self.assertRaises(ValueError):self.reader.read_order(dict(self.expected,**change))
        self.reader._fetch.assert_not_called()
    def test_invalid_signature_unknown_and_no_retry(self):
        headers,body=self.signed();self.reader._fetch=Mock(return_value=(headers,body+b' '))
        with self.assertRaises(ReadOnlyUnknown):self.reader.read_order(self.expected)
        self.reader._fetch.assert_called_once()
    def test_signed_amount_or_merchant_mismatch_rejected(self):
        for change in ({'sub_mchid':'99999999'},{'amount':{'total':102,'currency':'CNY'}},{'amount':{'total':101.0,'currency':'CNY'}}):
            self.reader._fetch=Mock(return_value=self.signed(change))
            with self.assertRaises(ReadOnlyUnknown):self.reader.read_order(self.expected)
    def test_timeout_redacted_and_not_retried(self):
        self.reader._fetch=Mock(side_effect=TimeoutError('Authorization secret'))
        with self.assertRaises(ReadOnlyUnknown) as caught:self.reader.read_order(self.expected)
        self.assertNotIn('secret',str(caught.exception));self.assertIsNone(caught.exception.__cause__)
        self.reader._fetch.assert_called_once()
    def test_unpaid_signed_reply_is_not_payment_proof(self):
        self.reader._fetch=Mock(return_value=self.signed({'trade_state':'NOTPAY','transaction_id':None}))
        result=self.reader.read_order(self.expected);self.assertEqual(result['provider_state'],'NOTPAY')
        self.assertFalse(result['finance_write']);self.assertIsNone(result['transaction_id'])
    def test_real_local_certificate_pair_and_serial(self):
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'fixture')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(self.merchant.public_key()).serial_number(0xABC).not_valid_before(now).not_valid_after(now+datetime.timedelta(days=1)).sign(self.merchant,hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
        self.assertTrue(certificate_matches(self.private,cert,'ABC'))
        self.assertFalse(certificate_matches(self.private,cert,'ABD'))
        other=self.provider.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        self.assertFalse(certificate_matches(other,cert,'ABC'))

if __name__=='__main__':unittest.main()
