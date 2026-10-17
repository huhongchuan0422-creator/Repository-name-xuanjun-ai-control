"""Versioned product prices and basket orders using original Center and stores.

Center reservations are durable before the original order write. A partial
cross-database failure recovers the same reference; it never reserves twice.
"""
import hashlib
import json
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import scope, valid_id, payment_amount
from scripts.community_order_store import create_order, state


class Commerce:
    def __init__(self, operations, identity):
        from scripts.community_center_operations import CenterOperations
        from scripts.community_mini_center_identity import CenterIdentity
        if type(operations) is not CenterOperations or type(identity) is not CenterIdentity or operations.center is not identity.center or operations.runtime is not identity.runtime:
            raise ValueError('SAME_ORIGINAL_CENTER_AND_STORES_REQUIRED')
        self.operations, self.identity = operations, identity
        self.center, self.runtime = identity.center, identity.runtime

    def _key(self, identity, kind, ref):
        return hashlib.sha256(canonical([identity, kind, ref])).hexdigest()

    def _read(self, identity, project, kind, ref):
        key = self._key(identity, kind, ref)
        row = self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=? AND project=? AND active=1", (key, project)).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0], 'community-commerce:' + key))

    def _save(self, identity, project, uid, kind, ref, value, update=False):
        key = self._key(identity, kind, ref)
        sql = "INSERT INTO links VALUES('COMMUNITY_COMMERCE_V1',?,?,?,?,1)"
        if update:
            sql += ' ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload'
        self.center.db.execute(sql, (key, uid, project, self.center.encrypt(canonical(value), 'community-commerce:' + key)))

    def _operator(self, session, csrf, workspace):
        if type(csrf) is not str or not csrf:
            raise PermissionError('CENTER_CSRF_REQUIRED')
        c = self.center
        uid = c.session(session, csrf)
        g = self.operations.grants.get(workspace)
        if g is None or uid != g['user_id'] or g['role'] not in ('MERCHANT_ADMIN', 'PLATFORM_OWNER'):
            raise PermissionError('MERCHANT_COMMERCE_GRANT_REQUIRED')
        principal = g['principal']
        if principal.role != g['role'] or self.runtime.bindings.get(principal) != g['scope']:
            raise PermissionError('MERCHANT_GRANT_CHANGED')
        project, _, _ = c.project(uid, g['project'], g['project_roles'])
        if project['tenant'] != g['tenant']:
            raise PermissionError('MERCHANT_TENANT_DENIED')
        if g['onboarding_required']:
            from scripts.community_merchant_opening import authorize_workspace
            authorize_workspace(self.operations.onboarding, self.operations, workspace, uid)
        return g

    def _catalog_item(self, identity, item_id, public=True):
        t, m, s = scope(identity)
        merchant = self.runtime.demo.merchant_db
        profile = merchant.execute('SELECT status FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?', (t, m, s)).fetchone()
        item = merchant.execute('SELECT name,status FROM catalog_items WHERE tenant_id=? AND merchant_id=? AND store_id=? AND item_id=?', (t, m, s, item_id)).fetchone()
        if profile is None or item is None or public and (profile[0] != 'ACTIVE' or item[1] != 'ACTIVE'):
            raise PermissionError('AVAILABLE_ORIGINAL_PRODUCT_REQUIRED')
        return item

    def dispatch(self, session, csrf, body):
        if type(body) is not dict or set(body) != {'workspace', 'operation', 'params'}:
            raise ValueError('INVALID_COMMERCE_FIELDS')
        g = self._operator(session, csrf, body['workspace'])
        op, p = body['operation'], body['params']
        if type(body['operation']) is str and body['operation'] in ('refund_application_read','refund_decide'):
            from scripts.community_refund_requests import RefundRequests
            return RefundRequests(self).review(g,body['operation'],body['params'])
        fields = {'price_set': {'item_id', 'expected_revision', 'unit_minor', 'stock', 'enabled'},
                  'price_read': {'item_id'}, 'order_lines': {'reference'}}
        if type(op) is not str or op not in fields or type(p) is not dict or set(p) != fields[op]:
            raise ValueError('INVALID_COMMERCE_OPERATION')
        c = self.center
        with c.tx():
            c.limit('community-commerce-operator:' + g['user_id'], 60, 60)
            if op.startswith('price_'):
                if not valid_id(p['item_id']):
                    raise ValueError('INVALID_PRODUCT_ID')
                self._catalog_item(g['scope'], p['item_id'], False)
                old = self._read(g['scope'], g['project'], 'PRODUCT', p['item_id'])
                if op == 'price_read':
                    result = old
                else:
                    revision = old['revision'] if old else 0
                    if (type(p['expected_revision']) is not int or p['expected_revision'] != revision
                            or type(p['unit_minor']) is not int or not 1 <= p['unit_minor'] <= 100000000
                            or type(p['stock']) is not int or not 0 <= p['stock'] <= 100000000
                            or type(p['enabled']) is not bool):
                        raise ValueError('INVALID_PRODUCT_PRICE_OR_REVISION')
                    result = dict(item_id=p['item_id'], revision=revision+1, unit_minor=p['unit_minor'],
                        currency='CNY', stock=p['stock'], enabled=p['enabled'], updated_at=c.now())
                    self._save(g['scope'], g['project'], g['user_id'], 'PRICE_VERSION', p['item_id'] + ':' + str(result['revision']), result)
                    self._save(g['scope'], g['project'], g['user_id'], 'PRODUCT', p['item_id'], result, True)
            else:
                if not valid_id(p['reference']):
                    raise ValueError('INVALID_ORDER_REFERENCE')
                result = self._read(g['scope'], g['project'], 'ORDER', p['reference'])
                if result is None:
                    raise ValueError('BASKET_ORDER_NOT_FOUND')
                result = dict(result, order=state(self.runtime.demo.db, g['scope'], p['reference']))
            c.audit(g['project'], g['user_id'], 'COMMERCE_' + op.upper(), hashlib.sha256(canonical(p)).hexdigest())
        return result

    def consumer(self, token, scene, op, p):
        i = self.identity
        now = self.center.now()
        i._time(now)
        uid, project, principal = i._resolve(token, scene)
        identity = self.runtime.bindings[principal]
        c = self.center
        if op in ('refund_apply','refund_application'):
            from scripts.community_refund_requests import RefundRequests
            return RefundRequests(self).consumer(token,scene,op,p)
        fields = {'products': set(), 'purchase': {'reference', 'lines'}, 'purchase_read': {'reference'}}
        if op not in fields or type(p) is not dict or set(p) != fields[op]:
            raise ValueError('INVALID_CONSUMER_COMMERCE_FIELDS')
        if op == 'products':
            t, m, s = scope(identity)
            items = self.runtime.demo.merchant_db.execute('SELECT item_id FROM catalog_items WHERE tenant_id=? AND merchant_id=? AND store_id=? AND status=\'ACTIVE\' ORDER BY sort_order,item_id LIMIT 100', (t, m, s)).fetchall()
            result = []
            for item_id, in items:
                item = self._catalog_item(identity, item_id)
                price = self._read(identity, project, 'PRODUCT', item_id)
                if price and price['enabled']:
                    result.append(dict(item_id=item_id, name=item[0], unit_minor=price['unit_minor'], currency='CNY', revision=price['revision'], available=price['stock'] > 0))
            return dict(products=result)
        reference = p['reference']
        if not valid_id(reference):
            raise ValueError('INVALID_ORDER_REFERENCE')
        if op == 'purchase_read':
            i.authorize_order_read(token, scene, reference, now)
            record = self._read(identity, project, 'ORDER', reference)
            if record is None or record['user_id'] != uid:
                raise PermissionError('OWNED_BASKET_REQUIRED')
            return dict(record, order=state(self.runtime.demo.db, identity, reference))
        lines = p['lines']
        if (type(lines) is not list or not 1 <= len(lines) <= 50
                or any(type(line) is not dict or set(line) != {'item_id', 'quantity', 'revision'} for line in lines)):
            raise ValueError('INVALID_BASKET')
        ids = set()
        for line in lines:
            if (not valid_id(line['item_id']) or line['item_id'] in ids
                    or type(line['quantity']) is not int or not 1 <= line['quantity'] <= 10000
                    or type(line['revision']) is not int or line['revision'] < 1):
                raise ValueError('INVALID_BASKET_LINE')
            ids.add(line['item_id'])
        request_hash = hashlib.sha256(canonical(sorted(lines, key=lambda line: line['item_id']))).hexdigest()
        with c.tx():
            c.limit('community-purchase:' + uid, 20, 60)
            record = self._read(identity, project, 'ORDER', reference)
            if record is not None:
                if record['user_id'] != uid or record['request_hash'] != request_hash:
                    raise PermissionError('BASKET_REFERENCE_COLLISION')
            else:
                resolved = []
                total = 0
                for line in lines:
                    item = self._catalog_item(identity, line['item_id'])
                    price = self._read(identity, project, 'PRODUCT', line['item_id'])
                    if price is None or not price['enabled'] or price['revision'] != line['revision'] or price['stock'] < line['quantity']:
                        raise ValueError('PRODUCT_PRICE_CHANGED_OR_OUT_OF_STOCK')
                    price = dict(price, stock=price['stock']-line['quantity'],revision=price['revision']+1,updated_at=c.now())
                    self._save(identity,project,uid,'PRICE_VERSION',line['item_id']+':'+str(price['revision']),price)
                    subtotal = price['unit_minor'] * line['quantity']
                    total += subtotal
                    resolved.append(dict(line, name=item[0], unit_minor=price['unit_minor'], subtotal_minor=subtotal))
                    self._save(identity, project, uid, 'PRODUCT', line['item_id'], price, True)
                payment_amount(total, 'CNY', reference)
                # Same original ownership format used by CenterIdentity; one transaction.
                ownership_key, _ = i._order_key(principal, reference)
                if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_ORDER' AND subject_idx=?", (ownership_key,)).fetchone():
                    raise PermissionError('ORDER_REFERENCE_ALREADY_RESERVED')
                t, m, s = scope(identity)
                if self.runtime.demo.db.execute('SELECT 1 FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?', (t, m, s, reference)).fetchone():
                    raise PermissionError('LEGACY_ORDER_CANNOT_BE_CLAIMED')
                ownership = dict(scope=identity, reference=reference, amount_minor=total)
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_ORDER',?,?,?,?,1)", (ownership_key, uid, project, c.encrypt(canonical(ownership), 'community-order:' + ownership_key)))
                community_key=hashlib.sha256(canonical([identity['tenant_id'],'CUSTOMER:'+uid])).hexdigest()
                relation=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_RELATION_V1' AND subject_idx=? AND project=? AND user_id=? AND active=1",(community_key,project,uid)).fetchone()
                community_id=None
                if relation is not None:
                    joined=json.loads(c.decrypt(relation[0],'community-relation:'+community_key))
                    directory_key=hashlib.sha256(canonical([identity['tenant_id'],joined['community_id']])).hexdigest()
                    directory=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_DIRECTORY_V1' AND subject_idx=? AND project=? AND active=1",(directory_key,project)).fetchone()
                    if directory is not None and json.loads(c.decrypt(directory[0],'community-directory:'+directory_key))['state']=='APPROVED':community_id=joined['community_id']
                profile_key=c.idx('community-profile:'+project+':'+uid)
                referrer=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_CUSTOMER_REFERRER' AND subject_idx=? AND project=? AND user_id=? AND active=1",(profile_key,project,uid)).fetchone()
                referrer_id=json.loads(c.decrypt(referrer[0],'COMMUNITY_CUSTOMER_REFERRER:'+profile_key))['referrer_user_id'] if referrer else None
                record = dict(reference=reference, user_id=uid, scope=dict(identity), community_id=community_id,referrer_user_id=referrer_id, lines=resolved, amount_minor=total,
                    currency='CNY', request_hash=request_hash, stock_reserved=True, created_at=now)
                self._save(identity, project, uid, 'ORDER', reference, record)
                c.audit(project, uid, 'COMMUNITY_BASKET_RESERVED', request_hash)
        # Cross-store recovery: never compensate blindly or allocate a new reference.
        i._resolve(token, scene)
        t, m, s = scope(identity)
        existing = self.runtime.demo.db.execute('SELECT amount_minor,currency FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?', (t, m, s, reference)).fetchone()
        if existing is None:
            create_order(self.runtime.demo.db, identity, reference, record['amount_minor'])
        elif tuple(existing) != (record['amount_minor'], 'CNY'):
            raise PermissionError('ORIGINAL_BASKET_ORDER_MISMATCH')
        i.authorize_order_read(token, scene, reference, c.now())
        return dict(record, order=state(self.runtime.demo.db, identity, reference))
