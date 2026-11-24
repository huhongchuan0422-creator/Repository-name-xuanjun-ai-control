"""Owned consumer refund applications and merchant review, separate from money."""
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import valid_id
from scripts.community_order_store import state
from scripts.community_order_provider_projection import provider_evidence
from scripts.community_customer_profile import notify


class RefundRequests:
    def __init__(self, commerce):
        self.commerce, self.center = commerce, commerce.center

    def consumer(self, token, scene, operation, params):
        i, c = self.commerce.identity, self.center
        fields = {'refund_apply': {'reference', 'application_id', 'amount_minor', 'reason'},
                  'refund_application': {'reference', 'application_id'},
                  'refund_current': {'reference'}}
        if operation not in fields or type(params) is not dict or set(params) != fields[operation]:
            raise ValueError('INVALID_REFUND_APPLICATION_FIELDS')
        p = params
        if not valid_id(p['reference']) or operation != 'refund_current' and not valid_id(p['application_id']):
            raise ValueError('INVALID_REFUND_APPLICATION_ID')
        i.authorize_order_read(token, scene, p['reference'], c.now())
        uid, project, principal = i._resolve(token, scene)
        identity = i.runtime.bindings[principal]
        with c.tx():
            c.limit('consumer-refund-application:' + uid, 20, 60)
            def owned_row(kind, reference):
                key = self.commerce._key(identity, kind, reference)
                row = c.db.execute("SELECT user_id,payload FROM links WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=? AND project=? AND active=1", (key, project)).fetchone()
                if row is None:return False, None
                if row[0] != uid:raise PermissionError('CURRENT_REFUND_LINK_OWNER_REQUIRED')
                return True, json.loads(c.decrypt(row[1], 'community-commerce:' + key))

            def application(application_id):
                exists, record = owned_row('REFUND_APPLICATION', application_id)
                if not exists:return None
                if (type(record) is not dict or record.get('application_id') != application_id
                        or record.get('reference') != p['reference'] or record.get('user_id') != uid
                        or record.get('scope') != identity or record.get('project') != project):
                    raise PermissionError('CURRENT_REFUND_BINDING_REQUIRED')
                return record

            if operation == 'refund_current':
                exists, pointer = owned_row('REFUND_CURRENT', p['reference'])
                if not exists:return dict(reference=p['reference'], application=None)
                if type(pointer) is not dict or not valid_id(pointer.get('application_id')):
                    raise ValueError('INVALID_CURRENT_REFUND_POINTER')
                current = application(pointer['application_id'])
                if current is None:raise PermissionError('CURRENT_REFUND_BINDING_REQUIRED')
                c.audit(project, uid, 'CONSUMER_REFUND_CURRENT_READ', p['reference'])
                return dict(reference=p['reference'], application=current)
            record = application(p['application_id'])
            if record is not None:
                if operation == 'refund_apply' and any(record[k] != p[k] for k in ('amount_minor', 'reason')):
                    raise ValueError('REFUND_APPLICATION_ID_COLLISION')
                return record
            if operation != 'refund_apply':
                raise ValueError('REFUND_APPLICATION_NOT_FOUND')
            order = state(i.runtime.demo.db, identity, p['reference'])
            if order['state'] != 'SUCCESS' or provider_evidence(i.runtime.demo.db, identity, p['reference']) is None:
                raise PermissionError('VERIFIED_PAID_ORDER_REQUIRED')
            if (type(p['amount_minor']) is not int or not 1 <= p['amount_minor'] <= order['amount_minor']
                    or type(p['reason']) is not str or not 1 <= len(p['reason']) <= 80
                    or any(ord(ch) < 32 for ch in p['reason'])):
                raise ValueError('INVALID_REFUND_APPLICATION')
            exists, pointer = owned_row('REFUND_CURRENT', p['reference'])
            if exists:
                if type(pointer) is not dict or not valid_id(pointer.get('application_id')):
                    raise ValueError('INVALID_CURRENT_REFUND_POINTER')
                prior = application(pointer['application_id'])
                if prior is None or prior['status'] not in ('REJECTED', 'COMPLETED', 'CLOSED'):
                    raise PermissionError('EXISTING_REFUND_APPLICATION_MUST_BE_RESOLVED')
            record = dict(reference=p['reference'], application_id=p['application_id'], scope=identity,
                user_id=uid, project=project, amount_minor=p['amount_minor'], reason=p['reason'],
                status='SUBMITTED', revision=1, opinion='', created_at=c.now())
            self.commerce._save(identity, project, uid, 'REFUND_APPLICATION', p['application_id'], record)
            self.commerce._save(identity, project, uid, 'REFUND_CURRENT', p['reference'], dict(application_id=p['application_id']), True)
            c.audit(project, uid, 'CONSUMER_REFUND_SUBMITTED', p['application_id'])
            return record

    def directory(self, g, params):
        """Discover original records, without a second queue or state projection."""
        if (type(params) is not dict or set(params) != {'after_id'}
                or type(params['after_id']) is not str
                or params['after_id'] and not re.fullmatch('[0-9a-f]{64}', params['after_id'])):
            raise ValueError('INVALID_REFUND_DIRECTORY_CURSOR')
        c = self.center
        with c.tx():
            c.limit('merchant-refund-directory:' + g['user_id'], 30, 60)
            cursor, found, scanned = params['after_id'], [], 0
            # Original links contains several record kinds and stores. Iterate
            # at most 1000 mixed rows per request; sparse pages can continue.
            while len(found) < 51 and scanned < 1000:
                rows = c.db.execute(
                    "SELECT subject_idx,user_id,payload FROM links WHERE channel='COMMUNITY_COMMERCE_V1' AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT ?",
                    (g['project'], cursor, min(200, 1000-scanned))).fetchall()
                if not rows:break
                for key, owner, raw in rows:
                    cursor = key
                    scanned += 1
                    value = json.loads(c.decrypt(raw, 'community-commerce:' + key))
                    if type(value) is not dict or 'application_id' not in value:continue
                    application = value['application_id']
                    if not valid_id(application):raise ValueError('INVALID_STORED_REFUND_ID')
                    expected = self.commerce._key(g['scope'], 'REFUND_APPLICATION', application)
                    if key != expected:continue  # Other stores and REFUND_CURRENT pointers.
                    if (value.get('scope') != g['scope'] or value.get('project') != g['project']
                            or value.get('user_id') != owner or not valid_id(value.get('reference'))):
                        raise PermissionError('REFUND_DIRECTORY_BINDING_CHANGED')
                    found.append((key, value))
                    if len(found) == 51:break
                if len(rows) < 200:break
            # A lookahead refund is never consumed unless returned. Otherwise
            # resume after the last examined mixed row, including on empty pages.
            if len(found)>50:
                more, next_cursor = True, found[49][0]
            else:
                more = c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_COMMERCE_V1' AND project=? AND active=1 AND subject_idx>? LIMIT 1", (g['project'], cursor)).fetchone() is not None
                next_cursor = cursor if more else None
            c.audit(g['project'], g['user_id'], 'MERCHANT_REFUND_DIRECTORY_READ', 'SCOPED_READ')
            return dict(records=[r[1] for r in found[:50]], has_more=more, next_cursor=next_cursor)

    def review(self, g, operation, params):
        p, c = params, self.center
        fields = {'refund_application_read': {'application_id'},
                  'refund_decide': {'application_id', 'expected_revision', 'decision', 'opinion'}}
        if operation not in fields or type(p) is not dict or set(p) != fields[operation] or not valid_id(p['application_id']):
            raise ValueError('INVALID_REFUND_REVIEW_FIELDS')
        with c.tx():
            record = self.commerce._read(g['scope'], g['project'], 'REFUND_APPLICATION', p['application_id'])
            if record is None or record['scope'] != g['scope'] or record['project'] != g['project']:
                raise PermissionError('SCOPED_REFUND_APPLICATION_REQUIRED')
            if operation == 'refund_application_read':
                return record
            if record['user_id'] == g['user_id']:
                raise PermissionError('SELF_REFUND_REVIEW_DENIED')
            if (type(p['expected_revision']) is not int or record['revision'] != p['expected_revision']
                    or record['status'] != 'SUBMITTED' or p['decision'] not in ('APPROVED', 'REJECTED')
                    or type(p['opinion']) is not str or not 1 <= len(p['opinion']) <= 1000):
                raise ValueError('REFUND_REVIEW_STATE_OR_VERSION_CONFLICT')
            result = dict(record, status=p['decision'], revision=record['revision']+1,
                opinion=p['opinion'], reviewed_by=g['user_id'], reviewed_at=c.now())
            self.commerce._save(g['scope'], g['project'], record['user_id'], 'REFUND_APPLICATION', p['application_id'], result, True)
            notify(c, g['project'], record['user_id'], 'REFUND_REVIEW', p['application_id'], result['status']+'：'+result['opinion'])
            c.audit(g['project'], g['user_id'], 'MERCHANT_REFUND_' + p['decision'], p['application_id'])
            return result

    def execute(self, actions, session, csrf, workspace, operation, params):
        if type(params) is not dict or set(params) != {'application_id'} or not valid_id(params['application_id']):
            raise ValueError('INVALID_APPROVED_REFUND_EXECUTION')
        g, _ = actions._authorize(session, csrf, workspace)
        c = self.center
        with c.tx():
            record = self.commerce._read(g['scope'], g['project'], 'REFUND_APPLICATION', params['application_id'])
            if record is None or record['scope'] != g['scope'] or record['project'] != g['project']:
                raise PermissionError('APPROVED_SCOPED_REFUND_REQUIRED')
            if g['user_id'] == record['user_id'] or record['status'] not in ('APPROVED', 'EXECUTION_RESERVED', 'COMPLETED', 'CLOSED'):
                raise PermissionError('INDEPENDENT_REFUND_EXECUTION_REQUIRED')
            event = hashlib.sha256(canonical([g['scope'], record['application_id']])).hexdigest()
            consumed = c.db.execute("SELECT 1 FROM events WHERE channel='COMMUNITY_REFUND_APPLICATION_EXECUTION' AND event_id=?", (event,)).fetchone()
            if operation == 'execute_refund_application' and consumed is None:
                c.db.execute("INSERT INTO events VALUES('COMMUNITY_REFUND_APPLICATION_EXECUTION',?,?)", (event, c.now()))
                operation_name = 'refund'
                record = dict(record, status='EXECUTION_RESERVED', revision=record['revision']+1)
                self.commerce._save(g['scope'], g['project'], record['user_id'], 'REFUND_APPLICATION', record['application_id'], record, True)
            else:
                if consumed is None:
                    raise ValueError('REFUND_NOT_EXECUTED')
                operation_name = 'resume_refund' if operation == 'execute_refund_application' else 'query_refund'
        request = dict(reference=record['reference'], request_id=record['application_id'])
        if operation_name == 'resume_refund':
            # The application reservation and provider intent are separate durable records.
            # Recover only the original, explicitly approved request; never auto-POST on query.
            try:
                actions.dispatch(session, csrf, dict(workspace=workspace,
                    operation='status_refund', params=request))
            except ValueError as exc:
                if str(exc) != 'PROVIDER_ACTION_NOT_FOUND':
                    raise
                operation_name = 'refund'
            else:
                operation_name = 'query_refund'
        if operation_name == 'refund':
            request.update(amount_minor=record['amount_minor'], reason=record['reason'])
        result = actions.dispatch(session, csrf, dict(workspace=workspace, operation=operation_name, params=request))
        if result['status'] in ('SUCCESS', 'CLOSED'):
            with c.tx():
                current = self.commerce._read(g['scope'], g['project'], 'REFUND_APPLICATION', record['application_id'])
                if current['status'] not in ('EXECUTION_RESERVED', 'COMPLETED', 'CLOSED'):
                    raise ValueError('REFUND_APPLICATION_EXECUTION_CONFLICT')
                new_status = 'COMPLETED' if result['status']=='SUCCESS' else 'CLOSED'
                if current['status'] in ('COMPLETED', 'CLOSED'):
                    if current['status'] != new_status:
                        raise ValueError('REFUND_APPLICATION_TERMINAL_CONFLICT')
                    return dict(result, application_id=record['application_id'])
                current = dict(current, status=new_status, revision=current['revision']+1)
                self.commerce._save(g['scope'], g['project'], current['user_id'], 'REFUND_APPLICATION', current['application_id'], current, True)
                notify(c, g['project'], current['user_id'], 'REFUND_RESULT', current['application_id'], '微信退款状态：'+result['status'])
                c.audit(g['project'], g['user_id'], 'REFUND_APPLICATION_PROVIDER_CONFIRMED', event)
        return dict(result, application_id=record['application_id'])
