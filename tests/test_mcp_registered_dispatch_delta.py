"""Original registered assignment and model queue, simulated host/provider only."""
import json,unittest
import test_mcp_dispatch_host as fx
from task_center_mcp_service import MCPTaskService,MCPWorkerAdmission
from task_center_mcp_dispatch_host import dispatch_rpc
from task_center_role_contract import RoleContractResolver
from model_orchestration import ModelScheduler,ProviderError

class Adapter:
    def __init__(self):self.calls=0;self.failure=None
    def invoke(self,*args):
        self.calls+=1
        if self.failure:raise ProviderError(self.failure,'fixture',False)
        return {'content':'fixture','usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2},'provider_request_id':'fixture'}

class RegisteredDispatch(unittest.TestCase):
    def setUp(self):
        self.f=fx.HostHTTPTests();self.f.setUp();f=self.f;self.db=f.control.db
        self.cfg=fx.config();self.identity={'tenant_id':'tenant-mcp','principal_id':'owner-1','project_id':'project-mcp','scopes':['task:read','task:submit']}
        spec=self.db.execute("SELECT spec_sha256 FROM tasks WHERE task_id='demo-b'").fetchone()[0]
        contract={'contract_id':'fixture-developer','contract_version':1,'tenant_id':'tenant-mcp','project_id':'project-mcp','task_id':'demo-b','attempt_id':'attempt-b','task_spec_sha256':spec,'role_id':'developer','role_version':'v1','role_scope':['general'],'provider_id':'fixture','required_categories':['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT','INSTALL','SOURCE'],'not_applicable':{}}
        self.contract=RoleContractResolver(self.db,[contract])
        self.service=MCPTaskService(f.f.db,fx.fixture.KEY,'tenant-mcp',f.f.master,'owner-1','project-mcp',execution_enabled=True)
        self.ident={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        self.args=dict(self.ident,input_text='local fixture',idempotency_key='registered-fixture',max_output_tokens=16)
        self.rpc('task_assign_role',self.ident)
    def tearDown(self):self.f.tearDown()
    def rpc(self,name,args):
        value={'jsonrpc':'2.0','id':9,'method':'tools/call','params':{'name':name,'arguments':args}}
        result=dispatch_rpc(self.service,self.identity,self.cfg,value,True,role_contract=self.contract)
        return json.loads(result['result']['content'][0]['text'])
    def scheduler(self,adapter,admission=True):
        return ModelScheduler(self.f.control,adapters={'openai-compatible':adapter},admission=MCPWorkerAdmission(self.contract,self.cfg) if admission else None)
    def test_new_dispatch_duplicate_and_guarded_worker(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)
        first=self.rpc('task_dispatch',self.args);again=self.rpc('task_dispatch',self.args)
        self.assertFalse(first['duplicate']);self.assertTrue(again['duplicate']);self.assertEqual(first['request_id'],again['request_id'])
        self.assertEqual(self.db.execute("SELECT count(*) FROM model_audit WHERE action='MCP_REGISTERED_QUEUE'").fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM mcp_task_bindings').fetchone()[0],0)
        adapter=Adapter();scheduler=self.scheduler(adapter)
        self.assertEqual(scheduler.run_once()['state'],'SUCCEEDED');self.assertEqual(adapter.calls,1)
        status=self.rpc('task_dispatch_status',{'task_id':'demo-b','attempt_id':'attempt-b','request_id':first['request_id']})
        self.assertEqual(status['request_state'],'SUCCEEDED');self.assertEqual(scheduler.run_once()['state'],'IDLE');self.assertEqual(adapter.calls,1)
    def test_untrusted_scheduler_cannot_bypass_worker_guard(self):
        self.rpc('task_dispatch',self.args);adapter=Adapter()
        result=self.scheduler(adapter,False).run_once()
        self.assertEqual(result['state'],'HOLD');self.assertEqual(adapter.calls,0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],1)
    def test_scope_revoked_before_queue_has_supervision(self):
        self.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='developer'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'TASK_CONTRACT_UNKNOWN'):self.rpc('task_dispatch',self.args)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],1)
    def test_queued_scope_revocation_and_missing_assignment_hold(self):
        first=self.rpc('task_dispatch',self.args)
        self.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='developer'");self.db.commit()
        adapter=Adapter();self.assertEqual(self.scheduler(adapter).run_once()['state'],'HOLD');self.assertEqual(adapter.calls,0)
        self.assertEqual(self.db.execute('SELECT state FROM model_requests WHERE request_id=?',(first['request_id'],)).fetchone()[0],'HOLD')
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],1)
    def test_attempt_drift_before_dispatch_does_not_queue(self):
        self.db.execute("UPDATE tasks SET attempt_id='different' WHERE task_id='demo-b'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'STALE_TASK_ATTEMPT'):self.rpc('task_dispatch',self.args)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)
    def test_missing_assignment_after_queue_is_visible(self):
        first=self.rpc('task_dispatch',self.args)
        self.db.execute("DELETE FROM model_assignments WHERE task_id='demo-b'");self.db.commit()
        adapter=Adapter();self.assertEqual(self.scheduler(adapter).run_once()['state'],'HOLD');self.assertEqual(adapter.calls,0)
        self.assertEqual(self.db.execute('SELECT state FROM model_requests WHERE request_id=?',(first['request_id'],)).fetchone()[0],'HOLD')
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],1)
    def test_missing_source_audit_default_scheduler_must_hold(self):
        first=self.rpc('task_dispatch',self.args)
        self.db.execute("DELETE FROM model_audit WHERE action='MCP_REGISTERED_QUEUE' AND target_id=?",(first['request_id'],));self.db.commit()
        adapter=Adapter();self.assertEqual(self.scheduler(adapter,False).run_once()['state'],'HOLD')
        self.assertEqual(adapter.calls,0)
        self.assertEqual(self.db.execute('SELECT state FROM model_requests WHERE request_id=?',(first['request_id'],)).fetchone()[0],'HOLD')
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],1)
    def test_missing_audit_and_assignment_still_supervised(self):
        first=self.rpc('task_dispatch',self.args)
        self.db.execute("DELETE FROM model_audit WHERE action='MCP_REGISTERED_QUEUE' AND target_id=?",(first['request_id'],))
        self.db.execute("DELETE FROM model_assignments WHERE task_id='demo-b'");self.db.commit()
        adapter=Adapter();self.assertEqual(self.scheduler(adapter,False).run_once()['state'],'HOLD');self.assertEqual(adapter.calls,0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],1)
    def test_duplicate_rejects_missing_partial_multiple_and_tampered_audit(self):
        first=self.rpc('task_dispatch',self.args)
        audit=self.db.execute("SELECT * FROM model_audit WHERE action='MCP_REGISTERED_QUEUE' AND target_id=?",(first['request_id'],)).fetchone()
        original=tuple(audit); detail=json.loads(audit['detail_json'])
        variants=[None,{},dict(detail,contract_sha256='a'*64),dict(detail,provider_id='other')]
        for value in variants:
            self.db.execute("DELETE FROM model_audit WHERE action='MCP_REGISTERED_QUEUE' AND target_id=?",(first['request_id'],))
            if value is not None:
                row=list(original);row[5]=json.dumps(value);self.db.execute('INSERT INTO model_audit VALUES (?,?,?,?,?,?,?)',row)
            self.db.commit()
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'MCP_REGISTERED_REQUEST_PROVENANCE_REQUIRED'):
                self.rpc('task_dispatch',self.args)
        self.db.execute("DELETE FROM model_audit WHERE action='MCP_REGISTERED_QUEUE' AND target_id=?",(first['request_id'],))
        self.db.execute('INSERT INTO model_audit VALUES (?,?,?,?,?,?,?)',original)
        second=list(original);second[0]='duplicate-fixture';self.db.execute('INSERT INTO model_audit VALUES (?,?,?,?,?,?,?)',second);self.db.commit()
        with self.assertRaisesRegex(ValueError,'MCP_REGISTERED_REQUEST_PROVENANCE_REQUIRED'):self.rpc('task_dispatch',self.args)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
    def test_erased_or_forged_source_marker_is_held(self):
        first=self.rpc('task_dispatch',self.args)
        self.db.execute('UPDATE model_request_bindings SET source_metadata_json=NULL,source_metadata_mac=NULL WHERE request_id=?',(first['request_id'],))
        self.db.execute("DELETE FROM model_audit WHERE action IN ('MCP_REGISTERED_QUEUE','ROLE_CONTRACT_PLANNED')");self.db.commit()
        adapter=Adapter();self.assertEqual(self.scheduler(adapter,False).run_once()['state'],'HOLD');self.assertEqual(adapter.calls,0)
        self.assertEqual(self.db.execute("SELECT error_kind FROM model_requests WHERE request_id=?",(first['request_id'],)).fetchone()[0],'MCP_REQUEST_SOURCE_INTEGRITY_HOLD')
    def test_worker_rejects_tampered_audit_detail(self):
        first=self.rpc('task_dispatch',self.args)
        row=self.db.execute("SELECT detail_json FROM model_audit WHERE action='MCP_REGISTERED_QUEUE' AND target_id=?",(first['request_id'],)).fetchone()
        detail=json.loads(row[0]);detail['contract_sha256']='a'*64
        self.db.execute("UPDATE model_audit SET detail_json=? WHERE action='MCP_REGISTERED_QUEUE' AND target_id=?",(json.dumps(detail),first['request_id']));self.db.commit()
        adapter=Adapter();self.assertEqual(self.scheduler(adapter).run_once()['state'],'HOLD');self.assertEqual(adapter.calls,0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],1)
    def test_modified_source_marker_is_held(self):
        first=self.rpc('task_dispatch',self.args)
        self.db.execute("UPDATE model_request_bindings SET source_metadata_json=? WHERE request_id=?",('{"kind":"MODEL_DIRECT_V1"}',first['request_id']));self.db.commit()
        adapter=Adapter();self.assertEqual(self.scheduler(adapter,False).run_once()['state'],'HOLD');self.assertEqual(adapter.calls,0)
    def test_unknown_retry_is_fact_only(self):
        first=self.rpc('task_dispatch',self.args);adapter=Adapter();adapter.failure='TIMEOUT_UNKNOWN'
        self.assertEqual(self.scheduler(adapter).run_once()['state'],'UNKNOWN');self.assertEqual(adapter.calls,1)
        again=self.rpc('task_dispatch',self.args);self.assertTrue(again['duplicate']);self.assertEqual(again['state'],'UNKNOWN')
        self.assertEqual(again['request_id'],first['request_id']);self.assertEqual(self.scheduler(adapter).run_once()['state'],'IDLE');self.assertEqual(adapter.calls,1)

if __name__=='__main__':unittest.main()

class LegacyDirectProvenance(unittest.TestCase):
    def setUp(self):
        import test_model_orchestration as old
        self.f=old.ModelOrchestrationTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def test_legacy_no_connection_direct_request_remains_executable(self):
        self.f.assigned()
        queued=self.f.control.queue_request('demo-b','developer',[{'role':'user','content':'x'}],'legacy-direct')
        db=self.f.supervisor.db
        db.execute('UPDATE model_request_bindings SET source_metadata_json=NULL,source_metadata_mac=NULL WHERE request_id=?',(queued['request_id'],));db.commit()
        self.assertEqual(ModelScheduler(self.f.control).run_once()['state'],'SUCCEEDED')
    def test_legacy_no_connection_unknown_remains_no_replay(self):
        self.f.assigned(model='slow')
        queued=self.f.control.queue_request('demo-b','developer',[],'legacy-slow')
        db=self.f.supervisor.db
        db.execute('UPDATE model_request_bindings SET source_metadata_json=NULL,source_metadata_mac=NULL WHERE request_id=?',(queued['request_id'],));db.commit()
        self.assertEqual(ModelScheduler(self.f.control).run_once()['state'],'UNKNOWN')
        self.assertEqual(ModelScheduler(self.f.control).run_once()['state'],'IDLE')
