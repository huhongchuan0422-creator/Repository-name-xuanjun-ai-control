"""Original RPC dispatch against isolated submit/worker fixtures."""
import json, unittest
import test_mcp_role_contract_delta as fixture
from task_center_mcp_service import MCPWorkerAdmission
from task_center_mcp_dispatch_host import dispatch_rpc
from model_orchestration import ModelScheduler
import test_mcp_worker_admission_delta as worker_fixture

class DispatchIntake(unittest.TestCase):
    def setUp(self):
        self.f=fixture.MCPIntakeDelta();self.f.setUp()
        self.first=json.loads(self.f.invoke()['result']['content'][0]['text'])
        self.task=self.first['task_id'];self.attempt='attempt-'+self.task[4:]
        self.db=self.f.f.control.db
        self.args={'task_id':self.task,'attempt_id':self.attempt,'role_id':'mcp-text-executor',
          'input_text':self.f.args['input_text'],'idempotency_key':self.f.args['idempotency_key'],
          'max_output_tokens':self.f.args['max_output_tokens']}
    def tearDown(self):self.f.tearDown()
    def rpc(self,name,args,enabled=True):
        value={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':name,'arguments':args}}
        result=dispatch_rpc(self.f.service,self.f.identity,self.f.cfg,value,enabled,role_contract=self.f.contract)
        return json.loads(result['result']['content'][0]['text'])
    def test_existing_assigned_dispatch_and_fake_worker_readback(self):
        assigned=self.rpc('task_assign_role',{k:self.args[k] for k in ('task_id','attempt_id','role_id')})
        self.assertTrue(assigned['duplicate'])
        sent=self.rpc('task_dispatch',self.args);again=self.rpc('task_dispatch',self.args)
        self.assertTrue(sent['duplicate']);self.assertEqual(sent['request_id'],again['request_id'])
        self.assertEqual(sent['request_id'],self.first['request_id'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
        adapter=worker_fixture.Adapter()
        scheduler=ModelScheduler(self.f.f.control,adapters={'openai-compatible':adapter},admission=MCPWorkerAdmission(self.f.contract,self.f.cfg))
        self.assertEqual(scheduler.run_once()['state'],'SUCCEEDED');self.assertEqual(adapter.calls,1)
        status=self.rpc('task_dispatch_status',{'task_id':self.task,'attempt_id':self.attempt,'request_id':sent['request_id']})
        self.assertEqual(status['request_state'],'SUCCEEDED');self.assertEqual(scheduler.run_once()['state'],'IDLE')
        self.assertEqual(adapter.calls,1)
    def test_scope_and_idempotency_and_worker_off(self):
        with self.assertRaisesRegex(ValueError,'MCP_DISPATCH_WORKER_DISABLED'):self.rpc('task_dispatch',self.args,False)
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_BINDING_CONFLICT'):self.rpc('task_dispatch',dict(self.args,input_text='changed'))
        self.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='mcp-text-executor'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'TASK_CONTRACT_UNKNOWN'):self.rpc('task_dispatch',self.args)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT state FROM model_requests').fetchone()[0],'HOLD')
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox WHERE task_id=? AND delivered_at IS NULL',(self.task,)).fetchone()[0],1)
    def test_missing_host_plan_holds_original_task_not_new_request(self):
        value={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'task_dispatch','arguments':self.args}}
        with self.assertRaisesRegex(ValueError,'MCP_WORKER_TRUSTED_PLAN_REQUIRED'):
            dispatch_rpc(self.f.service,self.f.identity,self.f.cfg,value,True,role_contract=None)
        self.assertEqual(self.db.execute('SELECT state FROM model_requests').fetchone()[0],'HOLD')
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox WHERE task_id=? AND delivered_at IS NULL',(self.task,)).fetchone()[0],1)
    def test_unknown_readback_does_not_replay(self):
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE request_id=?",(self.first['request_id'],));self.db.commit()
        result=self.rpc('task_dispatch',self.args)
        self.assertEqual(result['state'],'UNKNOWN');self.assertTrue(result['requires_effect_reconciliation'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)

if __name__=='__main__':unittest.main()
