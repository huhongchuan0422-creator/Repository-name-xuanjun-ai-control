from __future__ import print_function

import os
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from digital_twin_projection import build_projection


class DigitalTwinProjectionTests(unittest.TestCase):
    def fixture(self):
        tasks = [
            {'task_id':'task-a','project_id':'project-1','node_id':'node-1',
             'state':'RUNNING','runtime_status':'RUNNING','attempt_id':'a-1',
             'checkpoint_sha256':'a'*64,'input_version':'ui-v3',
             'last_real_progress_at':10,'effects_reconciled':'TRUE',
             'blocker':None},
            {'task_id':'task-b','project_id':'project-1','node_id':'node-2',
             'state':'READY','runtime_status':'WAITING_DEPENDENCY',
             'attempt_id':'b-1','checkpoint_sha256':'b'*64,
             'input_version':'ui-v3','last_real_progress_at':None,
             'effects_reconciled':'TRUE','blocker':'DEPENDENCY_WAIT'},
        ]
        return ({'tenant_id':'tenant-1','mode':'TEST_ONLY','observed_at':10,
                 'tasks':tasks,'timeline':[{'task_id':'task-a',
                   'attempt_id':'a-1','event_id':'event-progress',
                   'kind':'PROGRESS_EVIDENCED','observed_at':10,
                   'evidence_kind':'ARTIFACT','evidence_ref':'sha256:abc'}],
                 'integration_boundaries':[]},
                {'instances':[{'instance_id':'ai-1','role_id':'DEVELOPER',
                  'role_version':'v1','state':'ACTIVE','desired_state':'ACTIVE',
                  'current_request_id':'request-1','last_checkpoint_json':'{}',
                  'updated_at':10}],
                 'requests':[{'request_id':'request-1','task_id':'task-a',
                   'last_heartbeat':11}],
                 'assignments':[{'task_id':'task-a','attempt_id':'a-1',
                   'role_id':'DEVELOPER','role_version':'v1',
                   'principal_id':'ai-1','state':'ACTIVE','created_at':1}],
                 'candidates':[]})

    def test_same_records_drive_project_node_and_ai_views(self):
        value = build_projection(*self.fixture())
        self.assertEqual(value['views']['project_task_ids']['project-1'],
                         ['task-a','task-b'])
        self.assertEqual(value['views']['node_task_ids']['node-1'], ['task-a'])
        self.assertEqual(value['views']['ai_task_ids']['ai-1'], ['task-a'])
        self.assertEqual(len(value['records']['tasks']), 2)
        self.assertEqual(value['permissions']['mutation'], 'NONE')

    def test_animation_requires_real_execution_evidence(self):
        value = build_projection(*self.fixture())
        by_id = {item['task_id']:item for item in value['records']['tasks']}
        self.assertEqual(by_id['task-a']['display_state'], 'EXECUTING')
        self.assertTrue(by_id['task-a']['animation_allowed'])
        self.assertEqual(by_id['task-b']['display_state'], 'BLOCKED')
        self.assertFalse(by_id['task-b']['animation_allowed'])
        self.assertEqual(by_id['task-a']['heartbeat_state'], 'UNKNOWN')

    def test_missing_customer_install_and_liveness_stay_unknown(self):
        value = build_projection(*self.fixture())
        project = value['records']['projects'][0]
        instance = value['records']['ai_instances'][0]
        self.assertEqual(project['customer_id'], 'UNKNOWN')
        self.assertEqual(project['confirmed_version'], 'UNKNOWN')
        self.assertEqual(instance['session_id'], 'UNKNOWN')
        self.assertEqual(instance['process_id'], 'UNKNOWN')
        self.assertIn('P2_P3_INSTALL_RECEIPT_ADAPTER_NOT_CONNECTED',
                      value['gaps'])
        self.assertFalse(value['event_contract']['ai_may_confirm'])
        self.assertFalse(
            value['event_contract']['sent_ack_heartbeat_are_completion'])

    def test_interrupted_resume_is_not_reported_complete(self):
        task_projection, model_projection = self.fixture()
        task_projection['timeline'].append({
          'task_id':'task-a','attempt_id':'a-1','event_id':'resume-start',
          'kind':'RESUME_STARTED','observed_at':12,
          'evidence_kind':'RECEIPT','evidence_ref':'resume://start'})
        value = build_projection(task_projection, model_projection)
        task = next(item for item in value['records']['tasks']
                    if item['task_id'] == 'task-a')
        self.assertEqual(task['display_state'], 'RECOVERING')
        self.assertNotEqual(task['display_state'], 'COMPLETE')
