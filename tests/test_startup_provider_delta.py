import contextlib
import io
import json
import unittest
from unittest.mock import patch
import task_center_app
from test_execution_intent_delta import fixtures
from test_execution_recovery_delta import Provider
from task_center_mcp_development import DevelopmentHost

class Server:
    server_address=('127.0.0.1', 0)
    def serve_forever(self): pass
    def server_close(self): pass

class StartupDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ProducerExecutorTests(); self.f.producer_http_test=True; self.f.setUp()
        self.provider=Provider(); self.rid=self.f.proposal()
    def tearDown(self): self.f.tearDown()
    def call(self, provider):
        f=self.f
        def construct(bindings, **unused):
            def file(name, obj):
                p=f.root/name; p.write_text(json.dumps(obj)); p.chmod(0o600); return str(p)
            custody=file('startup-writer.json', {'demo-b':{'attempt_id':'attempt-b','ticket':f.ticket,'caller':f.caller,'lock_root':str(f.root/'locks')}})
            config=file('startup-host.json', {'schema_version':1,'enabled':True,'bindings':bindings,'review_keyring_file':None,'writer_context_file':custody})
            received=[]
            def server(*args,**kw): received.append(kw['mcp_development_host']); return Server()
            with patch('task_center_mcp_development.DevelopmentHost', DevelopmentHost), patch('task_center_app.make_server',side_effect=server), contextlib.redirect_stdout(io.StringIO()):
                task_center_app.main(['--db',str(f.root/'ledger.sqlite'),'--test-authority-key','fixture-key','--tenant','tenant-a','--enable-mcp','--mcp-development-config-file',config],execution_provider=provider)
            return received[0]
        with patch('task_center_mcp_development.DevelopmentHost', side_effect=construct):
            return f.host_call(self.rid)
    def count(self,kind): return self.f.s.db.execute('SELECT count(*) FROM events WHERE kind=?',(kind,)).fetchone()[0]
    def test_main_loader_dispatch_reconcile(self):
        with self.assertRaises(TimeoutError): self.call(self.provider)
        self.provider.response='unknown'; self.assertEqual(self.call(self.provider)['execution_state'],'UNKNOWN')
        self.provider.response='receipt'; r=self.call(self.provider)
        self.assertEqual(r['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        self.assertEqual(self.call(self.provider)['execution_event_id'],r['execution_event_id'])
        self.assertEqual((self.provider.execute_calls,self.provider.query_calls),(1,2))
        self.assertEqual((self.count('DEVELOPMENT_EXECUTION_INTENT'),self.count('DEVELOPMENT_EXECUTION')),(1,1))
    def test_cli_default_uses_installed_producer(self):
        self.assertEqual(self.call(None)['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        self.assertEqual(self.count('DEVELOPMENT_EXECUTION_INTENT'),1)
