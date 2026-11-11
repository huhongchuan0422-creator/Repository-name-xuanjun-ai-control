import copy
import unittest
from scripts.run_usage_projection import COUNTERS, usage_projection


def sample(run='R1'):
    return dict(run_id=run, provider='INTERNAL', counters=dict.fromkeys(COUNTERS, 10),
                evidence_sha256='a' * 64)


class UsageTests(unittest.TestCase):
    def test_totals_not_quota(self):
        r = usage_projection([sample(), sample('R2')])
        self.assertEqual(r['totals']['model_calls'], 20)
        self.assertIsNone(r['quota_remaining']); self.assertIsNone(r['amount'])
        self.assertFalse(r['execution_granted'])

    def test_duplicates_not_double_counted(self):
        self.assertEqual(usage_projection([sample(), sample()])['run_count'], 1)

    def test_conflicting_cumulative_sample(self):
        s = sample(); s['counters']['model_calls'] = 11
        with self.assertRaises(ValueError): usage_projection([sample(), s])

    def test_unknown_poison_each_counter(self):
        for counter in COUNTERS:
            s = sample(); s['counters'][counter] = None
            r = usage_projection([sample('R2'), s])
            self.assertIsNone(r['totals'][counter]); self.assertEqual(r['status'], 'HOLD')

    def test_missing_evidence_poison_all(self):
        s = sample(); s['evidence_sha256'] = None
        self.assertTrue(all(v is None for v in usage_projection([s])['totals'].values()))

    def test_missing_counter(self):
        s = sample(); del s['counters']['cpu_seconds']
        with self.assertRaises(ValueError): usage_projection([s])

    def test_bool_fraction_overflow(self):
        for value in (True, -1, 1.5, 2 ** 63):
            s = sample(); s['counters']['model_calls'] = value
            with self.assertRaises(ValueError): usage_projection([s])
        s = sample(); s['counters']['model_calls'] = 2 ** 63 - 1
        with self.assertRaises(ValueError): usage_projection([s, sample('R2')])

    def test_unknown_provider(self):
        s = sample(); s['provider'] = 'UNKNOWN'
        self.assertEqual(usage_projection([s])['status'], 'HOLD')

    def test_empty_is_unknown(self):
        self.assertTrue(all(v is None for v in usage_projection([])['totals'].values()))

    def test_no_mutation(self):
        s = [sample()]; before = copy.deepcopy(s); usage_projection(s)
        self.assertEqual(s, before)
