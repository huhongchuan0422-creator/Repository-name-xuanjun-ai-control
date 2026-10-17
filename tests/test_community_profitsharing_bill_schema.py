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
        raw=bill_bytes();self.signed_download(raw)
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
    def test_offline_download_uses_signed_get_and_exact_uncompressed_bytes(self):
        raw=bill_bytes();self.signed_download(raw)
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
        headers,ticket=self.signed_download(bill_bytes())
        self.fx.reader._fetch.return_value=(headers,ticket+b' ')
        with self.assertRaises(Exception):self.call('bill_fetch')
        self.bills._download.assert_not_called()
        self.assertEqual(self.fx.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_PROVIDER_BILL'").fetchone()[0],0)
    def test_hash_and_invalid_summary_never_persist(self):
        self.signed_download(bill_bytes())
        self.bills._download.return_value=bill_bytes()+b' '
        with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):self.call('bill_fetch')
        self.signed_download(bill_bytes(summary=['3','0','0','0','0']))
        with self.assertRaisesRegex(ValueError,'COUNT_MISMATCH'):self.call('bill_fetch')
        self.assertEqual(self.fx.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_PROVIDER_BILL'").fetchone()[0],0)
    def test_unknown_variant_is_unknown_after_verified_storage(self):
        rows=fixture_rows();rows[0][10]='未知业务'
        self.signed_download(bill_bytes(rows));self.call('bill_fetch')
        self.assertEqual(self.call('bill_reconcile')['status'],'UNKNOWN_SCHEMA')


if __name__=='__main__':unittest.main()
