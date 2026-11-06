import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from task_center_real_blackbox import (BLACKBOX_CHECKS, INTEGRATION_CHECKS,
    RealAcceptanceGateway)


F = 'f' * 64
B = 'b' * 64
A = 'a' * 64


class RealBlackboxTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.gate = RealAcceptanceGateway(self.db, 'tenant-1', 'admin-1',
                                          clock=lambda: 1000)

    def tearDown(self):
        self.db.close()

    def plan(self, legacy=None, task='task-1'):
        return {
          'task_id': task,
          'project_template': ('COMMUNITY_REVENUE_SHARE_ADMIN' if legacy else
                               'STANDARD_WEB_APPLICATION'),
          'legacy_integration_state': legacy,
          'entrypoint': 'https://acceptance.example.test/admin',
          'environment': 'acceptance-cn-1',
          'frontend_commit': F, 'frontend_build': 'web-build-7',
          'frontend_app_version': 'app-7.0.0', 'backend_commit': B,
          'backend_image': 'registry/backend@sha256:' + A,
          'api_schema_version': 'openapi-7', 'artifact_sha256': A,
          'roles': {'frontend_owner': 'fe-1', 'backend_owner': 'be-1',
                    'integration_owner': 'integration-1',
                    'acceptance_owner': 'acceptor-1',
                    'release_owner': 'release-1'},
          'secret_refs': [{'secret_ref': 'secret://acceptance/session-key',
            'purpose': 'acceptance-session', 'environment': 'acceptance-cn-1',
            'isolation_scope': 'TENANT_AND_ENVIRONMENT',
            'isolation_proof_ref': 'evidence://isolation/proof-7'}]}

    def register(self, **kwargs):
        value = self.plan(**kwargs)
        return value, self.gate.register_plan(value)['plan_id']

    def make_run(self, plan, plan_id, gate_type, status, run_id, recheck=None,
            mismatch=None, evidence_kind='LIVE_HTTP_TRACE'):
        required = (INTEGRATION_CHECKS if gate_type ==
                    'FRONTEND_BACKEND_INTEGRATION' else BLACKBOX_CHECKS)
        value = {'run_id': run_id, 'plan_id': plan_id,
          'gate_type': gate_type, 'status': status,
          'responsible': plan['roles']['integration_owner' if gate_type ==
            'FRONTEND_BACKEND_INTEGRATION' else 'acceptance_owner'],
          'observed_at': str(1100 + len(run_id)),
          'entrypoint': plan['entrypoint'], 'environment': plan['environment'],
          'frontend_commit': plan['frontend_commit'],
          'frontend_build': plan['frontend_build'],
          'frontend_app_version': plan['frontend_app_version'],
          'backend_commit': plan['backend_commit'],
          'backend_image': plan['backend_image'],
          'api_schema_version': plan['api_schema_version'],
          'artifact_sha256': plan['artifact_sha256'],
          'checklist': [{'id': item, 'status': status,
                         'evidence_refs': ['evidence://' + run_id + '/' + item]}
                        for item in required],
          'evidence': [{'evidence_ref': 'evidence://' + run_id,
                        'kind': evidence_kind, 'source': 'real-browser-and-server',
                        'observed_at': '2026-11-06T12:00:00+08:00'}],
          'blockers': [] if status == 'PASS' else ['blocker://' + run_id],
          'recheck_of': recheck or []}
        if mismatch:
            value[mismatch] = 'different-version'
        return value

    def record(self, value):
        self.gate.principal_id = value['responsible']
        return self.gate.record_run(value)

    def test_four_states_are_append_only_and_pass_rechecks_latest_failure(self):
        plan, plan_id = self.register()
        previous = None
        for index, status in enumerate(('FAIL', 'BLOCKED', 'NOT_TESTED')):
            run_id = 'integration-%d' % index
            self.record(self.make_run(plan, plan_id,
                'FRONTEND_BACKEND_INTEGRATION', status, run_id,
                [previous] if previous else []))
            previous = run_id
        with self.assertRaisesRegex(ValueError,
                                    'FIX_REQUIRES_SAME_BINDING_RECHECK'):
            self.record(self.make_run(plan, plan_id,
                'FRONTEND_BACKEND_INTEGRATION', 'PASS', 'integration-pass'))
        self.record(self.make_run(plan, plan_id,
            'FRONTEND_BACKEND_INTEGRATION', 'PASS', 'integration-pass',
            [previous]))
        rows = self.db.execute('SELECT status FROM real_acceptance_runs').fetchall()
        self.assertEqual([x['status'] for x in rows],
                         ['FAIL', 'BLOCKED', 'NOT_TESTED', 'PASS'])

    def test_version_environment_and_substitute_evidence_fail_closed(self):
        plan, plan_id = self.register()
        for field in ('frontend_build', 'backend_image', 'api_schema_version',
                      'environment', 'artifact_sha256'):
            with self.assertRaisesRegex(ValueError,
                         'ACCEPTANCE_VERSION_OR_ENVIRONMENT_MISMATCH'):
                self.record(self.make_run(plan, plan_id,
                    'FRONTEND_BACKEND_INTEGRATION', 'PASS', 'bad-' + field,
                    mismatch=field))
        with self.assertRaisesRegex(ValueError, 'SUBSTITUTE_EVIDENCE_REJECTED'):
            self.record(self.make_run(plan, plan_id,
                'FRONTEND_BACKEND_INTEGRATION', 'PASS', 'mock',
                evidence_kind='API_MOCK'))

    def test_secret_isolation_required(self):
        plan = self.plan()
        plan['secret_refs'][0]['isolation_proof_ref'] = ''
        with self.assertRaisesRegex(ValueError, 'NONEMPTY_ISOLATION_PROOF_REF'):
            self.gate.register_plan(plan)
        plan = self.plan()
        plan['secret_refs'][0]['isolation_scope'] = 'SHARED'
        with self.assertRaisesRegex(ValueError, 'SECRET_ISOLATION_PROOF_REQUIRED'):
            self.gate.register_plan(plan)

    def test_authenticated_actor_must_be_named_gate_responsible(self):
        plan, plan_id = self.register()
        value = self.make_run(plan, plan_id,
            'FRONTEND_BACKEND_INTEGRATION', 'PASS', 'wrong-actor')
        with self.assertRaisesRegex(
                ValueError, 'AUTHENTICATED_GATE_RESPONSIBLE_REQUIRED'):
            self.gate.record_run(value)

    def test_integration_precedes_blackbox_and_release_needs_both_pass(self):
        plan, plan_id = self.register()
        with self.assertRaisesRegex(ValueError, 'INTEGRATION_GATE_NOT_PASS'):
            self.record(self.make_run(plan, plan_id,
                'PRODUCT_ACCEPTANCE_AI', 'PASS', 'blackbox-early'))
        self.record(self.make_run(plan, plan_id,
            'FRONTEND_BACKEND_INTEGRATION', 'PASS', 'integration-pass'))
        self.record(self.make_run(plan, plan_id,
            'PRODUCT_ACCEPTANCE_AI', 'PASS', 'blackbox-pass'))
        self.assertEqual(self.gate.release_gate(plan_id)['state'], 'PASS')

    def test_legacy_community_template_is_explicit_not_a_fake_pass(self):
        plan, plan_id = self.register(legacy='LEGACY_NOT_RETROFITTED')
        integration = self.gate.require_integration(plan_id)
        self.assertEqual(integration['state'], 'LEGACY_NOT_RETROFITTED')
        self.assertFalse(integration['pass'])
        projection = self.gate.projection()
        self.assertEqual(projection['community_template']['surface'],
                         'MANAGEMENT_BACKEND')
        self.assertEqual(projection['community_template'][
                         'mini_program_responsible'], '小新')
        self.assertFalse(projection['community_template'][
                         'mini_program_task_created'])

    def test_old_records_without_plan_remain_readable_and_not_upgraded(self):
        result = self.gate.require_task_release('historical-task')
        self.assertEqual(result['state'],
                         'LEGACY_RECORD_NO_REAL_ACCEPTANCE_PLAN')
        self.assertFalse(result['enforced'])
        self.gate.mark_task_required('new-task')
        with self.assertRaisesRegex(ValueError, 'REAL_ACCEPTANCE_PLAN_REQUIRED'):
            self.gate.require_task_release('new-task')


if __name__ == '__main__':
    unittest.main()
