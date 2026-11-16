import hashlib
import json
import unittest
from test_local_development_executor import LocalExecutorTests


class ExecutionBindingDelta(LocalExecutorTests):
    def test_binding_real_candidate_is_observation_only(self):
        result = self.apply(self.proposal())
        binding = self.adapter.prepare_execution_binding('demo-b', 'attempt-b', result['candidate_event_id'])
        row = self.s.db.execute('SELECT payload_json,evidence_ref FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',
                                ('demo-b', 'attempt-b', result['candidate_event_id'])).fetchone()
        self.assertEqual(binding['candidate_sha256'], row['evidence_ref'])
        self.assertEqual(binding['candidate_sha256'], hashlib.sha256(row['payload_json'].encode()).hexdigest())
        self.assertEqual(binding['code_commit'], result['code_commit'])
        self.assertEqual(binding['execution_state'], 'HOLD_SANDBOX_UNAVAILABLE')
        self.assertEqual(binding['test_command_state'], 'NOT_BOUND')
        self.assertFalse(binding['writer_lease_validated'])
        self.assertFalse(binding['execution_evidence_verified'])
        self.assertEqual(self.s._task('demo-b')['state'], 'STARTED')
        with self.assertRaisesRegex(ValueError, 'HOLD_SANDBOX_UNAVAILABLE'):
            self.s._require_development_execution_ready(json.loads(row['payload_json']))

    def test_reject_tampered_candidate_and_stale_attempt(self):
        result = self.apply(self.proposal())
        eid = result['candidate_event_id']
        with self.assertRaisesRegex(ValueError, 'STALE_TASK_ATTEMPT'):
            self.adapter.prepare_execution_binding('demo-b', 'old-attempt', eid)
        self.s.db.execute("UPDATE events SET evidence_ref=? WHERE task_id=? AND event_id=?", ('0'*64, 'demo-b', eid))
        self.s.db.commit()
        with self.assertRaisesRegex(ValueError, 'CANDIDATE_DIGEST_MISMATCH'):
            self.adapter.prepare_execution_binding('demo-b', 'attempt-b', eid)

    def test_reject_changed_writer_generation(self):
        result = self.apply(self.proposal())
        self.s.db.execute('UPDATE tasks SET fence=fence+1 WHERE task_id=?', ('demo-b',))
        self.s.db.commit()
        with self.assertRaisesRegex(ValueError, 'CURRENT_LOCAL_CANDIDATE_BINDING_REQUIRED'):
            self.adapter.prepare_execution_binding('demo-b', 'attempt-b', result['candidate_event_id'])

if __name__ == '__main__':
    unittest.main()
