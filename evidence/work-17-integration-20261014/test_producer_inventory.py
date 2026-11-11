"""New completeness checks; all authentication keys and producers are fixtures."""
import copy
import unittest
import test_foundation_integration as fixture
from foundation_integration import digest
from producer_inventory import complete_producer_view
from run_usage_projection import COUNTERS


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.context = fixture.IntegrationTests(methodName='runTest')
        self.context.setUp()
        self.kind = 'costs'
        self.inventory = {'type': 'CANONICAL_PRODUCER_INVENTORY', 'revision': 1,
                          'items': [{'component_id': 'compute', 'currency': 'CNY', 'kind': 'ACTUAL'},
                                    {'component_id': 'storage', 'currency': 'USD', 'kind': 'ACTUAL'}]}
        self.records = [{'task_id': 'target', 'component_id': x['component_id'], 'currency': x['currency'],
                         'kind': x['kind'], 'amount_micros': 5, 'evidence_sha256': 'd' * 64} for x in self.inventory['items']]

    def tearDown(self):
        self.context.tearDown()

    def result(self, complete=True, revision=None, inventory=None, records=None,
               inventory_verifier=fixture.verify, records_verifier=fixture.verify):
        inv = self.inventory if inventory is None else inventory
        data = {'type': 'CANONICAL_PRODUCER_RECORDS', 'inventory_sha256': digest(inv),
                'revision': inv['revision'] if revision is None else revision,
                'complete': complete, 'records': self.records if records is None else records}
        return complete_producer_view(self.kind, self.context.binding,
                                      self.context.envelope(self.kind, inv),
                                      self.context.envelope(self.kind, data),
                                      inventory_verifier, records_verifier, 100)

    def test_complete_multi_currency_cost_view(self):
        r = self.result()
        self.assertEqual(r['status'], 'VIEW_READY')
        self.assertEqual(set(r['currencies']), {'CNY', 'USD'})
        self.assertFalse(r['payment_granted']); self.assertFalse(r['release_granted'])

    def test_omitted_cost_component_hold(self):
        self.assertEqual(self.result(records=self.records[:1])['status'], 'HOLD')

    def test_extra_component_hold(self):
        item = dict(self.records[0]); item['component_id'] = 'unregistered'
        self.assertEqual(self.result(records=self.records + [item])['status'], 'HOLD')

    def test_currency_rebound_hold(self):
        rows = copy.deepcopy(self.records); rows[0]['currency'] = 'USD'
        self.assertEqual(self.result(records=rows)['status'], 'HOLD')

    def test_revision_rebound_hold(self):
        self.assertEqual(self.result(revision=2)['status'], 'HOLD')

    def test_boolean_revision_is_not_one(self):
        self.assertEqual(self.result(revision=True)['status'], 'HOLD')

    def test_partial_flag_hold(self):
        for value in (False, None, 1, 'true'):
            with self.subTest(value=value): self.assertEqual(self.result(complete=value)['status'], 'HOLD')

    def test_inventory_authentication_required(self):
        self.assertEqual(self.result(inventory_verifier=lambda *_: False)['status'], 'HOLD')

    def test_records_authentication_required(self):
        self.assertEqual(self.result(records_verifier=lambda *_: False)['status'], 'HOLD')

    def test_missing_inventory_does_not_make_empty_total_zero(self):
        self.assertEqual(complete_producer_view('costs', self.context.binding, None, None,
                                               fixture.verify, fixture.verify, 100)['status'], 'HOLD')

    def test_empty_authenticated_inventory_hold(self):
        inv = copy.deepcopy(self.inventory); inv['items'] = []
        self.assertEqual(self.result(inventory=inv, records=[])['status'], 'HOLD')

    def test_duplicate_inventory_hold(self):
        inv = copy.deepcopy(self.inventory); inv['items'].append(dict(inv['items'][0]))
        self.assertEqual(self.result(inventory=inv)['status'], 'HOLD')

    def test_exact_repeated_cost_record_hold(self):
        r = self.result(records=self.records + [dict(self.records[0])])
        self.assertEqual(r['status'], 'HOLD')
        self.assertNotIn('currencies', r)
        self.assertFalse(r['execution_granted'])

    def test_exact_repeated_usage_record_hold(self):
        self.usage()
        r = self.result(records=self.records + [dict(self.records[0])])
        self.assertEqual(r['status'], 'HOLD')
        self.assertNotIn('totals', r)
        self.assertFalse(r['release_granted'])

    def test_conflicting_duplicate_record_hold(self):
        item = dict(self.records[0]); item['amount_micros'] = 10
        self.assertEqual(self.result(records=self.records + [item])['status'], 'HOLD')

    def test_other_task_cost_rejected(self):
        records = copy.deepcopy(self.records); records[0]['task_id'] = 'other'
        self.assertEqual(self.result(records=records)['status'], 'HOLD')

    def test_unknown_value_stays_hold_after_inventory_match(self):
        records = copy.deepcopy(self.records); records[0]['amount_micros'] = None
        r = self.result(records=records)
        self.assertEqual(r['status'], 'HOLD'); self.assertIsNone(r['currencies']['CNY']['actual_micros'])

    def usage(self):
        self.kind = 'usage'
        self.inventory = {'type': 'CANONICAL_PRODUCER_INVENTORY', 'revision': 3,
                          'items': [{'run_id': 'run-a', 'provider': 'INTERNAL'}, {'run_id': 'run-b', 'provider': 'TENANT'}]}
        self.records = [{'run_id': item['run_id'], 'provider': item['provider'],
                         'counters': dict.fromkeys(COUNTERS, 3), 'evidence_sha256': 'e' * 64} for item in self.inventory['items']]

    def test_complete_usage_view_never_grants_quota(self):
        self.usage(); r = self.result()
        self.assertEqual(r['totals']['model_calls'], 6); self.assertIsNone(r['quota_remaining'])
        self.assertFalse(r['execution_granted'])

    def test_omitted_run_hold(self):
        self.usage(); self.assertEqual(self.result(records=self.records[:1])['status'], 'HOLD')

    def test_provider_rebound_hold(self):
        self.usage(); rows = copy.deepcopy(self.records); rows[0]['provider'] = 'TENANT'
        self.assertEqual(self.result(records=rows)['status'], 'HOLD')

    def test_unknown_usage_not_zero(self):
        self.usage(); rows = copy.deepcopy(self.records); rows[0]['counters']['model_calls'] = None
        r = self.result(records=rows)
        self.assertEqual(r['status'], 'HOLD'); self.assertIsNone(r['totals']['model_calls'])

    def test_extra_inventory_fields_rejected(self):
        inv = copy.deepcopy(self.inventory); inv['items'][0]['secret'] = 'DO_NOT_DISPLAY'
        self.assertEqual(self.result(inventory=inv)['reasons'], ['UNVERIFIED_OR_INCOMPLETE_PRODUCER_INVENTORY'])


if __name__ == '__main__': unittest.main()
