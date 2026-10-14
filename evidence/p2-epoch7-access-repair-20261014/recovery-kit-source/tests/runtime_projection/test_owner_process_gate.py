"""Owner process authorization with local-only canonical SQLite fixtures."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import owner_dashboard
import uk_owner_callback_core as core
from execution_ledger import ExecutionLedger, LeaseLost
from test_read_integration import FakeConnection, Fixture, TEST_DIR


class OwnerProcessGateTests(Fixture):
    def test_missing_verifier_denies_before_activation_or_mutation(self):
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, self.callback_uid)
        with self.assertRaises(PermissionError):
            server.serve_connection(FakeConnection(self.callback_uid, self.owner_request()))
        self.store.read.assert_not_called()
        self.assertEqual(self.ledger.method_calls, [])

    def test_same_uid_dashboard_is_rejected_by_exact_process_verifier(self):
        verify = mock.Mock(side_effect=lambda pid, uid: pid == 100 and uid == self.callback_uid)
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, self.callback_uid,
                                               owner_process_verifier=verify)
        with self.assertRaises(PermissionError):
            server.serve_connection(FakeConnection(self.callback_uid, self.owner_request(), pid=200))
        verify.assert_called_once_with(200, self.callback_uid)
        self.store.read.assert_not_called()
        self.assertEqual(self.ledger.method_calls, [])

    def test_nonliteral_true_and_errors_never_authorize(self):
        for value in (False, None, 1, 'trusted', {}):
            self.server.owner_process_verifier = mock.Mock(return_value=value)
            with self.assertRaises(PermissionError):
                self.server.serve_connection(FakeConnection(self.callback_uid, self.owner_request()))
        self.server.owner_process_verifier = mock.Mock(side_effect=OSError('proc access denied'))
        with self.assertRaises(OSError):
            self.server.serve_connection(FakeConnection(self.callback_uid, self.owner_request()))
        self.store.read.assert_not_called()
        self.assertEqual(self.ledger.method_calls, [])

    def test_invalid_verifier_configuration_rejected(self):
        for verifier in (False, 1, 'trusted'):
            with self.assertRaises(ValueError):
                core.LedgerOwnerDecisionServer(self.store, self.ledger, self.callback_uid,
                                               owner_process_verifier=verifier)

    def test_owner_verifier_is_not_used_for_read_projection(self):
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, self.callback_uid)
        connection = FakeConnection(self.callback_uid,
            self.request('DASHBOARD_SNAPSHOT', {'limit':1}))
        with mock.patch.object(owner_dashboard, 'snapshot', return_value={'tasks': []}):
            server.serve_connection(connection)
        self.assertEqual(json.loads(connection.sent.decode())['result'], {'tasks': []})
        self.assertEqual(self.ledger.method_calls, [])

    def test_late_owner_verifier_rejected_before_mutation(self):
        now = [100.0]
        def verify(*args):
            now[0] += 5
            return True
        self.server.owner_process_verifier = verify
        with mock.patch('ledger_read_transport.time.monotonic', lambda: now[0]):
            with self.assertRaises(OSError):
                self.server.serve_connection(FakeConnection(self.callback_uid, self.owner_request()))
        self.store.read.assert_not_called()
        self.assertEqual(self.ledger.method_calls, [])


class OwnerCanonicalTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='owner-db-tests-', dir=TEST_DIR)
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, 'fixture.sqlite')
        with sqlite3.connect(self.path) as db:
            for table, fields in ExecutionLedger.SCHEMAS.items():
                declarations = [name + ' ' + kind + (' PRIMARY KEY' if primary else '')
                                for name, kind, primary in fields]
                db.execute('CREATE TABLE ' + table + '(' + ','.join(declarations) + ')')
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                ('task', 'CODEX_EXEC', 'WAITING_HUMAN', '[]', None, None, 3, '{}', 900.0))
            db.execute('INSERT INTO approvals VALUES(?,?,?,?)', ('task','PENDING',900.0,None))
        core.install_schema(self.path)
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO owner_callback_requests VALUES(?,?,?,?,?,?,?)',
                ('registered', 'task', 3, '42', '43', 2000.0, 0))
        self.active = dict(ledger_uuid='u', generation=1, epoch=8, instance='i',
            db_path=self.path, ledger_socket='/run/unused.sock')
        self.store = mock.Mock()
        self.store.read.side_effect = lambda **kwargs: dict(self.active)
        self.ledger = ExecutionLedger(self.path, ['org/repo'], clock=lambda:1000.0,
                                      activation_store=self.store)
        self.verifier = mock.Mock(side_effect=lambda pid, uid: pid == 123 and uid == 1004)
        self.server = core.LedgerOwnerDecisionServer(self.store, self.ledger, 1004,
                                                    owner_process_verifier=self.verifier)
        self.request = {key:self.active[key] for key in core.ACTIVATION_KEYS}
        self.request.update(operation='OWNER_DECISION', event=dict(request_id='registered',
            task_id='task', fence=3, owner_user_id='42', owner_chat_id='43', update_id=101,
            decision='APPROVE'))
    def digest(self):
        with open(self.path, 'rb') as stream: return hashlib.sha256(stream.read()).hexdigest()
    def invoke(self, pid=123):
        connection = FakeConnection(1004, self.request, pid=pid)
        self.server.serve_connection(connection)
        return json.loads(connection.sent.decode())
    def state(self):
        with sqlite3.connect(self.path) as db:
            return (db.execute('SELECT state FROM tasks').fetchone()[0],
                    db.execute('SELECT decision FROM approvals').fetchone()[0],
                    db.execute('SELECT consumed FROM owner_callback_requests').fetchone()[0],
                    db.execute('SELECT COUNT(*) FROM owner_callback_replays').fetchone()[0])
    def test_verified_callback_valid_approve_retains_atomic_gates(self):
        result = self.invoke()
        self.assertIs(result['accepted'], True)
        self.verifier.assert_called_once_with(123, 1004)
        self.assertEqual(self.state(), ('PENDING', 'APPROVE', 1, 1))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT event FROM events').fetchall(), [('OWNER_APPROVE',)])
    def test_verified_callback_valid_reject_is_unchanged(self):
        self.request['event']['decision'] = 'REJECT'
        self.assertIs(self.invoke()['accepted'], True)
        self.assertEqual(self.state(), ('FAILED', 'REJECT', 1, 1))
    def test_same_uid_dashboard_valid_event_cannot_mutate(self):
        before = self.digest()
        with self.assertRaises(PermissionError): self.invoke(pid=456)
        self.assertEqual(self.digest(), before)
        self.assertEqual(self.state(), ('WAITING_HUMAN', 'PENDING', 0, 0))
    def test_missing_production_verifier_cannot_mutate(self):
        self.server.owner_process_verifier = None
        before = self.digest()
        with self.assertRaises(PermissionError): self.invoke()
        self.assertEqual(self.digest(), before)
    def test_registered_request_owner_and_fence_gates_preserved(self):
        for key, value in (('request_id','missing'), ('owner_user_id','44'),
                ('owner_chat_id','45'), ('fence',4)):
            old = self.request['event'][key]; self.request['event'][key] = value
            before = self.digest()
            with self.assertRaises(PermissionError): self.invoke()
            self.assertEqual(self.digest(), before)
            self.request['event'][key] = old
    def test_expired_request_is_rejected_after_process_auth(self):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE owner_callback_requests SET expires_at=999')
        before = self.digest()
        with self.assertRaises(PermissionError): self.invoke()
        self.assertEqual(self.digest(), before)
    def test_consumed_request_replay_is_rejected(self):
        self.invoke(); before = self.digest()
        with self.assertRaises(PermissionError): self.invoke()
        self.assertEqual(self.digest(), before)
        self.assertEqual(self.state(), ('PENDING', 'APPROVE', 1, 1))
    def test_duplicate_update_id_rolls_back_transaction(self):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO owner_callback_replays VALUES(?,?)', (101,'prior-request'))
        before = self.digest()
        with self.assertRaises(sqlite3.IntegrityError): self.invoke()
        self.assertEqual(self.digest(), before)
        self.assertEqual(self.state(), ('WAITING_HUMAN', 'PENDING', 0, 1))
    def test_task_state_gate_is_preserved(self):
        with sqlite3.connect(self.path) as db: db.execute("UPDATE tasks SET state='DONE'")
        before = self.digest()
        with self.assertRaises(LeaseLost): self.invoke()
        self.assertEqual(self.digest(), before)
    def test_stale_activation_is_rejected(self):
        self.request['epoch'] = 7; before = self.digest()
        with self.assertRaises(PermissionError): self.invoke()
        self.assertEqual(self.digest(), before)


if __name__ == '__main__': unittest.main()
