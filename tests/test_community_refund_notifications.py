"""Synthetic RSA/AES callbacks against original SQLite; no live funds calls."""
import base64
import hashlib
import json
import unittest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import test_community_mini_center_identity as identity_fixture
import test_community_wechat_sp_readonly as keys_fixture
from scripts.pr122_customer_core import canonical
from scripts.community_center_operations import CenterOperations
from scripts.community_wechat_sp_actions import ProviderActions
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_order_provider_projection import project_verified_query
from scripts.community_refund_notifications import RefundNotifications
from scripts.community_demo_bootstrap import DEMO_SCOPE


class RefundCallbackJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        keys_fixture.SignedOrderQuery.setUpClass();cls.keys=keys_fixture.SignedOrderQuery
    def setUp(self):
        self.fx=identity_fixture.ExistingCenterComposition();self.fx.setUp();self.fx.checkout(self.fx.token())
        self.c=self.fx.center;self.reader=PartnerOrderReader('1234567890','ABC',self.keys.private,'PUB_KEY_ID_fixture',self.keys.public,lambda:self.fx.stage.now)
        operations=CenterOperations(self.c,self.fx.stage.api,{'finance':dict(user_id=self.fx.uid1,project='project1',project_roles=['OWNER'],principal=self.fx.stage.owner)})
        policy=dict(sp_appid=self.fx.identity.appid,sub_mchid='1234567891',sub_appid=None,refund_notify_url='https://example.org/notify',profit_sharing=False,max_total_bps=0,receivers={},enabled_operations=['REFUND'])
        self.actions=ProviderActions(operations,self.reader,{tuple(DEMO_SCOPE[k] for k in ('tenant_id','merchant_id','store_id')):policy})
        self.expected=dict(sp_mchid=self.reader._mchid,sub_mchid=policy['sub_mchid'],sp_appid=policy['sp_appid'],out_trade_no='cm_fixture',amount_minor=101,currency='CNY')
        observed=dict(source='SIGNED_PROVIDER_ORDER_QUERY',signature_key_id=self.reader._kid,out_trade_no='cm_fixture',amount_minor=101,currency='CNY',provider_state='SUCCESS',transaction_id='123456789',body_sha256='1'*64)
        project_verified_query(self.fx.stage.o,DEMO_SCOPE,'order1',self.expected,observed,self.fx.stage.now,self.reader._kid)
        self.ref='rf_fixture';self.action_key=hashlib.sha256(canonical([self.reader._mchid,'REFUND',self.ref])).hexdigest()
        saved=dict(kind='REFUND',scope=DEMO_SCOPE,project='project1',actor_user_id=self.fx.uid1,reference='order1',request_id='request1',provider_reference=self.ref,transaction_id='123456789',request_hash='2'*64,payload=dict(sub_mchid=policy['sub_mchid'],out_trade_no='cm_fixture',amount=dict(total=101,refund=101,currency='CNY')))
        with self.c.tx():self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",(self.action_key,self.fx.uid1,'project1',self.c.encrypt(canonical(saved),'provider-action:'+self.action_key)))
        self.inbox=RefundNotifications(self.actions,b'a'*32)
    def tearDown(self):self.fx.tearDown()
    def callback(self,patch=None,event_id='refund_event',status='SUCCESS'):
        data=dict(sp_mchid=self.reader._mchid,sub_mchid='1234567891',out_trade_no='cm_fixture',transaction_id='123456789',out_refund_no=self.ref,refund_status=status,amount=dict(total=101,refund=101,currency='CNY'))
        data.update(patch or {})
        nonce='123456789012';aad='refund';cipher=AESGCM(b'a'*32).encrypt(nonce.encode(),canonical(data),aad.encode())
        raw=canonical(dict(id=event_id,event_type='REFUND.'+status,resource_type='encrypt-resource',resource=dict(algorithm='AEAD_AES_256_GCM',nonce=nonce,associated_data=aad,ciphertext=base64.b64encode(cipher).decode())))
        at=str(self.fx.stage.now);sig=self.keys.provider.sign((at+'\nnonce\n').encode()+raw+b'\n',padding.PKCS1v15(),hashes.SHA256())
        return {'Wechatpay-Serial':self.reader._kid,'Wechatpay-Timestamp':at,'Wechatpay-Nonce':'nonce','Wechatpay-Signature':base64.b64encode(sig).decode()},raw
    def test_verified_success_replays_and_second_event_do_not_double_refund(self):
        headers,raw=self.callback();self.assertTrue(self.inbox.receive(headers,raw)['accepted'])
        self.inbox.receive(headers,raw);self.inbox.receive(*self.callback(event_id='second_event'))
        self.assertEqual(self.fx.stage.o.execute("SELECT state FROM orders WHERE reference='order1'").fetchone()[0],'REFUNDED')
        self.assertEqual(self.fx.stage.o.execute("SELECT count(*) FROM order_events WHERE event_id LIKE 'wr_%'").fetchone()[0],1)
        self.assertEqual(self.actions._load(self.action_key)['result']['status'],'SUCCESS')
    def test_wrong_amount_submerchant_or_transaction_never_projects(self):
        for patch in (dict(sub_mchid='9999999999'),dict(transaction_id='987654321'),dict(amount=dict(total=101,refund=100,currency='CNY'))):
            with self.assertRaises(ValueError):self.inbox.receive(*self.callback(patch))
        self.assertEqual(self.fx.stage.o.execute("SELECT state FROM orders WHERE reference='order1'").fetchone()[0],'SUCCESS')
    def test_invalid_signature_and_unsupported_event_do_not_persist(self):
        headers,raw=self.callback();headers['Wechatpay-Signature']=base64.b64encode(b'x'*256).decode()
        with self.assertRaises(ValueError):self.inbox.receive(headers,raw)
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM links WHERE channel='COMMUNITY_REFUND_CALLBACK'").fetchone()[0],0)
    def test_abnormal_remains_unpaid_then_success_and_terminal_conflict(self):
        self.inbox.receive(*self.callback(status='ABNORMAL'))
        self.assertEqual(self.fx.stage.o.execute("SELECT state FROM orders WHERE reference='order1'").fetchone()[0],'SUCCESS')
        self.inbox.receive(*self.callback(event_id='success',status='SUCCESS'))
        with self.assertRaises(ValueError):self.inbox.receive(*self.callback(event_id='closed',status='CLOSED'))
