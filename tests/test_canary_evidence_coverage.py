import copy
import unittest
from scripts.canary_evidence_coverage import CASES, evaluate_coverage

C = 'a' * 40
A = 'b' * 64


def receipts():
    return [dict(case=case, commit=C, artifact_sha256=A,
                 evidence_sha256='c' * 64, environment='UK_RUNTIME',
                 status='PASS', run_id='run-' + str(i)) for i, case in enumerate(CASES)]


class CanaryTests(unittest.TestCase):
    def test_complete_never_grants(self):
        r = evaluate_coverage(C, A, receipts())
        self.assertEqual(r['status'], 'COVERAGE_COMPLETE')
        for key in ('release_granted', 'install_granted', 'dispatch_performed'):
            self.assertFalse(r[key])

    def test_every_case_required(self):
        for i, case in enumerate(CASES):
            rows = receipts(); del rows[i]
            self.assertIn(case, evaluate_coverage(C, A, rows)['missing'])

    def test_fixture_not_runtime(self):
        for environment in ('FIXTURE', 'HOSTED_CI', 'UNKNOWN', None):
            rows = receipts(); rows[0]['environment'] = environment
            self.assertEqual(evaluate_coverage(C, A, rows)['status'], 'HOLD')

    def test_exact_versions(self):
        for key, value in (('commit', 'd' * 40), ('artifact_sha256', 'e' * 64)):
            rows = receipts(); rows[0][key] = value
            self.assertEqual(evaluate_coverage(C, A, rows)['status'], 'HOLD')

    def test_failure_not_hidden_by_pass(self):
        rows = receipts(); item = copy.deepcopy(rows[0]); item['status'] = 'FAIL'
        rows.append(item)
        r = evaluate_coverage(C, A, rows)
        self.assertEqual(r['status'], 'HOLD')
        self.assertIn('DUPLICATE_CASE_TASK_ONE_E2E', r['reasons'])

    def test_identical_duplicate_hold(self):
        rows = receipts(); rows.append(copy.deepcopy(rows[0]))
        self.assertEqual(evaluate_coverage(C, A, rows)['status'], 'HOLD')

    def test_missing_evidence(self):
        for key in ('run_id', 'evidence_sha256'):
            rows = receipts(); rows[0][key] = None
            self.assertEqual(evaluate_coverage(C, A, rows)['status'], 'HOLD')

    def test_unknown_case_and_bad_schema(self):
        for item in (None, {}, dict(receipts()[0], secret='hidden'),
                     dict(receipts()[0], case=['bad'])):
            self.assertEqual(evaluate_coverage(C, A, receipts() + [item])['status'], 'HOLD')

    def test_no_mutation(self):
        rows = receipts(); before = copy.deepcopy(rows)
        evaluate_coverage(C, A, rows)
        self.assertEqual(rows, before)

    def test_bound_and_invalid_version(self):
        with self.assertRaises(ValueError): evaluate_coverage(C, A, receipts() * 11)
        with self.assertRaises(ValueError): evaluate_coverage('bad', A, [])

    def test_empty_is_hold(self):
        self.assertEqual(len(evaluate_coverage(C, A, [])['missing']), len(CASES))
