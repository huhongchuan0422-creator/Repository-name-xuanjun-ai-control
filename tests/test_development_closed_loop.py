import copy
import hashlib
import hmac
import importlib.util
import os
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).parents[1]
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

    def test_no_model_or_process_dispatch_surface(self):
        raw=(ROOT/'scripts/development_closed_loop.py').read_text()
        for token in ('subprocess','Popen','openai','codex','runtime.subagent'):
            self.assertNotIn(token,raw.lower())

if __name__=='__main__':
    unittest.main(verbosity=2)
