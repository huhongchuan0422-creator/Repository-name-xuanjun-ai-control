import json
from pathlib import Path
import sqlite3
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
from test_model_orchestration import ModelOrchestrationTests
from model_orchestration import ModelControl
from task_center_mcp_completion import CandidateLifecycleMCP
from task_center_mcp_dispatch_host import validate_config,dispatch_rpc,check_existing_bindings
from task_center_mcp_service import MCPTaskService

class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.f=ModelOrchestrationTests();self.f.setUp();f=self.f;f.assigned()
        for rid,phase,kind in [('qa','REVIEWER','QA'),('security','REVIEWER','SECURITY'),('acceptor','ACCEPTOR',None)]:
            f.role(rid,phase,['code'],False,kind);f.control.assign('demo-b',rid,'v1',rid)
        self.bindings={}
        for rid,principal,phase,kind,action in [('developer','developer-1','EXECUTOR',None,'task_submit_candidate'),
            ('qa','qa','REVIEWER','QA','task_review_candidate'),('security','security','REVIEWER','SECURITY','task_review_candidate'),
            ('acceptor','acceptor','ACCEPTOR',None,'task_accept_candidate')]:
            self.bindings[rid]={'tenant_id':'tenant-a','principal_id':principal,'project_id':'demo-project',
                'role_id':rid,'role_version':'v1','phase':phase,'review_kind':kind,'actions':[action,'task_candidate_status']}
        self.config=validate_config({'schema_version':1,'enabled':True,'bindings':[],
            'completion_bindings':list(self.bindings.values())})
        self.check=f.checklist_sha()
    def tearDown(self):self.f.tearDown()
    def facade(self,rid):
        b=self.bindings[rid];f=self.f
        c=ModelControl(f.gateway,f.authority.issue('tenant-a',b['principal_id']),f.master)
        return CandidateLifecycleMCP(c,b,str(Path(f.root)/'locks'))
    def args(self,**kw):return dict(task_id='demo-b',attempt_id='attempt-b',**kw)
    def submit(self):return self.facade('developer').call('task_submit_candidate',self.args(artifact_sha256='a'*64,checklist_sha256=self.check))['candidate_id']
    def reviewed(self):
        cid=self.submit()
        for rid in ('qa','security'):self.facade(rid).call('task_review_candidate',self.args(candidate_id=cid,findings=[],passed=True))
        return cid
    def test_real_original_ledger_review_terminal_revoke_release_and_duplicate(self):
        cid=self.reviewed();a=self.facade('acceptor');result=a.call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(result['state'],'ACCEPTED');self.assertEqual(self.f.supervisor._task('demo-b')['state'],'SUCCESS')
        self.assertEqual(self.f.supervisor._task('demo-b')['authority_state'],'REVOKED')
        self.assertTrue(a.call('task_accept_candidate',self.args(candidate_id=cid))['duplicate'])
        self.assertGreater(self.f.supervisor.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
    def test_missing_review_does_not_complete(self):
        cid=self.submit()
        with self.assertRaisesRegex(ValueError,'REVIEW_PASS'):self.facade('acceptor').call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(self.f.supervisor._task('demo-b')['state'],'STARTED')
    def test_submit_and_review_exact_duplicates(self):
        cid=self.submit();self.assertEqual(self.submit(),cid)
        a=self.facade('qa');args=self.args(candidate_id=cid,findings=[],passed=True)
        a.call('task_review_candidate',args);self.assertTrue(a.call('task_review_candidate',args)['duplicate'])
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY'):a.call('task_review_candidate',dict(args,passed=False))
    def test_no_checklist_or_forged_actor_or_extra_argument(self):
        a=self.facade('developer')
        with self.assertRaisesRegex(ValueError,'CHECKLIST'):a.call('task_submit_candidate',self.args(artifact_sha256='a'*64,checklist_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'EXACT_LIFECYCLE'):a.call('task_submit_candidate',self.args(artifact_sha256='a'*64,checklist_sha256=self.check,principal_id='acceptor'))
        a.binding['principal_id']='acceptor'
        with self.assertRaisesRegex(ValueError,'PRINCIPAL'):a.call('task_submit_candidate',self.args(artifact_sha256='a'*64,checklist_sha256=self.check))
    def test_wrong_project_attempt_disabled_role(self):
        for key,value,error in [('project_id','other','PROJECT'),('role_version','v99','ROLE')]:
            a=self.facade('developer');a.binding[key]=value
            with self.assertRaisesRegex(ValueError,error):a.call('task_submit_candidate',self.args(artifact_sha256='a'*64,checklist_sha256=self.check))
        with self.assertRaisesRegex(ValueError,'STALE'):self.facade('developer').call('task_submit_candidate',dict(self.args(artifact_sha256='a'*64,checklist_sha256=self.check),attempt_id='old'))
    def test_development_contract_cannot_bypass_signed_execution_path(self):
        # A canonical development marker suffices: generic model acceptance is unavailable.
        self.f.supervisor.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('demo-b','attempt-b','dev-contract','DEVELOPMENT_CONTRACT',1,'TEST_RUN','x','{}'));self.f.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'CONTROLLED_DEVELOPMENT'):self.submit()
    def test_terminal_rechecks_project_after_outer_validation(self):
        cid=self.reviewed();a=self.facade('acceptor');original=a.control.validate_accept_candidate;calls=[0]
        def validate(*args,**kw):
            result=original(*args,**kw);calls[0]+=1
            if calls[0]==1:self.pending=True
            return result
        # Mutate via second SQLite connection after outer transaction rollback.
        original_record=self.f.supervisor.record
        def record(*args,**kw):
            db=sqlite3.connect(self.f.db);db.execute("UPDATE gateway_task_metadata SET project_id='moved' WHERE task_id='demo-b'");db.commit();db.close()
            return original_record(*args,**kw)
        self.f.supervisor.record=record
        with self.assertRaisesRegex(ValueError,'PROJECT'):a.call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(self.f.supervisor._task('demo-b')['state'],'STARTED')
    def test_wrong_lock_provider_denied_before_terminal(self):
        cid=self.reviewed();a=self.facade('acceptor');a.lock_dir=str(Path(self.f.root)/'wrong-lock-provider')
        with self.assertRaisesRegex(ValueError,'LOCK_PROVIDER'):a.call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(self.f.supervisor._task('demo-b')['state'],'STARTED')
    def test_non_test_resources_rejected(self):
        self.f.supervisor.db.execute("UPDATE tasks SET resource_scope_json=? WHERE task_id='demo-b'",(json.dumps(['git:owner/repo/main']),));self.f.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'NON_TEST_COMPLETION'):self.submit()
    def test_cross_tenant_and_other_task_candidate_denied(self):
        cid=self.submit();a=self.facade('qa')
        a.control=ModelControl(self.f.gateway,self.f.authority.issue('tenant-b','qa'),self.f.master)
        with self.assertRaisesRegex(ValueError,'CROSS_TENANT'):a.call('task_review_candidate',self.args(candidate_id=cid,findings=[],passed=True))
        a=self.facade('qa')
        with self.assertRaisesRegex(ValueError,'EXACT_HOST_CANDIDATE'):a.call('task_review_candidate',self.args(candidate_id='0'*64,findings=[],passed=True))
    def test_inflight_model_request_blocks_completion(self):
        cid=self.reviewed()
        self.f.control.queue_request('demo-b','developer',[{'role':'user','content':'NOT_DISPATCHED_TEST_ONLY'}],'pending',16)
        with self.assertRaisesRegex(ValueError,'SIDE_EFFECT'):self.facade('acceptor').call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(self.f.supervisor._task('demo-b')['state'],'STARTED')
    def test_role_revocation_second_connection_at_terminal_is_denied(self):
        cid=self.reviewed();a=self.facade('acceptor');record=self.f.supervisor.record
        def race(*args,**kw):
            db=sqlite3.connect(self.f.db);db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='acceptor'");db.commit();db.close()
            return record(*args,**kw)
        self.f.supervisor.record=race
        with self.assertRaisesRegex(ValueError,'LIFECYCLE_ROLE'):a.call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(self.f.supervisor._task('demo-b')['state'],'STARTED')
    def test_original_partial_revocation_never_replayed_as_success(self):
        from unittest.mock import patch
        cid=self.reviewed();a=self.facade('acceptor')
        with patch('task_center_mcp_completion.Fence.drain',side_effect=ValueError('TEST_DRAIN_INTERRUPTED')):
            with self.assertRaisesRegex(ValueError,'TEST_DRAIN'):a.call('task_accept_candidate',self.args(candidate_id=cid))
        status=a.call('task_candidate_status',self.args(candidate_id=cid))
        self.assertEqual(status['completion_state'],'HOLD_REVOCATION_RECONCILIATION')
        with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE'):a.call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertNotEqual(status['candidate_state'],'ACCEPTED')

    def test_final_accept_rechecks_original_frozen_snapshot(self):
        cid=self.reviewed();f=self.f
        f.executor.complete_success('demo-b','attempt-b','a'*64,json.loads(f.supervisor._task('demo-b')['completion_json']))
        # Existing frozen-spec regression pattern: inspect a changed persisted scope.
        f.supervisor.db.execute("UPDATE task_work_specs SET goal='changed original spec' WHERE task_id='demo-b'")
        f.supervisor.db.commit()
        a=self.facade('acceptor');b={k:a.binding[k] for k in ('project_id','principal_id','role_id','role_version','phase','review_kind')}
        b.update(task_id='demo-b',attempt_id='attempt-b',candidate_id=cid)
        with self.assertRaisesRegex(ValueError,'FROZEN'):
            a.control.accept_candidate(cid,'acceptor',_host_binding=b)
        self.assertEqual(f.supervisor.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(cid,)).fetchone()[0],'REVIEW_PASSED')
    def test_revoked_without_original_release_receipt_remains_hold(self):
        import time
        cid=self.reviewed();f=self.f;now=time.time();s=f.supervisor
        s.record('demo-b','attempt-b','terminal-attempt-b','TERMINAL',now,'TEST_RUN','test-terminal-attempt-b',
            {'state':'SUCCESS','artifact_sha256':'a'*64,'writer_stopped':True,'effects_reconciled':True,
             'next_action':'DEPENDENCIES_RECHECK','completion_evidence':json.loads(s._task('demo-b')['completion_json'])})
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'test-executor-finalizer'}
        f.fence.begin_revocation('demo-b',controller);f.fence.drain('demo-b',controller,timeout=1)
        f.fence.invalidate_source_resources('demo-b','terminal-release');s.complete_revocation('demo-b')
        a=self.facade('acceptor')
        with self.assertRaisesRegex(ValueError,'RESOURCE_RELEASE'):a.call('task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(a.call('task_candidate_status',self.args(candidate_id=cid))['completion_state'],'HOLD_RESOURCE_RELEASE_RECONCILIATION')
    def test_host_acceptance_and_audit_share_original_transaction(self):
        cid=self.reviewed();a=self.facade('acceptor');trace=[]
        a.control.db.set_trace_callback(trace.append)
        a.call('task_accept_candidate',self.args(candidate_id=cid))
        update=next(i for i,q in enumerate(trace) if 'UPDATE delivery_candidates SET accepted_by=' in q)
        audit=next(i for i,q in enumerate(trace) if 'INSERT' in q and 'model_audit' in q and 'CANDIDATE_ACCEPTED' in q)
        self.assertLess(update,audit);self.assertFalse(any(q=='COMMIT' for q in trace[update:audit]))

    def test_host_default_off_and_scopes_and_real_identity(self):
        f=self.f;b=self.bindings['developer'];identity=dict(b,scopes=['task:read'])
        service=MCPTaskService(f.db,b'0123456789abcdef0123456789abcdef','tenant-a',f.master,'developer-1','demo-project')
        call={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'task_submit_candidate','arguments':self.args(artifact_sha256='a'*64,checklist_sha256=self.check)}}
        with self.assertRaisesRegex(ValueError,'HOST_BINDING'):dispatch_rpc(service,identity,validate_config(None),call,False)
        with self.assertRaisesRegex(ValueError,'SCOPE'):dispatch_rpc(service,identity,self.config,call,False)
        identity['scopes']=['task:submit'];r=dispatch_rpc(service,identity,self.config,call,False)
        self.assertFalse(r['result']['isError'])
        cid=json.loads(r['result']['content'][0]['text'])['candidate_id']
        self.assertEqual(f.supervisor.db.execute('SELECT submitted_by FROM delivery_candidates WHERE candidate_id=?',(cid,)).fetchone()[0],'developer-1')
    def test_bool_and_readonly_status_and_existing_registry(self):
        cid=self.submit()
        with self.assertRaisesRegex(ValueError,'BOUNDED_REVIEW'):self.facade('qa').call('task_review_candidate',self.args(candidate_id=cid,findings=[],passed=1))
        result=self.facade('developer').call('task_candidate_status',self.args(candidate_id=cid));self.assertEqual(result['canonical_task_state'],'STARTED')
        check_existing_bindings(self.f.db,self.config)
        self.config['completion_bindings'][0]['role_version']='missing'
        with self.assertRaisesRegex(ValueError,'EXISTING_COMPLETION'):check_existing_bindings(self.f.db,self.config)

class CompletionHTTPTests(unittest.TestCase):
    def setUp(self):
        from test_mcp_dispatch_host import HostHTTPTests
        from test_mcp_dispatch_host import fixture
        from reusable_task_gateway import GatewayKernel,TestTenantAuthority,TestOnlyExecutor
        from reusable_scheduler_cli import demo_graph
        from task_supervisor import Supervisor
        from task_writer_fence import Fence
        import time
        self.h=HostHTTPTests();h=self.h
        h.f=fixture.MCPHTTPTests();h.f.setUp()
        h.f.server.mcp_worker.stop();h.f.server.shutdown();h.f.server.server_close();h.f.thread.join(2)
        h.supervisor=Supervisor(h.f.db);authority=TestTenantAuthority(fixture.KEY)
        h.gateway=GatewayKernel(h.supervisor,authority);h.context=authority.issue('tenant-mcp','admin:fixture')
        graph=demo_graph('tenant-mcp');graph['project_id']='project-mcp';h.gateway.register_graph(h.context,graph)
        h.fence=Fence(h.supervisor,h.f.db+'.test-only-locks')
        TestOnlyExecutor(h.gateway,h.fence,h.context).start('demo-b','attempt-b',['fake:demo-b'],time.time()+600)
        h.control=ModelControl(h.gateway,h.context,h.f.master)
        h.control.record_task_spec('demo-b','bounded test',['result'],['offline receipt'])
        h.control.create_role({'role_id':'developer','version':'v1','phase':'EXECUTOR','capabilities':['general'],
            'writer_allowed':True,'enabled':True,'review_kind':None})
        h.start_host(None,False)
        self.bindings=[]
        for rid,principal,phase,kind,action in [('developer','developer-1','EXECUTOR',None,'task_submit_candidate'),
            ('qa','qa','REVIEWER','QA','task_review_candidate'),('security','security','REVIEWER','SECURITY','task_review_candidate'),
            ('acceptor','acceptor','ACCEPTOR',None,'task_accept_candidate')]:
            if rid!='developer':h.control.create_role({'role_id':rid,'version':'v1','phase':phase,
                'capabilities':['general'],'writer_allowed':False,'enabled':True,'review_kind':kind})
            h.control.assign('demo-b',rid,'v1',principal)
            self.bindings.append({'tenant_id':'tenant-mcp','principal_id':principal,'project_id':'project-mcp',
                'role_id':rid,'role_version':'v1','phase':phase,'review_kind':kind,'actions':[action,'task_candidate_status']})
        self.config={'schema_version':1,'enabled':True,'bindings':[],'completion_bindings':self.bindings}
        self.check=h.control.register_checklist('demo-b',[{'id':'offline receipt','required':True,'result':'PASS',
            'evidence':'ISOLATED_HOST_FIXTURE_NOT_PRODUCTION_TEST'}],'admin:fixture')['content_sha256']
        h.restart(self.config)
    def tearDown(self):self.h.tearDown()
    def args(self,**kw):return dict(task_id='demo-b',attempt_id='attempt-b',**kw)
    def test_http_real_oauth_roles_to_terminal_default_off_restart(self):
        h=self.h
        token=h.token(principal='developer-1')
        cid=h.rpc(token,'task_submit_candidate',self.args(artifact_sha256='a'*64,checklist_sha256=self.check))['candidate_id']
        for actor in ('qa','security'):
            h.rpc(h.token(principal=actor),'task_review_candidate',self.args(candidate_id=cid,findings=[],passed=True))
        accept_token=h.token(principal='acceptor')
        result=h.rpc(accept_token,'task_accept_candidate',self.args(candidate_id=cid))
        self.assertEqual(result['canonical_task_state'],'SUCCESS')
        self.assertTrue(h.rpc(accept_token,'task_accept_candidate',self.args(candidate_id=cid))['duplicate'])
        h.restart(None)
        self.assertNotIn('task_accept_candidate',[x['name'] for x in h.rpc(accept_token)])
        self.assertEqual(h.supervisor._task('demo-b')['state'],'SUCCESS')
    def test_http_readonly_and_unbound_identity_rejected(self):
        from urllib.error import HTTPError
        h=self.h;args=self.args(artifact_sha256='a'*64,checklist_sha256=self.check)
        with self.assertRaises(HTTPError) as caught:h.rpc(h.token('task:read',principal='developer-1'),'task_submit_candidate',args)
        self.assertEqual(caught.exception.code,401)
        self.assertNotIn('task_submit_candidate',[x['name'] for x in h.rpc(h.token(principal='unbound'))])
    def test_http_concurrent_duplicate_submit_only_one_candidate(self):
        from concurrent.futures import ThreadPoolExecutor
        h=self.h;token=h.token(principal='developer-1');args=self.args(artifact_sha256='a'*64,checklist_sha256=self.check)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:h.rpc(token,'task_submit_candidate',args),range(4)))
        self.assertEqual(len({r['candidate_id'] for r in results}),1)
        self.assertEqual(h.supervisor.db.execute('SELECT count(*) FROM delivery_candidates').fetchone()[0],1)

if __name__=='__main__':unittest.main()
