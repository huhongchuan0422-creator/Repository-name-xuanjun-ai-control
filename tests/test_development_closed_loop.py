import copy
import sys
import hashlib
import hmac
import importlib.util
import os
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
for name,path in (
    ('entry_review_gate',ROOT/'scripts/entry_review_gate.py'),
    ('task_supervisor',ROOT/'scripts/task_supervisor.py'),
    ('development_closed_loop',ROOT/'scripts/development_closed_loop.py')):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    globals()[name]=module

KEYS={'qa-key':b'Q'*32,'security-key':b'S'*32}


def signed(payload,key_id):
    record=dict(schema=1,key_id=key_id,
                record_id=entry_review_gate.digest(
                    entry_review_gate.canonical(payload)),payload=payload)
    record['signature']=hmac.new(
        KEYS[key_id],entry_review_gate.canonical(record),
        hashlib.sha256).hexdigest()
    return record


class ClosedLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=os.path.join(self.tmp.name,'supervisor.sqlite')
        self.sup=task_supervisor.Supervisor(self.db,clock=lambda:100)
        self.contract=dict(task_id='task4',spec_sha256='a'*64,
            checkpoint_sha256='b'*64,target_repository='owner/repo',
            target_base_sha='c'*40,code_commit='d'*40,entry='CHATGPT',
            developer={'issuer':'native','subject':'developer'},
            allowed_files=['src/f.py'],
            trusted_reviewers=[
              {'issuer':'native','subject':'qa','key_id':'qa-key','role':'QA'},
              {'issuer':'native','subject':'security','key_id':'security-key','role':'SECURITY'}])
        self.files={'src/f.py':b'answer=42\n'}
        self.sup.register(dict(task_id='task4',parent_task_id='parent',
            stage='CODE_REVIEW',owner='reviewer',entry='CHATGPT',
            checkpoint_sha256='b'*64,spec_sha256='a'*64,
            next_action='REVIEW',dependencies=[],
            completion_conditions=['reviewed','delivered'],
            progress_deadline=500,receipt_deadline=500,
            started_deadline=500,terminal_deadline=1000,
            handoff_deadline=500),now=100)
        self.sup.claim('task4','attempt-1','reviewer','CHATGPT',
            'run-1','session-1','lease-1',1,1,now=101)
        self.sup.record('task4','attempt-1','start','STARTED',102,
            evidence_kind='PHASE_EXECUTION',evidence_ref='start-proof')

    def tearDown(self):
        self.sup.close();self.tmp.cleanup()

    def reviews(self,qa='PASS',security='PASS'):
        sha=entry_review_gate.review_bundle(
            self.contract,self.files,[])['bundle_sha256']
        values=[]
        for role,decision,key,subject in (
            ('QA',qa,'qa-key','qa'),
            ('SECURITY',security,'security-key','security')):
            payload=dict(reviewer={'issuer':'native','subject':subject},
                         role=role,bundle_sha256=sha,decision=decision)
            values.append(signed(payload,key))
        return values

    def test_fail_review_requests_repair_and_requires_exact_ack(self):
        result=development_closed_loop.apply_code_review(
            self.sup,'task4','attempt-1','review1',
            self.contract,self.files,self.reviews(qa='FAIL'),KEYS,103,
            'review-proof','developer','CHATGPT','tester','WORK')
        self.assertEqual(result['state'],'REPAIR_REQUIRED')
        self.assertEqual(development_closed_loop.closed_loop_status(
            self.sup,'task4')['state'],'WAITING_HANDOFF_ACK')
        with self.assertRaises(ValueError):
            development_closed_loop.acknowledge_handoff(
                self.sup,'task4','attempt-1','ack-bad',104,'handoff-proof',
                'developer','CHATGPT',dict(
                    development_closed_loop.TRUE_PROOF,
                    effects_reconciled=False))
        development_closed_loop.acknowledge_handoff(
            self.sup,'task4','attempt-1','ack-ok',104,'handoff-proof',
            'developer','CHATGPT',
            dict(development_closed_loop.TRUE_PROOF))
        row=self.sup.db.execute(
            "SELECT state,owner,entry FROM tasks WHERE task_id='task4'").fetchone()
        self.assertEqual(tuple(row),('READY','developer','CHATGPT'))

    def test_pass_review_handoffs_to_isolated_test(self):
        result=development_closed_loop.apply_code_review(
            self.sup,'task4','attempt-1','review2',
            self.contract,self.files,self.reviews(),KEYS,103,
            'review-proof','developer','CHATGPT','tester','WORK')
        self.assertEqual(result['state'],'ISOLATED_TEST_ELIGIBLE')
        self.assertEqual(result['next_owner'],'tester')
        self.assertEqual(result['next_entry'],'WORK')
        self.assertFalse(result['dispatch_performed'])

    def test_success_not_done_until_terminal_outbox_ack(self):
        completion=['reviewed','delivered']
        result=development_closed_loop.record_terminal(
            self.sup,'task4','attempt-1','terminal',103,'terminal-proof',
            'SUCCESS','e'*64,'NONE',completion)
        self.assertEqual(result['closed_loop_state'],'WAITING_OUTBOX_ACK')
        due=self.sup.due_outbox(now=103)
        self.assertEqual(len(due),1)
        ack=development_closed_loop.acknowledge_outbox(
            self.sup,due[0]['outbox_id'],104)
        self.assertEqual(ack['closed_loop_state'],'DONE')

    def test_delivery_exhaustion_is_visible_hold(self):
        development_closed_loop.record_terminal(
            self.sup,'task4','attempt-1','terminal',103,'terminal-proof',
            'SUCCESS','e'*64,'NONE',['reviewed','delivered'])
        row=self.sup.due_outbox(now=103)[0]
        now=103
        for index in range(5):
            result=self.sup.outbox_result(
                row['outbox_id'],False,now=now,error='transport')
            now=result.get('next_attempt_at',now+1)
        self.assertTrue(result['dead_lettered'])
        self.assertEqual(development_closed_loop.closed_loop_status(
            self.sup,'task4')['state'],'HOLD_OUTBOX_DEAD_LETTER')

    def test_changed_bytes_invalidate_review(self):
        reviews=self.reviews()
        self.files['src/f.py']=b'changed=1\n'
        with self.assertRaises(ValueError):
            development_closed_loop.apply_code_review(
                self.sup,'task4','attempt-1','review3',
                self.contract,self.files,reviews,KEYS,103,'review-proof',
                'developer','CHATGPT','tester','WORK')

    def test_review_contract_task_spec_checkpoint_and_attempt_fail_closed(self):
        for field, wrong in (('task_id','another-task'),
                             ('spec_sha256','f'*64),
                             ('checkpoint_sha256','e'*64)):
            contract=dict(self.contract)
            contract[field]=wrong
            sha=entry_review_gate.review_bundle(contract,self.files,[])['bundle_sha256']
            reviews=[]
            for role,key,subject in (('QA','qa-key','qa'),('SECURITY','security-key','security')):
                reviews.append(signed(dict(reviewer={'issuer':'native','subject':subject},
                                           role=role,bundle_sha256=sha,decision='PASS'),key))
            with self.assertRaises(ValueError):
                development_closed_loop.apply_code_review(
                    self.sup,'task4','attempt-1','bad-'+field,contract,
                    self.files,reviews,KEYS,103,'review-proof',
                    'developer','CHATGPT','tester','WORK')
        with self.assertRaises(ValueError):
            development_closed_loop.apply_code_review(
                self.sup,'task4','stale-attempt','bad-attempt',self.contract,
                self.files,self.reviews(),KEYS,103,'review-proof',
                'developer','CHATGPT','tester','WORK')
        count=self.sup.db.execute("SELECT count(*) FROM events WHERE kind IN ('PROGRESS','HANDOFF_REQUESTED')").fetchone()[0]
        self.assertEqual(count,0)

    def test_handoff_ack_wrong_receiver_and_stale_attempt_fail_closed(self):
        development_closed_loop.apply_code_review(
            self.sup,'task4','attempt-1','review-test',self.contract,
            self.files,self.reviews(),KEYS,103,'review-proof',
            'developer','CHATGPT','tester','WORK')
        for owner,entry,attempt in (('unrequested-owner','DOTS','attempt-1'),
                                    ('tester','DOTS','attempt-1'),
                                    ('tester','WORK','stale-attempt')):
            with self.assertRaises(ValueError):
                development_closed_loop.acknowledge_handoff(
                    self.sup,'task4',attempt,'wrong-ack',104,
                    'handoff-proof',owner,entry,
                    dict(development_closed_loop.TRUE_PROOF))
        state=self.sup.db.execute("SELECT state,owner,entry FROM tasks WHERE task_id='task4'").fetchone()
        self.assertEqual(tuple(state),('HANDOFF_PENDING','reviewer','CHATGPT'))
        self.assertEqual(self.sup.db.execute("SELECT count(*) FROM events WHERE kind='HANDOFF_ACKNOWLEDGED'").fetchone()[0],0)
        development_closed_loop.acknowledge_handoff(
            self.sup,'task4','attempt-1','ack-valid',104,
            'handoff-proof','tester','WORK',
            dict(development_closed_loop.TRUE_PROOF))
        with self.assertRaises(ValueError):
            development_closed_loop.acknowledge_handoff(
                self.sup,'task4','attempt-1','replay-new',105,
                'handoff-proof','tester','WORK',
                dict(development_closed_loop.TRUE_PROOF))


    def test_admission_ack_matches_claim_and_never_grants_authority(self):
        row=development_closed_loop._task(self.sup,'task4')
        binding={key:row[key] for key in (
            'lease_id','fence','epoch','checkpoint_sha256',
            'spec_sha256','run_id','session_id')}
        with self.assertRaises(ValueError):
            development_closed_loop.admitted_receipt_ack(
                self.sup,'task4','attempt-1','wrong',103,'real-receipt',
                dict(binding, fence=99))
        self.assertEqual(self.sup.db.execute(
            "SELECT count(*) FROM events WHERE event_id='wrong'").fetchone()[0],0)
        # A STARTED attempt cannot be relabeled as a new RECEIVED event.
        with self.assertRaises(ValueError):
            development_closed_loop.admitted_receipt_ack(
                self.sup,'task4','attempt-1','late',103,'real-receipt',binding)

    def test_owner_notice_durable_dedupe_and_no_false_acceptance(self):
        url=('https://github.com/huhongchuan0422-creator/'
             'Repository-name-xuanjun-ai-control/pull/58')
        # Existing STARTED task cannot be labeled unreceived.
        with self.assertRaises(ValueError):
            development_closed_loop.enqueue_owner_notice(
                self.sup,'task4','bad',105,'RECEIPT_TIMEOUT','d'*40,url)
        # Terminal failure notice uses the existing durable outbox.
        self.sup.record('task4','attempt-1','failure','TERMINAL',103,
            evidence_kind='PHASE_EXECUTION', evidence_ref='fail-proof',
            payload={'state':'FAILURE','artifact_sha256':'UNKNOWN',
                     'writer_stopped':False,'effects_reconciled':False,
                     'next_action':'REPAIR',
                     'completion_evidence':[]})
        notice=development_closed_loop.enqueue_owner_notice(
            self.sup,'task4','notice-failure',104,'FAILURE','d'*40,url)
        self.assertEqual(notice['state'],'PERSISTED_NOT_DELIVERED')
        replay=development_closed_loop.enqueue_owner_notice(
            self.sup,'task4','notice-failure',104,'FAILURE','d'*40,url)
        self.assertTrue(replay['duplicate'])
        self.assertEqual(self.sup.db.execute(
            "SELECT count(*) FROM outbox WHERE event_id='notice-failure'").fetchone()[0],1)
        with self.assertRaises(ValueError):
            development_closed_loop.enqueue_owner_notice(
                self.sup,'task4','notice-failure',104,'FAILURE','e'*40,url)

    def test_missing_ack_timeout_uses_ready_without_receiving(self):
        sup=task_supervisor.Supervisor(
            os.path.join(self.tmp.name,'second.sqlite'),clock=lambda:100)
        try:
            sup.register(dict(task_id='unreceived',parent_task_id='parent',
                stage='DELIVERY',owner='owner',entry='CHATGPT',
                checkpoint_sha256='a'*64,spec_sha256='b'*64,
                next_action='AWAIT',dependencies=[],
                completion_conditions=['done'],
                progress_deadline=105,receipt_deadline=105,
                started_deadline=105,terminal_deadline=105,
                handoff_deadline=105),now=100)
            url=('https://github.com/huhongchuan0422-creator/'
                 'Repository-name-xuanjun-ai-control/issues/19')
            result=development_closed_loop.enqueue_owner_notice(
                sup,'unreceived','receipt-timeout',106,
                'RECEIPT_TIMEOUT','c'*40,url)
            self.assertEqual(result['state'],'PERSISTED_NOT_DELIVERED')
            row=sup._task('unreceived')
            self.assertEqual(row['state'],'READY')
            self.assertEqual(row['attempt_id'],'UNKNOWN')
        finally:
            sup.close()

    def test_no_model_or_process_dispatch_surface(self):
        raw=(ROOT/'scripts/development_closed_loop.py').read_text()
        for token in ('subprocess','Popen','openai','codex','runtime.subagent'):
            self.assertNotIn(token,raw.lower())

if __name__=='__main__':
    unittest.main(verbosity=2)
