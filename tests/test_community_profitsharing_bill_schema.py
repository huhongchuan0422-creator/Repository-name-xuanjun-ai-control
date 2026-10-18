"""Synthetic official-shaped bills; no merchant data or live provider calls."""
import base64
import csv
import datetime as dt
import hashlib
import io
import json
import re
import unittest
from unittest.mock import Mock, patch
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import test_community_reports as fixtures
import test_community_wechat_sp_readonly as keys
from scripts.community_provider_bills import (
    ProviderBills, SPLIT_COLUMNS, SPLIT_SUMMARY_COLUMNS, SPLIT_SCHEMA, parse, parse_document)
from scripts.pr122_customer_core import canonical


def fixture_rows():
    return [['2026-10-16 12:00:00','synthetic-initiator','synthetic-sender',
             'synthetic-order-'+str(i),'synthetic-provider-'+str(i),
             'synthetic-detail-'+str(i),'synthetic-out-'+str(i),
             '1.00','private-synthetic-receiver-'+str(i),'0.01',kind,'成功','description','']
            for i,kind in enumerate(('分出','解冻','逾期解冻','分账回退'))]


def bill_bytes(rows=None, columns=SPLIT_COLUMNS, summary=None, trailer=True):
    rows=fixture_rows() if rows is None else rows
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(columns)
    for row in rows:writer.writerow(['`'+v for v in row])
    if trailer:
        writer.writerow(SPLIT_SUMMARY_COLUMNS)
        writer.writerow(summary or ['`'+str(len(rows))+'.0','`0.01','`0.0','`0.02','`0.01'])
    return out.getvalue().encode('utf-8-sig')


class OfficialSchemaParser(unittest.TestCase):
    def test_exact_sample_shape_excludes_summary_and_preserves_unknown_semantics(self):
        header,rows,schema=parse_document(bill_bytes())
        self.assertEqual(tuple(header),SPLIT_COLUMNS)
        self.assertEqual(len(rows),4)
        self.assertEqual(schema['id'],SPLIT_SCHEMA)
        self.assertEqual(schema['timezone'],'UNSPECIFIED')
        self.assertEqual(schema['receiver_type'],'UNSPECIFIED')
        self.assertEqual(schema['detail_join'],'UNVERIFIED')
        self.assertEqual(rows[3]['业务类型'],'分账回退')
        self.assertEqual(parse(bill_bytes()),(header,rows))

    def test_empty_bill_requires_zero_summary(self):
        self.assertEqual(parse_document(bill_bytes(rows=[],summary=['0','0','0','0','0']))[2]['summary_count'],0)

    def test_summary_shape_numeric_count_and_complete_trailer_are_required(self):
        for summary in (['4','0','0','0'],['4.5','0','0','0','0'],
                        ['3','0','0','0','0'],['4','-1','0','0','0'],
                        ['4','NaN','0','0','0'],['4','1e2','0','0','0'],
                        ['4','0.001','0','0','0'],['4','0','0','0','0','extra']):
            with self.subTest(summary=summary),self.assertRaises(ValueError):
                parse_document(bill_bytes(summary=summary))
        for raw in (bill_bytes(trailer=False),bill_bytes().rsplit(b'\r\n',2)[0]+b'\r\n',
                    bill_bytes()+b'junk,after,summary\r\n',
                    bill_bytes().replace('总条数'.encode(),'总笔数'.encode())):
            with self.assertRaises(ValueError):parse_document(raw)

    def test_invalid_detail_shape_money_time_and_identity_fail_closed(self):
        for index,value in ((0,'2026-02-31 12:00:00'),(0,'2026-10-16T12:00:00+08:00'),
                            (7,'0.001'),(9,'-1'),(8,''),(5,'')):
            rows=fixture_rows();rows[0][index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                parse_document(bill_bytes(rows))
        rows=fixture_rows();rows[0].append('extra')
        with self.assertRaises(ValueError):parse_document(bill_bytes(rows))

    def test_unknown_variant_retained_without_recognition(self):
        columns=list(SPLIT_COLUMNS);columns[0]='未知时间'
        self.assertIsNone(parse_document(bill_bytes(columns=columns))[2])
        for index,value in ((10,'未知业务'),(11,'未知状态')):
            rows=fixture_rows();rows[0][index]=value
            self.assertIsNone(parse_document(bill_bytes(rows))[2])
        columns=list(SPLIT_COLUMNS);columns[0],columns[1]=columns[1],columns[0]
        self.assertIsNone(parse_document(bill_bytes(columns=columns))[2])

    def test_legacy_trade_and_split_keep_tuple_api(self):
        for raw in (b'a,b\n`x,`y\n',
                    '商户分账单号,分账金额,分账结果\nref,0.10,成功\n'.encode()):
            self.assertEqual(len(parse(raw)[1]),1)
            self.assertIsNone(parse_document(raw)[2])


class OfficialSchemaSignedJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):
        self.fx=fixtures.CommunityReportJourney();self.fx.setUp()
        self.bills=ProviderBills(self.fx.actions)
        self.date=(dt.datetime.fromtimestamp(self.fx.c.now(),dt.timezone(dt.timedelta(hours=8))).date()-dt.timedelta(days=1)).isoformat()
    def tearDown(self):self.fx.tearDown()
    def call(self,op,**extra):
        return self.bills.dispatch(self.fx.web['token'],self.fx.web['csrf'],'finance',op,
                                   dict(kind='SPLIT',bill_date=self.date,**extra))
    def raw_bill(self,rows=None,**kwargs):
        rows=fixture_rows() if rows is None else rows
        for row in rows:
            row[1]=self.fx.reader._mchid
            row[2]='1234567891'
        return bill_bytes(rows,**kwargs)
    def signed_download(self,raw):
        ticket=canonical(dict(hash_type='SHA1',hash_value=hashlib.sha1(raw).hexdigest(),
                              download_url='https://api.mch.weixin.qq.com/v3/billdownload/file?token=fixture'))
        now=str(self.fx.c.now());nonce='fixture'
        signature=keys.SignedOrderQuery.provider.sign((now+'\n'+nonce+'\n').encode()+ticket+b'\n',padding.PKCS1v15(),hashes.SHA256())
        headers={'Wechatpay-Serial':'PUB_KEY_ID_fixture','Wechatpay-Timestamp':now,
                 'Wechatpay-Nonce':nonce,'Wechatpay-Signature':base64.b64encode(signature).decode()}
        self.fx.reader._fetch=Mock(return_value=(headers,ticket))
        self.bills._download=Mock(return_value=raw)
        return headers,ticket
    def test_signed_fetch_private_storage_pending_reconcile_and_audit(self):
        raw=self.raw_bill();self.signed_download(raw)
        before=list(self.fx.fx.stage.demo.db.iterdump())
        receipt=self.call('bill_fetch')
        self.assertEqual(receipt['row_count'],4)
        self.assertEqual(receipt['integrity'],'SIGNED_TICKET_HASH_VERIFIED')
        request=self.fx.reader._fetch.call_args.args[0]
        self.assertIn('/v3/profitsharing/bills?',request.full_url)
        self.assertEqual(request.method,'GET')
        g,_=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        key,saved=self.bills._read(g,'SPLIT',self.date)
        self.assertEqual(saved['rows'][0]['分账接收方'],'private-synthetic-receiver-0')
        encrypted=self.fx.c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_BILL'").fetchone()[0]
        self.assertNotIn('private-synthetic-receiver',str(encrypted))
        result=self.call('bill_reconcile')
        self.assertEqual(result['status'],'SCHEMA_RECOGNIZED_RECONCILIATION_PENDING')
        self.assertEqual(result['finance_status'],'UNCONFIRMED')
        self.assertFalse(result['funds_retry_authorized'])
        public=[receipt,result,self.call('bill_rows',offset=0),self.call('bill_audit',after_id='')]
        self.assertNotIn('private-synthetic-receiver',json.dumps(public))
        self.assertEqual(before,list(self.fx.fx.stage.demo.db.iterdump()))
    def test_summary_retained_privately_without_inventing_amount_reconciliation(self):
        # Intentionally not the sample arithmetic: no documented classification
        # formula authorizes rejecting or promoting these provider-reported sums.
        raw=self.raw_bill(summary=['4','9.91','2.03','8.07','7.09'])
        self.signed_download(raw);self.call('bill_fetch')
        g,_=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        _,saved=self.bills._read(g,'SPLIT',self.date)
        self.assertEqual(saved['reported_summary'],dict(zip(SPLIT_SUMMARY_COLUMNS,['4','9.91','2.03','8.07','7.09'])))
        result=self.call('bill_reconcile')
        self.assertEqual(result['summary_evidence'],'PROVIDER_REPORTED_VALUES_RETAINED')
        self.assertEqual(result['summary_amounts'],'NOT_RECONCILED')
        self.assertEqual(result['reverse_coverage'],'NOT_ESTABLISHED')
        self.assertNotIn('reported_summary',result)
        self.assertNotIn('9.91',json.dumps(result))
        del saved['reported_summary']
        self.assertEqual(self.bills.reconcile(g,saved)['summary_evidence'],'LEGACY_SUMMARY_VALUES_NOT_RETAINED')

    def test_offline_download_uses_signed_get_and_exact_uncompressed_bytes(self):
        raw=self.raw_bill();self.signed_download(raw)
        # Exercise the actual bounded downloader with an in-memory HTTP double.
        del self.bills._download
        response=Mock(status=200);response.read.return_value=raw
        context=Mock();context.__enter__=Mock(return_value=response)
        context.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=context
        with patch('scripts.community_provider_bills.urllib.request.build_opener',return_value=opener):
            self.assertEqual(self.call('bill_fetch')['row_count'],4)
        request=opener.open.call_args.args[0]
        fields=dict(re.findall(r'([a-z_]+)="([^"]*)"',request.get_header('Authorization')))
        target=request.full_url.removeprefix('https://api.mch.weixin.qq.com')
        message=('GET\n'+target+'\n'+fields['timestamp']+'\n'+fields['nonce_str']+'\n\n').encode()
        keys.SignedOrderQuery.merchant.public_key().verify(base64.b64decode(fields['signature']),message,
                                                          padding.PKCS1v15(),hashes.SHA256())
        self.assertIsNone(request.data)
        response.read.assert_called_once_with(15_000_001)

    def test_bad_ticket_signature_prevents_download_and_storage(self):
        headers,ticket=self.signed_download(self.raw_bill())
        self.fx.reader._fetch.return_value=(headers,ticket+b' ')
        with self.assertRaises(Exception):self.call('bill_fetch')
        self.bills._download.assert_not_called()
        self.assertEqual(self.fx.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_PROVIDER_BILL'").fetchone()[0],0)
    def test_hash_and_invalid_summary_never_persist(self):
        self.signed_download(self.raw_bill())
        self.bills._download.return_value=self.raw_bill()+b' '
        with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):self.call('bill_fetch')
        self.signed_download(bill_bytes(summary=['3','0','0','0','0']))
        with self.assertRaisesRegex(ValueError,'COUNT_MISMATCH'):self.call('bill_fetch')
        self.assertEqual(self.fx.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_PROVIDER_BILL'").fetchone()[0],0)
    def test_unknown_variant_is_unknown_after_verified_storage(self):
        rows=fixture_rows();rows[0][10]='未知业务'
        self.signed_download(self.raw_bill(rows));self.call('bill_fetch')
        self.assertEqual(self.call('bill_reconcile')['status'],'UNKNOWN_SCHEMA')


class ExactSplitDetailJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):
        self.fx=fixtures.CommunityReportJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.fx.basket();self.a=self.fx.actions;self.c=self.fx.c;self.bills=ProviderBills(self.a)
        self.g,self.policy=self.a._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        self.key=hashlib.sha256(canonical([self.fx.reader._mchid,'SPLIT','synthetic-split'])).hexdigest()
        self.saved=dict(kind='SPLIT',scope=self.g['scope'],project=self.g['project'],reference='basket',
            request_id='synthetic',request_hash='b'*64,provider_reference='synthetic-split',transaction_id='synthetic-tx',
            payload=dict(sub_mchid=self.policy['sub_mchid'],transaction_id='synthetic-tx',out_order_no='synthetic-split',
                         receivers=[dict(type='MERCHANT_ID',account='1234567892',amount=10)]))
        self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",
            (self.key,self.g['user_id'],self.g['project'],self.c.encrypt(canonical(self.saved),'provider-action:'+self.key)))
        self.a.runtime.demo.db.execute("UPDATE orders SET provider_transaction_id='synthetic-tx' WHERE reference='basket'")
        self.a.runtime.demo.db.commit()
        self.response=dict(sub_mchid=self.policy['sub_mchid'],transaction_id='synthetic-tx',out_order_no='synthetic-split',
            order_id='synthetic-wechat-split',state='FINISHED',receivers=[dict(type='MERCHANT_ID',account='1234567892',
            amount=10,result='SUCCESS',detail_id='synthetic-detail',finish_time='2026-10-16T12:00:00+08:00')])
    def signed_response(self,data):
        raw=canonical(data);now=str(self.c.now());nonce='synthetic-detail'
        signature=keys.SignedOrderQuery.provider.sign((now+'\n'+nonce+'\n').encode()+raw+b'\n',padding.PKCS1v15(),hashes.SHA256())
        self.fx.reader._fetch=Mock(return_value=({'Wechatpay-Serial':'PUB_KEY_ID_fixture',
            'Wechatpay-Timestamp':now,'Wechatpay-Nonce':nonce,'Wechatpay-Signature':base64.b64encode(signature).decode()},raw))
    def accept(self,data=None):
        self.signed_response(self.response if data is None else data)
        # Original query path performs actual RSA verification and frozen-intent checks.
        return self.a._query(self.fx.web['token'],self.fx.web['csrf'],'finance',self.g,self.policy,
                             self.key,'synthetic-lock',self.a._load(self.key))
    def bill(self,changes=None,rows=None):
        values=['2026-10-16 12:00:00',self.fx.reader._mchid,self.policy['sub_mchid'],'synthetic-tx',
                'synthetic-wechat-split','synthetic-detail','synthetic-split','1.01','1234567892','0.10',
                '分出','成功','synthetic description','']
        row=dict(zip(SPLIT_COLUMNS,values));row.update(changes or {})
        if rows is None:rows=[[row[k] for k in SPLIT_COLUMNS]]
        header,records,schema=parse_document(bill_bytes(rows))
        return dict(kind='SPLIT',columns=header,rows=records,schema=schema,sub_mchid=self.policy['sub_mchid'],
                    body_sha256='d'*64,bill_date='2026-10-16')
    def test_signed_query_retains_private_complete_evidence_and_exact_row_match(self):
        before=list(self.a.runtime.demo.db.iterdump())
        public=self.accept();saved=self.a._load(self.key)
        self.assertEqual(saved['bill_evidence']['details']['receivers'][0]['detail_id'],'synthetic-detail')
        self.assertNotIn('synthetic-detail',json.dumps(public))
        self.assertNotIn('1234567892',json.dumps(public))
        result=self.bills.reconcile(self.g,self.bill())
        self.assertEqual(result['status'],'DETAIL_FIELDS_MATCH_RECONCILIATION_PENDING')
        self.assertEqual(result['matched_detail_rows'],1)
        self.assertEqual(result['time_coverage'],'UNKNOWN_BILL_TIMEZONE')
        self.assertEqual(result['summary_amounts'],'NOT_RECONCILED')
        self.assertEqual(result['finance_status'],'UNCONFIRMED')
        self.assertFalse(result['funds_retry_authorized'])
        self.assertNotIn('1234567892',json.dumps(result))
        self.assertEqual(before,list(self.a.runtime.demo.db.iterdump()))
        encrypted=self.c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION'").fetchone()[0]
        self.assertNotIn('synthetic-detail',str(encrypted))
    def test_all_identity_and_amount_mismatches_are_explicit_exceptions(self):
        self.accept()
        for changes in ({'分账发起方':'other'}, {'分账方':'other'}, {'微信订单号':'other'},
                        {'微信分账/回退单号':'other'},{'分账明细单号':'other'},
                        {'分账接收方':'other'}, {'金额':'0.11'}, {'订单金额':'1.02'}):
            with self.subTest(changes=changes):
                result=self.bills.reconcile(self.g,self.bill(changes))
                self.assertEqual(result['status'],'EXCEPTION')
                self.assertEqual(result['matched_detail_rows'],0)
    def test_each_receiver_matches_its_detail_amount_never_aggregate(self):
        import copy
        identity=tuple(self.g['scope'][k] for k in ('tenant_id','merchant_id','store_id'))
        self.a.bindings[identity]['receivers']['second']=dict(type='PERSONAL_OPENID',account='private-openid',name=None,label='Synthetic')
        self.g,self.policy=self.a._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        saved=self.a._load(self.key)
        saved['payload']['receivers'].append(dict(type='PERSONAL_OPENID',account='private-openid',amount=5))
        self.a._save(self.key,saved)
        self.response['receivers'].append(dict(type='PERSONAL_OPENID',account='private-openid',amount=5,
            result='SUCCESS',detail_id='synthetic-detail-second',finish_time='2026-10-16T12:00:00Z'))
        self.accept()
        first=self.bill();second=self.bill({'分账明细单号':'synthetic-detail-second','分账接收方':'private-openid','金额':'0.05'})
        first['rows']+=second['rows']
        result=self.bills.reconcile(self.g,first)
        self.assertEqual(result['matched_detail_rows'],2)
        self.assertEqual(result['status'],'DETAIL_FIELDS_MATCH_RECONCILIATION_PENDING')
        wrong=self.bill({'金额':'0.15'})
        self.assertEqual(self.bills.reconcile(self.g,wrong)['status'],'EXCEPTION')
        # The naive CSV time is never localized from either signed API offset.
        self.assertEqual(result['time_coverage'],'UNKNOWN_BILL_TIMEZONE')
        self.assertNotIn('private-openid',json.dumps(result))

    def test_duplicate_detail_is_not_double_counted(self):
        self.accept();bill=self.bill();bill['rows']*=2
        result=self.bills.reconcile(self.g,bill)
        self.assertEqual(result['status'],'EXCEPTION')
        self.assertEqual(result['matched_detail_rows'],1)
        self.assertEqual(result['exceptions'][0]['reason'],'DUPLICATE_PROVIDER_DETAIL')
    def test_missing_old_evidence_stays_unknown_and_later_signed_query_enriches(self):
        import copy
        old=copy.deepcopy(self.response);del old['order_id'];self.accept(old)
        self.assertNotIn('bill_evidence',self.a._load(self.key))
        self.assertEqual(self.bills.reconcile(self.g,self.bill())['matched_detail_rows'],0)
        self.accept()
        self.assertEqual(self.bills.reconcile(self.g,self.bill())['matched_detail_rows'],1)
        retained=self.a._load(self.key)['bill_evidence'];self.accept(old)
        self.assertEqual(self.a._load(self.key)['bill_evidence'],retained)
    def test_signed_terminal_detail_changes_are_rejected_without_overwrite(self):
        import copy
        self.accept();before=self.a._load(self.key)
        for path,value in (('order_id','changed'),('detail_id','changed'),('finish_time','2026-10-16T12:00:01+08:00')):
            data=copy.deepcopy(self.response)
            if path=='order_id':data[path]=value
            else:data['receivers'][0][path]=value
            with self.assertRaises(Exception):self.accept(data)
            self.assertEqual(self.a._load(self.key),before)
    def test_missing_detail_and_invalid_signed_timestamp_never_become_matches(self):
        import copy
        old=copy.deepcopy(self.response);del old['receivers'][0]['detail_id'];self.accept(old)
        self.assertEqual(self.bills.reconcile(self.g,self.bill())['matched_detail_rows'],0)
        bad=copy.deepcopy(self.response);bad['receivers'][0]['finish_time']='2026-10-16 12:00:00'
        with self.assertRaises(Exception):self.accept(bad)
        self.assertNotIn('bill_evidence',self.a._load(self.key))
    def test_return_and_unfreeze_rows_remain_explicit_unknown(self):
        self.accept()
        for kind in ('分账回退','解冻','逾期解冻'):
            result=self.bills.reconcile(self.g,self.bill({'业务类型':kind}))
            self.assertEqual(result['matched_detail_rows'],0)
            self.assertEqual(result['status'],'SCHEMA_RECOGNIZED_RECONCILIATION_PENDING')
            self.assertIn('JOIN_UNVERIFIED',result['unknown_rows'][0]['reason'])
    def test_unverified_return_unfreeze_party_columns_are_not_inferred(self):
        self.accept()
        for kind in ('分账回退','解冻','逾期解冻'):
            result=self.bills.reconcile(self.g,self.bill({'业务类型':kind,
                '分账发起方':'other-unverified-party','分账方':'other-unverified-sender'}))
            self.assertEqual(result['matched_detail_rows'],0)
            self.assertEqual(result['exceptions'],[])
            self.assertEqual(result['status'],'SCHEMA_RECOGNIZED_RECONCILIATION_PENDING')
            self.assertIn('JOIN_UNVERIFIED',result['unknown_rows'][0]['reason'])

    def test_foreign_scope_or_ambiguous_local_reference_does_not_match(self):
        self.accept();saved=self.a._load(self.key)
        saved['scope']=dict(self.g['scope'],store_id='other');self.a._save(self.key,saved)
        result=self.bills.reconcile(self.g,self.bill())
        self.assertEqual(result['matched_detail_rows'],0)
        self.assertEqual(result['unknown_rows'][0]['reason'],'LOCAL_SPLIT_EVIDENCE_MISSING_OR_AMBIGUOUS')
    def test_signed_return_fields_are_encrypted_and_conflict_protected(self):
        from scripts.community_split_returns import SplitReturns
        from scripts.community_provider_reference import provider_order_reference
        returns=SplitReturns(self.a);request='returntest';reference='basket'
        ref='sr'+hashlib.sha256(canonical([self.fx.reader._mchid,self.g['scope'],reference,request])).hexdigest()[:30]
        key=hashlib.sha256(canonical([self.fx.reader._mchid,'RETURN',ref])).hexdigest()
        payload=dict(sub_mchid=self.policy['sub_mchid'],out_order_no='synthetic-split',out_return_no=ref,
                     return_mchid='1234567892',amount=5,description='synthetic')
        saved=dict(scope=self.g['scope'],project=self.g['project'],policy_hash=self.a._policy_hash(self.policy),
                   payload=payload,request_hash='a'*64,reference=reference,request_id=request,receiver_id='comm')
        self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_RETURN',?,?,?,?,1)",
            (key,self.g['user_id'],self.g['project'],self.c.encrypt(canonical(saved),'community-provider-return:'+key)))
        data=dict(payload,result='SUCCESS',order_id='synthetic-wechat-split',return_id='synthetic-wechat-return',
                  finish_time='2026-10-16T12:00:00+08:00')
        self.signed_response(data)
        def query():return returns.dispatch(self.fx.web['token'],self.fx.web['csrf'],'finance',
                                            'query_split_return',dict(reference=reference,request_id=request))
        public=query();retained=returns._read(key)
        self.assertEqual(retained['bill_evidence']['details']['return_id'],'synthetic-wechat-return')
        self.assertNotIn('1234567892',json.dumps(public));self.assertNotIn('synthetic-wechat-return',json.dumps(public))
        data['return_id']='changed';self.signed_response(data)
        with self.assertRaisesRegex(ValueError,'TERMINAL_BILL_EVIDENCE_CONFLICT'):query()
        self.assertEqual(returns._read(key),retained)


if __name__=='__main__':unittest.main()
