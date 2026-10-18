"""Owned cancellation, unknown-close recovery and exactly-once stock restoration."""
import unittest
from unittest.mock import Mock
import test_community_mini_payments as fixtures
from scripts.community_order_store import state
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.community_center_operations import CenterOperations
from scripts.community_commerce import Commerce


class CancellationJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.MiniPaymentJourney.setUpClass()
    def setUp(self):
        self.p=fixtures.MiniPaymentJourney();self.p.setUp();self.fx=self.p.fx
    def tearDown(self):self.p.tearDown()
    def cancel(self):return self.p.payments.dispatch(self.p.token,dict(scene='shop1',operation='cancel',reference='order1'))
    def test_never_submitted_order_cancels_without_network_and_cannot_pay(self):
        self.p.reader._fetch=Mock(side_effect=AssertionError('NO_NETWORK'))
        self.assertEqual(self.cancel()['order_state'],'CANCELLED')
        self.assertEqual(self.cancel()['order_state'],'CANCELLED')
        self.p.reader._fetch.assert_not_called()
        with self.assertRaises(PermissionError):self.p.call('prepare')
    def test_unknown_close_is_consumed_then_only_signed_query_recovers(self):
        self.p.reader._fetch=Mock(return_value=self.p.signed(dict(prepay_id='fixture')))
        self.p.call('prepare')
        self.p.reader._fetch=Mock(side_effect=TimeoutError())
        with self.assertRaises(Exception):self.cancel()
        self.assertEqual(self.p.reader._fetch.call_count,2)
        closed=dict(sp_mchid='1234567890',sub_mchid='1234567891',sp_appid=self.fx.identity.appid,out_trade_no='provider_order1',amount=dict(total=101,currency='CNY'),trade_state='CLOSED')
        self.p.reader._fetch=Mock(return_value=self.p.signed(closed))
        self.assertEqual(self.cancel()['order_state'],'CANCELLED')
        self.p.reader._fetch.assert_called_once()
        self.assertEqual(self.p.reader._fetch.call_args.args[0].method,'GET')
    def test_payment_winning_race_never_releases_or_cancels_paid_order(self):
        self.p.reader._fetch=Mock(return_value=self.p.signed(dict(prepay_id='fixture')));self.p.call('prepare')
        self.p.reader._fetch=Mock(side_effect=[TimeoutError(),self.p.paid()])
        result=self.cancel();self.assertEqual(result['order_state'],'SUCCESS')
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'order1')['state'],'SUCCESS')
        with self.assertRaises(PermissionError):self.cancel()
    def test_stock_release_is_exactly_once_and_keeps_price_revision(self):
        web=self.fx.center.login('one@example.org','FixturePassword123!')
        ops=CenterOperations(self.fx.center,self.fx.stage.api,{'merchant':dict(user_id=self.fx.uid1,project='project1',project_roles=['OWNER'],principal=self.fx.stage.merchant)})
        commerce=Commerce(ops,self.fx.identity);self.p.payments.commerce=commerce
        commerce.dispatch(web['token'],web['csrf'],dict(workspace='merchant',operation='price_set',params=dict(item_id='sample_item',expected_revision=0,unit_minor=101,stock=10,enabled=True)))
        commerce.consumer(self.p.token,'shop1','purchase',dict(reference='basket',lines=[dict(item_id='sample_item',quantity=1,revision=1)]))
        self.p.prepay.bindings['basket']=dict(self.p.binding,out_trade_no='provider_basket')
        for _ in range(2):self.p.payments.dispatch(self.p.token,dict(scene='shop1',operation='cancel',reference='basket'))
        price=commerce._read(DEMO_SCOPE,'project1','PRODUCT','sample_item')
        self.assertEqual((price['stock'],price['revision']),(10,3))
        self.assertTrue(commerce._read(DEMO_SCOPE,'project1','ORDER','basket')['stock_released'])
