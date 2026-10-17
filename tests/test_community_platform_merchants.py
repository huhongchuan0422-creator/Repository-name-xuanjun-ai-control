"""Lifecycle blocks new trading without blocking existing-order recovery."""
import unittest
from unittest.mock import Mock
import test_community_reports as fixtures
import test_community_mini_payments as payments
from scripts.community_platform_merchants import assert_trading,merchant_key
from scripts.pr122_customer_core import canonical

class PlatformMerchantJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):self.fx=fixtures.CommunityReportJourney();self.fx.setUp()
    def tearDown(self):self.fx.tearDown()
    def call(self,op,p,workspace='platform',web=None):return self.fx.call(op,p,workspace,web)
    def state(self,status,version):return self.call('platform_merchant_state',dict(merchant_workspace='merchant',status=status,expected_version=version,reason='Owner lifecycle fixture'))
    def test_pause_cas_purchase_and_owned_order_read_recovery(self):
        basket=self.fx.basket();self.state('PAUSED',0)
        with self.assertRaises(PermissionError):self.fx.commerce.consumer(self.fx.token,'shop1','purchase',dict(reference='new',lines=[dict(item_id='sample_item',quantity=1,revision=2)]))
        self.assertEqual(self.fx.commerce.consumer(self.fx.token,'shop1','purchase_read',dict(reference='basket'))['reference'],'basket')
        with self.assertRaises(ValueError):self.state('ACTIVE',0)
        self.state('ACTIVE',1)
        assert_trading(self.fx.c,self.fx.ops.grants['merchant']['scope'])
        self.assertEqual(self.fx.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_MERCHANT_LIFECYCLE_HISTORY'").fetchone()[0],2)
    def test_reviewer_cannot_change_and_consumer_cannot_list(self):
        with self.assertRaises(PermissionError):self.call('platform_merchant_state',dict(merchant_workspace='merchant',status='DISABLED',expected_version=0,reason='blocked'),workspace='reviewer',web=self.fx.reviewer)
        with self.assertRaises(PermissionError):self.call('platform_merchants',dict(after_workspace=''),workspace='customer')
        report=self.call('platform_merchants',dict(after_workspace=''))
        self.assertEqual([r['workspace'] for r in report['records']],['merchant']);self.assertNotIn('contact',report['records'][0])
        with self.assertRaises(PermissionError):self.call('platform_merchant_state',dict(merchant_workspace='foreign',status='DISABLED',expected_version=0,reason='denied'))

class SuspendedPaymentJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):payments.MiniPaymentJourney.setUpClass()
    def test_prepare_blocked_query_remains_available(self):
        fx=payments.MiniPaymentJourney();fx.setUp()
        try:
            identity=fx.fx.stage.api.bindings[fx.fx.stage.customer];key=merchant_key(identity);c=fx.fx.center
            with c.tx():c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',('COMMUNITY_MERCHANT_LIFECYCLE',key,fx.fx.uid1,'project1',c.encrypt(canonical(dict(scope=identity,status='DISABLED')),'community-merchant-lifecycle:'+key)))
            fx.reader._fetch=Mock(return_value=fx.paid())
            with self.assertRaises(PermissionError):fx.call('prepare')
            fx.reader._fetch.assert_not_called()
            self.assertEqual(fx.call('query')['provider_state'],'SUCCESS')
        finally:fx.tearDown()
