from __future__ import print_function

import json
import os
import shutil
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,HTTPServer

from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from connection_management import ConnectionManager
from model_orchestration import ModelControl,ModelScheduler,ProviderError
from provider_onboarding import ensure_schema as ensure_onboarding_schema
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from task_center_mcp_service import MCPTaskService,ensure_schema as ensure_mcp_schema
from task_supervisor import Supervisor,canonical


KEY=b'0123456789abcdef0123456789abcdef'


class ThreadServer(socketserver.ThreadingMixIn,HTTPServer):daemon_threads=True
class Fixture(BaseHTTPRequestHandler):
    calls=0
    def log_message(self,*_args):pass
    def do_POST(self):
        type(self).calls+=1
        length=int(self.headers.get('Content-Length','0'))
        value=json.loads(self.rfile.read(length).decode())
        body=json.dumps({'id':'mcp-fixture-result','choices':[{'message':{
          'content':'{"label":"safe","reason":"fixture"}'}}],
          'usage':{'prompt_tokens':8,'completion_tokens':4,
          'total_tokens':12}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers()
        self.wfile.write(body)


class MCPTaskServiceTests(unittest.TestCase):
    def setUp(self):
        Fixture.calls=0;self.root=tempfile.mkdtemp()
        self.db=os.path.join(self.root,'state.sqlite3');self.master=Fernet.generate_key()
        self.http=ThreadServer(('127.0.0.1',0),Fixture)
        self.thread=threading.Thread(target=self.http.serve_forever)
        self.thread.daemon=True;self.thread.start()
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY)
        gateway=GatewayKernel(supervisor,authority)
        context=authority.issue('tenant-mcp','admin:fixture')
        control=ModelControl(gateway,context,self.master)
        provider={'provider_id':'fixture','display_name':'Fixture',
          'adapter_type':'openai-compatible','base_url':'http://127.0.0.1:%d'%
          self.http.server_port,'enabled':True,'price_state':'KNOWN_FREE',
          'rate_limit_per_min':10,'concurrency_limit':1,'timeout_seconds':1,
          'retry_limit':0}
        control.upsert_provider(provider,'fixture-secret')
        control.set_quota_status('fixture','AVAILABLE','TEST_ONLY_LOCAL_FIXTURE',
                                 time.time(),None)
        control.upsert_model({'provider_id':'fixture','model_id':'fixture-chat',
          'capabilities':['general'],'enabled':True,'price_state':'KNOWN_FREE',
          'input_unit_cost':0,'output_unit_cost':0})
        manager=ConnectionManager(gateway,context,self.master)
        manager.upsert({'connection_id':'fixture-connection','provider_id':'fixture',
          'purpose':'MODEL_INFERENCE','auth_type':'API_KEY',
          'destination_origin':provider['base_url'],'issuer':None,
          'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False},'fixture-secret')
        control.register_benchmark_suite('mcp-v1',[{'case_id':'general-1',
          'capability':'general','messages':[{'role':'user','content':'classify'}],
          'expected_contains':'label'}])
        control.run_benchmark('fixture','fixture-chat','mcp-v1')
        ensure_onboarding_schema(supervisor.db)
        supervisor.db.execute('''INSERT INTO provider_onboarding_configs VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?)''',('tenant-mcp','fixture-platform',
          'fixture-connection','fixture','fixture-chat','SUCCEEDED','RETRIEVED',
          'TESTED_SUCCEEDED','fixture-chat',canonical(['fixture-chat']),'••••cret',
          time.time()))
        ensure_mcp_schema(supervisor.db)
        supervisor.db.commit();supervisor.close()
        self.service=MCPTaskService(self.db,KEY,'tenant-mcp',self.master,
          'owner-1','project-mcp')

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(2)
        shutil.rmtree(self.root)

    def submit_value(self):
        return {'project_id':'project-mcp','task_type':'TEXT_CLASSIFICATION',
          'input_text':'Classify: harmless greeting','idempotency_key':'idem-1',
          'connection_id':'fixture-connection','max_output_tokens':32}

    def test_submit_queue_execute_and_read_same_task_result(self):
        capabilities=self.service.capabilities()
        self.assertTrue(capabilities['connections'][0]['dispatch_ready'])
        first=self.service.submit(self.submit_value())
        duplicate=self.service.submit(self.submit_value())
        self.assertEqual(first['task_id'],duplicate['task_id'])
        self.assertTrue(duplicate['duplicate']);self.assertEqual(Fixture.calls,1)
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY)
        control=ModelControl(GatewayKernel(supervisor,authority),
          authority.issue('tenant-mcp','admin:worker'),self.master)
        executed=ModelScheduler(control,worker_id='fixture-worker').run_once()
        supervisor.close()
        self.assertEqual(executed['state'],'SUCCEEDED')
        result=self.service.result(first['task_id'])
        self.assertEqual(result['state'],'SUCCEEDED')
        self.assertEqual(result['result']['content'],
          '{"label":"safe","reason":"fixture"}')
        self.assertEqual(result['usage']['cost_state'],'KNOWN_ZERO')
        self.assertEqual(Fixture.calls,2) # benchmark + one task call
        self.assertEqual(self.service.status(first['task_id'])['request']['state'],
                         'SUCCEEDED')
        reconnected=MCPTaskService(self.db,KEY,'tenant-mcp',self.master,
          'owner-1','project-mcp')
        self.assertEqual(reconnected.result(first['task_id'])['state'],'SUCCEEDED')

    def test_timeout_unknown_is_persisted_and_requery_does_not_call_again(self):
        class TimeoutAdapter(object):
            calls=0
            def invoke(self,*_args,**_kwargs):
                self.calls+=1;raise ProviderError('TIMEOUT_UNKNOWN','timeout',False)
        submitted=self.service.submit(self.submit_value())
        adapter=TimeoutAdapter();supervisor=Supervisor(self.db)
        authority=TestTenantAuthority(KEY)
        control=ModelControl(GatewayKernel(supervisor,authority),
          authority.issue('tenant-mcp','admin:worker'),self.master)
        result=ModelScheduler(control,adapters={
          'openai-compatible':adapter},worker_id='fixture-worker').run_once()
        supervisor.close()
        self.assertEqual(result['state'],'UNKNOWN')
        self.assertEqual(self.service.result(submitted['task_id'])['state'],'UNKNOWN')
        self.assertEqual(self.service.result(submitted['task_id'])['state'],'UNKNOWN')
        self.assertEqual(adapter.calls,1)

    def test_project_scope_and_idempotency_conflict_are_rejected(self):
        bad=self.submit_value();bad['project_id']='other'
        with self.assertRaisesRegex(ValueError,'PROJECT_SCOPE'):
            self.service.submit(bad)
        self.service.submit(self.submit_value())
        changed=self.submit_value();changed['input_text']='different'
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
            self.service.submit(changed)
        changed=self.submit_value();changed['max_output_tokens']=31
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
            self.service.submit(changed)

    def test_failpoint_restart_resumes_one_binding_and_one_request(self):
        phases=('BINDING_PERSISTED','GRAPH_PERSISTED','CONTRACT_PERSISTED',
          'WRITER_STARTED','MODEL_ASSIGNED','QUEUED')
        for index,phase in enumerate(phases):
            with self.subTest(phase=phase):
                value=self.submit_value()
                value['idempotency_key']='recovery-%d'%index
                fired=[False]
                def fail_once(observed):
                    if observed==phase and not fired[0]:
                        fired[0]=True;raise RuntimeError('FAILPOINT_'+phase)
                interrupted=MCPTaskService(self.db,KEY,'tenant-mcp',self.master,
                  'owner-1','project-mcp',phase_hook=fail_once)
                with self.assertRaisesRegex(RuntimeError,'FAILPOINT_'+phase):
                    interrupted.submit(value)
                recovered=MCPTaskService(self.db,KEY,'tenant-mcp',self.master,
                  'owner-1','project-mcp').submit(value)
                self.assertEqual(recovered['state'],'QUEUED')
                supervisor=Supervisor(self.db)
                try:
                    binding=supervisor.db.execute('''SELECT task_id,request_id,
                      submit_state FROM mcp_task_bindings WHERE tenant_id=? AND
                      principal_id=? AND project_id=? AND idempotency_key=?''',(
                      'tenant-mcp','owner-1','project-mcp',
                      value['idempotency_key'])).fetchall()
                    self.assertEqual(len(binding),1)
                    self.assertEqual(binding[0]['submit_state'],'QUEUED')
                    count=supervisor.db.execute('''SELECT COUNT(*) FROM
                      model_requests WHERE tenant_id=? AND request_id=?''',(
                      'tenant-mcp',binding[0]['request_id'])).fetchone()[0]
                    self.assertEqual(count,1)
                finally:supervisor.close()


if __name__=='__main__':unittest.main()
