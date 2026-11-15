import hashlib
import shutil
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

class ProducerExecutorTests(unittest.TestCase):
    def git(self,*args,raw=None):
        return subprocess.check_output(['/usr/bin/git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            '--git-dir='+str(self.repo)]+list(args),input=raw,stderr=subprocess.DEVNULL).decode().strip()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.repo=self.root/'repo.git'
        shutil.copytree(ROOT.parent/'derived.git',self.repo)
        self.repo.chmod(0o700)
        self.base=self.git('rev-parse','refs/heads/main')
        self.before_blob=self.git('rev-parse',self.base+':scripts/task_center_app.py')
        self.s=Supervisor(str(self.root/'ledger.sqlite'));self.authority=TestTenantAuthority(KEY)
        self.gateway=GatewayKernel(self.s,self.authority);self.context=self.authority.issue('tenant-a','admin:fixture')
        graph=demo_graph('tenant-a');graph['tasks'][0]['resources']=['git:huhongchuan0422-creator/Repository-name-xuanjun-ai-control/main'];graph['tasks'][0]['entry']='CHATGPT'
        self.gateway.register_graph(self.context,graph)
        self.fence=Fence(self.s,str(self.root/'locks'))
        self.contract={'task_id':'demo-b','spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,
          'target_repository':'huhongchuan0422-creator/Repository-name-xuanjun-ai-control','target_base_sha':self.base,'entry':'CHATGPT',
          'developer':{'issuer':'fixture','subject':'developer'},'allowed_files':['scripts/task_center_app.py'],
          'trusted_reviewers':[{'issuer':'fixture','subject':'qa','key_id':'TEST-QA','role':'QA'},
                               {'issuer':'fixture','subject':'security','key_id':'TEST-SECURITY','role':'SECURITY'}]}
        if getattr(self,'producer_http_test',False):
            from producer_http_contract import REFERENCE_SHA256
            self.contract['producer_http_test_sha256']=REFERENCE_SHA256
        self.s.register_development_contract('demo-b',self.contract)
        start=TestOnlyExecutor(self.gateway,self.fence,self.context).start('demo-b','attempt-b',['git:huhongchuan0422-creator/Repository-name-xuanjun-ai-control/main'],time.time()+600)
        self.ticket=start['ticket'];self.caller=start['caller']
        self.control=ModelControl(self.gateway,self.context,Fernet.generate_key())
        self.control.record_task_spec('demo-b','fixture add implementation',['scripts/task_center_app.py'],['host fixed add cases'])
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
          'repository':'huhongchuan0422-creator/Repository-name-xuanjun-ai-control','branch':'main','repository_root':str(self.repo),'resource_key':'git:huhongchuan0422-creator/Repository-name-xuanjun-ai-control/main',
          'allowed_file':'scripts/task_center_app.py','max_source_bytes':131072,'producer_snapshot_sha256':'fe9b78539bf92674ca8dcddeb5fb1813ccd032d6b34d5e6e65528444dc63fd35'}
        self.adapter=LocalDevelopmentExecutor(self.control,self.fence,self.profile)
        self.raw=(ROOT.parent.parent/'tc-real-development-checkpoint-20261114'/'candidate'/'scripts'/'task_center_app.py').read_bytes()
    def tearDown(self):
        self.fence.close();self.s.close();self.temp.cleanup()
    def proposal(self,changes=None,text=None):
        p={'file_path':'scripts/task_center_app.py','base_blob':self.before_blob,'content':self.raw.decode()}
        if changes:p.update(changes)
        q=self.control.queue_request('demo-b','developer',[{'role':'user','content':'fixture developer proposal'}],
                                     'fixture-request',128)
        r=ModelScheduler(self.control,adapters={'openai-compatible':BoundaryFixture(text or json.dumps(p))}).run_once()
        self.assertEqual(r['state'],'SUCCEEDED')
        return q['request_id']
    def apply(self,rid):return self.adapter.apply_proposal('demo-b','attempt-b',rid,self.ticket,self.caller)
    def test_real_combo_candidate_and_single_file_tree(self):
        result=self.apply(self.proposal())
        self.assertEqual(result['execution_state'],'HOLD_SANDBOX_UNAVAILABLE')
        self.assertEqual(self.git('diff-tree','--no-commit-id','--name-only','-r',self.base,result['code_commit']), 'scripts/task_center_app.py')
        self.assertEqual(self.git('rev-parse',result['code_commit']+':scripts/task_center_app.py'), _git_sha('blob',self.raw))
        candidate=self.s.development_candidate('demo-b',result['candidate_event_id'])
        self.assertEqual(candidate['files']['scripts/task_center_app.py'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.s._task('demo-b')['state'],'STARTED')
        print('DERIVED_TEST base='+self.base+' result='+result['code_commit'])
    def test_other_path_rejected_before_write(self):
        rid=self.proposal({'file_path':'scripts/other.py'})
        with self.assertRaisesRegex(ValueError,'EXACT_SOURCE_PROPOSAL_REQUIRED'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)
    def test_expired_lease_rejected_before_write(self):
        rid=self.proposal()
        self.s.db.execute("UPDATE tasks SET authority_valid_until=0 WHERE task_id=?",('demo-b',));self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'STALE_WRITER_TICKET'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)
    def test_wrong_profile_rejected(self):
        p=dict(self.profile,allowed_file='scripts/other.py')
        with self.assertRaisesRegex(ValueError,'EXACT_PRODUCER_PROFILE_REQUIRED'):
            LocalDevelopmentExecutor(self.control,self.fence,p)

    def host_call(self, request_id):
        import base64
        from task_center_mcp_development import DevelopmentHost
        from task_center_mcp_dispatch_host import dispatch_rpc,validate_config
        from task_center_mcp_service import MCPTaskService
        from task_supervisor import canonical
        binding={'tenant_id':'tenant-a','principal_id':'developer-1','project_id':'demo-project','task_id':'demo-b',
                 'spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,'contract_sha256':hashlib.sha256(canonical(self.contract).encode()).hexdigest(),
                 'role_id':'developer','role_version':'v1','phase':'EXECUTOR','review_kind':None,
                 'authority_identity':{'issuer':'fixture','subject':'developer'},'actions':['task_development_apply'],
                 'candidate_root':None,'executor_profile':self.profile}
        host=DevelopmentHost([binding],writer_context_provider=lambda task,attempt:{'ticket':self.ticket,'caller':self.caller,'lock_root':str(self.root/'locks')})
        cipher=self.control.fernet;master=base64.urlsafe_b64encode(cipher._signing_key+cipher._encryption_key)
        service=MCPTaskService(str(self.root/'ledger.sqlite'),KEY,'tenant-a',master,'developer-1','demo-project')
        identity={'tenant_id':'tenant-a','principal_id':'developer-1','project_id':'demo-project','scopes':['task:read','task:submit']}
        value={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'task_development_apply','arguments':{'task_id':'demo-b','attempt_id':'attempt-b','request_id':request_id}}}
        return json.loads(dispatch_rpc(service,identity,validate_config(None),value,False,host)['result']['content'][0]['text'])

    def test_original_main_host_entry_applies_derived_producer(self):
        result=self.host_call(self.proposal())
        self.assertEqual(result['execution_state'],'HOLD_SANDBOX_UNAVAILABLE')
        self.assertEqual(self.git('diff-tree','--no-commit-id','--name-only','-r',self.base,result['code_commit']),'scripts/task_center_app.py')
        print('HOST_DERIVED_TEST base='+self.base+' result='+result['code_commit'])

    def test_host_entry_rejects_expired_lease(self):
        rid=self.proposal()
        self.s.db.execute("UPDATE tasks SET authority_valid_until=0 WHERE task_id=?",('demo-b',));self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'STALE_WRITER_TICKET'):self.host_call(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)

    def test_host_entry_rejects_other_path(self):
        rid=self.proposal({'file_path':'scripts/other.py'})
        with self.assertRaisesRegex(ValueError,'EXACT_SOURCE_PROPOSAL_REQUIRED'):self.host_call(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),self.base)

    def test_reject_other_base_tree(self):
        bad_blob=self.git('hash-object','-w','--stdin',raw=b'changed other file\n')
        bad_tree=self.git('mktree',raw=('100644 blob '+bad_blob+'\tREADME.md\n').encode())
        bad_base=self.git('commit-tree',bad_tree,raw=b'wrong base\n')
        self.git('update-ref','refs/heads/main',bad_base,self.base)
        self.contract['target_base_sha']=bad_base
        from task_supervisor import canonical
        body=canonical(self.contract)
        self.s.db.execute("UPDATE events SET payload_json=?,evidence_ref=? WHERE task_id=? AND event_id='development-contract-v1'",(body,hashlib.sha256(body.encode()).hexdigest(),'demo-b'));self.s.db.commit()
        rid=self.proposal()
        with self.assertRaisesRegex(ValueError,'EXACT_PRODUCER_BASE_TREE_REQUIRED'):self.apply(rid)
        self.assertEqual(self.git('rev-parse','refs/heads/main'),bad_base)
