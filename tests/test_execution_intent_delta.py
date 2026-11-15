import hashlib
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import local_development_executor
import task_center_mcp_development
sys.path.insert(0,str(ROOT/'tc-canonical-producer-scoped-20261114'/'candidate'/'tests'))
import test_producer_executor_delta as fixtures
from task_supervisor import canonical
import producer_http_runner
producer_http_runner.__file__=str(ROOT/'tc-canonical-producer-scoped-20261114'/'candidate'/'scripts'/'producer_http_runner.py')

class IntentDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ProducerExecutorTests();self.f.producer_http_test=True;self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def provider(self,intent,source):
        observation=producer_http_runner.run_producer_http(source)
        return dict(observation,intent_sha256=hashlib.sha256(canonical(intent).encode()).hexdigest())
    def test_real_fixed_runner_and_review_guard(self):
        f=self.f
        from unittest.mock import patch
        from task_center_mcp_development import DevelopmentHost
        def host(*args,**kwargs):
            return DevelopmentHost(*args,execution_provider=self.provider,**kwargs)
        with patch('task_center_mcp_development.DevelopmentHost',side_effect=host):
            result=f.host_call(f.proposal())
        f.adapter.execution_provider=self.provider
        self.assertEqual(result['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        candidate=f.s.development_candidate('demo-b',result['candidate_event_id'])
        f.s._require_development_execution_ready(candidate)
        with self.assertRaisesRegex(ValueError,'EXECUTION_INTENT_ALREADY_EXISTS_RECONCILE'):
            f.adapter._run_producer_http_acceptance('demo-b','attempt-b',result['candidate_event_id'],f.ticket,f.caller)
    def test_wrong_receipt_binding(self):
        f=self.f
        def wrong(intent,source):
            wrong_intent=dict(intent,task_id='wrong-task')
            return {'intent_sha256':hashlib.sha256(canonical(wrong_intent).encode()).hexdigest(),'result':{'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'},'test_reference_sha256':intent['test_reference_sha256'],'source_sha256':intent['source_sha256'],'artifact_sha256':'a'*64}
        f.adapter.execution_provider=wrong
        with self.assertRaisesRegex(ValueError,'PRODUCER_HTTP_TEST_BINDING_MISMATCH'):f.apply(f.proposal())
        self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())
    def test_expired_lease_after_observation(self):
        f=self.f
        def expire(intent,source):
            f.s.db.execute('UPDATE tasks SET authority_valid_until=0 WHERE task_id=?',('demo-b',));f.s.db.commit()
            return {'intent_sha256':hashlib.sha256(canonical(intent).encode()).hexdigest(),'result':{'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'},'test_reference_sha256':intent['test_reference_sha256'],'source_sha256':intent['source_sha256'],'artifact_sha256':'a'*64}
        f.adapter.execution_provider=expire
        with self.assertRaisesRegex(ValueError,'STALE_WRITER_TICKET'):f.apply(f.proposal())
        self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())

    def test_replay_actual_receipt_on_another_candidate(self):
        # Two independent test ledgers represent two invocations, not a live issuer.
        first=self.f; captured=[]
        def capture(intent,source):
            receipt=self.provider(intent,source);captured.append(receipt);return receipt
        first.adapter.execution_provider=capture
        result=first.apply(first.proposal())
        self.assertEqual(result['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        second=fixtures.ProducerExecutorTests();second.producer_http_test=True;second.setUp()
        try:
            second.raw+=b'\n# distinct candidate for receipt replay test\n'
            second.adapter.execution_provider=lambda intent,source: captured[0]
            with self.assertRaisesRegex(ValueError,'PRODUCER_HTTP_TEST_BINDING_MISMATCH'):
                second.apply(second.proposal())
            self.assertIsNone(second.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())
        finally:second.tearDown()

    def test_receipt_source_and_test_mismatch(self):
        for field in ('source_sha256','test_reference_sha256'):
            f=fixtures.ProducerExecutorTests();f.producer_http_test=True;f.setUp()
            try:
                def wrong(intent,source):
                    receipt={'intent_sha256':hashlib.sha256(canonical(intent).encode()).hexdigest(),
                        'result':{'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'},
                        'test_reference_sha256':intent['test_reference_sha256'],
                        'source_sha256':intent['source_sha256'],'artifact_sha256':'a'*64}
                    receipt[field]='0'*64
                    return receipt
                f.adapter.execution_provider=wrong
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError,'PRODUCER_HTTP_TEST_BINDING_MISMATCH'):f.apply(f.proposal())
                    self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())
            finally:f.tearDown()

    def test_receipt_candidate_and_attempt_mismatch(self):
        for field in ('candidate_sha256','attempt_id'):
            f=fixtures.ProducerExecutorTests();f.producer_http_test=True;f.setUp()
            try:
                def wrong(intent,source):
                    other=dict(intent);other[field]='different'
                    return {'intent_sha256':hashlib.sha256(canonical(other).encode()).hexdigest(),
                        'result':{'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'},
                        'test_reference_sha256':intent['test_reference_sha256'],
                        'source_sha256':intent['source_sha256'],'artifact_sha256':'a'*64}
                f.adapter.execution_provider=wrong
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError,'PRODUCER_HTTP_TEST_BINDING_MISMATCH'):f.apply(f.proposal())
                    self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone())
            finally:f.tearDown()

    def test_expired_lease_before_invocation(self):
        f=self.f;calls=[]
        # Establish candidate while no provider is connected, then expire its lease.
        result=f.apply(f.proposal())
        self.assertEqual(result['execution_state'],'NOT_CONNECTED')
        f.s.db.execute('UPDATE tasks SET authority_valid_until=0 WHERE task_id=?',('demo-b',));f.s.db.commit()
        f.adapter.execution_provider=lambda intent,source:calls.append(intent)
        with self.assertRaisesRegex(ValueError,'STALE_WRITER_TICKET'):
            f.adapter._run_producer_http_acceptance('demo-b','attempt-b',result['candidate_event_id'],f.ticket,f.caller)
        self.assertEqual(calls,[])
        self.assertIsNone(f.s.db.execute("SELECT 1 FROM events WHERE kind='DEVELOPMENT_EXECUTION_INTENT'").fetchone())
