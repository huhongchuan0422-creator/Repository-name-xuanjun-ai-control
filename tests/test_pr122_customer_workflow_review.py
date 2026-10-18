"""Independent whole-workflow review tests. Temp files and mock adapters only."""
import copy
import fcntl
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pr122_customer_release as release
from scripts import pr122_customer_workflow as workflow
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_customer_release as release_tests


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


if __name__ == '__main__':
    unittest.main()
