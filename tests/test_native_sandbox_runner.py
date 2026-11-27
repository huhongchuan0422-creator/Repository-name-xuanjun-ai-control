"""Real bubblewrap execution; synthetic isolated task authority, never live TC."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from native_sandbox_runner import BubblewrapNativeRunner,plan_manifest,digest,CANDIDATE_FILES,REPOSITORY,process_identity,challenges
from native_development_executor import NativeDevelopmentExecutor
from reusable_task_gateway import GatewayKernel,TestTenantAuthority,TestOnlyExecutor
from reusable_scheduler_cli import demo_graph
from task_supervisor import Supervisor
from task_writer_fence import Fence
KEY=b'0123456789abcdef0123456789abcdef'

class SandboxRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'canonical.sqlite')
        self.s=Supervisor(self.db);self.addCleanup(self.s.close)
        g=GatewayKernel(self.s,TestTenantAuthority(KEY));context=g.tenants.issue('sandbox-test-only','admin:fixture')
        graph=demo_graph('sandbox-test-only');graph['tasks'][0]['entry']='WORK';g.register_graph(context,graph)
        self.commit=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()
        self.contract=dict(task_id='demo-b',spec_sha256='b'*64,checkpoint_sha256='a'*64,target_repository=REPOSITORY,
            target_base_sha=self.commit,entry='WORK',developer={'issuer':'fixture','subject':'developer'},allowed_files=list(CANDIDATE_FILES),
            trusted_reviewers=[{'issuer':'fixture','subject':'qa','key_id':'qa','role':'QA'},{'issuer':'fixture','subject':'sec','key_id':'sec','role':'SECURITY'}])
        self.s.register_development_contract('demo-b',self.contract)
        self.fence=Fence(self.s,str(Path(self.tmp.name)/'locks'));self.addCleanup(self.fence.close)
        started=TestOnlyExecutor(g,self.fence,context).start('demo-b','sandbox-fixture-attempt',['fake:demo-b'],time.time()+600)
        ticket=started['ticket'];caller=started['caller']
        self.files={p:subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'show',self.commit+':'+p]) for p in CANDIDATE_FILES}
        receipt=dict(schema=1,entry='WORK',execution_path='WORK_NATIVE',task_id='demo-b',spec_sha256='b'*64,checkpoint_sha256='a'*64,
            target_repository=REPOSITORY,target_base_sha=self.commit,code_commit=self.commit,event='CODE_READY',attempt_id=ticket['attempt_id'],lease_id=ticket['lease_id'],fence=ticket['fence'],epoch=ticket['epoch'],
            lock_provider_id=self.fence.locks.provider_id,source_comment_id=1,status='RECEIPT_VALIDATED_NOT_ADMITTED',native_identity='TEST_FIXTURE_NOT_EXTERNAL_IDENTITY',quota_attribution='TEST_ONLY',authority_effect='NONE',required_gate='CANONICAL_TASK_SPEC_CHECKPOINT_TARGET_LEASE_FENCE',**caller)
        self.source_receipt=receipt
        self.candidate=self.s.bind_development_candidate(receipt,{p:hashlib.sha256(raw).hexdigest() for p,raw in self.files.items()})['candidate']
        self.runner=BubblewrapNativeRunner(self.db,str(ROOT),self.commit,digest(plan_manifest(str(ROOT),self.commit)))
        self.executor=NativeDevelopmentExecutor(self.runner,self.runner.plan)
    def run_plan(self):return self.executor.run(self.s,self.candidate,self.files,lambda:None)
    def test_actual_same_commit_fixed_plan_and_canonical_lookup_without_reexecution(self):
        try:result=self.run_plan()
        except Exception:
            print('SANDBOX_DIAGNOSTIC '+json.dumps(self.runner.status(digest(self.candidate)),sort_keys=True));raise
        receipt=result['receipt'];self.assertEqual(receipt['state'],'PASSED');self.assertEqual(receipt['tests_executed'],10)
        self.assertEqual(receipt['code_commit'],self.commit);self.assertEqual(receipt,self.runner.lookup(digest(self.candidate)))
        status=self.runner.status(digest(self.candidate));self.assertEqual(status['state'],'PASSED');self.assertIsNotNone(status['process']);self.assertFalse(status['wake_supported'])
        with patch('native_sandbox_runner.subprocess.Popen',side_effect=AssertionError('MUST_NOT_REEXECUTE')):
            self.assertEqual(result,self.run_plan())
        print('REAL_BWRAP_CANONICAL_FIXTURE '+json.dumps({'task_id':'demo-b','authority':'TEST_ONLY_FIXTURE_NOT_LIVE','receipt':receipt,'process':status['process'],'result':status['result']},sort_keys=True))
    def candidate_source(self,raw,extra_path=None):
        # A small shared local Git fixture, no clone of production data/objects.
        repo=Path(self.tmp.name)/'candidate.git'
        subprocess.check_call(['/usr/bin/git','clone','--shared','--bare','-q',str(ROOT),str(repo)])
        subprocess.check_call(['/usr/bin/git','--git-dir='+str(repo),'remote','set-url','origin','https://github.com/'+REPOSITORY+'.git'])
        def git(*args,data=None):
            return subprocess.check_output(['/usr/bin/git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','--git-dir='+str(repo)]+list(args),input=data).decode().strip()
        import os
        index=str(Path(self.tmp.name)/'index')
        env=dict(os.environ,GIT_INDEX_FILE=index)
        subprocess.check_call(['/usr/bin/git','--git-dir='+str(repo),'read-tree',self.commit],env=env)
        blob=git('hash-object','-w','--stdin',data=raw)
        subprocess.check_call(['/usr/bin/git','--git-dir='+str(repo),'update-index','--cacheinfo','100644',blob,CANDIDATE_FILES[0]],env=env)
        if extra_path:
            subprocess.check_call(['/usr/bin/git','--git-dir='+str(repo),'update-index','--add','--cacheinfo','100644',blob,extra_path],env=env)
        tree=subprocess.check_output(['/usr/bin/git','--git-dir='+str(repo),'write-tree'],env=env).decode().strip()
        commit=git('commit-tree',tree,'-p',self.commit,data=b'FIXTURE candidate only\n')
        self.files=dict(self.files);self.files[CANDIDATE_FILES[0]]=raw
        receipt=dict(self.source_receipt,source_comment_id=2,code_commit=commit)
        self.candidate=self.s.bind_development_candidate(receipt,{p:hashlib.sha256(v).hexdigest() for p,v in self.files.items()})['candidate']
        self.runner=BubblewrapNativeRunner(self.db,str(repo),self.commit,self.runner.plan)
        self.executor=NativeDevelopmentExecutor(self.runner,self.runner.plan)
    def replace_validator(self,body):
        source=self.files[CANDIDATE_FILES[0]].decode()
        start=source.index('def validate_event(');end=source.index('def bind_validated_receipt(',start)
        return (source[:start]+'def validate_event(event, control_repository, trusted_owner, destination=None):\n'+''.join('    '+line+'\n' for line in body.splitlines())+'\n\n'+source[end:]).encode()
    def test_real_candidate_failure_retains_failed_receipt_and_pid_binding(self):
        self.candidate_source(self.replace_validator('return {"authority_effect":"VALID"}'))
        with self.assertRaisesRegex(ValueError,'HOLD_NATIVE_TESTS_FAILED'):self.run_plan()
        status=self.runner.status(digest(self.candidate));self.assertEqual(status['state'],'FAILED')
        self.assertEqual(status['result']['receipt']['state'],'FAILED');self.assertIsNotNone(status['process'])
        with patch('native_sandbox_runner.subprocess.Popen',side_effect=AssertionError('NO_REPLAY')):
            with self.assertRaisesRegex(ValueError,'HOLD_NATIVE_TESTS_FAILED'):self.run_plan()
    def test_actual_stalled_candidate_timeout_fault_injection_is_query_only(self):
        self.candidate_source(self.replace_validator('while True: pass'))
        # Accelerate the existing fixed 180-second path for fault injection only.
        with patch('native_sandbox_runner.TIMEOUT',0.5):
            with self.assertRaisesRegex(ValueError,'HOLD_NATIVE_TESTS_FAILED'):self.run_plan()
        status=self.runner.status(digest(self.candidate));self.assertEqual(status['result']['detail']['reason'],'FIXED_PLAN_TIMEOUT')
        self.assertEqual(status['result']['receipt']['state'],'FAILED')
        self.assertTrue(status['result']['detail']['pure_contract_audited'])
        self.assertEqual(status['result']['detail']['last_started_case'],0)
        self.assertIsNone(process_identity(status['process']['pid']))
        with patch('native_sandbox_runner.subprocess.Popen',side_effect=AssertionError('NO_REPLAY')):
            self.assertEqual(self.runner.lookup(digest(self.candidate)),status['result']['receipt'])
    def test_unknown_response_reconciles_existing_canonical_receipt_without_second_spawn(self):
        original=self.runner.execute
        def lose_response(request,files):
            original(request,files)
            raise RuntimeError('TEST_LOST_RESPONSE_AFTER_REAL_EXECUTION')
        with patch.object(self.runner,'execute',side_effect=lose_response):
            with self.assertRaisesRegex(RuntimeError,'TEST_LOST_RESPONSE'):self.run_plan()
        self.assertEqual(self.runner.status(digest(self.candidate))['state'],'PASSED')
        with patch('native_sandbox_runner.subprocess.Popen',side_effect=AssertionError('NO_REPLAY')):
            self.assertEqual(self.run_plan()['receipt']['state'],'PASSED')
    def test_real_non_allowed_base_byte_change_is_rejected_before_send(self):
        self.candidate_source(self.files[CANDIDATE_FILES[0]],extra_path='scripts/not-approved.py')
        with self.assertRaisesRegex(ValueError,'NON_ALLOWED_BASE_BYTES_CHANGED'):self.run_plan()
        count=self.s.db.execute("SELECT count(*) FROM events WHERE kind='SANDBOX_INTENT'").fetchone()[0]
        self.assertEqual(count,0)
    def forged_output(self):
        responses=[dict(index=i,rejected=True) if row['expected'] is None else dict(index=i,result=row['expected']) for i,row in enumerate(challenges())]
        return ('XJ_SANDBOX_RESPONSE '+json.dumps(responses,sort_keys=True)+'\n').encode()
    def assert_no_forged_pass(self,raw):
        self.candidate_source(raw)
        with self.assertRaisesRegex(ValueError,'HOLD_NATIVE_TESTS_FAILED'):self.run_plan()
        status=self.runner.status(digest(self.candidate));self.assertEqual(status['state'],'FAILED')
        self.assertFalse(status['result']['detail']['pure_contract_audited'])
        for row in self.s.db.execute("SELECT payload_json FROM events WHERE kind='DEVELOPMENT_EXECUTION'"):
            self.assertNotEqual(json.loads(row[0])['receipt']['state'],'PASSED')
    def test_no_validate_function_cannot_forge_trusted_response_and_exit_zero(self):
        marker=self.forged_output()
        self.assert_no_forged_pass(('import os\nos.write(1,'+repr(marker)+')\nos._exit(0)\n').encode())
    def test_real_function_cannot_forge_stdout_from_module_top_level(self):
        marker=self.forged_output()
        raw=self.files[CANDIDATE_FILES[0]]+('\nos.write(1,'+repr(marker)+')\nos._exit(0)\n').encode()
        self.assert_no_forged_pass(raw)
    def test_called_function_cannot_forge_stdout_or_exit_before_return(self):
        marker=self.forged_output()
        self.assert_no_forged_pass(self.replace_validator('os.write(1,'+repr(marker)+')\nos._exit(0)'))
    def test_same_process_globals_introspection_cannot_reach_io_or_controller(self):
        self.assert_no_forged_pass(self.replace_validator('return validate_event.__globals__["os"]._exit(0)'))
    def test_indirect_json_callback_cannot_call_unaudited_module_function(self):
        self.assert_no_forged_pass(self.replace_validator('ignored = [0 for main in []]\nreturn json.loads("[]", object_pairs_hook=main)'))
    def test_decorator_cannot_run_before_audited_function_declaration(self):
        raw=self.files[CANDIDATE_FILES[0]].replace(b'def validate_event(',b'@os._exit(0)\ndef validate_event(',1)
        self.assert_no_forged_pass(raw)
    def test_missing_canonical_intent_or_plan_mismatch_cannot_execute(self):
        with self.assertRaisesRegex(ValueError,'EXISTING_CANONICAL_EXECUTION_INTENT_REQUIRED'):self.runner.lookup('0'*64)
        with self.assertRaisesRegex(ValueError,'PINNED_FIXED_PLAN_DIGEST_REQUIRED'):
            BubblewrapNativeRunner(self.db,str(ROOT),self.commit,'0'*64)
        with self.assertRaisesRegex(ValueError,'PINNED_FIXED_PLAN_DIGEST_REQUIRED'):BubblewrapNativeRunner(self.db,str(ROOT),self.commit,'0'*64)

if __name__=='__main__':unittest.main()
