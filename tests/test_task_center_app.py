from __future__ import print_function

import json
import os
import shutil
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

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
                                  port=0)
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


if __name__ == '__main__':
    unittest.main()
