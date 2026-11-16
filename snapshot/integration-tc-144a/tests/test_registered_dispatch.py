import importlib.util
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=ROOT
if not (BASE/'scripts/task_supervisor.py').is_file():
    BASE=ROOT.parents[1]/'mcp-db4a-review/unpacked/release'
sys.path.insert(0,str(BASE/'scripts'))
spec=importlib.util.spec_from_file_location('model_orchestration',ROOT/'scripts/model_orchestration.py')
core=importlib.util.module_from_spec(spec);sys.modules['model_orchestration']=core;spec.loader.exec_module(core)
spec=importlib.util.spec_from_file_location('dispatch_candidate',ROOT/'scripts/task_center_mcp.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('existing_model_tests',BASE/'tests/test_model_orchestration.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
from model_orchestration import ModelScheduler

class LocalProviderBoundary:
    calls=0
    def invoke(self,*args,**kwargs):
        self.calls+=1
        return {'content':'offline provider result; not executable code',
                'usage':{'input_tokens':3,'output_tokens':2,'total_tokens':5},
                'provider_request_id':'offline-boundary'}

class RegisteredDispatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ModelOrchestrationTests()
        self.fixture.setUp()
        f=self.fixture
        f.provider();f.model();f.role();f.qualify()
        f.control.set_quota_status('free','AVAILABLE','ISOLATED_TEST_ONLY',
                                  __import__('time').time(),None)
        self.binding={'developer':{'role_version':'v1','principal_id':'developer-1',
            'provider_id':'free','model_id':'ok','connection_id':None}}
        self.mcp=m.RegisteredTaskDispatchMCP(f.control,'demo-project',self.binding)
        self.identity={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        self.dispatch=dict(self.identity,input_text='test only',idempotency_key='dispatch-1',max_output_tokens=32)

    def tearDown(self):self.fixture.tearDown()

    def test_real_ledger_assignment_queue_worker_result_and_exactly_once(self):
        self.assertFalse(self.mcp.assign(self.identity)['duplicate'])
        self.assertTrue(self.mcp.assign(self.identity)['duplicate'])
        queued=self.mcp.dispatch(self.dispatch)
        self.assertEqual(queued['state'],'QUEUED')
        self.assertTrue(self.mcp.dispatch(self.dispatch)['duplicate'])
        provider=LocalProviderBoundary()
        scheduler=ModelScheduler(self.fixture.control,adapters={'openai-compatible':provider})
        result=scheduler.run_once()
        self.assertEqual(result['state'],'SUCCEEDED')
        self.assertEqual(scheduler.run_once()['state'],'IDLE')
        self.assertEqual(provider.calls,1)
        status=self.mcp.status({'task_id':'demo-b','attempt_id':'attempt-b','request_id':queued['request_id']})
        self.assertEqual(status['request_state'],'SUCCEEDED')
        self.assertEqual(status['canonical_task_state'],'STARTED')
        self.assertEqual(status['attempts'],1)
        self.assertIsNotNone(status['usage'])

    def test_cancel_is_persisted_idempotent_and_prevents_provider_call(self):
        self.mcp.assign(self.identity);queued=self.mcp.dispatch(self.dispatch)
        identity={'task_id':'demo-b','attempt_id':'attempt-b','request_id':queued['request_id']}
        self.assertEqual(self.mcp.cancel(identity)['state'],'CANCELLED')
        self.assertTrue(self.mcp.cancel(identity)['duplicate'])
        provider=LocalProviderBoundary()
        self.assertEqual(ModelScheduler(self.fixture.control,
            adapters={'openai-compatible':provider}).run_once()['state'],'IDLE')
        self.assertEqual(provider.calls,0)
        self.assertEqual(self.mcp.status(identity)['request_state'],'CANCELLED')

    def test_project_role_and_attempt_fail_closed(self):
        other=m.RegisteredTaskDispatchMCP(self.fixture.control,'other-project',self.binding)
        with self.assertRaisesRegex(ValueError,'PROJECT_TASK_NOT_VISIBLE'):other.assign(self.identity)
        with self.assertRaisesRegex(ValueError,'STALE_TASK_ATTEMPT'):
            self.mcp.assign(dict(self.identity,attempt_id='old'))
        with self.assertRaisesRegex(ValueError,'ROLE_NOT_ALLOWED_BY_HOST'):
            self.mcp.assign(dict(self.identity,role_id='admin'))
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_assignments').fetchone()[0],0)

    def test_idempotency_payload_token_and_identity_conflicts(self):
        self.mcp.assign(self.identity);self.mcp.dispatch(self.dispatch)
        for update in ({'input_text':'different'},{'max_output_tokens':33}, {'allow_paid':True}):
            with self.assertRaises(ValueError):self.mcp.dispatch(dict(self.dispatch,**update))
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)

    def test_no_assignment_or_stale_writer_cannot_dispatch(self):
        with self.assertRaisesRegex(ValueError,'CURRENT_TRUSTED_ASSIGNMENT_REQUIRED'):
            self.mcp.dispatch(self.dispatch)
        self.mcp.assign(self.identity)
        self.fixture.fence.begin_revocation('demo-b',{'role':'REVOCATION_CONTROLLER','caller_id':'test'})
        with self.assertRaisesRegex(ValueError,'CURRENT_WRITER_AUTHORITY_REQUIRED'):
            self.mcp.dispatch(self.dispatch)

    def test_cross_tenant_rejected_by_existing_gateway(self):
        from model_orchestration import ModelControl
        other=ModelControl(self.fixture.gateway,self.fixture.other,self.fixture.master)
        facade=m.RegisteredTaskDispatchMCP(other,'demo-project',self.binding)
        with self.assertRaisesRegex(ValueError,'CROSS_TENANT_ACCESS_REJECTED'):
            facade.assign(self.identity)

    def test_dependency_cannot_be_started_before_durable_ack(self):
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_CONSUMED_ACK_REQUIRED'):
            self.fixture.executor.start('demo-a','attempt-a',['fake:shared'],__import__('time').time()+600)

    def test_writer_change_between_preflight_and_commit_is_rejected(self):
        self.mcp.assign(self.identity)
        original=self.fixture.supervisor._task
        reads=[0]
        def changing_task(task_id):
            value=original(task_id);reads[0]+=1
            if reads[0]==3:
                import sqlite3
                other=sqlite3.connect(self.fixture.db)
                other.execute("UPDATE tasks SET authority_state='REVOKING' WHERE task_id='demo-b'")
                other.commit();other.close()
            return value
        self.fixture.supervisor._task=changing_task
        with self.assertRaisesRegex(ValueError,'WRITER_CHANGED_BEFORE_QUEUE_COMMIT'):
            self.mcp.dispatch(self.dispatch)
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)

    def test_registered_tools_are_opt_in_and_have_bounded_contracts(self):
        tools=self.mcp.rpc({'method':'tools/list','id':1})['result']['tools']
        self.assertEqual({x['name'] for x in tools},
            {'task_assign_role','task_dispatch','task_dispatch_status','task_cancel_dispatch'})
        for tool in tools:
            self.assertFalse(tool['inputSchema']['additionalProperties'])
            self.assertNotIn('principal_id',tool['inputSchema']['properties'])
            self.assertNotIn('allow_paid',tool['inputSchema']['properties'])

    def test_existing_durable_ack_unlocks_dependency_only_after_consumption(self):
        f=self.fixture
        f.executor.complete_success('demo-b','attempt-b','f'*64,
                                    [{'evidence_ref':'evid-demo-b'}])
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_CONSUMED_ACK_REQUIRED'):
            f.executor.start('demo-a','attempt-a',['fake:shared'],__import__('time').time()+600)
        outbox=f.gateway.db.execute("SELECT outbox_id,event_id FROM outbox WHERE task_id='demo-b'").fetchone()
        f.gateway.mark_outbox_sent(f.context,outbox['outbox_id'],'offline-transport-receipt')
        f.gateway.receive_outbox(f.context,outbox['outbox_id'])
        ack=f.gateway.acknowledge_event(f.context,'demo-b','attempt-b',outbox['event_id'])
        self.assertEqual(ack['state'],'CONSUMED_ACK')
        again=f.gateway.acknowledge_event(f.context,'demo-b','attempt-b',outbox['event_id'])
        self.assertTrue(again['duplicate'])
        f.executor.start('demo-a','attempt-a',['fake:shared'],__import__('time').time()+600)
        self.assertEqual(f.supervisor._task('demo-a')['state'],'STARTED')

    def test_lost_worker_remains_unknown_without_model_replay(self):
        self.mcp.assign(self.identity);queued=self.mcp.dispatch(self.dispatch)
        self.fixture.control.db.execute("UPDATE model_requests SET state='RUNNING',lease_owner='lost',lease_until=0,attempts=1 WHERE request_id=?",(queued['request_id'],))
        self.fixture.control.db.commit()
        provider=LocalProviderBoundary()
        scheduler=ModelScheduler(self.fixture.control,adapters={'openai-compatible':provider})
        self.assertEqual(scheduler.run_once()['state'],'IDLE')
        self.assertEqual(scheduler.run_once()['state'],'IDLE')
        status=self.mcp.status({'task_id':'demo-b','attempt_id':'attempt-b','request_id':queued['request_id']})
        self.assertEqual(status['request_state'],'UNKNOWN')
        self.assertEqual(status['error_kind'],'WORKER_LOST_SIDE_EFFECT_UNKNOWN')
        self.assertEqual(status['attempts'],1)
        self.assertEqual(provider.calls,0)

    def test_assignment_revocation_race_is_rejected_inside_transaction(self):
        original=self.fixture.supervisor._task
        reads=[0]
        def changing_task(task_id):
            value=original(task_id);reads[0]+=1
            if reads[0]==1:
                import sqlite3
                other=sqlite3.connect(self.fixture.db)
                other.execute("UPDATE tasks SET authority_state='REVOKING' WHERE task_id='demo-b'")
                other.commit();other.close()
            return value
        self.fixture.supervisor._task=changing_task
        with self.assertRaisesRegex(ValueError,'CURRENT_ADMITTED_WRITER_REQUIRED'):
            self.mcp.assign(self.identity)
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_assignments').fetchone()[0],0)

    def test_host_binding_change_before_queue_commit_is_rejected(self):
        self.mcp.assign(self.identity)
        original=self.fixture.supervisor._task
        reads=[0]
        def changing_task(task_id):
            value=original(task_id);reads[0]+=1
            if reads[0]==3:
                import sqlite3
                other=sqlite3.connect(self.fixture.db)
                other.execute("UPDATE model_assignments SET principal_id='not-host-principal' WHERE task_id='demo-b'")
                other.commit();other.close()
            return value
        self.fixture.supervisor._task=changing_task
        with self.assertRaisesRegex(ValueError,'ASSIGNMENT_CHANGED_BEFORE_QUEUE_COMMIT'):
            self.mcp.dispatch(self.dispatch)
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)

    def _move_project_from_second_connection(self):
        import sqlite3
        other=sqlite3.connect(self.fixture.db)
        other.execute("UPDATE gateway_task_metadata SET project_id='other-project' WHERE task_id='demo-b'")
        other.commit();other.close()

    def test_project_move_before_assign_commit_is_rejected(self):
        original=self.fixture.supervisor._task
        reads=[0]
        def changing(task_id):
            value=original(task_id);reads[0]+=1
            if reads[0]==1:self._move_project_from_second_connection()
            return value
        self.fixture.supervisor._task=changing
        with self.assertRaisesRegex(ValueError,'PROJECT_TASK_NOT_VISIBLE'):
            self.mcp.assign(self.identity)
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_assignments').fetchone()[0],0)

    def test_project_move_before_dispatch_commit_is_rejected(self):
        self.mcp.assign(self.identity)
        original=self.fixture.supervisor._task
        reads=[0]
        def changing(task_id):
            value=original(task_id);reads[0]+=1
            if reads[0]==3:self._move_project_from_second_connection()
            return value
        self.fixture.supervisor._task=changing
        with self.assertRaisesRegex(ValueError,'PROJECT_TASK_NOT_VISIBLE'):
            self.mcp.dispatch(self.dispatch)
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)

    def test_project_move_before_cancel_commit_is_rejected(self):
        self.mcp.assign(self.identity);queued=self.mcp.dispatch(self.dispatch)
        original=self.fixture.control.request_cancel
        def changing(*args,**kwargs):
            self._move_project_from_second_connection()
            return original(*args,**kwargs)
        self.fixture.control.request_cancel=changing
        with self.assertRaisesRegex(ValueError,'PROJECT_TASK_NOT_VISIBLE'):
            self.mcp.cancel({'task_id':'demo-b','attempt_id':'attempt-b','request_id':queued['request_id']})
        row=self.fixture.control.db.execute('SELECT state,cancel_requested FROM model_requests').fetchone()
        self.assertEqual(tuple(row),('QUEUED',0))

    def test_concurrent_idempotency_token_change_is_not_a_duplicate(self):
        self.mcp.assign(self.identity)
        original=self.fixture.control.queue_request
        def competing(*args,**kwargs):
            from task_supervisor import Supervisor
            from reusable_task_gateway import GatewayKernel
            from model_orchestration import ModelControl
            second=Supervisor(self.fixture.db)
            try:
                gateway=GatewayKernel(second,self.fixture.authority)
                control=ModelControl(gateway,self.fixture.context,self.fixture.master)
                control.queue_request('demo-b','developer',
                    [{'role':'user','content':'test only'}],'dispatch-1',33,
                    expected_attempt_id='attempt-b',expected_project_id='demo-project')
            finally:second.close()
            return original(*args,**kwargs)
        self.fixture.control.queue_request=competing
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_BINDING_CONFLICT'):
            self.mcp.dispatch(self.dispatch)
        row=self.fixture.control.db.execute('SELECT max_output_tokens FROM model_request_bindings').fetchone()
        self.assertEqual(row[0],33)
        self.assertEqual(self.fixture.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)

if __name__=='__main__':unittest.main()
