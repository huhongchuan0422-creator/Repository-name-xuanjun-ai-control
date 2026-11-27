"""ENTRY/native merge joins for this lineage only. No real authority, service or model call.

Reuses the reviewed resume-entry-merge-2355 design: the fixed BubblewrapNativeRunner
and NativeDevelopmentExecutor already exist unchanged here; only the protected-config
main wiring (load_host native_sandbox + db_path pass-through) is exercised below.
No bwrap execution is started by these tests (runner construction and guards only).
"""
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

    def test_protected_host_loader_builds_only_the_fixed_pinned_executor(self):
        f=sandbox.SandboxRunnerTests();f.setUp()
        try:
            config=Path(f.tmp.name)/'development.json'
            cfg={'schema_version':1,'enabled':True,'bindings':[],'review_keyring_file':None,'writer_context_file':None,
                'native_sandbox':{'repository_root':str(ROOT),'base_commit':f.commit,'test_plan_sha256':f.runner.plan}}
            config.write_text(json.dumps(cfg));config.chmod(0o600)
            host=development.load_host(str(config),db_path=f.db)
            self.assertEqual(host.native_executor.runner.plan,f.runner.plan)
            self.assertEqual(host.native_executor.runner.db_path,f.db)
            self.assertEqual(host.native_executor.plan,f.runner.plan)
        finally:f.doCleanups()

    def test_loader_rejects_arbitrary_fields_disabled_sandbox_and_second_executor(self):
        import test_native_sandbox_runner as fixture
        f=fixture.SandboxRunnerTests();f.setUp()
        try:
            config=Path(f.tmp.name)/'development.json'
            base={'schema_version':1,'enabled':True,'bindings':[],'review_keyring_file':None,'writer_context_file':None,
                'native_sandbox':{'repository_root':str(ROOT),'base_commit':f.commit,'test_plan_sha256':f.runner.plan}}
            cfg=dict(base);cfg['native_sandbox']=dict(base['native_sandbox'],command=['arbitrary'])
            config.write_text(json.dumps(cfg));config.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'FIXED_NATIVE_SANDBOX_REFERENCES_REQUIRED'):
                development.load_host(str(config),db_path=f.db)
            cfg=dict(base);cfg['enabled']=False
            config.write_text(json.dumps(cfg));config.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'DISABLED_DEVELOPMENT_CONFIG_MUST_BE_EMPTY'):
                development.load_host(str(config),db_path=f.db)
            config.write_text(json.dumps(dict(base)));config.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'ONE_TRUSTED_NATIVE_EXECUTOR_REQUIRED'):
                development.load_host(str(config),native_executor=f.executor,db_path=f.db)
        finally:f.doCleanups()

if __name__=='__main__':
    unittest.main()
