from __future__ import print_function

import json
import hashlib
import os
import shutil
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cryptography.fernet import Fernet

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys_path = os.path.join(ROOT, 'scripts')
import sys
sys.path.insert(0, sys_path)
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
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
                                  admin_token='test-admin-token-123456')
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
        self.assertEqual(status,200);self.assertIn(b'adminToken',body)


if __name__ == '__main__':
    unittest.main()
