"""Owned consumer refund applications and merchant review, separate from money."""
import hashlib
import json
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
                  'refund_application': {'reference', 'application_id'}}
        if operation not in fields or type(params) is not dict or set(params) != fields[operation]:
            raise ValueError('INVALID_REFUND_APPLICATION_FIELDS')
        p = params
        if not valid_id(p['reference']) or not valid_id(p['application_id']):
            raise ValueError('INVALID_REFUND_APPLICATION_ID')
        i.authorize_order_read(token, scene, p['reference'], c.now())
        uid, project, principal = i._resolve(token, scene)
        identity = i.runtime.bindings[principal]
        with c.tx():
            c.limit('consumer-refund-application:' + uid, 20, 60)
            record = self.commerce._read(identity, project, 'REFUND_APPLICATION', p['application_id'])
            if record is not None:
                if record['user_id'] != uid or record['reference'] != p['reference']:
                    raise PermissionError('REFUND_APPLICATION_OWNER_REQUIRED')
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
            pointer = self.commerce._read(identity, project, 'REFUND_CURRENT', p['reference'])
            if pointer:
                prior = self.commerce._read(identity, project, 'REFUND_APPLICATION', pointer['application_id'])
                if prior is None or prior['status'] not in ('REJECTED', 'COMPLETED', 'CLOSED'):
                    raise PermissionError('EXISTING_REFUND_APPLICATION_MUST_BE_RESOLVED')
            record = dict(reference=p['reference'], application_id=p['application_id'], scope=identity,
                user_id=uid, project=project, amount_minor=p['amount_minor'], reason=p['reason'],
                status='SUBMITTED', revision=1, opinion='', created_at=c.now())
            self.commerce._save(identity, project, uid, 'REFUND_APPLICATION', p['application_id'], record)
            self.commerce._save(identity, project, uid, 'REFUND_CURRENT', p['reference'], dict(application_id=p['application_id']), True)
            c.audit(project, uid, 'CONSUMER_REFUND_SUBMITTED', p['application_id'])
            return record

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
