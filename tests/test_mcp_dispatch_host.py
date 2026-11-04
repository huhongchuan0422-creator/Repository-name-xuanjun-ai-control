import copy
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs,urlsplit
import base64
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from task_center_mcp_dispatch_host import validate_config,load_config,roles_for,check_existing_bindings
import test_task_center_mcp_http as fixture
from task_center_app import make_server
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestTenantAuthority,TestOnlyExecutor
from model_orchestration import ModelControl
from task_supervisor import Supervisor
from task_writer_fence import Fence


def config():
    return {'schema_version':1,'enabled':True,'bindings':[{
        'tenant_id':'tenant-mcp','principal_id':'owner-1','project_id':'project-mcp',
        'roles':{'developer':{'role_version':'v1','principal_id':'developer-1',
          'provider_id':'fixture','model_id':'fixture-chat','connection_id':'fixture-connection'}}}]}

class HostConfigTests(unittest.TestCase):
    def test_default_off_and_no_mutation(self):
        self.assertFalse(validate_config(None)['enabled'])
        original=config();out=validate_config(original);out['bindings'].clear()
        self.assertEqual(len(original['bindings']),1)
    def test_exact_binding_and_no_credentials_or_permissions(self):
        for key,value in [('enabled',1),('schema_version',True),('api_key','secret'),('bindings',[])]:
            with self.assertRaises(ValueError):validate_config(dict(config(),**{key:value}))
        bad=config();bad['bindings'][0]['roles']['developer']['allow_paid']=True
        with self.assertRaises(ValueError):validate_config(bad)
    def test_duplicate_binding_and_identity_mismatch(self):
        bad=config();bad['bindings']*=2
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):validate_config(bad)
        for key in ('tenant_id','principal_id','project_id'):
            identity={k:config()['bindings'][0][k] for k in ('tenant_id','principal_id','project_id')}
            identity[key]='other'
            self.assertIsNone(roles_for(config(),identity))
    def test_owned_file_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'config.json';p.write_text(json.dumps(config()));p.chmod(0o600)
            self.assertTrue(load_config(str(p))['enabled'])
            p.chmod(0o644)
            with self.assertRaises(ValueError):load_config(str(p))
            p.chmod(0o600);p.write_text('{"schema_version":1,"schema_version":1,"enabled":false,"bindings":[]}')
            with self.assertRaisesRegex(ValueError,'DUPLICATE'):load_config(str(p))

class OfflineProvider:
    calls=0
    def invoke(self,*args,**kwargs):
        type(self).calls+=1
        return {'content':'offline-host-result','usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2},'provider_request_id':'offline-host'}

class HostHTTPTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.MCPHTTPTests();self.f.setUp()
        self.f.server.mcp_worker.stop()
        self.f.server.shutdown();self.f.server.server_close();self.f.thread.join(2)
        self.supervisor=Supervisor(self.f.db)
        authority=TestTenantAuthority(fixture.KEY);self.gateway=GatewayKernel(self.supervisor,authority)
        self.context=authority.issue('tenant-mcp','admin:fixture')
        graph=demo_graph('tenant-mcp');graph['project_id']='project-mcp'
        self.gateway.register_graph(self.context,graph)
        self.fence=Fence(self.supervisor,os.path.join(self.f.root,'dispatch-locks'))
        TestOnlyExecutor(self.gateway,self.fence,self.context).start('demo-b','attempt-b',['fake:demo-b'],time.time()+600)
        self.control=ModelControl(self.gateway,self.context,self.f.master)
        self.control.record_task_spec('demo-b','bounded test',['result'],['offline receipt'])
        self.control.create_role({'role_id':'developer','version':'v1','phase':'EXECUTOR',
            'capabilities':['general'],'writer_allowed':True,'enabled':True,'review_kind':None})
        self.start_host(config(),False)
        OfflineProvider.calls=0;fixture.ModelFixture.calls=0
    def start_host(self,cfg,worker):
        self.f.server=make_server(self.f.db,fixture.KEY,'tenant-mcp','owner',port=0,
            model_master_key=self.f.master,identity_provider=self.f.identity,session_store=self.f.sessions,
            outbound_enabled=False,external_origin='https://'+fixture.HOST,base_path='/task-center-test/',
            mcp_enabled=True,mcp_model_worker_enabled=worker,mcp_dispatch_config=cfg,
            mcp_worker_adapters={'openai-compatible':OfflineProvider()})
        self.f.thread=threading.Thread(target=self.f.server.serve_forever);self.f.thread.daemon=True;self.f.thread.start()
        self.f.base='http://127.0.0.1:%d/task-center-test'%self.f.server.server_port
    def restart(self,cfg,worker=False):
        if self.f.server.mcp_worker:self.f.server.mcp_worker.stop()
        self.f.server.shutdown();self.f.server.server_close();self.f.thread.join(2)
        self.start_host(cfg,worker)
    def tearDown(self):
        if self.f.server.mcp_worker:self.f.server.mcp_worker.stop()
        self.fence.close();self.supervisor.close();self.f.tearDown()
    def token(self,scope='task:read task:submit',principal='owner-1'):
        store=self.f.oauth_store();redirect='https://chatgpt.com/connector_platform_oauth_redirect'
        client=store.register({'redirect_uris':[redirect],'grant_types':['authorization_code'],
            'response_types':['code'],'token_endpoint_auth_method':'none'})
        verifier='x'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        location=store.authorize({'principal_id':principal},{'response_type':'code','client_id':client['client_id'],
            'redirect_uri':redirect,'code_challenge':challenge,'code_challenge_method':'S256','state':'s',
            'resource':'https://'+fixture.HOST+'/task-center-test/mcp','scope':scope})
        return store.exchange({'grant_type':'authorization_code','code':parse_qs(urlsplit(location).query)['code'][0],
            'client_id':client['client_id'],'redirect_uri':redirect,'code_verifier':verifier,
            'resource':'https://'+fixture.HOST+'/task-center-test/mcp'})['access_token']
    def rpc(self,token,name=None,args=None):
        value={'jsonrpc':'2.0','id':1,'method':'tools/call' if name else 'tools/list'}
        if name:value['params']={'name':name,'arguments':args or {}}
        result=json.loads(self.f.request('/mcp','POST',json.dumps(value).encode(),
            {'Content-Type':'application/json','Authorization':'Bearer '+token}).read())
        if name:return json.loads(result['result']['content'][0]['text'])
        return result['result']['tools']
    def test_host_wiring_lists_only_bound_identity_and_default_off(self):
        token=self.token()
        self.assertIn('task_assign_role',[x['name'] for x in self.rpc(token)])
        other=self.token(principal='other')
        self.assertNotIn('task_assign_role',[x['name'] for x in self.rpc(other)])
        with self.assertRaises(HTTPError):self.rpc(other,'task_assign_role',{'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'})
        self.restart(None)
        self.assertNotIn('task_assign_role',[x['name'] for x in self.rpc(token)])
    def test_read_scope_cannot_reach_any_new_write_tool(self):
        token=self.token('task:read')
        for name in ('task_assign_role','task_dispatch','task_cancel_dispatch'):
            with self.assertRaises(HTTPError) as caught:self.rpc(token,name,{})
            self.assertEqual(caught.exception.code,401)
        self.assertEqual(self.control.db.execute('SELECT count(*) FROM model_assignments').fetchone()[0],0)
    def test_http_assign_then_worker_off_rejects_dispatch(self):
        token=self.token();identity={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        self.assertEqual(self.rpc(token,'task_assign_role',identity)['state'],'ASSIGNED')
        with self.assertRaises(HTTPError) as caught:
            self.rpc(token,'task_dispatch',dict(identity,input_text='bounded',idempotency_key='host-1',max_output_tokens=16))
        self.assertIn('MCP_DISPATCH_WORKER_DISABLED',caught.exception.read().decode())
        self.assertEqual(self.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)
        self.assertEqual(fixture.ModelFixture.calls,0)
    def test_http_queue_worker_result_and_default_off_rollback_preserves_ledger(self):
        self.restart(config(),True)
        token=self.token();identity={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        self.rpc(token,'task_assign_role',identity)
        args=dict(identity,input_text='bounded',idempotency_key='host-1',max_output_tokens=16)
        queued=self.rpc(token,'task_dispatch',args)
        self.assertTrue(self.rpc(token,'task_dispatch',args)['duplicate'])
        request={'task_id':'demo-b','attempt_id':'attempt-b','request_id':queued['request_id']}
        deadline=time.monotonic()+4
        while True:
            status=self.rpc(token,'task_dispatch_status',request)
            if status['request_state']=='SUCCEEDED':break
            self.assertLess(time.monotonic(),deadline);time.sleep(.05)
        self.assertEqual(status['canonical_task_state'],'STARTED')
        self.assertEqual(OfflineProvider.calls,1);self.assertEqual(fixture.ModelFixture.calls,0)
        self.restart(None)
        row=self.control.db.execute('SELECT state,attempts FROM model_requests WHERE request_id=?',(queued['request_id'],)).fetchone()
        self.assertEqual(tuple(row),('SUCCEEDED',1))
        self.assertNotIn('task_dispatch',[x['name'] for x in self.rpc(token)])
    def test_missing_existing_role_fails_before_listener(self):
        bad=config();bad['bindings'][0]['roles']['developer']['role_version']='absent'
        with self.assertRaisesRegex(ValueError,'MCP_EXISTING_ROLE_MODEL_CONNECTION_REQUIRED'):
            check_existing_bindings(self.f.db,bad)

    def test_http_scoped_cancel_is_durable_and_duplicate_safe(self):
        token=self.token();identity={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        self.rpc(token,'task_assign_role',identity)
        queued=self.control.queue_request('demo-b','developer',[{'role':'user','content':'cancel fixture'}],
            'cancel-host',16,'fixture-connection',expected_attempt_id='attempt-b',expected_project_id='project-mcp')
        request={'task_id':'demo-b','attempt_id':'attempt-b','request_id':queued['request_id']}
        self.assertEqual(self.rpc(token,'task_cancel_dispatch',request)['state'],'CANCELLED')
        self.assertTrue(self.rpc(token,'task_cancel_dispatch',request)['duplicate'])
        self.assertEqual(self.rpc(token,'task_dispatch_status',request)['request_state'],'CANCELLED')
        self.assertEqual(fixture.ModelFixture.calls,0)
        with self.assertRaises(HTTPError):
            self.rpc(token,'task_cancel_dispatch',dict(request,attempt_id='other'))

    def test_nonobject_rpc_parameters_reject_before_mutation(self):
        token=self.token()
        with self.assertRaises(HTTPError) as caught:
            self.f.request('/mcp','POST',json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':['task_dispatch']}).encode(),
                {'Content-Type':'application/json','Authorization':'Bearer '+token})
        self.assertEqual(caught.exception.code,400)
        self.assertEqual(self.control.db.execute('SELECT count(*) FROM model_requests').fetchone()[0],0)

if __name__=='__main__':unittest.main()
