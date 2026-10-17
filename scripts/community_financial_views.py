"""Scoped provider-operation pages and signed per-order reconciliation evidence.

These are observed transaction records, never a replacement Finance ledger or
an assertion that an official daily bill or settlement has reconciled.
"""
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical
from scripts.community_order_store import state
from scripts.community_provider_reference import provider_order_reference
from scripts.community_order_provider_projection import project_verified_query, provider_evidence


class FinancialViews:
    def __init__(self, actions):
        self.actions, self.center = actions, actions.center

    def dispatch(self, session, csrf, workspace, operation, params):
        fields = {'financial_records': {'kind', 'after_id'}, 'reconcile_order': {'reference'},
                  'reconciliation_read': {'reference'}}
        if operation not in fields or type(params) is not dict or set(params) != fields[operation]:
            raise ValueError('INVALID_FINANCIAL_VIEW_FIELDS')
        g, policy = self.actions._authorize(session, csrf, workspace)
        c, a, p = self.center, self.actions, params
        with c.tx():c.limit('community-financial-requests:'+g['user_id'],30,60)
        if operation == 'financial_records':
            if p['kind'] not in ('REFUND', 'SPLIT', 'RETURN') or type(p['after_id']) is not str or p['after_id'] and not re.fullmatch('[0-9a-f]{64}', p['after_id']):
                raise ValueError('INVALID_FINANCIAL_PAGE')
            channel = 'COMMUNITY_PROVIDER_RETURN' if p['kind']=='RETURN' else 'COMMUNITY_PROVIDER_ACTION'
            rows = c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51', (channel, g['project'], p['after_id'])).fetchall()
            records = []
            scope_hash = hashlib.sha256(canonical(g['scope'])).hexdigest()
            for key, payload in rows[:50]:
                saved = json.loads(c.decrypt(payload, ('community-provider-return:' if p['kind']=='RETURN' else 'provider-action:') + key))
                if p['kind']=='RETURN':
                    if saved['scope'] != g['scope']:
                        continue
                    from scripts.community_split_returns import SplitReturns
                    records.append(SplitReturns(a).summary(saved))
                elif saved['scope_hash'] == scope_hash and saved['kind'] == p['kind']:
                    record = a._summary(saved)
                    if saved.get('result') is not None:
                        record['result'] = saved['result']
                    records.append(record)
            with c.tx():
                c.limit('community-financial-read:' + g['user_id'], 60, 60)
                c.audit(g['project'], g['user_id'], 'COMMUNITY_FINANCIAL_PAGE', p['kind'])
            return dict(records=records, has_more=len(rows)>50, next_cursor=rows[49][0] if len(rows)>50 else None,
                scope=g['scope'], finance_status='UNCONFIRMED', totals_scope='CURRENT_PAGE_ONLY')
        from scripts.community_merchant_contract import valid_id
        if not valid_id(p['reference']):
            raise ValueError('INVALID_RECONCILIATION_REFERENCE')
        key = hashlib.sha256(canonical([g['scope'], p['reference']])).hexdigest()
        if operation == 'reconciliation_read':
            row = c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_ORDER_RECONCILIATION' AND subject_idx=? AND project=? AND active=1", (key, g['project'])).fetchone()
            if row is None:
                raise ValueError('ORDER_RECONCILIATION_NOT_FOUND')
            return json.loads(c.decrypt(row[0], 'community-order-reconciliation:' + key))
        original = state(a.runtime.demo.db, g['scope'], p['reference'])
        expected = dict(sp_mchid=a.reader._mchid, sub_mchid=policy['sub_mchid'], sp_appid=policy['sp_appid'],
            out_trade_no=provider_order_reference(a.reader._mchid, g['scope'], p['reference']), amount_minor=original['amount_minor'], currency='CNY')
        observation = a.reader.read_order(expected)
        if a._authorize(session, csrf, workspace)[1] != policy:
            raise PermissionError('RECONCILIATION_POLICY_CHANGED')
        if state(a.runtime.demo.db, g['scope'], p['reference']) != original:
            raise ValueError('ORDER_CHANGED_DURING_RECONCILIATION')
        project_verified_query(a.runtime.demo.db, g['scope'], p['reference'], expected, observation, c.now(), a.reader._kid)
        order = state(a.runtime.demo.db, g['scope'], p['reference'])
        refunded = 0
        t, m, s = (g['scope'][k] for k in ('tenant_id','merchant_id','store_id'))
        for raw, in a.runtime.demo.db.execute('SELECT evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?', (t,m,s,p['reference'])):
            try:
                event = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if type(event) is dict and event.get('source') == 'WECHAT_SIGNED_REFUND_RESULT':
                refunded += event['refund_minor']
        lock = c.idx('provider-order-action:' + a.reader._mchid + ':' + expected['out_trade_no'])
        locked = c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=? AND active=1", (lock,)).fetchone() is not None
        anomalies = []
        if locked:
            anomalies.append('UNKNOWN_OR_PROCESSING_FUNDS_OPERATION')
        if observation['provider_state']=='REFUND' and refunded==0:
            anomalies.append('PROVIDER_REFUND_WITHOUT_LOCAL_REFUND_CONFIRMATION')
        if refunded > order['amount_minor']:
            anomalies.append('REFUND_TOTAL_EXCEEDS_ORIGINAL_PAYMENT')
        if refunded and observation['provider_state'] not in ('SUCCESS','REFUND'):
            anomalies.append('REFUND_AND_PROVIDER_PAYMENT_STATE_CONFLICT')
        if provider_evidence(a.runtime.demo.db,g['scope'],p['reference']) is None and order['state']!='PENDING':
            anomalies.append('LOCAL_STATE_HAS_NO_TRUSTED_PROVIDER_EVIDENCE')
        result = dict(reference=p['reference'], scope=g['scope'], original_amount_minor=order['amount_minor'],
            currency='CNY', provider_state=observation['provider_state'], local_order_state=order['state'],
            confirmed_local_refunds_minor=refunded, provider_body_sha256=observation['body_sha256'],
            observed_at=c.now(), anomalies=anomalies, status='EXCEPTION' if anomalies else 'OBSERVATIONS_MATCH',
            coverage='ORDER_OBSERVATIONS_ONLY', daily_bill_reconciled=False, finance_status='UNCONFIRMED',
            funds_retry_authorized=False)
        with c.tx():
            c.limit('community-reconcile:' + g['user_id'], 20, 60)
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_ORDER_RECONCILIATION',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload", (key,g['user_id'],g['project'],c.encrypt(canonical(result),'community-order-reconciliation:'+key)))
            event = hashlib.sha256(canonical(result)).hexdigest()
            c.db.execute("INSERT OR IGNORE INTO links VALUES('COMMUNITY_RECONCILIATION_HISTORY',?,?,?,?,1)", (event,g['user_id'],g['project'],c.encrypt(canonical(result),'community-reconciliation-history:'+event)))
            c.audit(g['project'],g['user_id'],'COMMUNITY_ORDER_RECONCILED',event)
        return result
