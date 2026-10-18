"""Offline bridge tests: original account/policy/runtime writers are mocked.

These tests cover binding and delegation, never host account creation, security
settings, subprocesses, runtime generation, or real source-closure attestation.
"""
import copy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import pr122_customer_preparation as preparation
from scripts import pr122_customer_runtime_stage as runtime_stage
from scripts import pr122_customer_runtime as runtime
from scripts.pr122_customer_core import Denied, canonical, digest
from scripts.pr122_customer_workflow import POLICY


class FakeLease:
    def __init__(self, stage, inputs, module):
        self.stage, self.live = stage, True
        self.inputs = copy.deepcopy(inputs)
        self.input_pin = digest(canonical(inputs))
        self.implementation_pin = digest(Path(module.__file__).read_bytes())
        self.approval = {'attempt_policy': POLICY}
        self.plan = {'source_commit': 'a' * 40}
        receipt = digest(b'verified account child receipt')
        self.identity = {'uid': 1201, 'gid': 1202, 'receipt_sha256': receipt}
        self.data = {'checkpoints': {'ACCOUNT': {
            'state': 'COMPLETE', 'receipt_sha256': receipt,
            'effect_sha256': digest(b'verified account effect'), 'source_commit': 'a' * 40}}}
        self.events = []
        self.ops = SimpleNamespace(input=self.input, account_identity=self.account_identity)

    def input(self, stage):
        if stage != self.stage:
            raise Denied('HOLD:WORKFLOW_CHILD_STAGE')
        return copy.deepcopy(self.inputs)

    def account_identity(self):
        return copy.deepcopy(self.identity)

    def assert_active(self):
        if not self.live:
            raise Denied('HOLD:WORKFLOW_STALE_CHILD_LEASE')

    def assert_fence(self):
        self.assert_active()

    def authority(self):
        self.assert_active()

    def verify_inputs(self, stage):
        if stage != self.stage or digest(canonical(self.inputs)) != self.input_pin:
            raise Denied('HOLD:WORKFLOW_STAGE_INPUT_DRIFT')

    def stage_contract(self, stage):
        self.verify_inputs(stage)
        return {'implementation_sha256': self.implementation_pin,
                'recovery_actions': ['RECONCILE_POLICY']}

    def record_stage(self, stage, phase, metadata):
        self.assert_active()
        if stage != self.stage:
            raise Denied('HOLD:WORKFLOW_CHILD_STAGE')
        self.events.append((stage, phase, copy.deepcopy(metadata)))


class FakeAccountOS:
    def __init__(self, platform):
        self.platform = copy.deepcopy(platform)
        self.mutations = []

    def platform_preconditions(self):
        return copy.deepcopy(self.platform)

    def reserve_original_evidence(self, path):
        self.mutations.append(('reserve', path))

    def record_original_evidence(self, path, state):
        self.mutations.append(('record', path, state))

    def run_fixed_useradd(self, argv):
        self.mutations.append(('useradd', tuple(argv)))
        return 0


class PreparationBridgeTests(unittest.TestCase):
    def setUp(self):
        forbidden = patch.object(runtime.subprocess, 'run',
                                 side_effect=AssertionError('Actual subprocess forbidden'))
        forbidden.start()
        self.addCleanup(forbidden.stop)
        self.platform = {'fixed_useradd_flags_supported': True,
                         'uid_min': 100, 'uid_max': 999,
                         'gid_min': 100, 'gid_max': 999}
        self.account_inputs = {'account': preparation.account.ACCOUNT,
                               'argv_sha256': digest(canonical(list(preparation.account.PROPOSED_ARGV))),
                               'platform_sha256': digest(canonical(self.platform))}

    def account_lease(self):
        return FakeLease('ACCOUNT', self.account_inputs, preparation.account)

    def runtime_lease(self):
        template = {
            'schema': 1, 'host': runtime.FIXED_HOST, 'source_commit': 'a' * 40,
            'runtime_module_sha256': digest(Path(runtime.__file__).read_bytes()),
            'wheel_directory': '/offline/reviewed/wheels',
            'interpreter_sha256': runtime.INTERPRETER_SHA256,
            'stdlib_trees': {'/usr/lib/python3.11': {'os.py': 'b' * 64}},
            'native_files': {'/lib64/libc.so.6': 'c' * 64},
            'abi': {'python': '3.11', 'machine': 'x86_64', 'glibc_min': '2.34'},
            'expected_venv_tree': {
                'venv/bin/python': {'kind': 'file', 'sha256': runtime.INTERPRETER_SHA256, 'mode': 0o755},
                'venv/pyvenv.cfg': {'kind': 'file', 'sha256': 'd' * 64, 'mode': 0o644}},
            'account_uid': None, 'account_gid': None,
        }
        return FakeLease('RUNTIME', {'runtime_template': template,
                                    'account_binding': 'VERIFIED_ACCOUNT_CHECKPOINT'}, runtime)

    def test_runtime_module_matches_reviewed_per_mutation_lease_guard_revision(self):
        self.assertEqual(digest(Path(runtime.__file__).read_bytes()),
                         '6665f91739d3339df4839dab78b1dc8e47332f900c2345da688a994ee9540ba9')

    def test_account_delegates_original_writer_and_preserves_success_evidence(self):
        lease = self.account_lease()
        ops = FakeAccountOS(self.platform)
        result = {'state': 'ACCOUNT_CREATED_VERIFIED', 'uid': 1201, 'gid': 1202,
                  'retry_allowed': False}
        with patch.object(preparation.account, 'OS', return_value=ops), \
                patch.object(preparation.account, 'create_once', return_value=result) as writer:
            self.assertEqual(preparation.account_once(lease), result)
        writer.assert_called_once()
        self.assertEqual([event[1] for event in lease.events],
                         ['ACCOUNT_CREATE_INTENT', 'ACCOUNT_VERIFIED'])
        self.assertEqual(ops.mutations, [])

    def test_account_fixed_argv_platform_module_and_lease_drift_block_writer(self):
        for case in ('argv', 'platform', 'module', 'lease', 'scope'):
            with self.subTest(case=case):
                lease = self.account_lease()
                if case == 'argv':
                    lease.inputs['argv_sha256'] = 'f' * 64
                    lease.input_pin = digest(canonical(lease.inputs))
                elif case == 'platform':
                    lease.inputs['platform_sha256'] = 'f' * 64
                    lease.input_pin = digest(canonical(lease.inputs))
                elif case == 'module': lease.implementation_pin = 'f' * 64
                elif case == 'lease': lease.live = False
                else: lease.approval['attempt_policy'] = 'CONTROLLED_INSTALL_RESUME_V2'
                with patch.object(preparation.account, 'OS', return_value=FakeAccountOS(self.platform)), \
                        patch.object(preparation.account, 'create_once') as writer, self.assertRaises(Denied):
                    preparation.account_once(lease)
                writer.assert_not_called()

    def test_account_failure_records_unknown_without_retry_or_deletion(self):
        lease = self.account_lease()
        error = OSError('offline original writer failure')
        with patch.object(preparation.account, 'OS', return_value=FakeAccountOS(self.platform)), \
                patch.object(preparation.account, 'create_once', side_effect=error) as writer:
            with self.assertRaises(OSError) as caught:
                preparation.account_once(lease)
        self.assertIs(caught.exception, error)
        writer.assert_called_once()
        self.assertEqual(lease.events[-1], ('ACCOUNT', 'ACCOUNT_UNKNOWN_PRESERVE', {'retry_allowed': False}))

    def test_expiry_inside_original_account_preflight_blocks_fixed_useradd(self):
        lease = self.account_lease()
        ops = FakeAccountOS(self.platform)

        def original_writer(adapter):
            lease.live = False  # Simulate expiry during original locked preflight.
            adapter.run_fixed_useradd(preparation.account.PROPOSED_ARGV)
            return {'state': 'ACCOUNT_CREATED_VERIFIED'}

        with patch.object(preparation.account, 'OS', return_value=ops), \
                patch.object(preparation.account, 'create_once', original_writer):
            with self.assertRaises(Denied):
                preparation.account_once(lease)
        self.assertEqual(ops.mutations, [])

    def test_account_platform_drift_inside_original_lock_blocks_writer(self):
        lease = self.account_lease()
        ops = FakeAccountOS(self.platform)

        def original_writer(adapter):
            ops.platform['uid_max'] += 100  # Valid values, different approved contract.
            adapter.platform_preconditions()
            adapter.run_fixed_useradd(preparation.account.PROPOSED_ARGV)
            return {'state': 'ACCOUNT_CREATED_VERIFIED'}

        with patch.object(preparation.account, 'OS', return_value=ops), \
                patch.object(preparation.account, 'create_once', original_writer):
            with self.assertRaisesRegex(Denied, 'PLATFORM'):
                preparation.account_once(lease)
        self.assertEqual(ops.mutations, [])

    def test_expiry_during_last_platform_read_prevents_useradd(self):
        lease = self.account_lease()
        ops = FakeAccountOS(self.platform)
        reads = []

        def platform_read():
            reads.append(True)
            if len(reads) == 2:
                lease.live = False
            return copy.deepcopy(self.platform)

        def original_writer(adapter):
            adapter.run_fixed_useradd(preparation.account.PROPOSED_ARGV)
            return {'state': 'ACCOUNT_CREATED_VERIFIED'}

        with patch.object(ops, 'platform_preconditions', platform_read), \
                patch.object(preparation.account, 'OS', return_value=ops), \
                patch.object(preparation.account, 'create_once', original_writer):
            with self.assertRaises(Denied):
                preparation.account_once(lease)
        self.assertEqual(len(reads), 2)
        self.assertEqual(ops.mutations, [])

    def test_preparation_guard_rechecks_lease_after_authority_reads(self):
        lease = self.account_lease()

        def expire_during_authority():
            lease.live = False

        with patch.object(lease, 'authority', expire_during_authority), self.assertRaises(Denied):
            preparation._guard(lease, 'ACCOUNT', preparation.account)

    def test_stale_account_lease_cannot_reserve_or_append_original_evidence(self):
        for method, arguments in (
            ('reserve_original_evidence', (preparation.account.ACCOUNT_RECEIPT,)),
            ('record_original_evidence', (preparation.account.ACCOUNT_RECEIPT, 'ACCOUNT_CREATE_INTENT_NO_RETRY')),
        ):
            with self.subTest(method=method):
                lease = self.account_lease()
                ops = FakeAccountOS(self.platform)

                def original_writer(adapter):
                    lease.live = False
                    getattr(adapter, method)(*arguments)
                    return {'state': 'ACCOUNT_CREATED_VERIFIED'}

                with patch.object(preparation.account, 'OS', return_value=ops), \
                        patch.object(preparation.account, 'create_once', original_writer), self.assertRaises(Denied):
                    preparation.account_once(lease)
                self.assertEqual(ops.mutations, [])

    def test_policy_delegates_only_original_restore_and_checks_exact_module(self):
        lease = FakeLease('POLICY_RESTORE', {'fixture': 'approved backups'}, preparation.bootstrap)
        result = {'state': 'ROLLED_BACK', 'evidence_retained': True}
        with patch.object(preparation.bootstrap, 'restore_for_workflow', return_value=result) as writer:
            self.assertEqual(preparation.restore_policy(lease), result)
            writer.assert_called_once_with(lease)
        lease.implementation_pin = 'f' * 64
        with patch.object(preparation.bootstrap, 'restore_for_workflow') as writer, self.assertRaises(Denied):
            preparation.restore_policy(lease)
        writer.assert_not_called()

    def test_cross_stage_lease_never_reaches_account_policy_or_runtime_writer(self):
        lease = FakeLease('PROBE', {}, preparation.account)
        with patch.object(preparation.account, 'create_once') as account_writer, \
                patch.object(preparation.bootstrap, 'restore_for_workflow') as policy_writer, \
                patch.object(runtime, 'protected_rebuild') as runtime_writer:
            for operation in (preparation.account_once, preparation.restore_policy, runtime_stage.rebuild_runtime):
                with self.subTest(operation=operation.__name__), self.assertRaises(Denied):
                    operation(lease)
        account_writer.assert_not_called()
        policy_writer.assert_not_called()
        runtime_writer.assert_not_called()

    def test_runtime_derives_only_account_selectors_and_forwards_exact_reviewed_closure(self):
        lease = self.runtime_lease()
        original = copy.deepcopy(lease.inputs)
        captured = []

        def original_writer(contract, bridge):
            bridge.authorize_runtime(contract)
            bridge.assert_locked()
            captured.append(copy.deepcopy(contract))
            bridge.record_runtime('RUNTIME_CREATE_INTENT', {'contract_sha256': digest(canonical(contract))})
            result = {'state': 'PROTECTED_RUNTIME_REBUILT_VERIFIED', 'retry_allowed': False}
            bridge.record_runtime('RUNTIME_VERIFIED', result)
            return result

        with patch.object(runtime, 'protected_rebuild', original_writer):
            result = runtime_stage.rebuild_runtime(lease)
        expected = copy.deepcopy(original['runtime_template'])
        expected.update(account_uid=1201, account_gid=1202)
        self.assertEqual(captured, [expected])
        self.assertEqual(lease.inputs, original)
        self.assertEqual(result['state'], 'PROTECTED_RUNTIME_REBUILT_VERIFIED')
        self.assertEqual([event[1] for event in lease.events], ['RUNTIME_CREATE_INTENT', 'RUNTIME_VERIFIED'])

    def test_runtime_absent_or_mismatched_account_receipt_and_invalid_ids_block_writer(self):
        for case in ('absent', 'receipt', 'uid_zero', 'uid_bool', 'gid_negative', 'fixed_uid', 'missing_uid'):
            with self.subTest(case=case):
                lease = self.runtime_lease()
                if case == 'absent': lease.data['checkpoints'].clear()
                elif case == 'receipt': lease.identity['receipt_sha256'] = 'f' * 64
                elif case == 'uid_zero': lease.identity['uid'] = 0
                elif case == 'uid_bool': lease.identity['uid'] = True
                elif case == 'gid_negative': lease.identity['gid'] = -1
                elif case == 'fixed_uid':
                    lease.inputs['runtime_template']['account_uid'] = 1201
                    lease.input_pin = digest(canonical(lease.inputs))
                else:
                    lease.inputs['runtime_template'].pop('account_uid')
                    lease.input_pin = digest(canonical(lease.inputs))
                with patch.object(runtime, 'protected_rebuild') as writer, self.assertRaises(Denied):
                    runtime_stage.rebuild_runtime(lease)
                writer.assert_not_called()

    def test_runtime_module_source_and_active_lease_binding_block_writer(self):
        for case in ('implementation', 'template_module', 'source', 'scope', 'lease'):
            with self.subTest(case=case):
                lease = self.runtime_lease()
                if case == 'implementation': lease.implementation_pin = 'f' * 64
                elif case == 'template_module':
                    lease.inputs['runtime_template']['runtime_module_sha256'] = 'f' * 64
                    lease.input_pin = digest(canonical(lease.inputs))
                elif case == 'source':
                    lease.inputs['runtime_template']['source_commit'] = 'f' * 40
                    lease.input_pin = digest(canonical(lease.inputs))
                elif case == 'scope': lease.approval['attempt_policy'] = 'CONTROLLED_INSTALL_RESUME_V2'
                else: lease.live = False
                with patch.object(runtime, 'protected_rebuild') as writer, self.assertRaises(Denied):
                    runtime_stage.rebuild_runtime(lease)
                writer.assert_not_called()

    def test_runtime_repeated_authorization_rejects_identity_input_and_closure_drift(self):
        for case in ('identity', 'input', 'closure'):
            with self.subTest(case=case):
                lease = self.runtime_lease()
                bridge = runtime_stage.RuntimeStage(lease)
                contract = copy.deepcopy(bridge.contract)
                if case == 'identity': lease.identity['uid'] += 1
                elif case == 'input': lease.inputs['runtime_template']['native_files'] = {}
                else: contract['stdlib_trees'] = {}
                with self.assertRaises(Denied):
                    bridge.authorize_runtime(contract)

    def test_original_runtime_missing_closure_error_and_failure_evidence_are_preserved(self):
        # Complete live closure verification belongs to protected_rebuild. This
        # mock models that original guard's rejection; it does not attest a host.
        lease = self.runtime_lease()
        lease.inputs['runtime_template']['stdlib_trees'] = {}
        lease.input_pin = digest(canonical(lease.inputs))
        error = runtime.Denied('REVIEWED_SOURCE_CLOSURE_REQUIRED')

        def original_guard(contract, bridge):
            bridge.record_runtime('RUNTIME_UNKNOWN_PRESERVE', {'retry_allowed': False})
            raise error

        with patch.object(runtime, 'protected_rebuild', original_guard):
            with self.assertRaises(runtime.Denied) as caught:
                runtime_stage.rebuild_runtime(lease)
        self.assertIs(caught.exception, error)
        self.assertEqual(lease.events[-1], ('RUNTIME', 'RUNTIME_UNKNOWN_PRESERVE', {'retry_allowed': False}))


if __name__ == '__main__':
    unittest.main()
