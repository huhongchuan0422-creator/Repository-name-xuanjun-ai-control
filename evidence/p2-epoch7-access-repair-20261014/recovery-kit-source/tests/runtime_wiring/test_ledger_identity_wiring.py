import sys
import types
import unittest
from unittest.mock import Mock, patch
import ledger_service as module


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.active = {'db_path': '/fixture/state.sqlite', 'release_sha256': 'a'*64,
                       'epoch': 8, 'state': 'ACTIVE'}
        self.config = dict(activation_descriptor='descriptor', activation_epoch_journal='journal',
                          activation_lock='lock', callback_user='xuanjun-callback',
                          control_repository='owner/repo', max_workers=2, source_commit='b'*40)
        self.store = Mock()
        self.store.read.return_value = dict(self.active)
        self.native = Mock()
        self.owner = Mock()
        self.db = Mock()
        self.server = Mock()
        endpoint = types.ModuleType('owner_feishu_ledger_endpoint')
        endpoint.OwnerFeishuLedgerEndpoint = Mock()
        patches = [patch.object(module, 'ActivationStore', return_value=self.store),
                   patch.object(module, 'load_native_peer_identity', self.native),
                   patch.object(module, 'load_owner_process_verifier', self.owner),
                   patch.object(module, 'ExecutionLedger', self.db),
                   patch.object(module, 'LedgerOwnerDecisionServer', self.server),
                   patch.object(module.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=1004)),
                   patch.dict(sys.modules, {'owner_feishu_ledger_endpoint': endpoint})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_exact_active_release_and_owner_verifier_reach_server(self):
        result = module.build(self.config)
        self.owner.assert_called_once_with('a'*64)
        self.assertIs(result, self.server.return_value)
        self.assertIs(self.server.call_args[1]['owner_process_verifier'], self.owner.return_value)
        self.assertIs(self.server.call_args[1]['native_identity'], self.native.return_value)
        self.assertEqual(self.server.call_args[0][2], 1004)

    def test_missing_owner_pins_prevent_database_open(self):
        self.owner.side_effect = FileNotFoundError('fixture')
        with self.assertRaises(FileNotFoundError): module.build(self.config)
        self.db.assert_not_called()
        self.server.assert_not_called()

    def test_invalid_native_pins_prevent_database_open(self):
        self.native.side_effect = ValueError('fixture')
        with self.assertRaises(ValueError): module.build(self.config)
        self.db.assert_not_called()
        self.owner.assert_not_called()

    def test_activation_drift_prevents_database_open(self):
        self.store.read.side_effect = [dict(self.active), dict(self.active, epoch=9)]
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_CHANGED'): module.build(self.config)
        self.db.assert_not_called()

    def test_inactive_second_read_prevents_database_open(self):
        self.store.read.side_effect = [dict(self.active), ValueError('inactive')]
        with self.assertRaises(ValueError): module.build(self.config)
        self.db.assert_not_called()

    def test_missing_release_binding_prevents_database_open(self):
        self.store.read.return_value = {'db_path': '/fixture/state.sqlite'}
        with self.assertRaises(KeyError): module.build(self.config)
        self.owner.assert_not_called()
        self.db.assert_not_called()

    def test_other_callback_user_prevents_database_open(self):
        with self.assertRaisesRegex(ValueError, 'CALLBACK_USER'):
            module.build(dict(self.config, callback_user='another-user'))
        self.native.assert_not_called()
        self.db.assert_not_called()

    def test_nss_uid_drift_prevents_database_open(self):
        module.pwd.getpwnam.return_value = types.SimpleNamespace(pw_uid=1005)
        with self.assertRaisesRegex(ValueError, 'CALLBACK_UID'): module.build(self.config)
        self.native.assert_not_called()
        self.db.assert_not_called()

    def test_both_pin_loaders_finish_before_writable_ledger_open(self):
        seen = []
        self.native.side_effect = lambda: seen.append('native') or self.native.return_value
        self.owner.side_effect = lambda value: seen.append('owner') or self.owner.return_value
        self.db.side_effect = lambda *a, **k: seen.append('database') or self.db.return_value
        module.build(self.config)
        self.assertEqual(seen, ['native', 'owner', 'database'])


if __name__ == '__main__': unittest.main()
