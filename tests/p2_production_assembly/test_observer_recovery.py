"""Real native authorization/projection and single-use-lock recovery regressions.

Only host IO/facts are isolated fixtures. Gate, ClaimAuthority, journal parsing,
native_state, ExistingInstallLock and PermitCycle recovery entry are actual code.
No production host or installation commands are used.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT/'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle'
sys.path[:0] = [str(CANDIDATE/'attempt5/runtime'),str(CANDIDATE/'attempt5/original')]
spec = importlib.util.spec_from_file_location('observer_recovery_server',
    str(ROOT/'production/p2_attempt5/observer_server.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

def suite(env):
    import native_state
    from receipt_provider import Hold
    from native_recovery import NativeRecovery
    from permit_cycle import policy
    Rig, sequence, host = env['Rig'],env['sequence'],env['host']
    class RecoveryTests(unittest.TestCase):
        def setUp(self):
            self.tmp = tempfile.TemporaryDirectory()
            self.addCleanup(self.tmp.cleanup)
            self.path = Path(self.tmp.name)/'native.lock'
            self.path.write_bytes(b'SYNTHETIC_ONLY_EXISTING_INSTALL_LOCK')
            os.chmod(str(self.path),0o600)
            self.record = dict(host.fs.metadata(os.stat(str(self.path))),
                kind='FILE',sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
            self.rig = self.fresh_rig()
            self.session = types.SimpleNamespace(driver=self.rig.driver,
                cfg={'grant':dict(source_commit='a'*40,source_tree='b'*40,
                    kit_sha256='c'*64,manifest_sha256='d'*64)},
                attestation={'checkpoint':{'sha256':'e'*64},'invoke_id':'FIXTURE'})
            self.reader = server.NativeReader(self.session)

        def fresh_lock(self):
            # Real constructor/enter/held/exit; only fixed path routed to fixture.
            lock = host.ExistingInstallLock(self.record)
            lock.path = str(self.path)
            return lock

        def fresh_rig(self):
            rig = Rig()
            rig.lock = self.fresh_lock()
            rig.verifier.lock_check = rig.lock.held
            rig.verifier.checked_under_lock = False
            rig.verifier.cached = None
            rig.driver.containment.runtime = types.SimpleNamespace(successful_commands={})
            # Actual immutable binding compiled from the original trusted gate.
            binding = {'claim_successor_sha256':sequence.retained.successor.digest(rig.gate.claim_successor),
                'review_id':rig.gate.review_id,'approval_body_sha256':rig.verifier.body_sha,
                'authorization_sha256':sequence.retained.d.digest(rig.gate.expected),
                'delta_sha256':rig.gate.delta_sha256,
                'complete_delta_sha256':rig.gate.expected['complete_delta_sha256'],
                'additive_targets_sha256':rig.gate.additions_sha256,
                'snapshot_sha256':rig.gate.delta['snapshot_sha256']}
            def absent_boot(path):raise FileNotFoundError(path)
            rig.outer_io._parent = absent_boot
            rig.outer_io.authority = host.ClaimAuthority(rig.lock,rig.verifier,rig.driver.context,binding)
            return rig

        def records(self, completed=0, intent=False, pending=False):
            rig = self.rig
            with rig.lock:
                rig.controls.verify_outer_review(rig.driver.context)
                # Fixture creates a legitimate pre-active authorization once.
                # Recovery below must never call this pre-active gate.check().
                rig.gate.check()
                done = list(sequence.PHASES[:completed])
                checkpoint = native_state.capture(rig.driver,done)
                state = {'admission':'ADMITTED','completed':done,'stage':
                    (sequence.PHASES[completed]+'_INTENT' if intent else
                     (done[-1]+'_COMPLETE' if done else 'ADMITTED')),
                    'component_checkpoint':checkpoint,'phase_evidence':{}}
                if pending:
                    state['pending_components'] = native_state.capture(rig.driver,
                        done+[sequence.PHASES[completed]])
                    state['pending_observation'] = sequence.observation(
                        rig.driver.context,sequence.PHASES[completed],env['h']('pending'))
                binding = rig.gate.journal_binding()
                outer = {'schema':1,'name':sequence.OUTER_NAME,
                    'transaction_id':sequence.retained.d.TX,
                    'context_sha256':rig.driver.context['context_sha256'],
                    'binding':binding,'state':state}
                inner = {'schema':1,'name':rig.driver.inner.name,
                    'transaction_id':sequence.retained.d.TX,'binding':binding,'state':{}}
                for value in (outer,inner):
                    rig.records[value['name']] = rig.ops.record(
                        sequence.retained.d.canonical(value)+b'\n')
            fresh = self.fresh_rig()
            fresh.records = copy.deepcopy(rig.records)
            self.rig = fresh
            self.session.driver = fresh.driver
            return state

        def read_project(self, pending=False):
            rig = self.rig
            before = copy.deepcopy(rig.records)
            self.assertIsNone(rig.gate.authorization)
            with rig.lock:
                rig.controls.verify_outer_review(rig.driver.context)
                with mock.patch.object(rig.gate,'check',side_effect=AssertionError('NO_PREACTIVE_GATE')):
                    record, inner, state = self.reader.journals()
                    done = state['completed'] + ([sequence.PHASES[len(state['completed'])]] if pending else [])
                    key = 'pending_components' if pending else 'component_checkpoint'
                    with self.reader.projection(state[key],done):
                        self.assertEqual(rig.gate.journal_binding(),rig.outer_io.authority.binding)
                        rig.outer_io.authority.receipt()
                    self.assertIsNone(rig.gate.authorization)
            self.assertEqual(before,rig.records)
            self.assertFalse(any(e.startswith('phase:') for e in rig.events))
            return state

        def test_fresh_admitted_projection(self):
            self.records();self.read_project()
        def test_fresh_completed_projection(self):
            self.records(3);self.read_project()
        def test_fresh_intent_without_pending_projection(self):
            self.records(3,True);self.read_project()
        def test_fresh_intent_pending_projection(self):
            self.records(3,True,True);self.read_project(True)
        def test_fresh_terminal_projection(self):
            self.records(16);self.read_project()
        def test_missing_review_before_journal_read_holds(self):
            self.records()
            with self.rig.lock:
                with self.assertRaises(ValueError):self.reader.journals()
            self.assertNotIn('outer:readback',self.rig.events)
        def change(self, name, edit):
            row = self.rig.records[name]
            value = json.loads(row['data'].decode())
            edit(value)
            row['data'] = sequence.retained.d.canonical(value)+b'\n'
        def rejected(self):
            with self.rig.lock:
                self.rig.controls.verify_outer_review(self.rig.driver.context)
                with self.assertRaises((ValueError,RuntimeError,Hold)):
                    rec,inner,state=self.reader.journals()
                    with self.reader.projection(state['component_checkpoint'],state['completed']):pass
                self.assertIsNone(self.rig.gate.authorization)
        def test_wrong_outer_claim_holds(self):
            self.records();self.change(sequence.OUTER_NAME,lambda v:v['binding'].update(review_id=1))
            self.rejected()
        def test_wrong_inner_binding_holds(self):
            self.records();self.change(self.rig.driver.inner.name,lambda v:v['binding'].update(review_id=1))
            self.rejected()
        def test_wrong_inner_name_holds(self):
            self.records();self.change(self.rig.driver.inner.name,lambda v:v.update(name='WRONG'))
            self.rejected()
        def test_wrong_checkpoint_review_holds(self):
            self.records();self.change(sequence.OUTER_NAME,lambda v:
                v['state']['component_checkpoint']['objects']['gate']['values']['authorization'].update(review_id=1))
            self.rejected()
        def test_wrong_checkpoint_cache_holds(self):
            self.records();self.change(sequence.OUTER_NAME,lambda v:
                v['state']['component_checkpoint']['objects']['verifier']['values']['cached'].update(body_sha256='f'*64))
            self.rejected()
        def test_projection_failure_restores_fields(self):
            self.records()
            with self.rig.lock:
                self.rig.controls.verify_outer_review(self.rig.driver.context)
                state=self.reader.journals()[2]
                with self.assertRaisesRegex(RuntimeError,'INJECTED'):
                    with self.reader.projection(state['component_checkpoint'],[]):
                        raise RuntimeError('INJECTED')
                self.assertIsNone(self.rig.gate.authorization)
        def test_lock_object_cannot_be_reentered(self):
            lock=self.rig.lock
            with lock:self.assertTrue(lock.held())
            with self.assertRaises(ValueError):
                with lock:pass
        def test_same_measured_lock_excludes_other_scope(self):
            first=self.rig.lock;second=self.fresh_lock()
            with first:
                with self.assertRaises(BlockingIOError):
                    with second:pass
                self.assertTrue(first.held())

        def cycle_case(self, recovery='NO_WRITE', actions=False, unknown=False, exception=False):
            # NativeRecovery type and actual PermitCycle.recover/checked are
            # retained. Only ledger/remote fact IO and terminal reconcile bodies
            # are isolated; lock enter/exit is the unchanged real class.
            locks=[];seen=[];ordinal=[1]
            grant={'grant_id':'FIXTURE','approval_body_sha256':'a'*64,
                   'source_commit':'b'*40,'source_tree':'c'*40,
                   'kit_sha256':'d'*64,'manifest_sha256':'e'*64}
            action={'id':'APPROVED','target':'/var/lib/xuanjun-attempt5/config/a.json',
                'before_sha256':'1'*64,'after_sha256':'2'*64,
                'payload_sha256':'3'*64,'checkpoint_sha256':'4'*64}
            approved=policy()
            if actions:approved['configuration_actions']=[action]
            class Ledger(object):
                def __init__(inner):inner.grant=grant
                def reconcile(inner,attempt,proof,verify):
                    self.assertTrue(verify(proof))
                    seen.append(('reconciled:NO_WRITE',attempt))
                def snapshot(inner):return {'attempts':[{'id':'same-attempt','ordinal':ordinal[0],
                    'state':'PARTIAL_WRITE','events':[{'kind':'execution_intent'}]}]}
            class Native(NativeRecovery):
                def __init__(inner):
                    inner.ledger=Ledger();inner.cycle_policy=approved;inner.approval_review_id=17
                    lock=self.fresh_lock();locks.append(lock)
                    inner.driver=types.SimpleNamespace(controls=types.SimpleNamespace(install_lock=lambda:lock),
                        journal_io=types.SimpleNamespace(journal_exists=lambda name:False,
                            read_journal=lambda name:self.rig.ops.record(sequence.retained.d.canonical(
                                {'state':{'admission':'ADMITTED','stage':'ADMITTED','completed':[]}})+b'\n')),
                        retained_io=types.SimpleNamespace(journal_exists=lambda name:False),
                        inner=types.SimpleNamespace(name='FIXTURE_INNER'))
                    inner.s=sequence
                def confirm_admission(inner,attempt,command):seen.append(('confirm',attempt))
                def converge_committed(inner,attempt):return False
                def fence(inner,attempt,step):
                    self.assertEqual(attempt,'same-attempt')
                def proof(inner,attempt,operation,payload):
                    if operation=='diagnose_attempt':
                        result=dict(binding=payload,status='UNKNOWN' if unknown else 'DIAGNOSED',
                            transaction_consistent=True,recovery=recovery,configuration_actions=
                            (['APPROVED'] if actions else []),
                            source_identity={k:grant[k] for k in
                            ('source_commit','source_tree','kit_sha256','manifest_sha256')})
                    elif operation=='reconcile_unadmitted':
                        result=dict(binding=payload,status='RECONCILED',proof={
                            'outcome':'NO_WRITE','evidence_sha256':'a'*64,
                            'checkpoint_sha256':'b'*64,'log_sha256':'c'*64})
                    else:
                        result=dict(binding=payload,status='COMMITTED',action=action,
                            backup_sha256=action['before_sha256'],after_sha256=action['after_sha256'])
                    session=object.__new__(server.ObserverSession)
                    session.driver=inner.driver
                    session.mutex=threading.RLock()
                    session.pending={'grant_sha256':server.digest(grant),'attempt_id':attempt,
                        'operation':operation,'payload':payload}
                    session.fence=lambda attempt:('same-writer',1,1)
                    session.reader=types.SimpleNamespace(observe=lambda op,p:read(op))
                    session.attestation={'run_id':'FIXTURE','job_id':'FIXTURE','invoke_id':'FIXTURE',
                        'backup':{'sha256':'a'*64},'checkpoint':{'sha256':'b'*64},
                        'expires_utc':9999999999}
                    session.cfg={'grant':{'expires_utc':9999999999}}
                    session.spec={'issuer':'FIXTURE'}
                    class BeforeSign(Exception):pass
                    def sign(raw):raise BeforeSign()
                    session.signer=sign
                    def read(op):
                        self.assertTrue(inner.driver.controls.install_lock().held())
                        seen.append((op,attempt))
                        if exception:raise TimeoutError('FIXTURE_TIMEOUT')
                        return result
                    binding=dict(session.pending)
                    request={'schema':1,'nonce':'a'*32,'payload':payload,'binding':{
                        'grant_sha256':binding['grant_sha256'],'attempt_id':attempt,
                        'operation':operation,'payload_sha256':server.digest(payload)}}
                    try:session._handle(request)
                    except BeforeSign:return result
                    raise AssertionError('UNREACHABLE_UNSIGNED_SUCCESS')
                def reconcile_unadmitted(inner,attempt):
                    return NativeRecovery.reconcile_unadmitted(inner,attempt)
                def reconcile(inner,attempt):
                    return NativeRecovery.reconcile(inner,attempt)
                def _recover_completed(inner,attempt,record,state):
                    self.assertTrue(inner.driver.controls.install_lock().held())
                    seen.append(('reconciled:NATIVE_CAS',attempt))
            cycle=server.ObserverPermitCycle(Native,approved)
            if unknown or exception:
                with self.assertRaises((Hold,RuntimeError,TimeoutError)):cycle.recover('same-attempt','f'*64)
                self.assertFalse(any(x[0].startswith('reconciled:') for x in seen))
            else:
                cycle.recover('same-attempt','f'*64)
                self.assertIn(('reconciled:'+recovery,'same-attempt'),seen)
            self.assertTrue(all(lock.entered and lock.fd is None for lock in locks))
            self.assertEqual(ordinal,[1])
            return locks
        def test_diagnose_then_no_write_reconcile_single_use(self):
            self.cycle_case()
        def test_diagnose_then_native_reconcile_single_use(self):
            self.cycle_case('NATIVE_CAS')
        def test_approved_config_then_reconcile_single_use(self):
            self.cycle_case('NATIVE_CAS',actions=True)
        def test_unknown_diagnosis_holds_and_releases(self):
            self.cycle_case(unknown=True)
        def test_timeout_holds_and_releases(self):
            self.cycle_case(exception=True)
        def test_next_fresh_driver_same_lock_identity(self):
            locks=self.cycle_case()
            next_lock=self.fresh_lock()
            with next_lock:self.assertTrue(next_lock.held())
            self.assertEqual(locks[0].expected,next_lock.expected)
    result=unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests)
    assert result.countTestCases()==20
    return result

if __name__=='__main__':
    original_spec=importlib.util.spec_from_file_location('original_transactions',
        str(CANDIDATE/'tests/test_successor_transactions.py'))
    original=importlib.util.module_from_spec(original_spec)
    original_spec.loader.exec_module(original)
    sys.exit(original.run_isolated(extra_suite_factory=suite,include_existing=False))
