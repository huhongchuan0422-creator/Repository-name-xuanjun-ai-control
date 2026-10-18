"""Lifecycle blocks new trading without blocking existing-order recovery."""
import unittest
from unittest.mock import Mock
import test_community_reports as fixtures
import test_community_mini_payments as payments
from scripts.community_platform_merchants import assert_trading,merchant_key
from scripts.pr122_customer_core import canonical
from scripts.community_saas_phase2 import Principal
from scripts.community_center_operations import CenterOperations
from scripts.community_demo_bootstrap import DEMO_SCOPE

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

    def revoked_mapping(self,workspace='revoked'):
        principal=Principal('tenant1','MERCHANT_ADMIN')
        self.fx.fx.stage.api.bindings[principal]=dict(DEMO_SCOPE,store_id='private-revoked-store')
        grant=dict(user_id=self.fx.fx.uid2,project='project1',project_roles=['EDITOR'],principal=principal)
        self.fx.ops.grants[workspace]=CenterOperations(self.fx.c,self.fx.fx.stage.api,{workspace:grant}).grants[workspace]
        self.fx.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid2,))
        return self.fx.ops.grants[workspace]

    def test_revoked_merchant_does_not_block_live_platform_owner_or_leak_private_scope(self):
        self.revoked_mapping()
        listing=self.call('platform_merchants',dict(after_workspace=''))
        self.assertEqual([r['workspace'] for r in listing['records']],['merchant'])
        self.assertIs(listing['coverage_complete'],False)
        self.assertEqual(listing['unavailable_mapping_count'],1)
        self.assertEqual(listing['unavailable_mappings'],[dict(workspace='revoked',status='UNAVAILABLE')])
        self.assertNotIn('private-revoked-store',str(listing))
        self.assertNotIn(self.fx.fx.uid2,str(listing))
        self.assertEqual(self.state('PAUSED',0)['status'],'PAUSED')
        with self.assertRaises(PermissionError):self.call('platform_merchant_state',dict(merchant_workspace='revoked',status='ACTIVE',expected_version=0,reason='cannot restore revoked grant'))

    def test_unavailable_mapping_pages_advance_even_when_no_accessible_merchant_on_page(self):
        grant=self.revoked_mapping('a_dead_000')
        for index in range(1,61):self.fx.ops.grants['a_dead_'+str(index).zfill(3)]=dict(grant)
        first=self.call('platform_merchants',dict(after_workspace=''))
        self.assertEqual(first['records'],[]);self.assertEqual(len(first['unavailable_mappings']),50)
        self.assertIs(first['has_more'],True);self.assertEqual(first['next_cursor'],'a_dead_049')
        second=self.call('platform_merchants',dict(after_workspace=first['next_cursor']))
        self.assertEqual([r['workspace'] for r in second['records']],['merchant'])
        self.assertEqual(len(second['unavailable_mappings']),11);self.assertIs(second['has_more'],False)
        self.assertIs(second['coverage_complete'],False);self.assertEqual(second['unavailable_mapping_count'],61)

    def test_platform_owner_revocation_still_denies_every_merchant_view(self):
        self.revoked_mapping()
        self.fx.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid1,))
        with self.assertRaises(PermissionError):self.call('platform_merchants',dict(after_workspace=''))

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
