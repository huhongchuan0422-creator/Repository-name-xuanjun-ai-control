import hashlib
import tempfile
import unittest
from unittest.mock import patch
from producer_http_contract import REFERENCE_SHA256
from producer_http_provider import ProducerHTTPProvider

class PersistentProviderTests(unittest.TestCase):
    def test_restart_query_bytes_and_no_replay(self):
        source=b'source'; artifact=b'actual bounded output'
        intent={'task_id':'new-isolated-intent', 'source_sha256':hashlib.sha256(source).hexdigest(), 'test_reference_sha256':REFERENCE_SHA256}
        result={'result':{'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'},'source_sha256':intent['source_sha256'], 'test_reference_sha256':REFERENCE_SHA256,'artifact_sha256':hashlib.sha256(artifact).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            with patch('producer_http_provider.run_producer_http_with_artifact',return_value=(result,artifact)) as runner:
                p=ProducerHTTPProvider(directory); first=p(intent,source)
                p=ProducerHTTPProvider(directory)
                self.assertEqual(first,p.query(intent)); self.assertEqual(artifact,p.artifact(intent))
                with self.assertRaisesRegex(ValueError,'ALREADY_RESERVED'): p(intent,source)
                self.assertEqual(runner.call_count,1)
                other=dict(intent,task_id='different'); self.assertIsNone(p.query(other))
    def test_failed_runner_stays_unknown(self):
        source=b'source'; intent={'source_sha256':hashlib.sha256(source).hexdigest(),'test_reference_sha256':REFERENCE_SHA256}
        with tempfile.TemporaryDirectory() as directory:
            with patch('producer_http_provider.run_producer_http_with_artifact',side_effect=TimeoutError) as runner:
                with self.assertRaises(TimeoutError): ProducerHTTPProvider(directory)(intent,source)
                p=ProducerHTTPProvider(directory); self.assertIsNone(p.query(intent))
                with self.assertRaisesRegex(ValueError,'ALREADY_RESERVED'): p(intent,source)
                self.assertEqual(runner.call_count,1)

class RealRunnerIntegration(unittest.TestCase):
    def test_fixed_runner_task_event_and_restart_query(self):
        import json
        from test_execution_intent_delta import fixtures
        from task_center_mcp_development import DevelopmentHost
        f=fixtures.ProducerExecutorTests(); f.producer_http_test=True; f.setUp()
        try:
            with tempfile.TemporaryDirectory() as directory:
                provider=ProducerHTTPProvider(directory)
                def host(*args,**kwargs):
                    return DevelopmentHost(*args,execution_provider=provider,**kwargs)
                with patch('task_center_mcp_development.DevelopmentHost',side_effect=host):
                    result=f.host_call(f.proposal())
                self.assertEqual(result['execution_state'],'ISOLATED_TEST_ELIGIBLE')
                row=f.s.db.execute("SELECT payload_json FROM events WHERE kind='DEVELOPMENT_EXECUTION_INTENT'").fetchone()
                intent=json.loads(row[0]); first=provider.query(intent); artifact=provider.artifact(intent)
                self.assertEqual(hashlib.sha256(artifact).hexdigest(),first['artifact_sha256'])
                provider=ProducerHTTPProvider(directory)
                with patch('producer_http_provider.run_producer_http_with_artifact',side_effect=AssertionError('replayed')):
                    f.adapter.execution_provider=provider
                    again=f.adapter._run_producer_http_acceptance('demo-b','attempt-b',result['candidate_event_id'],f.ticket,f.caller)
                self.assertEqual(again['execution_event_id'],result['execution_event_id'])
                self.assertEqual(provider.query(intent),first); self.assertEqual(provider.artifact(intent),artifact)
                self.assertEqual(f.s.db.execute("SELECT count(*) FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone()[0],1)
                print('REAL_RUNNER_ARTIFACT_BYTES=%d SHA256=%s' % (len(artifact),first['artifact_sha256']))
        finally:
            f.tearDown()

class MainWiringTests(unittest.TestCase):
    def test_main_constructs_and_passes_provider(self):
        import task_center_app
        class Server:
            server_address=('127.0.0.1',0)
            def serve_forever(self): raise KeyboardInterrupt()
            def server_close(self): pass
        with tempfile.TemporaryDirectory() as directory:
            with patch('task_center_mcp_development.load_host',return_value='host') as load, \
                 patch('task_center_app.make_server',return_value=Server()) as make:
                result=task_center_app.main(['--db',directory+'/tc.sqlite','--test-authority-key','test-only',
                    '--tenant','isolated-test','--mcp-development-config-file',directory+'/host.json',
                    '--mcp-producer-provider-directory',directory])
            self.assertEqual(result,0)
            self.assertIsInstance(load.call_args[1]['execution_provider'],ProducerHTTPProvider)
            self.assertEqual(make.call_args[1]['mcp_development_host'],'host')
