from __future__ import print_function

import json
import hashlib
import os
import shutil
import tempfile
import threading
import unittest
import sqlite3
from unittest import mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cryptography.fernet import Fernet

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys_path = os.path.join(ROOT, 'scripts')
import sys
sys.path.insert(0, sys_path)
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
import task_center_app
from task_center_app import make_server
from task_supervisor import Supervisor


KEY = b'0123456789abcdef0123456789abcdef'


class TaskCenterAppTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, 'state.sqlite3')
        supervisor = Supervisor(self.db)
        authority = TestTenantAuthority(KEY)
        GatewayKernel(supervisor, authority).register_graph(
            authority.issue('tenant-ui', 'seed'), demo_graph('tenant-ui'))
        supervisor.close()
        self.server = make_server(self.db, KEY, 'tenant-ui', 'viewer',
                                  port=0,model_master_key=Fernet.generate_key(),
                                  admin_token='test-admin-token-123456',
                                  provider_connection_test_enabled=True)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.thread.join(2)
        shutil.rmtree(self.root)

    def get(self, path):
        response = urlopen(self.base + path, timeout=3)
        return response.status, response.headers, response.read()

    def post(self, value, expect_error=None):
        request = Request(self.base + '/api/admin/model-control', method='POST',
            data=json.dumps(value).encode('utf-8'), headers={
            'Content-Type':'application/json',
            'X-Test-Admin-Token':'test-admin-token-123456'})
        if expect_error:
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
            self.assertEqual(caught.exception.code, 400)
            body=json.loads(caught.exception.read().decode('utf-8'))
            self.assertIn(expect_error, body['detail'])
            return body
        return json.loads(urlopen(request, timeout=3).read().decode('utf-8'))

    def test_projection_is_rebuilt_from_same_sqlite_and_static_app_serves(self):
        status, headers, body = self.get('/api/projection')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        value = json.loads(body.decode('utf-8'))
        self.assertEqual(value['schema'], 3)
        self.assertEqual(value['tenant_id'], 'tenant-ui')
        self.assertEqual(len(value['tasks']), 3)
        self.assertTrue(all(t['process_state'] == 'UNKNOWN'
                            for t in value['tasks']))
        status, _, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn(b'id="dataMode"', body)

    def test_projection_get_is_read_only_with_active_wal(self):
        writer = Supervisor(self.db)
        writer.db.execute('PRAGMA wal_autocheckpoint=0')
        writer.db.execute("UPDATE tasks SET next_action='WAL_VISIBLE' WHERE task_id='demo-a'")
        writer.db.commit()
        wal = self.db + '-wal'
        self.assertTrue(os.path.exists(wal))
        before = {}
        for path in (self.db, wal):
            with open(path, 'rb') as stream:
                before[path] = hashlib.sha256(stream.read()).hexdigest()
        status, _, body = self.get('/api/projection')
        self.assertEqual(status, 200)
        projection = json.loads(body.decode('utf-8'))
        task = next(x for x in projection['tasks'] if x['task_id'] == 'demo-a')
        self.assertEqual(task['next_action'], 'WAL_VISIBLE')
        after = {}
        for path in (self.db, wal):
            with open(path, 'rb') as stream:
                after[path] = hashlib.sha256(stream.read()).hexdigest()
        self.assertEqual(before, after)
        writer.close()

    def test_projection_rejects_existing_database_with_missing_schema(self):
        other_db = os.path.join(self.root, 'empty.sqlite3')
        import sqlite3
        connection = sqlite3.connect(other_db)
        connection.execute('CREATE TABLE unrelated(value TEXT)')
        connection.commit(); connection.close()
        server = make_server(other_db, KEY, 'tenant-ui', 'viewer', port=0)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True; thread.start()
        try:
            with self.assertRaises(HTTPError) as caught:
                urlopen('http://127.0.0.1:%d/api/projection' %
                        server.server_port, timeout=3)
            self.assertEqual(caught.exception.code, 500)
            detail = json.loads(caught.exception.read().decode('utf-8'))
            self.assertIn('READ_SCHEMA_MISSING', detail['detail'])
        finally:
            server.shutdown(); server.server_close(); thread.join(2)

    def test_mutation_and_path_escape_are_rejected(self):
        with self.assertRaises(Exception):
            urlopen(Request(self.base + '/api/projection', data=b'{}',
                            method='POST'), timeout=3)
        with self.assertRaises(Exception):
            self.get('/../../etc/passwd')

    def test_non_loopback_bind_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'LOOPBACK'):
            make_server(self.db, KEY, 'tenant-ui', 'viewer',
                        host='0.0.0.0', port=0)

    def test_model_admin_api_is_server_backed_masked_and_authorized(self):
        with self.assertRaises(HTTPError) as denied:
            self.get('/api/admin/model-control')
        self.assertEqual(denied.exception.code,403)
        config={'provider_id':'p1','display_name':'Provider 1',
          'adapter_type':'siliconflow','base_url':'https://api.siliconflow.cn',
          'enabled':True,'price_state':'UNKNOWN','rate_limit_per_min':10,
          'concurrency_limit':2,'timeout_seconds':5,'retry_limit':1}
        body=json.dumps({'action':'UPSERT_PROVIDER','config':config,
                         'secret':'fixture-secret-value'}).encode('utf-8')
        req=Request(self.base+'/api/admin/model-control',data=body,method='POST',
          headers={'Content-Type':'application/json',
                   'X-Test-Admin-Token':'test-admin-token-123456'})
        created=json.loads(urlopen(req,timeout=3).read().decode('utf-8'))
        self.assertEqual(created['secret_mask'],'••••alue')
        req=Request(self.base+'/api/admin/model-control',headers={
          'X-Test-Admin-Token':'test-admin-token-123456'})
        projection=json.loads(urlopen(req,timeout=3).read().decode('utf-8'))
        encoded=json.dumps(projection,ensure_ascii=False)
        self.assertNotIn('fixture-secret-value',encoded)
        self.assertIn('••••alue',encoded)
        status,_,body=self.get('/admin.html')
        self.assertEqual(status,200);self.assertIn(b'sessionIdentity',body)

    def test_simple_provider_onboarding_http_chain_is_real_server_backed(self):
        secret='sk-ui-test-123456789'
        fake={'platform':'siliconflow','auth_state':'SUCCEEDED',
          'catalog_state':'RETRIEVED','model_callable_state':'UNVERIFIED_NO_INFERENCE',
          'models':['model-a','model-b'],'message_zh':'鉴权成功并已读取模型'}
        with mock.patch.object(task_center_app,'test_connection',return_value=fake):
            tested=self.post({'action':'TEST_PROVIDER_CONNECTION',
              'platform':'siliconflow','credential':secret})
        self.assertEqual(tested['auth_state'],'SUCCEEDED')
        self.assertIn('test_receipt',tested)
        called={'model_callable_state':'TESTED_SUCCEEDED','usage_state':'KNOWN',
          'usage':{'input_tokens':4,'output_tokens':1,'total_tokens':5},
          'provider_request_id':'fixture','call_receipt':'fixture-replaced',
          'message_zh':'模型真实调用成功'}
        # Use the real receipt issuer through the real helper while only the
        # outbound adapter result is isolated.
        from provider_onboarding import test_model as real_test_model
        class Adapter(object):
            def invoke(self,*args,**kwargs):return {'content':'OK','usage':{
              'input_tokens':4,'output_tokens':1,'total_tokens':5},
              'provider_request_id':'fixture'}
        def isolated_model(control,master,tenant,platform,credential,model,receipt,confirmed):
            return real_test_model(control,master,tenant,platform,credential,model,
              receipt,confirmed,Adapter())
        with mock.patch.object(task_center_app,'test_model',side_effect=isolated_model):
            called=self.post({'action':'TEST_PROVIDER_MODEL',
              'platform':'siliconflow','credential':secret,'model_id':'model-a',
              'test_receipt':tested['test_receipt'],'confirm_paid_test':True})
        saved=self.post({'action':'SAVE_PROVIDER_ONBOARDING',
          'platform':'siliconflow','connection_name':'默认连接',
          'credential':secret,'model_id':'model-a',
          'test_receipt':tested['test_receipt'],
          'call_receipt':called['call_receipt']})
        self.assertEqual(saved['configuration_state'],'SAVED')
        self.assertEqual(saved['model_callable_state'],'TESTED_SUCCEEDED')
        self.assertEqual(saved['paid_inference'],'NOT_EXECUTED')
        req=Request(self.base+'/api/admin/model-control',headers={
          'X-Test-Admin-Token':'test-admin-token-123456'})
        projection=json.loads(urlopen(req,timeout=3).read().decode('utf-8'))
        encoded=json.dumps(projection,ensure_ascii=False)
        self.assertNotIn(secret,encoded);self.assertIn('••••6789',encoded)
        self.assertEqual({x['platform'] for x in projection['provider_presets']},
          {'siliconflow','bailian','deepseek','openai','chatgpt'})

    def test_provider_connection_test_flag_is_separate_from_runtime_outbound(self):
        disabled=make_server(self.db,KEY,'tenant-ui','viewer',port=0,
          model_master_key=Fernet.generate_key(),
          admin_token='test-admin-token-123456',outbound_enabled=False,
          provider_connection_test_enabled=False)
        thread=threading.Thread(target=disabled.serve_forever);thread.daemon=True
        thread.start()
        try:
            request=Request('http://127.0.0.1:%d/api/admin/model-control'%
              disabled.server_port,method='POST',data=json.dumps({
              'action':'TEST_PROVIDER_CONNECTION','platform':'deepseek',
              'credential':'sk-test-only-123456'}).encode(),headers={
              'Content-Type':'application/json',
              'X-Test-Admin-Token':'test-admin-token-123456'})
            with self.assertRaises(HTTPError) as caught:urlopen(request,timeout=3)
            self.assertIn('PROVIDER_CONNECTION_TEST_DISABLED',
              caught.exception.read().decode())
        finally:
            disabled.shutdown();disabled.server_close();thread.join(2)

    def test_invalid_project_task_and_unprepared_dispatch_leave_zero_side_effects(self):
        bad={'project_id':'project-zero','task_id':'task-zero',
          'board_id':'research-development','delivery_stage':'implementation',
          'feature_unit':'gate','goal':'','scope':['WRITE_SOURCE'],
          'asset_version':'asset-v1','deliverables':['source'],
          'acceptance':['tests'],'dependencies':[],'priority':50,
          'owner':'developer'}
        self.post({'action':'CREATE_PROJECT_TASK','task':bad},'NONEMPTY_GOAL_REQUIRED')
        connection=sqlite3.connect(self.db)
        self.assertEqual(connection.execute(
          "SELECT count(*) FROM tasks WHERE task_id='task-zero'").fetchone()[0],0)
        unit_table=connection.execute("SELECT count(*) FROM sqlite_master "
          "WHERE type='table' AND name='execution_units'").fetchone()[0]
        if unit_table:
            self.assertEqual(connection.execute(
              "SELECT count(*) FROM execution_units WHERE task_id='task-zero'").fetchone()[0],0)
        connection.close()

        good=dict(bad);good['goal']='deliver bounded candidate'
        self.post({'action':'CREATE_PROJECT_TASK','task':good})
        self.post({'action':'START_TEST_ONLY_TASK','task_id':'task-zero',
          'attempt_id':'attempt-zero'},'AUTHENTICATED_ACTOR_REQUIRED')
        self.post({'action':'ASSIGN_ROLE','task_id':'task-zero',
          'role_id':'missing','role_version':'v1','principal_id':'developer'},
          'DISPATCH_PREFLIGHT_REQUIRED')
        self.post({'action':'QUEUE_REQUEST','task_id':'task-zero',
          'role_id':'missing','messages':[],'idempotency_key':'zero'},
          'DISPATCH_PREFLIGHT_REQUIRED')
        connection=sqlite3.connect(self.db)
        self.assertEqual(connection.execute(
          "SELECT count(*) FROM model_assignments WHERE task_id='task-zero'").fetchone()[0],0)
        self.assertEqual(connection.execute(
          "SELECT count(*) FROM model_requests WHERE task_id='task-zero'").fetchone()[0],0)
        connection.close()


if __name__ == '__main__':
    unittest.main()
