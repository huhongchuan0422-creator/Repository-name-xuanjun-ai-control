"""Independent whole-workflow review tests. Temp files and mock adapters only."""
import copy
import fcntl
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pr122_customer_release as release
from scripts import pr122_customer_workflow as workflow
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_customer_release as release_tests
from tests import test_pr122_customer_workflow as workflow_tests


class OfflineOperations:
    def __init__(self, source_commit):
        self.source_commit = source_commit
        self.inputs = {stage: {'stage': stage} for stage in workflow.STAGES}
        self.calls = []

    def input(self, stage):
        return copy.deepcopy(self.inputs[stage])

    def implementation(self, stage):
        return ('offline test implementation ' + stage).encode()

    def checkpoint(self, stage):
        return {'state': 'COMPLETE', 'receipt_sha256': digest(stage.encode()),
                'effect_sha256': digest(('effect ' + stage).encode()),
                'source_commit': self.source_commit}

    def inherited(self, stage):
        return self.checkpoint(stage)

    def verify(self, stage, checkpoint):
        return checkpoint == self.checkpoint(stage)

    def execute(self, stage, lease):
        lease.assert_active()
        self.calls.append(stage)
        return self.checkpoint(stage)

    def reconcile(self, stage, intent, checkpoint, lease):
        return {'status': 'UNKNOWN', 'action': None,
                'evidence_sha256': digest(b'offline unknown'), 'checkpoint': None}


class WorkflowReviewTests(unittest.TestCase):
    inventory = release_tests.ReleaseTests.inventory
    patches = release_tests.ReleaseTests.patches

    def fake_run(self, args):
        raise AssertionError('Host command runner forbidden in workflow review')

    def setUp(self):
        release_tests.ReleaseTests.setUp(self)
        del self.fail  # The borrowed fixture uses this name as a runner flag.
        self.operations = OfflineOperations(self.base['source_commit'])
        self.base['workflow_contract'] = {'schema': 1, 'stages': [
            {'stage': stage,
             'input_sha256': digest(canonical(self.operations.input(stage))),
             'implementation_sha256': digest(self.operations.implementation(stage)),
             'adopt_receipt_sha256': None,
             'recovery_actions': sorted(workflow.RECOVERY[stage])}
            for stage in workflow.STAGES]}
        self.approval.update(attempt_policy=workflow.POLICY, max_executions=5,
                             plan_sha256=digest(canonical(self.base)),
                             workflow_contract_sha256=digest(canonical(self.base['workflow_contract'])))
        for adapter in (
            patch.object(workflow, 'protected_directory', lambda path: None),
            patch.object(workflow, 'read_private', lambda path: json.loads(Path(path).read_bytes())),
            patch.object(release.subprocess, 'run', side_effect=AssertionError('External process forbidden')),
        ):
            adapter.start()
            self.addCleanup(adapter.stop)

    def ledger_path(self):
        return release.STATE / (release.TXN + '.attempts.json')

    def test_caller_mutation_cannot_change_approved_stage_inputs(self):
        with self.patches(), release.LOCK.open('w') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            coordinator = workflow.Coordinator(release, self.source, 4, self.base,
                                               self.approval, self.operations, held.fileno())
            self.operations.inputs['PROBE'] = {'stage': 'unapproved altered probe'}
            self.base['workflow_contract']['stages'][0]['input_sha256'] = digest(
                canonical(self.operations.input('PROBE')))
            with self.assertRaisesRegex(Denied, 'STAGE_INPUT_DRIFT'):
                coordinator.run()
        self.assertEqual(self.operations.calls, [])

    def test_all_durable_complete_stages_finalize_without_consuming_extra_attempt(self):
        self.approval['max_executions'] = 1
        with self.patches():
            result = release.workflow_apply(self.source, 4, self.base, self.operations)
        self.assertEqual(result['state'], 'SUCCESS')
        original_calls = list(self.operations.calls)
        data = json.loads(self.ledger_path().read_bytes())
        # This is the durable snapshot just after the sixth checkpoint and before
        # the final success save, as a process kill can leave it.
        data['state'] = 'RUNNING'
        data['attempts'][-1]['state'] = 'STARTED_UNKNOWN'
        data['attempts'][-1].pop('ended_unix', None)
        self.ledger_path().write_bytes(canonical(data))
        with self.patches():
            result = release.workflow_apply(self.source, 4, self.base, self.operations)
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 1)
        self.assertEqual(self.operations.calls, original_calls)

    def test_stale_intent_binding_is_rejected_before_adapter_reconciliation(self):
        with self.patches(), patch.object(self.operations, 'execute',
                                         side_effect=OSError('offline unknown result')):
            with self.assertRaises(workflow.WorkflowStopped):
                release.workflow_apply(self.source, 4, self.base, self.operations)
        data = json.loads(self.ledger_path().read_bytes())
        data['intent']['attempt'] = 99
        data['intent']['input_sha256'] = 'f' * 64
        self.ledger_path().write_bytes(canonical(data))
        proof = {'status': 'SAFE_TO_RETRY', 'action': 'REVALIDATE_READONLY',
                 'evidence_sha256': digest(b'offline safe proof'), 'checkpoint': None}
        with self.patches(), patch.object(self.operations, 'reconcile', return_value=proof) as reconcile:
            with self.assertRaisesRegex(Denied, 'INTENT'):
                release.workflow_apply(self.source, 4, self.base, self.operations)
        reconcile.assert_not_called()
        self.assertEqual(json.loads(self.ledger_path().read_bytes()), data)

    def test_old_child_lease_does_not_gain_authority_from_next_attempt(self):
        old_leases = []
        stale_rejections = []
        original_execute = self.operations.execute

        def execute(stage, lease):
            if stage == 'PROBE' and not old_leases:
                old_leases.append(lease)
                raise OSError('offline first execution interrupted')
            if stage == 'PROBE':
                try:
                    old_leases[0].assert_active()
                except Denied:
                    stale_rejections.append(True)
                else:
                    stale_rejections.append(False)
            return original_execute(stage, lease)

        proof = {'status': 'SAFE_TO_RETRY', 'action': 'REVALIDATE_READONLY',
                 'evidence_sha256': digest(b'offline safe proof'), 'checkpoint': None}
        with self.patches(), patch.object(self.operations, 'execute', execute), \
                patch.object(self.operations, 'reconcile', return_value=proof):
            result = release.workflow_apply(self.source, 4, self.base, self.operations)
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 2)
        self.assertEqual(stale_rejections, [True])

    def test_completed_child_lease_cannot_authorize_next_stage_in_same_attempt(self):
        old_leases = []
        original_execute = self.operations.execute

        def execute(stage, lease):
            if stage == 'PROBE':
                old_leases.append(lease)
            elif stage == 'ACCOUNT':
                with self.assertRaisesRegex(Denied, 'STALE_CHILD_LEASE'):
                    old_leases[0].assert_active()
            return original_execute(stage, lease)

        with self.patches(), patch.object(self.operations, 'execute', execute):
            result = release.workflow_apply(self.source, 4, self.base, self.operations)
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 1)

    def test_reconciliation_lease_never_authorizes_child_writes(self):
        attempts = []
        original_execute = self.operations.execute

        def execute(stage, lease):
            if stage == 'PROBE' and not attempts:
                attempts.append(True)
                raise OSError('offline first execution interrupted')
            return original_execute(stage, lease)

        def reconcile(stage, intent, checkpoint, lease):
            lease.assert_fence()
            with self.assertRaisesRegex(Denied, 'RECONCILIATION_READONLY'):
                lease.assert_active()
            return {'status': 'SAFE_TO_RETRY', 'action': 'REVALIDATE_READONLY',
                    'evidence_sha256': digest(b'offline safe proof'), 'checkpoint': None}

        with self.patches(), patch.object(self.operations, 'execute', execute), \
                patch.object(self.operations, 'reconcile', reconcile):
            result = release.workflow_apply(self.source, 4, self.base, self.operations)
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 2)


class ExhaustedReadonlyTests(unittest.TestCase):
    """Fifth-attempt read-only completion, using the real original coordinator."""
    inventory = workflow_tests.WorkflowTests.inventory
    patches = workflow_tests.WorkflowTests.patches
    fake_run = workflow_tests.WorkflowTests.fake_run
    bind_contract = workflow_tests.WorkflowTests.bind_contract
    apply = workflow_tests.WorkflowTests.apply
    ledger_path = workflow_tests.WorkflowTests.ledger_path
    ledger = workflow_tests.WorkflowTests.ledger
    assert_ledger = workflow_tests.WorkflowTests.assert_ledger

    def setUp(self):
        workflow_tests.WorkflowTests.setUp(self)
        self.last_proof = 'COMPLETE'
        self.last_error = RuntimeError('completed child response lost')
        self.readonly_leases = []
        self.proof_hook = None

        def execute(stage, lease):
            number = lease.active['number']
            self.assertLessEqual(number, 5, 'No sixth effect or child execution is permitted')
            if stage == 'PROBE' and number < 5:
                raise RuntimeError('known no-effect probe failure')
            if stage == 'CUSTOMER_APPLY':
                raise self.last_error

        def reconcile(stage, intent, checkpoint, lease):
            self.readonly_leases.append(lease)
            lease.assert_fence()
            with self.assertRaisesRegex(Denied, 'RECONCILIATION_READONLY'):
                lease.assert_active()
            if stage != 'PROBE' and self.proof_hook is not None:
                value = self.proof_hook(stage, intent, checkpoint, lease)
                if value is not None:
                    return value
            return self.ops.proof(stage, 'SAFE_TO_RETRY' if stage == 'PROBE' else self.last_proof)

        self.ops.execute_hook = execute
        self.ops.reconcile_hook = reconcile

    def assert_five_only(self):
        data = self.ledger()
        self.assertEqual(len(data['attempts']), 5)
        self.assertEqual([number for stage, number in self.ops.executed if stage == 'PROBE'], [1, 2, 3, 4, 5])
        self.assertEqual([stage for stage, number in self.ops.executed if number == 5], list(workflow.STAGES))
        self.assertFalse(any(number > 5 for _, number in self.ops.executed))
        return data

    def test_fifth_completed_child_response_loss_finalizes_without_sixth_effect(self):
        permit = canonical(self.approval)
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 5)
        self.assertEqual(canonical(self.approval), permit)
        data = self.assert_five_only()
        self.assertEqual(set(data['checkpoints']), set(workflow.STAGES))
        self.assertEqual(data['recoveries'][-1]['status'], 'COMPLETE')
        self.assertEqual(data['recoveries'][-1]['stage'], 'CUSTOMER_APPLY')
        self.assertEqual(len(self.readonly_leases), 5)
        self.assert_ledger(['FAILED_HOLD'] * 4 + ['SUCCESS'])

    def hold_fifth_unknown(self):
        self.last_proof = 'UNKNOWN'
        with self.patches(), self.assertRaises(workflow.WorkflowStopped) as stopped:
            self.apply()
        self.assertEqual(stopped.exception.summary['state'], 'HOLD')
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'HOLD')
        self.assertEqual(data['intent']['stage'], 'CUSTOMER_APPLY')
        return data

    def test_unknown_fifth_result_stays_hold_and_never_adopts_unproven_completion(self):
        data = self.hold_fifth_unknown()
        self.assertNotIn('CUSTOMER_APPLY', data['checkpoints'])
        self.assertEqual(len(data['recoveries']), 4)
        self.assertEqual(len(self.readonly_leases), 5)
        self.assert_ledger(['FAILED_HOLD'] * 5)

    def test_repeated_unknown_restart_spends_no_attempt_or_effect(self):
        self.hold_fifth_unknown()
        calls = list(self.ops.executed)
        for _ in range(2):
            with self.patches(), self.assertRaises(workflow.WorkflowStopped) as stopped:
                self.apply()
            self.assertEqual(stopped.exception.summary['state'], 'HOLD')
        self.assertEqual(self.ops.executed, calls)
        self.assertEqual(len(self.ledger()['attempts']), 5)
        self.assertEqual(len(self.readonly_leases), 7)

    def test_unknown_then_trusted_complete_restart_finalizes_same_fifth_attempt(self):
        self.hold_fifth_unknown()
        calls = list(self.ops.executed)
        self.last_proof = 'COMPLETE'
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 5)
        self.assertEqual(self.ops.executed, calls)
        self.assert_ledger(['FAILED_HOLD'] * 4 + ['SUCCESS'])

    def test_safe_to_retry_without_completion_is_exhausted_not_a_sixth_attempt(self):
        self.last_proof = 'SAFE_TO_RETRY'
        with self.patches(), self.assertRaises(workflow.WorkflowStopped) as stopped:
            self.apply()
        self.assertEqual(stopped.exception.summary['state'], 'EXHAUSTED')
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'EXHAUSTED')
        self.assertNotIn('CUSTOMER_APPLY', data['checkpoints'])
        self.assertEqual(data['recoveries'][-1]['status'], 'SAFE_TO_RETRY')
        calls = list(self.ops.executed)
        with self.patches(), self.assertRaises(Denied):
            self.apply()
        self.assertEqual(self.ops.executed, calls)
        self.assertEqual(len(self.ledger()['attempts']), 5)

    def test_complete_earlier_fifth_stage_cannot_start_remaining_stages(self):
        def execute(stage, lease):
            if stage == 'PROBE' and lease.active['number'] < 5:
                raise RuntimeError('known no-effect probe failure')
            if stage == 'RUNTIME':
                raise RuntimeError('runtime complete but response lost')
        self.ops.execute_hook = execute
        with self.patches(), self.assertRaises(workflow.WorkflowStopped) as stopped:
            self.apply()
        self.assertEqual(stopped.exception.summary['state'], 'EXHAUSTED')
        self.assertEqual([stage for stage, number in self.ops.executed if number == 5],
                         ['PROBE', 'ACCOUNT', 'RUNTIME'])
        self.assertEqual(set(self.ledger()['checkpoints']), {'PROBE', 'ACCOUNT', 'RUNTIME'})
        self.assertEqual(len(self.ledger()['attempts']), 5)

    def test_fifth_keyboard_interrupt_preserves_intent_then_readonly_restart_finishes(self):
        self.last_error = KeyboardInterrupt('fixture process interruption')
        with self.patches(), self.assertRaises(KeyboardInterrupt):
            self.apply()
        data = self.assert_five_only()
        self.assertEqual(data['intent']['stage'], 'CUSTOMER_APPLY')
        self.assertNotIn('CUSTOMER_APPLY', data['checkpoints'])
        calls = list(self.ops.executed)
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(self.ops.executed, calls)
        self.assertEqual(len(self.ledger()['attempts']), 5)

    def test_legacy_exhausted_fifth_intent_is_readonly_reconcilable_not_new_budget(self):
        data = self.hold_fifth_unknown()
        data['state'] = 'EXHAUSTED'
        self.ledger_path().write_bytes(canonical(data))
        calls = list(self.ops.executed)
        self.last_proof = 'COMPLETE'
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(self.ops.executed, calls)
        self.assertEqual(len(self.ledger()['attempts']), 5)

    def test_crashed_started_unknown_fifth_intent_finishes_from_complete_proof(self):
        data = self.hold_fifth_unknown()
        data['state'] = 'RUNNING'
        data['attempts'][-1]['state'] = 'STARTED_UNKNOWN'
        data['attempts'][-1].pop('ended_unix', None)
        self.ledger_path().write_bytes(canonical(data))
        calls = list(self.ops.executed)
        self.last_proof = 'COMPLETE'
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(self.ops.executed, calls)
        self.assert_ledger(['FAILED_HOLD'] * 4 + ['SUCCESS'])

    def test_reconciliation_exception_preserves_hold_without_effect_or_error_text_leak(self):
        def failed_proof(*args):
            raise OSError('fixture private diagnostic must not enter ledger')
        self.proof_hook = failed_proof
        with self.patches(), self.assertRaises((Denied, OSError)):
            self.apply()
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'HOLD')
        self.assertEqual(data['intent']['stage'], 'CUSTOMER_APPLY')
        self.assertNotIn('CUSTOMER_APPLY', data['checkpoints'])
        self.assertNotIn('fixture private diagnostic', self.ledger_path().read_text())

    def test_complete_claim_without_live_checkpoint_proof_stays_hold(self):
        def reject_child(stage, checkpoint):
            if stage == 'CUSTOMER_APPLY': return False
        self.ops.verify_hook = reject_child
        with self.patches(), self.assertRaisesRegex(Denied, 'CHECKPOINT_UNPROVEN'):
            self.apply()
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'HOLD')
        self.assertNotIn('CUSTOMER_APPLY', data['checkpoints'])

    def test_complete_proof_needs_explicit_original_recovery_permission(self):
        self.base['workflow_contract']['stages'][-1]['recovery_actions'] = []
        self.bind_contract()
        with self.patches(), self.assertRaisesRegex(Denied, 'RECOVERY_NOT_APPROVED'):
            self.apply()
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'HOLD')
        self.assertNotIn('CUSTOMER_APPLY', data['checkpoints'])

    def test_final_success_rechecks_previously_completed_stages(self):
        def previous_stage_drifts(*args):
            self.ops.verify_hook = lambda stage, checkpoint: False if stage == 'ACCOUNT' else None
        self.proof_hook = previous_stage_drifts
        with self.patches(), self.assertRaisesRegex(Denied, 'CHECKPOINT_UNPROVEN'):
            self.apply()
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'HOLD')
        self.assertNotEqual(data['attempts'][-1]['state'], 'SUCCESS')

    def test_keyboard_interrupt_inside_readonly_proof_preserves_restartable_intent(self):
        self.proof_hook = lambda *args: (_ for _ in ()).throw(KeyboardInterrupt('fixture readonly interruption'))
        with self.patches(), self.assertRaises(KeyboardInterrupt):
            self.apply()
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'HOLD')
        self.assertEqual(data['intent']['stage'], 'CUSTOMER_APPLY')
        calls = list(self.ops.executed)
        self.proof_hook = None
        with self.patches(): result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(self.ops.executed, calls)

    def test_readonly_recovery_lease_cannot_record_or_authorize_repairs(self):
        blocked = []
        def prove(stage, intent, checkpoint, lease):
            for action in (lease.assert_locked,
                           lambda: lease.record_stage(stage, 'CUSTOMER_VERIFIED', {})):
                with self.assertRaises(Denied): action()
                blocked.append(True)
        self.proof_hook = prove
        with self.patches():
            result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(blocked, [True, True])
        self.assert_five_only()

    def test_expiry_during_fifth_proof_prevents_final_success(self):
        now = [self.approval['issued_unix'] + 1]
        def expire(*args):
            now[0] = self.approval['expires_unix']
        self.proof_hook = expire
        with self.patches(), patch.object(workflow.time, 'time', side_effect=lambda: now[0]), \
                self.assertRaisesRegex(Denied, 'EXPIRED'):
            self.apply()
        data = self.assert_five_only()
        self.assertEqual(data['state'], 'HOLD')
        self.assertNotIn('CUSTOMER_APPLY', data['checkpoints'])
        calls = list(self.ops.executed)
        with self.patches(), patch.object(workflow.time, 'time', return_value=now[0]), \
                self.assertRaisesRegex(Denied, 'EXPIRED'):
            self.apply()
        self.assertEqual(self.ops.executed, calls)

    def test_global_lock_replacement_during_fifth_proof_cannot_commit_success(self):
        saved = []
        def replace_lock(*args):
            saved.append(self.ledger_path().read_bytes())
            replacement = release.LOCK.with_name('replacement-fixture-lock')
            replacement.write_bytes(b'')
            os.replace(replacement, release.LOCK)
        self.proof_hook = replace_lock
        with self.patches(), self.assertRaisesRegex(Denied, 'LOCK_REPLACED'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), saved[0])
        self.assert_five_only()

    def test_ledger_fence_change_during_fifth_proof_is_never_overwritten(self):
        changed = []
        def lose_fence(*args):
            data = self.ledger()
            data['failures'].append({'fixture': 'new durable writer'})
            changed.append(canonical(data))
            self.ledger_path().write_bytes(changed[0])
        self.proof_hook = lose_fence
        with self.patches(), self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), changed[0])
        self.assert_five_only()

    def test_successful_fifth_readonly_completion_remains_sealed(self):
        with self.patches():
            self.apply()
        before, calls = self.ledger_path().read_bytes(), list(self.ops.executed)
        with self.patches(), self.assertRaisesRegex(Denied, 'WORKFLOW_FINISHED'):
            self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assertEqual(self.ops.executed, calls)


if __name__ == '__main__':
    unittest.main()
