"""Community attribution and payout read models use immutable original snapshots."""
import base64
import hashlib
import json
import unittest
from unittest.mock import Mock
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import test_community_mini_center_identity as fixtures
import test_community_wechat_sp_readonly as keys
from scripts.pr122_customer_core import canonical
from scripts.community_center_communities import CenterCommunities
from scripts.community_center_operations import CenterOperations
from scripts.community_commerce import Commerce
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_sp_actions import ProviderActions
from scripts.community_split_rules import SplitRules
from scripts.community_order_provider_projection import project_verified_query
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.community_provider_reference import provider_order_reference

class CommunityReportJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):keys.SignedOrderQuery.setUpClass()
    def setUp(self):
        self.fx=fixtures.ExistingCenterComposition();self.fx.setUp();self.c=self.fx.center
        self.web=self.c.login('one@example.org','FixturePassword123!');self.reviewer=self.c.login('two@example.org','FixturePassword123!');self.token=self.fx.token()
        grants={}
        for name,user,role in [('community',self.fx.uid1,'COMMUNITY_ADMIN'),('customer',self.fx.uid1,'CUSTOMER'),('platform',self.fx.uid1,'PLATFORM_OWNER'),('reviewer',self.fx.uid2,'PLATFORM_REVIEWER'),('other',self.fx.uid2,'COMMUNITY_ADMIN')]:grants[name]=dict(user_id=user,project='project1',tenant='tenant1',role=role)
        self.communities=CenterCommunities(self.c,grants)
        def grant(principal):return dict(user_id=self.fx.uid1,project='project1',project_roles=['OWNER'],principal=principal)
        self.ops=CenterOperations(self.c,self.fx.stage.api,dict(merchant=grant(self.fx.stage.merchant),finance=grant(self.fx.stage.owner)))
        self.commerce=Commerce(self.ops,self.fx.identity)
        self.reader=PartnerOrderReader('1234567890','ABC',keys.SignedOrderQuery.private,'PUB_KEY_ID_fixture',keys.SignedOrderQuery.public,lambda:self.fx.stage.now)
        policy=dict(sp_appid=self.fx.identity.appid,sub_mchid='1234567891',sub_appid=None,refund_notify_url='https://example.org/notify',profit_sharing=True,max_total_bps=1000,receivers={'comm':dict(type='MERCHANT_ID',account='1234567892',name='Fixture Community',label='Community')},enabled_operations=['SPLIT','RETURN'])
        self.actions=ProviderActions(self.ops,self.reader,{tuple(DEMO_SCOPE[k] for k in ('tenant_id','merchant_id','store_id')):policy})
        self.communities.commerce=self.commerce;self.communities.provider_actions=self.actions
        draft=self.call('register',dict(name='Community',description='Fixture',contact='private'))
        self.cid=draft['id'];self.call('submit',dict(community_id=self.cid,expected_version=1))
        self.call('review',dict(community_id=self.cid,expected_version=2,decision='APPROVED',opinion='checked'),workspace='reviewer',web=self.reviewer)
    def tearDown(self):self.fx.tearDown()
    def call(self,op,p,workspace='community',web=None):
        w=web or self.web
        return self.communities.dispatch(w['token'],w['csrf'],dict(workspace=workspace,operation=op,params=p))
    def finance(self,op,p):return self.actions.dispatch(self.web['token'],self.web['csrf'],dict(workspace='finance',operation=op,params=p))
    def basket(self):
        self.call('join',dict(community_id=self.cid,kind='CUSTOMER'),workspace='customer')
        self.commerce.dispatch(self.web['token'],self.web['csrf'],dict(workspace='merchant',operation='price_set',params=dict(item_id='sample_item',expected_revision=0,unit_minor=101,stock=3,enabled=True)))
        return self.commerce.consumer(self.token,'shop1','purchase',dict(reference='basket',lines=[dict(item_id='sample_item',quantity=1,revision=1)]))
    def signed_response(self,data):
        raw=canonical(data);now=str(self.c.now());nonce='report-fixture'
        signature=keys.SignedOrderQuery.provider.sign((now+'\n'+nonce+'\n').encode()+raw+b'\n',padding.PKCS1v15(),hashes.SHA256())
        return {'Wechatpay-Serial':'PUB_KEY_ID_fixture','Wechatpay-Timestamp':now,
            'Wechatpay-Nonce':nonce,'Wechatpay-Signature':base64.b64encode(signature).decode()},raw
    def complete_split(self):
        # Populate the real executor's action, original-order budget and signature
        # evidence instead of a partial manually injected report-only action.
        def provider(request):
            if request.method=='GET' and '/v3/pay/partner/transactions/' in request.full_url:
                return self.signed_response(dict(sp_mchid=self.reader._mchid,sub_mchid='1234567891',
                    sp_appid=self.fx.identity.appid,out_trade_no=provider_order_reference(self.reader._mchid,DEMO_SCOPE,'basket'),
                    amount=dict(total=101,currency='CNY'),trade_state='SUCCESS',transaction_id='123456789'))
            if request.method=='POST' and request.full_url.endswith('/v3/profitsharing/orders'):
                payload=json.loads(request.data)
                return self.signed_response(dict(sub_mchid=payload['sub_mchid'],out_order_no=payload['out_order_no'],
                    transaction_id=payload['transaction_id'],state='FINISHED',receivers=[
                        dict(type=r['type'],account=r['account'],amount=r['amount'],result='SUCCESS') for r in payload['receivers']]))
            raise AssertionError('Unexpected synthetic provider request')
        self.reader._fetch=Mock(side_effect=provider)
        return self.finance('split_by_rule',dict(reference='basket',request_id='split1'))
    def test_order_attribution_is_frozen_and_report_denies_foreign_community_admin(self):
        self.basket();self.call('leave',dict(community_id=self.cid,kind='CUSTOMER'),workspace='customer')
        records=self.call('community_orders',dict(community_id=self.cid,after_id=''))['records']
        self.assertEqual([r['reference'] for r in records],['basket']);self.assertNotIn('user_id',records[0])
        with self.assertRaises(PermissionError):self.call('community_orders',dict(community_id=self.cid,after_id=''),workspace='other',web=self.reviewer)
    def test_receiver_binding_is_owner_only_and_rule_snapshot_keeps_old_mapping(self):
        self.basket()
        with self.assertRaises(PermissionError):self.call('community_receiver_bind',dict(community_id=self.cid,provider_workspace='finance',receiver_id='comm',expected_version=0))
        self.call('community_receiver_bind',dict(community_id=self.cid,provider_workspace='finance',receiver_id='comm',expected_version=0),workspace='platform')
        self.finance('rule_create',dict(rule_id='rule',version=1,shares_bps=dict(comm=1000),description='community',unfreeze_unsplit=True))
        self.finance('rule_activate',dict(rule_id='rule',version=1,expected_revision=0))
        snapshot=self.finance('rule_freeze',dict(reference='basket'))
        self.assertEqual(snapshot['receiver_communities']['comm']['community_id'],self.cid)
        key=hashlib.sha256(canonical([DEMO_SCOPE,'comm'])).hexdigest()
        with self.c.tx():self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_RECEIVER_BINDING' AND subject_idx=?",(key,))
        self.assertEqual(self.finance('rule_snapshot',dict(reference='basket'))['receiver_communities']['comm']['community_id'],self.cid)
        self.complete_split()
        report=self.call('community_earnings',dict(community_id=self.cid,after_id=''))
        self.assertEqual((report['page_gross_minor'],report['page_net_minor']),(10,10));self.assertEqual(report['finance_status'],'UNCONFIRMED')
