import copy
import hashlib
import hmac
import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]/'scripts'))
from task_supervisor import Supervisor
from task_writer_fence import Fence

spec=importlib.util.spec_from_file_location('gate',pathlib.Path(__file__).parents[1]/'scripts/entry_review_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
KEYS={'qa-key':b'Q'*32,'security-key':b'S'*32,'ledger-key':b'L'*32}


def signed(payload,key_id):
    record=dict(schema=1,key_id=key_id,record_id=gate.digest(gate.canonical(payload)),payload=payload)
    record['signature']=hmac.new(KEYS[key_id],gate.canonical(record),hashlib.sha256).hexdigest()
    return record


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.contract=dict(task_id='original',spec_sha256='a'*64,checkpoint_sha256='b'*64,
            target_repository='owner/repo',target_base_sha='c'*40,code_commit='d'*40,entry='CHATGPT',
            developer={'issuer':'native','subject':'developer'},allowed_files=['src/f.py','src/data.json'],
            trusted_reviewers=[{'issuer':'native','subject':'qa','key_id':'qa-key','role':'QA'},
                               {'issuer':'native','subject':'security','key_id':'security-key','role':'SECURITY'}])
        self.files={'src/f.py':b'answer=42\n','src/data.json':b'{}\n'}
        self.binding=dict(task_id='same',attempt_id='attempt-1',run_id='run-1',session_id='session-1',fence=1,
                          checkpoint_sha256='a'*64,ledger_revision=2,receipt_sha256='b'*64,authority_key_id='ledger-key')

    def reviews(self):
        sha=gate.review_bundle(self.contract,self.files,[])['bundle_sha256']
        return [signed(dict(reviewer={k:p[k] for k in ('issuer','subject')},role=p['role'],bundle_sha256=sha,decision='PASS'),p['key_id']) for p in self.contract['trusted_reviewers']]

    def evidence(self,kind='CONTINUED',proof=None,at=1000):
        return signed(dict(binding=copy.deepcopy(self.binding),kind=kind,observed_at=at,
                           proof=proof or {'verified_execution':True}),'ledger-key')

    def test_three_entries_require_authenticated_independent_review(self):
        for entry in gate.ENTRIES:
            self.contract['entry']=entry
            self.assertEqual(gate.review_bundle(self.contract,self.files,[])['state'],'HOLD_INDEPENDENT_REVIEW_REQUIRED')
            result=gate.review_bundle(self.contract,self.files,self.reviews(),KEYS)
            self.assertEqual(result['state'],'ISOLATED_TEST_ELIGIBLE');self.assertFalse(result['release_approved'])

    def test_all_policy_fields_bound_to_digest(self):
        reviews=self.reviews()
        for field,value in [('developer',{'issuer':'native','subject':'other'}),('allowed_files',['src/f.py']),('trusted_reviewers',[dict(p,subject=p['subject']+'2') for p in self.contract['trusted_reviewers']])]:
            changed=copy.deepcopy(self.contract);changed[field]=value
            with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,reviews,KEYS)

    def test_string_policy_and_duplicate_identity_rejected(self):
        for change in ('qa_security',[self.contract['trusted_reviewers'][0]]*2):
            changed=dict(self.contract,trusted_reviewers=change)
            with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,[],KEYS)
        changed=dict(self.contract,developer='developer')
        with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,[],KEYS)

    def test_tampered_forged_or_duplicate_reviews(self):
        for mutate in ('signature','payload','record','duplicate','nokey'):
            reviews=self.reviews();keys=KEYS
            if mutate=='signature':reviews[0]['signature']='0'*64
            if mutate=='payload':reviews[0]['payload']['reviewer']['subject']='security'
            if mutate=='record':reviews[0]['record_id']='0'*64
            if mutate=='duplicate':reviews[1]=reviews[0]
            if mutate=='nokey':keys={}
            with self.assertRaises(ValueError):gate.review_bundle(self.contract,self.files,reviews,keys)

    def test_changed_code_invalidates_reviews(self):
        reviews=self.reviews();self.files['src/f.py']+=b'changed=1\n'
        with self.assertRaises(ValueError):gate.review_bundle(self.contract,self.files,reviews,KEYS)

    def test_paths_encoding_and_limits(self):
        for files in ({'../f.py':b'x=1'},{'src/f.py':b'\xff'},{'src/f.py':b'x=1\r\n'},{'src/f.py':b'x'*131073}):
            with self.assertRaises((ValueError,UnicodeError)):gate.review_bundle(self.contract,files,[])

    def test_read_heartbeat_and_missing_progress_do_not_close(self):
        for age,state in [(299,'AWAIT_EXECUTION_EVIDENCE'),(300,'RECOVER_INTAKE'),(600,'INSPECT_AND_RESUME_SAME_ATTEMPT'),(900,'HOLD_CONTINUATION_MISSING')]:
            for kind in ('READ','HEARTBEAT','CONTINUED'):
                record=self.evidence(kind,{'verified_execution':False},age)
                self.assertEqual(gate.continuation_due(self.binding,0,age,record,KEYS)['state'],state)

    def test_each_canonical_binding_field_rejects_unrelated_evidence(self):
        for field in self.binding:
            changed=copy.deepcopy(self.binding)
            changed[field]=changed[field]+1 if type(changed[field]) is int else 'x'*64 if field.endswith('sha256') else changed[field]+'-other'
            with self.assertRaises(ValueError):gate.continuation_due(changed,0,1000,self.evidence(),KEYS)

    def test_stale_future_unsigned_evidence_rejected(self):
        for at in (-1,1001,float('inf')):
            if at==float('inf'):
                with self.assertRaises(ValueError):self.evidence(at=at)
            else:
                with self.assertRaises(ValueError):gate.continuation_due(self.binding,0,1000,self.evidence(at=at),KEYS)
        with self.assertRaises(ValueError):gate.continuation_due(self.binding,0,1000,{'kind':'CONTINUED','verified_execution':True},KEYS)

    def test_handoff_requires_full_same_attempt_proof(self):
        proof=dict(receiver_accepted=True,old_writer_stopped=True,old_fence_invalidated=True,effects_reconciled=True)
        self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence('HANDOFF_ACKNOWLEDGED',proof),KEYS)['state'],'HANDOFF_ACKNOWLEDGED')
        for key in proof:
            changed=dict(proof);changed[key]=False
            self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence('HANDOFF_ACKNOWLEDGED',changed),KEYS)['state'],'HOLD_CONTINUATION_MISSING')

    def test_real_progress_and_bound_hold(self):
        self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence(),KEYS)['state'],'CONTINUED')
        proof=dict(blocker='api missing',checkpoint=self.binding['checkpoint_sha256'],next_action='bind api')
        self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence('HOLD',proof),KEYS)['state'],'HOLD')

    def test_clock_drift(self):
        for now in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):gate.continuation_due(self.binding,0,now)

    def test_exact_authorized_file_set_required(self):
        del self.files['src/data.json']
        with self.assertRaises(ValueError):
            gate.review_bundle(self.contract,self.files,[])
        self.files['src/data.json']=b'{}\n'
        self.assertEqual(gate.review_bundle(self.contract,self.files,[])['state'],'HOLD_INDEPENDENT_REVIEW_REQUIRED')

    def test_invalid_task_repository_and_policy_paths(self):
        for field,value in [('task_id',{}),('target_repository','owner/repo/../other'),('allowed_files',['../bad.py','src/f.py'])]:
            changed=dict(self.contract);changed[field]=value
            with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,[])

    def test_same_key_cannot_claim_two_independent_reviewers(self):
        records=self.reviews();keys=dict(KEYS);keys['security-key']=keys['qa-key']
        record=records[1]
        record['signature']=hmac.new(keys['security-key'],gate.canonical({k:v for k,v in record.items() if k!='signature'}),hashlib.sha256).hexdigest()
        with self.assertRaises(ValueError):gate.review_bundle(self.contract,self.files,records,keys)



class CanonicalCompletionTests(unittest.TestCase):
    def setUp(self):
        handle,self.path=tempfile.mkstemp();os.close(handle)
        self.lock_root=self.path+'.locks'
        self.now=1000.0
        self.s=Supervisor(self.path,lambda:self.now)
        self.fence=Fence(self.s,self.lock_root)
        self.task='original';self.child='child'
        self.s.register(dict(
            task_id=self.task,parent_task_id='parent',stage='dev',
            owner='developer',entry='CHATGPT',checkpoint_sha256='b'*64,
            spec_sha256='a'*64,next_action='implement',dependencies=[],
            completion_conditions=['reviewed-development'],
            progress_deadline=1900,receipt_deadline=1100,
            started_deadline=1200,terminal_deadline=3000,
            handoff_deadline=1800),now=self.now)
        self.s.register(dict(
            task_id=self.child,parent_task_id='parent',stage='dev-next',
            owner='developer',entry='CHATGPT',checkpoint_sha256='e'*64,
            spec_sha256='f'*64,next_action='next',dependencies=[self.task],
            completion_conditions=['next'],
            progress_deadline=1900,receipt_deadline=1100,
            started_deadline=1200,terminal_deadline=3000,
            handoff_deadline=1800),now=self.now)
        self.contract=dict(
            task_id=self.task,spec_sha256='a'*64,checkpoint_sha256='b'*64,
            target_repository='owner/repo',target_base_sha='c'*40,
            code_commit='d'*40,entry='CHATGPT',
            developer={'issuer':'native','subject':'developer'},
            allowed_files=['src/f.py','src/data.json'],
            trusted_reviewers=[
                {'issuer':'native','subject':'qa','key_id':'qa-key','role':'QA'},
                {'issuer':'native','subject':'security','key_id':'security-key',
                 'role':'SECURITY'}])
        base={k:v for k,v in self.contract.items() if k!='code_commit'}
        self.s.register_development_contract(self.task,base)
        self.caller={'caller_id':'writer','run_id':'run1',
                     'session_id':'session1','gateway_id':'gateway1'}
        ticket=self.fence.claim(
            self.task,'a1','developer','CHATGPT',self.caller,'lease1',
            ['fake:development/source'],1700)
        self.files={'src/f.py':b'answer=42\n','src/data.json':b'{}\n'}
        manifest={p:hashlib.sha256(raw).hexdigest()
                  for p,raw in self.files.items()}
        receipt=dict(
            schema=1,entry='CHATGPT',execution_path='CHATGPT_NATIVE',
            task_id=self.task,spec_sha256='a'*64,checkpoint_sha256='b'*64,
            target_repository='owner/repo',target_base_sha='c'*40,
            code_commit='d'*40,event='CODE_READY',attempt_id='a1',
            lease_id='lease1',fence=ticket['fence'],epoch=ticket['epoch'],
            caller_id=self.caller['caller_id'],run_id=self.caller['run_id'],
            session_id=self.caller['session_id'],
            gateway_id=self.caller['gateway_id'],
            lock_provider_id=self.fence.locks.provider_id,
            source_comment_id=123,status='RECEIPT_VALIDATED_NOT_ADMITTED',
            native_identity='CLAIMED_NOT_VERIFIED',quota_attribution='UNKNOWN',
            authority_effect='NONE',
            required_gate='CANONICAL_TASK_SPEC_CHECKPOINT_TARGET_LEASE_FENCE')
        self.candidate=self.s.bind_development_candidate(receipt,manifest)

    def tearDown(self):
        try:self.fence.close()
        except Exception:pass
        try:self.s.close()
        except Exception:pass
        if os.path.exists(self.path):os.unlink(self.path)
        if os.path.isdir(self.lock_root):
            for name in os.listdir(self.lock_root):
                os.unlink(os.path.join(self.lock_root,name))
            os.rmdir(self.lock_root)

    def reviews(self, contract=None, files=None):
        contract=contract or self.contract
        files=files or self.files
        sha=gate.review_bundle(contract,files,[])['bundle_sha256']
        result=[]
        for p in contract['trusted_reviewers']:
            payload=dict(
                reviewer={k:p[k] for k in ('issuer','subject')},
                role=p['role'],bundle_sha256=sha,decision='PASS')
            result.append(signed(payload,p['key_id']))
        return result

    def reviewed(self, event_id='dev-reviewed-1'):
        return gate.complete_reviewed_candidate(
            self.s,self.task,self.candidate['candidate_event_id'],
            self.files,self.reviews(),KEYS,event_id)

    def revoke_complete(self):
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'owner'}
        self.fence.begin_revocation(self.task,controller)
        self.fence.drain(self.task,controller,0.2)
        self.fence.invalidate_source_resources(self.task,'dev-invalidate')
        return self.s.complete_revocation(self.task)

    def test_review_pass_does_not_complete_or_unlock_before_revocation(self):
        result=self.reviewed()
        self.assertEqual(result['canonical_review']['reviewed']['code_commit'],
                         'd'*40)
        self.assertNotEqual(self.s._task(self.task)['state'],'SUCCESS')
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])
        with self.assertRaisesRegex(
                ValueError,'DEVELOPMENT_REVOCATION_PROOF_REQUIRED'):
            gate.finalize_reviewed_candidate(
                self.s,self.task,'dev-reviewed-1','dev-complete-1')
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])

    def test_exact_reviews_revoke_coverage_then_unlock_registered_child(self):
        reviewed=self.reviewed()
        revoke=self.revoke_complete()
        self.assertEqual(revoke['state'],'REVOKED')
        result=gate.finalize_reviewed_candidate(
            self.s,self.task,'dev-reviewed-1','dev-complete-1')
        self.assertEqual(result['state'],'SUCCESS')
        task=self.s._task(self.task)
        self.assertEqual(task['authority_state'],'REVOKED')
        self.assertEqual(task['state'],'SUCCESS')
        self.assertNotEqual(task['coverage_digest'],'UNKNOWN')
        self.assertNotEqual(task['resource_scope_digest'],'UNKNOWN')
        self.assertNotEqual(task['writer_stopped'],'TRUE')
        self.assertNotEqual(task['effects_reconciled'],'TRUE')
        self.assertIn(self.child,[x['task_id'] for x in self.s.ready()])
        event=self.s.db.execute(
            "SELECT payload_json FROM events WHERE task_id=? AND event_id=?",
            (self.task,'dev-complete-1')).fetchone()
        payload=__import__('json').loads(event[0])
        self.assertEqual(payload['authority_state'],'REVOKED')
        self.assertEqual(payload['coverage_digest'],task['coverage_digest'])
        self.assertEqual(payload['code_commit'],'d'*40)
        self.assertEqual(set(payload['review_record_ids']),{'QA','SECURITY'})

    def test_missing_reviewer_holds_and_does_not_unlock_child(self):
        result=gate.complete_reviewed_candidate(
            self.s,self.task,self.candidate['candidate_event_id'],
            self.files,self.reviews()[:1],KEYS,'dev-reviewed-1')
        self.assertEqual(
            result['canonical_review'],'HOLD_INDEPENDENT_REVIEW_REQUIRED')
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])
        self.assertIsNone(self.s.db.execute(
            "SELECT 1 FROM events WHERE kind='DEVELOPMENT_REVIEWED'"
        ).fetchone())

    def test_changed_bundle_and_canonical_event_id_mismatch_rejected(self):
        changed=dict(self.files);changed['src/f.py']=b'answer=99\n'
        with self.assertRaises(ValueError):
            gate.complete_reviewed_candidate(
                self.s,self.task,self.candidate['candidate_event_id'],
                changed,self.reviews(),KEYS,'dev-reviewed-change')
        with self.assertRaisesRegex(ValueError,'CURRENT_DEVELOPMENT_CANDIDATE_REQUIRED'):
            gate.complete_reviewed_candidate(
                self.s,self.task,'development-candidate:wrong',
                self.files,self.reviews(),KEYS,'dev-reviewed-wrong')
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])

    def test_review_policy_and_wrong_commit_cannot_replace_canonical_contract(self):
        drift=copy.deepcopy(self.contract)
        drift['developer']={'issuer':'native','subject':'other-developer'}
        drift_reviews=self.reviews(drift)
        with self.assertRaisesRegex(
                ValueError,'INDEPENDENT_EXACT_VERSION_REVIEW_REQUIRED'):
            gate.complete_reviewed_candidate(
                self.s,self.task,self.candidate['candidate_event_id'],
                self.files,drift_reviews,KEYS,'dev-reviewed-policy-drift')

        wrong=copy.deepcopy(self.contract)
        wrong['code_commit']='9'*40
        wrong_reviews=self.reviews(wrong)
        with self.assertRaises(ValueError):
            gate.complete_reviewed_candidate(
                self.s,self.task,self.candidate['candidate_event_id'],
                self.files,wrong_reviews,KEYS,'dev-reviewed-wrong-commit')
        candidate=self.s.development_candidate(
            self.task,self.candidate['candidate_event_id'])
        self.assertEqual(candidate['code_commit'],'d'*40)
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])

    def test_revoking_and_unresolved_operation_block_final_success(self):
        self.reviewed()
        operation={
            'operation_id':'op1','event_id':'op-event',
            'resource_key':'fake:development/source',
            'operation_kind':'FAKE_TXN',
            'expected_before':{'value':'old'},
            'requested_after':{'value':'new'},
            'request_sha256':'9'*64,
            'operation_marker':'xuanjun-op:op1'}
        ticket=self.s._authority_ticket(self.s._task(self.task))
        self.fence.prepare(ticket,self.caller,operation)
        self.s.begin_dispatch(
            ticket,self.caller,'op1',self.fence.locks.provider_id)
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'owner'}
        self.fence.begin_revocation(self.task,controller)
        self.fence.drain(self.task,controller,0.2)
        self.fence.invalidate_source_resources(self.task,'dev-invalidate')
        with self.assertRaisesRegex(ValueError,'REVOCATION_NOT_COMPLETED'):
            self.s.complete_revocation(self.task)
        with self.assertRaises(ValueError):
            gate.finalize_reviewed_candidate(
                self.s,self.task,'dev-reviewed-1','dev-complete-1')
        ctx={'role':'RECONCILER','evidence_id':'readback',
             'caller_id':'reader'}
        receipt={
            'schema':1,'outcome':'NOT_APPLIED','operation_id':'op1',
            'resource_key':'fake:development/source',
            'operation_marker':'xuanjun-op:op1',
            'attribution':{'kind':'READBACK',
                           'before':{'value':'old'},
                           'after':{'value':'old'}}}
        self.s.reconcile_operation(
            'op1',ctx,'NOT_APPLIED',{'readback':'old'},receipt)
        self.s.complete_revocation(self.task)
        result=gate.finalize_reviewed_candidate(
            self.s,self.task,'dev-reviewed-1','dev-complete-1')
        self.assertEqual(result['state'],'SUCCESS')

    def test_completion_restart_idempotent_and_conflict_stays_closed(self):
        self.reviewed()
        self.revoke_complete()
        first=gate.finalize_reviewed_candidate(
            self.s,self.task,'dev-reviewed-1','dev-complete-1')
        replay=gate.finalize_reviewed_candidate(
            self.s,self.task,'dev-reviewed-1','dev-complete-1')
        self.assertFalse(first['duplicate']);self.assertTrue(replay['duplicate'])
        self.fence.close();self.s.close()
        self.s=Supervisor(self.path,lambda:self.now)
        self.fence=Fence(self.s,self.lock_root)
        due=self.s.due_outbox(1000)
        self.assertEqual(len(due),1)
        self.assertEqual(self.s._task(self.task)['state'],'SUCCESS')
        self.assertIn(self.child,[x['task_id'] for x in self.s.ready()])
        with self.assertRaises(ValueError):
            gate.finalize_reviewed_candidate(
                self.s,self.task,'dev-reviewed-1','different-completion-id')



if __name__=='__main__':unittest.main()



class BatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ReviewTests()
        self.fixture.setUp()

    def record(self, age, evidence=None):
        return dict(binding=copy.deepcopy(self.fixture.binding),
                    receipt_read_at=1000-age, evidence=evidence)

    def test_all_tasks_are_assessed_without_first_task_shortcut(self):
        result=gate.continuation_batch([self.record(v) for v in (900,10,600,300)],1000,KEYS)
        self.assertEqual([v['state'] for v in result],['HOLD_CONTINUATION_MISSING',
                         'AWAIT_EXECUTION_EVIDENCE','INSPECT_AND_RESUME_SAME_ATTEMPT','RECOVER_INTAKE'])
        self.assertEqual([v['index'] for v in result],[0,1,2,3])
        self.assertTrue(all(v['authority_effect']=='NONE' for v in result))
        self.assertTrue(all(v['takeover_allowed'] is False for v in result))

    def test_one_forged_receipt_does_not_hide_other_overdue_tasks(self):
        forged=self.fixture.evidence()
        forged['signature']='0'*64
        result=gate.continuation_batch([self.record(900,forged),self.record(900)],1000,KEYS)
        self.assertEqual(result[0]['state'],'HOLD_INVALID_CONTINUATION_EVIDENCE')
        self.assertEqual(result[1]['state'],'HOLD_CONTINUATION_MISSING')

    def test_receiver_without_ack_never_closes_handoff(self):
        proof=dict(receiver_accepted=False,old_writer_stopped=True,
                   old_fence_invalidated=True,effects_reconciled=True)
        evidence=self.fixture.evidence('HANDOFF_ACKNOWLEDGED',proof)
        result=gate.continuation_batch([self.record(900,evidence)],1000,KEYS)
        self.assertEqual(result[0]['state'],'HOLD_CONTINUATION_MISSING')

    def test_bad_inventory_visible_and_no_unbounded_scan(self):
        result=gate.continuation_batch([{},self.record(900)],1000,KEYS)
        self.assertEqual(result[0]['state'],'HOLD_INVALID_INVENTORY_RECORD')
        self.assertEqual(result[1]['state'],'HOLD_CONTINUATION_MISSING')
        with self.assertRaises(ValueError):gate.continuation_batch([{}]*257,1000)
        with self.assertRaises(ValueError):gate.continuation_batch([],float('nan'))
