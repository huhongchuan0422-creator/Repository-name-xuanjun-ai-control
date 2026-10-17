"""Synthetic bill integrity and scoped reconciliation; no live provider calls."""
import datetime as dt
import hashlib
import unittest
from unittest.mock import Mock
import test_community_reports as fixtures
from scripts.community_provider_bills import ProviderBills,minor,parse
from scripts.community_provider_reference import provider_order_reference

class BillJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):
        self.fx=fixtures.CommunityReportJourney();self.fx.setUp();self.bills=ProviderBills(self.fx.actions)
        self.date=(dt.datetime.fromtimestamp(self.fx.c.now(),dt.timezone(dt.timedelta(hours=8))).date()-dt.timedelta(days=1)).isoformat()
    def tearDown(self):self.fx.tearDown()
    def call(self,op,**extra):
        return self.bills.dispatch(self.fx.web['token'],self.fx.web['csrf'],'finance',op,dict(kind='TRADE',bill_date=self.date,**extra))
    def download(self,raw):
        self.fx.actions._call=Mock(return_value=(dict(hash_type='SHA1',hash_value=hashlib.sha1(raw).hexdigest(),download_url='https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=fixture'),'a'*64))
        self.bills._download=Mock(return_value=raw)
    def test_signed_ticket_hash_private_rows_and_no_automatic_finance(self):
        self.download('商户订单号,微信订单号,交易状态,订单金额,用户标识\nx,1,SUCCESS,1.00,private-openid\n'.encode())
        r=self.call('bill_fetch');self.assertEqual(r['integrity'],'SIGNED_TICKET_HASH_VERIFIED')
        self.assertNotIn('用户标识',self.call('bill_rows',offset=0)['records'][0])
        r=self.call('bill_reconcile');self.assertEqual(r['status'],'EXCEPTION');self.assertFalse(r['funds_retry_authorized']);self.assertEqual(r['finance_status'],'UNCONFIRMED')
    def test_hash_mismatch_never_persists(self):
        self.download(b'a,b\nx,y\n');self.bills._download.return_value=b'a,b\nx,z\n'
        with self.assertRaises(PermissionError):self.call('bill_fetch')
        self.assertEqual(self.fx.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_PROVIDER_BILL'").fetchone()[0],0)
    def test_auth_and_schema_fail_closed(self):
        with self.assertRaises(PermissionError):self.bills.dispatch(self.fx.web['token'],'','finance','bill_fetch',dict(kind='TRADE',bill_date=self.date))
        self.download(b'unknown,columns\na,b\n');self.call('bill_fetch')
        self.assertEqual(self.call('bill_reconcile')['status'],'UNKNOWN_SCHEMA')
    def test_fixed_download_origin_rejects_redirect_targets_before_io(self):
        for url in ['https://evil.invalid/v3/bill/downloadurl?token=x','http://api.mch.weixin.qq.com/v3/bill/downloadurl?token=x','https://api.mch.weixin.qq.com@evil.invalid/v3/bill/downloadurl?token=x','https://api.mch.weixin.qq.com/v3/other?token=x']:
            with self.assertRaises(PermissionError):self.bills._download(url)
    def test_exact_minor_and_bounded_csv(self):
        self.assertEqual(minor('`0.29'),29)
        for value in ['0.001','NaN','1e2','-1','1,000']:
            with self.assertRaises(ValueError):minor(value)
        self.assertEqual(parse(b'a,b\n`x,`y\n')[1],[dict(a='x',b='y')])
        with self.assertRaises(ValueError):parse(b'a,a\nx,y\n')
        with self.assertRaises(ValueError):parse(b'a,b\nx,y,z\n')
    def test_receiver_detail_layout_not_treated_as_aggregate_match(self):
        g,_=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        bill=dict(kind='SPLIT',columns=['商户分账单号','分账金额','分账结果','接收方账号'],rows=[],body_sha256='a'*64)
        self.assertEqual(self.bills.reconcile(g,bill)['status'],'UNKNOWN_SCHEMA')
