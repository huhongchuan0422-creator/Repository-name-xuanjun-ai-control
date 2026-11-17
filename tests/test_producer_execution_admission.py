import hashlib
import json
import unittest
import test_producer_executor_delta as fixtures
from task_supervisor import canonical
from producer_http_contract import REFERENCE_SHA256

class ExecutionAdmission(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ProducerExecutorTests();self.f.producer_http_test=True;self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def test_main_host_real_execution_admits_review(self):
        f=self.f;result=f.host_call(f.proposal())
        self.assertTrue(result['execution_evidence_verified'])
        self.assertEqual(result['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        candidate=f.s.development_candidate('demo-b',result['candidate_event_id'])
        f.s._require_development_execution_ready(candidate)
        from entry_review_gate import complete_reviewed_candidate
        pending=complete_reviewed_candidate(f.s,'demo-b',result['candidate_event_id'],
            {'scripts/task_center_app.py':f.raw},[],{},'synthetic-review')
        self.assertEqual(pending['state'],'HOLD_INDEPENDENT_REVIEW_REQUIRED')
        self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_REVIEWED'").fetchone())
        self.assertEqual(f.s._task('demo-b')['state'],'STARTED')
        row=f.s.db.execute("SELECT * FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone()
        data=json.loads(row['payload_json'])
        self.assertEqual(data['source_sha256'],hashlib.sha256(f.raw).hexdigest())
        self.assertEqual(data['test_reference_sha256'],REFERENCE_SHA256)
        self.assertEqual(data['artifact_sha256'],result['execution_artifact_sha256'])
        f.s.db.execute("UPDATE events SET evidence_ref=? WHERE kind='DEVELOPMENT_EXECUTION'",('0'*64,));f.s.db.commit()
        with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX_UNAVAILABLE'):
            f.s._require_development_execution_ready(candidate)
        print('SYNTHETIC_EXECUTION result='+json.dumps(result,sort_keys=True))
    def test_repeated_success_reuses_bound_execution_and_rejects_tamper(self):
        from unittest.mock import patch
        import producer_http_runner
        f=self.f; request=f.proposal(); real=producer_http_runner.run_producer_http
        with patch('producer_http_runner.run_producer_http',wraps=real) as runner:
            first=f.host_call(request); second=f.host_call(request)
            self.assertEqual(runner.call_count,1)
        self.assertTrue(first['execution_evidence_verified'])
        self.assertTrue(second['execution_evidence_verified'])
        self.assertEqual(first['execution_event_id'],second['execution_event_id'])
        self.assertEqual(first['execution_artifact_sha256'],second['execution_artifact_sha256'])
        self.assertEqual(f.s.db.execute("SELECT count(*) FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone()[0],1)
        prior=f.s.db.execute("SELECT evidence_ref FROM events WHERE kind='DEVELOPMENT_EXECUTION_INTENT'").fetchone()[0]
        f.s.db.execute("UPDATE events SET evidence_ref=? WHERE kind='DEVELOPMENT_EXECUTION_INTENT'",('0'*64,));f.s.db.commit()
        with self.assertRaisesRegex(ValueError,'EXECUTION_INTENT_BINDING_CONFLICT'):f.host_call(request)
        f.s.db.execute("UPDATE events SET evidence_ref=? WHERE kind='DEVELOPMENT_EXECUTION_INTENT'",(prior,));f.s.db.commit()
        f.s.db.execute("UPDATE events SET evidence_ref=? WHERE kind='DEVELOPMENT_EXECUTION'",('0'*64,));f.s.db.commit()
        with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX_UNAVAILABLE'):f.host_call(request)

    def test_fixed_runner_unknown_stays_unknown_without_replay(self):
        from unittest.mock import patch
        f=self.f; request=f.proposal()
        with patch('producer_http_runner.run_producer_http',side_effect=TimeoutError('lost result')) as runner:
            with self.assertRaises(TimeoutError):f.host_call(request)
            result=f.host_call(request)
            self.assertEqual(runner.call_count,1)
        self.assertEqual(result['execution_state'],'UNKNOWN')
        self.assertEqual(result['reconciliation_state'],'ORIGINAL_PROVIDER_UNAVAILABLE_NO_REPLAY')
        self.assertFalse(result['execution_evidence_verified'])
        self.assertEqual(f.s.db.execute("SELECT count(*) FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone()[0],0)

    def test_wrong_http_semantics_do_not_admit(self):
        f=self.f;f.raw=f.raw.replace(b"'MAX_CANONICAL_TASK_LAST_EVENT_AT'",b"'NOT_THE_EXPECTED_SEMANTICS'")
        with self.assertRaisesRegex(ValueError,'PRODUCER_HTTP_TEST_NOT_PASSED'):f.host_call(f.proposal())
        self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())
        self.assertEqual(f.s._task('demo-b')['state'],'STARTED')
    def test_import_early_exit_does_not_admit(self):
        f=self.f;f.raw=b'import os\nprint("PASS",flush=True)\nos._exit(0)\n'
        with self.assertRaisesRegex(ValueError,'PRODUCER_HTTP_TEST_NOT_PASSED'):f.host_call(f.proposal())
        self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())
    def test_expired_lease_during_real_test_rejected(self):
        from unittest.mock import patch
        import producer_http_runner
        f=self.f;original=producer_http_runner.run_producer_http
        def expire_after_real_runtime(source):
            observation=original(source)
            f.s.db.execute('UPDATE tasks SET authority_valid_until=0 WHERE task_id=?',('demo-b',));f.s.db.commit()
            return observation
        with patch('producer_http_runner.run_producer_http',side_effect=expire_after_real_runtime):
            with self.assertRaisesRegex(ValueError,'STALE_WRITER_TICKET'):f.host_call(f.proposal())
        self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())
        self.assertEqual(f.s._task('demo-b')['state'],'STARTED')
