import copy
import unittest
from scripts.task_cost_projection import project_costs, MAX_AMOUNT


def record(component='compute', kind='ACTUAL', amount=100, evidence='a' * 64,
           currency='USD'):
    return dict(task_id='T1', component_id=component, currency=currency,
                kind=kind, amount_micros=amount, evidence_sha256=evidence)


class CostTests(unittest.TestCase):
    def test_actual_estimate_separate(self):
        r = project_costs('T1', [record(), record(kind='ESTIMATE', amount=250)])
        self.assertEqual(r['currencies']['USD']['actual_micros'], 100)
        self.assertEqual(r['currencies']['USD']['estimate_micros'], 250)
        self.assertFalse(r['payment_granted'])

    def test_missing_actual_not_estimate(self):
        r = project_costs('T1', [record(kind='ESTIMATE')])
        self.assertIsNone(r['currencies']['USD']['actual_micros'])
        self.assertEqual(r['status'], 'HOLD')

    def test_unknown_poison_total(self):
        r = project_costs('T1', [record(), record('storage', 'UNKNOWN', None, None)])
        self.assertIsNone(r['currencies']['USD']['actual_micros'])

    def test_missing_evidence(self):
        for field in ('amount_micros', 'evidence_sha256'):
            item = record(); item[field] = None
            self.assertIsNone(project_costs('T1', [item])['currencies']['USD']['actual_micros'])

    def test_known_zero(self):
        r = project_costs('T1', [record(amount=0)])
        self.assertEqual(r['currencies']['USD']['actual_micros'], 0)
        self.assertEqual(r['status'], 'VIEW_READY')

    def test_currencies_never_added(self):
        r = project_costs('T1', [record(), record('storage', currency='CNY')])
        self.assertEqual(set(r['currencies']), {'USD', 'CNY'})

    def test_duplicate_not_double_counted(self):
        r = project_costs('T1', [record(), record()])
        self.assertEqual(r['currencies']['USD']['actual_micros'], 100)

    def test_conflict_currency_or_amount(self):
        for item in (record(amount=101), record(currency='CNY')):
            with self.assertRaises(ValueError):
                project_costs('T1', [record(), item])

    def test_bad_amounts(self):
        for amount in (True, -1, 1.2, '100', MAX_AMOUNT + 1):
            with self.assertRaises(ValueError):
                project_costs('T1', [record(amount=amount)])

    def test_overflow(self):
        with self.assertRaises(ValueError):
            project_costs('T1', [record(amount=MAX_AMOUNT), record('storage', amount=1)])

    def test_cross_task(self):
        item = record(); item['task_id'] = 'T2'
        with self.assertRaises(ValueError): project_costs('T1', [item])

    def test_empty_unknown(self):
        self.assertEqual(project_costs('T1', [])['status'], 'HOLD')

    def test_bad_schema(self):
        for item in (None, {}, dict(record(), secret='hidden')):
            with self.assertRaises(ValueError): project_costs('T1', [item])

    def test_no_mutation_or_identifiers_in_output(self):
        items = [record()]; before = copy.deepcopy(items)
        result = project_costs('T1', items)
        self.assertEqual(items, before)
        self.assertNotIn('compute', repr(result))
        self.assertNotIn('a' * 64, repr(result))

    def test_input_bound(self):
        with self.assertRaises(ValueError): project_costs('T1', [record()] * 10001)
