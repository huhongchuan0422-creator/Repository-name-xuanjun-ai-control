"""Composition tests over original durable Stage5 stores, not a second ledger."""
import os
import sqlite3
import tempfile
import time
import unittest
from scripts.community_stage_runtime import StageRuntime
from scripts.community_demo_api import DemoService
from scripts.community_demo_bootstrap import fixture_stores, DEMO_SCOPE
from scripts.community_order_store import connect, create_order
from scripts.community_refund_preview_store import open_refund_store
from scripts.community_saas_phase2 import Principal, OfflineSaas
from scripts.community_saas_modules import connect as modules
from scripts.community_saas_offer_catalog import install as offers
from scripts.community_saas_order_preparation import install, install_lifecycle
from scripts.community_saas_offline_handoff import install_reviews
from scripts.community_local_admin import LocalAdminPolicy

class RuntimeJourney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.order_path = os.path.join(self.tmp.name, 'orders.sqlite')
        self.o = connect(self.order_path)
        self.m, self.a, self.now = fixture_stores()
        self.r = open_refund_store(os.path.join(self.tmp.name, 'refunds.sqlite'))
        self.q = modules(); offers(self.q)
        self.s = sqlite3.connect(':memory:'); install(self.s); install_lifecycle(self.s); install_reviews(self.s)
        self.customer = Principal('tenant1', 'CUSTOMER')
        self.merchant = Principal('tenant1', 'MERCHANT_ADMIN')
        self.owner = Principal('tenant1', 'PLATFORM_OWNER')
        self.other = Principal('tenant2', 'CUSTOMER')
        self.policy = LocalAdminPolicy('m'*32, 'p'*32, DEMO_SCOPE)
        self.demo = DemoService(self.o, self.m, self.a, self.now, self.r, b'k'*32, self.policy)
        bindings = {p: DEMO_SCOPE for p in (self.customer, self.merchant, self.owner)}
        bindings[self.other] = dict(DEMO_SCOPE, tenant_id='tenant2')
        self.api = StageRuntime(self.demo, OfflineSaas(self.q, self.s, self.q), bindings, lambda:self.now)
    def tearDown(self):
        for c in (self.o, self.m, self.a, self.r, self.q, self.s): c.close()
        self.tmp.cleanup()
    def call(self, op, params=None, principal=None):
        return self.api.dispatch(principal or self.customer, 'community.'+op, params or {}, 0)
    def checkout(self):
        token = self.call('qr', {'context':'mini'})['token']
        return self.call('checkout', {'context':'mini', 'token':token, 'reference':'order1', 'amount_minor':101})
    def test_full_journey_refund_split_reconciliation_and_saas(self):
        self.assertIsNotNone(self.call('storefront')['ads']['AD_SLOT_PAYMENT_AMOUNT'])
        self.checkout()
        self.assertIsNone(self.call('receipt', {'reference':'order1'})['ads']['AD_SLOT_PAYMENT_SUCCESS'])
        self.api.simulate_from_operator(self.owner, 'order1', 'event1', 'SUCCESS', 'tx1')
        receipt = self.call('receipt', {'reference':'order1'})
        self.assertEqual(receipt['payment_state'], 'MOCK_PAID_SIMULATED')
        self.assertIsNone(receipt['ads']['AD_SLOT_PAYMENT_SUCCESS'])
        self.assertFalse(receipt['provider_payment_verified'])
        self.assertFalse(receipt['financial_receipt_issued'])
        p = {'reference':'order1','event_id':'refund1','amount_minor':11}
        self.call('refund_record', p, self.merchant)
        duplicate = self.call('refund_record', p, self.merchant)
        self.assertFalse(duplicate['recorded'])
        split = self.call('split_preview', {'reference':'order1','shares_bps':{'merchant':8000,'platform':2000}}, self.merchant)
        self.assertEqual(sum(split['allocations_minor'].values())+split['refund_preview_minor'],101)
        self.assertEqual(self.call('reconciliation', principal=self.owner)['simulated_net_minor'],90)
        self.assertEqual(len(self.call('orders', principal=self.merchant)['orders']),1)
        self.assertTrue(self.api.dispatch(self.customer,'catalog',{},0)['framework_free'])
        self.assertFalse(self.api.dispatch(self.customer,'entitlement',{'module_id':'advertising'},0)['active'])
    def test_success_placement_requires_provider_projection(self):
        from scripts.community_order_provider_projection import project_verified_query
        from scripts.community_provider_reference import provider_order_reference
        self.checkout()
        ref = provider_order_reference('1234567890', DEMO_SCOPE, 'order1')
        expected = dict(sp_mchid='1234567890', sub_mchid='1234567891',
                        sp_appid='wx1234567890abcdef', out_trade_no=ref,
                        amount_minor=101, currency='CNY')
        observation = dict(source='SIGNED_PROVIDER_ORDER_QUERY',
                           signature_key_id='PUB_KEY_ID_fixture',
                           out_trade_no=ref, amount_minor=101, currency='CNY',
                           provider_state='SUCCESS', transaction_id='420000000000000001',
                           body_sha256='a'*64)
        project_verified_query(self.o, DEMO_SCOPE, 'order1', expected,
                               observation, self.now, 'PUB_KEY_ID_fixture')
        receipt = self.call('receipt', {'reference':'order1'})
        self.assertTrue(receipt['provider_payment_verified'])
        self.assertIsNotNone(receipt['ads']['AD_SLOT_PAYMENT_SUCCESS'])
        self.assertFalse(receipt['financial_receipt_issued'])

    def test_scope_injection_and_forged_payment_rejected(self):
        for op, body in [('storefront', {'tenant_id':'tenant2'}), ('receipt', {'reference':'order1','paid':True}), ('simulate', {})]:
            with self.assertRaises(ValueError): self.call(op,body)
    def test_customer_no_financial_admin(self):
        for op in ('orders','summary','reconciliation','ads'):
            with self.assertRaises(PermissionError): self.call(op)
    def test_unknown_and_copied_principal_rejected(self):
        with self.assertRaises(PermissionError): self.call('storefront',principal=Principal('tenant1','CUSTOMER'))
        with self.assertRaises(PermissionError): self.api.dispatch({'role':'PLATFORM_OWNER'},'catalog',{},0)
    def test_cross_tenant_receipt_denied(self):
        self.checkout()
        with self.assertRaisesRegex(ValueError,'ORDER_NOT_FOUND'):
            self.call('receipt',{'reference':'order1'},self.other)
    def test_ad_expiry_uses_server_clock(self):
        self.checkout()
        self.api.simulate_from_operator(self.owner,'order1','event1','SUCCESS','tx1')
        self.now += 90000
        self.assertIsNone(self.call('receipt',{'reference':'order1'})['ads']['AD_SLOT_PAYMENT_SUCCESS'])
    def test_ad_failure_does_not_break_receipt(self):
        self.checkout()
        self.api.simulate_from_operator(self.owner,'order1','event1','SUCCESS','tx1')
        self.a.execute('DROP TABLE campaigns')
        self.assertEqual(self.call('receipt',{'reference':'order1'})['order']['amount_minor'],101)
    def test_operator_hook_restricted_and_duplicate(self):
        self.checkout()
        with self.assertRaises(PermissionError): self.api.simulate_from_operator(self.customer,'order1','event1','SUCCESS','tx1')
        self.api.simulate_from_operator(self.owner,'order1','event1','SUCCESS','tx1')
        self.assertTrue(self.api.simulate_from_operator(self.owner,'order1','event1','SUCCESS','tx1')['duplicate'])
    def test_reopen_reads_same_order_without_recreation(self):
        self.checkout()
        self.api.simulate_from_operator(self.owner,'order1','event1','SUCCESS','tx1')
        self.o.close(); self.o=connect(self.order_path); self.demo.db=self.o
        self.assertEqual(self.call('receipt',{'reference':'order1'})['order']['amount_minor'],101)
        self.assertEqual(self.o.execute('SELECT count(*) FROM order_events').fetchone()[0],1)
    def test_no_cross_store_merchant_admin(self):
        principal=Principal('tenant1','MERCHANT_ADMIN')
        self.api.bindings[principal]=dict(DEMO_SCOPE,merchant_id='merchant2')
        with self.assertRaises(PermissionError):
            self.call('profile',{'record':{},'expected_version':1},principal)
    def test_server_time_overrides_client_for_phase2(self):
        from unittest.mock import Mock
        self.api.saas=Mock()
        self.api.dispatch(self.customer,'catalog',{},1)
        self.api.saas.dispatch.assert_called_once_with(self.customer,'catalog',{},self.now)

if __name__ == '__main__': unittest.main()
