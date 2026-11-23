"""Real main -> make_server -> OAuth HTTP. Synthetic custody; no live service."""
import contextlib
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import task_center_app as app
import test_mcp_canonical_claim_http as fixture

class MainBootstrapTests(unittest.TestCase):
    def run_main_http(self, inject):
        f=fixture.ClaimHTTPTests();f.setUp();self.addCleanup(f.tearDown)
        f.server.shutdown();f.server.server_close();f.thread.join(2)
        key=f.root/'authority';key.write_bytes(fixture.KEY);key.chmod(0o600)
        master=f.root/'master';master.write_bytes(f.master);master.chmod(0o600)
        args=['--db',f.path,'--test-authority-key-file',str(key),'--tenant','tenant-a',
              '--principal','fixture','--port','0','--model-master-key-file',str(master),
              '--test-identity-file',str(f.root/'users.json'),'--external-origin',f.origin,'--enable-mcp']
        if inject == 'config':
            from cryptography.hazmat.primitives import serialization
            public=f.root/'owner.pem';public.write_bytes(f.private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo));public.chmod(0o600)
            custody=f.root/'custody.json';custody.write_text(json.dumps({'demo-b':{'tenant_id':'tenant-a','principal_id':'developer','project_id':'project-mcp','custody':f.custody}}));custody.chmod(0o600)
            config=f.root/'development.json';config.write_text(json.dumps({'schema_version':1,'enabled':True,'bindings':f.host.bindings,'review_keyring_file':None,'writer_context_file':None,'claim_registration':{'owner_public_key_file':str(public),'custody_file':str(custody)}}));config.chmod(0o600)
            args += ['--mcp-development-config-file',str(config)]
        original=app.TaskCenterHTTPServer.serve_forever
        observed={}
        def bounded(server):
            f.server=server
            f.thread=threading.Thread(target=lambda:original(server),daemon=True);f.thread.start()
            try:
                status,value=f.rpc();self.assertEqual(status,200)
                observed['names']=[t['name'] for t in value['result']['tools']]
                if inject:
                    self.assertIn('task_claim',observed['names'])
                    result=f.payload('task_claim');self.assertEqual(result['state'],'RECEIVED')
                    self.assertFalse(result['execution_started'])
                    self.assertEqual(result,f.payload('task_claim_status'))
                    observed['claim']=result
                else:self.assertNotIn('task_claim',observed['names'])
            finally:server.shutdown();f.thread.join(2)
        with patch.object(app.TaskCenterHTTPServer,'serve_forever',bounded),contextlib.redirect_stdout(io.StringIO()):
            result=app.main(args,mcp_claim_host=f.host if inject is True else None)
        self.assertEqual(result,0)
        return observed
    def test_trusted_main_injection_reaches_real_oauth_claim_and_readback(self):
        self.run_main_http(True)
    def test_original_main_loads_protected_config_and_claims_over_http(self):
        self.run_main_http('config')
    def test_plain_main_remains_default_off_without_injection(self):
        self.run_main_http(False)

class ProtectedRegistrationConfigTests(unittest.TestCase):
    def test_unknown_executable_registration_key_and_relative_paths_rejected(self):
        import tempfile
        from task_center_mcp_development import load_host
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'host.json'
            base={'schema_version':1,'enabled':True,'bindings':[],'review_keyring_file':None,'writer_context_file':None}
            for refs in ({'module':'untrusted.py'}, {'owner_public_key_file':'relative','custody_file':'/custody'}):
                config.write_text(json.dumps(dict(base,claim_registration=refs)));config.chmod(0o600)
                with self.assertRaisesRegex(ValueError,'EXISTING_CLAIM_REGISTRATION_REFERENCES_REQUIRED'):load_host(str(config))
    def test_disabled_config_cannot_load_registration_custody(self):
        import tempfile
        from task_center_mcp_development import load_host
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'host.json'
            config.write_text(json.dumps({'schema_version':1,'enabled':False,'bindings':[],'review_keyring_file':None,'writer_context_file':None,'claim_registration':{'owner_public_key_file':'/owner','custody_file':'/custody'}}));config.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'DISABLED_DEVELOPMENT_CONFIG_MUST_BE_EMPTY'):load_host(str(config))

if __name__=='__main__':unittest.main()
