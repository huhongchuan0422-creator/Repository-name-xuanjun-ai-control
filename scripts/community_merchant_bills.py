"""Explicit merchant-wide read/reconcile grant on the existing Center.

This capability is deliberately separate from ProviderActions authorization.
It never submits funds operations or installs grants into the original runtime.
Configured local stores are not a proof of provider population completeness.
"""
import datetime as dt
import hashlib
import json
import re
import urllib.parse

from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import scope, valid_id
from scripts.community_provider_bills import ProviderBills, SPLIT_COLUMNS, _parse_document, sample_summary_diagnostic
from scripts.community_provider_reference import provider_order_reference
from scripts.community_wechat_sp_actions import ProviderActions

PERMISSION = 'SUBMERCHANT_ALL_STORES_BILL_READ_RECONCILE'
FIELDS = {'finance_workspace', 'user_id', 'project', 'tenant_id', 'merchant_id',
          'sp_mchid', 'sub_mchid', 'revision', 'permission'}
OPERATIONS = {'bill_fetch': {'kind', 'bill_date'},
              'bill_rows': {'kind', 'bill_date', 'offset'},
              'bill_reconcile': {'kind', 'bill_date'},
              'bill_audit': {'kind', 'bill_date', 'after_id'}}
CHANNEL = 'COMMUNITY_MERCHANT_BILL'
AUDIT_CHANNEL = 'COMMUNITY_MERCHANT_BILL_AUDIT'
ROW_FIELDS = {'交易时间', '商户订单号', '微信订单号', '商户退款单号', '微信退款单号',
    '交易状态', '退款状态', '订单金额', '总金额', '退款金额', '商户分账单号',
    '分账金额', '分账结果', '特约商户号', '币种', '货币种类', '分账时间',
    '微信分账/回退单号', '分账明细单号', '商户分账/回退单号', '金额', '业务类型', '处理状态'}


def _copy(value):
    return json.loads(canonical(value))


def _hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class _ProjectLedger:
    """Narrow read adapter: original storage, with no money/authorization API."""
    def __init__(self, actions, project):
        self.center, self.reader, self.runtime = actions.center, actions.reader, actions.runtime
        # Read-only snapshot of the original admitted receiver policies. ProviderBills
        # needs only receiver/sub_appid validation; this adapter still exposes no
        # authorization or money-operation methods.
        self.bindings = {identity: _copy(policy) for identity, policy in actions.bindings.items()}
        self.project = project

    def _load(self, key):
        row = self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION' AND subject_idx=? AND project=? AND active=1",
            (key, self.project)).fetchone()
        if row is None:
            return None
        value = json.loads(self.center.decrypt(row[0], 'provider-action:' + key))
        if type(value) is not dict or value.get('project') != self.project:
            raise PermissionError('LOCAL_ACTION_PROJECT_BINDING_CHANGED')
        return value


class MerchantBills:
    def __init__(self, actions, grants=None):
        if type(actions) is not ProviderActions or grants is not None and type(grants) is not dict:
            raise ValueError('ORIGINAL_ACTIONS_AND_EXPLICIT_BILL_GRANTS_REQUIRED')
        self.actions, self.center = actions, actions.center
        self.grants = {}
        for workspace, grant in (grants or {}).items():
            self._validate(workspace, grant)
            self.grants[workspace] = _copy(grant)
        self.bills = ProviderBills(actions)

    @staticmethod
    def _validate(workspace, grant):
        if (not valid_id(workspace) or type(grant) is not dict or set(grant) != FIELDS
                or any(not valid_id(grant[k]) for k in
                    ('finance_workspace', 'user_id', 'project', 'tenant_id', 'merchant_id'))
                or type(grant['revision']) is not int or grant['revision'] < 1
                or grant['permission'] != PERMISSION
                or any(type(grant[k]) is not str or not re.fullmatch(r'[0-9]{6,32}', grant[k])
                       for k in ('sp_mchid', 'sub_mchid'))):
            raise PermissionError('EXPLICIT_MERCHANT_BILL_GRANT_REQUIRED')

    def _context(self, session, csrf, workspace):
        grant = self.grants.get(workspace)
        self._validate(workspace, grant)
        grant = _copy(grant)
        original, policy = self.actions._authorize(session, csrf, grant['finance_workspace'])
        if (original['user_id'] != grant['user_id'] or original['project'] != grant['project']
                or original['tenant'] != grant['tenant_id']
                or original['scope']['tenant_id'] != grant['tenant_id']
                or original['scope']['merchant_id'] != grant['merchant_id']
                or self.actions.reader._mchid != grant['sp_mchid']
                or policy['sub_mchid'] != grant['sub_mchid']):
            raise PermissionError('MERCHANT_BILL_GRANT_BINDING_CHANGED')
        project, project_role, _ = self.center.project(grant['user_id'], grant['project'], original['project_roles'])
        bindings = []
        for identity, configured in list(self.actions.bindings.items()):
            if type(configured) is not dict:
                raise PermissionError('INVALID_PROVIDER_STORE_BINDING')
            if configured.get('sub_mchid') != grant['sub_mchid']:
                continue
            if type(identity) is not tuple or len(identity) != 3:
                raise PermissionError('INVALID_PROVIDER_STORE_BINDING')
            target = dict(zip(('tenant_id', 'merchant_id', 'store_id'), identity))
            scope(target)
            if identity[:2] != (grant['tenant_id'], grant['merchant_id']):
                raise PermissionError('SUBMERCHANT_CROSS_SUBJECT_BINDING_CONFLICT')
            bindings.append({'scope': target, 'policy': _copy(configured)})
        bindings.sort(key=lambda x: x['scope']['store_id'])
        if not bindings:
            raise PermissionError('MERCHANT_LOCAL_BINDINGS_REQUIRED')
        epoch = self.center.db.execute('SELECT epoch FROM accounts WHERE id=?', (grant['user_id'],)).fetchone()[0]
        anchor = {k: _copy(original[k]) for k in ('user_id', 'project', 'tenant', 'scope', 'role', 'project_roles')}
        anchor['principal_identity'] = id(original['principal'])
        return dict(grant=grant, anchor=anchor, policy=policy, bindings=bindings,
            account_epoch=epoch, project_role=project_role,
            project={k: project[k] for k in ('id', 'tenant', 'customer', 'owner', 'revision', 'expires', 'active')})

    def _check(self, session, csrf, workspace, context):
        if canonical(self._context(session, csrf, workspace)) != canonical(context):
            raise PermissionError('MERCHANT_BILL_AUTHORIZATION_CHANGED')

    @staticmethod
    def _scope(context):
        return {k: context['grant'][k] for k in ('project', 'tenant_id', 'merchant_id', 'sp_mchid', 'sub_mchid')}

    def _key(self, context, params):
        return _hash(['MERCHANT_BILL_V1', self._scope(context), params['kind'], params['bill_date']])

    @staticmethod
    def _bound_row(context, bill, row):
        """Use only already-known merchant fields; unknown directions stay private."""
        grant = context['grant']
        if '特约商户号' in row:
            if row['特约商户号'] != grant['sub_mchid']:
                raise PermissionError('MERCHANT_BILL_SUBMERCHANT_MISMATCH')
            columns = set(bill['columns'])
            if (bill['kind'] == 'TRADE'
                    and {'商户订单号', '微信订单号', '交易状态'}.issubset(columns)
                    and ('订单金额' in columns or '总金额' in columns)):
                return True
        if bill['kind'] == 'SPLIT' and tuple(bill['columns']) == SPLIT_COLUMNS and row.get('业务类型') == '分出':
            if row['分账发起方'] != grant['sp_mchid'] or row['分账方'] != grant['sub_mchid']:
                raise PermissionError('MERCHANT_BILL_SUBMERCHANT_MISMATCH')
            return True
        # Return/unfreeze directions and unknown layouts cannot be invented from
        # an API ticket that does not echo its request merchant. Keep encrypted.
        return False

    def _read(self, context, key, params):
        row = self.center.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',
            (CHANNEL, key, context['grant']['project'])).fetchone()
        if row is None:
            raise ValueError('VERIFIED_MERCHANT_BILL_NOT_FOUND')
        value = json.loads(self.center.decrypt(row[0], 'merchant-bill:' + key))
        if (type(value) is not dict or value.get('merchant_scope') != self._scope(context)
                or value.get('kind') != params['kind'] or value.get('bill_date') != params['bill_date']
                or value.get('sub_mchid') != context['grant']['sub_mchid']):
            raise PermissionError('MERCHANT_BILL_CACHE_BINDING_CHANGED')
        for row in value['rows']:
            self._bound_row(context, value, row)
        return value

    def dispatch(self, session, csrf, body):
        if (type(body) is not dict or set(body) != {'workspace', 'operation', 'params'}
                or type(body['workspace']) is not str or type(body['operation']) is not str
                or body['operation'] not in OPERATIONS or type(body['params']) is not dict):
            raise PermissionError('MERCHANT_BILL_READ_ONLY_OPERATION_REQUIRED')
        workspace, operation, params = body['workspace'], body['operation'], body['params']
        allowed = OPERATIONS[operation]
        if (set(params) != allowed and not (operation == 'bill_reconcile' and set(params) == allowed | {'require_complete'})
                or params.get('kind') not in ('TRADE', 'SPLIT')
                or 'require_complete' in params and type(params['require_complete']) is not bool):
            raise ValueError('INVALID_MERCHANT_BILL_FIELDS')
        if (type(params['bill_date']) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', params['bill_date'])):
            raise ValueError('INVALID_BILL_DATE')
        date = dt.date.fromisoformat(params['bill_date'])
        today = dt.datetime.fromtimestamp(self.center.now(), dt.timezone(dt.timedelta(hours=8))).date()
        if not 0 < (today - date).days <= 90:
            raise ValueError('BILL_DATE_OUTSIDE_SUPPORTED_HISTORY')
        context = self._context(session, csrf, workspace)
        if params.get('require_complete'):
            raise ValueError('COMPLETE_MERCHANT_BILL_RECONCILIATION_UNAVAILABLE')
        key = self._key(context, params)
        grant = context['grant']
        c = self.center
        with c.tx():
            c.limit('community-merchant-bill:' + grant['user_id'], 10, 60)
        if operation == 'bill_fetch':
            query = dict(sub_mchid=grant['sub_mchid'], bill_date=params['bill_date'])
            if params['kind'] == 'TRADE':
                query['bill_type'] = 'ALL'
            target = ('/v3/bill/tradebill' if params['kind'] == 'TRADE' else '/v3/profitsharing/bills') + '?' + urllib.parse.urlencode(query)
            self._check(session, csrf, workspace, context)
            ticket, ticket_digest = self.actions._call('GET', target)
            self._check(session, csrf, workspace, context)
            if (ticket.get('hash_type') != 'SHA1' or type(ticket.get('hash_value')) is not str
                    or not re.fullmatch(r'[0-9a-fA-F]{40}', ticket['hash_value'])
                    or type(ticket.get('download_url')) is not str):
                raise ValueError('INVALID_SIGNED_BILL_TICKET')
            raw = self.bills._download(ticket['download_url'])
            self._check(session, csrf, workspace, context)
            if hashlib.sha1(raw).hexdigest() != ticket['hash_value'].lower():
                raise PermissionError('PROVIDER_BILL_HASH_MISMATCH')
            columns, rows, schema, summary = _parse_document(raw)
            record = dict(merchant_scope=self._scope(context), sub_mchid=grant['sub_mchid'],
                kind=params['kind'], bill_date=params['bill_date'], columns=columns, rows=rows,
                schema=schema, reported_summary=summary, body_sha256=hashlib.sha256(raw).hexdigest(),
                ticket_sha256=ticket_digest, provider_sha1=ticket['hash_value'].lower(), received_at=c.now())
            for row in rows:
                self._bound_row(context, record, row)
            with c.tx():
                self._check(session, csrf, workspace, context)
                previous = c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',
                    (CHANNEL, key, grant['project'])).fetchone()
                if previous and json.loads(c.decrypt(previous[0], 'merchant-bill:' + key))['body_sha256'] != record['body_sha256']:
                    raise ValueError('IMMUTABLE_MERCHANT_BILL_CHANGED_REVIEW_REQUIRED')
                if previous is None:
                    c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)', (CHANNEL, key, grant['user_id'], grant['project'],
                        c.encrypt(canonical(record), 'merchant-bill:' + key)))
                c.audit(grant['project'], grant['user_id'], 'MERCHANT_BILL_HASH_VERIFIED', record['body_sha256'])
                self._check(session, csrf, workspace, context)
            return dict(kind=params['kind'], bill_date=params['bill_date'], row_count=len(rows),
                body_sha256=record['body_sha256'], integrity='SIGNED_TICKET_HASH_VERIFIED',
                authorization_scope=PERMISSION, reconciliation='NOT_RUN', finance_status='UNCONFIRMED')
        with c.tx():
            self._check(session, csrf, workspace, context)
            bill = self._read(context, key, params)
            self._check(session, csrf, workspace, context)
            if operation == 'bill_rows':
                offset = params['offset']
                if type(offset) is not int or not 0 <= offset <= 100000:
                    raise ValueError('INVALID_BILL_PAGE')
                page = bill['rows'][offset:offset + 50]
                proven = [self._bound_row(context, bill, row) for row in page]
                result = dict(records=[{k: v for k, v in row.items() if k in ROW_FIELDS} if bound else {}
                    for row, bound in zip(page, proven)],
                    has_more=offset + 50 < len(bill['rows']),
                    next_offset=offset + 50 if offset + 50 < len(bill['rows']) else None,
                    unattributed_rows_redacted=proven.count(False),
                    authorization_scope=PERMISSION, coverage='PROVEN_SUBMERCHANT_FINANCIAL_FIELDS_ONLY',
                    finance_status='UNCONFIRMED')
            elif operation == 'bill_audit':
                after = params['after_id']
                if type(after) is not str or after and not re.fullmatch(r'[0-9a-f]{64}', after):
                    raise ValueError('INVALID_BILL_AUDIT_CURSOR')
                rows = c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51',
                    (AUDIT_CHANNEL + ':' + key, grant['project'], after)).fetchall()
                records = []
                for ref, payload in rows[:50]:
                    saved = json.loads(c.decrypt(payload, 'merchant-bill-audit:' + ref))
                    if type(saved) is not dict or _hash(saved) != ref:
                        raise ValueError('MERCHANT_BILL_AUDIT_INTEGRITY_CHANGED')
                    if saved.get('bill_key') != key or saved.get('merchant_scope') != self._scope(context):
                        raise PermissionError('MERCHANT_BILL_AUDIT_BINDING_CHANGED')
                    records.append(dict(id=ref, result=saved['result']))
                result = dict(records=records, has_more=len(rows) > 50,
                    next_cursor=rows[49][0] if len(rows) > 50 else None,
                    coverage='EXACT_MERCHANT_BILL_AUDIT_ONLY', finance_status='UNCONFIRMED')
            else:
                result = self._reconcile(context, bill)
                self._check(session, csrf, workspace, context)
                saved = dict(bill_key=key, merchant_scope=self._scope(context), result=result)
                ref = _hash(saved)
                c.db.execute('INSERT OR IGNORE INTO links VALUES(?,?,?,?,?,1)', (AUDIT_CHANNEL + ':' + key, ref,
                    grant['user_id'], grant['project'], c.encrypt(canonical(saved), 'merchant-bill-audit:' + ref)))
                c.audit(grant['project'], grant['user_id'], 'MERCHANT_BILL_RECONCILED', ref)
            self._check(session, csrf, workspace, context)
        return result

    def _reconcile(self, context, bill):
        """Partition rows once by proven original scope; never sum full bills."""
        grant = context['grant']
        scopes = {tuple(x['scope'][k] for k in ('tenant_id', 'merchant_id', 'store_id')): x['scope']
                  for x in context['bindings']}
        mapping, partitions = {}, {identity: [] for identity in scopes}
        if bill['kind'] == 'TRADE':
            for identity, target in scopes.items():
                for ref, tx in self.actions.runtime.demo.db.execute('SELECT reference,provider_transaction_id FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=?', identity):
                    key = provider_order_reference(grant['sp_mchid'], target, ref)
                    mapping.setdefault(key, []).append(identity)
        else:
            for key, encrypted in self.center.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION' AND project=? AND active=1", (grant['project'],)):
                saved = json.loads(self.center.decrypt(encrypted, 'provider-action:' + key))
                if type(saved) is not dict or saved.get('kind') != 'SPLIT':
                    continue
                target = saved.get('scope')
                if type(target) is not dict:
                    raise ValueError('UNCLASSIFIABLE_LOCAL_BILL_SCOPE')
                identity = tuple(target.get(k) for k in ('tenant_id', 'merchant_id', 'store_id'))
                if identity not in scopes:
                    continue
                ref = saved.get('provider_reference')
                if (saved.get('project') != grant['project'] or type(saved.get('payload')) is not dict
                        or saved['payload'].get('sub_mchid') != grant['sub_mchid']
                        or key != _hash([grant['sp_mchid'], 'SPLIT', ref])):
                    continue
                mapping.setdefault(ref, []).append(identity)
        unknown, duplicate, seen = [], [], set()
        for index, row in enumerate(bill['rows']):
            if bill['kind'] == 'TRADE':
                ref = row.get('商户订单号')
                identity = (ref, row.get('商户退款单号', ''))
            else:
                ref = row.get('商户分账/回退单号', row.get('商户分账单号'))
                identity = row.get('分账明细单号', ref)
                if row.get('业务类型', '分出') != '分出':
                    unknown.append(dict(row=index, reason='RETURN_OR_UNFREEZE_DETAIL_JOIN_UNVERIFIED'))
                    continue
            if identity in seen:
                duplicate.append(dict(row=index, reason='DUPLICATE_PROVIDER_ROW'))
                continue
            seen.add(identity)
            owners = mapping.get(ref, [])
            if len(owners) != 1:
                unknown.append(dict(row=index, reason='LOCAL_SCOPE_MISSING_OR_AMBIGUOUS'))
                continue
            partitions[owners[0]].append((index, row))
        stores, matched = [], 0
        ledger = ProviderBills(_ProjectLedger(self.actions, grant['project']))
        for identity, rows in partitions.items():
            target = scopes[identity]
            scoped_grant = dict(scope=target, project=grant['project'], user_id=grant['user_id'])
            subset = dict(bill, scope=target, rows=[row for _, row in rows], reported_summary=None)
            evidence = ledger.reconcile(scoped_grant, subset)
            for field in ('exceptions', 'unknown_rows'):
                for item in evidence.get(field, []):
                    if 'row' in item:
                        item['row'] = rows[item['row']][0]
            matched += evidence.get('matched_detail_rows', evidence.get('matched_rows', 0))
            stores.append(dict(scope=target, result=evidence))
        return dict(status='MERCHANT_EVIDENCE_RECONCILIATION_PENDING', total_rows=len(bill['rows']),
            matched_rows=matched, stores=stores, configured_store_count=len(scopes),
            unknown_rows=unknown[:200], unknown_rows_truncated=len(unknown) > 200,
            exceptions=duplicate[:200], exceptions_truncated=len(duplicate) > 200,
            authorization_scope=PERMISSION, local_coverage='ALL_CONFIGURED_LOCAL_STORES',
            provider_population_completeness='NOT_ESTABLISHED', summary_amounts='NOT_RECONCILED',
            sample_arithmetic=sample_summary_diagnostic(bill) if bill['kind'] == 'SPLIT' else None,
            complete_reconciliation_available=False, cross_database_atomic=False,
            body_sha256=bill['body_sha256'], finance_status='UNCONFIRMED', funds_retry_authorized=False)
