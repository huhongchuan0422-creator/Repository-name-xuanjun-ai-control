"""Service-provider split returns with durable reservations and signed queries.

Official /v3/profitsharing/return-orders supports merchant receivers only.
Personal receiver returns are unsupported and remain an explicit manual hold.
"""
import hashlib
import json
import urllib.parse
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import valid_id
from scripts.community_provider_reference import provider_order_reference


class SplitReturns:
    def __init__(self, actions):
        self.actions, self.center = actions, actions.center

    def _read(self, key):
        row = self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_RETURN' AND subject_idx=? AND active=1", (key,)).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0], 'community-provider-return:' + key))

    def refund_ready(self, g, budget):
        split = self.actions._load(budget['split_action'])
        if split is None or split.get('result', {}).get('status') != 'FINISHED':
            raise PermissionError('SPLIT_FINAL_RESULT_REQUIRED_BEFORE_REFUND')
        returned = {}
        for key in budget.get('return_actions', []):
            record = self._read(key)
            if record and record.get('result') == 'SUCCESS':
                returned[record['receiver_id']] = returned.get(record['receiver_id'], 0) + record['payload']['amount']
        for receiver in split['result']['receivers']:
            if receiver['result'] == 'SUCCESS' and returned.get(receiver['receiver_id'], 0) < receiver['amount_minor']:
                raise PermissionError('CONFIRMED_SPLIT_RETURN_REQUIRED_BEFORE_REFUND')

    def dispatch(self, session, csrf, workspace, operation, p):
        fields = {'split_return': {'reference', 'request_id', 'receiver_id', 'amount_minor', 'description'},
                  'query_split_return': {'reference', 'request_id'}, 'status_split_return': {'reference', 'request_id'}}
        if operation not in fields or type(p) is not dict or set(p) != fields[operation] or not valid_id(p['reference']) or not valid_id(p['request_id']):
            raise ValueError('INVALID_SPLIT_RETURN_FIELDS')
        a, c = self.actions, self.center
        g, policy = a._authorize(session, csrf, workspace)
        order_ref = provider_order_reference(a.reader._mchid, g['scope'], p['reference'])
        lock = c.idx('provider-order-action:' + a.reader._mchid + ':' + order_ref)
        return_ref = 'sr' + hashlib.sha256(canonical([a.reader._mchid, g['scope'], p['reference'], p['request_id']])).hexdigest()[:30]
        key = hashlib.sha256(canonical([a.reader._mchid, 'RETURN', return_ref])).hexdigest()
        saved = self._read(key)
        if saved and (saved['scope'] != g['scope'] or saved['project'] != g['project'] or saved['policy_hash'] != a._policy_hash(policy)):
            raise PermissionError('RETURN_BINDING_CHANGED')
        if operation == 'status_split_return':
            if saved is None:
                raise ValueError('SPLIT_RETURN_NOT_FOUND')
            return self.summary(saved)
        if operation == 'query_split_return':
            if saved is None:
                raise ValueError('SPLIT_RETURN_NOT_FOUND')
            target = '/v3/profitsharing/return-orders/' + return_ref + '?' + urllib.parse.urlencode(dict(sub_mchid=policy['sub_mchid'], out_order_no=saved['payload']['out_order_no']))
            data, digest = a._call('GET', target)
        else:
            if 'RETURN' not in policy['enabled_operations']:
                raise PermissionError('SPLIT_RETURN_NOT_ENABLED')
            request_hash = hashlib.sha256(canonical(p)).hexdigest()
            if saved:
                if saved['request_hash'] != request_hash:
                    raise PermissionError('SPLIT_RETURN_REQUEST_COLLISION')
                return self.summary(saved)
            if (not valid_id(p['receiver_id']) or type(p['amount_minor']) is not int or p['amount_minor'] <= 0
                    or type(p['description']) is not str or not 1 <= len(p['description']) <= 80):
                raise ValueError('INVALID_SPLIT_RETURN_AMOUNT')
            with c.tx():
                c.limit('community-split-return:' + g['user_id'], 20, 60)
                budget_row = c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_BUDGET' AND subject_idx=? AND project=? AND active=1", (lock, g['project'])).fetchone()
                if budget_row is None:
                    raise PermissionError('ORIGINAL_SPLIT_REQUIRED')
                budget = json.loads(c.decrypt(budget_row[0], 'provider-order-budget'))
                split = a._load(budget['split_action']) if budget.get('split_action') else None
                if split is None or split.get('result', {}).get('status') != 'FINISHED' or c.now() - split['at'] > 180*86400:
                    raise PermissionError('FINISHED_SPLIT_WITHIN_RETURN_WINDOW_REQUIRED')
                receiver = policy['receivers'].get(p['receiver_id'])
                if receiver is None or receiver['type'] != 'MERCHANT_ID':
                    raise PermissionError('PERSONAL_SPLIT_RETURN_UNSUPPORTED')
                admitted = [r for r in split['result']['receivers'] if r['receiver_id'] == p['receiver_id'] and r['result'] == 'SUCCESS']
                if len(admitted) != 1:
                    raise PermissionError('SUCCESSFUL_ORIGINAL_RECEIVER_REQUIRED')
                returns = budget.setdefault('return_actions', [])
                if len(returns) >= 50:
                    raise ValueError('SPLIT_RETURN_REQUEST_LIMIT')
                reserved = sum(self._read(k)['payload']['amount'] for k in returns if self._read(k)['receiver_id'] == p['receiver_id'])
                if reserved + p['amount_minor'] > admitted[0]['amount_minor']:
                    raise ValueError('RETURN_RESERVED_AMOUNT_EXCEEDS_SPLIT')
                if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=? AND active=1", (lock,)).fetchone():
                    raise PermissionError('PRIOR_ORDER_ACTION_UNKNOWN_QUERY_REQUIRED')
                payload = dict(sub_mchid=policy['sub_mchid'], out_order_no=split['provider_reference'], out_return_no=return_ref,
                    return_mchid=receiver['account'], amount=p['amount_minor'], description=p['description'])
                saved = dict(reference=p['reference'], request_id=p['request_id'], receiver_id=p['receiver_id'], scope=g['scope'],
                    project=g['project'], user_id=g['user_id'], policy_hash=a._policy_hash(policy), payload=payload, request_hash=request_hash)
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_RETURN',?,?,?,?,1)", (key, g['user_id'], g['project'], c.encrypt(canonical(saved), 'community-provider-return:' + key)))
                returns.append(key)
                c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_PROVIDER_ORDER_BUDGET' AND subject_idx=? AND project=?", (c.encrypt(canonical(budget), 'provider-order-budget'), lock, g['project']))
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ORDER_LOCK',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload,active=1", (lock, g['user_id'], g['project'], c.encrypt(canonical(dict(action=key)), 'provider-order-lock')))
                c.audit(g['project'], g['user_id'], 'PROVIDER_SPLIT_RETURN_RESERVED', key)
            data, digest = a._call('POST', '/v3/profitsharing/return-orders', saved['payload'])
        if a._authorize(session, csrf, workspace)[1] != policy:
            raise PermissionError('RETURN_POLICY_CHANGED')
        expected = saved['payload']
        if (any(data.get(k) != expected[k] for k in ('sub_mchid', 'out_order_no', 'out_return_no', 'return_mchid'))
                or type(data.get('amount')) is not int or data['amount'] != expected['amount']
                or data.get('result') not in ('PROCESSING', 'SUCCESS', 'FAILED')):
            raise ValueError('SIGNED_SPLIT_RETURN_BINDING_MISMATCH')
        with c.tx():
            current = self._read(key)
            if current is None or current['request_hash'] != saved['request_hash']:
                raise PermissionError('RETURN_INTENT_CHANGED')
            if current.get('result') in ('SUCCESS', 'FAILED') and current['result'] != data['result']:
                raise ValueError('TERMINAL_SPLIT_RETURN_CONFLICT')
            current.update(result=data['result'], response_sha256=digest, observed_at=c.now())
            c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_PROVIDER_RETURN' AND subject_idx=? AND active=1", (c.encrypt(canonical(current), 'community-provider-return:' + key), key))
            if data['result'] in ('SUCCESS', 'FAILED'):
                row = c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=? AND active=1", (lock,)).fetchone()
                if row and json.loads(c.decrypt(row[0], 'provider-order-lock')) == dict(action=key):
                    c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_PROVIDER_ORDER_LOCK' AND subject_idx=?", (lock,))
            c.audit(g['project'], g['user_id'], 'PROVIDER_SPLIT_RETURN_OBSERVED', digest)
        return self.summary(current)

    def summary(self, saved):
        return dict(reference=saved['reference'], request_id=saved['request_id'], receiver_id=saved['receiver_id'],
            amount_minor=saved['payload']['amount'], status=saved.get('result', 'UNKNOWN_QUERY_EXISTING_ONLY'),
            provider_response_verified='result' in saved, automatic_retry_allowed=False, finance_status='UNCONFIRMED')
