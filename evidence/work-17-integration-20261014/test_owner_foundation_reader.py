"""Original ActivationStore/SQLite fixtures, never deployed Owner acceptance."""
import copy
import json
import unittest
import test_foundation_integration as fixture
from activation_control import ActivationStore
from owner_foundation_reader import read_owner_foundations
from foundation_integration import digest


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.context = fixture.IntegrationTests(methodName='runTest')
        self.context.setUp()
        self.active = {'schema': 1, 'state': 'ACTIVE', 'release_sha256': 'a' * 64,
                       'config_sha256': 'b' * 64, 'binary_sha256': 'c' * 64,
                       'ledger_uuid': '11111111-1111-4111-8111-111111111111',
                       'instance': '22222222-2222-4222-8222-222222222222',
                       'generation': 1, 'epoch': 2, 'db_path': str(self.context.path),
                       'ledger_socket': str(self.context.path.parent / 'ledger.sock')}
        self.context.read()

    def tearDown(self): self.context.tearDown()

    def reader(self, **kwargs):
        values = dict(db=self.context.reader, binding=self.context.binding, now=100,
                      activation_reader=lambda **_: copy.deepcopy(self.active),
                      expected_activation=copy.deepcopy(self.active), receipts={},
                      receipt_verifier=fixture.verify, producer_envelopes={},
                      inventory_verifier=fixture.verify, records_verifier=fixture.verify)
        values.update(kwargs)
        return read_owner_foundations(**values)

    def test_all_seven_views_and_chinese_summary_missing_producer_hold(self):
        result = self.reader()
        self.assertEqual(len(result['views']), 7); self.assertEqual(len(result['summary']), 7)
        self.assertEqual(result['status'], 'HOLD'); self.assertFalse(result['execution_granted'])

    def test_internal_paths_and_secret_not_exposed(self):
        result = json.dumps(self.reader())
        self.assertNotIn(str(self.context.path), result)
        self.assertNotIn(self.active['ledger_uuid'], result)
        self.assertNotIn('DO_NOT_DISPLAY', result)

    def test_nonactive_epoch_rejected(self):
        expected = copy.deepcopy(self.active); expected['state'] = 'PREPARED'
        with self.assertRaisesRegex(ValueError, 'ACTIVE_EPOCH'): self.reader(expected_activation=expected)

    def test_stale_epoch_rejected(self):
        expected = copy.deepcopy(self.active); expected['epoch'] = 3
        with self.assertRaisesRegex(ValueError, 'ACTIVE_EPOCH'): self.reader(expected_activation=expected)

    def test_descriptor_configuration_drift_rejected(self):
        expected = copy.deepcopy(self.active); expected['config_sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_BINDING'): self.reader(expected_activation=expected)

    def test_switch_during_read_rejected(self):
        count = [0]
        def read(**kwargs):
            count[0] += 1; result = copy.deepcopy(self.active)
            if count[0] == 2: result['epoch'] += 1
            return result
        with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_READ'): self.reader(activation_reader=read)

    def test_other_db_path_rejected(self):
        active = copy.deepcopy(self.active); active['db_path'] = str(self.context.path.parent / 'other.sqlite')
        with self.assertRaisesRegex(ValueError, 'DATABASE_PATH'):
            self.reader(expected_activation=active, activation_reader=lambda **_: active)

    def test_partial_cost_generic_receipt_cannot_bypass_inventory(self):
        with self.assertRaisesRegex(ValueError, 'COMPLETE_PRODUCER_PATH'):
            self.reader(receipts={'costs': self.context.envelope('costs', [])})

    def test_complete_inventory_reaches_owner_view(self):
        inventory = {'type': 'CANONICAL_PRODUCER_INVENTORY', 'revision': 1,
                     'items': [{'component_id': 'compute', 'currency': 'CNY', 'kind': 'ACTUAL'}]}
        records = {'type': 'CANONICAL_PRODUCER_RECORDS', 'revision': 1,
                   'inventory_sha256': digest(inventory), 'complete': True,
                   'records': [{'task_id': 'target', 'component_id': 'compute', 'currency': 'CNY',
                                'kind': 'ACTUAL', 'amount_micros': 10, 'evidence_sha256': 'd' * 64}]}
        pair = {'inventory': self.context.envelope('costs', inventory),
                'records': self.context.envelope('costs', records)}
        result = self.reader(producer_envelopes={'costs': pair})
        self.assertEqual(result['views']['costs']['currencies']['CNY']['actual_micros'], 10)
        self.assertEqual(result['views']['usage']['status'], 'HOLD')
        self.assertFalse(result['release_granted'])

    def test_unknown_producer_pair_rejected(self):
        with self.assertRaises(ValueError): self.reader(producer_envelopes={'other': {}})

    def test_no_canonical_writes(self):
        before = list(self.context.writer.iterdump())
        self.reader()
        self.assertEqual(before, list(self.context.writer.iterdump()))

    def test_original_real_activation_store_read_callback(self):
        import os
        root = self.context.path.parent / 'activation'; root.mkdir(mode=0o700)
        store = ActivationStore(str(root/'active.json'), str(root/'epochs.jsonl'), str(root/'lock'), owner_uid=os.geteuid())
        store.prepare('a'*64, 'b'*64, 'c'*64, self.active['ledger_uuid'], 1, self.active['instance'],
                              str(self.context.path), self.active['ledger_socket'])
        # Exercise real append-only store in isolated fixture, never host activation.
        self.assertEqual(store.read()['state'], 'PREPARED')
        with self.assertRaises(Exception): self.reader(activation_reader=store.read)


if __name__ == '__main__': unittest.main()
