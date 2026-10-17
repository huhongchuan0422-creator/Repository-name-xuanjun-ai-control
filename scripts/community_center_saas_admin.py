"""Project-bounded original SaaS administration; no financial authority or repair."""
import json
import sqlite3

FIELDS = {
    'owner_admin_snapshot': set(),
    'owner_review_open': {'task_id', 'order_id', 'kind', 'reason'},
    'owner_review_close': {'task_id', 'event_id', 'state'},
    'owner_refund_reversal_plan': {'order_id', 'reason'},
    'owner_diagnostics': set(),
}


def dispatch(api, grant, operation, params):
    if grant['role'] != 'PLATFORM_OWNER':
        raise PermissionError('ORIGINAL_PLATFORM_OWNER_REQUIRED')
    center, runtime = api.center, api.runtime
    db = runtime.saas.orders

    def owned_orders():
        # Historical tenant-only records do not imply project admission.
        admitted = set()
        rows = center.db.execute(
            "SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_SAAS_ORDER' AND project=? AND active=1",
            (grant['project'],)).fetchall()
        for reference, payload in rows:
            value = json.loads(center.decrypt(payload, 'community-saas:' + reference))
            if type(value) is not dict:
                raise ValueError('INVALID_SAAS_PROJECT_ORDER_BINDING')
            if value.get('tenant_id') != grant['tenant'] or value.get('order_id') != reference:
                raise PermissionError('SAAS_PROJECT_ORDER_BINDING_CHANGED')
            admitted.add(reference)
        return admitted

    def original(op, fields):
        return runtime.dispatch(grant['principal'], op, fields, None)

    def require_order(reference):
        if type(reference) is not str or reference not in owned_orders():
            raise PermissionError('SAAS_PROJECT_ORDER_REQUIRED')
        # Original reader additionally verifies that the actual order belongs to tenant.
        original('order_read', {'order_id': reference})

    def project_snapshot():
        admitted = owned_orders()
        snapshot = original('admin_snapshot', {})
        return dict(
            orders=[r for r in snapshot['orders'] if r['order_id'] in admitted],
            review_tasks=[r for r in snapshot['review_tasks'] if r['order_id'] in admitted],
            missing_order_reservations=sorted(admitted - {r['order_id'] for r in snapshot['orders']}),
            scope='ORIGINAL_PROJECT_OWNED_ORDERS',
            production_payments_verified=False, live_deployment=False)

    if operation == 'owner_admin_snapshot':
        return project_snapshot()
    if operation == 'owner_review_open':
        require_order(params['order_id'])
        return original('review_open', params)
    if operation == 'owner_review_close':
        if type(params['task_id']) is not str:
            raise ValueError('INVALID_REVIEW_TASK_ID')
        row = db.execute('SELECT order_id FROM saas_review_tasks WHERE task_id=? AND tenant_id=?',
                         (params['task_id'], grant['tenant'])).fetchone()
        if row is None:
            raise PermissionError('SAAS_PROJECT_REVIEW_REQUIRED')
        require_order(row[0])
        return original('review_close', params)
    if operation == 'owner_refund_reversal_plan':
        require_order(params['order_id'])
        return original('refund_reversal_plan', params)
    if operation == 'owner_diagnostics':
        try:
            snapshot = project_snapshot()
            # Filtering identifiers must never erase an original recovery HOLD.
            original_report = original('recovery', {})
            original_hold = any(original_report[k] for k in
                                ('awaiting_review', 'integrity_hold', 'open_tasks',
                                 'orphan_lifecycle_events_global_hold'))
            report = dict(
                original_recovery_hold=bool(original_hold),
                missing_order_reservations=snapshot['missing_order_reservations'],
                awaiting_review=[r['order_id'] for r in snapshot['orders'] if r['state'] in
                                 ('CONFIRMATION_UNKNOWN', 'AWAITING_EXTERNAL', 'STATE_INCONSISTENT')],
                integrity_hold=[r['order_id'] for r in snapshot['orders'] if r['state'] == 'STATE_INCONSISTENT'],
                open_tasks=[r['task_id'] for r in snapshot['review_tasks'] if r['state'] == 'PENDING'],
                orphan_lifecycle_events_global_hold=bool(original_report['orphan_lifecycle_events_global_hold']),
                resend_payment_requests=False, automatic_reconcile_executed=False)
            hold = any(report[k] for k in ('awaiting_review', 'integrity_hold', 'open_tasks',
                                          'orphan_lifecycle_events_global_hold',
                                          'original_recovery_hold', 'missing_order_reservations'))
            reasons = []
            if original_hold:reasons.append('ORIGINAL_RECOVERY_HOLD')
            if report['missing_order_reservations']:reasons.append('PROJECT_ORDER_PREPARATION_MISSING')
            return dict(status='HOLD' if hold else 'OFFLINE_CHECKED', report=report, reasons=reasons,
                        production_release_authorized=False, automatic_repair_executed=False)
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError):
            return dict(status='HOLD', reason='OFFLINE_STORE_CHECK_FAILED',
                        production_release_authorized=False, automatic_repair_executed=False)
    raise ValueError('INVALID_SAAS_ADMIN_OPERATION')
