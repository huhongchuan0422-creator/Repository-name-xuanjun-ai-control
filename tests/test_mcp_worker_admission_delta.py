"""Isolated model worker admission; no external model is called."""
import json, unittest
import test_mcp_role_contract_delta as intake_fixture
from task_center_mcp_service import MCPWorkerAdmission
from model_orchestration import ModelScheduler, ProviderError

class Adapter:
    calls=0
    failure=None
    def invoke(self,*args):
        self.calls+=1
        if self.failure:raise ProviderError(self.failure,'fixture',False)
        return {'content':'fixture','usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2},'provider_request_id':'fixture'}

class WorkerAdmission(unittest.TestCase):
    def setUp(self):
        self.fixture=intake_fixture.MCPIntakeDelta();self.fixture.setUp();self.f=self.fixture
        result=json.loads(self.f.invoke()['result']['content'][0]['text'])
        self.request=result['request_id'];self.task=result['task_id']
        self.db=self.f.f.control.db;self.adapter=Adapter()
        self.admission=MCPWorkerAdmission(self.f.contract,self.f.cfg)
    def tearDown(self):self.fixture.tearDown()
    def run_worker(self,admission=True):
        return ModelScheduler(self.f.f.control,adapters={'openai-compatible':self.adapter},
                              admission=self.admission if admission else None).run_once()
    def test_valid_once_and_duplicate_does_not_call(self):
        result=self.run_worker();self.assertEqual(result['state'],'SUCCEEDED')
        self.assertEqual(self.adapter.calls,1);self.assertEqual(self.run_worker()['state'],'IDLE')
        self.assertEqual(self.adapter.calls,1)
    def assert_hold(self):
        self.assertEqual(self.run_worker()['state'],'HOLD');self.assertEqual(self.adapter.calls,0)
        self.assertEqual(self.db.execute('SELECT state FROM model_requests WHERE request_id=?',(self.request,)).fetchone()[0],'HOLD')
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox WHERE task_id=? AND delivered_at IS NULL',(self.task,)).fetchone()[0],1)
    def test_role_disabled(self):
        self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='mcp-text-executor'");self.db.commit();self.assert_hold()
    def test_scope_changed(self):
        self.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='mcp-text-executor'");self.db.commit();self.assert_hold()
    def test_connection_lost(self):
        self.db.execute("UPDATE service_connections SET status='REAUTH_REQUIRED' WHERE connection_id='fixture-connection'");self.db.commit();self.assert_hold()
    def test_attempt_expired(self):
        self.db.execute('UPDATE tasks SET authority_valid_until=0 WHERE task_id=?',(self.task,));self.db.commit();self.assert_hold()
    def test_final_guard_drift_no_provider_call(self):
        original=self.admission.check;calls=[]
        def check(db,row,now):
            calls.append(1)
            if len(calls)==2:
                db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='mcp-text-executor'")
            return original(db,row,now)
        self.admission.check=check
        self.assert_hold();self.assertEqual(len(calls),2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM model_call_reservations WHERE request_id=? AND state='ACTIVE'",(self.request,)).fetchone()[0],0)
    def test_explicit_no_call_reauthorization_keeps_one_request(self):
        self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='mcp-text-executor'");self.db.commit()
        self.assert_hold()
        scheduler=ModelScheduler(self.f.f.control,adapters={'openai-compatible':self.adapter},admission=self.admission)
        with self.assertRaises(ValueError):scheduler.resume_mcp_no_call_hold(self.request)
        self.db.execute("UPDATE role_templates SET enabled=1 WHERE role_id='mcp-text-executor'");self.db.commit()
        self.assertEqual(scheduler.resume_mcp_no_call_hold(self.request)['state'],'QUEUED')
        self.assertEqual(scheduler.run_once()['state'],'SUCCEEDED');self.assertEqual(self.adapter.calls,1)
        self.assertEqual(scheduler.run_once()['state'],'IDLE');self.assertEqual(self.adapter.calls,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
    def test_unknown_is_not_eligible_for_no_call_resume(self):
        self.adapter.failure='TIMEOUT_UNKNOWN';self.assertEqual(self.run_worker()['state'],'UNKNOWN')
        scheduler=ModelScheduler(self.f.f.control,adapters={'openai-compatible':self.adapter},admission=self.admission)
        with self.assertRaisesRegex(ValueError,'MCP_NO_CALL_HOLD_REQUIRED'):scheduler.resume_mcp_no_call_hold(self.request)
        self.assertEqual(self.adapter.calls,1)
    def test_missing_host_plan_fails_closed(self):
        self.assertEqual(self.run_worker(False)['state'],'HOLD');self.assertEqual(self.adapter.calls,0)
    def test_timeout_unknown_never_replays(self):
        self.adapter.failure='TIMEOUT_UNKNOWN'
        self.assertEqual(self.run_worker()['state'],'UNKNOWN');self.assertEqual(self.adapter.calls,1)
        self.assertEqual(self.run_worker()['state'],'IDLE');self.assertEqual(self.adapter.calls,1)

if __name__=='__main__':unittest.main()
