"""Delta regression: stale outbox failures must not mutate a successor."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from task_supervisor import Supervisor


class OutboxAttemptTests(unittest.TestCase):
    def scenario(self, origin, target, phase):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'fixture.sqlite')
            s = Supervisor(path, lambda: 2000.0)
            try:
                s.register(dict(task_id='t', parent_task_id='fixture',
                    stage='test', owner='old', entry=origin,
                    checkpoint_sha256='a'*64, spec_sha256='b'*64,
                    next_action='test', dependencies=[],
                    completion_conditions=['tests'],
                    progress_deadline=5000, receipt_deadline=5000,
                    started_deadline=5000, terminal_deadline=5000,
                    handoff_deadline=5000), now=1000)
                s.claim('t', 'a1', 'old', origin, 'r1', 's1', 'l1', 1, 1, 1000)
                s.record('t', 'a1', 'start', 'STARTED', 1001)
                s.scan(1302)
                item = s.due_outbox(1302)[0]
                if phase != 'same':
                    s.record('t', 'a1', 'handoff', 'HANDOFF_REQUESTED', 1303)
                    proof = dict(receiver_accepted=True, old_writer_stopped=True,
                        old_fence_invalidated=True, effects_reconciled=True,
                        new_owner='new', new_entry=target, lease_id='l1',
                        fence=1, epoch=1)
                    s.record('t', 'a1', 'ack', 'HANDOFF_ACKNOWLEDGED',
                             1304, 'PHASE_EXECUTION', 'fixture', proof)
                if phase == 'started':
                    s.claim('t', 'a2', 'new', target, 'r2', 's2', 'l2',
                            2, 2, 1305)
                    s.record('t', 'a2', 'start2', 'STARTED', 1306)
                before = dict(s._task('t'))
                for index in range(5):
                    result = s.outbox_result(item['outbox_id'], False,
                                             1400 + index*300, 'offline')
                self.assertTrue(result['dead_lettered'])
                expected = dict(s._task('t'))
                if phase == 'same':
                    self.assertEqual(expected['state'], 'HOLD')
                else:
                    self.assertEqual(expected, before)
                self.assertEqual(s.due_outbox(999999), [])
                record = s.db.execute(
                    'SELECT * FROM outbox WHERE outbox_id=?',
                    (item['outbox_id'],)).fetchone()
                self.assertEqual(record['attempt_id'], 'a1')
                self.assertEqual(record['attempts'], 5)
                self.assertIsNotNone(record['dead_lettered_at'])
                s.close()
                s = Supervisor(path, lambda: 3000.0)
                self.assertEqual(dict(s._task('t')), expected)
                self.assertEqual(s.due_outbox(999999), [])
            finally:
                s.close()

    def test_same_attempt_failure_still_holds(self):
        for entry in ('WORK', 'DOTS', 'CHATGPT'):
            with self.subTest(entry=entry):
                self.scenario(entry, entry, 'same')

    def test_old_failure_preserves_acknowledged_ready_task(self):
        for entry in ('WORK', 'DOTS', 'CHATGPT'):
            with self.subTest(entry=entry):
                self.scenario(entry, entry, 'ready')

    def test_old_failure_preserves_each_successor_entry_pair(self):
        for origin in ('WORK', 'DOTS', 'CHATGPT'):
            for target in ('WORK', 'DOTS', 'CHATGPT'):
                with self.subTest(origin=origin, target=target):
                    self.scenario(origin, target, 'started')


if __name__ == '__main__':
    unittest.main()
