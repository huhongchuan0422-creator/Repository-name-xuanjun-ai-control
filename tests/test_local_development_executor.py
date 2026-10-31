import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT
sys.path.insert(0,str(BASE/'scripts'));sys.path.insert(0,str(ROOT/'scripts'))
from cryptography.fernet import Fernet
from task_supervisor import Supervisor
from task_writer_fence import Fence
from reusable_task_gateway import GatewayKernel,TestTenantAuthority,TestOnlyExecutor
from reusable_scheduler_cli import demo_graph
from model_orchestration import ModelControl,ModelScheduler
from local_development_executor import LocalDevelopmentExecutor,capabilities,_git_sha
KEY=b'0123456789abcdef0123456789abcdef'

class BoundaryFixture:
    def __init__(self,content):self.content=content
    def invoke(self,*args,**kwargs):
        return {'content':self.content,'usage':{'input_tokens':1,'output_tokens':32,'total_tokens':33},
                'provider_request_id':'OFFLINE_TEST_FIXTURE_NOT_AI'}

class LocalExecutorTests(unittest.TestCase):
    def git(self,*args,raw=None):
        return subprocess.check_output(['/usr/bin/git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            '--git-dir='+str(self.repo)]+list(args),input=raw,stderr=subprocess.DEVNULL).decode().strip()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.repo=self.root/'repo.git'
        subprocess.check_call(['/usr/bin/git','init','--bare','-q',str(self.repo)])
        self.repo.chmod(0o700);self.git('remote','add','origin','https://github.com/owner/repo.git')
        self.before_raw=b'def add(a, b):\n    return a - b\n'
        self.before_blob=self.git('hash-object','-w','--stdin',raw=self.before_raw)
        tree=self.git('mktree',raw=('100644 blob '+self.before_blob+'\tmodule.py\n').encode())
        self.base=self.git('commit-tree',tree,raw=b'fixture base\n');self.git('update-ref','refs/heads/main',self.base)
        self.s=Supervisor(str(self.root/'ledger.sqlite'));self.authority=TestTenantAuthority(KEY)
        self.gateway=GatewayKernel(self.s,self.authority);self.context=self.authority.issue('tenant-a','admin:fixture')
        graph=demo_graph('tenant-a');graph['tasks'][0]['resources']=['git:owner/repo/main'];graph['tasks'][0]['entry']='CHATGPT'
        self.gateway.register_graph(self.context,graph)
        self.fence=Fence(self.s,str(self.root/'locks'))
        self.contract={'task_id':'demo-b','spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,
          'target_repository':'owner/repo','target_base_sha':self.base,'entry':'CHATGPT',
          'developer':{'issuer':'fixture','subject':'developer'},'allowed_files':['module.py'],
          'trusted_reviewers':[{'issuer':'fixture','subject':'qa','key_id':'TEST-QA','role':'QA'},
                               {'issuer':'fixture','subject':'security','key_id':'TEST-SECURITY','role':'SECURITY'}]}
        self.s.register_development_contract('demo-b',self.contract)
        start=TestOnlyExecutor(self.gateway,self.fence,self.context).start('demo-b','attempt-b',['git:owner/repo/main'],time.time()+600)
        self.ticket=start['ticket'];self.caller=start['caller']
        self.control=ModelControl(self.gateway,self.context,Fernet.generate_key())
        self.control.record_task_spec('demo-b','fixture add implementation',['module.py'],['host fixed add cases'])
        self.control.upsert_provider({'provider_id':'offline','display_name':'offline fixture','adapter_type':'openai-compatible',
          'base_url':'http://127.0.0.1:1','enabled':True,'price_state':'KNOWN_FREE','rate_limit_per_min':10,
          'concurrency_limit':1,'timeout_seconds':1,'retry_limit':0},'fixture-only-secret')
        self.control.upsert_model({'provider_id':'offline','model_id':'fixture','capabilities':['code'],
          'enabled':True,'price_state':'KNOWN_FREE','input_unit_cost':0,'output_unit_cost':0})
        self.control.set_quota_status('offline','AVAILABLE','TEST_FIXTURE_NOT_BALANCE',time.time(),None)
        self.control.register_benchmark_suite('fixture',[{'case_id':'c','capability':'code',
            'messages':[{'role':'user','content':'fixture'}],'expected_contains':'ok'}])
        self.control.run_benchmark('offline','fixture','fixture',BoundaryFixture('ok'))
        self.control.create_role({'role_id':'developer','version':'v1','phase':'EXECUTOR','capabilities':['code'],
            'writer_allowed':True,'enabled':True,'review_kind':None})
        self.control.assign('demo-b','developer','v1','developer-1')
        self.profile={'project_id':'demo-project','role_id':'developer','role_version':'v1','principal_id':'developer-1',
          'repository':'owner/repo','branch':'main','repository_root':str(self.repo),'resource_key':'git:owner/repo/main',
          'allowed_file':'module.py','max_source_bytes':8192}
        self.adapter=LocalDevelopmentExecutor(self.control,self.fence,self.profile)
        self.raw=b'def add(a, b):\n    return a + b\n'
    def tearDown(self):
        self.fence.close();self.s.close();self.temp.cleanup()
    def proposal(self,changes=None,text=None):
        p={'file_path':'module.py','base_blob':self.before_blob,'content':self.raw.decode()}
        if changes:p.update(changes)
        q=self.control.queue_request('demo-b','developer',[{'role':'user','content':'fixture developer proposal'}],
                                     'fixture-request',128)
        r=ModelScheduler(self.control,adapters={'openai-compatible':BoundaryFixture(text or json.dumps(p))}).run_once()
        self.assertEqual(r['state'],'SUCCEEDED')
        return q['request_id']
    def apply(self,rid):return self.adapter.apply_proposal('demo-b','attempt-b',rid,self.ticket,self.caller)
    def test_real_git_write_and_canonical_candidate_but_execution_hold(self):
        result=self.apply(self.proposal())
        self.assertEqual(self.git('show','refs/heads/main:module.py'),self.raw.decode().strip())
        self.assertEqual(result['execution_state'],'HOLD_SANDBOX_UNAVAILABLE')
        self.assertFalse(result['generated_code_executed'])
        self.assertEqual(result['syntax_state'],'PASS_SYNTAX')
        self.assertEqual(self.s._task('demo-b')['state'],'STARTED')
        candidate=self.s.development_candidate('demo-b',result['candidate_event_id'])
        self.assertEqual(candidate['source_kind'],'LOCAL_ONLY_CONFIRMED_OPERATION')
        self.assertNotIn('source_comment_id',candidate)
        self.assertEqual(candidate['files']['module.py'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.adapter.status('demo-b','attempt-b')['execution_state'],'HOLD_SANDBOX_UNAVAILABLE')
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_CONSUMED_ACK_REQUIRED'):
            TestOnlyExecutor(self.gateway,self.fence,self.context).start('demo-a','attempt-a',['fake:shared'],time.time()+600)
    def test_duplicate_returns_same_commit_without_reapplying(self):
        rid=self.proposal();a=self.apply(rid);b=self.apply(rid)
        self.assertTrue(b['duplicate']);self.assertEqual(a['code_commit'],b['code_commit'])
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM writer_operations').fetchone()[0],1)
    def test_shell_extra_fields_and_path_proposals_rejected(self):
        rid=self.proposal({'shell':'echo forbidden'})
        with self.assertRaisesRegex(ValueError,'EXACT_SOURCE_PROPOSAL_REQUIRED'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)
    def test_noncanonical_file_rejected(self):
        rid=self.proposal({'file_path':'../outside.py'})
        with self.assertRaises(ValueError):self.apply(rid)
    def test_invalid_syntax_never_writes(self):
        rid=self.proposal({'content':'def broken('})
        with self.assertRaisesRegex(ValueError,'SOURCE_SYNTAX_REJECTED'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)
    def test_import_side_effect_is_not_executed(self):
        marker=self.root/'must-not-exist'
        self.raw=('open('+repr(str(marker))+',"w").write("bad")\n').encode()
        result=self.apply(self.proposal())
        self.assertFalse(marker.exists());self.assertEqual(result['execution_state'],'HOLD_SANDBOX_UNAVAILABLE')
    def test_revoked_writer_cannot_write(self):
        rid=self.proposal();self.fence.begin_revocation('demo-b',{'role':'REVOCATION_CONTROLLER','caller_id':'fixture'})
        with self.assertRaises(ValueError):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)
    def test_unknown_operation_cannot_replay(self):
        rid=self.proposal();original=self.adapter._git
        def failed(*args,**kwargs):
            if args[0]=='update-ref':raise ValueError('SIMULATED_LOCAL_FAILURE')
            return original(*args,**kwargs)
        self.adapter._git=failed
        with self.assertRaisesRegex(ValueError,'SIMULATED_LOCAL_FAILURE'):self.apply(rid)
        self.adapter._git=original
        self.assertEqual(self.s.db.execute('SELECT state FROM writer_operations').fetchone()[0],'UNKNOWN')
        with self.assertRaisesRegex(ValueError,'EXISTING_OPERATION_HOLD_NO_REPLAY'):self.apply(rid)
    def test_forged_reviews_cannot_turn_execution_hold_into_success(self):
        self.apply(self.proposal())
        with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX_UNAVAILABLE'):
            self.adapter.review_or_finalize({'decision':'PASS','signature':'TEST-FIXTURE'})
        self.assertEqual(self.s._task('demo-b')['state'],'STARTED')
    def test_canonical_review_direct_call_rejects_local_hold(self):
        result=self.apply(self.proposal())
        candidate=self.s.development_candidate('demo-b',result['candidate_event_id'])
        contract=dict(self.contract,code_commit=candidate['code_commit'])
        binding={'contract':contract,'files':candidate['files']}
        from task_supervisor import canonical
        bundle=hashlib.sha256(canonical(binding).encode()).hexdigest()
        for authority in ('VALID','REVOKING','REVOKED'):
            self.s.db.execute('UPDATE tasks SET authority_state=? WHERE task_id=?',(authority,'demo-b'))
            self.s.db.commit()
            with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX_UNAVAILABLE'):
                self.s.record_development_review('demo-b',result['candidate_event_id'],
                    {'module.py':self.raw},bundle,{'QA':'1'*64,'SECURITY':'2'*64},'direct-review')
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM events WHERE kind='DEVELOPMENT_REVIEWED'").fetchone()[0],0)
        self.assertEqual(self.s._task('demo-b')['state'],'STARTED')

    def test_canonical_complete_rejects_historical_local_review(self):
        result=self.apply(self.proposal())
        row=self.s.db.execute('SELECT * FROM events WHERE event_id=?',(result['candidate_event_id'],)).fetchone()
        # Simulate a pre-fix persisted reviewed event; never real QA evidence.
        reviewed={'candidate_event_id':result['candidate_event_id'],'candidate_sha256':row['evidence_ref']}
        self.s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
            ('demo-b','attempt-b','historical-test-review','DEVELOPMENT_REVIEWED',time.time(),
             'TEST_RUN','1'*64,json.dumps(reviewed)))
        self.s.db.commit()
        for authority in ('VALID','REVOKING','REVOKED'):
            self.s.db.execute('UPDATE tasks SET authority_state=? WHERE task_id=?',(authority,'demo-b'))
            self.s.db.commit()
            with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX_UNAVAILABLE'):
                self.s.complete_development_candidate('demo-b','historical-test-review','direct-complete')
        self.assertEqual(self.s._task('demo-b')['state'],'STARTED')
        self.assertIsNone(self.s.db.execute('SELECT 1 FROM events WHERE event_id=?',('direct-complete',)).fetchone())

    def test_successful_proposal_with_revoked_role_write_bit_does_not_write(self):
        rid=self.proposal()
        self.s.db.execute("UPDATE role_templates SET writer_allowed=0 WHERE role_id='developer'");self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'EXACT_SUCCESSFUL_DEVELOPER_PROPOSAL_REQUIRED'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM writer_operations').fetchone()[0],0)

    def test_wrong_project_and_old_attempt_rejected(self):
        rid=self.proposal()
        with self.assertRaisesRegex(ValueError,'STALE_TASK_ATTEMPT'):
            self.adapter.apply_proposal('demo-b','old',rid,self.ticket,self.caller)
        self.adapter.profile['project_id']='other'
        with self.assertRaisesRegex(ValueError,'PROJECT_TASK_NOT_VISIBLE'):self.apply(rid)
    def test_capabilities_never_claim_executed_code(self):
        c=capabilities();self.assertFalse(c['generated_code_execution']);self.assertFalse(c['review_execution'])
        self.assertFalse(c['model_invocation']);self.assertEqual(c['execution_state'],'HOLD_SANDBOX_UNAVAILABLE')

    def test_cancel_requested_or_unknown_model_result_cannot_write(self):
        rid=self.proposal()
        self.s.db.execute('UPDATE model_requests SET cancel_requested=1 WHERE request_id=?',(rid,));self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'EXACT_SUCCESSFUL_DEVELOPER_PROPOSAL_REQUIRED'):self.apply(rid)
        self.s.db.execute("UPDATE model_requests SET cancel_requested=0,state='UNKNOWN' WHERE request_id=?",(rid,));self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'EXACT_SUCCESSFUL_DEVELOPER_PROPOSAL_REQUIRED'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)

    def test_symlink_repository_member_rejected(self):
        rid=self.proposal();(self.repo/'forbidden-link').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError,'UNSAFE_LOCAL_REPOSITORY'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)

    def test_canonical_local_candidate_rejects_forged_provenance(self):
        captured={};original=self.s.bind_local_development_candidate
        def observe(receipt,files):
            captured['receipt']=dict(receipt);captured['files']=dict(files)
            return original(receipt,files)
        self.s.bind_local_development_candidate=observe
        self.apply(self.proposal())
        receipt=captured['receipt'];files=captured['files']
        for override in ({'code_commit':'0'*40},{'source_operation_id':'unregistered'}):
            with self.assertRaises(ValueError):original(dict(receipt,**override),files)
        with self.assertRaisesRegex(ValueError,'LOCAL_OPERATION_PROVENANCE_REQUIRED'):
            original(dict(receipt,source_comment_id=123),files)
        with self.assertRaisesRegex(ValueError,'LOCAL_OPERATION_CANDIDATE_MISMATCH'):
            original(receipt,{'module.py':b'def add(a,b): return 999\n'})

    def test_executor_does_not_change_model_budget_or_issue_another_request(self):
        rid=self.proposal()
        before=tuple(self.s.db.execute('SELECT max_output_tokens,allow_paid FROM model_request_bindings WHERE request_id=?',(rid,)).fetchone())
        self.apply(rid)
        after=tuple(self.s.db.execute('SELECT max_output_tokens,allow_paid FROM model_request_bindings WHERE request_id=?',(rid,)).fetchone())
        self.assertEqual(before,after);self.assertEqual(after,(128,0))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
        self.assertEqual(self.s.db.execute('SELECT attempts FROM model_requests').fetchone()[0],1)

if __name__=='__main__':unittest.main()
