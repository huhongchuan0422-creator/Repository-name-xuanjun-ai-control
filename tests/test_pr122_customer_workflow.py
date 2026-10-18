"""Offline fixed-stage coordinator tests, not production adapter acceptance.

The stage operations below are deliberately fake. These tests prove coordinator
bookkeeping and guards only; no account, runtime, policy, channel or target-host
integration is implemented or exercised by this fixture.
"""
import copy
import errno
import fcntl
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pr122_customer_release as r
from scripts import pr122_customer_workflow as workflow
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_customer_release as release_tests


class OfflineOperations:
    """Explicit test double for the six trusted-adapter methods."""

    def __init__(self):
        self.inputs = {stage: {'stage': stage, 'fixture_revision': 1}
                       for stage in workflow.STAGES}
        self.implementations = {stage: ('offline implementation ' + stage).encode()
                                for stage in workflow.STAGES}
        self.receipts = {stage: {
            'state': 'COMPLETE', 'receipt_sha256': digest(('receipt ' + stage).encode()),
            'effect_sha256': digest(('effect ' + stage).encode()), 'source_commit': 'a' * 40,
        } for stage in workflow.STAGES}
        self.executed, self.verified, self.adopted, self.reconciled = [], [], [], []
        self.execute_hook = self.verify_hook = self.reconcile_hook = None
        self.proof_status = 'UNKNOWN'

    def input(self, stage):
        return copy.deepcopy(self.inputs[stage])

    def implementation(self, stage):
        return self.implementations[stage]

    def inherited(self, stage):
        self.adopted.append(stage)
        return copy.deepcopy(self.receipts[stage])

    def verify(self, stage, checkpoint):
        self.verified.append((stage, copy.deepcopy(checkpoint)))
        if self.verify_hook:
            value = self.verify_hook(stage, checkpoint)
            if value is not None:
                return value
        return checkpoint == self.receipts[stage]

    def execute(self, stage, lease):
        lease.assert_active()
        self.executed.append((stage, lease.active['number']))
        if self.execute_hook:
            value = self.execute_hook(stage, lease)
            if value is not None:
                return value
        return copy.deepcopy(self.receipts[stage])

    def proof(self, stage, status=None):
        status = status or self.proof_status
        return {'status': status, 'action': sorted(workflow.RECOVERY[stage])[0],
                'evidence_sha256': digest(canonical({'stage': stage, 'proof': status})),
                'checkpoint': copy.deepcopy(self.receipts[stage]) if status == 'COMPLETE' else None}

    def reconcile(self, stage, intent, checkpoint, lease):
        lease.assert_fence()
        self.reconciled.append((stage, copy.deepcopy(intent), copy.deepcopy(checkpoint)))
        if self.reconcile_hook:
            value = self.reconcile_hook(stage, intent, checkpoint, lease)
            if value is not None:
                return value
        return self.proof(stage)


class WorkflowTests(unittest.TestCase):
    # Reuse fixture methods, never inherit the original TestCase's test methods.
    inventory = release_tests.ReleaseTests.inventory
    patches = release_tests.ReleaseTests.patches

    def setUp(self):
        release_tests.ReleaseTests.setUp(self)
        del self.fail  # The original fixture's selector shadows TestCase.fail.
        self.ops = OfflineOperations()
        self.base['workflow_contract'] = {'schema': 1, 'stages': [{
            'stage': stage, 'input_sha256': digest(canonical(self.ops.input(stage))),
            'implementation_sha256': digest(self.ops.implementation(stage)),
            'adopt_receipt_sha256': None, 'recovery_actions': sorted(workflow.RECOVERY[stage]),
        } for stage in workflow.STAGES]}
        self.approval.update(max_executions=5, attempt_policy=workflow.POLICY)
        self.bind_contract()
        for adapter in (
            patch.object(workflow, 'protected_directory', lambda path: None),
            patch.object(workflow, 'read_private', lambda path: json.loads(Path(path).read_bytes())),
            patch.object(r.subprocess, 'run', side_effect=AssertionError('Actual commands forbidden')),
        ):
            adapter.start()
            self.addCleanup(adapter.stop)

    def fake_run(self, args):
        raise AssertionError('Coordinator tests must not call release.run: ' + repr(args))

    def bind_contract(self):
        self.approval['workflow_contract_sha256'] = digest(canonical(self.base['workflow_contract']))
        self.approval['plan_sha256'] = digest(canonical(self.base))

    def apply(self, comment=4):
        return r.workflow_apply(self.source, comment, self.base, self.ops)

    def ledger_path(self):
        return r.STATE / (r.TXN + '.attempts.json')

    def ledger(self):
        return json.loads(self.ledger_path().read_bytes())

    def assert_ledger(self, states):
        data = self.ledger()
        self.assertEqual(data['schema'], 3)
        self.assertEqual(data['policy'], workflow.POLICY)
        self.assertEqual(data['binding']['transaction'], r.TXN)
        self.assertEqual(data['binding']['approval_comment'], 4)
        self.assertEqual(data['binding']['approval_sha256'], digest(canonical(self.approval)))
        self.assertEqual(data['binding']['plan_sha256'], digest(canonical(self.base)))
        self.assertEqual([row['state'] for row in data['attempts']], states)
        previous = None
        for number, row in enumerate(data['attempts'], 1):
            self.assertEqual(row['number'], number)
            self.assertEqual(row['previous_sha256'], previous)
            self.assertEqual(row['lease'], {'fence': number, 'expires_unix': self.approval['expires_unix'],
                                           'binding_sha256': digest(canonical(data['binding']))})
            previous = digest(canonical(row))
        return data

    def fail_stage(self, stage, count=None):
        failed = []

        def fail(current, _lease):
            if current == stage and (count is None or len(failed) < count):
                failed.append(True)
                raise RuntimeError('fixture stage failure')
        self.ops.execute_hook = fail
        return failed

    def held_at_runtime(self):
        self.fail_stage('RUNTIME')
        with self.patches(), self.assertRaises(workflow.WorkflowStopped) as caught:
            self.apply()
        self.assertEqual(caught.exception.summary['state'], 'HOLD')
        self.assert_ledger(['FAILED_HOLD'])

    def test_happy_chain_uses_one_original_ledger_attempt_and_exact_fixed_stages(self):
        permit = canonical(self.approval)
        with self.patches(), patch.object(r, 'gate', return_value=self.approval) as gate:
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 1)
        self.assertEqual(result['completed_stages'], list(workflow.STAGES))
        self.assertEqual(result['target_acceptance'], 'NOT_VERIFIED')
        self.assertEqual(self.ops.executed, [(stage, 1) for stage in workflow.STAGES])
        self.assertEqual(canonical(self.approval), permit)
        self.assertTrue(all(call.args == (4, self.base) for call in gate.call_args_list))
        self.assert_ledger(['SUCCESS'])
        self.assertEqual(list(r.STATE.iterdir()), [self.ledger_path()])
        self.assertFalse(r.CODE.exists())

    def test_whole_chain_retry_budget_is_five_total_not_five_per_stage(self):
        failed = set()
        self.ops.proof_status = 'SAFE_TO_RETRY'

        def one_failure_per_stage(stage, _lease):
            if stage not in failed:
                failed.add(stage)
                raise RuntimeError('fixture distinct stage cause')
        self.ops.execute_hook = one_failure_per_stage
        with self.patches(), self.assertRaises(workflow.WorkflowStopped) as caught:
            self.apply()
        result = caught.exception.summary
        self.assertEqual(result['state'], 'EXHAUSTED')
        self.assertEqual(result['attempts_used'], 5)
        self.assertEqual(len(result['failures']), 5)
        self.assertEqual([row['stage'] for row in result['failures']], list(workflow.STAGES[:5]))
        self.assertNotIn('CUSTOMER_APPLY', [stage for stage, _ in self.ops.executed])
        self.assert_ledger(['FAILED_HOLD'] * 5)

    def test_completed_earlier_stages_never_execute_again_across_multiple_failures(self):
        failures = {'RUNTIME': 2, 'CHANNEL_REBIND': 1}
        self.ops.proof_status = 'SAFE_TO_RETRY'

        def fail(stage, _lease):
            if failures.get(stage, 0):
                failures[stage] -= 1
                raise RuntimeError('fixture stage failure')
        self.ops.execute_hook = fail
        with self.patches():
            result = self.apply()
        self.assertEqual(result['attempts_used'], 4)
        self.assertEqual(self.ops.executed, [('PROBE', 1), ('ACCOUNT', 1), ('RUNTIME', 1),
                         ('RUNTIME', 2), ('RUNTIME', 3), ('POLICY_RESTORE', 3),
                         ('CHANNEL_REBIND', 3), ('CHANNEL_REBIND', 4), ('CUSTOMER_APPLY', 4)])
        self.assert_ledger(['FAILED_HOLD'] * 3 + ['SUCCESS'])

    def test_pinned_successful_probe_and_account_receipts_are_verified_and_skipped(self):
        for row in self.base['workflow_contract']['stages'][:2]:
            row['adopt_receipt_sha256'] = self.ops.receipts[row['stage']]['receipt_sha256']
        self.bind_contract()
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(self.ops.adopted, ['PROBE', 'ACCOUNT'])
        self.assertEqual(self.ops.executed, [(stage, 1) for stage in workflow.STAGES[2:]])
        self.assertTrue(all(stage in [name for name, _ in self.ops.verified] for stage in ('PROBE', 'ACCOUNT')))
        self.assert_ledger(['SUCCESS'])

    def test_exactly_pinned_old_source_probe_and_account_receipts_are_adopted(self):
        for row in self.base['workflow_contract']['stages'][:2]:
            self.ops.receipts[row['stage']]['source_commit'] = 'b' * 40
            row['adopt_receipt_sha256'] = self.ops.receipts[row['stage']]['receipt_sha256']
        self.bind_contract()
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(self.ops.adopted, ['PROBE', 'ACCOUNT'])
        self.assertEqual(self.ops.executed, [(stage, 1) for stage in workflow.STAGES[2:]])
        self.assertEqual(self.ledger()['checkpoints']['PROBE']['source_commit'], 'b' * 40)
        self.assertEqual(self.ledger()['checkpoints']['ACCOUNT']['source_commit'], 'b' * 40)
        self.assert_ledger(['SUCCESS'])

    def test_unpinned_old_source_receipt_cannot_be_a_completion_checkpoint(self):
        self.ops.receipts['PROBE']['source_commit'] = 'b' * 40
        with self.patches(), self.assertRaises(workflow.WorkflowStopped):
            self.apply()
        self.assertEqual(self.ledger()['checkpoints'], {})
        self.assertEqual(self.ops.executed, [('PROBE', 1)])
        self.assert_ledger(['FAILED_HOLD'])

    def test_unpinned_receipt_is_not_implicitly_adopted(self):
        with self.patches():
            self.apply()
        self.assertEqual(self.ops.adopted, [])
        self.assertEqual(self.ops.executed[0:2], [('PROBE', 1), ('ACCOUNT', 1)])

    def test_inherited_receipt_digest_drift_blocks_without_consuming_attempt(self):
        self.base['workflow_contract']['stages'][0]['adopt_receipt_sha256'] = 'f' * 64
        self.bind_contract()
        with self.patches(), self.assertRaisesRegex(Denied, 'INHERITED_RECEIPT_DRIFT'):
            self.apply()
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(self.ops.executed, [])

    def test_failure_cause_and_recovery_proof_persist_before_success(self):
        self.fail_stage('RUNTIME', count=1)
        self.ops.proof_status = 'SAFE_TO_RETRY'
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['failures'], [{'attempt': 1, 'stage': 'RUNTIME', 'cause': 'RuntimeError'}])
        recovery = result['recoveries'][0]
        self.assertEqual(recovery['attempt'], 1)
        self.assertEqual(recovery['stage'], 'RUNTIME')
        self.assertEqual({key: recovery[key] for key in ('status', 'action', 'evidence_sha256', 'checkpoint')},
                         self.ops.proof('RUNTIME', 'SAFE_TO_RETRY'))
        self.assert_ledger(['FAILED_HOLD', 'SUCCESS'])

    def test_complete_reconcile_proof_skips_stage_without_replaying_its_effect(self):
        self.fail_stage('RUNTIME', count=1)
        self.ops.proof_status = 'COMPLETE'
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual([row for row in self.ops.executed if row[0] == 'RUNTIME'], [('RUNTIME', 1)])
        self.assertEqual(result['recoveries'][0]['checkpoint'], self.ops.receipts['RUNTIME'])
        self.assert_ledger(['FAILED_HOLD', 'SUCCESS'])

    def test_unknown_hold_never_retries_or_consumes_budget_without_safe_proof(self):
        self.held_at_runtime()
        before = self.ledger_path().read_bytes()
        executed = list(self.ops.executed)
        with self.patches(), self.assertRaises(workflow.WorkflowStopped):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assertEqual(self.ops.executed, executed)
        self.assert_ledger(['FAILED_HOLD'])

    def test_restart_same_permit_safe_proof_resumes_remaining_stages(self):
        self.held_at_runtime()
        completed = copy.deepcopy(self.ledger()['checkpoints'])
        self.ops.execute_hook = None
        self.ops.proof_status = 'SAFE_TO_RETRY'
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 2)
        self.assertEqual(self.ops.executed, [('PROBE', 1), ('ACCOUNT', 1), ('RUNTIME', 1),
                         ('RUNTIME', 2), ('POLICY_RESTORE', 2), ('CHANNEL_REBIND', 2), ('CUSTOMER_APPLY', 2)])
        self.assertEqual({stage: self.ledger()['checkpoints'][stage] for stage in completed}, completed)
        self.assert_ledger(['FAILED_HOLD', 'SUCCESS'])

    def test_fifth_failure_seals_budget_and_sixth_invocation_has_no_effects(self):
        self.fail_stage('CUSTOMER_APPLY')
        self.ops.proof_status = 'SAFE_TO_RETRY'
        with self.patches(), self.assertRaises(workflow.WorkflowStopped) as caught:
            self.apply()
        self.assertEqual(caught.exception.summary['state'], 'EXHAUSTED')
        self.assertEqual(caught.exception.summary['attempts_used'], 5)
        self.assertEqual([n for stage, n in self.ops.executed if stage == 'CUSTOMER_APPLY'], [1, 2, 3, 4, 5])
        self.assertEqual([stage for stage, _ in self.ops.executed if stage != 'CUSTOMER_APPLY'], list(workflow.STAGES[:-1]))
        before, executed = self.ledger_path().read_bytes(), list(self.ops.executed)
        with self.patches(), self.assertRaisesRegex(Denied, 'EXHAUSTED'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assertEqual(self.ops.executed, executed)
        self.assert_ledger(['FAILED_HOLD'] * 5)

    def test_success_seals_the_same_permit_without_executing_any_stage_again(self):
        with self.patches():
            self.apply()
            executed = list(self.ops.executed)
            with self.assertRaisesRegex(Denied, 'FINISHED'):
                self.apply()
        self.assertEqual(self.ops.executed, executed)
        self.assert_ledger(['SUCCESS'])

    def test_old_v2_attempt_ledger_is_sealed_and_never_replaced(self):
        r.STATE.mkdir()
        old = canonical({'schema': 1, 'binding': {'transaction': r.TXN},
                         'attempts': [{'number': 1, 'state': 'HOLD_UNKNOWN_OR_PARTIAL'}]})
        self.ledger_path().write_bytes(old)
        with self.patches(), self.assertRaisesRegex(Denied, 'LEGACY_OR_CHANGED_SCOPE_SEALED'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), old)
        self.assertEqual(self.ops.executed, [])

    def test_old_v2_transaction_without_ledger_cannot_gain_fresh_budget(self):
        (r.STATE / r.TXN).mkdir(parents=True)
        old_receipt = r.STATE / r.TXN / 'receipt.json'
        old_receipt.write_bytes(canonical({'schema': 2, 'state': 'HOLD_UNKNOWN_OR_PARTIAL'}))
        with self.patches(), self.assertRaisesRegex(Denied, 'LEGACY_TRANSACTION_SEALED'):
            self.apply()
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(self.ops.executed, [])

    def test_source_drift_before_first_attempt_has_no_stage_effects(self):
        (self.source / 'boot.py').write_bytes(b'changed source')
        with self.patches(), self.assertRaisesRegex(Denied, 'SOURCE_HASH'):
            self.apply()
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(self.ops.executed, [])

    def test_source_drift_on_restart_preserves_held_original_ledger(self):
        self.held_at_runtime()
        before = self.ledger_path().read_bytes()
        executed = list(self.ops.executed)
        (self.source / 'boot.py').write_bytes(b'changed source')
        with self.patches(), self.assertRaisesRegex(Denied, 'SOURCE_HASH'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assertEqual(self.ops.executed, executed)

    def test_source_drift_during_last_stage_cannot_be_marked_success(self):
        def drift(stage, lease):
            if stage == 'CUSTOMER_APPLY':
                (self.source / 'boot.py').write_bytes(b'changed during last stage')
        self.ops.execute_hook = drift
        with self.patches(), self.assertRaises(Denied):
            self.apply()
        self.assertNotEqual(self.ledger()['state'], 'SUCCESS')
        self.assertEqual(len(self.ledger()['attempts']), 1)

    def test_permission_drift_during_last_stage_cannot_be_marked_success(self):
        def drift(stage, lease):
            if stage == 'CUSTOMER_APPLY':
                self.approval['expires_unix'] += 1
        self.ops.execute_hook = drift
        with self.patches(), self.assertRaises(Denied):
            self.apply()
        self.assertNotEqual(self.ledger()['state'], 'SUCCESS')
        self.assertEqual(len(self.ledger()['attempts']), 1)

    def test_changed_permit_or_comment_cannot_reset_original_attempt_counter(self):
        self.held_at_runtime()
        before = self.ledger_path().read_bytes()
        original = copy.deepcopy(self.approval)
        for key, value in [('max_executions', 4), ('expires_unix', original['expires_unix'] + 1)]:
            with self.subTest(key=key):
                self.approval = dict(original, **{key: value})
                with self.patches(), self.assertRaisesRegex(Denied, 'CHANGED_SCOPE_SEALED'):
                    self.apply()
        self.approval = original
        with self.patches(), self.assertRaisesRegex(Denied, 'CHANGED_SCOPE_SEALED'):
            self.apply(comment=99)
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assert_ledger(['FAILED_HOLD'])

    def test_stage_input_drift_blocks_before_any_attempt(self):
        self.ops.inputs['POLICY_RESTORE']['fixture_revision'] = 2
        with self.patches(), self.assertRaisesRegex(Denied, 'STAGE_INPUT_DRIFT'):
            self.apply()
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(self.ops.executed, [])

    def test_stage_implementation_drift_blocks_before_any_attempt(self):
        self.ops.implementations['CHANNEL_REBIND'] = b'unreviewed implementation'
        with self.patches(), self.assertRaisesRegex(Denied, 'STAGE_INPUT_DRIFT'):
            self.apply()
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(self.ops.executed, [])

    def test_completed_checkpoint_live_proof_failure_blocks_restart(self):
        self.held_at_runtime()
        before = self.ledger_path().read_bytes()
        self.ops.verify_hook = lambda stage, checkpoint: False if stage == 'ACCOUNT' else None
        with self.patches(), self.assertRaisesRegex(Denied, 'CHECKPOINT_UNPROVEN'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assert_ledger(['FAILED_HOLD'])

    def test_checkpoint_shape_is_exact_and_boolean_success_does_not_suffice(self):
        self.ops.execute_hook = lambda stage, lease: {'state': 'COMPLETE', 'success': True}
        with self.patches(), self.assertRaises(workflow.WorkflowStopped):
            self.apply()
        self.assertEqual(self.ledger()['checkpoints'], {})
        self.assert_ledger(['FAILED_HOLD'])

    def test_reconciliation_proof_shape_rejects_unbound_evidence_and_extra_fields(self):
        self.held_at_runtime()
        before = self.ledger_path().read_bytes()
        for field, value in [('evidence_sha256', 'not a digest'), ('extra_instruction', 'retry anything')]:
            with self.subTest(field=field):
                proof = dict(self.ops.proof('RUNTIME', 'SAFE_TO_RETRY'), **{field: value})
                self.ops.reconcile_hook = lambda *args: proof
                with self.patches(), self.assertRaisesRegex(Denied, 'RECONCILE_PROOF'):
                    self.apply()
                self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_recovery_action_must_match_explicit_stage_scope(self):
        self.held_at_runtime()
        proof = dict(self.ops.proof('RUNTIME', 'SAFE_TO_RETRY'), action='RECONCILE_ACCOUNT')
        self.ops.reconcile_hook = lambda *args: proof
        before = self.ledger_path().read_bytes()
        with self.patches(), self.assertRaisesRegex(Denied, 'RECOVERY_NOT_APPROVED'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_fixed_stage_order_and_exact_contract_binding_are_required(self):
        original = copy.deepcopy(self.base['workflow_contract'])
        for changed in ('order', 'extra_stage', 'wrong_hash'):
            with self.subTest(changed=changed):
                self.base['workflow_contract'] = copy.deepcopy(original)
                if changed == 'order':
                    self.base['workflow_contract']['stages'].reverse()
                elif changed == 'extra_stage':
                    self.base['workflow_contract']['stages'].append(copy.deepcopy(original['stages'][0]))
                else:
                    self.approval['workflow_contract_sha256'] = 'f' * 64
                with self.patches(), self.assertRaises(Denied):
                    self.apply()
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(self.ops.executed, [])

    def test_maximum_attempts_requires_exact_integer_one_through_five(self):
        for limit in (0, 6, True, False, '5', 5.0, None):
            with self.subTest(limit=limit), self.patches(), self.assertRaises(Denied):
                self.approval['max_executions'] = limit
                self.apply()
        self.assertFalse(self.ledger_path().exists())

    def test_missing_protected_workflow_inputs_fail_closed_without_partial_installer_fallback(self):
        with self.patches(), patch.object(r, 'apply', side_effect=AssertionError('No fallback')):
            with self.assertRaises(FileNotFoundError) as caught:
                r.workflow_apply(self.source, 4, self.base, None)
        self.assertEqual(Path(caught.exception.filename), r.CONFIG / 'WHOLE_WORKFLOW_INPUTS.json')
        self.assertFalse(r.STATE.exists())
        self.assertEqual(self.ops.executed, [])

    def test_original_shared_lock_blocks_competing_workflow_before_attempt_consumption(self):
        with r.LOCK.open('w') as held, self.patches():
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.apply()
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(self.ops.executed, [])

    def test_original_lock_remains_held_during_reconciliation(self):
        self.fail_stage('RUNTIME', count=1)
        checked = []

        def reconcile(stage, intent, checkpoint, lease):
            with r.LOCK.open('w') as competing:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)
            checked.append(True)
            return self.ops.proof(stage, 'SAFE_TO_RETRY')
        self.ops.reconcile_hook = reconcile
        with self.patches():
            self.assertEqual(self.apply()['state'], 'SUCCESS')
        self.assertEqual(checked, [True])

    def test_ledger_fence_tamper_prevents_late_checkpoint_and_overwrite(self):
        changed = []

        def tamper(stage, lease):
            data = self.ledger()
            data['attempts'][-1]['lease']['fence'] = 999
            raw = canonical(data)
            self.ledger_path().write_bytes(raw)
            changed.append(raw)
        self.ops.execute_hook = tamper
        with self.patches(), self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), changed[0])
        self.assertEqual(self.ledger()['checkpoints'], {})
        self.assertEqual(self.ops.executed, [('PROBE', 1)])

    def test_reconcile_fence_tamper_cannot_rewrite_newer_durable_ledger(self):
        self.held_at_runtime()
        changed = []

        def tamper(stage, intent, checkpoint, lease):
            data = self.ledger()
            data['state'] = 'NEWER_FIXTURE_OWNER'
            raw = canonical(data)
            self.ledger_path().write_bytes(raw)
            changed.append(raw)
            return self.ops.proof(stage, 'SAFE_TO_RETRY')
        self.ops.reconcile_hook = tamper
        with self.patches(), self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), changed[0])
        self.assertEqual(len(self.ledger()['attempts']), 1)

    def test_replaced_lock_inode_prevents_further_effects_or_ledger_writes(self):
        before = []

        def replace_lock(stage, lease):
            before.append(self.ledger_path().read_bytes())
            replacement = self.b / 'replacement.lock'
            replacement.touch(mode=0o600)
            os.replace(replacement, r.LOCK)
        self.ops.execute_hook = replace_lock
        with self.patches(), self.assertRaisesRegex(Denied, 'LOCK_REPLACED'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before[0])
        self.assertEqual(self.ops.executed, [('PROBE', 1)])

    def test_expired_lease_prevents_next_stage_and_new_attempt(self):
        clock = [self.approval['issued_unix'] + 1]

        def expire(stage, lease):
            clock[0] = self.approval['expires_unix']
        self.ops.execute_hook = expire
        with self.patches(), patch.object(workflow.time, 'time', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(Denied, 'LEASE_EXPIRED'):
                self.apply()
        self.assertEqual(self.ops.executed, [('PROBE', 1)])
        self.assert_ledger(['FAILED_HOLD'])

    def test_crash_with_durable_effect_intent_requires_proof_before_restart(self):
        original = workflow.Coordinator.save
        crashed = []

        def save(coordinator, initial=False):
            if crashed or 'ACCOUNT' in coordinator.data['checkpoints']:
                crashed.append(True)
                raise OSError(errno.EIO, 'fixture lost process after account effect')
            return original(coordinator, initial)

        with self.patches(), patch.object(workflow.Coordinator, 'save', save):
            with self.assertRaises(OSError):
                self.apply()
        durable = self.ledger()
        self.assertEqual(durable['state'], 'RUNNING')
        self.assertEqual(durable['intent']['stage'], 'ACCOUNT')
        self.assertEqual(list(durable['checkpoints']), ['PROBE'])
        self.assert_ledger(['STARTED_UNKNOWN'])
        before = self.ledger_path().read_bytes()
        with self.patches(), self.assertRaises(workflow.WorkflowStopped):
            self.apply()
        expected=json.loads(before);expected['state']='HOLD'
        self.assertEqual(self.ledger(),expected)  # Only terminal bookkeeping changes, no new effect.
        self.ops.proof_status = 'COMPLETE'
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['failures'][0]['cause'], 'PROCESS_INTERRUPTED')
        self.assertEqual(self.ops.executed, [('PROBE', 1), ('ACCOUNT', 1),
                         *[(stage, 2) for stage in workflow.STAGES[2:]]])
        self.assert_ledger(['FAILED_RECONCILED', 'SUCCESS'])

    def test_crash_between_complete_checkpoints_skips_proven_prior_stages(self):
        original = workflow.Coordinator.save
        crashed = []

        def save(coordinator, initial=False):
            intent = coordinator.data['intent']
            if crashed or intent is not None and intent['stage'] == 'RUNTIME':
                crashed.append(True)
                raise OSError(errno.EIO, 'fixture lost process between checkpoints')
            return original(coordinator, initial)

        with self.patches(), patch.object(workflow.Coordinator, 'save', save):
            with self.assertRaises(OSError):
                self.apply()
        self.assertIsNone(self.ledger()['intent'])
        self.assertEqual(list(self.ledger()['checkpoints']), ['ACCOUNT', 'PROBE'])
        self.assert_ledger(['STARTED_UNKNOWN'])
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['failures'][0]['cause'], 'INTERRUPTED_BETWEEN_CHECKPOINTS')
        self.assertEqual(self.ops.executed, [('PROBE', 1), ('ACCOUNT', 1),
                         *[(stage, 2) for stage in workflow.STAGES[2:]]])
        self.assert_ledger(['FAILED_RECONCILED', 'SUCCESS'])

    def test_crash_before_final_success_receipt_finishes_without_spending_another_attempt(self):
        original = workflow.Coordinator.save
        crashed = []

        def save(coordinator, initial=False):
            if crashed or coordinator.data['state'] == 'SUCCESS':
                crashed.append(True)
                raise OSError(errno.EIO, 'fixture lost process before final receipt')
            return original(coordinator, initial)

        with self.patches(), patch.object(workflow.Coordinator, 'save', save):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(self.ledger()['state'], 'RUNNING')
        self.assertEqual(set(self.ledger()['checkpoints']), set(workflow.STAGES))
        self.assertIsNone(self.ledger()['intent'])
        executed = list(self.ops.executed)
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 1)
        self.assertEqual(self.ops.executed, executed)
        self.assertTrue(self.ledger()['attempts'][0]['completion_reconciled'])
        self.assert_ledger(['SUCCESS'])


if __name__ == '__main__':
    unittest.main()
