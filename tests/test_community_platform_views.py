"""Platform reads are original-project scoped, paginated and evidence-labelled."""
import unittest
import test_community_reports as fixtures
from scripts.community_order_store import create_order

class PlatformViewJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):self.fx=fixtures.CommunityReportJourney();self.fx.setUp()
    def tearDown(self):self.fx.tearDown()
    def call(self,op,p,workspace='platform'):return self.fx.call(op,p,workspace)
    def test_foreign_store_excluded_and_unverified_paid_state_not_money_receipt(self):
        self.fx.basket();db=self.fx.fx.stage.demo.db
        foreign=dict(tenant_id='foreign',merchant_id='foreign',store_id='foreign')
        create_order(db,foreign,'foreign-order',999)
        db.execute("UPDATE orders SET state='SUCCESS' WHERE reference='basket'");db.commit()
        report=self.call('platform_overview',{})
        self.assertEqual(report['order_counts'],dict(SUCCESS=1));self.assertEqual(report['signed_paid_order_count'],0);self.assertEqual(report['signed_net_payment_minor'],0);self.assertEqual(report['unverified_paid_state_count'],1)
        listing=self.call('platform_orders',dict(after_id=0,status='ALL'))
        self.assertEqual([r['reference'] for r in listing['records']],['basket']);self.assertIsNone(listing['records'][0]['payment_evidence'])
    def test_platform_overview_refuses_corrupted_original_payment_evidence(self):
        from scripts.community_order_provider_projection import project_verified_query
        from scripts.community_provider_reference import provider_order_reference
        from scripts.community_demo_bootstrap import DEMO_SCOPE
        self.fx.basket()
        db=self.fx.fx.stage.demo.db
        g,policy=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        expected=dict(sp_mchid=self.fx.reader._mchid,sub_mchid=policy['sub_mchid'],
            sp_appid=policy['sp_appid'],
            out_trade_no=provider_order_reference(self.fx.reader._mchid,DEMO_SCOPE,'basket'),
            amount_minor=101,currency='CNY')
        observation=dict(source='SIGNED_PROVIDER_ORDER_QUERY',signature_key_id=self.fx.reader._kid,
            out_trade_no=expected['out_trade_no'],amount_minor=101,currency='CNY',
            provider_state='SUCCESS',transaction_id='420000000000000001',body_sha256='a'*64)
        project_verified_query(db,DEMO_SCOPE,'basket',expected,observation,self.fx.c.now(),self.fx.reader._kid)
        db.execute("INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)",
            ('bad_evidence',DEMO_SCOPE['tenant_id'],DEMO_SCOPE['merchant_id'],
             DEMO_SCOPE['store_id'],'basket','SUCCESS','SUCCESS','invalid-json'))
        db.commit()
        with self.assertRaisesRegex(ValueError,'UNREADABLE_ORDER_EVIDENCE_RECONCILIATION_DENIED'):
            self.call('platform_overview',{})

    def test_project_users_no_credentials_contact_or_global_search(self):
        fx=self.fx.fx
        other,_=fx.account('unrelated@example.org')
        result=self.call('platform_customers',dict(after_id=''))
        self.assertEqual({r['user_id'] for r in result['records']},{fx.uid1,fx.uid2});self.assertNotIn(other,{r['user_id'] for r in result['records']})
        for row in result['records']:
            for field in ('email','password','openid','contact','salt'):self.assertNotIn(field,row)
        with self.assertRaises(PermissionError):self.call('platform_customers',dict(after_id=''),workspace='customer')
    def test_audit_page_authorization_and_cursor_validation(self):
        self.call('platform_overview',{})
        logs=self.call('platform_audit',dict(after_id=0))
        self.assertTrue(any(r['event']=='PLATFORM_OVERVIEW' for r in logs['records']))
        for op,p in [('platform_audit',dict(after_id=True)),('platform_orders',dict(after_id=-1,status='ALL')),('platform_customers',dict(after_id='../other'))]:
            with self.assertRaises(ValueError):self.call(op,p)

    def test_unrelated_revoked_merchant_does_not_block_project_members_and_audit(self):
        from unittest.mock import patch
        from scripts.community_platform_merchants import PlatformMerchants
        with patch.object(PlatformMerchants,'_targets',side_effect=AssertionError('UNRELATED_MERCHANT_LOOKUP')):
            customers=self.call('platform_customers',dict(after_id=''))
            self.assertEqual(len(customers['records']),2)
            audit=self.call('platform_audit',dict(after_id=0))
            self.assertTrue(audit['records'])

    def test_incomplete_store_coverage_is_explicit_and_never_leaks_revoked_orders(self):
        from scripts.community_saas_phase2 import Principal
        from scripts.community_center_operations import CenterOperations
        from scripts.community_demo_bootstrap import DEMO_SCOPE
        self.fx.basket()
        identity=dict(DEMO_SCOPE,store_id='revoked-private-store')
        principal=Principal('tenant1','MERCHANT_ADMIN');self.fx.fx.stage.api.bindings[principal]=identity
        grant=dict(user_id=self.fx.fx.uid2,project='project1',project_roles=['EDITOR'],principal=principal)
        self.fx.ops.grants['revoked']=CenterOperations(self.fx.c,self.fx.fx.stage.api,{'revoked':grant}).grants['revoked']
        create_order(self.fx.fx.stage.demo.db,identity,'revoked-private-order',777)
        self.fx.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid2,))
        customers=self.call('platform_customers',dict(after_id=''))
        revoked=next(row for row in customers['records'] if row['user_id']==self.fx.fx.uid2)
        self.assertIs(revoked['membership_active'],False)
        self.assertTrue(self.call('platform_audit',dict(after_id=0))['records'])
        for op,p in [('platform_overview',{}),('platform_orders',dict(after_id=0,status='ALL'))]:
            result=self.call(op,p)
            self.assertIs(result['coverage_complete'],False)
            self.assertEqual(result['totals_scope'],'ACCESSIBLE_STORE_SUBTOTAL')
            self.assertEqual(result['unavailable_mapping_count'],1)
            self.assertEqual(result['unavailable_mappings'],[dict(workspace='revoked',status='UNAVAILABLE')])
            self.assertNotIn('revoked-private-store',str(result));self.assertNotIn('revoked-private-order',str(result))
        self.fx.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid1,))
        for op,p in [('platform_customers',dict(after_id='')),('platform_audit',dict(after_id=0)),('platform_overview',{})]:
            with self.assertRaises(PermissionError):self.call(op,p)
