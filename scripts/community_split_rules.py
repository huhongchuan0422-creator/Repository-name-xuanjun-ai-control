"""Immutable split-rule versions and per-order allocation snapshots in Center.

The provider executor remains the only funds interface. Calculation does not
confirm payment, settlement, beneficiary identity or provider success.
"""
import hashlib
import json
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import valid_id, split_amounts
from scripts.community_order_store import state


class SplitRules:
    module = {'id': 'XJ-COMMUNITY-SPLIT-001', 'version': '1.0.0',
              'author': '玄钧AI实验室', 'dependencies': ['original-center', 'community-provider-actions'],
              'description': 'Immutable rules and deterministic integer minor-unit snapshots'}

    def __init__(self, actions):
        self.actions = actions
        self.center = actions.center

    def _key(self, scope, kind, ref):
        return hashlib.sha256(canonical([scope, kind, ref])).hexdigest()

    def _get(self, g, kind, ref):
        key = self._key(g['scope'], kind, ref)
        row = self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_SPLIT_RULES_V1' AND subject_idx=? AND project=? AND active=1", (key, g['project'])).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0], 'community-split-rule:' + key))

    def _put(self, g, kind, ref, record, replace=False):
        key = self._key(g['scope'], kind, ref)
        sql = "INSERT INTO links VALUES('COMMUNITY_SPLIT_RULES_V1',?,?,?,?,1)"
        if replace:
            sql += ' ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload'
        self.center.db.execute(sql, (key, g['user_id'], g['project'], self.center.encrypt(canonical(record), 'community-split-rule:' + key)))

    def dispatch(self, session, csrf, workspace, op, p):
        fields = {'rule_create': {'rule_id', 'version', 'shares_bps', 'description', 'unfreeze_unsplit'},
                  'rule_activate': {'rule_id', 'version', 'expected_revision'},
                  'rule_read': {'rule_id', 'version'}, 'rule_active': set(),
                  'rule_freeze': {'reference'}, 'rule_snapshot': {'reference'}}
        if op not in fields or type(p) is not dict or set(p) != fields[op]:
            raise ValueError('INVALID_SPLIT_RULE_FIELDS')
        g, policy = self.actions._authorize(session, csrf, workspace)
        c = self.center
        with c.tx():
            c.limit('community-split-rules:' + g['user_id'], 30, 60)
            if op in ('rule_create', 'rule_activate', 'rule_read'):
                if not valid_id(p['rule_id']) or type(p['version']) is not int or not 1 <= p['version'] <= 1000000:
                    raise ValueError('INVALID_SPLIT_RULE_VERSION')
                ref = p['rule_id'] + ':' + str(p['version'])
            if op == 'rule_create':
                if g['role'] != 'PLATFORM_OWNER':
                    raise PermissionError('PLATFORM_OWNER_RULE_POLICY_REQUIRED')
                shares = p['shares_bps']
                if (type(shares) is not dict or not 1 <= len(shares) <= 19
                        or any(k not in policy['receivers'] or k=='_merchant_remainder' for k in shares)
                        or any(type(v) is not int or not 1 <= v <= 10000 for v in shares.values())
                        or sum(shares.values()) > policy['max_total_bps']
                        or type(p['description']) is not str or not 1 <= len(p['description']) <= 80
                        or type(p['unfreeze_unsplit']) is not bool or not policy['profit_sharing']):
                    raise ValueError('INVALID_ADMITTED_SPLIT_RULE')
                result = dict(rule_id=p['rule_id'], version=p['version'], shares_bps=shares,
                    description=p['description'], unfreeze_unsplit=p['unfreeze_unsplit'],
                    policy_hash=self.actions._policy_hash(policy), created_at=c.now(), author=g['user_id'])
                prior = self._get(g, 'VERSION', ref)
                if prior is not None:
                    if any(prior[k] != result[k] for k in ('rule_id', 'version', 'shares_bps', 'description', 'unfreeze_unsplit', 'policy_hash')):
                        raise ValueError('IMMUTABLE_SPLIT_RULE_VERSION')
                    result = prior
                else:
                    self._put(g, 'VERSION', ref, result)
            elif op == 'rule_activate':
                if g['role'] != 'PLATFORM_OWNER':
                    raise PermissionError('PLATFORM_OWNER_RULE_POLICY_REQUIRED')
                rule = self._get(g, 'VERSION', ref)
                if rule is None or rule['policy_hash'] != self.actions._policy_hash(policy):
                    raise PermissionError('CURRENT_ADMITTED_RULE_REQUIRED')
                active = self._get(g, 'ACTIVE', 'current')
                revision = active['revision'] if active else 0
                if type(p['expected_revision']) is not int or p['expected_revision'] != revision:
                    raise ValueError('SPLIT_RULE_REVISION_CONFLICT')
                result = dict(rule_id=p['rule_id'], version=p['version'], revision=revision+1, activated_at=c.now())
                self._put(g, 'ACTIVE', 'current', result, replace=True)
            elif op == 'rule_active':
                result = self._get(g, 'ACTIVE', 'current')
            elif op == 'rule_read':
                result = self._get(g, 'VERSION', ref)
                if result is None:
                    raise ValueError('SPLIT_RULE_NOT_FOUND')
            else:
                if not valid_id(p['reference']):
                    raise ValueError('INVALID_ORDER_REFERENCE')
                order = state(self.actions.runtime.demo.db, g['scope'], p['reference'])
                result = self._get(g, 'ORDER', p['reference'])
                if op == 'rule_snapshot':
                    if result is None:
                        raise ValueError('ORDER_SPLIT_SNAPSHOT_NOT_FOUND')
                elif result is None:
                    result=self.freeze_original(g,policy,p['reference'])
                if result['amount_minor'] != order['amount_minor'] or result['currency'] != order['currency']:
                    raise PermissionError('FROZEN_ORDER_AMOUNT_CHANGED')
            c.audit(g['project'], g['user_id'], 'COMMUNITY_' + op.upper(), hashlib.sha256(canonical(p)).hexdigest())
        return result

    def freeze_original(self,g,policy,reference):
        c=self.center
        p={'reference':reference}
        order=state(self.actions.runtime.demo.db,g['scope'],reference)
        existing=self._get(g,'ORDER',reference)
        if existing is not None:
            if existing['amount_minor']!=order['amount_minor'] or existing['policy_hash']!=self.actions._policy_hash(policy):raise PermissionError('FROZEN_ORDER_POLICY_CHANGED')
            return existing
        if order['state'] != 'PENDING':
            raise PermissionError('RULE_MUST_BE_FROZEN_BEFORE_PAYMENT_CONFIRMATION')
        active = self._get(g, 'ACTIVE', 'current')
        if active is None:
            raise ValueError('ACTIVE_SPLIT_RULE_REQUIRED')
        rule = self._get(g, 'VERSION', active['rule_id'] + ':' + str(active['version']))
        if rule['policy_hash'] != self.actions._policy_hash(policy):
            raise PermissionError('SPLIT_POLICY_CHANGED_REVIEW_RULE')
        # Reuse the original largest-remainder precision rule.
        shares=dict(rule['shares_bps'])
        shares['_merchant_remainder']=10000-sum(shares.values())
        rounded=split_amounts(order['amount_minor'],shares)['shares_minor']
        allocations={rid: amount for rid, amount in rounded.items() if rid!='_merchant_remainder' and amount>0}
        if sum(allocations.values())>order['amount_minor']*policy['max_total_bps']//10000:
            raise ValueError('ROUNDED_SPLIT_EXCEEDS_ADMITTED_PROVIDER_LIMIT')
        result = dict(reference=p['reference'], amount_minor=order['amount_minor'], currency='CNY',
            rule_id=rule['rule_id'], version=rule['version'], allocations=allocations,
            retained_minor=order['amount_minor']-sum(allocations.values()),
            policy_hash=rule['policy_hash'], description=rule['description'],
            unfreeze_unsplit=rule['unfreeze_unsplit'], frozen_at=c.now(),
            eligible=bool(allocations), provider_split_confirmed=False)
        result['snapshot_sha256'] = hashlib.sha256(canonical(result)).hexdigest()
        self._put(g, 'ORDER', p['reference'], result)
        return result

    def split(self, session, csrf, workspace, params):
        if type(params) is not dict or set(params) != {'reference', 'request_id'}:
            raise ValueError('INVALID_RULE_SPLIT_FIELDS')
        snapshot = self.dispatch(session, csrf, workspace, 'rule_snapshot', {'reference': params['reference']})
        g, policy = self.actions._authorize(session, csrf, workspace)
        if snapshot['policy_hash'] != self.actions._policy_hash(policy) or not snapshot['eligible']:
            raise PermissionError('FROZEN_SPLIT_NOT_ELIGIBLE')
        result = self.actions.dispatch(session, csrf, dict(workspace=workspace, operation='split', params=dict(
            reference=params['reference'], request_id=params['request_id'], allocations=snapshot['allocations'],
            description=snapshot['description'], unfreeze_unsplit=snapshot['unfreeze_unsplit'])))
        return dict(result, rule_id=snapshot['rule_id'], rule_version=snapshot['version'], snapshot_sha256=snapshot['snapshot_sha256'])
