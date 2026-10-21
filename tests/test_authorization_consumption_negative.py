"""Original community boundary negatives while PR122 wire contract is pending.

No proposed request/response fields are introduced here. Caller/audience,
request/operation/expiry, mapping revision and remote UNKNOWN reconciliation
must be tested against the frozen PR122 contract, not fabricated envelopes.
"""
import unittest
from unittest.mock import patch
import test_community_center_operations as original


class ConsumptionBoundaryNegatives(unittest.TestCase):
    def setUp(self):
        self.fixture = original.ExistingCenterOperations()
        self.fixture.setUp()
        self.center = self.fixture.fx.center
        self.runtime = self.fixture.fx.stage.api

    def tearDown(self):
        self.fixture.tearDown()

    def assert_no_business_call(self, exception, action):
        before = self.center.check_integrity()
        with patch.object(self.runtime, 'dispatch', wraps=self.runtime.dispatch) as dispatch:
            with self.assertRaises(exception):
                action()
            dispatch.assert_not_called()
        self.assertEqual(self.center.check_integrity(), before)

    def test_valid_project_owner_cannot_supply_another_tenant(self):
        grant = self.fixture.operations.grants['staff']
        grant['tenant'] = 'different_tenant'
        # A valid OWNER/session does not override the community tenant binding.
        self.assert_no_business_call(PermissionError, self.fixture.call)

    def test_valid_session_cannot_redirect_protected_grant_to_another_project(self):
        self.fixture.operations.grants['staff']['project'] = 'unadmitted_project'
        self.assert_no_business_call(PermissionError, self.fixture.call)

    def test_store_binding_drift_blocks_before_original_runtime(self):
        self.runtime.bindings[self.fixture.staff]['store_id'] = 'different_store'
        self.assert_no_business_call(PermissionError, self.fixture.call)

    def test_another_verified_member_cannot_borrow_exact_operator_grant(self):
        # uid2 is an actual verified EDITOR in the same existing project.
        self.assert_no_business_call(PermissionError, lambda: self.fixture.call(web=self.fixture.other))

    def test_revocation_is_rechecked_after_a_successful_request(self):
        self.fixture.call()
        with self.center.tx():
            self.center.db.execute('UPDATE members SET active=0 WHERE project=? AND user_id=?', ('project1', self.fixture.fx.uid1))
        self.assert_no_business_call(PermissionError, self.fixture.call)

    def test_attempt_audit_failure_prevents_business_io(self):
        with patch.object(self.center, 'audit', side_effect=RuntimeError('synthetic audit unavailable')):
            self.assert_no_business_call(RuntimeError, self.fixture.call)

    def test_timeout_during_dispatch_is_not_automatically_retried(self):
        with patch.object(self.runtime, 'dispatch', side_effect=TimeoutError('synthetic operation timeout')) as dispatch:
            with self.assertRaises(TimeoutError):
                self.fixture.call()
            dispatch.assert_called_once()
        # This proves one invocation has no retry; it does NOT establish durable
        # cross-request UNKNOWN/reference handling for an unfrozen remote API.

    def test_completion_audit_failure_does_not_replay_business(self):
        audit = self.center.audit
        def fail_completion(project, user, kind, reference):
            if kind == 'COMMUNITY_OPERATION_COMPLETED':
                raise RuntimeError('synthetic completion unknown')
            return audit(project, user, kind, reference)
        with patch.object(self.center, 'audit', side_effect=fail_completion):
            with patch.object(self.runtime, 'dispatch', wraps=self.runtime.dispatch) as dispatch:
                with self.assertRaises(RuntimeError):
                    self.fixture.call()
                dispatch.assert_called_once()


if __name__ == '__main__':
    unittest.main()
