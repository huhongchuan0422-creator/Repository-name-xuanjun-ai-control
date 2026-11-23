"""Only ENTRY/native merge joins. No real authority, service or model call."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import task_center_app as app
import task_center_mcp_development as development
import test_mcp_claim_main_bootstrap as bootstrap
import test_native_sandbox_runner as sandbox
from native_sandbox_runner import plan_manifest,digest

class EntryNativeMergeTests(unittest.TestCase):
    def test_actual_main_preserves_runtime_and_loads_sandbox_from_protected_config(self):
        runtime=object()  # Injection identity only; no inference/SDK execution.
        original_main=app.main;original_load=development.load_host
        commit=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()
        loaded=[]
        def load(path,*args,**kwargs):
            cfg=json.loads(Path(path).read_text())
            cfg['native_sandbox']={'repository_root':str(ROOT),'base_commit':commit,'test_plan_sha256':digest(plan_manifest(str(ROOT),commit))}
            Path(path).write_text(json.dumps(cfg))
            host=original_load(path,*args,**kwargs);loaded.append(host)
            self.assertEqual(host.native_executor.runner.db_path,kwargs['db_path'])
            return host
        def main(args,**kwargs):return original_main(args,gateway_runtime=runtime,**kwargs)
        case=bootstrap.MainBootstrapTests()
        try:
            with patch.object(app,'main',side_effect=main),patch.object(development,'load_host',side_effect=load),patch.object(app,'make_server',wraps=app.make_server) as server,patch.object(app,'MCPTaskService',wraps=app.MCPTaskService) as service:
                case.run_main_http('config')
                self.assertIs(server.call_args[1]['gateway_runtime'],runtime)
                self.assertIs(service.call_args[1]['gateway_runtime'],runtime)
                self.assertIsNotNone(loaded[-1].native_executor)
        finally:case.doCleanups()
    def test_unbound_identity_contract_does_not_claim_binding_or_drop_schema(self):
        import test_mcp_canonical_claim_http as claim_fixture
        f=claim_fixture.ClaimHTTPTests();f.setUp()
        try:
            status,value=f.rpc('task_dispatch_contract',{})
            self.assertEqual(status,200)
            contract=json.loads(value['result']['content'][0]['text'])
            self.assertTrue(contract['canonical_claim']['host_bound'])
            self.assertTrue(all(isinstance(t,dict) and 'inputSchema' in t for t in contract['canonical_claim']['tools']))
            status,value=f.rpc('task_dispatch_contract',{},token=f.token_for('qa'))
            self.assertEqual(status,200)
            contract=json.loads(value['result']['content'][0]['text'])
            self.assertFalse(contract['canonical_claim']['host_bound']);self.assertEqual(contract['canonical_claim']['tools'],[])
        finally:f.tearDown()
    def test_source_native_gate_and_existing_producer_gate_remain_separate(self):
        import hashlib,inspect
        from task_supervisor import Supervisor
        # Pinned body digest from actual installed app71cefb dependency snapshot;
        # no installed /opt path needed when running tests in CI.
        body=inspect.getsource(Supervisor._require_existing_producer_execution_ready).split('\n',1)[1].rstrip()
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),'52ee54778c0aa42daf92e4569fe4aff9a9aebc26143bba09eac576f1a66781d0')
        f=sandbox.SandboxRunnerTests();f.setUp()
        try:
            with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX_UNAVAILABLE'):
                f.s._require_development_execution_ready({'source_kind':'LOCAL_ONLY_CONFIRMED_OPERATION','source_operation_id':'not-producer','task_id':'demo-b','attempt_id':f.candidate['attempt_id']})
            with self.assertRaisesRegex(ValueError,'HOLD_TRUSTED_NATIVE_EXECUTION_REQUIRED'):
                f.s._require_development_execution_ready(f.candidate)
        finally:f.doCleanups()
    def test_entry_readonly_projections_assets_and_source_acceptance_gate_coexist(self):
        import test_task_center_app as fixture
        from urllib.request import Request,build_opener,ProxyHandler
        f=fixture.TaskCenterAppTests();f.setUp()
        try:
            opener=build_opener(ProxyHandler({}))
            def get(path,admin=False):
                headers={'X-Test-Admin-Token':'test-admin-token-123456'} if admin else {}
                with opener.open(Request(f.base+path,headers=headers),timeout=3) as response:return response.status,response.read()
            self.assertEqual(get('/readyz')[0],200)
            self.assertEqual(get('/api/projection')[0],200)
            status,raw=get('/api/admin/model-control',True);self.assertEqual(status,200)
            self.assertIn('real_acceptance',json.loads(raw))
            status,raw=get('/api/public-projection');self.assertEqual(status,200)
            public=json.loads(raw);self.assertIn('boards',public);self.assertNotIn('tasks',public)
            self.assertEqual(get('/task-center.html')[0],200);self.assertEqual(get('/task-center.js')[0],200)
        finally:f.tearDown()
    def test_protected_host_loader_executes_real_fixed_plan_then_lookup(self):
        f=sandbox.SandboxRunnerTests();f.setUp()
        try:
            config=Path(f.tmp.name)/'development.json'
            cfg={'schema_version':1,'enabled':True,'bindings':[],'review_keyring_file':None,'writer_context_file':None,
                'native_sandbox':{'repository_root':str(ROOT),'base_commit':f.commit,'test_plan_sha256':f.runner.plan}}
            config.write_text(json.dumps(cfg));config.chmod(0o600)
            host=development.load_host(str(config),db_path=f.db)
            result=host.native_executor.run(f.s,f.candidate,f.files,lambda:None)
            self.assertEqual(result['receipt']['state'],'PASSED')
            self.assertEqual(result['receipt'],host.native_executor.runner.lookup(digest(f.candidate)))
            cfg['native_sandbox']['command']=['arbitrary'];config.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'FIXED_NATIVE_SANDBOX_REFERENCES_REQUIRED'):development.load_host(str(config),db_path=f.db)
        finally:f.doCleanups()

if __name__=='__main__':unittest.main()
