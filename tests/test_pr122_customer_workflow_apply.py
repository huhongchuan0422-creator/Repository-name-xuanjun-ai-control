"""Borrowed CUSTOMER_APPLY lease tests, using temp files and mocked commands."""
import copy
import errno
import fcntl
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import pr122_customer_attempts as attempts
from scripts import pr122_customer_release as release
from scripts import pr122_customer_resume as resume
from scripts import pr122_customer_workflow as workflow
from scripts import pr122_customer_workflow_apply as child
from scripts import pr122_customer_workflow_operations as operations
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_customer_resume as resume_tests


class FakeWholeLease:
    """Test-only whole-stage authority with a single externally admitted counter."""
    def __init__(self, fixture):
        self.fixture = fixture
        self.live = True
        self.readonly = False
        self.active = {'number': 1}
        self.approval = copy.deepcopy(fixture.approval)
        self.plan = copy.deepcopy(fixture.base)
        self.static = {k: v for k, v in fixture.base.items() if k not in child.DYNAMIC_FIELDS}
        self.impl = digest(Path(release.__file__).read_bytes())
        self.actions = sorted(workflow.RECOVERY['CUSTOMER_APPLY'])
        self.checkpoints = {stage: {'state': 'COMPLETE', 'receipt_sha256': digest(stage.encode()),
                                  'effect_sha256': digest(('effect ' + stage).encode()),
                                  'source_commit': fixture.base['source_commit']}
                            for stage in ('ACCOUNT', 'RUNTIME')}
        self.data = {'checkpoints': copy.deepcopy(self.checkpoints)}
        self.identity = {'uid': fixture.base['account_uid'], 'gid': fixture.base['account_gid'],
                         'receipt_sha256': self.checkpoints['ACCOUNT']['receipt_sha256']}
        self.ops = SimpleNamespace(input=lambda stage: {'static_plan': copy.deepcopy(self.static)},
                                   account_identity=lambda: copy.deepcopy(self.identity), verify=self.verify)
        self.verified = []
        self.ledger_path = release.STATE / (release.TXN + '.attempts.json')
        release.STATE.mkdir(exist_ok=True)
        self.admit(1)

    def admit(self, number):
        self.active = {'number': number}
        self.expected_ledger = canonical({'schema': 3, 'policy': workflow.POLICY,
                                          'attempts': [{'number': n} for n in range(1, number + 1)]})
        self.ledger_path.write_bytes(self.expected_ledger)

    def assert_fence(self):
        if self.ledger_path.read_bytes() != self.expected_ledger:
            raise Denied('HOLD:WORKFLOW_FENCE_LOST')

    def assert_active(self):
        self.assert_fence()
        if not self.live or self.readonly:
            raise Denied('HOLD:WORKFLOW_NO_ACTIVE_ATTEMPT')

    def authority(self):
        self.assert_fence()
        if not self.live:
            raise Denied('HOLD:WORKFLOW_LEASE_EXPIRED')

    def verify_inputs(self, stage):
        if stage != 'CUSTOMER_APPLY':
            raise Denied('HOLD:WORKFLOW_CHILD_STAGE')

    def stage_contract(self, stage):
        self.verify_inputs(stage)
        return {'implementation_sha256': self.impl,
                'recovery_actions': list(self.actions)}

    def verify(self, stage, checkpoint):
        self.verified.append(stage)
        return checkpoint == self.checkpoints[stage]


class CustomerWorkflowApplyTests(unittest.TestCase):
    inventory = resume_tests.ResumeTests.inventory
    patches = resume_tests.ResumeTests.patches
    interrupt_file_once = resume_tests.ResumeTests.interrupt_file_once
    mutations = resume_tests.ResumeTests.mutations
    assert_mutations_once = resume_tests.ResumeTests.assert_mutations_once

    def setUp(self):
        resume_tests.ResumeTests.setUp(self)
        if 'fail' in self.__dict__: del self.fail
        self.approval['attempt_policy'] = workflow.POLICY
        self.lease = FakeWholeLease(self)
        self.held = release.LOCK.open('w')
        fcntl.flock(self.held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(self.held.close)
        blocked = patch.object(attempts.Attempts, '__init__',
                               side_effect=AssertionError('Nested attempt/budget forbidden'))
        blocked.start()
        self.addCleanup(blocked.stop)

    def fake_run(self, args):
        self.calls.append(args)
        if self.command_failure:
            error = self.command_failure(args)
            if error is not None:
                raise error
        if args[0].endswith('curl'):
            return b'fixture html'
        if args[:3] == ['/usr/bin/systemctl', 'show', release.UNITS[3]]:
            return (str(release.UNIT / release.UNITS[3]).encode() if 'FragmentPath' in args
                    else b'success' if 'Result' in args else b'')
        return b''

    def receipt(self):
        return json.loads((release.STATE / release.TXN / 'receipt.json').read_bytes())

    def execute(self):
        with self.patches():
            return child.execute(self.lease, release, self.source)

    def reconcile(self):
        self.lease.readonly = True
        try:
            with self.patches():
                return child.reconcile(self.lease, release, self.source)
        finally:
            self.lease.readonly = False

    def test_success_borrows_exact_outer_attempt_and_never_creates_another_budget(self):
        result = self.execute()
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertEqual(result['receipt_sha256'], digest((release.STATE / release.TXN / 'receipt.json').read_bytes()))
        self.assertEqual(self.receipt()['schema'], 3)
        self.assertEqual(self.receipt()['attempt_number'], 1)
        self.assertEqual(self.receipt()['state'], resume.SUCCESS)
        self.assertEqual(self.lease.ledger_path.read_bytes(), self.lease.expected_ledger)
        self.assert_mutations_once()

    def test_complete_reconciliation_is_readonly_and_proves_existing_child_receipt(self):
        result = self.execute()
        path = release.STATE / release.TXN / 'receipt.json'
        old = path.read_bytes()
        commands = copy.deepcopy(self.calls)
        proof = self.reconcile()
        self.assertEqual(proof['status'], 'COMPLETE')
        self.assertEqual(proof['checkpoint'], result)
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(self.calls, commands)
        self.assertEqual(self.lease.ledger_path.read_bytes(), self.lease.expected_ledger)

    def test_partial_owned_file_uses_next_outer_attempt_without_inner_retry(self):
        target = release.CODE / 'boot.py'
        fault, original = self.interrupt_file_once(target, errno.EINTR)
        with fault, self.assertRaises(resume.Recoverable):
            self.execute()
        self.assertEqual(self.receipt()['attempt_number'], 1)
        self.assertEqual(self.receipt()['state'], 'HOLD_WHOLE_WORKFLOW')
        self.assertEqual(self.calls, [])
        inode = target.stat().st_ino
        self.assertEqual(self.reconcile()['status'], 'SAFE_TO_RETRY')
        self.lease.admit(2)
        self.assertEqual(self.execute()['state'], 'COMPLETE')
        self.assertEqual(target.stat().st_ino, inode)
        self.assertEqual(target.read_bytes(), original[0])
        self.assertEqual(self.receipt()['attempt_number'], 2)
        self.assertEqual(len(self.receipt()['failures']), 1)
        self.assertEqual(self.lease.ledger_path.read_bytes(), self.lease.expected_ledger)
        self.assert_mutations_once()

    def test_transient_smoke_defers_retry_to_outer_budget_and_skips_completed_effects(self):
        def fail(args):
            if args[0].endswith('curl'):
                return release.CommandFailure(args, 7, b'offline transient')
        self.command_failure = fail
        with self.assertRaises(resume.Recoverable):
            self.execute()
        old_files = {path: (Path(path).stat().st_ino, Path(path).stat().st_mtime_ns)
                     for path in self.receipt()['files']}
        self.assertEqual(self.reconcile()['status'], 'SAFE_TO_RETRY')
        self.lease.admit(2)
        self.command_failure = None
        self.execute()
        self.assertEqual({path: (Path(path).stat().st_ino, Path(path).stat().st_mtime_ns)
                          for path in self.receipt()['files']}, old_files)
        self.assert_mutations_once()
        self.assertEqual(self.lease.ledger_path.read_bytes(), self.lease.expected_ledger)

    def test_unresolved_service_intent_stays_unknown_without_replay(self):
        def fail(args):
            if args[:3] == ['/usr/bin/systemctl', 'start', release.UNITS[0]]:
                return release.CommandFailure(args, result_unknown=True)
        self.command_failure = fail
        with self.assertRaises(release.CommandFailure):
            self.execute()
        commands = copy.deepcopy(self.calls)
        path = release.STATE / release.TXN / 'receipt.json'
        old = path.read_bytes()
        self.assertEqual(self.reconcile()['status'], 'UNKNOWN')
        self.assertEqual(self.calls, commands)
        self.assertEqual(path.read_bytes(), old)

    def test_absent_child_proof_is_readonly_and_does_not_admit_an_attempt(self):
        proof = self.reconcile()
        self.assertEqual(proof['status'], 'SAFE_TO_RETRY')
        self.assertFalse((release.STATE / release.TXN).exists())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.lease.ledger_path.read_bytes(), self.lease.expected_ledger)

    def test_old_v2_child_is_never_adopted_or_overwritten(self):
        txn = release.STATE / release.TXN
        txn.mkdir()
        raw = canonical({'schema': 2, 'policy': resume.POLICY, 'approval': self.lease.approval})
        (txn / 'receipt.json').write_bytes(raw)
        with self.assertRaisesRegex(Denied, 'LEGACY'):
            self.execute()
        self.assertEqual((txn / 'receipt.json').read_bytes(), raw)
        self.assertEqual(self.reconcile()['status'], 'UNKNOWN')
        self.assertEqual(self.calls, [])

    def test_expired_lease_and_implementation_drift_prevent_child_creation(self):
        for case in ('expired', 'implementation'):
            with self.subTest(case=case):
                self.lease.live = case != 'expired'
                self.lease.impl = 'f' * 64 if case == 'implementation' else digest(Path(release.__file__).read_bytes())
                with self.assertRaises(Denied):
                    self.execute()
                self.assertFalse((release.STATE / release.TXN).exists())
        self.assertEqual(self.calls, [])

    def test_live_child_prerequisites_are_reverified_before_any_customer_effect(self):
        for case in ('ACCOUNT', 'RUNTIME', 'missing_runtime', 'uid', 'dynamic_plan'):
            with self.subTest(case=case):
                self.lease.data['checkpoints'] = copy.deepcopy(self.lease.checkpoints)
                self.lease.identity['uid'] = self.base['account_uid']
                self.lease.static.pop('account_uid', None)
                if case in ('ACCOUNT', 'RUNTIME'):
                    self.lease.data['checkpoints'][case]['effect_sha256'] = 'f' * 64
                elif case == 'missing_runtime':
                    self.lease.data['checkpoints'].pop('RUNTIME')
                elif case == 'uid':
                    self.lease.identity['uid'] += 1
                else:
                    self.lease.static['account_uid'] = self.base['account_uid']
                with self.assertRaises(Denied):
                    self.execute()
                self.assertFalse((release.STATE / release.TXN).exists())
        self.assertEqual(self.calls, [])

    def test_fence_loss_during_command_preserves_existing_child_and_newer_outer_ledger(self):
        snapshots = []

        def lose_fence(args):
            if args[:2] == ['/usr/bin/systemctl', 'daemon-reload']:
                path = release.STATE / release.TXN / 'receipt.json'
                snapshots.append(path.read_bytes())
                self.lease.ledger_path.write_bytes(b'{"newer_owner":true}')
        self.command_failure = lose_fence
        with self.assertRaisesRegex(Denied, 'FENCE_LOST'):
            self.execute()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual((release.STATE / release.TXN / 'receipt.json').read_bytes(), snapshots[0])
        self.assertEqual(self.lease.ledger_path.read_bytes(), b'{"newer_owner":true}')
        self.assertEqual(len(self.mutations()), 1)

    def test_narrow_readonly_retry_proof_uses_the_explicitly_approved_action(self):
        self.lease.actions = ['RETRY_TRANSIENT_READONLY_CHECK']
        self.command_failure = lambda args: (release.CommandFailure(args, 7, b'offline transient')
                                            if args[0].endswith('curl') else None)
        with self.assertRaises(resume.Recoverable):
            self.execute()
        proof = self.reconcile()
        self.assertEqual(proof['status'], 'SAFE_TO_RETRY')
        self.assertIn(proof['action'], self.lease.actions)

    def test_narrow_owned_repair_proof_requires_matching_recorded_evidence(self):
        self.lease.actions = ['REPAIR_INCOMPLETE_OWNED_FILE']
        fault, _ = self.interrupt_file_once(release.CODE / 'boot.py', errno.EINTR)
        with fault, self.assertRaises(resume.Recoverable):
            self.execute()
        original = self.receipt()
        proof = self.reconcile()
        self.assertEqual(proof['status'], 'SAFE_TO_RETRY')
        self.assertEqual(proof['action'], 'REPAIR_INCOMPLETE_OWNED_FILE')
        for field, value in (('errno', errno.EIO), ('expected_sha256', 'f' * 64),
                             ('owned_identity', {})):
            with self.subTest(field=field):
                receipt = copy.deepcopy(original)
                receipt['failures'][-1]['evidence'][field] = value
                (release.STATE / release.TXN / 'receipt.json').write_bytes(canonical(receipt))
                self.assertEqual(self.reconcile()['status'], 'UNKNOWN')
        self.assertEqual(self.calls, [])

    def test_narrow_readonly_retry_does_not_adopt_wrong_attempt_or_failure_code(self):
        self.lease.actions = ['RETRY_TRANSIENT_READONLY_CHECK']
        self.command_failure = lambda args: (release.CommandFailure(args, 7, b'offline transient')
                                            if args[0].endswith('curl') else None)
        with self.assertRaises(resume.Recoverable):
            self.execute()
        original = self.receipt()
        commands = copy.deepcopy(self.calls)
        for field, value in (('attempt', 2), ('code', 'UNKNOWN_OR_UNSAFE_EFFECT'),
                             ('step', 'START_RUNTIME')):
            with self.subTest(field=field):
                receipt = copy.deepcopy(original)
                receipt['failures'][-1][field] = value
                (release.STATE / release.TXN / 'receipt.json').write_bytes(canonical(receipt))
                self.assertEqual(self.reconcile()['status'], 'UNKNOWN')
        self.assertEqual(self.calls, commands)

    def test_narrow_actions_cannot_authorize_generic_absent_or_complete_proof(self):
        for action in ('REPAIR_INCOMPLETE_OWNED_FILE', 'RETRY_TRANSIENT_READONLY_CHECK'):
            self.lease.actions = [action]
            self.assertEqual(self.reconcile()['status'], 'UNKNOWN')
        self.execute()
        commands = copy.deepcopy(self.calls)
        for action in ('REPAIR_INCOMPLETE_OWNED_FILE', 'RETRY_TRANSIENT_READONLY_CHECK'):
            self.lease.actions = [action]
            self.assertEqual(self.reconcile()['status'], 'UNKNOWN')
        self.assertEqual(self.calls, commands)

    def test_registry_customer_proof_rejects_child_plan_outside_approved_static_input(self):
        self.execute()
        inputs = {'schema': 1, 'stages': {stage: {} for stage in workflow.STAGES}}
        inputs['stages']['CUSTOMER_APPLY'] = {'static_plan': copy.deepcopy(self.lease.static)}
        ops = operations.OriginalOperations(release, self.source, self.lease.plan, inputs)
        ops.attach(self.lease)
        with self.patches():
            self.assertEqual(ops.inherited('CUSTOMER_APPLY')['state'], 'COMPLETE')
        receipt = self.receipt()
        receipt['plan']['source_commit'] = 'b' * 40
        (release.STATE / release.TXN / 'receipt.json').write_bytes(canonical(receipt))
        with self.patches(), self.assertRaises(Denied):
            ops.inherited('CUSTOMER_APPLY')


if __name__ == '__main__':
    unittest.main()

from tests import test_pr122_customer_workflow as coordinator_fixtures

class ExhaustedRealChildReceiptTests(unittest.TestCase):
    """Actual temp child files/Journal + original adapter, no host commands."""
    inventory=CustomerWorkflowApplyTests.inventory
    patches=CustomerWorkflowApplyTests.patches
    fake_run=CustomerWorkflowApplyTests.fake_run
    receipt=CustomerWorkflowApplyTests.receipt
    def setUp(self):
        CustomerWorkflowApplyTests.setUp(self)
        self.lease.ledger_path.unlink()  # Discard the fixture-only stub, use real coordinator below.
        self.static=copy.deepcopy(self.base)
        self.lost_return=RuntimeError
        self.reconciled=[]
        fixture=self
        class Ops(coordinator_fixtures.OfflineOperations):
            def __init__(self):
                super().__init__()
                self.inputs['CUSTOMER_APPLY']={'static_plan':{k:v for k,v in fixture.static.items() if k not in child.DYNAMIC_FIELDS}}
                self.implementations['CUSTOMER_APPLY']=Path(release.__file__).read_bytes()
            def attach(self,c):
                self.coordinator=c
                self.original=operations.OriginalOperations(release,fixture.source,fixture.base,{'schema':1,'stages':self.inputs})
                self.original.attach(c)
            def account_identity(self):
                return {'uid':fixture.static['account_uid'],'gid':fixture.static['account_gid'],
                        'receipt_sha256':self.receipts['ACCOUNT']['receipt_sha256']}
            def execute(self,stage,lease):
                lease.assert_active();self.executed.append((stage,lease.active['number']))
                if stage=='PROBE' and lease.active['number']<5:raise RuntimeError('known readonly failure')
                if stage=='CUSTOMER_APPLY':
                    child.execute(lease,release,fixture.source)
                    assert fixture.receipt()['state']==resume.SUCCESS
                    raise fixture.lost_return('child success durable, caller return lost')
                return copy.deepcopy(self.receipts[stage])
            def verify(self,stage,checkpoint):
                if stage=='CUSTOMER_APPLY':return self.original.verify(stage,checkpoint)
                return super().verify(stage,checkpoint)
            def reconcile(self,stage,intent,checkpoint,lease):
                fixture.reconciled.append(stage)
                if stage=='CUSTOMER_APPLY':
                    assert lease._readonly
                    return self.original.reconcile(stage,intent,checkpoint,lease)
                return self.proof(stage,'SAFE_TO_RETRY')
        self.ops=Ops()
        self.base['workflow_contract']={'schema':1,'stages':[{'stage':stage,
            'input_sha256':digest(canonical(self.ops.input(stage))),
            'implementation_sha256':digest(self.ops.implementation(stage)),
            'adopt_receipt_sha256':None,'recovery_actions':sorted(workflow.RECOVERY[stage])} for stage in workflow.STAGES]}
        self.approval.update(workflow_contract_sha256=digest(canonical(self.base['workflow_contract'])),
                             plan_sha256=digest(canonical(self.base)))
        self.held.close()
        for adapter in (patch.object(workflow,'protected_directory',lambda p:None),
                        patch.object(workflow,'read_private',lambda p:json.loads(Path(p).read_bytes()))):
            adapter.start();self.addCleanup(adapter.stop)
    def apply_real(self):
        with self.patches(),patch.object(release,'plan',return_value=copy.deepcopy(self.static)):
            return release.workflow_apply(self.source,4,self.base,self.ops)
    def assert_final(self):
        data=json.loads((release.STATE/(release.TXN+'.attempts.json')).read_bytes())
        self.assertEqual(data['state'],'SUCCESS');self.assertEqual(len(data['attempts']),5)
        self.assertEqual(self.receipt()['state'],resume.SUCCESS)
        self.assertEqual([x for x in self.ops.executed if x[0]=='CUSTOMER_APPLY'],[('CUSTOMER_APPLY',5)])
        self.assertEqual(self.calls.count(['/usr/bin/systemctl','start',release.UNITS[0]]),1)
        self.assertIn('CUSTOMER_APPLY',self.reconciled)
    def test_fifth_actual_child_success_receipt_lost_return_converges_without_effect_retry(self):
        self.assertEqual(self.apply_real()['state'],'SUCCESS');self.assert_final()
    def test_fifth_actual_child_success_interrupt_then_restart_only_reconciles(self):
        self.lost_return=KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):self.apply_real()
        before=list(self.calls);executed=list(self.ops.executed)
        self.assertEqual(self.apply_real()['state'],'SUCCESS')
        self.assertEqual(self.calls,before);self.assertEqual(self.ops.executed,executed)
        self.assert_final()
