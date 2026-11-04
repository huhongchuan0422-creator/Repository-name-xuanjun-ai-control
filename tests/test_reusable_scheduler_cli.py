from __future__ import print_function

import json
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
CLI = os.path.join(ROOT, 'scripts', 'reusable_scheduler_cli.py')
EXAMPLE = os.path.join(ROOT, 'examples',
                       'reusable-scheduler-task-graph.json')
KEY = '0123456789abcdef0123456789abcdef'


class SchedulerCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, 'state.sqlite3')

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_cli(self, *args):
        command = ['python3', CLI, '--db', self.db,
                   '--test-authority-key', KEY] + list(args)
        output = subprocess.check_output(command, cwd=ROOT)
        return json.loads(output.decode('utf-8'))

    def test_arbitrary_graph_register_project_and_export_ui(self):
        registered = self.run_cli(
            'register', '--tenant', 'tenant-demo', '--graph', EXAMPLE)
        self.assertFalse(registered['duplicate'])
        projection = self.run_cli('project', '--tenant', 'tenant-demo')
        self.assertEqual(projection['schema'], 3)
        self.assertEqual(len(projection['boards']), 7)
        self.assertEqual(len(projection['tasks']), 2)
        self.assertEqual(len(projection['anomalies']), 1)
        output = os.path.join(self.root, 'digital-twin-data.js')
        receipt = self.run_cli('export-ui', '--tenant', 'tenant-demo',
                               '--output', output)
        self.assertEqual(receipt['tasks'], 2)
        with open(output, 'r') as stream:
            body = stream.read()
        self.assertTrue(body.startswith('window.XUANJUN_TWIN_DATA = {'))
        self.assertIn('"production_status": "NOT_IMPLEMENTED"', body)

    def test_demo_restarts_to_identical_projection(self):
        first = self.run_cli('demo', '--tenant', 'tenant-a', '--lock-root',
                             os.path.join(self.root, 'locks'))
        second = self.run_cli('project', '--tenant', 'tenant-a')
        self.assertEqual(first, second)
        self.assertEqual(len(second['tasks']), 3)

    def test_app_demo_is_multi_project_dynamic_and_restart_rebuilds(self):
        first = self.run_cli('app-demo', '--tenant', 'tenant-app',
                             '--lock-root', os.path.join(self.root, 'locks'))
        second = self.run_cli('project', '--tenant', 'tenant-app')
        self.assertEqual(first, second)
        self.assertGreaterEqual(len({x['project_id'] for x in
                                    second['tasks']}), 4)
        states = {x['task_id']: x['runtime_status']
                  for x in second['tasks']}
        self.assertEqual(states['customer-failed'], 'FAILURE')
        self.assertEqual(states['finance-awaiting'],
                         'WAITING_AUTHORIZATION')
        self.assertEqual(states['ecosystem-waiting'],
                         'WAITING_DEPENDENCY')
        self.assertEqual(states['operations-unknown'], 'LIVENESS_UNKNOWN')


if __name__ == '__main__':
    unittest.main()
