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
from permit_cycle import PermitCycle
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
            elif operation in ('verify_cycle_binding','diagnose_attempt','apply_approved_configuration'):
                result.update(binding=payload,source_identity={k:self.ledger.grant[k] for k in ('source_commit','source_tree','kit_sha256','manifest_sha256')})
                if operation=='verify_cycle_binding':result.update(status='UNCHANGED')
                elif operation=='diagnose_attempt':result.update(status='DIAGNOSED',transaction_consistent=True,recovery='NATIVE_CAS' if s.OUTER_NAME in self.rig.records else 'NO_WRITE',configuration_actions=[])
                else:raise AssertionError('No configured action adapter')
            elif operation=='authorize_first_admission':result.update(status='AUTHORIZED',policy='P2_ATTEMPT5_V1',context_sha256=payload['context_sha256'])
            elif operation=='authenticate_native_recovery':
                state=json.loads(self.rig.records[s.OUTER_NAME]['data'].decode())['state']
                result.update(status='AUTHORIZED',binding=payload,policy='P2_ATTEMPT5_V1',max_attempts=5,safe_stage=state['stage'])
            elif operation in ('verify_phase_commit','verify_completed_phase'):result.update(status='VERIFIED',checkpoint_sha256=payload['checkpoint_sha256'])
            elif operation=='reconcile_native_intent':
                result.update(status='COMMITTED',binding=payload,observation=s.observation(self.rig.driver.context,payload['phase'],env['h'](payload['phase'])),proof={'outcome':'SAFE_CHECKPOINT','evidence_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64})
            elif operation=='read_committed_outcome':result.update(status='UNRESOLVED',binding=payload,committed=None)
            elif operation=='reconcile_completed_checkpoint':result.update(status='RECONCILED',proof={'outcome':'SAFE_CHECKPOINT','evidence_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64})
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
        def test_full_service_ledger_native_chain_five_attempts(self):
            from authority_store import AuthorityStore
            from issuer_service import IssuerService
            store=AuthorityStore(str(Path(self.folder.name)/'trusted-fixture-service.db'),initialize=True,clock=lambda:100)
            try:
                store.register(self.ledger.grant)
                original=self.transport
                def host_readback(g,aid,operation,payload):
                    request={'schema':1,'grant_sha256':digest(g),'attempt_id':aid,
                             'operation':operation,'nonce':'0'*32,'payload':payload}
                    result=original(request)['body']['result']
                    return {'grant_sha256':digest(g),'attempt_id':aid,'operation':operation,
                            'payload_sha256':digest(payload),'run_id':'TEST_RUN','job_id':'TEST_JOB',
                            'invoke_id':'TEST_INVOKE','backup_sha256':'a'*64,
                            'checkpoint_sha256':'b'*64,'log_sha256':'c'*64,'result':result}
                signer=lambda raw:subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=raw)
                service=IssuerService(store,host_readback,signer,'TEST_ONLY')
                principal={'actor_id':self.ledger.grant['actor_id'],'host':'TEST_ONLY','writer_id':'isolated-service-writer'}
                self.provider=ReceiptProvider(lambda request:service.handle(request,principal),
                                              self.modulus,65537,'TEST_ONLY',clock=lambda:101)
                self.native=NativeRecovery(self.rig.driver,self.ledger,self.provider,
                    {k:self.ledger.grant[k] for k in ('source_commit','source_tree','manifest_sha256')},fixture_mode=True)
                ids=[]
                for ordinal in range(1,5):
                    aid=self.begin();ids.append(aid)
                    self.assertEqual(self.native.reconcile_unadmitted(aid),'FAILED_NO_WRITE')
                fifth=self.begin();ids.append(fifth)
                self.assertEqual(self.native.run(fifth),'SUCCEEDED')
                self.assertEqual(len(set(ids)),5)
                self.assertEqual(store.db.execute('SELECT consumed,terminal FROM grants').fetchone(),(5,1))
                self.assertEqual(len([x for x in self.rig.events if x.startswith('phase:')]),16)
                with self.assertRaises(Hold):self.begin()
            finally:store.close()
        def test_full_service_autonomous_one_permit_fifth_success(self):
            from authority_store import AuthorityStore
            from issuer_service import IssuerService
            store=AuthorityStore(str(Path(self.folder.name)/'trusted-fixture-service.db'),initialize=True,clock=lambda:100)
            try:
                store.register(self.ledger.grant)
                from permit_cycle import policy
                approved=policy()
                store.register_cycle(self.ledger.grant,approved,{'grant_sha256':digest(self.ledger.grant),
                    'approval_body_sha256':self.ledger.grant['approval_body_sha256'],
                    'cycle_policy_sha256':digest(approved),'review_id':9000000001})
                self.admission_failures(4)
                original=self.transport
                def host_readback(g,aid,operation,payload):
                    request={'schema':1,'grant_sha256':digest(g),'attempt_id':aid,
                             'operation':operation,'nonce':'0'*32,'payload':payload}
                    result=original(request)['body']['result']
                    return {'grant_sha256':digest(g),'attempt_id':aid,'operation':operation,
                            'payload_sha256':digest(payload),'run_id':'TEST_RUN','job_id':'TEST_JOB',
                            'invoke_id':'TEST_INVOKE','backup_sha256':'a'*64,
                            'checkpoint_sha256':'b'*64,'log_sha256':'c'*64,'result':result}
                signer=lambda raw:subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=raw)
                service=IssuerService(store,host_readback,signer,'TEST_ONLY')
                principal={'actor_id':self.ledger.grant['actor_id'],'host':'TEST_ONLY','writer_id':'isolated-service-writer'}
                self.provider=ReceiptProvider(lambda request:service.handle(request,principal),
                                              self.modulus,65537,'TEST_ONLY',clock=lambda:101)
                self.native=NativeRecovery(self.rig.driver,self.ledger,self.provider,
                    {k:self.ledger.grant[k] for k in ('source_commit','source_tree','manifest_sha256')},fixture_mode=True)
                def factory():
                    self.restart_native()
                    self.native.approval_review_id=9000000001
                    return self.native
                report=PermitCycle(factory).run('d'*64)
                self.assertEqual((report['status'],report['used']),('SUCCEEDED',5))
                self.assertEqual(store.db.execute('SELECT consumed,terminal FROM grants').fetchone(),(5,1))
                self.assertEqual(len([x for x in self.rig.events if x.startswith('phase:')]),16)
                self.assertEqual(store.db.execute('SELECT count(*) FROM cycles').fetchone()[0],1)
                self.assertEqual(len(list(Path(self.folder.name).glob('cycle-report-*.json'))),1)
            finally:store.close()
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
        def connect_real_service(self):
            from authority_store import AuthorityStore
            from issuer_service import IssuerService
            store=AuthorityStore(str(Path(self.folder.name)/'recovery-service.db'),initialize=True,clock=lambda:100)
            store.register(self.ledger.grant)
            original=self.transport
            def host(g,aid,operation,payload):
                request={'schema':1,'grant_sha256':digest(g),'attempt_id':aid,'operation':operation,'nonce':'0'*32,'payload':payload}
                result=original(request)['body']['result']
                return {'grant_sha256':digest(g),'attempt_id':aid,'operation':operation,'payload_sha256':digest(payload),
                        'run_id':'TEST_RUN','job_id':'TEST_JOB','invoke_id':'TEST_INVOKE','backup_sha256':'a'*64,
                        'checkpoint_sha256':'b'*64,'log_sha256':'c'*64,'result':result}
            signer=lambda raw:subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=raw)
            service=IssuerService(store,host,signer,'TEST_ONLY')
            principal={'actor_id':self.ledger.grant['actor_id'],'host':'TEST_ONLY','writer_id':'fixture-recovery-writer'}
            self.provider=ReceiptProvider(lambda request:service.handle(request,principal),self.modulus,65537,'TEST_ONLY',clock=lambda:101)
            self.restart_native()
            return store,service
        def test_complete_cas_then_local_checkpoint_failure_converges(self):
            aid=self.begin()
            self.ledger.checkpoint=lambda *args:(_ for _ in ()).throw(IOError('fixture checkpoint disk failure'))
            with self.assertRaises(IOError):self.native.run(aid)
            self.restart_native();self.assertEqual(self.native.reconcile(aid),'SAFE_RECONCILED')
            self.restart_native();self.native.run(self.begin())
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
        def test_admitted_checkpoint_can_reconcile_without_reclaim(self):
            aid=self.begin()
            def change(request,result):
                if request['operation']=='verify_fence' and request['payload']['step']=='BEFORE_'+s.PHASES[0]:result['status']='LOST'
            self.change=change
            with self.assertRaises(Hold):self.native.run(aid)
            self.change=lambda request,result:None
            self.restart_native();self.assertEqual(self.native.reconcile(aid),'SAFE_RECONCILED')
            self.restart_native();self.native.run(self.begin())
            self.assertEqual(len([e for e in self.rig.events if e.startswith('phase:')]),16)
        def test_complete_checkpoint_unknown_host_still_holds(self):
            aid=self.begin();self.ledger.checkpoint=lambda *args:(_ for _ in ()).throw(IOError('checkpoint'))
            with self.assertRaises(IOError):self.native.run(aid)
            self.restart_native()
            self.change=lambda request,result:result.update(status='UNKNOWN') if request['operation']=='verify_completed_phase' else None
            with self.assertRaises(Hold):self.native.reconcile(aid)
            self.assertEqual(self.ledger.snapshot()['attempts'][-1]['state'],'PARTIAL_WRITE')
        def test_safe_reconcile_commit_then_lost_response_recovers(self):
            store,service=self.connect_real_service()
            try:
                aid=self.fail_after_first_effect();self.restart_native()
                signer=service.signer
                def fail(raw):
                    if json.loads(raw)['result'].get('status')=='RECONCILED':raise IOError('fixture signer failure after commit')
                    return signer(raw)
                service.signer=fail
                with self.assertRaises(Hold):self.native.reconcile(aid)
                self.assertEqual(store.db.execute('SELECT state FROM attempts').fetchone()[0],'SAFE_CHECKPOINT')
                service.signer=signer;self.restart_native()
                self.assertEqual(self.native.reconcile(aid),'SAFE_RECONCILED')
                self.restart_native();self.native.run(self.begin())
                self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
            finally:store.close()
        def test_terminal_success_response_loss_recovers_read_only(self):
            store,service=self.connect_real_service()
            try:
                signer=service.signer
                def fail(raw):
                    if json.loads(raw)['result'].get('status')=='SUCCESS':raise IOError('fixture terminal signer failure')
                    return signer(raw)
                service.signer=fail;aid=self.begin()
                with self.assertRaises(Hold):self.native.run(aid)
                self.assertEqual(store.db.execute('SELECT consumed,terminal FROM grants').fetchone(),(1,1))
                service.signer=signer;self.restart_native()
                leases=store.db.execute("SELECT count(*) FROM audit WHERE event='LEASE'").fetchone()[0]
                self.assertEqual(self.native.reconcile(aid),'SUCCEEDED')
                self.assertEqual(store.db.execute("SELECT count(*) FROM audit WHERE event='LEASE'").fetchone()[0],leases)
                self.assertEqual(len([e for e in self.rig.events if e.startswith('phase:')]),16)
            finally:store.close()
        def test_terminal_audit_failure_survives_service_restart(self):
            from authority_store import AuthorityStore
            store,service=self.connect_real_service()
            try:
                audit=store.audit
                def fail(gid,event,body):
                    if event=='SIGNED_RECEIPT' and body['operation']=='verify_terminal':raise IOError('fixture audit disk failure')
                    return audit(gid,event,body)
                store.audit=fail;aid=self.begin()
                with self.assertRaises(Hold):self.native.run(aid)
                store.close()
                store=AuthorityStore(str(Path(self.folder.name)/'recovery-service.db'),clock=lambda:100)
                service.store=store;self.restart_native()
                self.assertEqual(self.native.reconcile(aid),'SUCCEEDED')
                self.assertEqual(store.db.execute('SELECT consumed,terminal FROM grants').fetchone(),(1,1))
            finally:store.close()
        def test_all_sixteen_complete_before_local_checkpoint_failure_recovers_success(self):
            store,service=self.connect_real_service()
            try:
                aid=self.begin();checkpoint=self.ledger.checkpoint
                def fail(aid,phase,pin):
                    if phase==s.PHASES[-1]:raise IOError('fixture final checkpoint failure')
                    return checkpoint(aid,phase,pin)
                self.ledger.checkpoint=fail
                with self.assertRaises(IOError):self.native.run(aid)
                self.restart_native();self.assertEqual(self.native.reconcile(aid),'SUCCEEDED')
                self.assertEqual(len(self.ledger.snapshot()['completed']),16)
                self.assertEqual(store.db.execute('SELECT consumed,terminal FROM grants').fetchone(),(1,1))
                self.assertEqual(len([e for e in self.rig.events if e.startswith('phase:')]),16)
            finally:store.close()
        def test_native_complete_cas_post_commit_interrupt_recovery(self):
            save=s.OuterJournal.save
            def fail(journal,state):
                result=save(journal,state)
                if state.get('stage')==s.PHASES[0]+'_COMPLETE':raise IOError('fixture crash after native CAS')
                return result
            aid=self.begin();s.OuterJournal.save=fail
            try:
                with self.assertRaises(IOError):self.native.run(aid)
            finally:s.OuterJournal.save=save
            self.restart_native();self.assertEqual(self.native.reconcile(aid),'SAFE_RECONCILED')
            self.restart_native();self.native.run(self.begin())
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
        def test_cycle_terminal_lost_response_converges_without_new_attempt(self):
            store,service=self.connect_real_service()
            try:
                signer=service.signer
                service.signer=lambda raw:(_ for _ in ()).throw(IOError('fixture lost terminal')) if json.loads(raw)['result'].get('status')=='SUCCESS' else signer(raw)
                aid=self.begin()
                with self.assertRaises(Hold):self.native.run(aid)
                service.signer=signer
                report=self.cycle().run('d'*64)
                self.assertEqual((report['status'],report['used']),('SUCCEEDED',1))
                self.assertEqual(len(report['ledger']['completed']),16)
                self.assertEqual(len([e for e in self.rig.events if e.startswith('phase:')]),16)
            finally:store.close()
        def cycle(self):
            def factory():
                self.restart_native()
                return self.native
            return PermitCycle(factory)
        def admission_failures(self,count):
            seen=[0]
            def change(request,result):
                if request['operation']=='authorize_first_admission':
                    seen[0]+=1
                    if seen[0]<=count:result['status']='DENIED'
            self.change=change
            return seen
        def test_cycle_four_failures_then_fifth_success_one_grant(self):
            seen=self.admission_failures(4)
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('SUCCEEDED',5))
            self.assertEqual(seen[0],5)
            self.assertEqual(len(set(a['id'] for a in report['ledger']['attempts'])),5)
            self.assertEqual(report['approval_body_sha256'],self.ledger.grant['approval_body_sha256'])
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
        def test_cycle_approved_configuration_automatically_applied_with_backup(self):
            from approved_config import ApprovedConfiguration,sha
            from permit_cycle import policy
            with tempfile.TemporaryDirectory(prefix='cycle-config-',dir='/') as root:
                os.chmod(root,0o700)
                target=Path(root)/'settings.json';target.write_bytes(b'{"retry":1}');os.chmod(str(target),0o600)
                new=b'{"retry":2}'
                action={'id':'retry-limit','target':str(target),'before_sha256':sha(target.read_bytes()),'after_sha256':sha(new),
                        'payload_sha256':sha(new),'checkpoint_sha256':'a'*64}
                approved=policy();approved['configuration_actions']=[action]
                config=ApprovedConfiguration(root,{'retry-limit':('settings.json',new)},lambda:self.native.fence(self.ledger.snapshot()['attempts'][-1]['id'],'CONFIG_CAS'),lambda:'a'*64)
                failures=[0]
                def change(request,result):
                    if request['operation']=='authorize_first_admission':
                        failures[0]+=1
                        if failures[0]==1:result['status']='DENIED'
                    if request['operation']=='diagnose_attempt':result['configuration_actions']=['retry-limit']
                    if request['operation']=='apply_approved_configuration':result.update(config.apply(request['payload']['action']))
                self.change=change
                original=self.transport
                # The fixture transport's default denies config operations;
                # route this exact approved action through the real CAS helper.
                def transport(request):
                    if request['operation']=='apply_approved_configuration':
                        result={'grant_id':self.ledger.grant['grant_id'],'attempt_id':request['attempt_id'],'binding':request['payload']}
                        result.update(config.apply(request['payload']['action']))
                        body={'schema':1,'issuer':'TEST_ONLY','request_sha256':digest(request),'issued_utc':100,'expires_utc':130,'result':result}
                        signature=subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=canonical(body))
                        return {'body':body,'signature':base64.b64encode(signature).decode()}
                    return original(request)
                self.provider=ReceiptProvider(transport,self.modulus,65537,'TEST_ONLY',clock=lambda:101)
                def factory():
                    self.restart_native()
                    self.native=NativeRecovery(self.rig.driver,self.ledger,self.provider,
                        {k:self.ledger.grant[k] for k in ('source_commit','source_tree','manifest_sha256')},fixture_mode=True,cycle_policy=approved)
                    return self.native
                try:
                    report=PermitCycle(factory,approved).run('d'*64)
                    self.assertEqual((report['status'],report['used']),('SUCCEEDED',2))
                    self.assertEqual(target.read_bytes(),new)
                    self.assertEqual(len(list(Path(root).glob('backup-*.json'))),1)
                finally:config.close()
        def test_cycle_parallel_controller_refused_without_claim(self):
            import fcntl
            path=os.path.join(self.folder.name,'permit-cycle.lock')
            fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(Hold):self.cycle().run('d'*64)
                self.assertEqual(self.ledger.snapshot()['attempts'],[])
            finally:os.close(fd)
        def test_cycle_first_success_stops(self):
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('SUCCEEDED',1))
        def test_cycle_five_failures_exhausted_full_report(self):
            self.admission_failures(9)
            previous=self.change
            def change(request,result):
                previous(request,result)
                if request['operation']=='diagnose_attempt' and len(self.ledger.snapshot()['attempts'])==5:
                    result['configuration_actions']=['must-not-execute-after-quota-exhausted']
            self.change=change
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('EXHAUSTED',5))
            self.assertTrue(all(a['state']=='FAILED_NO_WRITE' for a in report['ledger']['attempts']))
        def test_cycle_restart_does_not_reset_exhausted_quota(self):
            self.admission_failures(9)
            self.cycle().run('d'*64)
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('EXHAUSTED',5))
        def test_cycle_unknown_holds_same_permit_then_recovers(self):
            def change(request,result):
                if request['operation'] in ('authorize_first_admission','diagnose_attempt'):result['status']='UNKNOWN'
            self.change=change
            first=self.cycle().run('d'*64)
            self.assertEqual((first['status'],first['used']),('HOLD',1))
            self.change=lambda request,result:None
            second=self.cycle().run('d'*64)
            self.assertEqual((second['status'],second['used']),('SUCCEEDED',2))
            self.assertEqual(first['approval_body_sha256'],second['approval_body_sha256'])
        def test_cycle_source_change_before_claim_holds(self):
            self.change=lambda request,result:result.update(status='CHANGED') if request['operation']=='verify_cycle_binding' else None
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('HOLD',0))
        def test_cycle_unapproved_configuration_holds(self):
            def change(request,result):
                if request['operation']=='authorize_first_admission':result['status']='DENIED'
                if request['operation']=='diagnose_attempt':result['configuration_actions']=['not-approved']
            self.change=change
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('HOLD',1))
        def test_cycle_fence_loss_never_claims(self):
            self.change=lambda request,result:result.update(status='LOST') if request['operation']=='verify_fence' else None
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('HOLD',0))
        def test_cycle_pending_native_effect_recovered_without_replay(self):
            seen=[0]
            def change(request,result):
                if request['operation']=='verify_phase_commit':
                    seen[0]+=1
                    if seen[0]==1:result['status']='UNKNOWN'
            self.change=change
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('SUCCEEDED',2))
            self.assertEqual(self.rig.events.count('phase:'+s.PHASES[0]),1)
        def test_cycle_existing_success_replay_consumes_nothing(self):
            self.cycle().run('d'*64)
            report=self.cycle().run('d'*64)
            self.assertEqual((report['status'],report['used']),('SUCCEEDED',1))
    return unittest.defaultTestLoader.loadTestsFromTestCase(NativeTests)

def run(candidate):
    spec=importlib.util.spec_from_file_location('original_transactions',str(candidate/'tests/test_successor_transactions.py'))
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    return original.run_isolated(extra_suite_factory=native_suite,include_existing=False)
if __name__=='__main__':sys.exit(run(Path(sys.argv[1])))
