"""Signed bill tickets, bounded private downloads and scoped row reconciliation.

Download bodies have no APIv3 signature: integrity is checked against the hash
inside the RSA-verified ticket. No download token or customer row is logged.
Unknown columns stay UNKNOWN; bill matches never grant Finance settlement.
"""
import base64
import csv
import datetime as dt
import hashlib
import io
import json
import re
import secrets
import urllib.parse
import urllib.request
from decimal import Decimal
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.pr122_customer_core import canonical
from scripts.community_mini_login import _NoRedirect
from scripts.community_provider_reference import provider_order_reference

MAX_BYTES=15_000_000


def minor(value):
    value=value.removeprefix('`').strip()
    if not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,2})?',value):raise ValueError('INVALID_BILL_AMOUNT')
    return int(Decimal(value)*100)


# Official layout evidence (retrieved 2026-10-17):
# https://pay.wechatpay.cn/doc/v3/partner/4012075366 links 分账账单.xlsx,
# SHA256 4091e88e5c39a30b781b76f6c733e4fa495c61f7ec4e397c6117cbc4a7de89ff.
# https://pay.wechatpay.cn/doc/v3/partner/4012761140 documents CSV detail
# backtick prefixes, a separate summary header, and SHA1 of uncompressed bytes.
# This is a local evidence/layout revision, not a claimed provider version.
# The sample has no receiver type or timezone; return-detail join semantics
# are unverified. Recognition MUST NOT establish receiver/aggregate matches.
SPLIT_SCHEMA='WECHAT_PROFITSHARING_SAMPLE_20261017_V1'
SPLIT_COLUMNS=('分账时间','分账发起方','分账方','微信订单号','微信分账/回退单号',
    '分账明细单号','商户分账/回退单号','订单金额','分账接收方','金额','业务类型','处理状态','分账描述','备注')
SPLIT_SUMMARY_COLUMNS=('总条数','分账成功出资金','分账失败已转回分账方','解冻资金给分账方','分账回退资金')
SPLIT_TYPES={'分出','解冻','逾期解冻','分账回退'}


def _split_summary(row, count):
    if len(row)!=5 or not re.fullmatch(r'[0-9]{1,6}(?:\.0{1,2})?',row[0]):
        raise ValueError('INVALID_SPLIT_BILL_SUMMARY')
    if Decimal(row[0])!=count:raise ValueError('SPLIT_BILL_SUMMARY_COUNT_MISMATCH')
    try:
        for value in row[1:]:minor(value)
    except ValueError:raise ValueError('INVALID_SPLIT_BILL_SUMMARY') from None


def parse_document(raw):
    if type(raw) is not bytes or len(raw)>MAX_BYTES:raise ValueError('BOUNDED_PROVIDER_BILL_REQUIRED')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:raise ValueError('INVALID_BILL_UTF8') from None
    if '\x00' in text:raise ValueError('INVALID_BILL_TEXT')
    rows=csv.reader(io.StringIO(text),strict=True)
    try:header=[v.removeprefix('`').strip() for v in next(rows)]
    except StopIteration:raise ValueError('EMPTY_PROVIDER_BILL')
    except csv.Error:raise ValueError('INVALID_BILL_CSV') from None
    if len(set(header))!=len(header) or not 2<=len(header)<=100:raise ValueError('INVALID_BILL_COLUMNS')
    if any(not v or any(ord(ch)<32 or 0x202a<=ord(ch)<=0x202e or 0x2066<=ord(ch)<=0x2069 for ch in v) for v in header):raise ValueError('INVALID_BILL_COLUMN_NAME')
    records=[];summary=False;split_summary=None;summary_values=None
    exact_split=tuple(header)==SPLIT_COLUMNS;known_values=True
    try:
        for raw_row in rows:
            if not raw_row or not any(raw_row):continue
            row=[v.removeprefix('`').strip() for v in raw_row]
            if split_summary is not None:
                if summary_values is not None:raise ValueError('UNEXPECTED_SPLIT_BILL_TRAILER')
                _split_summary(row,len(records));summary_values=row;continue
            if row[0]=='总条数':
                if tuple(row)!=SPLIT_SUMMARY_COLUMNS:raise ValueError('INVALID_SPLIT_BILL_SUMMARY_HEADER')
                split_summary=row;continue
            if exact_split and row[0].startswith(('总交易单数','总笔数','总交易额','总分账笔数')):
                raise ValueError('INVALID_SPLIT_BILL_SUMMARY_HEADER')
            if row[0].startswith(('总交易单数','总笔数','总交易额','总分账笔数')):summary=True;continue
            if summary:continue
            if len(row)!=len(header) or len(records)>=100000:raise ValueError('BILL_ROW_SHAPE_OR_LIMIT')
            if exact_split:
                if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}',row[0]):
                    raise ValueError('INVALID_SPLIT_BILL_TIME')
                try:dt.datetime.strptime(row[0],'%Y-%m-%d %H:%M:%S')
                except ValueError:raise ValueError('INVALID_SPLIT_BILL_TIME') from None
                minor(row[7]);minor(row[9])
                if any(not row[i] for i in range(1,7)) or not row[8]:
                    raise ValueError('INVALID_SPLIT_BILL_DETAIL')
                # Preserve unfamiliar business/status values without guessing.
                known_values=known_values and row[10] in SPLIT_TYPES and row[11]=='成功'
            records.append(dict(zip(header,row)))
    except csv.Error:raise ValueError('INVALID_BILL_CSV') from None
    if (exact_split or split_summary is not None) and summary_values is None:
        raise ValueError('MISSING_SPLIT_BILL_SUMMARY')
    metadata=None
    if exact_split and known_values:
        metadata=dict(id=SPLIT_SCHEMA,summary_count=len(records),amount_unit='YUAN',
                      timezone='UNSPECIFIED',receiver_type='UNSPECIFIED',
                      detail_join='UNVERIFIED',summary_shape='VALIDATED')
    return header,records,metadata


def parse(raw):
    header,records,_=parse_document(raw)
    return header,records



class ProviderBills:
    def __init__(self,actions):self.actions,self.center=actions,actions.center
    def _download(self,url):
        parsed=urllib.parse.urlsplit(url)
        if (parsed.scheme!='https' or parsed.hostname!='api.mch.weixin.qq.com' or parsed.port not in (None,443)
                or parsed.username or parsed.password or parsed.fragment
                or parsed.path not in ('/v3/billdownload/file','/v3/bill/downloadurl')
                or not parsed.query or len(url)>2048 or any(ord(ch)<33 for ch in url)):
            raise PermissionError('SIGNED_FIXED_ORIGIN_BILL_URL_REQUIRED')
        reader=self.actions.reader;target=parsed.path+'?'+parsed.query;now=reader._clock();nonce=secrets.token_hex(16)
        signature=base64.b64encode(reader._private.sign(('GET\n'+target+'\n'+str(now)+'\n'+nonce+'\n\n').encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
        authorization='WECHATPAY2-SHA256-RSA2048 mchid="'+reader._mchid+'",nonce_str="'+nonce+'",timestamp="'+str(now)+'",serial_no="'+reader._serial+'",signature="'+signature+'"'
        req=urllib.request.Request(url,headers={'Authorization':authorization,'Accept':'application/octet-stream'})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
        try:
            with opener.open(req,timeout=10) as response:
                if response.status!=200:raise ValueError('BILL_DOWNLOAD_NOT_200')
                raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError('BILL_DOWNLOAD_TOO_LARGE')
            return raw
        except Exception:raise RuntimeError('BILL_DOWNLOAD_UNKNOWN_NO_TOKEN_DISCLOSURE') from None
    def _read(self,g,kind,date):
        key=hashlib.sha256(canonical([g['scope'],kind,date])).hexdigest()
        row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_BILL' AND subject_idx=? AND project=? AND active=1",(key,g['project'])).fetchone()
        if row is None:raise ValueError('VERIFIED_PROVIDER_BILL_NOT_FOUND')
        return key,json.loads(self.center.decrypt(row[0],'community-bill:'+key))
    def dispatch(self,session,csrf,workspace,operation,p):
        fields={'bill_fetch':{'kind','bill_date'},'bill_rows':{'kind','bill_date','offset'},'bill_reconcile':{'kind','bill_date'},'bill_audit':{'kind','bill_date','after_id'}}
        if operation not in fields or type(p) is not dict or set(p)!=fields[operation] or p['kind'] not in ('TRADE','SPLIT'):raise ValueError('INVALID_PROVIDER_BILL_FIELDS')
        a,c=self.actions,self.center;g,policy=a._authorize(session,csrf,workspace)
        if type(p['bill_date']) is not str or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',p['bill_date']):raise ValueError('INVALID_BILL_DATE')
        date=dt.date.fromisoformat(p['bill_date']);today=dt.datetime.fromtimestamp(c.now(),dt.timezone(dt.timedelta(hours=8))).date()
        if not 0<(today-date).days<=90:raise ValueError('BILL_DATE_OUTSIDE_SUPPORTED_HISTORY')
        with c.tx():c.limit('community-provider-bill:'+g['user_id'],10,60)
        if operation=='bill_fetch':
            query=dict(sub_mchid=policy['sub_mchid'],bill_date=p['bill_date'])
            if p['kind']=='TRADE':query['bill_type']='ALL'
            target=('/v3/bill/tradebill' if p['kind']=='TRADE' else '/v3/profitsharing/bills')+'?'+urllib.parse.urlencode(query)
            ticket,ticket_digest=a._call('GET',target)
            if ticket.get('hash_type')!='SHA1' or type(ticket.get('hash_value')) is not str or not re.fullmatch('[0-9a-fA-F]{40}',ticket['hash_value']) or type(ticket.get('download_url')) is not str:raise ValueError('INVALID_SIGNED_BILL_TICKET')
            raw=self._download(ticket['download_url'])
            if hashlib.sha1(raw).hexdigest()!=ticket['hash_value'].lower():raise PermissionError('PROVIDER_BILL_HASH_MISMATCH')
            if a._authorize(session,csrf,workspace)[1]!=policy:raise PermissionError('BILL_AUTHORIZATION_CHANGED')
            header,rows,schema=parse_document(raw);key=hashlib.sha256(canonical([g['scope'],p['kind'],p['bill_date']])).hexdigest()
            record=dict(scope=g['scope'],sub_mchid=policy['sub_mchid'],kind=p['kind'],bill_date=p['bill_date'],columns=header,rows=rows,
                schema=schema,body_sha256=hashlib.sha256(raw).hexdigest(),provider_sha1=ticket['hash_value'].lower(),ticket_sha256=ticket_digest,received_at=c.now())
            with c.tx():
                previous=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_BILL' AND subject_idx=? AND project=? AND active=1",(key,g['project'])).fetchone()
                if previous and json.loads(c.decrypt(previous[0],'community-bill:'+key))['body_sha256']!=record['body_sha256']:raise ValueError('IMMUTABLE_PROVIDER_BILL_CHANGED_REVIEW_REQUIRED')
                if previous is None:c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_BILL',?,?,?,?,1)",(key,g['user_id'],g['project'],c.encrypt(canonical(record),'community-bill:'+key)))
                c.audit(g['project'],g['user_id'],'PROVIDER_BILL_HASH_VERIFIED',record['body_sha256'])
            return dict(kind=p['kind'],bill_date=p['bill_date'],row_count=len(rows),body_sha256=record['body_sha256'],integrity='SIGNED_TICKET_HASH_VERIFIED',reconciliation='NOT_RUN',finance_status='UNCONFIRMED')
        key,bill=self._read(g,p['kind'],p['bill_date'])
        if bill['scope']!=g['scope'] or bill['sub_mchid']!=policy['sub_mchid']:raise PermissionError('BILL_MERCHANT_BINDING_CHANGED')
        if operation=='bill_audit':
            after=p['after_id']
            if type(after) is not str or (after and not re.fullmatch('[0-9a-f]{64}',after)):
                raise ValueError('INVALID_BILL_AUDIT_CURSOR')
            rows=c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_BILL_RECONCILIATION' AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51",(g['project'],after)).fetchall()
            records=[]
            for ref,payload in rows[:50]:
                saved=json.loads(c.decrypt(payload,'community-bill-reconciliation:'+ref))
                if type(saved) is dict and 'bill_key' in saved and 'result' in saved:
                    digest=hashlib.sha256(canonical([saved['bill_key'],saved['result']])).hexdigest()
                    if digest!=ref:raise ValueError('BILL_AUDIT_INTEGRITY_CHANGED')
                if (type(saved) is dict and saved.get('bill_key')==key
                        and saved.get('kind')==p['kind'] and saved.get('bill_date')==p['bill_date']
                        and saved.get('scope')==g['scope']):
                    records.append(dict(id=ref,result=saved['result']))
            return dict(records=records,has_more=len(rows)>50,
                        next_cursor=rows[49][0] if len(rows)>50 else None,
                        coverage='EXACT_SCOPE_BILL_AUDIT_ONLY',finance_status='UNCONFIRMED')
        if operation=='bill_rows':
            offset=p['offset']
            if type(offset) is not int or not 0<=offset<=100000:raise ValueError('INVALID_BILL_PAGE')
            # Raw consumer identifiers stay encrypted; page returns only fields
            # needed by finance reconciliation, never openid/bank/card columns.
            allowed={'交易时间','商户订单号','微信订单号','商户退款单号','微信退款单号','交易状态','退款状态','订单金额','总金额','退款金额','商户分账单号','分账金额','分账结果','特约商户号','币种','货币种类'}
            return dict(records=[{k:v for k,v in row.items() if k in allowed} for row in bill['rows'][offset:offset+50]],has_more=offset+50<len(bill['rows']),next_offset=offset+50 if offset+50<len(bill['rows']) else None)
        result=self.reconcile(g,bill)
        with c.tx():
            event=hashlib.sha256(canonical([key,result])).hexdigest()
            c.db.execute("INSERT OR IGNORE INTO links VALUES('COMMUNITY_BILL_RECONCILIATION',?,?,?,?,1)",(event,g['user_id'],g['project'],c.encrypt(canonical(dict(bill_key=key,kind=p['kind'],bill_date=p['bill_date'],scope=g['scope'],result=result)),'community-bill-reconciliation:'+event)))
            c.audit(g['project'],g['user_id'],'PROVIDER_BILL_RECONCILED',event)
        return result
    def reconcile(self,g,bill):
        a=self.actions;rows=bill['rows'];columns=set(bill['columns']);exceptions=[];matched=0;seen=set();missing=[];undated=0;reverse='NOT_APPLICABLE_TO_SPLIT_LAYOUT'
        if (bill['kind']=='SPLIT' and tuple(bill['columns'])==SPLIT_COLUMNS
                and type(bill.get('schema')) is dict
                and bill['schema'].get('id')==SPLIT_SCHEMA):
            return dict(status='SCHEMA_RECOGNIZED_RECONCILIATION_PENDING',
                schema=dict(bill['schema']),total_rows=len(rows),body_sha256=bill['body_sha256'],
                pending_evidence=['RECEIVER_TYPE_AND_BINDING','RETURN_DETAIL_JOIN','BILL_TIMEZONE'],
                finance_status='UNCONFIRMED',funds_retry_authorized=False)
        # Receiver-level split layouts require explicit receiver binding. Never
        # compare a detail row against an aggregate payout amount.
        if bill['kind']=='SPLIT' and any('接收' in k or '收款' in k for k in columns):
            return dict(status='UNKNOWN_SCHEMA',body_sha256=bill['body_sha256'],finance_status='UNCONFIRMED')
        if bill['kind']=='TRADE':
            amount_column='订单金额' if '订单金额' in columns else '总金额' if '总金额' in columns else None
            if not {'商户订单号','微信订单号','交易状态'}.issubset(columns) or amount_column is None:
                return dict(status='UNKNOWN_SCHEMA',body_sha256=bill['body_sha256'],finance_status='UNCONFIRMED')
            t,m,s=(g['scope'][k] for k in ('tenant_id','merchant_id','store_id'))
            local={provider_order_reference(a.reader._mchid,g['scope'],ref):(ref,amount,tx,state) for ref,amount,tx,state in a.runtime.demo.db.execute('SELECT reference,amount_minor,provider_transaction_id,state FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=?',(t,m,s))}
            for index,row in enumerate(rows):
                row_identity=(row['商户订单号'],row.get('商户退款单号',''))
                if row_identity in seen:exceptions.append(dict(row=index,reason='DUPLICATE_PROVIDER_ROW'));continue
                seen.add(row_identity)
                if any(row.get(field)!='CNY' for field in ('货币种类','币种') if field in columns):exceptions.append(dict(row=index,reason='UNSUPPORTED_BILL_CURRENCY'));continue
                existing=local.get(row['商户订单号'])
                if existing is None:exceptions.append(dict(row=index,reason='PROVIDER_ORDER_NOT_IN_THIS_STORE'));continue
                ref,amount,tx,status=existing
                try:row_amount=minor(row[amount_column])
                except ValueError:exceptions.append(dict(row=index,reason='INVALID_BILL_AMOUNT'));continue
                if row_amount!=amount or row['微信订单号']!=tx:exceptions.append(dict(row=index,reference=ref,reason='PAYMENT_AMOUNT_OR_TRANSACTION_MISMATCH'));continue
                if '特约商户号' in columns and row['特约商户号']!=bill['sub_mchid']:exceptions.append(dict(row=index,reason='BILL_SUBMERCHANT_MISMATCH'));continue
                if row['交易状态'] not in ('SUCCESS','REFUND','成功','退款') or status not in ('SUCCESS','REFUNDED'):exceptions.append(dict(row=index,reference=ref,reason='PAYMENT_STATE_MISMATCH'));continue
                refund=row.get('商户退款单号')
                if refund and refund not in ('0','无','-'):
                    action_key=hashlib.sha256(canonical([a.reader._mchid,'REFUND',refund])).hexdigest();action=a._load(action_key)
                    try:refund_amount=minor(row.get('退款金额',''))
                    except ValueError:exceptions.append(dict(row=index,reference=ref,reason='INVALID_REFUND_AMOUNT'));continue
                    if action is None or action.get('scope')!=g['scope'] or action.get('reference')!=ref or action.get('result',{}).get('status')!='SUCCESS' or refund_amount!=action['payload']['amount']['refund']:exceptions.append(dict(row=index,reference=ref,reason='REFUND_NOT_CONFIRMED_OR_AMOUNT_MISMATCH'));continue
                matched+=1
            provider_refs={row['商户订单号'] for row in rows}
            for out_ref,(ref,amount,tx,status) in local.items():
                if status not in ('SUCCESS','REFUNDED'):continue
                dates=set()
                for raw, in a.runtime.demo.db.execute('SELECT evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,s,ref)):
                    try:value=json.loads(raw)
                    except (ValueError,TypeError):continue
                    if type(value) is dict and value.get('source')=='WECHAT_SIGNED_PAYMENT_TIME' and value.get('transaction_id')==tx and type(value.get('paid_at')) is int:
                        dates.add(dt.datetime.fromtimestamp(value['paid_at'],dt.timezone(dt.timedelta(hours=8))).date().isoformat())
                if len(dates)!=1:undated+=1;continue
                if bill['bill_date'] in dates and out_ref not in provider_refs:missing.append(ref)
            reverse='COMPLETE_FOR_SIGNED_DATED_LOCAL_PAYMENTS' if not undated else 'PARTIAL_UNDATED_LOCAL_PAYMENTS'
        else:
            # Unknown official format is retained, not coerced into a match.
            if not {'商户分账单号','分账金额','分账结果'}.issubset(columns):return dict(status='UNKNOWN_SCHEMA',body_sha256=bill['body_sha256'],finance_status='UNCONFIRMED')
            actions={}
            for key,payload in self.center.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION' AND project=? AND active=1",(g['project'],)):
                saved=json.loads(self.center.decrypt(payload,'provider-action:'+key))
                if saved.get('kind')=='SPLIT' and saved.get('scope')==g['scope']:actions[saved['provider_reference']]=saved
            for index,row in enumerate(rows):
                if row['商户分账单号'] in seen:exceptions.append(dict(row=index,reason='DUPLICATE_PROVIDER_ROW'));continue
                seen.add(row['商户分账单号'])
                if any(row.get(field)!='CNY' for field in ('货币种类','币种') if field in columns):
                    exceptions.append(dict(row=index,reason='UNSUPPORTED_BILL_CURRENCY'));continue
                action=actions.get(row['商户分账单号'])
                if action is None or action.get('result',{}).get('status')!='FINISHED':exceptions.append(dict(row=index,reason='SPLIT_NOT_CONFIRMED'));continue
                # Optional official identifiers must agree with the bound, signed intent.
                # Never silently accept a split row belonging to another payment or submerchant.
                if '特约商户号' in columns and row['特约商户号']!=bill['sub_mchid']:
                    exceptions.append(dict(row=index,reason='BILL_SUBMERCHANT_MISMATCH'));continue
                if '微信订单号' in columns and row['微信订单号']!=action.get('transaction_id'):
                    exceptions.append(dict(row=index,reason='SPLIT_TRANSACTION_MISMATCH'));continue
                total=sum(r['amount_minor'] for r in action['result']['receivers'] if r['result']=='SUCCESS')
                try:row_amount=minor(row['分账金额'])
                except ValueError:exceptions.append(dict(row=index,reason='INVALID_BILL_AMOUNT'));continue
                if row_amount!=total or row['分账结果'] not in ('SUCCESS','成功','FINISHED'):exceptions.append(dict(row=index,reason='SPLIT_AMOUNT_OR_STATE_MISMATCH'));continue
                matched+=1
        return dict(status='EXCEPTION' if exceptions or missing else 'BILL_ROWS_MATCH',matched_rows=matched,total_rows=len(rows),exceptions=exceptions[:200],exceptions_truncated=len(exceptions)>200,
            body_sha256=bill['body_sha256'],coverage='BILL_ROWS_TO_LOCAL_RECORDS',missing_provider_rows=missing[:200],missing_rows_truncated=len(missing)>200,reverse_coverage=reverse,undated_local_payments=undated,finance_status='UNCONFIRMED',funds_retry_authorized=False)
