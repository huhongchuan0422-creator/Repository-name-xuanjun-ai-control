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
        self.now=1000.0
        self.s=Supervisor(self.path,lambda:self.now)
        self.task='original'
        self.child='child'
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
        self.s.register_development_contract(self.task,base,now=self.now)
        caller={'caller_id':'writer','run_id':'run1',
                'session_id':'session1','gateway_id':'gateway1'}
        self.s.claim_writer(self.task,'a1','developer','CHATGPT',caller,
                            'lease1','provider1',['fake:development/source'],
                            1700)
        self.files={'src/f.py':b'answer=42\n','src/data.json':b'{}\n'}
        manifest={p:hashlib.sha256(raw).hexdigest()
                  for p,raw in self.files.items()}
        receipt=dict(
            schema=1,entry='CHATGPT',execution_path='CHATGPT_NATIVE',
            task_id=self.task,spec_sha256='a'*64,checkpoint_sha256='b'*64,
            target_repository='owner/repo',target_base_sha='c'*40,
            code_commit='d'*40,event='CODE_READY',attempt_id='a1',
            lease_id='lease1',fence=1,epoch=1,source_comment_id=123,
            status='RECEIPT_VALIDATED_NOT_ADMITTED',
            native_identity='CLAIMED_NOT_VERIFIED',quota_attribution='UNKNOWN',
            authority_effect='NONE',
            required_gate='CANONICAL_TASK_SPEC_CHECKPOINT_TARGET_LEASE_FENCE')
        self.candidate=self.s.bind_development_candidate(receipt,manifest,now=1001)

    def tearDown(self):
        try:self.s.close()
        except Exception:pass
        if os.path.exists(self.path):os.unlink(self.path)

    def reviews(self):
        sha=gate.review_bundle(self.contract,self.files,[])['bundle_sha256']
        result=[]
        for p in self.contract['trusted_reviewers']:
            payload=dict(
                reviewer={k:p[k] for k in ('issuer','subject')},
                role=p['role'],bundle_sha256=sha,decision='PASS')
            result.append(signed(payload,p['key_id']))
        return result

    def test_exact_independent_reviews_complete_and_unlock_registered_child(self):
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])
        result=gate.complete_reviewed_candidate(
            self.s,self.contract,self.files,self.reviews(),KEYS,
            self.candidate,'dev-complete-1')
        self.assertEqual(result['canonical_completion']['state'],'SUCCESS')
        self.assertEqual(self.s._task(self.task)['state'],'SUCCESS')
        self.assertIn(self.child,[x['task_id'] for x in self.s.ready()])
        event=self.s.db.execute(
            "SELECT payload_json FROM events WHERE task_id=? AND event_id=?",
            (self.task,'dev-complete-1')).fetchone()
        payload=__import__('json').loads(event[0])
        self.assertEqual(payload['bundle_sha256'],result['bundle_sha256'])
        self.assertEqual(payload['code_commit'],'d'*40)
        self.assertEqual(set(payload['review_record_ids']),{'QA','SECURITY'})

    def test_missing_reviewer_holds_and_does_not_unlock_child(self):
        result=gate.complete_reviewed_candidate(
            self.s,self.contract,self.files,self.reviews()[:1],KEYS,
            self.candidate,'dev-complete-1')
        self.assertEqual(
            result['canonical_completion'],'HOLD_INDEPENDENT_REVIEW_REQUIRED')
        self.assertNotEqual(self.s._task(self.task)['state'],'SUCCESS')
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])

    def test_changed_bundle_or_wrong_commit_does_not_complete(self):
        reviews=self.reviews()
        changed=dict(self.files);changed['src/f.py']=b'answer=99\n'
        with self.assertRaises(ValueError):
            gate.complete_reviewed_candidate(
                self.s,self.contract,changed,reviews,KEYS,
                self.candidate,'dev-complete-1')
        wrong=dict(self.contract);wrong['code_commit']='9'*40
        wrong_sha=gate.review_bundle(wrong,self.files,[])['bundle_sha256']
        wrong_reviews=[]
        for p in wrong['trusted_reviewers']:
            payload=dict(
                reviewer={k:p[k] for k in ('issuer','subject')},
                role=p['role'],bundle_sha256=wrong_sha,decision='PASS')
            wrong_reviews.append(signed(payload,p['key_id']))
        with self.assertRaisesRegex(
                ValueError,'REVIEW_CANDIDATE_BINDING_MISMATCH'):
            gate.complete_reviewed_candidate(
                self.s,wrong,self.files,wrong_reviews,KEYS,
                self.candidate,'dev-complete-2')
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])

    def test_review_policy_drift_from_canonical_contract_is_rejected(self):
        drift=copy.deepcopy(self.contract)
        drift['developer']={'issuer':'native','subject':'other-developer'}
        drift_sha=gate.review_bundle(drift,self.files,[])['bundle_sha256']
        drift_reviews=[]
        for p in drift['trusted_reviewers']:
            payload=dict(
                reviewer={k:p[k] for k in ('issuer','subject')},
                role=p['role'],bundle_sha256=drift_sha,decision='PASS')
            drift_reviews.append(signed(payload,p['key_id']))
        with self.assertRaisesRegex(
                ValueError,'REVIEW_CANDIDATE_BINDING_MISMATCH'):
            gate.complete_reviewed_candidate(
                self.s,drift,self.files,drift_reviews,KEYS,
                self.candidate,'dev-complete-policy-drift')
        self.assertNotIn(self.child,[x['task_id'] for x in self.s.ready()])

    def test_completion_replay_restart_outbox_and_conflict(self):
        reviews=self.reviews()
        first=gate.complete_reviewed_candidate(
            self.s,self.contract,self.files,reviews,KEYS,
            self.candidate,'dev-complete-1')
        replay=gate.complete_reviewed_candidate(
            self.s,self.contract,self.files,reviews,KEYS,
            self.candidate,'dev-complete-1')
        self.assertFalse(first['canonical_completion']['duplicate'])
        self.assertTrue(replay['canonical_completion']['duplicate'])
        self.s.close();self.s=Supervisor(self.path,lambda:self.now)
        due=self.s.due_outbox(1000)
        self.assertEqual(len(due),1)
        self.assertEqual(self.s._task(self.task)['state'],'SUCCESS')
        self.assertIn(self.child,[x['task_id'] for x in self.s.ready()])
        with self.assertRaisesRegex(
                ValueError,'DEVELOPMENT_COMPLETION_EVENT_CONFLICT'):
            self.s.complete_development_candidate(
                self.task,self.candidate['candidate_event_id'],
                first['bundle_sha256'],
                {'QA':'1'*64,'SECURITY':'2'*64},
                'dev-complete-1',now=1002)



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
