"""Regression tests for approved refund application recovery (no provider network)."""
import contextlib
import hashlib
import unittest
from unittest import mock

from scripts.pr122_customer_core import canonical
from scripts.community_refund_requests import RefundRequests


class DB:
    def __init__(self):
        self.events = set()
    def execute(self, sql, values):
        if sql.startswith("SELECT 1 FROM events"):
            return Row((1,)) if values[0] in self.events else Row(None)
        if sql.startswith("INSERT INTO events"):
            self.events.add(values[0])
            return Row(None)
        raise AssertionError(sql)


class Row:
    def __init__(self, value):
        self.value = value
    def fetchone(self):
        return self.value


class Center:
    def __init__(self):
        self.db = DB()
        self.audits = []
    def tx(self):
        return contextlib.nullcontext()
    def now(self):
        return 100
    def audit(self, *args):
        self.audits.append(args)


class Commerce:
    def __init__(self, status='APPROVED'):
        self.center = Center()
        self.data = dict(application_id='apply1', reference='order1',
                         project='project1', scope={'tenant_id': 'tenant1'},
                         user_id='consumer1', status=status, revision=2,
                         amount_minor=100, reason='customer requested')
    def _read(self, scope, project, channel, key):
        if channel != 'REFUND_APPLICATION' or key != 'apply1':
            raise AssertionError((channel, key))
        return dict(self.data)
    def _save(self, scope, project, user, channel, key, value, replace):
        self.data = dict(value)


class Actions:
    def __init__(self, provider_exists=False, terminal=None):
        self.provider_exists = provider_exists
        self.terminal = terminal
        self.calls = []
    def _authorize(self, session, csrf, workspace):
        return dict(scope={'tenant_id': 'tenant1'}, project='project1',
                    user_id='reviewer1'), {}
    def dispatch(self, session, csrf, body):
        op = body['operation']
        self.calls.append(op)
        if op == 'status_refund':
            if not self.provider_exists:
                raise ValueError('PROVIDER_ACTION_NOT_FOUND')
            return {'status': 'SUBMITTED_RESULT_UNKNOWN'}
        if op == 'refund':
            self.provider_exists = True
            return {'status': self.terminal or 'PROCESSING'}
        if op == 'query_refund':
            if not self.provider_exists:
                raise ValueError('PROVIDER_ACTION_NOT_FOUND')
            return {'status': self.terminal or 'PROCESSING'}
        raise AssertionError(op)


class RefundRecoveryTest(unittest.TestCase):
    def call(self, commerce, actions, operation='execute_refund_application'):
        with mock.patch('scripts.community_refund_requests.notify'):
            return RefundRequests(commerce).execute(
                actions, 'session', 'csrf', 'workspace', operation,
                {'application_id': 'apply1'})

    def test_reserved_without_provider_intent_recovers_exact_original_request(self):
        c, a = Commerce(), Actions()
        self.call(c, a)
        self.assertEqual(a.calls, ['refund'])
        self.assertEqual(c.data['status'], 'EXECUTION_RESERVED')
        self.call(c, a)
        self.assertEqual(a.calls, ['refund', 'status_refund', 'query_refund'])
        self.assertEqual(a.calls.count('refund'), 1)

    def test_reserved_without_intent_query_does_not_post(self):
        c, a = Commerce(), Actions()
        self.call(c, a)
        a.provider_exists = False
        with self.assertRaisesRegex(ValueError, 'PROVIDER_ACTION_NOT_FOUND'):
            self.call(c, a, 'query_refund_application')
        self.assertEqual(a.calls, ['refund', 'query_refund'])

    def test_reserved_with_provider_intent_queries_only(self):
        c, a = Commerce(status='EXECUTION_RESERVED'), Actions(provider_exists=True)
        event = hashlib.sha256(canonical([c.data['scope'], 'apply1'])).hexdigest()
        c.center.db.events.add(event)
        self.call(c, a)
        self.assertEqual(a.calls, ['status_refund', 'query_refund'])

    def test_completed_replay_does_not_increment_revision(self):
        c, a = Commerce(), Actions(terminal='SUCCESS')
        self.call(c, a)
        revision = c.data['revision']
        self.call(c, a)
        self.assertEqual(c.data['status'], 'COMPLETED')
        self.assertEqual(c.data['revision'], revision)
        self.assertEqual(a.calls.count('refund'), 1)

    def test_terminal_conflict_is_rejected(self):
        c, a = Commerce(), Actions(terminal='SUCCESS')
        self.call(c, a)
        a.terminal = 'CLOSED'
        with self.assertRaisesRegex(ValueError, 'REFUND_APPLICATION_TERMINAL_CONFLICT'):
            self.call(c, a)
        self.assertEqual(c.data['status'], 'COMPLETED')


if __name__ == '__main__':
    unittest.main()
