"""Synthetic bill integrity and scoped reconciliation; no live provider calls."""
import datetime as dt
import hashlib
import unittest
from unittest.mock import Mock
import test_community_reports as fixtures
from scripts.community_provider_bills import ProviderBills,minor,parse
from scripts.community_provider_reference import provider_order_reference

class FinanceRefundEvidenceValidation(unittest.TestCase):
    def test_refund_total_rejects_boolean_negative_and_string_amounts(self):
        from scripts.community_financial_views import verified_refund_total
        from scripts.pr122_customer_core import canonical
        class DB:
            def __init__(self,event):self.event=event
            def execute(self,sql,args):
                return [(canonical(self.event).decode(),)]
        identity=dict(tenant_id='tenant1',merchant_id='merchant1',store_id='store1')
        for amount in (True,-1,0,'100',1.0):
            db=DB(dict(source='WECHAT_SIGNED_REFUND_RESULT',refund_minor=amount))
            with self.assertRaisesRegex(ValueError,'INVALID_SIGNED_REFUND_LEDGER_AMOUNT'):
                verified_refund_total(db,identity,'order1')
        self.assertEqual(verified_refund_total(DB(dict(source='WECHAT_SIGNED_REFUND_RESULT',
                         refund_minor=20)),identity,'order1'),20)
        self.assertEqual(verified_refund_total(DB(dict(source='OTHER',refund_minor=-10)),
                         identity,'order1'),0)

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
    def test_reverse_reconciliation_uses_signed_payment_date_not_observation_date(self):
        from scripts.community_order_provider_projection import project_verified_query
        from scripts.community_demo_bootstrap import DEMO_SCOPE
        self.fx.basket()
        g,policy=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        expected=dict(sp_mchid=self.fx.reader._mchid,sub_mchid=policy['sub_mchid'],out_trade_no=provider_order_reference(self.fx.reader._mchid,DEMO_SCOPE,'basket'),amount_minor=101,currency='CNY')
        observation=dict(source='SIGNED_PROVIDER_ORDER_QUERY',signature_key_id=self.fx.reader._kid,out_trade_no=expected['out_trade_no'],amount_minor=101,currency='CNY',provider_state='SUCCESS',transaction_id='123456789',body_sha256='a'*64)
        db=self.fx.fx.stage.demo.db
        project_verified_query(db,DEMO_SCOPE,'basket',expected,observation,self.fx.c.now(),self.fx.reader._kid)
        bill=dict(kind='TRADE',bill_date=self.date,sub_mchid=policy['sub_mchid'],columns=['商户订单号','微信订单号','交易状态','订单金额'],rows=[],body_sha256='b'*64)
        self.assertEqual(self.bills.reconcile(g,bill)['undated_local_payments'],1)
        paid_at=int(dt.datetime.fromisoformat(self.date+'T12:00:00+08:00').timestamp())
        observation['paid_at']=paid_at
        project_verified_query(db,DEMO_SCOPE,'basket',expected,observation,self.fx.c.now(),self.fx.reader._kid)
        project_verified_query(db,DEMO_SCOPE,'basket',expected,observation,self.fx.c.now(),self.fx.reader._kid)
        result=self.bills.reconcile(g,bill)
        self.assertEqual(result['missing_provider_rows'],['basket']);self.assertEqual(result['status'],'EXCEPTION')
        self.assertEqual(result['undated_local_payments'],0)
        observation['paid_at']+=1
        with self.assertRaises(ValueError):project_verified_query(db,DEMO_SCOPE,'basket',expected,observation,self.fx.c.now(),self.fx.reader._kid)
        bill['rows']=[dict(zip(bill['columns'],[expected['out_trade_no'],'123456789','SUCCESS','1.01']))]
        self.assertEqual(self.bills.reconcile(g,bill)['status'],'BILL_ROWS_MATCH')
        bill['columns'].append('特约商户号')
        bill['rows'][0]['特约商户号']=''
        self.assertEqual(self.bills.reconcile(g,bill)['exceptions'][0]['reason'],'BILL_SUBMERCHANT_MISMATCH')
        bill['rows'][0]['特约商户号']=policy['sub_mchid']
        self.assertEqual(self.bills.reconcile(g,bill)['status'],'BILL_ROWS_MATCH')
        bill['rows']*=2
        self.assertEqual(self.bills.reconcile(g,bill)['exceptions'][0]['reason'],'DUPLICATE_PROVIDER_ROW')
    def test_signed_time_has_timezone_bounds_and_no_clock_substitution(self):
        from scripts.community_wechat_sp_verification import signed_success_time
        now=self.fx.c.now()
        self.assertIsNone(signed_success_time(None,now))
        self.assertEqual(signed_success_time('2020-01-01T08:00:00+08:00',now),1577836800)
        for value in ['2020-01-01T00:00:00','2020-02-31T00:00:00Z','2099-01-01T00:00:00Z',0]:
            with self.assertRaises(ValueError):signed_success_time(value,now)
    def test_receiver_detail_layout_not_treated_as_aggregate_match(self):
        g,_=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        bill=dict(kind='SPLIT',columns=['商户分账单号','分账金额','分账结果','接收方账号'],rows=[],body_sha256='a'*64)
        self.assertEqual(self.bills.reconcile(g,bill)['status'],'UNKNOWN_SCHEMA')

    def test_receiver_account_variants_never_become_aggregate_matches(self):
        g,_=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        for column in ('收款方账号','分账接收方账号','接收方账号','收款商户号'):
            bill=dict(kind='SPLIT',columns=['商户分账单号','分账金额','分账结果',column],
                rows=[{'商户分账单号':'unknown','分账金额':'1.00','分账结果':'SUCCESS',column:'private'}],
                body_sha256='a'*64)
            self.assertEqual(self.bills.reconcile(g,bill)['status'],'UNKNOWN_SCHEMA')

    def test_split_bill_optional_signed_identifiers_must_match_original_intent(self):
        from scripts.pr122_customer_core import canonical
        from scripts.community_demo_bootstrap import DEMO_SCOPE
        g,policy=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        action=dict(kind='SPLIT',scope=DEMO_SCOPE,reference='basket',provider_reference='ps_bill_fixture',
                    transaction_id='420000000000001234',result=dict(status='FINISHED',
                    receivers=[dict(receiver_id='comm',amount_minor=10,result='SUCCESS')]))
        key='f'*64
        with self.fx.c.tx():
            self.fx.c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",
                (key,self.fx.fx.uid1,'project1',self.fx.c.encrypt(canonical(action),'provider-action:'+key)))
        columns=['商户分账单号','分账金额','分账结果','微信订单号','特约商户号']
        values=['ps_bill_fixture','0.10','SUCCESS','420000000000001234',policy['sub_mchid']]
        bill=dict(kind='SPLIT',columns=columns,rows=[dict(zip(columns,values))],
                  sub_mchid=policy['sub_mchid'],body_sha256='d'*64)
        self.assertEqual(self.bills.reconcile(g,bill)['status'],'BILL_ROWS_MATCH')
        bill['rows']=[dict(zip(columns,values[:3]+['999999999999999999',values[4]]))]
        result=self.bills.reconcile(g,bill)
        self.assertEqual(result['status'],'EXCEPTION')
        self.assertEqual(result['exceptions'][0]['reason'],'SPLIT_TRANSACTION_MISMATCH')
        bill['rows']=[dict(zip(columns,values[:4]+['9999999999']))]
        result=self.bills.reconcile(g,bill)
        self.assertEqual(result['exceptions'][0]['reason'],'BILL_SUBMERCHANT_MISMATCH')

        bill['columns'].append('币种')
        bill['rows']=[dict(zip(columns,values),币种='USD')]
        self.assertEqual(self.bills.reconcile(g,bill)['exceptions'][0]['reason'],'UNSUPPORTED_BILL_CURRENCY')
        bill['rows']=[dict(zip(columns,values),币种='')]
        self.assertEqual(self.bills.reconcile(g,bill)['exceptions'][0]['reason'],'UNSUPPORTED_BILL_CURRENCY')
        bill['columns'].append('货币种类')
        bill['rows']=[dict(zip(columns,values),币种='CNY',货币种类='USD')]
        self.assertEqual(self.bills.reconcile(g,bill)['exceptions'][0]['reason'],'UNSUPPORTED_BILL_CURRENCY')
        bill['columns'].remove('货币种类')
        bill['columns'].remove('币种')

        bill['rows']=[dict(zip(columns,values[:3]+['',values[4]]))]
        self.assertEqual(self.bills.reconcile(g,bill)['exceptions'][0]['reason'],'SPLIT_TRANSACTION_MISMATCH')
        bill['rows']=[dict(zip(columns,values[:4]+['']))]
        self.assertEqual(self.bills.reconcile(g,bill)['exceptions'][0]['reason'],'BILL_SUBMERCHANT_MISMATCH')
