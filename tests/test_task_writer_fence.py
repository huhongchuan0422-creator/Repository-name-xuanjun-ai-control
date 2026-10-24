from __future__ import print_function

import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from task_supervisor import Supervisor, UNKNOWN
from task_writer_fence import (
    CommitLease, LocalActionLocks, production_fencing_verdict,
    reconcile_unknown, revoke_with_local_drain,
)


class WriterFenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, 'ledger.sqlite')
        self.lock_root = os.path.join(self.directory.name, 'locks')
        self.now = 1000.0
        self.s = Supervisor(self.path, lambda: self.now)
        self.register('t1')

    def tearDown(self):
        try:
            self.s.close()
        except Exception:
            pass
        self.directory.cleanup()

    def register(self, task):
        self.s.register(dict(
            task_id=task, parent_task_id='parent', stage='dev',
            owner='developer', entry='WORK',
            checkpoint_sha256='a' * 64, spec_sha256='b' * 64,
            next_action='implement', dependencies=[],
            completion_conditions=['tests'],
            progress_deadline=1900, receipt_deadline=1100,
            started_deadline=1200, terminal_deadline=3000,
            handoff_deadline=1800), now=self.now)

    def claim(self, task='t1', attempt='a1', resources=None,
              run='run1', session='session1', gateway='gateway1'):
        return self.s.claim_writer(
            task, attempt, 'developer', 'WORK', run, session,
            'lease-' + attempt, gateway,
            resources or ['git:repo:branch:feature/x'],
            valid_until=1700, now=self.now)

    def caller(self, run='run1', session='session1', gateway='gateway1'):
        return {'caller_id': 'writer-process', 'run_id': run,
                'session_id': session, 'gateway_id': gateway}

    def operation(self, op='op1', event='event1',
                  resource='git:repo:branch:feature/x'):
        return {
            'operation_id': op, 'event_id': event,
            'resource_key': resource, 'operation_kind': 'GIT_COMMIT',
            'expected_before': {'head': 'base-head', 'blob': 'old-blob'},
            'requested_after': {'blob': 'new-blob'},
            'request_sha256': 'c' * 64,
            'operation_marker': 'xuanjun-op:' + op,
        }

    def invalidate_and_complete(self, task='t1'):
        self.s.record_resource_invalidation(
            task, 'git:repo:branch:feature/x',
            {'outcome': 'INVALIDATED', 'proof': 'fake-source-only'},
            now=1100)
        return self.s.complete_revocation(task, now=1101)

    def test_store_allocates_exact_max_plus_one(self):
        ticket = self.claim()
        self.assertEqual((ticket['fence'], ticket['epoch']), (1, 1))
        self.assertEqual(self.s._task('t1')['authority_state'], 'VALID')

    def test_two_scopes_cannot_claim_same_resource(self):
        self.claim()
        self.register('t2')
        with self.assertRaisesRegex(ValueError, 'RESOURCE_SCOPE_CONFLICT'):
            self.claim('t2', 'b1')

    def test_resource_set_claim_is_atomic(self):
        self.claim(resources=['resource:a'])
        self.register('t2')
        with self.assertRaisesRegex(ValueError, 'RESOURCE_SCOPE_CONFLICT'):
            self.claim('t2', 'b1', resources=['resource:b', 'resource:a'])
        self.assertIsNone(self.s.db.execute(
            "SELECT 1 FROM resource_claims WHERE resource_key='resource:b'"
        ).fetchone())

    def test_stolen_ticket_wrong_caller_is_rejected(self):
        ticket = self.claim()
        with self.assertRaisesRegex(ValueError, 'CALLER_CONTEXT_MISMATCH'):
            self.s.prepare_operation(
                ticket, self.caller(session='stolen-session'),
                self.operation(), now=1001)

    def test_prepare_then_revoking_blocks_dispatch(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        self.s.begin_revocation('t1', controller, now=1002)
        with self.assertRaisesRegex(ValueError, 'WRITER_AUTHORITY_NOT_VALID'):
            self.s.begin_dispatch(ticket, self.caller(), 'op1', now=1003)
        self.assertEqual(self.s.db.execute(
            "SELECT state FROM writer_operations WHERE operation_id='op1'"
        ).fetchone()[0], 'PREPARED')

    def test_commit_lease_holds_final_validation_through_result(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        with CommitLease(self.s, ticket, self.caller(), 'op1',
                         self.lock_root, now=1002) as lease:
            state = self.s.db.execute(
                "SELECT state FROM writer_operations WHERE operation_id='op1'"
            ).fetchone()[0]
            self.assertEqual(state, 'DISPATCHING')
            lease.confirmed({'outcome': 'CONFIRMED',
                             'operation_marker': 'xuanjun-op:op1'},
                            now=1003)
        self.assertEqual(self.s.db.execute(
            "SELECT state FROM writer_operations WHERE operation_id='op1'"
        ).fetchone()[0], 'CONFIRMED')

    def test_revocation_can_cancel_undispatched_prepared_operation(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        self.s.begin_revocation('t1', controller, now=1002)
        ctx = {'role': 'RECONCILER', 'evidence_id': 'prepared-cancel-1',
               'caller_id': 'trusted-readback'}
        result = self.s.reconcile_operation(
            'op1', ctx, 'NOT_APPLIED',
            {'dispatch_started': False, 'readback': 'base-unchanged'},
            receipt={'outcome': 'NOT_APPLIED',
                     'reason': 'PREPARED_NEVER_DISPATCHED'},
            now=1003)
        self.assertEqual(result['state'], 'NOT_APPLIED')
        self.assertEqual(self.s.unresolved_operations('t1'), [])
        with self.assertRaisesRegex(
                ValueError, 'OPERATION_NOT_RECONCILABLE'):
            self.s.reconcile_operation(
                'op1', {'role': 'RECONCILER', 'evidence_id': 'again',
                        'caller_id': 'trusted-readback'},
                'CONFIRMED', {'readback': 'no'},
                receipt={'outcome': 'CONFIRMED'}, now=1004)

    def test_unknown_can_be_reconciled_without_redispatch(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        with CommitLease(self.s, ticket, self.caller(), 'op1',
                         self.lock_root, now=1002) as lease:
            lease.unknown({'transport': 'connection-lost'}, now=1003)
        ctx = {'role': 'RECONCILER', 'evidence_id': 'readback-1',
               'caller_id': 'trusted-readback'}
        result = reconcile_unknown(
            self.s, 'op1', ctx, 'NOT_APPLIED',
            {'readback': 'base-head-still-current'},
            receipt={'outcome': 'NOT_APPLIED', 'marker': 'absent'},
            now=1004)
        self.assertEqual(result['state'], 'NOT_APPLIED')
        evidence = self.s.db.execute(
            "SELECT count(*) FROM writer_reconcile_evidence WHERE operation_id='op1'"
        ).fetchone()[0]
        receipts = self.s.db.execute(
            "SELECT count(*) FROM writer_receipts WHERE operation_id='op1'"
        ).fetchone()[0]
        self.assertGreaterEqual(evidence, 2)
        self.assertEqual(receipts, 1)

    def test_unknown_observation_does_not_consume_final_receipt(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        self.s.begin_dispatch(ticket, self.caller(), 'op1', now=1002)
        ctx1 = {'role': 'RECONCILER', 'evidence_id': 'probe-unknown',
                'caller_id': 'trusted-readback'}
        self.s.reconcile_operation('op1', ctx1, 'UNKNOWN',
                                   {'readback': 'timeout'}, now=1003)
        self.assertIsNone(self.s.db.execute(
            "SELECT 1 FROM writer_receipts WHERE operation_id='op1'"
        ).fetchone())
        ctx2 = {'role': 'RECONCILER', 'evidence_id': 'probe-final',
                'caller_id': 'trusted-readback'}
        self.s.reconcile_operation(
            'op1', ctx2, 'CONFLICT', {'readback': 'different-marker'},
            receipt={'outcome': 'CONFLICT', 'marker': 'other-operation'},
            now=1004)
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM writer_receipts WHERE operation_id='op1'"
        ).fetchone()[0], 1)

    def test_final_receipt_same_bytes_idempotent_different_bytes_conflict(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        self.s.begin_dispatch(ticket, self.caller(), 'op1', now=1002)
        receipt = {'outcome': 'CONFIRMED', 'operation_marker': 'xuanjun-op:op1'}
        self.s.confirm_operation(ticket, self.caller(), 'op1', receipt,
                                 now=1003)
        with self.s.db:
            self.assertTrue(
                self.s._append_receipt_locked('op1', receipt, 1004)['duplicate'])
            with self.assertRaisesRegex(ValueError, 'FINAL_RECEIPT_CONFLICT'):
                self.s._append_receipt_locked(
                    'op1', {'outcome': 'CONFIRMED', 'operation_marker': 'x'}, 1005)

    def test_kill_restart_dispatched_remains_unresolved(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        self.s.begin_dispatch(ticket, self.caller(), 'op1', now=1002)
        self.s.close()
        self.s = Supervisor(self.path, lambda: self.now)
        self.assertEqual(self.s.unresolved_operations('t1')[0]['state'],
                         'DISPATCHING')
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        self.s.begin_revocation('t1', controller, now=1003)
        with self.assertRaisesRegex(ValueError, 'REVOCATION_NOT_COMPLETED'):
            self.s.complete_revocation('t1', now=1004)

    def test_revoke_timeout_does_not_become_revoked(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        entered = threading.Event()
        release = threading.Event()

        def old_writer():
            worker = Supervisor(self.path, lambda: 1002.0)
            try:
                with CommitLease(worker, ticket, self.caller(), 'op1',
                                 self.lock_root, now=1002) as lease:
                    entered.set()
                    release.wait(2)
                    lease.unknown({'transport': 'still-running'}, now=1003)
            finally:
                worker.close()

        thread = threading.Thread(target=old_writer)
        thread.start()
        self.assertTrue(entered.wait(1))
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        with self.assertRaisesRegex(ValueError, 'REVOCATION_NOT_COMPLETED'):
            revoke_with_local_drain(
                self.s, 't1', controller, self.lock_root, timeout=0.05,
                now=1002)
        self.assertEqual(self.s._task('t1')['authority_state'], 'REVOKING')
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_revoking_blocks_all_new_effects(self):
        ticket = self.claim()
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        self.s.begin_revocation('t1', controller, now=1001)
        with self.assertRaisesRegex(ValueError, 'WRITER_AUTHORITY_NOT_VALID'):
            self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                     now=1002)

    def test_revoke_coverage_ack_and_takeover_are_gapless(self):
        old = self.claim()
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        self.s.begin_revocation('t1', controller, now=1050)
        result = self.invalidate_and_complete()
        ack = {
            'task_id': 't1', 'old_attempt_id': 'a1',
            'new_attempt_id': 'a2', 'new_owner': 'developer',
            'new_entry': 'WORK', 'new_run_id': 'run2',
            'new_session_id': 'session2', 'new_lease_id': 'lease-a2',
            'new_gateway_id': 'gateway2',
            'resource_scope_digest': result['coverage_digest'],
            'spec_sha256': 'b' * 64, 'checkpoint_sha256': 'a' * 64,
        }
        self.s.record_receiver_ack('t1', ack, now=1102)
        new = self.s.takeover_claim('t1', ack, valid_until=1800, now=1103)
        self.assertEqual((new['fence'], new['epoch']), (2, 2))
        self.assertEqual(self.s._task('t1')['authority_state'], 'VALID')
        with self.assertRaises(ValueError):
            self.s.prepare_operation(old, self.caller(), self.operation('old'),
                                     now=1104)

    def test_unknown_authority_only_recovers_to_revoking(self):
        self.claim()
        self.s.db.execute("UPDATE tasks SET authority_state=? WHERE task_id='t1'",
                          (UNKNOWN,))
        self.s.db.commit()
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        result = self.s.recover_unknown_to_revoking(
            't1', controller, {'readback_plan': 'required'}, now=1050)
        self.assertEqual(result['state'], 'REVOKING')
        self.assertEqual(self.s._task('t1')['state'], 'HOLD')
        with self.assertRaises(ValueError):
            self.s.takeover_claim('t1', {}, valid_until=1800, now=1051)

    def test_clock_rollback_and_expiry_fail_closed(self):
        ticket = self.claim()
        self.s.prepare_operation(ticket, self.caller(), self.operation(),
                                 now=1001)
        with self.assertRaisesRegex(ValueError, 'CLOCK_ROLLBACK_HOLD'):
            self.s.prepare_operation(
                ticket, self.caller(), self.operation('op2', 'event2'),
                now=999)
        with self.assertRaisesRegex(ValueError, 'WRITER_TICKET_EXPIRED'):
            self.s.prepare_operation(
                ticket, self.caller(), self.operation('op3', 'event3'),
                now=1700)

    def test_operation_identity_cannot_rebind(self):
        ticket = self.claim()
        op = self.operation()
        first = self.s.prepare_operation(ticket, self.caller(), op, now=1001)
        second = self.s.prepare_operation(ticket, self.caller(), op, now=1002)
        self.assertFalse(first['duplicate'])
        self.assertTrue(second['duplicate'])
        changed = dict(op)
        changed['request_sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'OPERATION_IDENTITY_CONFLICT'):
            self.s.prepare_operation(ticket, self.caller(), changed, now=1003)

    def test_content_match_without_operation_marker_is_not_confirmed(self):
        # Offline GitHub CAS model: equal content alone is not attributable.
        def readback(expected_marker, observed):
            if observed.get('marker') != expected_marker:
                return 'UNKNOWN'
            if observed.get('parent') != 'base-head':
                return 'CONFLICT'
            return 'CONFIRMED'
        self.assertEqual(
            readback('xuanjun-op:op1',
                     {'blob': 'new-blob', 'parent': 'base-head'}),
            'UNKNOWN')

    def test_shared_raw_credential_bypass_forces_production_hold(self):
        verdict = production_fencing_verdict(
            inventory_complete=False, raw_write_capable=True)
        self.assertEqual(verdict['production_fencing'], 'HOLD')
        self.assertIn('UNFENCED_PATH_PRESENT', verdict['reasons'])
        self.assertIn('PRODUCTION_INVENTORY_INCOMPLETE', verdict['reasons'])


if __name__ == '__main__':
    unittest.main()
