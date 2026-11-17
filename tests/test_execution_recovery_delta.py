import hashlib
import unittest
from unittest.mock import patch
from test_execution_intent_delta import fixtures
from task_supervisor import canonical
from task_center_mcp_development import DevelopmentHost

class Provider:
    def __init__(self):self.execute_calls=0;self.query_calls=0;self.receipt=None;self.response='receipt'
    def __call__(self,intent,source):
        self.execute_calls+=1
        self.receipt={'intent_sha256':hashlib.sha256(canonical(intent).encode()).hexdigest(),
            'result':{'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'},
            'test_reference_sha256':intent['test_reference_sha256'],
            'source_sha256':intent['source_sha256'],'artifact_sha256':'a'*64}
        raise TimeoutError('unknown result')
    def query(self,intent):
        self.query_calls+=1
        if self.response=='unknown':return None
        result=dict(self.receipt)
        if self.response=='wrong_intent':result['intent_sha256']='0'*64
        if self.response=='wrong_source':result['source_sha256']='0'*64
        if self.response=='wrong_test':result['test_reference_sha256']='0'*64
        return result

class RecoveryDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ProducerExecutorTests();self.f.producer_http_test=True;self.f.setUp()
        self.provider=Provider();self.rid=self.f.proposal()
    def tearDown(self):self.f.tearDown()
    def host(self):
        def create(*a,**kw):return DevelopmentHost(*a,execution_provider=self.provider,**kw)
        with patch('task_center_mcp_development.DevelopmentHost',side_effect=create):
            return self.f.host_call(self.rid)
    def timeout(self):
        with self.assertRaisesRegex(TimeoutError,'unknown result'):self.host()
        self.assertEqual(self.provider.execute_calls,1)
    def count(self,kind):
        return self.f.s.db.execute('SELECT count(*) FROM events WHERE kind=?',(kind,)).fetchone()[0]
    def test_timeout_then_mcp_recovers_same_receipt_idempotently(self):
        self.timeout()
        recovered=self.host();self.assertEqual(recovered['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        candidate=self.f.s.development_candidate('demo-b',recovered['candidate_event_id'])
        self.f.s._require_development_execution_ready(candidate)
        duplicate=self.host();self.assertEqual(duplicate['execution_event_id'],recovered['execution_event_id'])
        self.assertEqual((self.provider.execute_calls,self.provider.query_calls),(1,2))
        self.assertEqual((self.count('DEVELOPMENT_EXECUTION_INTENT'),self.count('DEVELOPMENT_EXECUTION')),(1,1))
    def test_unknown_query_never_reexecutes(self):
        self.timeout();self.provider.response='unknown'
        result=self.host();self.assertEqual(result['execution_state'],'UNKNOWN')
        self.assertFalse(result['execution_evidence_verified'])
        self.assertEqual((self.provider.execute_calls,self.provider.query_calls),(1,1))
        self.assertEqual((self.count('DEVELOPMENT_EXECUTION_INTENT'),self.count('DEVELOPMENT_EXECUTION')),(1,0))
    def test_missing_provider_never_replays_existing_intent(self):
        self.timeout()
        candidate=self.f.s.db.execute("SELECT event_id FROM events WHERE kind='DEVELOPMENT_CANDIDATE'").fetchone()[0]
        self.f.adapter.execution_provider=None
        with patch('producer_http_runner.run_producer_http') as old_runner:
            with self.assertRaisesRegex(ValueError,'EXECUTION_INTENT_ALREADY_EXISTS_RECONCILE'):
                self.f.adapter._run_producer_http_acceptance('demo-b','attempt-b',candidate,self.f.ticket,self.f.caller)
            old_runner.assert_not_called()
        self.assertEqual((self.provider.execute_calls,self.count('DEVELOPMENT_EXECUTION')),(1,0))
    def test_bad_query_receipt_rejected(self):
        self.timeout()
        for field in ('wrong_intent','wrong_source','wrong_test'):
            self.provider.response=field
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError,'PRODUCER_HTTP_TEST_BINDING_MISMATCH'):self.host()
                self.assertEqual(self.count('DEVELOPMENT_EXECUTION'),0)
        self.assertEqual(self.provider.execute_calls,1)
    def test_expired_lease_stops_query(self):
        self.timeout();self.f.s.db.execute('UPDATE tasks SET authority_valid_until=0 WHERE task_id=?',('demo-b',));self.f.s.db.commit()
        with self.assertRaisesRegex(ValueError,'STALE_WRITER_TICKET'):self.host()
        self.assertEqual((self.provider.execute_calls,self.provider.query_calls),(1,0))
        self.assertEqual(self.count('DEVELOPMENT_EXECUTION'),0)
    def test_expired_lease_after_query_stops_event(self):
        self.timeout();original=self.provider.query
        def expire(intent):
            receipt=original(intent)
            self.f.s.db.execute('UPDATE tasks SET authority_valid_until=0 WHERE task_id=?',('demo-b',));self.f.s.db.commit()
            return receipt
        self.provider.query=expire
        with self.assertRaisesRegex(ValueError,'STALE_WRITER_TICKET'):self.host()
        self.assertEqual((self.provider.execute_calls,self.provider.query_calls),(1,1))
        self.assertEqual(self.count('DEVELOPMENT_EXECUTION'),0)
