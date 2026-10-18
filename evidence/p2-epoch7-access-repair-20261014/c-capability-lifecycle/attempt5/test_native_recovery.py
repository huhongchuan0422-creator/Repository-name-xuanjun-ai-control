"""Actual native admission/CAS/phase-loop tests with explicit synthetic host effects.
No UK commands or production provider. Reuses the unchanged transaction Rig.
"""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'runtime'),str(HERE/'original'),str(HERE)]
from attempt_ledger import Ledger
from receipt_provider import ReceiptProvider, Hold, canonical, digest
from native_recovery import NativeRecovery
from test_receipt_provider import ProviderTests
from test_authority_store import grant

def native_suite(env):
    Rig,s=env['Rig'],env['sequence']
    class NativeTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):ProviderTests.setUpClass.__func__(cls)
        @classmethod
        def tearDownClass(cls):cls.tmp.cleanup()
        def setUp(self):
            self.folder=tempfile.TemporaryDirectory();os.chmod(self.folder.name,0o700)
            self.ledger=Ledger(self.folder.name,grant(),clock=lambda:100)
            self.rig=Rig();self.change=lambda request,result:None
            self.provider=ReceiptProvider(self.transport,self.modulus,65537,'TEST_ONLY',clock=lambda:101)
            self.native=NativeRecovery(self.rig.driver,self.ledger,self.provider,{k:self.ledger.grant[k] for k in ('source_commit','source_tree','manifest_sha256')},fixture_mode=True)
        def tearDown(self):self.folder.cleanup()
        def transport(self,request):
            operation=request['operation'];payload=request['payload']
            result={'grant_id':self.ledger.grant['grant_id'],'attempt_id':request['attempt_id']}
            if operation=='verify_fence':result.update(status='HELD',exclusive=True,writer='fixture',lease_epoch=1,fence=1)
            elif operation=='consume_attempt':result.update(status='CONSUMED',ordinal=payload['ordinal'],max_attempts=5)
            elif operation=='authorize_first_admission':result.update(status='AUTHORIZED',policy='P2_ATTEMPT5_V1',context_sha256=payload['context_sha256'])
            elif operation=='authenticate_native_recovery':
                state=json.loads(self.rig.records[s.OUTER_NAME]['data'].decode())['state']
                result.update(status='AUTHORIZED',binding=payload,policy='P2_ATTEMPT5_V1',max_attempts=5,safe_stage=state['stage'])
            elif operation in ('verify_phase_commit','verify_completed_phase'):result.update(status='VERIFIED',checkpoint_sha256=payload['checkpoint_sha256'])
            elif operation=='reconcile_native_intent':
                result.update(status='COMMITTED',binding=payload,observation=s.observation(self.rig.driver.context,payload['phase'],env['h'](payload['phase'])),proof={'outcome':'SAFE_CHECKPOINT','evidence_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64})
            elif operation=='reconcile_unadmitted':result.update(status='RECONCILED',binding=payload,proof={'outcome':'NO_WRITE','evidence_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64})
            elif operation=='commit_safe_reconciliation':result.update(status='RECONCILED',proof=payload['proof'])
            elif operation=='verify_terminal':result.update(status='SUCCESS',proof={'outcome':'SUCCESS','evidence_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64})
            else:raise AssertionError(operation)
            self.change(request,result)
            body={'schema':1,'issuer':'TEST_ONLY','request_sha256':digest(request),'issued_utc':100,'expires_utc':130,'result':result}
            signature=subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=canonical(body))
            return {'body':body,'signature':base64.b64encode(signature).decode()}
        def begin(self):return self.native.begin('d'*64)
        def test_native_claim_and_all_sixteen_durable_transitions(self):
            aid=self.begin();self.assertEqual(self.native.run(aid),'SUCCEEDED')
            state=json.loads(self.rig.records[s.OUTER_NAME]['data'].decode())['state']
            self.assertEqual(state['completed'],list(s.PHASES))
            self.assertEqual([row['name'] for row in self.ledger.snapshot()['completed']],list(s.PHASES))
        def test_success_cannot_start_second_attempt(self):
            aid=self.begin();self.native.run(aid)
            with self.assertRaises(ValueError):self.native.begin('d'*64)
        def test_missing_version_identity_refused(self):
            with self.assertRaises(Hold):NativeRecovery(self.rig.driver,self.ledger,self.provider)
        def test_wrong_version_identity_refused(self):
            identity={k:self.ledger.grant[k] for k in ('source_commit','source_tree','manifest_sha256')}
            identity['source_tree']='f'*40
            with self.assertRaises(Hold):NativeRecovery(self.rig.driver,self.ledger,self.provider,identity)
        def test_missing_provider_refused(self):
            with self.assertRaises(Hold):NativeRecovery(self.rig.driver,self.ledger,None)
        def test_unknown_commit_consumes_and_holds(self):
            aid=self.begin()
            def change(request,result):
                if request['operation']=='verify_phase_commit':result['status']='UNKNOWN'
            self.change=change
            with self.assertRaises(Hold):self.native.run(aid)
            self.assertEqual(self.ledger.snapshot()['attempts'][-1]['state'],'PARTIAL_WRITE')
            with self.assertRaises(ValueError):self.ledger.claim()
            self.assertTrue(any(x.startswith('cleanup:') for x in self.rig.events))
        def test_lease_loss_does_not_repeat_effect(self):
            aid=self.begin()
            def change(request,result):
                if request['operation']=='verify_fence' and request['payload']['step'].startswith('AFTER_'):result['status']='LOST'
            self.change=change
            with self.assertRaises(Hold):self.native.run(aid)
            self.assertEqual([x for x in self.rig.events if x.startswith('phase:')],['phase:'+s.PHASES[0]])
        def test_cross_grant_signed_receipt_refused(self):
            self.change=lambda request,result:result.update(grant_id='OTHER')
            with self.assertRaises(Hold):self.begin()
            self.assertEqual(self.ledger.snapshot()['attempts'],[])
        def test_global_quota_denial_retains_local_claim(self):
            def change(request,result):
                if request['operation']=='consume_attempt':result['status']='EXHAUSTED'
            self.change=change
            with self.assertRaises(Hold):self.begin()
            self.assertEqual(len(self.ledger.snapshot()['attempts']),1)
            with self.assertRaises(ValueError):self.ledger.claim()
        def test_second_driver_cannot_repeat_same_attempt(self):
            aid=self.begin();self.native.run(aid)
            with self.assertRaises(Hold):self.native.run(aid)
        def test_forged_terminal_success_without_success_outcome_refused(self):
            aid=self.begin()
            def change(request,result):
                if request['operation']=='verify_terminal':result['proof']['outcome']='NO_WRITE'
            self.change=change
            with self.assertRaises(Hold):self.native.run(aid)
            with self.assertRaises(ValueError):self.ledger.claim()
        def restart_native(self):
            old=self.rig.driver
            new=s.InjectedDriver(old.gate,old.controls,old.journal_io,old.retained_io,
                                 old.handlers,old.containment,old.diagnostics,old.payloads,old.identity_payloads)
            new.phase=self.rig.phase;self.rig.driver=new
            self.ledger=Ledger(self.folder.name,grant(),clock=lambda:100)
            self.native=NativeRecovery(new,self.ledger,self.provider,{k:self.ledger.grant[k] for k in ('source_commit','source_tree','manifest_sha256')},fixture_mode=True)
        def fail_after_first_effect(self):
            aid=self.begin()
            def change(request,result):
                if request['operation']=='verify_phase_commit':result['status']='UNKNOWN'
            self.change=change
            with self.assertRaises(Hold):self.native.run(aid)
            self.change=lambda request,result:None
            return aid
        def test_restart_reconciles_committed_phase_without_repeating(self):
            aid=self.fail_after_first_effect()
            self.restart_native()
            self.assertEqual(self.native.reconcile(aid),'SAFE_RECONCILED')
            self.restart_native();second=self.begin()
            self.assertNotEqual(aid,second)
            self.assertEqual(self.native.run(second),'SUCCEEDED')
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
            self.assertEqual(len(self.ledger.snapshot()['attempts']),2)
        def test_unreconciled_partial_is_never_resumed(self):
            aid=self.fail_after_first_effect();self.restart_native()
            def change(request,result):
                if request['operation']=='reconcile_native_intent':result['status']='UNKNOWN'
            self.change=change
            with self.assertRaises(Hold):self.native.reconcile(aid)
            with self.assertRaises(ValueError):self.ledger.claim()
        def test_proven_no_native_write_allows_controlled_retry(self):
            first=self.begin()
            self.assertEqual(self.native.reconcile_unadmitted(first),'FAILED_NO_WRITE')
            second=self.begin();self.assertNotEqual(first,second)
            self.assertEqual(self.native.run(second),'SUCCEEDED')
            self.assertEqual(len(self.ledger.snapshot()['attempts']),2)
        def test_unadmitted_unknown_cannot_retry(self):
            first=self.begin()
            def change(request,result):
                if request['operation']=='reconcile_unadmitted':result['status']='UNKNOWN'
            self.change=change
            with self.assertRaises(Hold):self.native.reconcile_unadmitted(first)
            with self.assertRaises(ValueError):self.ledger.claim()
        def test_existing_partial_claim_cannot_be_no_write(self):
            first=self.fail_after_first_effect()
            with self.assertRaises(Hold):self.native.reconcile_unadmitted(first)
            with self.assertRaises(ValueError):self.ledger.claim()
        def test_tampered_component_authority_never_restored(self):
            aid=self.fail_after_first_effect();self.restart_native();self.native.reconcile(aid)
            record=self.rig.records[s.OUTER_NAME]
            value=json.loads(record['data'].decode())
            value['state']['component_checkpoint']['objects']['gate']['values']['authorization']['binding']['schema']=999
            record['data']=s.packed(value)
            self.restart_native();second=self.begin()
            with self.assertRaises(Hold):self.native.run(second)
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
        def test_real_finite_cursor_survives_native_reconciliation(self):
            from epoch7_live_controls import FiniteLiveControls
            controls=FiniteLiveControls.__new__(FiniteLiveControls)
            original=self.rig.controls
            controls.lock=self.rig.lock;controls.next_index=0;controls.open_phase=None;controls.phase_deadline=None
            controls.verify_outer_review=original.verify_outer_review
            controls._begin_guard=original._begin_guard
            controls.observer=original.observer
            def preflight(context):
                controls._begin_guard(False)
                return s.observation(context,'preflight',env['h']('cursor fixture preflight'))
            controls.preflight=preflight
            controls._boundary=lambda context,phase,boundary,index:s.observation(context,boundary+':'+phase,env['h'](phase))
            self.rig.controls=controls;self.rig.driver.controls=controls
            aid=self.fail_after_first_effect()
            self.assertEqual(controls.next_index,1)
            self.restart_native()
            self.native.reconcile(aid)
            # Recreate the native process cursor, then restore from persisted
            # component state. Actual before/after methods enforce phase order.
            controls.next_index=0;controls.open_phase=None
            self.restart_native();second=self.begin();self.native.run(second)
            self.assertEqual(controls.next_index,16)
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
        def test_checkpoint_drift_blocks_recovery(self):
            aid=self.fail_after_first_effect();self.restart_native();self.native.reconcile(aid)
            self.restart_native();second=self.begin()
            def change(request,result):
                if request['operation']=='verify_completed_phase':result['checkpoint_sha256']='f'*64
            self.change=change
            with self.assertRaises(Hold):self.native.run(second)
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
        def test_reconciliation_receipt_is_retained(self):
            aid=self.fail_after_first_effect();self.restart_native();self.native.reconcile(aid)
            state=json.loads(self.rig.records[s.OUTER_NAME]['data'].decode())['state']
            self.assertEqual(state['attempt5_recoveries'][0]['attempt'],aid)
            self.assertEqual(state['completed'],[s.PHASES[0]])
        def test_drifted_fence_holds(self):
            aid=self.begin()
            def change(request,result):
                if request['operation']=='verify_fence' and request['payload']['step']=='START':result['fence']=2
            self.change=change
            with self.assertRaises(Hold):self.native.run(aid)
            self.assertFalse(any(x.startswith('phase:') for x in self.rig.events))
    return unittest.defaultTestLoader.loadTestsFromTestCase(NativeTests)

def run(candidate):
    spec=importlib.util.spec_from_file_location('original_transactions',str(candidate/'tests/test_successor_transactions.py'))
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    return original.run_isolated(extra_suite_factory=native_suite,include_existing=False)
if __name__=='__main__':sys.exit(run(Path(sys.argv[1])))
