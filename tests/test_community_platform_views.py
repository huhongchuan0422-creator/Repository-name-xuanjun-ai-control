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
