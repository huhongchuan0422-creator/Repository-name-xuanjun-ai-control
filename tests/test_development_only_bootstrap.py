"""Bootstrap/HTTP fixtures only, never evidence of a production source."""
import contextlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import task_center_app as app
import task_center_handoff_launch as launch
from task_supervisor import Supervisor
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from reusable_scheduler_cli import demo_graph
from test_guarded_provenance_consumer_delta import Source

class DevelopmentOnlyBootstrap(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=str(self.root/'canonical.sqlite')
        self.key=b'0123456789abcdef0123456789abcdef'
        s=Supervisor(self.db);authority=TestTenantAuthority(self.key)
        GatewayKernel(s,authority).register_graph(authority.issue('tenant','seed'),demo_graph('tenant'))
        s.close()
        def protected(name,raw):
            p=self.root/name;p.write_bytes(raw);p.chmod(0o600);return str(p)
        cfg=protected('development.json',json.dumps(dict(schema_version=1,enabled=True,
            bindings=[],review_keyring_file=None,writer_context_file=None)).encode())
        self.args=['--db',self.db,'--tenant','tenant','--enable-mcp',
            '--mcp-development-config-file',cfg,'--port','0','--external-origin','https://fixture.example',
            '--test-authority-key-file',protected('authority',self.key),
            '--model-master-key-file',protected('model',Fernet.generate_key())]
        self.source=Source();self.source.binding['expires_at']=time.time()+300
        self.mapper=lambda b:dict(tenant_id=b['tenant_id'],principal_id=b['principal_id'],roles=['TASK_EXECUTOR'])
    def test_missing_source_stops_before_database_or_listener(self):
        with patch.object(launch.sqlite3,'connect',side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(ValueError,'FORMAL_PROVENANCE_UNAVAILABLE'):
                launch.development_main(self.args,issuer='fixture-source',provenance_source=None,principal_mapper=self.mapper)
    def test_original_test_identity_mode_cannot_mix(self):
        with patch.object(launch.sqlite3,'connect',side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(ValueError,'SINGLE_AUTH_MODE_REQUIRED'):
                launch.development_main(self.args+['--test-identity-file','/unused'],
                    issuer='fixture-source',provenance_source=self.source,principal_mapper=self.mapper)
    def run_http(self,formal):
        if formal:
            # Isolated schema fixture, not a live profile change or migration.
            import sqlite3
            with sqlite3.connect(self.db) as db:
                db.execute("UPDATE authority_runtime_profile SET profile='FORMAL'")
        observed=[]
        def serve(server):
            def post():
                thread=threading.Thread(target=server.handle_request);thread.start()
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    c.request('POST','/api/session/login',json.dumps({'username':'fixture','password':'fixture'}),
                        {'Host':'fixture.example','Origin':'https://fixture.example','Content-Type':'application/json'})
                    r=c.getresponse();observed.append((r.status,json.loads(r.read())))
                finally:c.close();thread.join(5)
            post()
            if formal:
                self.source.live=False;post()
        with patch.object(app.TaskCenterHTTPServer,'serve_forever',serve),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launch.development_main(self.args,issuer='fixture-source',
                provenance_source=self.source,principal_mapper=self.mapper),0)
        self.assertEqual([x[0] for x in observed],[200,401] if formal else [401])
        self.assertEqual(observed[-1][1]['detail'],'FORMAL_PROVENANCE_UNAVAILABLE')
        if formal:self.assertEqual(observed[0][1]['principal_id'],'writer')
    def test_login_http_without_handoff_roots_and_source_revocation(self):self.run_http(True)
    def test_test_only_canonical_profile_is_not_promoted(self):self.run_http(False)
    def test_native_runner_reaches_existing_host_without_handoff(self):
        class Runner:
            def execute(self,*args):raise AssertionError('not running tests in bootstrap')
            def lookup(self,*args):raise AssertionError('not looking up in bootstrap')
        runner=Runner()
        def original_app(argv,gateway_runtime,**kw):
            self.assertNotIn('handoff_host',kw)
            executor=kw['mcp_development_host'].native_executor
            self.assertIs(executor.runner,runner);self.assertEqual(executor.plan,'a'*64)
            self.assertIsNone(kw['mcp_claim_host'])
            return 0
        with patch.object(app,'main',side_effect=original_app):
            self.assertEqual(launch.development_main(self.args,issuer='fixture-source',
                provenance_source=self.source,principal_mapper=self.mapper,
                native_runner=runner,native_test_plan_sha256='a'*64),0)

if __name__=='__main__':unittest.main()
