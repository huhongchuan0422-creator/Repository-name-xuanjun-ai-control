import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('gate', pathlib.Path(__file__).parents[1] / 'scripts/entry_review_gate.py')
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.contract = dict(task_id='original', spec_sha256='a'*64,
            checkpoint_sha256='b'*64, target_repository='owner/repo',
            target_base_sha='c'*40, code_commit='d'*40, entry='CHATGPT',
            developer='developer', allowed_files=['src/f.py', 'src/data.json'],
            trusted_reviewers=['qa', 'security'])
        self.files = {'src/f.py': b'answer = 42\n', 'src/data.json': b'{"ok":true}\n'}
        self.identity = dict(task_id='original', attempt='attempt-1', run_id='run-1',
            session_id='session-1', fence='fence-1', checkpoint_sha256='b'*64,
            ledger_revision=7)

    def reviews(self):
        sha = gate.review_bundle(self.contract, self.files, [])['bundle_sha256']
        return [dict(reviewer=who, role=role, bundle_sha256=sha,
                     decision='PASS', evidence_id='github-review:'+number)
                for who, role, number in [('qa','QA','101'), ('security','SECURITY','102')]]

    def evidence(self, kind, **values):
        result = dict(self.identity, kind=kind, observed_at=900)
        result.update(values)
        return result

    def test_three_entries_need_independent_review(self):
        for entry in gate.ENTRIES:
            self.contract['entry'] = entry
            self.assertEqual(gate.review_bundle(self.contract, self.files, [])['state'], 'HOLD_INDEPENDENT_REVIEW_REQUIRED')
            self.assertEqual(gate.review_bundle(self.contract, self.files, self.reviews())['state'], 'ISOLATED_TEST_ELIGIBLE')

    def test_policy_fields_and_exact_file_set_are_bound(self):
        first = gate.review_bundle(self.contract, self.files, [])['bundle_sha256']
        for field, value in [('developer','developer-2'),
                             ('allowed_files',['src/f.py']),
                             ('trusted_reviewers',['qa-2','security'])]:
            altered = dict(self.contract); altered[field] = value
            if field == 'allowed_files':
                with self.assertRaises(ValueError): gate.review_bundle(altered, self.files, [])
            else:
                self.assertNotEqual(first, gate.review_bundle(altered, self.files, [])['bundle_sha256'])

    def test_reviewer_list_is_strict_and_evidence_authenticated(self):
        altered = dict(self.contract); altered['trusted_reviewers'] = 'qa_security'
        with self.assertRaises(ValueError): gate.review_bundle(altered, self.files, [])
        reviews = self.reviews(); reviews[0]['evidence_id'] = 'authenticated:qa'
        with self.assertRaises(ValueError): gate.review_bundle(self.contract, self.files, reviews)

    def test_reviewed_bytes_changed_or_self_review(self):
        reviews = self.reviews(); self.files['src/f.py'] += b'changed=1\n'
        with self.assertRaises(ValueError): gate.review_bundle(self.contract, self.files, reviews)
        self.files['src/f.py'] = b'answer = 42\n'
        altered = dict(self.contract); altered['developer'] = 'qa'
        with self.assertRaises(ValueError): gate.review_bundle(altered, self.files, [])

    def test_corrupt_bytes_and_paths(self):
        for raw in (b'x="broken\n', b'\xff', b'x=1\r\n', b'x=\x00'):
            files = dict(self.files); files['src/f.py'] = raw
            with self.assertRaises((ValueError, SyntaxError, UnicodeError)): gate.review_bundle(self.contract, files, [])

    def test_receipt_reads_do_not_close_obligation(self):
        for age, expected in [(299,'AWAIT_EXECUTION_EVIDENCE'), (300,'RECOVER_INTAKE'), (600,'INSPECT_AND_RESUME_SAME_ATTEMPT'), (900,'HOLD_CONTINUATION_MISSING')]:
            for evidence in (None, dict(self.identity,kind='READ',observed_at=age),
                             dict(self.identity,kind='HEARTBEAT',observed_at=age)):
                self.assertEqual(gate.continuation_due(0,age,evidence,self.identity)['state'], expected)

    def test_attempt_replay_and_extra_fields_rejected(self):
        valid = self.evidence('CONTINUED', verified_execution=True,
                              execution_receipt_sha256='e'*64)
        self.assertEqual(gate.continuation_due(0,900,valid,self.identity)['state'], 'CONTINUED')
        replay = dict(valid); replay['attempt'] = 'attempt-2'
        with self.assertRaises(ValueError): gate.continuation_due(0,900,replay,self.identity)
        extra = dict(valid); extra['unbound'] = True
        self.assertEqual(gate.continuation_due(0,900,extra,self.identity)['state'], 'HOLD_CONTINUATION_MISSING')

    def test_handoff_and_hold_require_full_bound_proof(self):
        handoff = self.evidence('HANDOFF_ACKNOWLEDGED', receiver_accepted=True,
            old_writer_stopped=True, old_fence_invalidated=True, effects_reconciled=True,
            handoff_receipt_sha256='f'*64)
        self.assertEqual(gate.continuation_due(0,900,handoff,self.identity)['state'], 'HANDOFF_ACKNOWLEDGED')
        altered = dict(handoff); altered['old_writer_stopped'] = False
        self.assertEqual(gate.continuation_due(0,900,altered,self.identity)['state'], 'HOLD_CONTINUATION_MISSING')
        hold = self.evidence('HOLD', blocker='api missing', checkpoint='b'*64,
            next_action='bind api', hold_receipt_sha256='1'*64)
        self.assertEqual(gate.continuation_due(0,900,hold,self.identity)['state'], 'HOLD')

    def test_clock_drift(self):
        for now in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): gate.continuation_due(0,now,None,self.identity)


if __name__ == '__main__': unittest.main()
