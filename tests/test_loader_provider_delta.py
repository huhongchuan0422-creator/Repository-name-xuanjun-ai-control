import json
import unittest
from unittest.mock import patch
from test_execution_intent_delta import fixtures
from test_execution_recovery_delta import Provider
from task_center_mcp_development import load_host

class LoaderDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ProducerExecutorTests(); self.f.producer_http_test=True; self.f.setUp()
        self.provider=Provider(); self.rid=self.f.proposal()
    def tearDown(self): self.f.tearDown()
    def call(self, provider, wrong=False):
        f=self.f
        def construct(bindings, **unused):
            if wrong: bindings[0]['principal_id']='other-principal'
            def file(name, obj):
                p=f.root/name; p.write_text(json.dumps(obj)); p.chmod(0o600); return str(p)
            custody=file('writer.json', {'demo-b':{'attempt_id':'attempt-b','ticket':f.ticket,'caller':f.caller,'lock_root':str(f.root/'locks')}})
            config=file('host.json', {'schema_version':1,'enabled':True,'bindings':bindings,'review_keyring_file':None,'writer_context_file':custody})
            return load_host(config, execution_provider=provider)
        with patch('task_center_mcp_development.DevelopmentHost', side_effect=construct) as mock:
            # load_host must instantiate the actual host, not the fixture constructor.
            from test_loader_provider_delta import REAL_HOST
            def construct_once(*a,**kw):
                mock.side_effect=None; mock.side_effect=REAL_HOST
                return construct(*a,**kw)
            mock.side_effect=construct_once
            return f.host_call(self.rid)
    def count(self,kind): return self.f.s.db.execute('SELECT count(*) FROM events WHERE kind=?',(kind,)).fetchone()[0]
    def test_loader_unknown_query_recovery_and_idempotence(self):
        with self.assertRaises(TimeoutError): self.call(self.provider)
        self.provider.response='unknown'; self.assertEqual(self.call(self.provider)['execution_state'],'UNKNOWN')
        self.assertEqual((self.provider.execute_calls,self.provider.query_calls),(1,1))
        self.provider.response='receipt'; result=self.call(self.provider)
        self.assertEqual(result['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        candidate=self.f.s.development_candidate('demo-b',result['candidate_event_id']); self.f.s._require_development_execution_ready(candidate)
        self.assertEqual(self.call(self.provider)['execution_event_id'],result['execution_event_id'])
        self.assertEqual((self.provider.execute_calls,self.provider.query_calls),(1,3))
        self.assertEqual((self.count('DEVELOPMENT_EXECUTION_INTENT'),self.count('DEVELOPMENT_EXECUTION')),(1,1))
    def test_fixed_http_oracle_via_loader(self):
        import hashlib
        import producer_http_runner
        from task_supervisor import canonical
        calls=[]
        def synthetic_provider(intent, source):
            calls.append(intent)
            observation=producer_http_runner.run_producer_http(source)
            return dict(observation,intent_sha256=hashlib.sha256(canonical(intent).encode()).hexdigest())
        result=self.call(synthetic_provider)
        self.assertEqual(result['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        self.assertEqual(len(calls),1)
        self.assertEqual((self.count('DEVELOPMENT_EXECUTION_INTENT'),self.count('DEVELOPMENT_EXECUTION')),(1,1))
    def test_none_not_connected(self):
        self.assertEqual(self.call(None)['execution_state'],'NOT_CONNECTED')
        self.assertEqual(self.count('DEVELOPMENT_EXECUTION_INTENT'),0)
    def test_wrong_binding_rejected_before_execution(self):
        with self.assertRaises(ValueError): self.call(self.provider,True)
        self.assertEqual(self.provider.execute_calls,0)
        self.assertEqual(self.count('DEVELOPMENT_EXECUTION_INTENT'),0)

from task_center_mcp_development import DevelopmentHost as REAL_HOST
