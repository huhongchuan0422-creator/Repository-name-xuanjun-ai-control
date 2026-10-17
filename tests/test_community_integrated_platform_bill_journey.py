"""Integrated original Center / community / signed provider evidence / platform report.

All provider observations are synthetic, never live money or Finance settlement.
"""
import datetime as dt
import hashlib
import unittest
from unittest.mock import Mock
import test_community_reports as fixtures
from scripts.community_order_provider_projection import project_verified_query
from scripts.community_provider_reference import provider_order_reference
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.community_provider_bills import ProviderBills


class IntegratedPlatformLedgerReadJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.CommunityReportJourney.setUpClass()

    def setUp(self):
        self.fx=fixtures.CommunityReportJourney()
        self.fx.setUp()

    def tearDown(self):
        self.fx.tearDown()

    def test_community_attributed_paid_order_through_official_bill_and_platform(self):
        self.fx.basket()
        g,policy=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        trade=provider_order_reference(self.fx.reader._mchid,DEMO_SCOPE,'basket')
        expected=dict(sp_mchid=self.fx.reader._mchid,sub_mchid=policy['sub_mchid'],
                      sp_appid=policy['sp_appid'],out_trade_no=trade,amount_minor=101,
                      currency='CNY')
        date=(dt.datetime.fromtimestamp(self.fx.c.now(),
              dt.timezone(dt.timedelta(hours=8))).date()-dt.timedelta(days=1))
        paid_at=int(dt.datetime.fromisoformat(date.isoformat()+'T12:00:00+08:00').timestamp())
        evidence=dict(source='SIGNED_PROVIDER_ORDER_QUERY',signature_key_id=self.fx.reader._kid,
                      out_trade_no=trade,amount_minor=101,currency='CNY',
                      provider_state='SUCCESS',transaction_id='420000000000001234',
                      body_sha256='a'*64,paid_at=paid_at)
        db=self.fx.fx.stage.demo.db
        project_verified_query(db,DEMO_SCOPE,'basket',expected,evidence,self.fx.c.now(),
                               self.fx.reader._kid)
        platform=self.fx.call('platform_overview',{},workspace='platform')
        self.assertEqual(platform['signed_paid_order_count'],1)
        self.assertEqual(platform['signed_gross_payment_minor'],101)
        self.assertEqual(platform['signed_net_payment_minor'],101)
        self.assertEqual(platform['finance_status'],'UNCONFIRMED')
        order=self.fx.call('community_orders',dict(community_id=self.fx.cid,after_id=''))
        self.assertEqual([v['reference'] for v in order['records']],['basket'])
        self.assertNotIn('user_id',order['records'][0])
        rows=('商户订单号,微信订单号,交易状态,订单金额,特约商户号,币种\n'
              +trade+',420000000000001234,SUCCESS,1.01,'
              +policy['sub_mchid']+',CNY\n').encode()
        bills=ProviderBills(self.fx.actions)
        bills._download=Mock(return_value=rows)
        self.fx.actions._call=Mock(return_value=(
            dict(hash_type='SHA1',hash_value=hashlib.sha1(rows).hexdigest(),
                 download_url='https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=fixture'),
            'b'*64))
        params=dict(kind='TRADE',bill_date=date.isoformat())
        receipt=bills.dispatch(self.fx.web['token'],self.fx.web['csrf'],'finance',
                               'bill_fetch',params)
        self.assertEqual(receipt['integrity'],'SIGNED_TICKET_HASH_VERIFIED')
        outcome=bills.dispatch(self.fx.web['token'],self.fx.web['csrf'],'finance',
                               'bill_reconcile',params)
        self.assertEqual(outcome['status'],'BILL_ROWS_MATCH')
        self.assertEqual(outcome['reverse_coverage'],'COMPLETE_FOR_SIGNED_DATED_LOCAL_PAYMENTS')
        self.assertEqual(outcome['finance_status'],'UNCONFIRMED')


if __name__=='__main__':
    unittest.main()
