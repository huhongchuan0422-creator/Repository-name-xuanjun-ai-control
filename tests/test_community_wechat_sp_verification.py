import base64
import json
import unittest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from scripts.community_wechat_sp_verification import verify_signed_body,notification_candidate

class PublicKeyCandidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.pub=cls.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    def setUp(self):
        self.now=1700000000;self.kid='PUB_KEY_ID_fixture';self.aes=b'k'*32
        self.order={'sp_mchid':'1234567890','sub_mchid':'1234567891','sp_appid':'wx1d5f8873eaea5392',
                    'out_trade_no':'order1','amount_minor':101,'currency':'CNY'}
    def signed(self,body,stamp=None):
        stamp=str(self.now if stamp is None else stamp);nonce='fixture_nonce'
        sig=self.key.sign(stamp.encode()+b'\n'+nonce.encode()+b'\n'+body+b'\n',padding.PKCS1v15(),hashes.SHA256())
        return {'Wechatpay-Serial':self.kid,'Wechatpay-Timestamp':stamp,'Wechatpay-Nonce':nonce,'Wechatpay-Signature':base64.b64encode(sig).decode()}
    def event(self,changes=None):
        payment={k:self.order[k] for k in ('sp_mchid','sub_mchid','sp_appid','out_trade_no')}
        payment.update(amount={'total':101,'currency':'CNY'},trade_state='SUCCESS',transaction_id='1234567890123')
        payment.update(changes or {})
        encrypted=AESGCM(self.aes).encrypt(b'012345678901',json.dumps(payment).encode(),b'transaction')
        return json.dumps({'id':'event1','event_type':'TRANSACTION.SUCCESS','resource_type':'encrypt-resource',
            'resource':{'algorithm':'AEAD_AES_256_GCM','nonce':'012345678901','associated_data':'transaction',
                        'ciphertext':base64.b64encode(encrypted).decode()}}).encode()
    def parse(self,body=None,key=None,order=None):
        body=body or self.event()
        return notification_candidate(self.signed(body),body,self.pub,self.kid,key or self.aes,order or self.order,self.now)
    def test_valid_signature_and_decryption_no_money_effect(self):
        r=self.parse();self.assertFalse(r['finance_write']);self.assertFalse(r['provider_settlement_verified'])
        self.assertEqual(r['payment'],'HOLD');self.assertEqual(r['reconciliation'],'REQUIRED')
        self.assertFalse(r['replay_authorization'])
    def test_tampered_raw_body_rejected_before_json(self):
        body=self.event()
        with self.assertRaisesRegex(ValueError,'INVALID_SIGNATURE'):
            verify_signed_body(self.signed(body),body+b' ',self.pub,self.kid,self.now)
    def test_expired_and_future_signatures_rejected(self):
        body=self.event()
        for offset in (-301,301):
            with self.assertRaisesRegex(ValueError,'SIGNATURE_TIME_WINDOW'):
                verify_signed_body(self.signed(body,self.now+offset),body,self.pub,self.kid,self.now)
    def test_wrong_pinned_key_id(self):
        body=self.event()
        with self.assertRaisesRegex(ValueError,'PINNED_PUBLIC_KEY'):
            verify_signed_body(self.signed(body),body,self.pub,'PUB_KEY_ID_other',self.now)
    def test_wrong_aes_key(self):
        with self.assertRaisesRegex(ValueError,'RESOURCE_DECRYPTION_FAILED'):self.parse(key=b'x'*32)
    def test_cross_merchant_and_order_rejected(self):
        for field in ('sp_mchid','sub_mchid','sp_appid','out_trade_no'):
            with self.assertRaisesRegex(ValueError,'ORDER_BINDING_MISMATCH'):self.parse(self.event({field:'other'}))
    def test_boolean_float_wrong_currency_amount_rejected(self):
        for amount in ({'total':True,'currency':'CNY'},{'total':101.0,'currency':'CNY'},
                       {'total':102,'currency':'CNY'},{'total':101,'currency':'USD'}):
            with self.assertRaisesRegex(ValueError,'ORDER_AMOUNT_MISMATCH'):self.parse(self.event({'amount':amount}))
    def test_non_success_rejected(self):
        with self.assertRaisesRegex(ValueError,'INVALID_TRANSACTION'):self.parse(self.event({'trade_state':'NOTPAY'}))
    def test_duplicate_signed_json_rejected(self):
        body=b'{"id":"event1","id":"event2"}'
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):self.parse(body)
    def test_duplicate_case_headers_rejected(self):
        body=self.event();h=self.signed(body);h['wechatpay-serial']=self.kid
        with self.assertRaisesRegex(ValueError,'DUPLICATE_HEADER'):
            verify_signed_body(h,body,self.pub,self.kid,self.now)
    def test_repeat_is_candidate_not_replay_permission(self):
        body=self.event();a=self.parse(body);b=self.parse(body)
        self.assertEqual(a['body_sha256'],b['body_sha256']);self.assertFalse(b['replay_authorization'])

if __name__=='__main__':unittest.main()
