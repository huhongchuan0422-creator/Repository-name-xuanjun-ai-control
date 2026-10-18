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

    def project_document_authorize(self, token, scene):
        from scripts.community_project_materials import ProjectMaterials
        return ProjectMaterials(self).authorize_upload(token, scene)

    def project_document_upload(self, token, scene, body):
        from scripts.community_project_materials import ProjectMaterials
        return ProjectMaterials(self).upload(token, scene, body)

    def project_material_review(self, session, csrf, body):
        from scripts.community_project_materials import ProjectMaterials
        return ProjectMaterials(self).reviewer(session, csrf, body)

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
        if public:
            from scripts.community_platform_merchants import assert_trading
            assert_trading(self.center,identity)
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
        if body['operation']=='project_review':
            # Web-only Center session, not mini-scene bearer or merchant grant.
            # Original CRM authority admits independent REVIEWER membership.
            c=self.center
            p=body['params']
            project=body['workspace']
            if (type(csrf) is not str or not csrf or not valid_id(project)
                    or type(p) is not dict or set(p)!={'item','revision','action','reason'}
                    or not valid_id(p['item']) or type(p['revision']) is not int
                    or p['revision']<0 or p['action'] not in
                    ('begin_review','request_changes','approve')
                    or type(p['reason']) is not str or len(p['reason'])>1000):
                raise ValueError('INVALID_INDEPENDENT_PROJECT_REVIEW')
            uid=c.session(session,csrf)
            c.project(uid,project,('REVIEWER',))
            return c.transition(uid,project,p['item'],p['revision'],p['action'],p['reason'])
        g = self._operator(session, csrf, body['workspace'])
        op, p = body['operation'], body['params']
        if op == 'refund_applications':
            from scripts.community_refund_requests import RefundRequests
            return RefundRequests(self).directory(g,p)
        if type(body['operation']) is str and body['operation'] in ('refund_application_read','refund_decide'):
            from scripts.community_refund_requests import RefundRequests
            return RefundRequests(self).review(g,body['operation'],body['params'])
        if op=='order_complete':
            from scripts.community_order_provider_projection import provider_evidence
            if type(p) is not dict or set(p)!={'reference','expected_revision','note'} or not valid_id(p['reference']) or type(p['note']) is not str or len(p['note'])>500:raise ValueError('INVALID_ORDER_COMPLETION')
            with self.center.tx():
                record=self._read(g['scope'],g['project'],'ORDER',p['reference'])
                if record is None:raise ValueError('ORIGINAL_BASKET_ORDER_REQUIRED')
                original=state(self.runtime.demo.db,g['scope'],p['reference'])
                if original['state']!='SUCCESS' or provider_evidence(self.runtime.demo.db,g['scope'],p['reference']) is None:raise PermissionError('TRUSTED_PAID_ORDER_REQUIRED')
                revision=record.get('fulfillment_revision',0)
                if type(p['expected_revision']) is not int or p['expected_revision']!=revision or record.get('fulfillment_state')=='COMPLETED':raise ValueError('ORDER_COMPLETION_VERSION_CONFLICT')
                result=dict(record,fulfillment_revision=revision+1,fulfillment_state='COMPLETED',completed_at=self.center.now(),completion_note=p['note'])
                self._save(g['scope'],g['project'],record['user_id'],'ORDER',p['reference'],result,True)
                from scripts.community_customer_profile import notify
                notify(self.center,g['project'],record['user_id'],'ORDER_COMPLETED',p['reference'],'商家已完成订单 '+p['reference'])
                self.center.audit(g['project'],g['user_id'],'COMMUNITY_ORDER_COMPLETED',p['reference'])
            return result
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
        if op in ('communities','community_mine','community_join','community_leave','promotion_redeem'):
            from scripts.community_consumer_communities import ConsumerCommunities
            return ConsumerCommunities(self).consumer(token,scene,op,p)
        if op in ('profile_read','profile_update','referral_code','referral_bind','notices','notice_read'):
            from scripts.community_customer_profile import CustomerProfile
            return CustomerProfile(identity=i).consumer(token,scene,op,p)
        if op in ('refund_apply','refund_application','refund_current'):
            from scripts.community_refund_requests import RefundRequests
            return RefundRequests(self).consumer(token,scene,op,p)
        if op == 'project_save_reference':
            # Reuse original Center requirement version and host-side provider
            # verification; a mini-supplied string is never proof of a secret.
            if (type(p) is not dict or set(p) != {'item','revision','kind','reference'}
                    or not valid_id(p['item']) or type(p['revision']) is not int
                    or p['revision'] < 0 or p['kind'] not in
                    ('SECRETREF','OAUTH','SERVER_CHALLENGE')
                    or type(p['reference']) is not str):
                raise ValueError('INVALID_PROJECT_REFERENCE_SAVE')
            c.project(uid, project, ('OWNER','EDITOR'))
            return c.save(uid, project, p['item'], p['revision'],
                          p['kind'], p['reference'])
        if op == 'project_submit':
            # Only an existing version of an original Center requirement may be
            # submitted. Approval and correction remain with independent reviewers.
            if (type(p) is not dict or set(p) != {'item','revision'}
                    or not valid_id(p['item']) or type(p['revision']) is not int
                    or p['revision'] < 0):
                raise ValueError('INVALID_PROJECT_REQUIREMENT_SUBMISSION')
            c.project(uid, project, ('OWNER','EDITOR'))
            return c.transition(uid, project, p['item'], p['revision'], 'submit')
        if op in ('project_summary', 'project_checklist', 'project_feedback', 'project_messages'):
            # Reuse immutable original Center project membership, requirements
            # and archived feedback; never create a parallel project authority.
            expected = {'message'} if op == 'project_feedback' else set()
            if type(p) is not dict or set(p) != expected:
                raise ValueError('INVALID_PROJECT_CENTER_FIELDS')
            source, role, details = c.project(uid, project)
            if op == 'project_summary':
                checklist = c.checklist(uid, project)
                return dict(project_id=project, title=details['title'], role=role,
                            customer_id=source['customer'],
                            requirements_revision=source['revision'],
                            checklist_overall=checklist['overall'])
            if op == 'project_checklist':
                return c.checklist(uid, project)
            if op == 'project_messages':
                # Bounded original Center archived conversation. No new message store.
                return dict(records=c.messages(uid,project),source='ORIGINAL_CENTER_ARCHIVE',
                            provider_reply_verified=False)
            # Core persists to original encrypted messaging and audit trail.
            # ARCHIVED is not evidence of a human or provider response.
            if type(p['message']) is not str:
                raise ValueError('INVALID_PROJECT_FEEDBACK')
            return c.message(uid, project, p['message'], 'WEB')
        if op == 'receipt_ad':
            # Success creative is optional and requires both original order ownership
            # and durable signed-provider evidence. A caller's payment flag is ignored.
            if type(p) is not dict or set(p) != {'reference'} or not valid_id(p['reference']):
                raise ValueError('INVALID_RECEIPT_AD_FIELDS')
            i.authorize_order_read(token, scene, p['reference'], now)
            with c.tx():
                c.limit('community-receipt-ad:' + uid, 30, 60)
                owned = self._read(identity, project, 'ORDER', p['reference'])
                if owned is None or owned['user_id'] != uid:
                    raise PermissionError('OWNED_BASKET_REQUIRED')
            from scripts.community_order_provider_projection import provider_evidence
            order = state(self.runtime.demo.db, identity, p['reference'])
            if order['state'] != 'SUCCESS' or provider_evidence(self.runtime.demo.db, identity, p['reference']) is None:
                return dict(creative=None, payment_success_verified=False,
                            finance_status='UNCONFIRMED')
            from scripts.community_ad_store import choose
            from scripts.community_ad_contract import SUCCESS
            import sqlite3
            try:
                creative = choose(self.runtime.demo.ad_db, identity, SUCCESS, now)
            except sqlite3.DatabaseError:
                creative = None  # Ads must not block purchase or receipt recovery.
            return dict(creative=creative, payment_success_verified=True,
                        finance_status='UNCONFIRMED')
        fields = {'orders': {'after_id'}, 'products': set(), 'purchase': {'reference', 'lines'}, 'purchase_read': {'reference'}, 'purchase_recover': {'reference'}}
        if op not in fields or type(p) is not dict or (set(p) != fields[op] and not (op == 'products' and set(p) == {'after_id'})):
            raise ValueError('INVALID_CONSUMER_COMMERCE_FIELDS')
        if op=='orders':
            after=p['after_id']
            import re
            if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}',after):raise ValueError('INVALID_CUSTOMER_ORDER_CURSOR')
            rows=c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_ORDER' AND user_id=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51",(uid,project,after)).fetchall()
            records=[]
            for key,payload in rows[:50]:
                owned=json.loads(c.decrypt(payload,'community-order:'+key))
                if owned['scope']!=identity:continue
                try:order=state(self.runtime.demo.db,identity,owned['reference'])
                except ValueError as exc:
                    if str(exc)!='ORDER_NOT_FOUND':raise
                    order=dict(state='CREATION_UNKNOWN_RECOVER_SAME_REFERENCE',amount_minor=owned['amount_minor'],currency='CNY',provider_settlement_verified=False)
                basket=self._read(identity,project,'ORDER',owned['reference'])
                records.append(dict(reference=owned['reference'],order=order,lines=basket['lines'] if basket else None,community_id=basket.get('community_id') if basket else None))
            return dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None)
        if op == 'products':
            t, m, s = scope(identity)
            # Keep the original sort order and first-page API. The cursor is a
            # validated keyset, never SQL or authority over another store.
            after = p.get('after_id', '')
            if type(after) is not str or len(after) > 160:
                raise ValueError('INVALID_PRODUCT_CURSOR')
            params = [t, m, s]
            sql = "SELECT item_id,sort_order FROM catalog_items WHERE tenant_id=? AND merchant_id=? AND store_id=? AND status='ACTIVE'"
            if after:
                try:
                    cursor = json.loads(after)
                except (ValueError, TypeError):
                    raise ValueError('INVALID_PRODUCT_CURSOR') from None
                if (type(cursor) is not list or len(cursor) != 2
                        or type(cursor[0]) is not int or not -(2**63) <= cursor[0] < 2**63
                        or not valid_id(cursor[1])):
                    raise ValueError('INVALID_PRODUCT_CURSOR')
                sql += ' AND (sort_order>? OR (sort_order=? AND item_id>?))'
                params.extend((cursor[0], cursor[0], cursor[1]))
            items = self.runtime.demo.merchant_db.execute(sql + ' ORDER BY sort_order,item_id LIMIT 101', params).fetchall()
            result = []
            for item_id, _ in items[:100]:
                item = self._catalog_item(identity, item_id)
                price = self._read(identity, project, 'PRODUCT', item_id)
                if price and price['enabled']:
                    result.append(dict(item_id=item_id, name=item[0], unit_minor=price['unit_minor'], currency='CNY', revision=price['revision'], available=price['stock'] > 0))
            # Disabled/unpriced items still advance the bounded scan cursor.
            # This is a live directory, not an immutable inventory snapshot.
            return dict(products=result, has_more=len(items) > 100,
                        next_cursor=json.dumps([items[99][1], items[99][0]], separators=(',', ':')) if len(items) > 100 else None)
        reference = p['reference']
        if not valid_id(reference):
            raise ValueError('INVALID_ORDER_REFERENCE')
        if op == 'purchase_recover':
            # Recovery uses only the original, owned reservation. The current
            # catalog and client-supplied quantities never reprice this order.
            return self._complete_reserved_purchase(token, scene, reference, uid, project, identity)
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
        return self._complete_reserved_purchase(token, scene, reference, uid, project, identity)

    def _complete_reserved_purchase(self, token, scene, reference, uid, project, identity):
        """Finish the exact durable reservation without reserving any more stock.

        Center's write lock keeps live authorization/ownership stable until the
        original order is committed. The original order lock serializes first
        creation across connections. This is not a cross-database transaction:
        either commit may fail, and explicit recovery always uses the same ID.
        """
        c, i, db = self.center, self.identity, self.runtime.demo.db
        if db.in_transaction:
            raise ValueError('EXTERNAL_ORDER_TRANSACTION_DENIED')
        with c.tx():
            def authorize():
                i._time(c.now())
                actual_uid, actual_project, principal = i._resolve(token, scene)
                if ((actual_uid, actual_project) != (uid, project)
                        or self.runtime.bindings[principal] != identity):
                    raise PermissionError('ORIGINAL_BASKET_IDENTITY_CHANGED')
                return principal
            principal = authorize()
            c.limit('community-purchase-recovery:' + uid, 30, 60)
            key = self._key(identity, 'ORDER', reference)
            row = c.db.execute("SELECT user_id,payload FROM links WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=? AND project=? AND active=1", (key, project)).fetchone()
            if row is None or row[0] != uid:
                raise PermissionError('OWNED_BASKET_RESERVATION_REQUIRED')
            record = json.loads(c.decrypt(row[1], 'community-commerce:' + key))
            if (type(record) is not dict or record.get('user_id') != uid
                    or record.get('scope') != identity or record.get('reference') != reference
                    or record.get('currency') != 'CNY' or record.get('stock_reserved') is not True
                    or type(record.get('stock_released', False)) is not bool
                    or type(record.get('lines')) is not list or not 1 <= len(record['lines']) <= 50):
                raise PermissionError('ORIGINAL_BASKET_RESERVATION_REQUIRED')
            payment_amount(record.get('amount_minor'), 'CNY', reference)
            requested, ids, total = [], set(), 0
            for line in record['lines']:
                if (type(line) is not dict or set(line) != {'item_id','quantity','revision','name','unit_minor','subtotal_minor'}
                        or not valid_id(line['item_id']) or line['item_id'] in ids
                        or type(line['quantity']) is not int or not 1 <= line['quantity'] <= 10000
                        or type(line['revision']) is not int or line['revision'] < 1
                        or type(line['name']) is not str or not line['name']
                        or type(line['unit_minor']) is not int or not 1 <= line['unit_minor'] <= 100000000
                        or type(line['subtotal_minor']) is not int
                        or line['subtotal_minor'] != line['quantity'] * line['unit_minor']):
                    raise PermissionError('ORIGINAL_FROZEN_BASKET_REQUIRED')
                ids.add(line['item_id'])
                total += line['subtotal_minor']
                requested.append({k: line[k] for k in ('item_id','quantity','revision')})
            request_hash = hashlib.sha256(canonical(sorted(requested, key=lambda line: line['item_id']))).hexdigest()
            if total != record['amount_minor'] or record.get('request_hash') != request_hash:
                raise PermissionError('ORIGINAL_FROZEN_BASKET_MISMATCH')
            ownership_key, _ = i._order_key(principal, reference)
            owners = c.db.execute("SELECT user_id,project,payload FROM links WHERE channel='COMMUNITY_ORDER' AND subject_idx=? AND active=1", (ownership_key,)).fetchall()
            if (len(owners) != 1 or tuple(owners[0][:2]) != (uid, project)
                    or json.loads(c.decrypt(owners[0][2], 'community-order:' + ownership_key))
                    != dict(scope=identity, reference=reference, amount_minor=record['amount_minor'])):
                raise PermissionError('ORIGINAL_BASKET_OWNER_REQUIRED')
            t, m, s = scope(identity)
            db.execute('BEGIN IMMEDIATE')
            try:
                # Acquiring the other SQLite lock may have waited past expiry.
                authorize()
                existing = db.execute('SELECT amount_minor,currency FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?', (t, m, s, reference)).fetchone()
                if existing is None:
                    if record.get('stock_released') is True or record.get('fulfillment_state') == 'COMPLETED':
                        raise PermissionError('TERMINAL_BASKET_ORDER_MISSING')
                    create_order(db, identity, reference, record['amount_minor'])
                elif tuple(existing) != (record['amount_minor'], 'CNY'):
                    raise PermissionError('ORIGINAL_BASKET_ORDER_MISMATCH')
                else:
                    db.commit()
            except BaseException:
                db.rollback()
                raise
            i.authorize_order_read(token, scene, reference, c.now())
            c.audit(project, uid, 'COMMUNITY_BASKET_ORDER_RECOVERED', reference)
            return dict(record, order=state(db, identity, reference))

    def release_cancelled(self,identity,project,uid,reference):
        from scripts.community_order_cancellation import cancelled_observation
        c=self.center
        with c.tx():
            if cancelled_observation(self.runtime.demo.db,identity,reference) is None:
                raise PermissionError('CONFIRMED_CANCELLATION_REQUIRED')
            order=state(self.runtime.demo.db,identity,reference)
            ownership_key=c.idx('community-order:'+canonical([identity,reference]).decode())
            ownership=c.db.execute("SELECT user_id,project,payload FROM links WHERE channel='COMMUNITY_ORDER' AND subject_idx=? AND active=1",(ownership_key,)).fetchone()
            if (ownership is None or ownership['user_id']!=uid or ownership['project']!=project
                    or json.loads(c.decrypt(ownership['payload'],'community-order:'+ownership_key))
                    !=dict(scope=identity,reference=reference,amount_minor=order['amount_minor'])):
                raise PermissionError('ORIGINAL_BASKET_OWNER_REQUIRED')
            record=self._read(identity,project,'ORDER',reference)
            # Original amount-only orders never reserved product stock.
            if record is None:return
            basket_owner=c.db.execute("SELECT user_id FROM links WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=? AND project=? AND active=1",(self._key(identity,'ORDER',reference),project)).fetchone()
            if (type(record) is not dict or record.get('user_id')!=uid or basket_owner is None or basket_owner[0]!=uid
                    or record.get('scope')!=identity or record.get('reference')!=reference
                    or type(record.get('amount_minor')) is not int or record['amount_minor']!=order['amount_minor']
                    or record.get('currency')!='CNY'):
                raise PermissionError('ORIGINAL_BASKET_BINDING_REQUIRED')
            if (record.get('stock_reserved') is not True
                    or type(record.get('stock_released',False)) is not bool
                    or type(record.get('lines')) is not list or not 1<=len(record['lines'])<=50):
                raise PermissionError('ORIGINAL_STOCK_RESERVATION_REQUIRED')

            def checked_price(price,item_id,revision=None):
                if (type(price) is not dict or price.get('item_id')!=item_id or price.get('currency')!='CNY'
                        or type(price.get('revision')) is not int or price['revision']<1
                        or revision is not None and price['revision']!=revision
                        or type(price.get('stock')) is not int or not 0<=price['stock']<=100000000
                        or type(price.get('unit_minor')) is not int or not 1<=price['unit_minor']<=100000000
                        or type(price.get('enabled')) is not bool
                        or type(price.get('updated_at')) is not int or price['updated_at']<0):
                    raise ValueError('ORIGINAL_PRODUCT_VERSION_REQUIRED')
                return price

            requested=[];ids=set();total=0
            for line in record['lines']:
                if (type(line) is not dict or set(line)!={'item_id','quantity','revision','name','unit_minor','subtotal_minor'}
                        or not valid_id(line['item_id']) or line['item_id'] in ids
                        or type(line['quantity']) is not int or not 1<=line['quantity']<=10000
                        or type(line['revision']) is not int or line['revision']<1
                        or type(line['name']) is not str or not line['name']
                        or type(line['unit_minor']) is not int or not 1<=line['unit_minor']<=100000000
                        or type(line['subtotal_minor']) is not int
                        or line['subtotal_minor']!=line['unit_minor']*line['quantity']):
                    raise PermissionError('ORIGINAL_FROZEN_BASKET_REQUIRED')
                item_id,revision=line['item_id'],line['revision']
                ids.add(item_id);total+=line['subtotal_minor']
                requested.append({k:line[k] for k in ('item_id','quantity','revision')})
                before=checked_price(self._read(identity,project,'PRICE_VERSION',item_id+':'+str(revision)),item_id,revision)
                reserved=checked_price(self._read(identity,project,'PRICE_VERSION',item_id+':'+str(revision+1)),item_id,revision+1)
                if (not before['enabled'] or before['unit_minor']!=line['unit_minor']
                        or before['stock']<line['quantity']
                        or dict(before,stock=before['stock']-line['quantity'],revision=revision+1,updated_at=reserved['updated_at'])!=reserved):
                    raise PermissionError('ORIGINAL_STOCK_RESERVATION_MISMATCH')
            request_hash=hashlib.sha256(canonical(sorted(requested,key=lambda line:line['item_id']))).hexdigest()
            if total!=record['amount_minor'] or record.get('request_hash')!=request_hash:
                raise PermissionError('ORIGINAL_FROZEN_BASKET_MISMATCH')
            if record.get('stock_released') is True:return
            # Once released, only the immutable reservation is relevant; later
            # catalogue edits must never turn a successful recovery into a retry.
            updates=[]
            for line in record['lines']:
                item_id=line['item_id']
                self._catalog_item(identity,item_id,False)
                price=checked_price(self._read(identity,project,'PRODUCT',item_id),item_id)
                if (price['revision']<line['revision']+1
                        or self._read(identity,project,'PRICE_VERSION',item_id+':'+str(price['revision']))!=price):
                    raise ValueError('ORIGINAL_PRODUCT_VERSION_CONFLICT')
                updated=dict(price,stock=price['stock']+line['quantity'],revision=price['revision']+1,updated_at=c.now())
                updates.append((item_id,updated))
            for item_id,updated in updates:
                if updated['stock']>100000000:raise ValueError('INVENTORY_RESTORE_OVERFLOW')
                self._save(identity,project,uid,'PRICE_VERSION',item_id+':'+str(updated['revision']),updated)
                self._save(identity,project,uid,'PRODUCT',item_id,updated,True)
            self._save(identity,project,uid,'ORDER',reference,dict(record,stock_released=True),True)
            c.audit(project,uid,'CANCELLED_ORDER_STOCK_RELEASED',reference)
