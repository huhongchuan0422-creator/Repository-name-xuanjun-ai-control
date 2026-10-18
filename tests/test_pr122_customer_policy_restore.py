"""Offline fixed policy-restore boundary tests; no host security commands.

All paths are disposable sandbox files. Host ownership/baseline, original lock
entry, visudo and the coordinator lease are test doubles. This does not establish
production authority, account admission or PR99 security acceptance.
"""
import copy
import errno
import json
import os
import stat
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.pr122_account_admission import domestic_bootstrap as bootstrap
from scripts.pr122_customer_core import Denied
from scripts.pr122_customer_workflow import POLICY as WORKFLOW_POLICY


class OfflinePolicyLease:
    """Only the fixed coordinator interface consumed by restore_for_workflow."""

    def __init__(self, inputs):
        self.approval = {'attempt_policy': WORKFLOW_POLICY}
        self.inputs = copy.deepcopy(inputs)
        self.data = {'intent': {'stage': 'POLICY_RESTORE', 'attempt': 1}}
        self.actions = ['RECONCILE_POLICY']
        self.ops = SimpleNamespace(input=lambda stage: copy.deepcopy(self.inputs))
        self.records = []
        self.guard_calls = []
        self.expired = False
        self.fence_lost = False
        self.input_drift = False

    def authority(self):
        self.guard_calls.append('authority')
        if self.expired:
            raise Denied('HOLD:WORKFLOW_LEASE_EXPIRED')

    def assert_active(self):
        self.guard_calls.append('active')
        if self.fence_lost:
            raise Denied('HOLD:WORKFLOW_FENCE_LOST')
        if self.expired:
            raise Denied('HOLD:WORKFLOW_LEASE_EXPIRED')

    def verify_inputs(self, stage):
        self.guard_calls.append(('inputs', stage))
        if self.input_drift:
            raise Denied('HOLD:WORKFLOW_STAGE_INPUT_DRIFT')

    def stage_contract(self, stage):
        if stage != 'POLICY_RESTORE':
            raise AssertionError('Unexpected stage')
        return {'recovery_actions': list(self.actions)}

    def record_stage(self, stage, phase, metadata):
        self.assert_active()
        self.records.append((stage, phase, copy.deepcopy(metadata)))


class PolicyRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root / 'base'
        self.control = self.base / 'readonly-bootstrap-20261017'
        self.control.mkdir(parents=True, mode=0o700)
        values = {'BASE': self.base, 'CONTROL': self.control,
                  'EXEC': self.root / 'libexec' / 'channel',
                  'POLICY': self.root / 'sudoers' / 'channel',
                  'HELPER': self.base / 'readonly-admission.py'}
        for name, value in values.items():
            value.parent.mkdir(parents=True, exist_ok=True)
            adapter = patch.object(bootstrap, name, value)
            adapter.start()
            self.addCleanup(adapter.stop)
        self.helper = b'# exact reviewed offline helper\n'
        self.baseline = {'fixture_host_identity': 'unchanged original baseline'}
        self.plan = {'scope': 'DOMESTIC_READONLY_BOOTSTRAP_20261017',
                     'baseline': self.baseline,
                     'manifest': {'files': {'domestic-readonly-helper.py': {
                         'sha256': bootstrap.sha(self.helper), 'size': len(self.helper)}}}}
        self.put(self.control / 'plan.json', bootstrap.canonical(self.plan), 0o400)
        self.put(self.control / 'old-wrapper', bootstrap.expected_wrapper(), 0o400)
        self.put(self.control / 'old-sudoers', bootstrap.expected_policy(), 0o400)
        self.put(self.control / 'new-helper', self.helper, 0o400)
        self.put(bootstrap.HELPER, self.helper, 0o400)
        self.put(bootstrap.EXEC, bootstrap.new_wrapper(), 0o755)
        self.put(bootstrap.POLICY, bootstrap.new_policy(), 0o440)
        self.lease = OfflinePolicyLease({
            'transaction': self.control.name,
            'plan_sha256': bootstrap.sha((self.control / 'plan.json').read_bytes()),
            'old_wrapper_sha256': bootstrap.sha(bootstrap.expected_wrapper()),
            'old_policy_sha256': bootstrap.sha(bootstrap.expected_policy()),
        })
        self.events = []
        self.lock_depth = 0
        self.before_replace = self.after_replace = self.before_record = None
        original_replace, original_record = bootstrap.replace, bootstrap.record

        @contextmanager
        def owner_lock(create_allowed=False):
            self.assertFalse(create_allowed)
            self.events.append(('lock_enter',))
            self.lock_depth += 1
            try:
                yield
            finally:
                self.lock_depth -= 1
                self.events.append(('lock_exit',))

        def sandbox_secure(path, directory=False):
            path = Path(path)
            self.assertTrue(path == self.root or self.root in path.parents)
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_dir() if directory else path.is_file())
            return path

        def read(path, mode=None):
            path = sandbox_secure(path)
            bootstrap.need(mode is None or stat.S_IMODE(path.stat().st_mode) == mode, 'MODE_DRIFT')
            return path.read_bytes()

        def replace(path, raw, mode):
            self.assertEqual(self.lock_depth, 1)
            self.events.append(('replace', Path(path), raw, mode))
            if self.before_replace:
                self.before_replace(Path(path))
            original_replace(path, raw, mode)
            if self.after_replace:
                self.after_replace(Path(path))

        def record(state):
            self.assertEqual(self.lock_depth, 1)
            self.events.append(('record', state))
            if self.before_record:
                self.before_record(state)
            original_record(state)

        def policy_check(path):
            self.assertEqual(self.lock_depth, 1)
            self.assertEqual(path, self.control / 'old-sudoers')
            self.assertEqual(read(path, 0o400), bootstrap.expected_policy())
            self.events.append(('policy_check', Path(path)))

        for adapter in (
            patch.object(bootstrap, 'owner', side_effect=lambda: self.events.append(('owner',))),
            patch.object(bootstrap, 'owner_lock', owner_lock),
            patch.object(bootstrap, 'baseline', side_effect=lambda: copy.deepcopy(self.baseline)),
            patch.object(bootstrap, 'secure', sandbox_secure),
            patch.object(bootstrap, 'read', read),
            patch.object(bootstrap, 'replace', replace),
            patch.object(bootstrap, 'record', record),
            patch.object(bootstrap, 'policy_check', policy_check),
            patch.object(bootstrap.subprocess, 'run', side_effect=AssertionError('Host commands forbidden')),
        ):
            adapter.start()
            self.addCleanup(adapter.stop)

    def put(self, path, raw, mode):
        # Fault injection changes only this test's owned disposable files.
        if path.exists():
            path.chmod(0o600)
        path.write_bytes(raw)
        path.chmod(mode)

    def restore(self):
        return bootstrap.restore_for_workflow(self.lease)

    def writes(self):
        return [event for event in self.events if event[0] in ('replace', 'record')]

    def replaced(self):
        return [event[1] for event in self.events if event[0] == 'replace']

    def assert_no_writes(self):
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.lease.records, [])

    def mark(self, phase, raw=None):
        self.put(self.control / (phase + '.json'),
                 raw if raw is not None else bootstrap.canonical({'state': phase}), 0o400)

    def test_requires_new_whole_workflow_grant_not_old_v1_v2_or_missing_permission(self):
        for policy in (None, 'CONTROLLED_PREACTIVATION_V1', 'CONTROLLED_INSTALL_RESUME_V2'):
            with self.subTest(policy=policy):
                self.lease.approval['attempt_policy'] = policy
                with self.assertRaisesRegex(RuntimeError, 'WHOLE_WORKFLOW_PERMISSION_REQUIRED'):
                    self.restore()
        self.assert_no_writes()
        self.assertEqual(self.events, [])

    def test_explicit_policy_reconciliation_action_required_before_writes(self):
        self.lease.actions = []
        with self.assertRaisesRegex(RuntimeError, 'POLICY_RESTORATION_NOT_APPROVED'):
            self.restore()
        self.assert_no_writes()
        self.assertEqual(self.events, [])

    def test_only_current_policy_restore_intent_can_invoke_restoration(self):
        for intent in (None, {'stage': 'RUNTIME'}, {'stage': 'CUSTOMER_APPLY'}):
            with self.subTest(intent=intent):
                self.lease.data['intent'] = intent
                with self.assertRaisesRegex(RuntimeError, 'POLICY_STAGE_NOT_ACTIVE'):
                    self.restore()
        self.assert_no_writes()

    def test_expired_authority_is_rejected_before_lock_or_writes(self):
        self.lease.expired = True
        with self.assertRaisesRegex(Denied, 'LEASE_EXPIRED'):
            self.restore()
        self.assert_no_writes()
        self.assertEqual(self.events, [])

    def test_initial_fence_loss_is_rejected_before_lock_or_writes(self):
        self.lease.fence_lost = True
        with self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.restore()
        self.assert_no_writes()
        self.assertEqual(self.events, [])

    def test_exact_original_transaction_plan_and_backup_hashes_are_required(self):
        original = copy.deepcopy(self.lease.inputs)
        for key in original:
            with self.subTest(key=key):
                self.lease.inputs = dict(original, **{key: 'wrong' if key == 'transaction' else 'f' * 64})
                with self.assertRaisesRegex(RuntimeError, 'POLICY_RESTORE_EXACT_BACKUPS'):
                    self.restore()
                self.assert_no_writes()

    def test_input_shape_rejects_extra_unapproved_fields(self):
        self.lease.inputs['arbitrary_command'] = 'forbidden'
        with self.assertRaisesRegex(RuntimeError, 'POLICY_RESTORE_EXACT_BACKUPS'):
            self.restore()
        self.assert_no_writes()

    def test_withdraws_policy_before_wrapper_under_original_owner_lock(self):
        result = self.restore()
        self.assertEqual(result, {'state': 'ROLLED_BACK', 'already_complete': False, 'evidence_retained': True})
        self.assertEqual(self.replaced(), [bootstrap.POLICY, bootstrap.EXEC])
        self.assertEqual(bootstrap.POLICY.read_bytes(), bootstrap.expected_policy())
        self.assertEqual(bootstrap.EXEC.read_bytes(), bootstrap.expected_wrapper())
        self.assertEqual(bootstrap.HELPER.read_bytes(), self.helper)
        self.assertEqual([event for event in self.events if event[0] == 'record'],
                         [('record', 'ROLLBACK_INTENT'), ('record', 'ROLLED_BACK')])
        self.assertLess(self.events.index(('record', 'ROLLBACK_INTENT')),
                        next(i for i, event in enumerate(self.events) if event[0] == 'replace'))
        self.assertEqual([row[1] for row in self.lease.records],
                         ['POLICY_RESTORE_INTENT', 'POLICY_RESTORE_VERIFIED'])
        self.assertEqual(self.events[0:2], [('owner',), ('lock_enter',)])
        self.assertEqual(self.events[-1], ('lock_exit',))

    def test_already_restored_policy_bytes_skip_policy_write(self):
        self.put(bootstrap.POLICY, bootstrap.expected_policy(), 0o440)
        self.assertEqual(self.restore()['state'], 'ROLLED_BACK')
        self.assertEqual(self.replaced(), [bootstrap.EXEC])

    def test_already_restored_wrapper_bytes_skip_wrapper_write(self):
        self.put(bootstrap.EXEC, bootstrap.expected_wrapper(), 0o755)
        self.assertEqual(self.restore()['state'], 'ROLLED_BACK')
        self.assertEqual(self.replaced(), [bootstrap.POLICY])

    def test_complete_bytes_without_receipt_only_finish_original_records(self):
        self.put(bootstrap.POLICY, bootstrap.expected_policy(), 0o440)
        self.put(bootstrap.EXEC, bootstrap.expected_wrapper(), 0o755)
        self.assertFalse(self.restore()['already_complete'])
        self.assertEqual(self.replaced(), [])
        self.assertTrue((self.control / 'ROLLED_BACK.json').exists())

    def test_old_intent_with_exact_partial_restore_can_resume_under_new_grant(self):
        self.mark('ROLLBACK_INTENT')
        intent_before = (self.control / 'ROLLBACK_INTENT.json').stat().st_ino
        self.put(bootstrap.POLICY, bootstrap.expected_policy(), 0o440)
        result = self.restore()
        self.assertEqual(result['state'], 'ROLLED_BACK')
        self.assertEqual(self.replaced(), [bootstrap.EXEC])
        self.assertEqual((self.control / 'ROLLBACK_INTENT.json').stat().st_ino, intent_before)
        self.assertEqual([event for event in self.events if event[0] == 'record'], [('record', 'ROLLED_BACK')])

    def test_existing_complete_receipt_and_bytes_return_without_any_writes(self):
        self.mark('ROLLBACK_INTENT')
        self.mark('ROLLED_BACK')
        self.put(bootstrap.POLICY, bootstrap.expected_policy(), 0o440)
        self.put(bootstrap.EXEC, bootstrap.expected_wrapper(), 0o755)
        result = self.restore()
        self.assertEqual(result, {'state': 'ROLLED_BACK', 'already_complete': True, 'evidence_retained': True})
        self.assert_no_writes()
        self.assertFalse(any(event[0] == 'policy_check' for event in self.events))

    def test_foreign_policy_or_wrapper_bytes_hold_without_overwriting(self):
        originals = {bootstrap.POLICY: (bootstrap.new_policy(), 0o440),
                     bootstrap.EXEC: (bootstrap.new_wrapper(), 0o755)}
        for path, (raw, mode) in originals.items():
            with self.subTest(path=path):
                self.put(path, b'foreign bytes', mode)
                with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_WRAPPER_POLICY'):
                    self.restore()
                self.assertEqual(path.read_bytes(), b'foreign bytes')
                self.assert_no_writes()
                self.put(path, raw, mode)

    def test_foreign_installed_helper_holds_and_preserves_helper(self):
        self.put(bootstrap.HELPER, b'foreign helper', 0o400)
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_HELPER'):
            self.restore()
        self.assertEqual(bootstrap.HELPER.read_bytes(), b'foreign helper')
        self.assert_no_writes()

    def test_original_backup_byte_drift_holds_even_if_new_input_hash_matches_it(self):
        path = self.control / 'old-sudoers'
        self.put(path, b'foreign backup', 0o400)
        self.lease.inputs['old_policy_sha256'] = bootstrap.sha(path.read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'BACKUP_DRIFT'):
            self.restore()
        self.assert_no_writes()

    def test_helper_backup_drift_is_not_adopted(self):
        self.put(self.control / 'new-helper', b'foreign helper backup', 0o400)
        with self.assertRaisesRegex(RuntimeError, 'HELPER_BACKUP_DRIFT'):
            self.restore()
        self.assert_no_writes()

    def test_plan_file_hash_drift_holds_before_policy_or_wrapper_write(self):
        changed = dict(self.plan, harmless_but_unapproved='extra')
        self.put(self.control / 'plan.json', bootstrap.canonical(changed), 0o400)
        with self.assertRaisesRegex(RuntimeError, 'POLICY_RESTORE_EXACT_BACKUPS'):
            self.restore()
        self.assert_no_writes()

    def test_pending_staging_file_for_either_target_holds_without_deleting_it(self):
        for path in (bootstrap.EXEC, bootstrap.POLICY):
            pending = path.parent / ('.' + path.name + '.readonly-bootstrap-pending')
            with self.subTest(path=path):
                self.put(pending, b'unresolved staged bytes', 0o600)
                with self.assertRaisesRegex(RuntimeError, 'PARTIAL_STAGING_REQUIRES_REVIEW'):
                    self.restore()
                self.assertEqual(pending.read_bytes(), b'unresolved staged bytes')
                self.assert_no_writes()
                pending.unlink()

    def test_old_intent_or_complete_receipt_drift_holds_without_replacing_receipt(self):
        for phase in ('ROLLBACK_INTENT', 'ROLLED_BACK'):
            with self.subTest(phase=phase):
                self.mark(phase, b'{"state":"foreign"}')
                path = self.control / (phase + '.json')
                with self.assertRaisesRegex(RuntimeError, 'POLICY_RECEIPT_DRIFT'):
                    self.restore()
                self.assertEqual(path.read_bytes(), b'{"state":"foreign"}')
                self.assert_no_writes()
                path.unlink()

    def test_complete_receipt_cannot_hide_non_restored_exact_new_bytes(self):
        self.mark('ROLLED_BACK')
        with self.assertRaisesRegex(RuntimeError, 'COMPLETED_POLICY_DRIFT'):
            self.restore()
        self.assert_no_writes()

    def test_mode_drift_is_not_silently_repaired(self):
        bootstrap.POLICY.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'MODE_DRIFT'):
            self.restore()
        self.assert_no_writes()

    def test_expiry_between_writes_preserves_partial_and_never_writes_wrapper(self):
        self.after_replace = lambda path: setattr(self.lease, 'expired', True)
        with self.assertRaisesRegex(Denied, 'LEASE_EXPIRED'):
            self.restore()
        self.assertEqual(self.replaced(), [bootstrap.POLICY])
        self.assertEqual(bootstrap.POLICY.read_bytes(), bootstrap.expected_policy())
        self.assertEqual(bootstrap.EXEC.read_bytes(), bootstrap.new_wrapper())
        self.assertTrue((self.control / 'ROLLBACK_INTENT.json').exists())
        self.assertFalse((self.control / 'ROLLED_BACK.json').exists())
        self.assertEqual([row[1] for row in self.lease.records], ['POLICY_RESTORE_INTENT'])

    def test_fence_loss_between_writes_preserves_partial_and_no_stale_stage_record(self):
        self.after_replace = lambda path: setattr(self.lease, 'fence_lost', True)
        with self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.restore()
        self.assertEqual(self.replaced(), [bootstrap.POLICY])
        self.assertEqual(bootstrap.POLICY.read_bytes(), bootstrap.expected_policy())
        self.assertEqual(bootstrap.EXEC.read_bytes(), bootstrap.new_wrapper())
        self.assertFalse((self.control / 'ROLLED_BACK.json').exists())
        self.assertEqual([row[1] for row in self.lease.records], ['POLICY_RESTORE_INTENT'])

    def test_input_drift_between_writes_holds_and_records_unknown_when_lease_remains_valid(self):
        self.after_replace = lambda path: setattr(self.lease, 'input_drift', True)
        with self.assertRaisesRegex(Denied, 'STAGE_INPUT_DRIFT'):
            self.restore()
        self.assertEqual(self.replaced(), [bootstrap.POLICY])
        self.assertEqual(bootstrap.EXEC.read_bytes(), bootstrap.new_wrapper())
        self.assertEqual(self.lease.records[-1],
                         ('POLICY_RESTORE', 'POLICY_RESTORE_UNKNOWN', {'evidence_retained': True}))

    def test_foreign_wrapper_appearing_between_writes_is_preserved_not_overwritten(self):
        def drift_after_policy(path):
            if path == bootstrap.POLICY:
                self.put(bootstrap.EXEC, b'foreign wrapper introduced after policy restore', 0o755)
        self.after_replace = drift_after_policy
        with self.assertRaises(RuntimeError):
            self.restore()
        self.assertEqual(self.replaced(), [bootstrap.POLICY])
        self.assertEqual(bootstrap.EXEC.read_bytes(), b'foreign wrapper introduced after policy restore')
        self.assertFalse((self.control / 'ROLLED_BACK.json').exists())
        self.assertEqual(self.lease.records[-1][1], 'POLICY_RESTORE_UNKNOWN')

    def test_write_exception_is_propagated_with_unknown_evidence_and_original_intent(self):
        error = OSError(errno.EIO, 'fixture policy write failure')

        def fail(path):
            raise error
        self.before_replace = fail
        with self.assertRaises(OSError) as caught:
            self.restore()
        self.assertIs(caught.exception, error)
        self.assertEqual(bootstrap.POLICY.read_bytes(), bootstrap.new_policy())
        self.assertEqual(bootstrap.EXEC.read_bytes(), bootstrap.new_wrapper())
        self.assertTrue((self.control / 'ROLLBACK_INTENT.json').exists())
        self.assertFalse((self.control / 'ROLLED_BACK.json').exists())
        self.assertEqual(self.lease.records[-1],
                         ('POLICY_RESTORE', 'POLICY_RESTORE_UNKNOWN', {'evidence_retained': True}))

    def test_exception_after_policy_write_resumes_only_remaining_wrapper(self):
        def fail_after_policy(path):
            if path == bootstrap.POLICY:
                raise OSError(errno.EIO, 'fixture interrupted after policy replace')
        self.after_replace = fail_after_policy
        with self.assertRaises(OSError):
            self.restore()
        self.assertEqual(self.replaced(), [bootstrap.POLICY])
        self.after_replace = None
        self.events.clear()
        self.assertEqual(self.restore()['state'], 'ROLLED_BACK')
        self.assertEqual(self.replaced(), [bootstrap.EXEC])

    def test_policy_check_failure_happens_before_any_intent_or_write(self):
        with patch.object(bootstrap, 'policy_check', side_effect=RuntimeError('fixture visudo rejection')):
            with self.assertRaisesRegex(RuntimeError, 'visudo rejection'):
                self.restore()
        self.assert_no_writes()
        self.assertFalse((self.control / 'ROLLBACK_INTENT.json').exists())

    def test_final_receipt_failure_retains_exact_restored_bytes_for_later_completion(self):
        def fail_record(phase):
            if phase == 'ROLLED_BACK':
                raise OSError(errno.EIO, 'fixture final receipt write failure')
        self.before_record = fail_record
        with self.assertRaises(OSError):
            self.restore()
        self.assertEqual(bootstrap.POLICY.read_bytes(), bootstrap.expected_policy())
        self.assertEqual(bootstrap.EXEC.read_bytes(), bootstrap.expected_wrapper())
        self.assertFalse((self.control / 'ROLLED_BACK.json').exists())
        self.assertEqual(self.lease.records[-1][1], 'POLICY_RESTORE_UNKNOWN')
        self.before_record = None
        self.events.clear()
        self.assertEqual(self.restore()['state'], 'ROLLED_BACK')
        self.assertEqual(self.replaced(), [])

    def test_original_rollback_stays_one_shot_when_old_intent_exists(self):
        self.mark('ROLLBACK_INTENT')
        with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_ALREADY_STARTED_NO_RETRY'):
            bootstrap.rollback()
        self.assert_no_writes()


if __name__ == '__main__':
    unittest.main()
