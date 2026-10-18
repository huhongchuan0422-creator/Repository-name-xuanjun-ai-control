"""Mocked live-proof and recovery tests for concrete OriginalOperations.

No account, runtime, channel, policy or customer writer is run. Host reads,
identity checks and commands are replaced with explicit in-memory test data.
These tests validate adapter decisions, not production target acceptance.
"""
import copy
import json
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import pr122_customer_workflow_operations as operations
from scripts.pr122_customer_core import Denied, canonical, digest
from scripts.pr122_customer_workflow import POLICY, STAGES


class OriginalOperationsTests(unittest.TestCase):
    def setUp(self):
        self.original_read_bytes = Path.read_bytes
        self.original_lstat = operations.os.lstat
        self.original_lexists = operations.os.path.lexists
        self.plan = {'source_commit': 'a' * 40, 'manifest_sha256': digest(b'fixture manifest')}
        self.approval = {'attempt_policy': POLICY, 'fixture': 'same signed workflow'}
        self.platform = {'uid_min': 1000, 'uid_max': 1999, 'gid_min': 1000, 'gid_max': 1999}
        self.post = {'uid': 1001, 'gid': 1001, 'name': operations.account.ACCOUNT,
                     'primary_group': operations.account.ACCOUNT, 'group_gid': 1001,
                     'home': '/nonexistent', 'shell': '/usr/sbin/nologin', 'supplementary_groups': [],
                     **{key: True for key in ('password_locked', 'home_absent', 'mail_spool_absent',
                                             'no_subids', 'no_sudo_grants')}}
        self.account_receipt = canonical({'state': 'ACCOUNT_CREATED_VERIFIED_NO_RETRY',
                            'host': operations.account.HOST, 'account': operations.account.ACCOUNT,
                            'retry_allowed': False})
        self.probe_value = {'state': 'READONLY_OBSERVED_ACCOUNT_CREATION_HOLD',
                            'hostname': operations.account.HOST, 'account': operations.account.ACCOUNT,
                            'mutations': 0, 'creation_authorized': False}
        self.runtime_tree = {'python': {'sha256': 'c' * 64, 'mode': 0o755}}
        self.root_info = SimpleNamespace(st_dev=1, st_ino=2, st_uid=0, st_gid=0,
                                         st_mode=stat.S_IFDIR | 0o755)
        self.runtime_report = {'account_uid': 1001, 'account_gid': 1001,
            'runtime_closure_sha256': digest(canonical(self.runtime_tree)),
            'runtime_root_identity': {'dev': 1, 'ino': 2, 'uid': 0, 'gid': 0, 'mode': 0o755},
            'source_closure_sha256': 'd' * 64}
        self.bootstrap_plan = {'fixture': 'exact original restore plan'}
        self.channel_files = {'boot.py': b'fixed channel candidate'}
        self.channel_code, self.channel_archive = b'fixed new channel', b'fixed archive'
        self.channel_value = {'zip_sha256': 'e' * 64, 'binding': {'source_commit': self.plan['source_commit']}}
        self.channel_plan = {'new': self.channel_value, 'fixture': 'exact original rebind plan'}
        self.channel_receipt = {'state': 'BOUND', 'phase': 'BOUND', 'step_status': 'DONE',
                               'plan': self.channel_plan, 'approval': {
            'workflow_approval_sha256': digest(canonical(self.approval)), 'rollback_approved': False}}
        self.release = SimpleNamespace(STATE=Path('/offline/customer-state'), TXN='original-txn',
                                       __file__='/offline/release.py', source=Mock(),
                                       run=Mock(side_effect=AssertionError('Actual command forbidden')))
        self.folder = Path('/offline/reviewed-source')
        self.customer_receipt = {'schema': 3, 'policy': POLICY, 'approval': self.approval,
                                 'state': operations.resume.SUCCESS,
                                 'plan': {'fixture_static_context': 'approved', 'account_uid': 1001,
                                          'account_gid': 1001, 'isolated_python': {'fixture': 'verified'}}}
        self.customer_cp = {'state': 'COMPLETE', 'receipt_sha256': '1' * 64,
                            'effect_sha256': '2' * 64, 'source_commit': self.plan['source_commit']}
        self.raw = {operations.PROBE_RECEIPT: canonical(self.probe_value)}
        self.bootstrap_raw = {
            operations.bootstrap.CONTROL / 'ROLLED_BACK.json': operations.bootstrap.canonical({'state': 'ROLLED_BACK'}),
            operations.bootstrap.POLICY: operations.bootstrap.expected_policy(),
            operations.bootstrap.EXEC: operations.bootstrap.expected_wrapper(),
            operations.bootstrap.CONTROL / 'plan.json': operations.bootstrap.canonical(self.bootstrap_plan),
            operations.bootstrap.CONTROL / 'old-wrapper': operations.bootstrap.expected_wrapper(),
            operations.bootstrap.CONTROL / 'old-sudoers': operations.bootstrap.expected_policy(),
        }
        self.channel_raw = {
            operations.channel.CONTROL / 'receipt.json': operations.channel.canonical(self.channel_receipt),
            operations.channel.BASE / 'channel.py': self.channel_code,
            operations.channel.BASE / operations.channel.ARCHIVE: self.channel_archive,
            operations.channel.BASE / 'grant-state.json': b'{"state":"GRANTED"}',
        }
        self.inputs = {'schema': 1, 'stages': {
            'PROBE': {'receipt_sha256': digest(self.raw[operations.PROBE_RECEIPT])},
            'ACCOUNT': {'platform_sha256': digest(canonical(self.platform))},
            'RUNTIME': {'runtime_template': {'fixture': 'approved runtime template'}},
            'POLICY_RESTORE': {
                'transaction': operations.bootstrap.CONTROL.name,
                'plan_sha256': digest(self.bootstrap_raw[operations.bootstrap.CONTROL / 'plan.json']),
                'old_wrapper_sha256': digest(operations.bootstrap.expected_wrapper()),
                'old_policy_sha256': digest(operations.bootstrap.expected_policy())},
            'CHANNEL_REBIND': {'plan_sha256': digest(operations.channel.canonical(self.channel_plan)),
                               'zip_sha256': self.channel_value['zip_sha256']},
            'CUSTOMER_APPLY': {'static_plan': {'fixture_static_context': 'approved'}},
        }}
        records = [{'stage': 'ACCOUNT', 'phase': 'ACCOUNT_VERIFIED', 'metadata': {'uid': 1001, 'gid': 1001}},
                   {'stage': 'RUNTIME', 'phase': 'RUNTIME_VERIFIED', 'metadata': self.runtime_report}]
        self.coordinator = SimpleNamespace(approval=self.approval, data={'stage_records': records},
            stage_contract=Mock(return_value={'recovery_actions': ['RECONCILE_CUSTOMER']}), assert_fence=Mock())
        self.lease = SimpleNamespace(assert_fence=Mock(), authority=Mock(), assert_active=Mock())
        self.account_os = SimpleNamespace(platform_preconditions=Mock(side_effect=lambda: copy.deepcopy(self.platform)),
            private_postcheck=Mock(side_effect=lambda: copy.deepcopy(self.post)),
            getpwnam=Mock(side_effect=KeyError('absent')), getgrnam=Mock(side_effect=KeyError('absent')))
        self.journal = Mock()
        self.release.source.return_value = (copy.deepcopy(self.plan), b'fixture manifest', {'boot.py': b'fixed bytes'})
        self.existing = set()
        modules = {'PROBE': operations.probe, 'ACCOUNT': operations.account, 'RUNTIME': operations.runtime,
                   'POLICY_RESTORE': operations.bootstrap, 'CHANNEL_REBIND': operations.channel,
                   'CUSTOMER_APPLY': self.release}
        for name, module in modules.items():
            self.raw[Path(module.__file__)] = ('exact implementation ' + name).encode()

        def private_read(path):
            if Path(path) == operations.PROBE_RECEIPT:
                return json.loads(self.raw[Path(path)])
            if Path(path) == self.release.STATE / self.release.TXN / 'receipt.json':
                return copy.deepcopy(self.customer_receipt)
            raise AssertionError('Unexpected private host read: ' + str(path))

        self.writers = []
        adapters = [
            patch.object(Path, 'read_bytes', lambda path: self.raw[Path(path)]),
            patch.object(operations.resume, 'read_private', side_effect=private_read),
            patch.object(operations.account, 'read_public_config', side_effect=lambda path: self.account_receipt.decode()),
            patch.object(operations.account, 'OS', return_value=self.account_os),
            patch.object(operations.runtime, '_runtime_tree', side_effect=lambda root: copy.deepcopy(self.runtime_tree)),
            patch.object(operations.runtime, '_source_identity', return_value=self.runtime_report['source_closure_sha256']),
            patch.object(operations.os, 'lstat', side_effect=lambda path: self.root_info),
            patch.object(operations.os.path, 'lexists', side_effect=lambda path: Path(path) in self.existing),
            patch.object(operations.bootstrap, 'read', side_effect=lambda path, mode=None: self.bootstrap_raw[Path(path)]),
            patch.object(operations.bootstrap, 'transaction', side_effect=lambda: (copy.deepcopy(self.bootstrap_plan), b'fixed helper')),
            patch.object(operations.channel, 'read', side_effect=lambda path: self.channel_raw[Path(path)]),
            patch.object(operations.channel, 'bundle', side_effect=lambda pin: (copy.deepcopy(self.channel_value), copy.deepcopy(self.channel_files), self.channel_archive, self.channel_code)),
            patch.object(operations.channel, 'snapshot', side_effect=lambda path: {n: {'sha256': digest(raw), 'mode': 0o400} for n, raw in self.channel_files.items()}),
            patch.object(operations.channel, 'plan', side_effect=lambda **kwargs: copy.deepcopy(self.channel_plan)),
            patch.object(operations.channel, 'verify_policy'), patch.object(operations.channel, 'backup_verify'),
            patch.object(operations.resume, 'backup_bytes', return_value=b'fixed backup'),
            patch.object(operations.resume, 'context'), patch.object(operations.resume, 'Journal', return_value=self.journal),
            patch.object(operations.customer, '_checkpoint', return_value=copy.deepcopy(self.customer_cp)),
            patch.object(operations.customer, 'reconcile', return_value={'status': 'UNKNOWN', 'action': 'RECONCILE_CUSTOMER', 'evidence_sha256': '3' * 64, 'checkpoint': None}),
        ]
        for module, name in [(operations.preparation, 'account_once'), (operations.runtime_stage, 'rebuild_runtime'),
                             (operations.preparation, 'restore_policy'), (operations.channel, 'apply_for_workflow'),
                             (operations.customer, 'execute')]:
            adapter = patch.object(module, name, return_value=copy.deepcopy(self.customer_cp) if name == 'execute' else None)
            self.writers.append(adapter.start())
            self.addCleanup(adapter.stop)
        for adapter in adapters:
            adapter.start()
            self.addCleanup(adapter.stop)
        self.ops = operations.OriginalOperations(self.release, self.folder, self.plan, self.inputs)
        self.ops.attach(self.coordinator)

    def assert_no_writers(self):
        for writer in self.writers:
            writer.assert_not_called()
        self.release.run.assert_not_called()

    def invalidate_observation(self):
        adapter = patch.object(self.ops, '_observe', side_effect=Denied('HOLD:NO_COMPLETED_PROOF'))
        adapter.start()
        self.addCleanup(adapter.stop)

    def recover(self, stage):
        return self.ops.reconcile(stage, {'stage': stage, 'attempt': 1}, None, self.lease)

    def assert_proof(self, proof, status):
        self.assertEqual(set(proof), {'status', 'action', 'evidence_sha256', 'checkpoint'})
        self.assertEqual(proof['status'], status)
        self.assertEqual(len(proof['evidence_sha256']), 64)
        int(proof['evidence_sha256'], 16)
        self.assert_no_writers()

    def test_protected_inputs_require_all_and_only_six_fixed_stages(self):
        for inputs in ({}, {'schema': 2, 'stages': self.inputs['stages']},
                       {'schema': 1, 'stages': {'PROBE': {}}},
                       dict(self.inputs, extra='not allowed')):
            with self.subTest(inputs=inputs), self.assertRaises(Denied):
                operations.OriginalOperations(self.release, self.folder, self.plan, inputs)
        self.assert_no_writers()

    def test_inputs_and_plan_are_defensive_copies_and_attach_is_one_shot(self):
        self.inputs['stages']['PROBE']['receipt_sha256'] = 'f' * 64
        copied = self.ops.input('PROBE')
        copied['receipt_sha256'] = 'e' * 64
        self.assertEqual(self.ops.input('PROBE')['receipt_sha256'], digest(self.raw[operations.PROBE_RECEIPT]))
        with self.assertRaisesRegex(Denied, 'ALREADY_BOUND'):
            self.ops.attach(self.coordinator)
        self.assert_no_writers()

    def test_implementation_bytes_come_from_each_fixed_original_module(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(self.ops.implementation(stage), ('exact implementation ' + stage).encode())
        self.assert_no_writers()

    def test_all_six_completed_stages_are_live_verified_readonly(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                cp = self.ops.inherited(stage)
                self.assertEqual(set(cp), {'state', 'receipt_sha256', 'effect_sha256', 'source_commit'})
                self.assertTrue(self.ops.verify(stage, cp))
        self.journal.reconcile.assert_called()
        self.journal.file.assert_not_called()
        self.assert_no_writers()

    def test_verify_compares_live_receipt_and_effect_even_if_prior_source_was_pinned(self):
        cp = self.ops.inherited('PROBE')
        cp['source_commit'] = 'f' * 40
        self.assertTrue(self.ops.verify('PROBE', cp))
        for field in ('receipt_sha256', 'effect_sha256'):
            wrong = dict(cp, **{field: 'f' * 64})
            self.assertFalse(self.ops.verify('PROBE', wrong))
        self.assert_no_writers()

    def test_probe_receipt_byte_drift_is_not_accepted_from_cached_checkpoint(self):
        cp = self.ops.inherited('PROBE')
        self.raw[operations.PROBE_RECEIPT] += b' '
        with self.assertRaisesRegex(Denied, 'PROBE_EXACT_EXISTING_RECEIPT'):
            self.ops.verify('PROBE', cp)
        self.assert_no_writers()

    def test_probe_state_must_prove_readonly_no_creation_authorization(self):
        self.probe_value['creation_authorized'] = True
        self.raw[operations.PROBE_RECEIPT] = canonical(self.probe_value)
        self.ops.inputs['PROBE']['receipt_sha256'] = digest(self.raw[operations.PROBE_RECEIPT])
        with self.assertRaisesRegex(Denied, 'PROBE_HISTORICAL_RESULT'):
            self.ops.inherited('PROBE')
        self.assert_no_writers()

    def test_account_live_security_postcondition_drift_rejects_complete_checkpoint(self):
        cp = self.ops.inherited('ACCOUNT')
        self.post['shell'] = '/bin/bash'
        with self.assertRaisesRegex(Denied, 'ACCOUNT_LIVE_POSTCONDITION'):
            self.ops.verify('ACCOUNT', cp)
        self.assert_no_writers()

    def test_created_account_uid_gid_cannot_drift_within_otherwise_valid_range(self):
        self.post.update(uid=1002, gid=1002, group_gid=1002)
        with self.assertRaisesRegex(Denied, 'ACCOUNT_CREATED_IDENTITY_DRIFT'):
            self.ops.inherited('ACCOUNT')
        self.assert_no_writers()

    def test_account_platform_hash_drift_rejects_live_proof(self):
        self.platform['uid_max'] = 2999
        with self.assertRaisesRegex(Denied, 'ACCOUNT_PLATFORM_DRIFT'):
            self.ops.inherited('ACCOUNT')

    def test_runtime_requires_original_completed_stage_record(self):
        self.coordinator.data['stage_records'] = self.coordinator.data['stage_records'][:1]
        with self.assertRaisesRegex(Denied, 'CHILD_SUCCESS_RECEIPT_REQUIRED'):
            self.ops.inherited('RUNTIME')

    def test_runtime_completed_tree_is_rechecked_instead_of_reused(self):
        cp = self.ops.inherited('RUNTIME')
        self.runtime_tree['foreign'] = {'sha256': 'e' * 64, 'mode': 0o755}
        with self.assertRaisesRegex(Denied, 'COMPLETED_CLOSURE_DRIFT'):
            self.ops.verify('RUNTIME', cp)
        self.assert_no_writers()

    def test_runtime_root_inode_and_source_closure_are_live_pinned(self):
        cp = self.ops.inherited('RUNTIME')
        self.root_info.st_ino = 99
        with self.assertRaisesRegex(Denied, 'ROOT_IDENTITY_DRIFT'):
            self.ops.verify('RUNTIME', cp)
        self.root_info.st_ino = 2
        operations.runtime._source_identity.return_value = 'e' * 64
        with self.assertRaisesRegex(Denied, 'SOURCE_CLOSURE_DRIFT'):
            self.ops.verify('RUNTIME', cp)
        self.assert_no_writers()

    def test_policy_completed_bytes_and_original_backups_are_live_pinned(self):
        cp = self.ops.inherited('POLICY_RESTORE')
        self.bootstrap_raw[operations.bootstrap.POLICY] = b'foreign policy'
        with self.assertRaisesRegex(Denied, 'COMPLETED_BYTES_DRIFT'):
            self.ops.verify('POLICY_RESTORE', cp)
        self.bootstrap_raw[operations.bootstrap.POLICY] = operations.bootstrap.expected_policy()
        self.bootstrap_raw[operations.bootstrap.CONTROL / 'old-sudoers'] = b'foreign backup'
        with self.assertRaisesRegex(Denied, 'POLICY_BACKUP_DRIFT'):
            self.ops.verify('POLICY_RESTORE', cp)
        self.assert_no_writers()

    def test_policy_completion_receipt_shape_is_exact(self):
        self.bootstrap_raw[operations.bootstrap.CONTROL / 'ROLLED_BACK.json'] = b'{"state":"ROLLED_BACK","extra":true}'
        with self.assertRaisesRegex(Denied, 'POLICY_COMPLETION_RECEIPT'):
            self.ops.inherited('POLICY_RESTORE')

    def test_channel_completed_code_and_grant_are_live_verified(self):
        cp = self.ops.inherited('CHANNEL_REBIND')
        self.channel_raw[operations.channel.BASE / 'channel.py'] = b'foreign code'
        with self.assertRaisesRegex(Denied, 'CHANNEL_COMPLETED_DRIFT'):
            self.ops.verify('CHANNEL_REBIND', cp)
        self.channel_raw[operations.channel.BASE / 'channel.py'] = self.channel_code
        self.channel_raw[operations.channel.BASE / 'grant-state.json'] = b'{"state":"UPGRADING"}'
        with self.assertRaisesRegex(Denied, 'CHANNEL_COMPLETED_DRIFT'):
            self.ops.verify('CHANNEL_REBIND', cp)
        self.assert_no_writers()

    def test_channel_complete_receipt_requires_this_exact_forward_only_permission(self):
        self.channel_receipt['approval']['rollback_approved'] = True
        self.channel_raw[operations.channel.CONTROL / 'receipt.json'] = operations.channel.canonical(self.channel_receipt)
        with self.assertRaisesRegex(Denied, 'CHANNEL_SAME_WORKFLOW_PERMISSION'):
            self.ops.inherited('CHANNEL_REBIND')
        self.assert_no_writers()

    def test_channel_backup_and_policy_verifiers_are_required_for_completion(self):
        operations.channel.backup_verify.side_effect = RuntimeError('HOLD:BACKUP_DRIFT')
        with self.assertRaisesRegex(RuntimeError, 'BACKUP_DRIFT'):
            self.ops.inherited('CHANNEL_REBIND')
        operations.channel.verify_policy.assert_called_once_with(self.channel_plan)
        self.assert_no_writers()

    def test_customer_receipt_requires_success_and_same_workflow_approval(self):
        self.customer_receipt['state'] = 'HOLD_UNKNOWN_OR_PARTIAL'
        with self.assertRaisesRegex(Denied, 'CUSTOMER_COMPLETION_REQUIRED'):
            self.ops.inherited('CUSTOMER_APPLY')
        self.journal.reconcile.assert_not_called()
        self.assert_no_writers()

    def test_customer_complete_checkpoint_rechecks_journal_and_context_without_mutating(self):
        self.assertEqual(self.ops.inherited('CUSTOMER_APPLY'), self.customer_cp)
        operations.resume.context.assert_called_once()
        self.journal.reconcile.assert_called_once_with()
        proof = operations.resume.Journal.call_args.kwargs['workflow_lease']
        proof.assert_fence()
        self.coordinator.assert_fence.assert_called_once_with()
        with self.assertRaisesRegex(Denied, 'CUSTOMER_PROOF_SCOPE'):
            proof.stage_contract('ACCOUNT')
        self.journal.reconcile.side_effect = Denied('HOLD:OWNED_FILE_DRIFT')
        with self.assertRaisesRegex(Denied, 'OWNED_FILE_DRIFT'):
            self.ops.verify('CUSTOMER_APPLY', self.customer_cp)
        self.assert_no_writers()

    def test_customer_completed_static_plan_must_match_exact_approved_context(self):
        self.customer_receipt['plan']['fixture_static_context'] = 'changed'
        with self.assertRaisesRegex(Denied, 'CUSTOMER_COMPLETED_PLAN_BINDING'):
            self.ops.inherited('CUSTOMER_APPLY')
        self.journal.reconcile.assert_not_called()
        self.assert_no_writers()

    def test_customer_static_plan_cannot_smuggle_dynamic_account_or_runtime_fields(self):
        for field in operations.customer.DYNAMIC_FIELDS:
            with self.subTest(field=field):
                self.ops.inputs['CUSTOMER_APPLY']['static_plan'][field] = self.customer_receipt['plan'][field]
                with self.assertRaisesRegex(Denied, 'CUSTOMER_COMPLETED_PLAN_BINDING'):
                    self.ops.inherited('CUSTOMER_APPLY')
                del self.ops.inputs['CUSTOMER_APPLY']['static_plan'][field]
        self.journal.reconcile.assert_not_called()
        self.assert_no_writers()

    def test_customer_completed_source_commit_and_manifest_hash_are_freshly_bound(self):
        for manifest, raw in [({'source_commit': 'f' * 40}, b'fixture manifest'),
                              ({'source_commit': self.plan['source_commit']}, b'changed manifest')]:
            with self.subTest(manifest=manifest, raw=raw):
                self.release.source.return_value = (manifest, raw, {'boot.py': b'fixed bytes'})
                with self.assertRaisesRegex(Denied, 'CUSTOMER_COMPLETED_SOURCE_BINDING'):
                    self.ops.inherited('CUSTOMER_APPLY')
        self.journal.reconcile.assert_not_called()
        self.assert_no_writers()

    def test_all_proven_completed_reconciliations_are_readonly(self):
        for stage in STAGES[:-1]:
            with self.subTest(stage=stage):
                proof = self.recover(stage)
                self.assert_proof(proof, 'COMPLETE')
                self.assertEqual(proof['checkpoint'], self.ops.inherited(stage))

    def test_no_effect_account_recovery_requires_absent_user_group_and_original_receipt(self):
        self.invalidate_observation()
        self.assert_proof(self.recover('ACCOUNT'), 'SAFE_TO_RETRY')
        self.account_os.getpwnam.side_effect = None
        self.account_os.getpwnam.return_value = object()
        self.assert_proof(self.recover('ACCOUNT'), 'UNKNOWN')
        self.account_os.getpwnam.side_effect = KeyError('absent')
        self.existing.add(Path(operations.account.ACCOUNT_RECEIPT))
        self.assert_proof(self.recover('ACCOUNT'), 'UNKNOWN')

    def test_no_effect_account_recovery_does_not_ignore_preexisting_group(self):
        self.invalidate_observation()
        self.account_os.getgrnam.side_effect = None
        self.account_os.getgrnam.return_value = object()
        self.assert_proof(self.recover('ACCOUNT'), 'UNKNOWN')

    def test_runtime_absent_may_retry_but_present_unknown_tree_is_never_deleted(self):
        self.invalidate_observation()
        self.assert_proof(self.recover('RUNTIME'), 'SAFE_TO_RETRY')
        self.existing.add(operations.runtime.PROTECTED_RUNTIME)
        self.assert_proof(self.recover('RUNTIME'), 'UNKNOWN')

    def test_channel_no_effect_recovery_requires_absent_transaction_and_same_exact_plan(self):
        self.invalidate_observation()
        self.assert_proof(self.recover('CHANNEL_REBIND'), 'SAFE_TO_RETRY')
        operations.channel.plan.assert_called_with(expected_zip_sha256=self.inputs['stages']['CHANNEL_REBIND']['zip_sha256'])
        self.channel_plan['drift'] = True
        self.assert_proof(self.recover('CHANNEL_REBIND'), 'UNKNOWN')
        self.existing.add(operations.channel.CONTROL)
        self.assert_proof(self.recover('CHANNEL_REBIND'), 'UNKNOWN')

    def test_policy_exact_partial_bytes_can_retry_without_restoring_during_proof(self):
        self.invalidate_observation()
        self.bootstrap_raw[operations.bootstrap.POLICY] = operations.bootstrap.new_policy()
        self.assert_proof(self.recover('POLICY_RESTORE'), 'SAFE_TO_RETRY')
        self.bootstrap_raw[operations.bootstrap.EXEC] = b'foreign wrapper'
        self.assert_proof(self.recover('POLICY_RESTORE'), 'UNKNOWN')

    def test_unproven_probe_is_unknown_and_never_rerun(self):
        self.invalidate_observation()
        self.assert_proof(self.recover('PROBE'), 'UNKNOWN')
        with self.assertRaisesRegex(Denied, 'EXISTING_SUCCESSFUL_PROBE_PIN_REQUIRED'):
            self.ops.execute('PROBE', self.lease)
        self.assert_no_writers()

    def test_customer_recovery_is_delegated_to_original_fixed_customer_proof(self):
        proof = self.recover('CUSTOMER_APPLY')
        self.assert_proof(proof, 'UNKNOWN')
        operations.customer.reconcile.assert_called_once_with(self.lease, self.release, self.folder)

    def test_recovery_checks_fence_and_authority_before_observing_or_deciding(self):
        self.lease.assert_fence.side_effect = Denied('HOLD:STALE_FENCE')
        with self.assertRaisesRegex(Denied, 'STALE_FENCE'):
            self.recover('ACCOUNT')
        self.account_os.platform_preconditions.assert_not_called()
        self.assert_no_writers()

    def test_execute_routes_each_remaining_stage_to_only_its_original_writer(self):
        for index, stage in enumerate(STAGES[1:]):
            with self.subTest(stage=stage), patch.object(self.ops, '_observe', return_value=self.customer_cp):
                self.assertEqual(self.ops.execute(stage, self.lease), self.customer_cp)
            self.writers[index].assert_called_once()
        operations.preparation.account_once.assert_called_once_with(self.lease)
        operations.runtime_stage.rebuild_runtime.assert_called_once_with(self.lease)
        operations.preparation.restore_policy.assert_called_once_with(self.lease)
        operations.channel.apply_for_workflow.assert_called_once_with(self.lease)
        operations.customer.execute.assert_called_once_with(self.lease, self.release, self.folder)
        self.release.run.assert_not_called()

    def test_stale_execute_lease_prevents_any_original_writer_call(self):
        self.lease.assert_active.side_effect = Denied('HOLD:STALE_STAGE')
        with self.assertRaisesRegex(Denied, 'STALE_STAGE'):
            self.ops.execute('ACCOUNT', self.lease)
        self.assert_no_writers()

    def test_real_coordinator_and_concrete_adapters_share_one_budget_across_runtime_retry(self):
        """Real coordinator/ledger plus concrete adapter routing; writers mocked."""
        from scripts import pr122_customer_release as release
        from scripts import pr122_customer_attempts as attempts
        from scripts import pr122_customer_workflow as workflow
        from tests.test_pr122_customer_release import ReleaseTests

        def read_bytes(path):
            path = Path(path)
            return self.raw[path] if path in self.raw else self.original_read_bytes(path)

        def lstat(path, *args, **kwargs):
            if Path(path) == operations.runtime.PROTECTED_RUNTIME:
                return self.root_info
            return self.original_lstat(path, *args, **kwargs)

        host_targets = {Path(operations.account.ACCOUNT_RECEIPT),
                        operations.runtime.PROTECTED_RUNTIME, operations.channel.CONTROL}

        def lexists(path):
            path = Path(path)
            return path in self.existing if path in host_targets else self.original_lexists(path)

        with patch.object(Path, 'read_bytes', read_bytes), \
                patch.object(operations.os, 'lstat', lstat), \
                patch.object(operations.os.path, 'lexists', lexists):
            fixture = ReleaseTests()
            fixture.setUp()
            try:
                self.release, self.folder = release, fixture.source
                actual_ops = operations.OriginalOperations(release, fixture.source, fixture.base, self.inputs)
                fixture.base['workflow_contract'] = {'schema': 1, 'stages': [{
                    'stage': stage, 'input_sha256': digest(canonical(actual_ops.input(stage))),
                    'implementation_sha256': digest(actual_ops.implementation(stage)),
                    'adopt_receipt_sha256': digest(self.raw[operations.PROBE_RECEIPT]) if stage == 'PROBE' else None,
                    'recovery_actions': sorted(workflow.RECOVERY[stage]),
                } for stage in STAGES]}
                fixture.approval.update(attempt_policy=POLICY, max_executions=5,
                    workflow_contract_sha256=digest(canonical(fixture.base['workflow_contract'])),
                    plan_sha256=digest(canonical(fixture.base)))
                self.customer_receipt['approval'] = copy.deepcopy(fixture.approval)
                self.channel_receipt['approval']['workflow_approval_sha256'] = digest(canonical(fixture.approval))
                self.channel_raw[operations.channel.CONTROL / 'receipt.json'] = operations.channel.canonical(self.channel_receipt)
                runtime_attempts = []
                customer_attempts = []

                def account_writer(lease):
                    lease.assert_active()
                    lease.record_stage('ACCOUNT', 'ACCOUNT_VERIFIED', {'uid': 1001, 'gid': 1001})

                def runtime_writer(lease):
                    lease.assert_active()
                    runtime_attempts.append(lease.active['number'])
                    if len(runtime_attempts) == 1:
                        raise RuntimeError('fixture no-effect runtime failure')
                    lease.record_stage('RUNTIME', 'RUNTIME_VERIFIED', copy.deepcopy(self.runtime_report))

                def customer_writer(lease, supplied_release, folder):
                    lease.assert_active()
                    self.assertIs(supplied_release, release)
                    self.assertEqual(folder, fixture.source)
                    customer_attempts.append(lease.active['number'])
                    return copy.deepcopy(self.customer_cp)

                operations.preparation.account_once.side_effect = account_writer
                operations.runtime_stage.rebuild_runtime.side_effect = runtime_writer
                operations.customer.execute.side_effect = customer_writer
                with fixture.patches(), \
                        patch.object(workflow, 'protected_directory', lambda path: None), \
                        patch.object(workflow, 'read_private', lambda path: json.loads(Path(path).read_bytes())), \
                        patch.object(attempts, 'Attempts', side_effect=AssertionError('Nested attempt ledger forbidden')) as nested, \
                        patch.object(release.subprocess, 'run', side_effect=AssertionError('Real commands forbidden')):
                    result = release.workflow_apply(fixture.source, 4, fixture.base, actual_ops)
                self.assertEqual(result['state'], 'SUCCESS')
                self.assertEqual(result['attempts_used'], 2)
                self.assertEqual(runtime_attempts, [1, 2])
                self.assertEqual(customer_attempts, [2])
                operations.preparation.account_once.assert_called_once()
                operations.preparation.restore_policy.assert_called_once()
                operations.channel.apply_for_workflow.assert_called_once()
                operations.customer.execute.assert_called_once()
                nested.assert_not_called()
                ledger_path = release.STATE / (release.TXN + '.attempts.json')
                ledger = json.loads(ledger_path.read_bytes())
                self.assertEqual([row['state'] for row in ledger['attempts']], ['FAILED_HOLD', 'SUCCESS'])
                self.assertEqual(ledger['failures'][0]['stage'], 'RUNTIME')
                self.assertEqual(ledger['recoveries'][0]['status'], 'SAFE_TO_RETRY')
                self.assertEqual(ledger['checkpoints']['PROBE']['receipt_sha256'], digest(self.raw[operations.PROBE_RECEIPT]))
                self.assertEqual(ledger['checkpoints']['ACCOUNT']['receipt_sha256'], digest(self.account_receipt))
                self.assertEqual(list(release.STATE.iterdir()), [ledger_path])
            finally:
                fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
