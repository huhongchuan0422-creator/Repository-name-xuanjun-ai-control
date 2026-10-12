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
        self.files = {'src/f.py': b'answer = 42\n'}

    def reviews(self):
        sha = gate.review_bundle(self.contract, self.files, [])['bundle_sha256']
        return [dict(reviewer=who, role=role, bundle_sha256=sha,
                     decision='PASS', evidence_id='authenticated:'+who)
                for who, role in [('qa','QA'), ('security','SECURITY')]]

    def test_three_entries_need_independent_review(self):
        for entry in gate.ENTRIES:
            self.contract['entry'] = entry
            self.assertEqual(gate.review_bundle(self.contract, self.files, [])['state'], 'HOLD_INDEPENDENT_REVIEW_REQUIRED')
            result = gate.review_bundle(self.contract, self.files, self.reviews())
            self.assertEqual(result['state'], 'ISOLATED_TEST_ELIGIBLE')
            self.assertFalse(result['release_approved'])

    def test_reviewed_bytes_changed(self):
        reviews = self.reviews(); self.files['src/f.py'] += b'changed=1\n'
        with self.assertRaises(ValueError): gate.review_bundle(self.contract, self.files, reviews)

    def test_self_review_or_same_reviewer(self):
        for mode in ('self', 'duplicate'):
            reviews = self.reviews()
            if mode == 'self': reviews[0]['reviewer'] = 'developer'
            else: reviews[1]['reviewer'] = 'qa'
            with self.assertRaises(ValueError): gate.review_bundle(self.contract, self.files, reviews)

    def test_corrupt_quotes_and_encoding(self):
        for raw in (b'x="broken\n', b'\xff', b'x=1\r\n', b'x=\x00'):
            with self.assertRaises((ValueError, SyntaxError, UnicodeError)):
                gate.review_bundle(self.contract, {'src/f.py': raw}, [])

    def test_paths_and_nonbytes(self):
        for files in ({'../src/f.py': b'x=1'}, {'src//f.py': b'x=1'}, {'src/f.py': 'x=1'}, {'src/f.py': b'x'*131073}):
            with self.assertRaises(ValueError): gate.review_bundle(self.contract, files, [])

    def test_duplicate_json_and_nonfinite(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(ValueError): gate.review_bundle(self.contract, {'src/data.json': raw}, [])

    def test_receipt_reads_do_not_close_obligation(self):
        for age, expected in [(299,'AWAIT_EXECUTION_EVIDENCE'), (300,'RECOVER_INTAKE'), (600,'INSPECT_AND_RESUME_SAME_ATTEMPT'), (900,'HOLD_CONTINUATION_MISSING')]:
            for evidence in (None, {'kind':'READ'}, {'kind':'HEARTBEAT'}, {'kind':'CONTINUED','verified_execution':False}):
                self.assertEqual(gate.continuation_due(0,age,evidence)['state'], expected)

    def test_handoff_requires_full_proof(self):
        e = dict(kind='HANDOFF_ACKNOWLEDGED', receiver_accepted=True,
                 old_writer_stopped=True, old_fence_invalidated=True, effects_reconciled=True)
        self.assertEqual(gate.continuation_due(0,900,e)['state'], e['kind'])
        for k in list(e):
            if k == 'kind': continue
            altered = dict(e); altered[k] = False
            self.assertEqual(gate.continuation_due(0,900,altered)['state'], 'HOLD_CONTINUATION_MISSING')

    def test_real_progress_and_explicit_hold(self):
        self.assertEqual(gate.continuation_due(0,900,dict(kind='CONTINUED',verified_execution=True))['state'], 'CONTINUED')
        self.assertEqual(gate.continuation_due(0,900,dict(kind='HOLD',blocker='api missing',checkpoint='hash',next_action='bind api'))['state'], 'HOLD')

    def test_clock_drift(self):
        for now in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): gate.continuation_due(0,now,None)


if __name__ == '__main__': unittest.main()
