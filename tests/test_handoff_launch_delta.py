"""Protected config -> real original app/HTTP; synthetic backend only."""
import contextlib,http.client,io,json,os,sqlite3,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import task_center_app as app
import task_center_handoff_launch as launch
import test_handoff_backup_script_main_delta as fixture
from test_handoff_runtime_bootstrap_delta import Authority

class LaunchConfig(unittest.TestCase):
    write_config=fixture.ScriptMainBackup.write_config
    def setUp(self):fixture.ScriptMainBackup.setUp(self)
    def make_config(self,enabled):
        path=self.root/'runtime.json';doc=dict(schema_version=1,enabled=enabled)
        if enabled:
            root=self.root/'lifecycle';(root/'artifacts').mkdir(parents=True,exist_ok=True)
            ledger=self.root/'runtime-ledger';ledger.mkdir(exist_ok=True)
            doc.update(tenant_id='tenant-1',issuer='formal-fixture',lifecycle_root=str(root),ledger_root=str(ledger),
                namespace='tenant-ledger',writer='writer',contracts=list(self.host.role_contract.contracts),intake_plans=[])
        path.write_text(json.dumps(doc));path.chmod(0o600);return path
    def invoke(self,path,backend=None,extra=()):
        original=app.make_server;captured=[];objects=[]
        def wrapping(*args,**kwargs):
            objects.append((args,kwargs));server=original(*args,**kwargs)
            def serve():
                t=threading.Thread(target=server.handle_request);t.start()
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    c.request('POST','/api/admin/handoff-reference',json.dumps(dict(task_id='demo-b',attempt_id='attempt-1',handoff_version=1)),
                        {'Host':'localhost:%d'%server.server_port,'Cookie':self.sessions.COOKIE+'='+self.token,
                         'X-CSRF-Token':self.csrf,'Content-Type':'application/json'})
                    r=c.getresponse();captured.append((r.status,json.loads(r.read())))
                finally:c.close();t.join(5)
            server.serve_forever=serve;return server
        with patch.object(app,'make_server',side_effect=wrapping),contextlib.redirect_stdout(io.StringIO()):
            launch.main(['--handoff-runtime-config-file',str(path)]+self.argv+list(extra),identity_backend=backend)
        return captured,objects
    def test_enabled_config_uses_canonical_session_and_host_without_plugin_loader(self):
        result,objects=self.invoke(self.make_config(True),Authority())
        self.assertEqual(result[0][0],200)
        host=objects[0][1]['handoff_host'];self.assertEqual(host.tenant_id,'tenant-1')
        self.assertEqual(host._lifecycle_candidate_readback.artifacts,str(self.root/'lifecycle'/'artifacts'))
        self.assertIs(objects[0][1]['ledger_bridge'].host,host)
        with self.assertRaises(sqlite3.ProgrammingError):host.db.execute('SELECT 1')
    def test_disabled_config_keeps_test_entry_and_handoff_unavailable(self):
        identities=self.root/'test-identity.json';identities.write_text('{"users":{}}');identities.chmod(0o600)
        result,objects=self.invoke(self.make_config(False),extra=['--test-identity-file',str(identities)])
        self.assertEqual(result[0][0],503);self.assertIsNone(objects[0][1]['handoff_host'])
    def test_enabled_missing_backend_cli_fails_before_db_or_listener(self):
        config=self.make_config(True);missing=self.root/'must-not-create.sqlite'
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('PYTHONPATH',None)
        result=subprocess.run([sys.executable,'scripts/task_center_handoff_launch.py','--handoff-runtime-config-file',str(config),
            '--db',str(missing),'--tenant','tenant-1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertEqual(result.returncode,69)
        self.assertEqual(result.stderr.decode().strip(),'FORMAL_IDENTITY_BACKEND_UNAVAILABLE')
        self.assertFalse(missing.exists())
    def test_protected_mode_duplicate_keys_and_wrong_tenant_rejected(self):
        path=self.make_config(False);path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'HANDOFF_RUNTIME_CONFIG_UNAVAILABLE_OR_INVALID'):launch.load_config(str(path))
        path.chmod(0o600);path.write_text('{"schema_version":1,"enabled":false,"enabled":true}')
        with self.assertRaisesRegex(ValueError,'HANDOFF_RUNTIME_CONFIG_UNAVAILABLE_OR_INVALID'):launch.load_config(str(path))
        path=self.make_config(True)
        with patch.object(launch.sqlite3,'connect',side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(ValueError,'HANDOFF_RUNTIME_TENANT_MISMATCH'):
                launch.main(['--handoff-runtime-config-file',str(path),'--db',self.path,'--tenant','other'],identity_backend=Authority())
    def test_packaged_dependency_closure_imports_without_external_pythonpath(self):
        names=['backup','handoff','source_adapter','backup_component_hostcycle','task_center_backup_bridge','task_center_backup_bridge_v2']
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('PYTHONPATH',None)
        code="import sys;sys.path.insert(0,'scripts');"+';'.join('import '+n for n in names)+";print('CLOSURE_OK')"
        result=subprocess.run([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertEqual(result.returncode,0,result.stderr.decode());self.assertEqual(result.stdout.decode().strip(),'CLOSURE_OK')
