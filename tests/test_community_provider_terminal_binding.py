"""Provider-bound refund and split terminal-state safety, synthetic only."""
import contextlib
import unittest
from unittest.mock import Mock

from scripts.community_wechat_sp_actions import ProviderActions, ProviderActionUnknown


class Center:
    def now(self):
        return 100
    def tx(self):
        return contextlib.nullcontext()


class ProviderTerminalBindingTest(unittest.TestCase):
    def setUp(self):
        self.actions = object.__new__(ProviderActions)
        self.actions.center = Center()
        self.g = {'scope': {'tenant_id': 'tenant', 'merchant_id': 'merchant', 'store_id': 'store'},
                  'project': 'project', 'user_id': 'finance'}
        self.policy = {'sub_mchid': '1234567891',
                       'receivers': {'recipient': {'type': 'MERCHANT_ID', 'account': '1234567892'}}}
        self.actions._authorize = Mock(return_value=(self.g, self.policy))

    def test_refund_transaction_binding_rejects_unrelated_payment(self):
        saved = {'kind': 'REFUND', 'provider_reference': 'rf1',
                 'transaction_id': 'real-transaction', 'payload': {
                     'out_trade_no': 'trade1', 'amount': {
                         'total': 100, 'refund': 20, 'currency': 'CNY'}}}
        data = {'sub_mchid': '1234567891', 'out_refund_no': 'rf1',
                'out_trade_no': 'trade1', 'transaction_id': 'wrong-transaction',
                'status': 'SUCCESS', 'amount': {'total': 100, 'refund': 20, 'currency': 'CNY'}}
        self.actions._load = Mock(side_effect=AssertionError('must reject before mutation'))
        with self.assertRaisesRegex(ValueError, 'PROVIDER_REFUND_BINDING_MISMATCH'):
            self.actions._accept('session', 'csrf', 'workspace', self.g, self.policy,
                                 'key', 'lock', saved, data, 'd' * 64)
        self.actions._load.assert_not_called()

    def test_finished_split_cannot_change_receiver_outcome(self):
        receiver = {'receiver_id': 'recipient', 'amount_minor': 20, 'result': 'SUCCESS'}
        saved = {'kind': 'SPLIT', 'provider_reference': 'ps1',
                 'transaction_id': 'transaction1',
                 'request_hash': 'h' * 64, 'payload': {'receivers': [
                     {'type': 'MERCHANT_ID', 'account': '1234567892', 'amount': 20}]}}
        persisted = dict(saved, result={
            'status': 'FINISHED', 'receivers': [receiver],
            'receiver_results_pending': False})
        self.actions._load = Mock(return_value=persisted)
        self.actions._save = Mock()
        data = {'sub_mchid': '1234567891', 'out_order_no': 'ps1',
                'transaction_id': 'transaction1', 'state': 'FINISHED',
                'receivers': [{'type': 'MERCHANT_ID', 'account': '1234567892',
                               'amount': 20, 'result': 'CLOSED'}]}
        with self.assertRaisesRegex(ProviderActionUnknown, 'TERMINAL_PROVIDER_RESULT_CONFLICT'):
            self.actions._accept('session', 'csrf', 'workspace', self.g, self.policy,
                                 'key', 'lock', saved, data, 'd' * 64)
        self.actions._save.assert_not_called()

    def test_finished_split_identical_replay_not_rejected_as_conflict(self):
        receiver = {'receiver_id': 'recipient', 'amount_minor': 20, 'result': 'SUCCESS'}
        saved = {'kind': 'SPLIT', 'provider_reference': 'ps1',
                 'transaction_id': 'transaction1', 'request_hash': 'h' * 64,
                 'payload': {'receivers': [
                     {'type': 'MERCHANT_ID', 'account': '1234567892', 'amount': 20}]}}
        persisted = dict(saved, result={'status': 'FINISHED',
                                        'receivers': [receiver], 'receiver_results_pending': False})
        self.actions._load = Mock(return_value=persisted)
        self.actions._save = Mock()
        data = {'sub_mchid': '1234567891', 'out_order_no': 'ps1',
                'transaction_id': 'transaction1', 'state': 'FINISHED',
                'receivers': [{'type': 'MERCHANT_ID', 'account': '1234567892',
                               'amount': 20, 'result': 'SUCCESS'}]}
        # Terminal consistency has been checked before later DB lock/audit work.
        # Halt at the expected database access rather than masking an early conflict.
        self.actions.center.db = Mock()
        self.actions.center.db.execute.side_effect = RuntimeError('NEXT_DB_STEP')
        with self.assertRaisesRegex(RuntimeError, 'NEXT_DB_STEP'):
            self.actions._accept('session', 'csrf', 'workspace', self.g, self.policy,
                                 'key', 'lock', saved, data, 'd' * 64)


if __name__ == '__main__':
    unittest.main()
