"""Unprivileged, in-memory tests of the original channel workflow seam.

Every host read, lock, plan, bundle and filesystem mutation is mocked. These
checks do not run UpgradeTests, PR99 commands, sudo or any production adapter.
"""
import copy
import json
import stat
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import pr122_customer_channel_upgrade as upgrade
from scripts import pr122_customer_workflow as workflow
from scripts.pr122_customer_core import Denied, canonical, digest


class OfflineChannelCoordinator:
    def __init__(self, inputs, implementation):
        self.approval = {'attempt_policy': workflow.POLICY, 'max_executions': 5,
                         'expires_unix': int(time.time()) + 600, 'fixture_permit': 'one permit',
                         'artifact_zip_sha256': inputs['zip_sha256']}
        self.plan = {'source_commit': 'b' * 40, 'manifest_sha256': 'c' * 64}
        self.inputs = copy.deepcopy(inputs)
        self.input_pin = digest(canonical(inputs))
        self.implementation = implementation
        self.active = {'number': 1, 'state': 'STARTED_UNKNOWN'}
        self.data = {'attempts': [self.active], 'intent': {'stage': 'CHANNEL_REBIND', 'attempt': 1}}
        self.ops = SimpleNamespace(input=lambda stage: copy.deepcopy(self.inputs))
        self.expired = self.fence_lost = self.permission_lost = False
        self.authority_calls = 0

    def assert_fence(self):
        if self.fence_lost:
            raise Denied('HOLD:WORKFLOW_FENCE_LOST')

    def assert_active(self):
        self.assert_fence()
        if self.expired:
            raise Denied('HOLD:WORKFLOW_LEASE_EXPIRED')

    def authority(self):
        self.authority_calls += 1
        self.assert_active()
        if self.permission_lost:
            raise Denied('HOLD:WORKFLOW_PERMISSION_DRIFT')

    def verify_inputs(self, stage):
        if stage != 'CHANNEL_REBIND' or digest(canonical(self.inputs)) != self.input_pin:
            raise Denied('HOLD:WORKFLOW_STAGE_INPUT_DRIFT')

    def stage_contract(self, stage):
        if stage != 'CHANNEL_REBIND':
            raise AssertionError('Unexpected stage')
        return {'implementation_sha256': self.implementation, 'recovery_actions': ['RECONCILE_CHANNEL']}

    def record_stage(self, *args):
        raise AssertionError('Channel seam must retain original channel receipt authority')


class ChannelWorkflowTests(unittest.TestCase):
    def setUp(self):
        root = Path('/offline-channel-fixture')
        for name, value in {'BASE': root / 'base', 'CONTROL': root / 'base/upgrades/fixed',
                            'EXEC': root / 'channel-exec', 'POLICY': root / 'fixed-policy',
                            'INPUT': root / 'review-artifact.zip', 'TRUST': root / 'trust.json'}.items():
            adapter = patch.object(upgrade, name, value)
            adapter.start()
            self.addCleanup(adapter.stop)
        self.module = Path(upgrade.__file__).absolute()
        self.module_bytes = b'# exact offline channel implementation\n'
        self.old_code, self.new_code = b'# old channel\n', b'# new channel\n'
        self.old_tar, self.new_tar = b'old fixture archive', b'new fixture archive'
        self.new_files = {'boot.py': b'new fixture boot', 'CUSTOMER_MANIFEST.json': b'{}'}
        self.files = {
            self.module: (self.module_bytes, 0o444),
            upgrade.BASE / 'channel.py': (self.old_code, 0o444),
            upgrade.BASE / upgrade.ARCHIVE: (self.old_tar, 0o400),
            upgrade.BASE / 'grant-state.json': (b'{"state":"GRANTED"}', 0o600),
            upgrade.BASE / 'candidate/boot.py': (b'old fixture boot', 0o400),
            upgrade.EXEC: (upgrade.expected_wrapper(), 0o755),
            upgrade.POLICY: (upgrade.expected_policy(), 0o440),
        }
        self.dirs = {root, upgrade.BASE, upgrade.BASE / 'candidate', upgrade.CONTROL.parent}
        self.events, self.mutations, self.checkpoints = [], [], []
        self.lock_depth = 0
        self.event_hook = self.replace_hook = None
        self.new = {'zip_sha256': upgrade.FROZEN_ZIP,
                    'binding': {'channel_sha256': upgrade.sha(self.new_code),
                                'tar_sha256': upgrade.sha(self.new_tar),
                                'source_commit': 'b' * 40, 'manifest_sha256': 'c' * 64}}
        self.original_plan = {'transaction': upgrade.TXN, 'new': copy.deepcopy(self.new), 'old': {
            'files': self.snapshot(upgrade.BASE / 'candidate'),
            'code_sha256': upgrade.sha(self.old_code), 'tar_sha256': upgrade.sha(self.old_tar),
            'wrapper_sha256': upgrade.sha(upgrade.expected_wrapper()),
            'policy_sha256': upgrade.sha(upgrade.expected_policy()),
            'grant_sha256': upgrade.sha(b'{"state":"GRANTED"}'),
        }, 'production_service_changes': 0, 'customer_install': 'NOT_CALLED'}
        self.coordinator = OfflineChannelCoordinator(
            {'plan_sha256': upgrade.sha(upgrade.canonical(self.original_plan)), 'zip_sha256': upgrade.FROZEN_ZIP},
            upgrade.sha(self.module_bytes))
        self.lease = workflow.StageLease(self.coordinator, self.coordinator.active,
                                        digest(canonical(self.coordinator.data['intent'])), 'CHANNEL_REBIND')

        def plan(ignore_transaction=False, expected_zip_sha256=None):
            upgrade.need(ignore_transaction or upgrade.CONTROL not in self.dirs,
                         'TRANSACTION_EXISTS_DO_NOT_RETRY')
            return copy.deepcopy(self.original_plan)

        @contextmanager
        def owner_lock(create_allowed=False):
            self.lock_depth += 1
            self.events.append(('LOCK', create_allowed))
            try:
                yield
            finally:
                self.lock_depth -= 1

        def mkdir(path, *args, **kwargs):
            self.dirs.add(Path(path))

        def file_stat(path, *args, **kwargs):
            path = Path(path)
            if path not in self.files:
                raise AssertionError('Unexpected host stat: ' + str(path))
            return SimpleNamespace(st_mode=stat.S_IFREG | self.files[path][1])

        def iterdir(path):
            path = Path(path)
            return iter(sorted(p for p in self.files if p.parent == path))

        def event(receipt, phase, status):
            self.assertEqual(self.lock_depth, 1)
            receipt.update(phase=phase, step_status=status)
            self.events.append((phase, status))
            folder = upgrade.CONTROL / 'events'
            previous = [p for p in self.files if p.parent == folder]
            self.files[folder / ('%06d.json' % (len(previous) + 1))] = (upgrade.canonical(receipt), 0o400)
            self.files[upgrade.CONTROL / 'receipt.json'] = (upgrade.canonical(receipt), 0o600)
            if self.event_hook:
                self.event_hook(receipt, phase, status)

        adapters = [
            patch.object(upgrade, 'owner'),
            patch.object(upgrade, 'plan', side_effect=plan),
            patch.object(upgrade, 'read', side_effect=lambda path: self.files[Path(path)][0]),
            patch.object(upgrade, 'secure', side_effect=lambda path, directory=False: Path(path)),
            patch.object(upgrade, 'owner_lock', owner_lock),
            patch.object(upgrade, 'bundle', side_effect=lambda expected_zip_sha256=None: (copy.deepcopy(self.new), copy.deepcopy(self.new_files), self.new_tar, self.new_code)),
            patch.object(upgrade, 'create', side_effect=self.create),
            patch.object(upgrade, 'replace', side_effect=self.replace),
            patch.object(upgrade, 'move', side_effect=self.move),
            patch.object(upgrade, 'tree_write', side_effect=self.tree_write),
            patch.object(upgrade, 'snapshot', side_effect=self.snapshot),
            patch.object(upgrade, 'sync'),
            patch.object(upgrade, 'event', side_effect=event),
            patch.object(upgrade, 'gate', side_effect=AssertionError('Old gate fallback forbidden')),
            patch.object(upgrade, 'fetch', side_effect=AssertionError('Network fetch forbidden')),
            patch.object(upgrade.os.path, 'lexists', side_effect=lambda path: Path(path) in self.files or Path(path) in self.dirs),
            patch.object(Path, 'mkdir', mkdir),
            patch.object(Path, 'stat', file_stat),
            patch.object(Path, 'iterdir', iterdir),
        ]
        for adapter in adapters:
            adapter.start()
            self.addCleanup(adapter.stop)

    def create(self, path, raw, mode):
        path = Path(path)
        self.assertEqual(self.lock_depth, 1)
        if path in self.files:
            raise FileExistsError(str(path))
        self.mutations.append(('create', path))
        self.files[path] = (bytes(raw), mode)

    def replace(self, path, raw, mode):
        path = Path(path)
        self.assertEqual(self.lock_depth, 1)
        self.mutations.append(('replace', path))
        self.files[path] = (bytes(raw), mode)
        if self.replace_hook:
            self.replace_hook(path)

    def tree_write(self, folder, files):
        self.dirs.add(Path(folder))
        for name, raw in files.items():
            self.create(Path(folder) / name, raw, 0o400)

    def snapshot(self, folder):
        folder = Path(folder)
        return {path.relative_to(folder).as_posix(): {'sha256': upgrade.sha(raw), 'mode': mode}
                for path, (raw, mode) in self.files.items() if folder in path.parents}

    def move(self, source, target):
        source, target = Path(source), Path(target)
        self.assertEqual(self.lock_depth, 1)
        self.assertNotIn(target, self.dirs)
        self.mutations.append(('move', source, target))
        for path in list(self.files):
            if source in path.parents:
                self.files[target / path.relative_to(source)] = self.files.pop(path)
        self.dirs.discard(source)
        self.dirs.add(target)

    def apply(self):
        return upgrade.apply_for_workflow(self.lease, checkpoint=self.checkpoints.append)

    def approval(self):
        return json.loads(self.files[upgrade.CONTROL / 'approval.json'][0])

    def test_wrapper_routes_only_to_original_apply_with_explicit_same_lease(self):
        callback = lambda stage: None
        with patch.object(upgrade, 'apply', return_value={'fixture': 'routed'}) as original:
            self.assertEqual(upgrade.apply_for_workflow(self.lease, callback), {'fixture': 'routed'})
        original.assert_called_once_with(checkpoint=callback, workflow_lease=self.lease)

    def test_new_authority_is_exactly_bound_and_forward_only(self):
        result = upgrade._workflow_authority(self.lease, self.original_plan)
        self.assertEqual(result, {'workflow_policy': workflow.POLICY,
                         'workflow_approval_sha256': upgrade.sha(upgrade.canonical(self.coordinator.approval)),
                         'expires_unix': self.coordinator.approval['expires_unix'], 'rollback_approved': False})
        self.assertGreater(self.coordinator.authority_calls, 0)
        self.assertEqual(self.mutations, [])

    def test_v1_v2_or_missing_policy_cannot_authorize_forward_rebind(self):
        for policy in (None, 'CONTROLLED_PREACTIVATION_V1', 'CONTROLLED_INSTALL_RESUME_V2'):
            with self.subTest(policy=policy):
                self.coordinator.approval['attempt_policy'] = policy
                with self.assertRaisesRegex(RuntimeError, 'WHOLE_WORKFLOW_PERMISSION_REQUIRED'):
                    self.apply()
        self.assertEqual(self.mutations, [])
        upgrade.gate.assert_not_called()

    def test_exact_plan_hash_and_zip_pin_required_even_with_consistent_input_contract(self):
        original = copy.deepcopy(self.coordinator.inputs)
        for key in original:
            with self.subTest(key=key):
                self.coordinator.inputs = dict(original, **{key: 'f' * 64})
                self.coordinator.input_pin = digest(canonical(self.coordinator.inputs))
                with self.assertRaisesRegex(RuntimeError, 'WORKFLOW_CHANNEL_EXACT_INPUTS'):
                    self.apply()
        self.assertEqual(self.mutations, [])

    def test_extra_channel_input_fields_are_rejected(self):
        self.coordinator.inputs['arbitrary_command'] = 'forbidden'
        self.coordinator.input_pin = digest(canonical(self.coordinator.inputs))
        with self.assertRaisesRegex(RuntimeError, 'WORKFLOW_CHANNEL_EXACT_INPUTS'):
            self.apply()
        self.assertEqual(self.mutations, [])

    def test_stage_input_contract_drift_is_checked_before_mutation(self):
        self.coordinator.inputs['plan_sha256'] = 'f' * 64
        with self.assertRaisesRegex(Denied, 'STAGE_INPUT_DRIFT'):
            self.apply()
        self.assertEqual(self.mutations, [])

    def test_module_implementation_hash_must_match_current_stage_contract(self):
        self.files[self.module] = (b'changed module implementation', 0o444)
        with self.assertRaisesRegex(RuntimeError, 'WORKFLOW_CHANNEL_IMPLEMENTATION'):
            self.apply()
        self.assertEqual(self.mutations, [])
        upgrade.gate.assert_not_called()

    def test_stage_lease_cannot_be_reused_for_different_pending_stage(self):
        self.coordinator.data['intent'] = {'stage': 'CUSTOMER_APPLY', 'attempt': 1}
        with self.assertRaisesRegex(Denied, 'STALE_CHILD_LEASE'):
            self.apply()
        self.assertEqual(self.mutations, [])

    def test_readonly_reconciliation_lease_cannot_authorize_rebind_writes(self):
        self.lease = workflow.StageLease(self.coordinator, self.coordinator.active,
                     digest(canonical(self.coordinator.data['intent'])), 'CHANNEL_REBIND', True)
        with self.assertRaisesRegex(Denied, 'RECONCILIATION_READONLY'):
            self.apply()
        self.assertEqual(self.mutations, [])

    def test_success_uses_original_body_receipts_and_never_calls_legacy_gate(self):
        result = self.apply()
        self.assertEqual(result['state'], 'BOUND')
        self.assertEqual(result['customer_install'], 'NOT_CALLED')
        self.assertFalse(result['sudoers_changed'])
        self.assertEqual(self.files[upgrade.BASE / 'channel.py'][0], self.new_code)
        self.assertEqual(self.files[upgrade.BASE / upgrade.ARCHIVE][0], self.new_tar)
        self.assertEqual(self.files[upgrade.EXEC][0], upgrade.expected_wrapper())
        self.assertEqual(self.files[upgrade.POLICY][0], upgrade.expected_policy())
        self.assertFalse(self.approval()['rollback_approved'])
        self.assertEqual(self.approval()['workflow_policy'], workflow.POLICY)
        self.assertIn(('LOCK', True), self.events)
        self.assertIn('BACKUP_VERIFIED', self.checkpoints)
        self.assertIn('BOUND', self.checkpoints)
        upgrade.gate.assert_not_called()
        upgrade.fetch.assert_not_called()

    def test_workflow_forward_receipt_cannot_authorize_original_rollback(self):
        self.apply()
        before = copy.deepcopy(self.mutations)
        with patch.object(upgrade, 'recovery_gate', side_effect=AssertionError('No recovery fallback')):
            with self.assertRaisesRegex(RuntimeError, 'TRANSACTION_BINDING'):
                upgrade.rollback()
        self.assertEqual(self.mutations, before)
        self.assertFalse(self.approval()['rollback_approved'])

    def test_rollback_does_not_accept_or_forward_a_workflow_lease_argument(self):
        with self.assertRaises(TypeError):
            upgrade.rollback(workflow_lease=self.lease)
        self.assertEqual(self.mutations, [])

    def test_original_nonworkflow_apply_still_uses_legacy_gate(self):
        approved = {'id': 123, 'body_sha256': 'd' * 64, 'rollback_approved': True,
                    'expires_unix': int(time.time()) + 600}
        with patch.object(upgrade, 'gate', return_value=approved) as gate, \
                patch.object(upgrade, '_workflow_authority', side_effect=AssertionError('No workflow fallback')):
            self.assertEqual(upgrade.apply()['state'], 'BOUND')
        self.assertEqual(gate.call_count, 3)
        self.assertTrue(self.approval()['rollback_approved'])
        self.assertNotIn('workflow_policy', self.approval())

    def test_original_gate_denial_never_falls_back_to_workflow_authority(self):
        with patch.object(upgrade, 'gate', side_effect=RuntimeError('HOLD:OLD_GATE_DENIED')), \
                patch.object(upgrade, '_workflow_authority', side_effect=AssertionError('No alternate authority')):
            with self.assertRaisesRegex(RuntimeError, 'OLD_GATE_DENIED'):
                upgrade.apply()
        self.assertEqual(self.mutations, [])

    def test_expired_lease_before_start_has_no_mutations_or_legacy_gate_fallback(self):
        self.coordinator.expired = True
        with self.assertRaisesRegex(Denied, 'LEASE_EXPIRED'):
            self.apply()
        self.assertEqual(self.mutations, [])
        upgrade.gate.assert_not_called()

    def test_lost_fence_before_start_has_no_mutations(self):
        self.coordinator.fence_lost = True
        with self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.apply()
        self.assertEqual(self.mutations, [])

    def test_expiry_at_staged_checkpoint_stops_before_activation(self):
        def expire(receipt, phase, status):
            if phase == 'STAGED' and status == 'DONE':
                self.coordinator.expired = True
        self.event_hook = expire
        with self.assertRaisesRegex(Denied, 'LEASE_EXPIRED'):
            self.apply()
        self.assertEqual(self.files[upgrade.BASE / 'channel.py'][0], self.old_code)
        self.assertEqual(self.files[upgrade.BASE / 'grant-state.json'][0], b'{"state":"GRANTED"}')
        self.assertFalse(any(row[0] == 'move' for row in self.mutations))
        # The expired writer cannot append containment or rewrite its receipt.
        self.assertEqual(json.loads(self.files[upgrade.CONTROL / 'receipt.json'][0])['state'], 'PREPARING')

    def test_fence_loss_before_mutating_fenced_step_stops_before_upgrade_grant(self):
        def lose_fence(receipt, phase, status):
            if phase == 'FENCED' and status == 'INTENT':
                self.coordinator.fence_lost = True
        self.event_hook = lose_fence
        with self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.apply()
        self.assertFalse(any(row[0] == 'move' for row in self.mutations))
        self.assertEqual(self.files[upgrade.BASE / 'channel.py'][0], self.old_code)
        # A fenced-out writer must not perform even the old containment write.
        self.assertEqual(self.files[upgrade.BASE / 'grant-state.json'][0], b'{"state":"GRANTED"}')
        self.assertEqual(self.files[upgrade.POLICY][0], upgrade.expected_policy())

    def test_fence_lost_inside_intent_checkpoint_cannot_execute_following_mutation(self):
        def checkpoint(stage):
            if stage == 'FENCED:INTENT':
                self.coordinator.fence_lost = True
        with self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            upgrade.apply_for_workflow(self.lease, checkpoint=checkpoint)
        self.assertEqual(self.files[upgrade.BASE / 'grant-state.json'][0], b'{"state":"GRANTED"}')
        self.assertFalse(any(row[0] == 'replace' for row in self.mutations))

    def test_permission_change_at_checkpoint_stops_forward_progress(self):
        def revoke(receipt, phase, status):
            if phase == 'BACKUP_VERIFIED' and status == 'DONE':
                self.coordinator.permission_lost = True
        self.event_hook = revoke
        with self.assertRaisesRegex(Denied, 'PERMISSION_DRIFT'):
            self.apply()
        self.assertNotIn(upgrade.CONTROL / 'new-channel.py', self.files)
        self.assertEqual(self.files[upgrade.BASE / 'channel.py'][0], self.old_code)

    def test_module_drift_after_staging_is_rechecked_before_activation(self):
        def drift(receipt, phase, status):
            if phase == 'STAGED' and status == 'DONE':
                self.files[self.module] = (b'changed after staging', 0o444)
        self.event_hook = drift
        with self.assertRaisesRegex(RuntimeError, 'WORKFLOW_CHANNEL_IMPLEMENTATION'):
            self.apply()
        self.assertFalse(any(row[0] == 'move' for row in self.mutations))
        self.assertEqual(self.files[upgrade.BASE / 'grant-state.json'][0], b'{"state":"GRANTED"}')

    def test_consumed_channel_transaction_remains_sealed_on_repeat_workflow_call(self):
        self.apply()
        before = copy.deepcopy(self.mutations)
        with self.assertRaisesRegex(RuntimeError, 'TRANSACTION_EXISTS_DO_NOT_RETRY'):
            self.apply()
        self.assertEqual(self.mutations, before)
        upgrade.gate.assert_not_called()

    def test_under_lock_plan_drift_stops_before_any_filesystem_mutation(self):
        changed = dict(self.original_plan, unexpected='drift')
        with patch.object(upgrade, 'plan', side_effect=[copy.deepcopy(self.original_plan), changed]):
            with self.assertRaisesRegex(RuntimeError, 'UNDER_LOCK_DRIFT'):
                self.apply()
        self.assertEqual(self.mutations, [])

    def test_bundle_metadata_drift_stops_before_transaction_consumption(self):
        changed = dict(self.new, zip_sha256='f' * 64)
        with patch.object(upgrade, 'bundle', return_value=(changed, self.new_files, self.new_tar, self.new_code)):
            with self.assertRaisesRegex(RuntimeError, 'STAGING_DRIFT'):
                self.apply()
        self.assertNotIn(upgrade.CONTROL, self.dirs)
        self.assertEqual(self.mutations, [])

    def test_new_signed_zip_is_passed_to_plan_and_bundle_without_changing_legacy_default(self):
        new_pin = 'e' * 64
        self.new['zip_sha256'] = new_pin
        self.original_plan['new'] = copy.deepcopy(self.new)
        self.coordinator.inputs = {'plan_sha256': upgrade.sha(upgrade.canonical(self.original_plan)),
                                   'zip_sha256': new_pin}
        self.coordinator.input_pin = digest(canonical(self.coordinator.inputs))
        self.coordinator.approval['artifact_zip_sha256'] = new_pin
        self.assertEqual(self.apply()['state'], 'BOUND')
        self.assertTrue(all(call.kwargs['expected_zip_sha256'] == new_pin
                            for call in upgrade.plan.call_args_list))
        upgrade.bundle.assert_called_once_with(new_pin)
        self.assertNotEqual(upgrade.FROZEN_ZIP, new_pin)

    def test_zip_must_match_the_signed_workflow_artifact_pin(self):
        self.coordinator.approval['artifact_zip_sha256'] = 'e' * 64
        with self.assertRaisesRegex(RuntimeError, 'WORKFLOW_CHANNEL_EXACT_INPUTS'):
            self.apply()
        self.assertEqual(self.mutations, [])

    def test_channel_source_and_manifest_must_match_the_whole_workflow_plan(self):
        for key, wrong in [('source_commit', 'd' * 40), ('manifest_sha256', 'd' * 64)]:
            with self.subTest(key=key):
                original = self.coordinator.plan[key]
                self.coordinator.plan[key] = wrong
                with self.assertRaisesRegex(RuntimeError, 'WORKFLOW_CHANNEL_EXACT_INPUTS'):
                    self.apply()
                self.coordinator.plan[key] = original
        self.assertEqual(self.mutations, [])


if __name__ == '__main__':
    unittest.main()
