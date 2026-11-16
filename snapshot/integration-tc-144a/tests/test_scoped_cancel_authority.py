# -*- coding: utf-8 -*-
"""Direct boundary tests for real-actor scoped cancel authorization
(model_orchestration.request_cancel gate).  Canonical binding source only:
a non-admin principal may cancel its own task/attempt dispatch requests iff
the canonical model_assignments table already binds that exact principal to
that exact task/attempt.  Admin path unchanged; no fabricated admin, no
role/project widening, no new authority.
"""
import unittest

import test_mcp_dispatch_host as host
from model_orchestration import ModelControl


class ScopedCancelAuthorityTests(host.HostHTTPTests):
    # reuse the reviewed HTTP host fixture (admin chain) and add the real
    # bound actor control on the SAME canonical tenant/graph

    def _bind_developer(self):
        token = self.token()
        identity = {'task_id': 'demo-b', 'attempt_id': 'attempt-b',
                    'role_id': 'developer'}
        self.rpc(token, 'task_assign_role', identity)
        queued = self.control.queue_request(
            'demo-b', 'developer',
            [{'role': 'user', 'content': 'actor cancel fixture'}],
            'cancel-actor', 16, 'fixture-connection',
            expected_attempt_id='attempt-b', expected_project_id='project-mcp')
        return queued['request_id']

    def _actor_control(self, principal):
        context = self.gateway.tenants.issue('tenant-mcp', principal) \
            if hasattr(self.gateway.tenants, 'issue') else None
        if context is None:
            from reusable_task_gateway import TestTenantAuthority
            context = TestTenantAuthority(host.fixture.KEY).issue(
                'tenant-mcp', principal)
        return ModelControl(self.gateway, context, self.f.master)

    def test_bound_actor_can_cancel_own_scoped_request(self):
        request_id = self._bind_developer()
        actor = self._actor_control('developer-1')
        result = actor.request_cancel(request_id, expected_task_id='demo-b',
            expected_attempt_id='attempt-b',
            expected_project_id='project-mcp')
        self.assertEqual(result['state'], 'CANCELLED')
        self.assertTrue(result['cancel_requested'])
        audit = actor.db.execute('''SELECT principal_id FROM model_audit WHERE
            action='REQUEST_CANCEL' AND target_id=? ORDER BY observed_at DESC''',
            (request_id,)).fetchone()
        self.assertEqual(audit['principal_id'], 'developer-1')

    def test_duplicate_second_cancel_by_actor_is_state_guarded(self):
        request_id = self._bind_developer()
        actor = self._actor_control('developer-1')
        actor.request_cancel(request_id, expected_task_id='demo-b',
            expected_attempt_id='attempt-b',
            expected_project_id='project-mcp')
        with self.assertRaises(ValueError) as caught:
            actor.request_cancel(request_id, expected_task_id='demo-b',
                expected_attempt_id='attempt-b',
                expected_project_id='project-mcp')
        self.assertEqual(str(caught.exception), 'REQUEST_ALREADY_TERMINAL')

    def test_unbound_principal_is_rejected(self):
        request_id = self._bind_developer()
        stranger = self._actor_control('intruder-9')
        with self.assertRaises(ValueError) as caught:
            stranger.request_cancel(request_id, expected_task_id='demo-b',
                expected_attempt_id='attempt-b',
                expected_project_id='project-mcp')
        self.assertEqual(str(caught.exception), 'MODEL_ADMIN_REQUIRED')

    def test_bound_principal_wrong_attempt_is_rejected(self):
        request_id = self._bind_developer()
        actor = self._actor_control('developer-1')
        with self.assertRaises(ValueError) as caught:
            actor.request_cancel(request_id, expected_task_id='demo-b',
                expected_attempt_id='attempt-z',
                expected_project_id='project-mcp')
        self.assertEqual(str(caught.exception), 'MODEL_ADMIN_REQUIRED')

    def test_bound_principal_wrong_project_still_project_guarded(self):
        request_id = self._bind_developer()
        actor = self._actor_control('developer-1')
        with self.assertRaises(ValueError) as caught:
            actor.request_cancel(request_id, expected_task_id='demo-b',
                expected_attempt_id='attempt-b',
                expected_project_id='project-other')
        self.assertEqual(str(caught.exception), 'PROJECT_TASK_NOT_VISIBLE')

    def test_unscoped_nonadmin_cancel_still_requires_admin(self):
        request_id = self._bind_developer()
        actor = self._actor_control('developer-1')
        with self.assertRaises(ValueError) as caught:
            actor.request_cancel(request_id)
        self.assertEqual(str(caught.exception), 'MODEL_ADMIN_REQUIRED')

    def test_admin_path_is_byte_unchanged(self):
        request_id = self._bind_developer()
        result = self.control.request_cancel(request_id,
            expected_task_id='demo-b', expected_attempt_id='attempt-b',
            expected_project_id='project-mcp')
        self.assertEqual(result['state'], 'CANCELLED')


if __name__ == '__main__':
    unittest.main()
