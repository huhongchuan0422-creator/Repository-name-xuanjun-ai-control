"""Original MCP dispatcher with isolated providers; no production calls."""
import copy, json, time, unittest
import test_mcp_dispatch_host as fx
from task_center_mcp_service import MCPTaskService
from task_center_mcp_dispatch_host import dispatch_rpc, validate_config
from task_center_role_contract import RoleContractResolver

class MCPRoleDelta(unittest.TestCase):
    def setUp(self):
        self.f=fx.HostHTTPTests();self.f.setUp();f=self.f;c=f.control
        # Add a second isolated provider and role using the original fixture's
        # loopback-only model; no real credentials or customer data.
        provider={'provider_id':'fixture-b','display_name':'Fixture B','adapter_type':'openai-compatible',
          'base_url':'http://127.0.0.1:%d'%f.f.model.server_port,'enabled':True,'price_state':'KNOWN_FREE',
          'rate_limit_per_min':10,'concurrency_limit':1,'timeout_seconds':1,'retry_limit':0}
        c.upsert_provider(provider,'local-fixture');c.set_quota_status('fixture-b','AVAILABLE','TEST_ONLY_LOCAL_FIXTURE',time.time(),None)
        c.upsert_model({'provider_id':'fixture-b','model_id':'fixture-b-chat','capabilities':['general'],'enabled':True,'price_state':'KNOWN_FREE','input_unit_cost':0,'output_unit_cost':0})
        c.run_benchmark('fixture-b','fixture-b-chat','mcp-v1')
        c.create_role({'role_id':'designer','version':'v1','phase':'EXECUTOR','capabilities':['general'],'writer_allowed':True,'enabled':True,'review_kind':None})
        self.cfg=fx.config();self.cfg['bindings'][0]['roles']['designer']={'role_version':'v1','principal_id':'designer-1','provider_id':'fixture-b','model_id':'fixture-b-chat','connection_id':'unused-fixture-b'}
        self.cfg=validate_config(self.cfg)
        spec=c.db.execute("SELECT spec_sha256 FROM tasks WHERE task_id='demo-b'").fetchone()[0]
        def policy(role,provider,required,na):
            return {'contract_id':'contract-'+role,'contract_version':1,'tenant_id':'tenant-mcp','project_id':'project-mcp','task_id':'demo-b','attempt_id':'attempt-b','task_spec_sha256':spec,'role_id':role,'role_version':'v1','role_scope':['general'],'provider_id':provider,'required_categories':required,'not_applicable':na}
        self.dev=policy('developer','fixture',['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT','INSTALL','SOURCE'],{})
        self.ui=policy('designer','fixture-b',['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT'],{'SOURCE':'NON_SOURCE_WORK_PRODUCT','INSTALL':'NO_INSTALLATION_SCOPE'})
        self.contract=RoleContractResolver(c.db,[self.dev,self.ui])
        self.service=MCPTaskService(f.f.db,fx.fixture.KEY,'tenant-mcp',f.f.master,'owner-1','project-mcp',execution_enabled=True)
        self.identity={'tenant_id':'tenant-mcp','principal_id':'owner-1','project_id':'project-mcp','scopes':['task:read','task:submit']}
    def tearDown(self):self.f.tearDown()
    def rpc(self,name,args,role_contract=True):
        value={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}}
        result=dispatch_rpc(self.service,self.identity,self.cfg,value,True,role_contract=self.contract if role_contract else None)
        return json.loads(result['result']['content'][0]['text'])
    def test_two_roles_can_be_assigned_before_artifact_exists(self):
        for role in ('developer','designer'):
            args={'task_id':'demo-b','attempt_id':'attempt-b','role_id':role}
            self.assertEqual(self.rpc('task_assign_role',args)['state'],'ASSIGNED')
            self.assertTrue(self.rpc('task_assign_role',args)['duplicate'])
        rows=self.f.control.db.execute("SELECT action,detail_json FROM model_audit WHERE action='ROLE_CONTRACT_PLANNED' ORDER BY detail_json").fetchall()
        self.assertEqual(len(rows),2)
        values=[json.loads(row['detail_json']) for row in rows]
        self.assertEqual({v['provider_id'] for v in values},{'fixture','fixture-b'})
        self.assertIn('SOURCE',next(v for v in values if v['provider_id']=='fixture')['required_categories'])
        self.assertNotIn('SOURCE',next(v for v in values if v['provider_id']=='fixture-b')['required_categories'])
    def test_protected_http_routes_reach_original_role_assignment(self):
        from connection_management import ConnectionManager
        from task_center_handoff_host import HandoffHost,HostAuthAdapter
        from task_center_app import make_server
        import threading
        class HostAdapter(HostAuthAdapter):pass
        f=self.f
        ConnectionManager(f.gateway,f.context,f.f.master).upsert({
          'connection_id':'unused-fixture-b','provider_id':'fixture-b',
          'purpose':'MODEL_INFERENCE','auth_type':'API_KEY',
          'destination_origin':'http://127.0.0.1:%d'%f.f.model.server_port,
          'issuer':None,'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False},'local-fixture')
        f.f.server.shutdown();f.f.server.server_close();f.f.thread.join(2)
        host=HandoffHost(f.supervisor.db,'tenant-mcp','formal-fixture',HostAdapter(),mcp_config=self.cfg,role_contract=self.contract)
        f.f.server=make_server(f.f.db,fx.fixture.KEY,'tenant-mcp','owner',port=0,
            model_master_key=f.f.master,identity_provider=f.f.identity,session_store=f.f.sessions,
            outbound_enabled=False,external_origin='https://'+fx.fixture.HOST,base_path='/task-center-test/',
            mcp_enabled=True,mcp_model_worker_enabled=False,mcp_dispatch_config=self.cfg,handoff_host=host)
        f.f.thread=threading.Thread(target=f.f.server.serve_forever);f.f.thread.daemon=True;f.f.thread.start()
        f.f.base='http://127.0.0.1:%d/task-center-test'%f.f.server.server_port
        auth=f.token()
        for role in ('developer','designer'):
            result=f.rpc(auth,'task_assign_role',{'task_id':'demo-b','attempt_id':'attempt-b','role_id':role})
            self.assertEqual(result['state'],'ASSIGNED')

    def test_planned_contract_and_assignment_rollback_together(self):
        self.f.control.db.execute("UPDATE model_quota_status SET quota_state='UNKNOWN' WHERE provider_id='fixture'");self.f.control.db.commit()
        args={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        with self.assertRaises(ValueError):self.rpc('task_assign_role',args)
        self.assertEqual(self.f.control.db.execute("SELECT count(*) FROM model_audit WHERE action='ROLE_CONTRACT_PLANNED'").fetchone()[0],0)
        self.assertEqual(self.f.control.db.execute('SELECT count(*) FROM model_assignments').fetchone()[0],0)

    def test_unknown_contract_and_unconnected_execution_hold(self):
        args={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        with self.assertRaisesRegex(ValueError,'TASK_CONTRACT_UNKNOWN'):self.rpc('task_assign_role',args,False)
        self.assertEqual(self.f.control.db.execute('SELECT count(*) FROM model_assignments').fetchone()[0],0)
        self.assertEqual(self.rpc('task_assign_role',args)['state'],'ASSIGNED')
        with self.assertRaisesRegex(ValueError,'TASK_BACKUP_EVIDENCE_NOT_CONNECTED'):
            self.rpc('task_dispatch',dict(args,input_text='local',idempotency_key='mcp-role-test',max_output_tokens=8))
        self.assertEqual(self.f.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)
        with self.assertRaisesRegex(ValueError,'EXACT_MCP_SUBMIT_REQUIRED'):
            self.rpc('task_submit',{})

    def test_submit_identity_scope_contract_holds_before_persistence(self):
        args={'project_id':'project-mcp','task_type':'TEXT_CLASSIFICATION',
              'input_text':'fixture','idempotency_key':'intake-fixture',
              'connection_id':'fixture-connection','max_output_tokens':8}
        value={'jsonrpc':'2.0','id':1,'method':'tools/call',
               'params':{'name':'task_submit','arguments':args}}
        db=self.f.control.db
        before=db.execute('SELECT count(*) FROM mcp_task_bindings').fetchone()[0]
        cases=[(dict(self.identity,scopes=['task:read']),self.contract,'MCP_SUBMIT_SCOPE_REQUIRED'),
               (dict(self.identity,principal_id='other'),self.contract,'MCP_SUBMIT_IDENTITY_MISMATCH'),
               (self.identity,None,'TASK_CONTRACT_UNKNOWN'),
               (self.identity,self.contract,'TASK_CONTRACT_UNKNOWN')]
        for identity,contract,error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError,error):
                dispatch_rpc(self.service,identity,self.cfg,value,True,role_contract=contract)
            self.assertEqual(db.execute('SELECT count(*) FROM mcp_task_bindings').fetchone()[0],before)

class MCPIntakeDelta(unittest.TestCase):
    def setUp(self):
        self.f=fx.HostHTTPTests();self.f.setUp();f=self.f
        from task_center_mcp_service import ROLE_ID,ROLE_VERSION
        from task_supervisor import canonical
        import hashlib
        f.control.create_role({'role_id':ROLE_ID,'version':ROLE_VERSION,'phase':'EXECUTOR',
            'capabilities':['general'],'writer_allowed':True,'enabled':True,'review_kind':None})
        self.service=MCPTaskService(f.f.db,fx.fixture.KEY,'tenant-mcp',f.f.master,'owner-1','project-mcp',execution_enabled=True)
        self.args={'project_id':'project-mcp','task_type':'TEXT_CLASSIFICATION','input_text':'fixture text',
                   'idempotency_key':'intake-fixture','connection_id':'fixture-connection','max_output_tokens':8}
        task,attempt,spec=self.service.intake_identity_spec(self.args)
        contract={'contract_id':'intake-fixture','contract_version':1,'tenant_id':'tenant-mcp',
          'project_id':'project-mcp','task_id':task,'attempt_id':attempt,
          'task_spec_sha256':hashlib.sha256(canonical(spec).encode()).hexdigest(),
          'role_id':ROLE_ID,'role_version':ROLE_VERSION,'role_scope':['general'],'provider_id':'fixture',
          'required_categories':['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT'],
          'not_applicable':{'SOURCE':'NON_SOURCE_WORK_PRODUCT','INSTALL':'NO_INSTALLATION_SCOPE'}}
        plan={'contract_id':'intake-fixture','principal_id':'owner-1','connection_id':'fixture-connection','execution_entry':'model-scheduler-runtime'}
        self.contract=RoleContractResolver(f.supervisor.db,[contract],[plan])
        self.cfg=fx.config();self.cfg['bindings'][0]['roles'][ROLE_ID]={'role_version':ROLE_VERSION,
            'principal_id':'mcp-worker','provider_id':'fixture','model_id':'fixture-chat','connection_id':'fixture-connection'}
        self.cfg=validate_config(self.cfg)
        self.identity={'tenant_id':'tenant-mcp','principal_id':'owner-1','project_id':'project-mcp','scopes':['task:read','task:submit']}
        self.value={'jsonrpc':'2.0','id':17,'method':'tools/call','params':{'name':'task_submit','arguments':self.args}}
    def tearDown(self):self.f.tearDown()
    def invoke(self,contract=None,identity=None,service=None,value=None):
        return dispatch_rpc(service or self.service,identity or self.identity,self.cfg,value or self.value,True,role_contract=contract or self.contract)
    def test_rpc_prewrite_rejections_and_checkpoint_resume(self):
        db=self.f.control.db
        def count():return db.execute('SELECT count(*) FROM mcp_task_bindings').fetchone()[0]
        for identity,contract,err in [(dict(self.identity,scopes=['task:read']),self.contract,'MCP_SUBMIT_SCOPE_REQUIRED'),
           (dict(self.identity,project_id='other'),self.contract,'MCP_SUBMIT_IDENTITY_MISMATCH'),
           (self.identity,RoleContractResolver(db,[]),'TASK_CONTRACT_UNKNOWN'),
           (self.identity,RoleContractResolver(db,self.contract.contracts,[dict(self.contract.intake_plans[0],execution_entry='missing')]),'TASK_INTAKE_ENTRY_REQUIRED')]:
            with self.subTest(err=err),self.assertRaisesRegex(ValueError,err):self.invoke(contract,identity)
            self.assertEqual(count(),0)
        bad=dict(self.value,params={'name':'task_submit','arguments':dict(self.args,project_id='other')})
        with self.assertRaisesRegex(ValueError,'MCP_PROJECT_SCOPE_REJECTED'):self.invoke(value=bad)
        self.assertEqual(count(),0)
        no_permission=RoleContractResolver(db,self.contract.contracts,[])
        with self.assertRaisesRegex(ValueError,'TASK_INTAKE_PERMISSION_REQUIRED'):self.invoke(contract=no_permission)
        self.assertEqual(count(),0)
        def fail(phase):
            if phase=='GRAPH_PERSISTED':raise RuntimeError('fixture failpoint')
        disabled=MCPTaskService(self.f.f.db,fx.fixture.KEY,'tenant-mcp',self.f.f.master,'owner-1','project-mcp',execution_enabled=False)
        with self.assertRaisesRegex(ValueError,'MCP_MODEL_OUTBOUND_DISABLED'):self.invoke(service=disabled)
        self.assertEqual(count(),0)
        self.service.phase_hook=fail
        with self.assertRaisesRegex(RuntimeError,'fixture failpoint'):self.invoke()
        self.service.phase_hook=None
        first=json.loads(self.invoke()['result']['content'][0]['text'])
        second=json.loads(self.invoke()['result']['content'][0]['text'])
        self.assertEqual(first['task_id'],second['task_id']);self.assertTrue(second['duplicate'])
        self.assertEqual(count(),1)
        self.assertEqual(db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
        self.assertEqual(fx.fixture.ModelFixture.calls,0) # no worker provider calls
    def test_http_submit_with_trusted_fixture_plan_and_worker_stopped(self):
        from task_center_handoff_host import HandoffHost,HostAuthAdapter
        from task_center_app import make_server
        import threading
        f=self.f
        class Adapter(HostAuthAdapter):pass
        f.f.server.shutdown();f.f.server.server_close();f.f.thread.join(2)
        host=HandoffHost(f.supervisor.db,'tenant-mcp','fixture',Adapter(),mcp_config=self.cfg,role_contract=self.contract)
        f.f.server=make_server(f.f.db,fx.fixture.KEY,'tenant-mcp','owner',port=0,model_master_key=f.f.master,
          identity_provider=f.f.identity,session_store=f.f.sessions,outbound_enabled=False,
          external_origin='https://'+fx.fixture.HOST,base_path='/task-center-test/',mcp_enabled=True,
          mcp_model_worker_enabled=True,mcp_dispatch_config=self.cfg,handoff_host=host)
        f.f.server.mcp_worker.stop()
        f.f.thread=threading.Thread(target=f.f.server.serve_forever,daemon=True);f.f.thread.start()
        f.f.base='http://127.0.0.1:%d/task-center-test'%f.f.server.server_port
        token=f.token()
        from urllib.error import HTTPError
        bad={'jsonrpc':'2.0','id':18,'method':'tools/call','params':{'name':'task_submit',
             'arguments':dict(self.args,project_id='other')}}
        with self.assertRaises(HTTPError) as failure:
            f.f.request('/mcp','POST',json.dumps(bad).encode(),
              {'Content-Type':'application/json','Authorization':'Bearer '+token})
        error=json.loads(failure.exception.read())
        self.assertEqual(error['error_description'],'MCP_PROJECT_SCOPE_REJECTED')
        self.assertEqual(error['supervisory_alert'],'NOT_DELIVERED')
        self.assertEqual(len(error['request_ref']),32)
        self.assertEqual(f.control.db.execute('SELECT count(*) FROM mcp_task_bindings').fetchone()[0],0)
        first=f.rpc(token,'task_submit',self.args);second=f.rpc(token,'task_submit',self.args)
        self.assertEqual(first['task_id'],second['task_id']);self.assertTrue(second['duplicate'])
        self.assertEqual(f.control.db.execute('SELECT count(*) FROM mcp_task_bindings').fetchone()[0],1)
        self.assertEqual(f.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],1)
        self.assertEqual(fx.fixture.ModelFixture.calls,0)

if __name__=='__main__':unittest.main()
