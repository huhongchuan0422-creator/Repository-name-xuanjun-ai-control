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


# Verified response-field contracts (ordinary service provider, not ecommerce/brand):
# https://pay.wechatpay.cn/doc/v3/partner/4012466850 (split query)
# https://pay.wechatpay.cn/doc/v3/partner/4012466858 (return query)
# Bill amounts are yuan: https://pay.wechatpay.cn/doc/v3/partner/4012761140.
# Query timestamps carry RFC3339 offsets; the CSV sample does not. Never apply
# that offset to a naive bill timestamp or assert date/reverse completeness.
BILL_EVIDENCE_VERSION='SIGNED_PROFITSHARING_DETAIL_V1'


def _evidence_id(value):
    return type(value) is str and 1<=len(value)<=64 and all(33<=ord(c)<=126 for c in value)


def _evidence_time(value):
    if type(value) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})',value):return False
    try:return dt.datetime.fromisoformat(value.replace('Z','+00:00')).utcoffset() is not None
    except ValueError:return False


def signed_bill_evidence(data,digest,kind):
    """Called ONLY after original RSA verification and frozen-intent validation.

    This is private supplemental evidence, not a replacement public action result.
    Older responses missing fields remain usable by original workflows, but cannot
    be promoted into exact-detail bill matches. No replay or network occurs here.
    """
    if kind=='SPLIT':
        if data.get('state')!='FINISHED':return None
        fields=('sub_mchid','transaction_id','out_order_no','order_id')
        if any(k not in data for k in fields):return None
        if any(not _evidence_id(data[k]) for k in fields):raise ValueError('INVALID_SIGNED_BILL_DETAIL_EVIDENCE')
        details=[];seen=set()
        for r in data.get('receivers',[]):
            if any(k not in r for k in ('detail_id','finish_time')):return None
            if (not _evidence_id(r['detail_id']) or not _evidence_time(r['finish_time'])
                    or r['detail_id'] in seen):raise ValueError('INVALID_SIGNED_BILL_DETAIL_EVIDENCE')
            seen.add(r['detail_id'])
            details.append({k:r[k] for k in ('type','account','amount','result','detail_id','finish_time')})
        if not details:return None
        result={k:data[k] for k in fields};result['receivers']=sorted(details,key=lambda r:r['detail_id'])
    elif kind=='RETURN':
        if data.get('result')!='SUCCESS':return None
        fields=('sub_mchid','out_order_no','order_id','out_return_no','return_id','return_mchid')
        if any(k not in data for k in fields) or 'finish_time' not in data:return None
        if any(not _evidence_id(data[k]) for k in fields) or not _evidence_time(data['finish_time']):
            raise ValueError('INVALID_SIGNED_BILL_DETAIL_EVIDENCE')
        result={k:data[k] for k in fields};result.update(amount=data['amount'],finish_time=data['finish_time'])
    else:raise ValueError('INVALID_BILL_EVIDENCE_KIND')
    if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('INVALID_SIGNED_BILL_EVIDENCE_DIGEST')
    return dict(version=BILL_EVIDENCE_VERSION,kind=kind,body_sha256=digest,details=result)


def retain_bill_evidence(saved,evidence):
    if evidence is None:return
    previous=saved.get('bill_evidence')
    if previous is not None and any(previous.get(k)!=evidence[k] for k in ('version','kind','details')):
        raise ValueError('TERMINAL_BILL_EVIDENCE_CONFLICT')
    # Keep first complete terminal evidence and its matching signed-body digest.
    if previous is None:saved['bill_evidence']=evidence


def _split_summary(row, count):
    if len(row)!=5 or not re.fullmatch(r'[0-9]{1,6}(?:\.0{1,2})?',row[0]):
        raise ValueError('INVALID_SPLIT_BILL_SUMMARY')
    if Decimal(row[0])!=count:raise ValueError('SPLIT_BILL_SUMMARY_COUNT_MISMATCH')
    try:
        for value in row[1:]:minor(value)
    except ValueError:raise ValueError('INVALID_SPLIT_BILL_SUMMARY') from None


def _parse_document(raw):
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
    # Retain the provider-reported summary separately from public schema metadata.
    # Column names/sample arithmetic do not establish classification semantics.
    reported_summary=(dict(zip(SPLIT_SUMMARY_COLUMNS,summary_values))
                      if exact_split and summary_values is not None else None)
    return header,records,metadata,reported_summary


def sample_summary_diagnostic(bill):
    """Compare arithmetic illustrated by the pinned official sample only.

    This is not a provider classification contract: failed-return, posting-date
    and signed-detail population semantics remain unresolved. Never expose raw
    provider summary amounts or turn this diagnostic into Finance authority.
    """
    result=dict(coverage='PINNED_SAMPLE_ARITHMETIC_ONLY',
                establishes_reconciliation=False, differing_columns=[])
    reported=bill.get('reported_summary')
    if reported is None:
        return dict(result,status='UNAVAILABLE_LEGACY_SUMMARY')
    schema=bill.get('schema')
    if (type(reported) is not dict or set(reported)!=set(SPLIT_SUMMARY_COLUMNS)
            or type(schema) is not dict or schema.get('id')!=SPLIT_SCHEMA):
        return dict(result,status='UNKNOWN_SCHEMA')
    totals={SPLIT_SUMMARY_COLUMNS[i]:0 for i in (1,3,4)}
    categories={'分出':SPLIT_SUMMARY_COLUMNS[1],
                '解冻':SPLIT_SUMMARY_COLUMNS[3],
                '逾期解冻':SPLIT_SUMMARY_COLUMNS[3],
                '分账回退':SPLIT_SUMMARY_COLUMNS[4]}
    try:
        for row in bill['rows']:
            if row.get('处理状态')!='成功' or row.get('业务类型') not in categories:
                return dict(result,status='UNKNOWN_BUSINESS_OR_STATE')
            totals[categories[row['业务类型']]]+=minor(row['金额'])
        failed=minor(reported[SPLIT_SUMMARY_COLUMNS[2]])
        result['differing_columns']=[name for name,total in totals.items()
                                    if minor(reported[name])!=total]
    except (TypeError,ValueError,KeyError,AttributeError):
        return dict(result,status='INVALID_RETAINED_SUMMARY')
    result['failed_return_semantics']=('UNSPECIFIED_NONZERO' if failed else 'ZERO_IN_REPORTED_SAMPLE')
    return dict(result,status='DIFFERENT_FROM_SAMPLE_ARITHMETIC' if result['differing_columns']
                else 'SAMPLE_ARITHMETIC_EQUAL_UNVERIFIED_SEMANTICS')


def parse_document(raw):
    return _parse_document(raw)[:3]


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
        if operation not in fields or type(p) is not dict:raise ValueError('INVALID_PROVIDER_BILL_FIELDS')
        allowed=fields[operation]
        if (set(p)!=allowed and not (operation=='bill_reconcile' and set(p)==allowed|{'require_complete'})
                or p.get('kind') not in ('TRADE','SPLIT')
                or 'require_complete' in p and (p['kind']!='SPLIT' or type(p['require_complete']) is not bool)):
            raise ValueError('INVALID_PROVIDER_BILL_FIELDS')
        a,c=self.actions,self.center;g,policy=a._authorize(session,csrf,workspace)
        g=dict(g,scope=dict(g['scope']))
        if type(p['bill_date']) is not str or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',p['bill_date']):raise ValueError('INVALID_BILL_DATE')
        date=dt.date.fromisoformat(p['bill_date']);today=dt.datetime.fromtimestamp(c.now(),dt.timezone(dt.timedelta(hours=8))).date()
        if not 0<(today-date).days<=90:raise ValueError('BILL_DATE_OUTSIDE_SUPPORTED_HISTORY')
        with c.tx():c.limit('community-provider-bill:'+g['user_id'],10,60)
        if operation=='bill_fetch':
            # Host grants may be replaced or mutated during provider I/O. Keep
            # the original identity independent of the live configuration.
            g=dict(g,scope=dict(g['scope']))
            query=dict(sub_mchid=policy['sub_mchid'],bill_date=p['bill_date'])
            if p['kind']=='TRADE':query['bill_type']='ALL'
            target=('/v3/bill/tradebill' if p['kind']=='TRADE' else '/v3/profitsharing/bills')+'?'+urllib.parse.urlencode(query)
            ticket,ticket_digest=a._call('GET',target)
            if ticket.get('hash_type')!='SHA1' or type(ticket.get('hash_value')) is not str or not re.fullmatch('[0-9a-fA-F]{40}',ticket['hash_value']) or type(ticket.get('download_url')) is not str:raise ValueError('INVALID_SIGNED_BILL_TICKET')
            raw=self._download(ticket['download_url'])
            if hashlib.sha1(raw).hexdigest()!=ticket['hash_value'].lower():raise PermissionError('PROVIDER_BILL_HASH_MISMATCH')
            current,current_policy=a._authorize(session,csrf,workspace)
            if (any(current[k]!=g[k] for k in ('scope','project','user_id'))
                    or current_policy!=policy):raise PermissionError('BILL_AUTHORIZATION_CHANGED')
            header,rows,schema,reported_summary=_parse_document(raw);key=hashlib.sha256(canonical([g['scope'],p['kind'],p['bill_date']])).hexdigest()
            record=dict(scope=g['scope'],sub_mchid=policy['sub_mchid'],kind=p['kind'],bill_date=p['bill_date'],columns=header,rows=rows,
                schema=schema,reported_summary=reported_summary,body_sha256=hashlib.sha256(raw).hexdigest(),provider_sha1=ticket['hash_value'].lower(),ticket_sha256=ticket_digest,received_at=c.now())
            with c.tx():
                previous=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_BILL' AND subject_idx=? AND project=? AND active=1",(key,g['project'])).fetchone()
                if previous and json.loads(c.decrypt(previous[0],'community-bill:'+key))['body_sha256']!=record['body_sha256']:raise ValueError('IMMUTABLE_PROVIDER_BILL_CHANGED_REVIEW_REQUIRED')
                if previous is None:c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_BILL',?,?,?,?,1)",(key,g['user_id'],g['project'],c.encrypt(canonical(record),'community-bill:'+key)))
                c.audit(g['project'],g['user_id'],'PROVIDER_BILL_HASH_VERIFIED',record['body_sha256'])
            return dict(kind=p['kind'],bill_date=p['bill_date'],row_count=len(rows),body_sha256=record['body_sha256'],integrity='SIGNED_TICKET_HASH_VERIFIED',reconciliation='NOT_RUN',finance_status='UNCONFIRMED')
        key,bill=self._read(g,p['kind'],p['bill_date'])
        if bill['scope']!=g['scope'] or bill['sub_mchid']!=policy['sub_mchid']:raise PermissionError('BILL_MERCHANT_BINDING_CHANGED')
        # An explicit full-day request is rejected even for an empty or exactly
        # matching bill. Local enumeration cannot supply missing provider rules.
        if p.get('require_complete'):raise ValueError('COMPLETE_SPLIT_BILL_RECONCILIATION_UNAVAILABLE')
        if operation=='bill_audit':
            after=p['after_id']
            if type(after) is not str or (after and not re.fullmatch('[0-9a-f]{64}',after)):
                raise ValueError('INVALID_BILL_AUDIT_CURSOR')
            with c.tx():
                current,current_policy=a._authorize(session,csrf,workspace)
                if (any(current[k]!=g[k] for k in ('scope','project','user_id'))
                        or current_policy!=policy):raise PermissionError('BILL_AUTHORIZATION_CHANGED')
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
                current,current_policy=a._authorize(session,csrf,workspace)
                if (any(current[k]!=g[k] for k in ('scope','project','user_id'))
                        or current_policy!=policy):raise PermissionError('BILL_AUTHORIZATION_CHANGED')
            return dict(records=records,has_more=len(rows)>50,
                        next_cursor=rows[49][0] if len(rows)>50 else None,
                        coverage='EXACT_SCOPE_BILL_AUDIT_ONLY',finance_status='UNCONFIRMED')
        if operation=='bill_rows':
            offset=p['offset']
            if type(offset) is not int or not 0<=offset<=100000:raise ValueError('INVALID_BILL_PAGE')
            # Raw consumer identifiers stay encrypted; page returns only fields
            # needed by finance reconciliation, never openid/bank/card columns.
            allowed={'交易时间','商户订单号','微信订单号','商户退款单号','微信退款单号','交易状态','退款状态','订单金额','总金额','退款金额','商户分账单号','分账金额','分账结果','特约商户号','币种','货币种类'}
            # Provider tickets are submerchant-wide, whereas grants are scoped
            # to a store. A field allowlist alone cannot establish row ownership.
            with c.tx():
                current,current_policy=a._authorize(session,csrf,workspace)
                if (any(current[k]!=g[k] for k in ('scope','project','user_id'))
                        or current_policy!=policy):raise PermissionError('BILL_AUTHORIZATION_CHANGED')
                records=[];unattributed=0
                t,m,s=(g['scope'][k] for k in ('tenant_id','merchant_id','store_id'))
                owned={provider_order_reference(a.reader._mchid,g['scope'],ref):tx
                    for ref,tx in a.runtime.demo.db.execute('SELECT reference,provider_transaction_id FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=?',(t,m,s))}
                for row in bill['rows'][offset:offset+50]:
                    if bill['kind']=='TRADE':
                        tx=owned.get(row.get('商户订单号'))
                        proven=bool(tx) and row.get('微信订单号')==tx
                        refund=row.get('商户退款单号')
                        if proven and refund and refund not in ('0','无','-'):
                            action=a._load(hashlib.sha256(canonical([a.reader._mchid,'REFUND',refund])).hexdigest())
                            proven=(type(action) is dict and action.get('scope')==g['scope'] and action.get('project')==g['project']
                                and action.get('payload',{}).get('out_trade_no')==row['商户订单号'])
                    else:
                        ref=row.get('商户分账/回退单号',row.get('商户分账单号'))
                        action=a._load(hashlib.sha256(canonical([a.reader._mchid,'SPLIT',ref])).hexdigest()) if ref else None
                        proven=(type(action) is dict and action.get('kind')=='SPLIT' and action.get('scope')==g['scope']
                            and action.get('project')==g['project'] and action.get('payload',{}).get('sub_mchid')==bill['sub_mchid']
                            and row.get('业务类型','分出')=='分出'
                            and ('微信订单号' not in row or row['微信订单号']==action.get('transaction_id')))
                    if proven:
                        records.append({k:v for k,v in row.items() if k in allowed})
                    else:
                        unattributed+=1
                        # Preserve page positions, but expose only already-known
                        # merchant/currency constants for unproven rows.
                        records.append({k:v for k,v in row.items()
                            if k=='特约商户号' and v==policy['sub_mchid'] or k in ('币种','货币种类') and v=='CNY'})
                current,current_policy=a._authorize(session,csrf,workspace)
                if (any(current[k]!=g[k] for k in ('scope','project','user_id'))
                        or current_policy!=policy):raise PermissionError('BILL_AUTHORIZATION_CHANGED')
            return dict(records=records,has_more=offset+50<len(bill['rows']),next_offset=offset+50 if offset+50<len(bill['rows']) else None,
                unattributed_rows_redacted=unattributed,coverage='CURRENT_SCOPE_PROVEN_ROWS_ONLY')
        with c.tx():
            current,current_policy=a._authorize(session,csrf,workspace)
            if (any(current[k]!=g[k] for k in ('scope','project','user_id'))
                    or current_policy!=policy):raise PermissionError('BILL_AUTHORIZATION_CHANGED')
            result=self.reconcile(g,bill)
            current,current_policy=a._authorize(session,csrf,workspace)
            if (any(current[k]!=g[k] for k in ('scope','project','user_id'))
                    or current_policy!=policy):raise PermissionError('BILL_AUTHORIZATION_CHANGED')
            event=hashlib.sha256(canonical([key,result])).hexdigest()
            c.db.execute("INSERT OR IGNORE INTO links VALUES('COMMUNITY_BILL_RECONCILIATION',?,?,?,?,1)",(event,g['user_id'],g['project'],c.encrypt(canonical(dict(bill_key=key,kind=p['kind'],bill_date=p['bill_date'],scope=g['scope'],result=result)),'community-bill-reconciliation:'+event)))
            c.audit(g['project'],g['user_id'],'PROVIDER_BILL_RECONCILED',event)
        return result
    def _split_local_inventory(self,g,bill):
        """Capture all local split/return records, not a provider business day.

        Both channels and the original audit anchor are read in one SQLite
        transaction. The encrypted immutable manifest makes the digest auditable
        after live records change. This proves local enumeration at capture only:
        it cannot cover external initiators, automatic expiry, or bill-date rules.
        """
        c=self.center
        if not c.db.in_transaction:
            with c.tx():return self._split_local_inventory(g,bill)
        captured_at=c.now()
        anchor=c.db.execute('SELECT seq,sha FROM audit WHERE project=? ORDER BY seq DESC LIMIT 1',(g['project'],)).fetchone()
        watermark=dict(seq=anchor[0],sha256=anchor[1]) if anchor else dict(seq=0,sha256='0'*64)
        records=[];local={};candidates=[]
        counts={name:0 for name in ('split_records','return_records','inactive_records','invalid_binding_records',
            'split_terminal_records','split_nonterminal_records','split_missing_evidence_records',
            'split_terminal_missing_evidence_records','split_invalid_evidence_records',
            'return_terminal_records','return_nonterminal_records','return_missing_evidence_records',
            'return_terminal_missing_evidence_records','return_invalid_evidence_records',
            'successful_split_details','closed_split_details','successful_return_records','failed_return_records')}
        source=c.db.execute("SELECT channel,subject_idx,payload,active FROM links WHERE project=? AND channel IN ('COMMUNITY_PROVIDER_ACTION','COMMUNITY_PROVIDER_RETURN') ORDER BY channel,subject_idx",(g['project'],))
        for channel,key,encrypted,active in source:
            aad=('provider-action:' if channel=='COMMUNITY_PROVIDER_ACTION' else 'community-provider-return:')+key
            saved=json.loads(c.decrypt(encrypted,aad))
            if type(saved) is not dict:raise ValueError('INVALID_LOCAL_BILL_INVENTORY_RECORD')
            scope=saved.get('scope')
            if (type(scope) is not dict or set(scope)!={'tenant_id','merchant_id','store_id'}
                    or any(type(v) is not str or not 1<=len(v)<=128 for v in scope.values())):
                raise ValueError('UNCLASSIFIABLE_LOCAL_BILL_INVENTORY_SCOPE')
            if saved.get('scope')!=g['scope']:continue
            if channel=='COMMUNITY_PROVIDER_ACTION' and saved.get('kind')=='REFUND':continue
            kind='SPLIT' if channel=='COMMUNITY_PROVIDER_ACTION' else 'RETURN'
            records.append(dict(channel=channel,key=key,active=active,record=saved))
            counts['split_records' if kind=='SPLIT' else 'return_records']+=1
            if active!=1:counts['inactive_records']+=1
            payload=saved.get('payload',{})
            ref=saved.get('provider_reference') if kind=='SPLIT' else payload.get('out_return_no') if type(payload) is dict else None
            expected=hashlib.sha256(canonical([self.actions.reader._mchid,kind,ref])).hexdigest()
            if (not _evidence_id(ref) or key!=expected or saved.get('project')!=g['project']
                    or type(payload) is not dict or payload.get('sub_mchid')!=bill['sub_mchid']
                    or kind=='SPLIT' and (saved.get('kind')!='SPLIT' or 'result' in saved and type(saved['result']) is not dict)):
                counts['invalid_binding_records']+=1;continue
            forward=dict(saved)
            if active==1 and kind=='SPLIT':local.setdefault(ref,[]).append(forward)
            prefix='split' if kind=='SPLIT' else 'return'
            result=saved.get('result',{}) if kind=='SPLIT' else saved.get('result')
            status=result.get('status') if type(result) is dict else result
            terminal=status=='FINISHED' if kind=='SPLIT' else status in ('SUCCESS','FAILED')
            counts[prefix+('_terminal_records' if terminal else '_nonterminal_records')]+=1
            if kind=='RETURN' and status in ('SUCCESS','FAILED'):
                counts['successful_return_records' if status=='SUCCESS' else 'failed_return_records']+=1
            evidence=saved.get('bill_evidence')
            if evidence is None:
                counts[prefix+'_missing_evidence_records']+=1
                if terminal:counts[prefix+'_terminal_missing_evidence_records']+=1
                continue
            try:
                if (type(evidence) is not dict or evidence.get('version')!=BILL_EVIDENCE_VERSION
                        or evidence.get('kind')!=kind or not terminal):raise ValueError()
                detail=evidence['details']
                data=dict(detail,**({'state':'FINISHED'} if kind=='SPLIT' else {'result':'SUCCESS'}))
                if signed_bill_evidence(data,evidence['body_sha256'],kind)!=evidence:raise ValueError()
                fields=('sub_mchid','out_order_no','transaction_id') if kind=='SPLIT' else ('sub_mchid','out_order_no','out_return_no','return_mchid','amount')
                if any(detail[k]!=payload.get(k) for k in fields):raise ValueError()
                if kind=='RETURN':
                    if (status!='SUCCESS' or type(detail['amount']) is not int or detail['amount']<=0
                            or type(payload['amount']) is not int or payload['amount']<=0):raise ValueError()
                    continue  # The CSV return join is not established by this API.
                if detail['transaction_id']!=saved.get('transaction_id') or detail['out_order_no']!=ref:raise ValueError()
                receivers=detail['receivers']
                intended=sorted((r['type'],r['account'],r['amount']) for r in payload['receivers'])
                observed=sorted((r['type'],r['account'],r['amount']) for r in receivers)
                if (observed!=intended
                        or any(type(r['amount']) is not int or r['amount']<=0 or r['type'] not in ('MERCHANT_ID','PERSONAL_OPENID')
                               or type(r['account']) is not str or not r['account'] for r in receivers+payload['receivers'])
                        or any(r['result'] not in ('SUCCESS','CLOSED') for r in receivers)):raise ValueError()
                for receiver in receivers:
                    counts['successful_split_details' if receiver['result']=='SUCCESS' else 'closed_split_details']+=1
                    if active==1 and receiver['result']=='SUCCESS':
                        identity=(ref,detail['order_id'],detail['transaction_id'],receiver['detail_id'])
                        candidates.append((identity,c.idx('bill-inventory-detail:'+canonical([g['scope'],key,receiver['detail_id']]).decode())))
            except (ValueError,TypeError,KeyError,AttributeError):
                counts[prefix+'_invalid_evidence_records']+=1
                forward['_bill_inventory_evidence_invalid']=True
        manifest=dict(version='LOCAL_SPLIT_RETURN_SNAPSHOT_V1',scope=g['scope'],project=g['project'],
                      captured_at=captured_at,audit_watermark=watermark,records=records)
        digest=hashlib.sha256(canonical(manifest)).hexdigest()
        c.db.execute("INSERT OR IGNORE INTO links VALUES('COMMUNITY_BILL_LOCAL_SNAPSHOT',?,?,?,?,1)",
            (digest,g['user_id'],g['project'],c.encrypt(canonical(manifest),'community-bill-local-snapshot:'+digest)))
        bill_ids={(r['商户分账/回退单号'],r['微信分账/回退单号'],r['微信订单号'],r['分账明细单号'])
                  for r in bill['rows'] if r['业务类型']=='分出'}
        absent=sorted(token for identity,token in candidates if identity not in bill_ids)
        return local,dict(coverage='ALL_PERSISTED_SCOPE_SPLIT_RETURN_RECORDS_AT_CAPTURE',
            snapshot_sha256=digest,captured_at=captured_at,audit_watermark=watermark,
            cutoff_basis='LOCAL_SQLITE_SNAPSHOT_NOT_PROVIDER_BUSINESS_DATE',counts=counts,
            runtime_order_database='NOT_INCLUDED_IN_LOCAL_SNAPSHOT',
            provider_population_completeness='NOT_ESTABLISHED',bill_date_membership='NOT_ASSIGNED',
            reverse_candidates=dict(coverage='SUCCESSFUL_ACTIVE_LOCAL_SPLIT_DETAILS_WITHOUT_DATE_FILTER',
                absent_from_selected_bill_count=len(absent),opaque_detail_tokens=absent[:200],
                truncated=len(absent)>200,establishes_missing_bill_rows=False),
            complete_reconciliation_available=False)
    def _reconcile_split_details(self,g,bill):
        # Only ordinary successful split rows have a fully documented detail join.
        # Return APIs expose return_id but no bill detail_id. Unfreeze/return rows
        # remain explicit unknowns; no aggregate or identifier-shape inference.
        local,inventory=self._split_local_inventory(g,bill)
        matched=0;exceptions=[];unknown=[];seen=set()
        for index,row in enumerate(bill['rows']):
            def issue(reason):exceptions.append(dict(row=index,reason=reason))
            def unresolved(reason):unknown.append(dict(row=index,reason=reason))
            if row['业务类型']!='分出':
                unresolved('RETURN_DETAIL_JOIN_UNVERIFIED' if row['业务类型']=='分账回退' else 'UNFREEZE_DETAIL_JOIN_UNVERIFIED');continue
            if row['分账发起方']!=self.actions.reader._mchid or row['分账方']!=bill['sub_mchid']:
                issue('BILL_MERCHANT_BINDING_MISMATCH');continue
            identity=row['分账明细单号']
            if identity in seen:issue('DUPLICATE_PROVIDER_DETAIL');continue
            seen.add(identity)
            candidates=local.get(row['商户分账/回退单号'],[])
            if len(candidates)!=1:
                unresolved('LOCAL_SPLIT_EVIDENCE_MISSING_OR_AMBIGUOUS');continue
            action=candidates[0];evidence=action.get('bill_evidence')
            if action.get('_bill_inventory_evidence_invalid'):
                unresolved('INVALID_LOCAL_SIGNED_DETAIL_EVIDENCE');continue
            if (action.get('result',{}).get('status')!='FINISHED' or type(evidence) is not dict
                    or evidence.get('version')!=BILL_EVIDENCE_VERSION or evidence.get('kind')!='SPLIT'):
                unresolved('SIGNED_DETAIL_EVIDENCE_REQUIRED');continue
            detail=evidence['details'];payload=action['payload']
            if (detail['sub_mchid']!=bill['sub_mchid'] or payload.get('sub_mchid')!=bill['sub_mchid']
                    or detail['transaction_id']!=row['微信订单号'] or action['transaction_id']!=row['微信订单号']
                    or payload.get('transaction_id')!=row['微信订单号']
                    or payload.get('out_order_no')!=row['商户分账/回退单号']
                    or detail['order_id']!=row['微信分账/回退单号']
                    or detail['out_order_no']!=row['商户分账/回退单号']):
                issue('SPLIT_PROVIDER_IDENTITY_MISMATCH');continue
            receivers=[r for r in detail['receivers'] if r['detail_id']==identity]
            if len(receivers)!=1:issue('SPLIT_DETAIL_ID_MISMATCH');continue
            receiver=receivers[0]
            intents=[r for r in payload['receivers'] if r['type']==receiver['type'] and r['account']==receiver['account']]
            if len(intents)!=1:
                unresolved('FROZEN_RECEIVER_BINDING_AMBIGUOUS');continue
            if (receiver['account']!=row['分账接收方'] or receiver['amount']!=minor(row['金额'])
                    or intents[0]['amount']!=receiver['amount'] or receiver['result']!='SUCCESS'
                    or row['处理状态']!='成功'):
                issue('SPLIT_RECEIVER_AMOUNT_OR_STATE_MISMATCH');continue
            t,m,st=(g['scope'][k] for k in ('tenant_id','merchant_id','store_id'))
            order=self.actions.runtime.demo.db.execute('SELECT amount_minor,provider_transaction_id FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,st,action['reference'])).fetchone()
            if order is None:unresolved('ORIGINAL_PAYMENT_EVIDENCE_REQUIRED');continue
            if order[0]!=minor(row['订单金额']) or order[1]!=row['微信订单号']:
                issue('SPLIT_ORIGINAL_PAYMENT_MISMATCH');continue
            matched+=1
        status=('EXCEPTION' if exceptions else 'DETAIL_FIELDS_MATCH_RECONCILIATION_PENDING' if matched and not unknown
                else 'PARTIAL_DETAIL_FIELDS_MATCH_RECONCILIATION_PENDING' if matched
                else 'SCHEMA_RECOGNIZED_RECONCILIATION_PENDING')
        local_incomplete=any(value for name,value in inventory['counts'].items()
            if any(word in name for word in ('inactive','invalid','missing','nonterminal')))
        return dict(status=status,schema=dict(bill['schema']),matched_detail_rows=matched,total_rows=len(bill['rows']),
                    exceptions=exceptions[:200],exceptions_truncated=len(exceptions)>200,
                    unknown_rows=unknown[:200],unknown_rows_truncated=len(unknown)>200,
                    body_sha256=bill['body_sha256'],coverage='SPLIT_DETAIL_IDENTITIES_AND_AMOUNTS_ONLY',
                    time_coverage='UNKNOWN_BILL_TIMEZONE',reverse_coverage='NOT_ESTABLISHED',
                    local_inventory=inventory,
                    summary_amounts='NOT_RECONCILED',
                    sample_arithmetic=sample_summary_diagnostic(bill),
                    summary_evidence=('PROVIDER_REPORTED_VALUES_RETAINED' if bill.get('reported_summary') is not None
                                      else 'LEGACY_SUMMARY_VALUES_NOT_RETAINED'),
                    pending_evidence=['BILL_TIMEZONE','SUMMARY_AMOUNT_SEMANTICS',
                                      'BILL_DATE_MEMBERSHIP_RULE','PROVIDER_POPULATION_COMPLETENESS']+
                        (['LOCAL_SIGNED_DETAIL_EVIDENCE_COMPLETENESS'] if local_incomplete else [])+
                        sorted({r['reason'] for r in unknown}),
                    finance_status='UNCONFIRMED',funds_retry_authorized=False)

    def reconcile(self,g,bill):
        a=self.actions;rows=bill['rows'];columns=set(bill['columns']);exceptions=[];matched=0;seen=set();missing=[];undated=0;reverse='NOT_APPLICABLE_TO_SPLIT_LAYOUT'
        if (bill['kind']=='SPLIT' and tuple(bill['columns'])==SPLIT_COLUMNS
                and type(bill.get('schema')) is dict
                and bill['schema'].get('id')==SPLIT_SCHEMA):
            return self._reconcile_split_details(g,bill)
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
