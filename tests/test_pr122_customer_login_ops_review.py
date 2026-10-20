"""Offline operator-scope checks. No listeners, providers or host mutation."""
import base64
import copy
import io
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import pr122_customer_ops as ops
from scripts import pr122_customer_http as http
from scripts import pr122_customer_publication_worker as publication
from scripts.pr122_customer_core import Denied, canonical
from scripts.pr122_customer_profile import FULL, LOGIN_ONLY


class LoginOpsTests(unittest.TestCase):
    def setUp(self):
        self.config = {'deployment_profile': LOGIN_ONLY, 'keys': {'v1': base64.b64encode(b'k' * 32).decode()},
                       'active_key': 'v1', 'providers': {'smtp': {'host': 'smtp.invalid'}},
                       'backup_key': base64.b64encode(b'b' * 32).decode(), 'backup_key_ref': 'fixture'}
        self.center = Mock()
        self.center.check_integrity.return_value = {'verified': True}
        self.factory = Mock(return_value=self.center)
        self.mail = Mock(return_value={'status': 'SENT'})
        self.message = Mock(return_value={'status': 'ACCEPTED'})
        self.publisher = Mock(return_value={'status': 'DONE'})
        self.serve = Mock()

    def invocation(self, action, config=None):
        config = copy.deepcopy(self.config if config is None else config)
        stack = ExitStack()
        runtime = action in ('serve', 'worker')
        if runtime:
            config = {key: value for key, value in config.items()
                      if key not in ('backup_key', 'backup_key_ref')}
        for adapter in (
            patch('sys.argv', ['operator', action, '--input', '/offline/forbidden-input', '--output', '/offline/unused-output']),
            patch.object(ops.os, 'geteuid', return_value=12345 if runtime else 0),
            patch.object(ops.os, 'uname', return_value=SimpleNamespace(nodename=ops.HOST)),
            patch.object(ops, 'load_config', return_value=config),
            patch.object(ops, 'private_path', side_effect=lambda path: Path(path)),
            patch.object(Path, 'stat', return_value=SimpleNamespace(st_uid=12345, st_mode=0o600)),
            patch.object(Path, 'read_bytes', return_value=canonical(config)),
            patch.object(ops, 'factory', self.factory),
            patch.object(ops, 'drain_mail', self.mail),
            patch.object(ops, 'drain_message', self.message),
            patch.object(publication, 'main_worker', self.publisher),
            patch.object(http, 'serve', self.serve),
            patch('pwd.getpwnam', return_value=SimpleNamespace(pw_uid=12345, pw_gid=12345)),
            patch.object(ops.os, 'umask'), patch.object(ops.os, 'setgroups'),
            patch.object(ops.os, 'setgid'), patch.object(ops.os, 'setuid'),
            patch('sys.stdout', new_callable=io.StringIO),
        ):
            stack.enter_context(adapter)
        return stack

    def test_all_business_cli_actions_are_denied_before_factory_or_publisher(self):
        for action in ('publisher', 'import-authority', 'import-change-authority', 'issue-preview-delivery'):
            with self.subTest(action=action), self.invocation(action), \
                    patch.object(ops, 'private_path', side_effect=AssertionError('Business input read')), \
                    self.assertRaisesRegex(Denied, 'LOGIN_ONLY_OPERATOR_SCOPE'):
                ops.main()
        self.factory.assert_not_called()
        self.publisher.assert_not_called()
        self.mail.assert_not_called()
        self.message.assert_not_called()

    def test_login_worker_drains_only_mail(self):
        with self.invocation('worker'):
            ops.main()
        self.factory.assert_called_once()
        self.mail.assert_called_once()
        self.message.assert_not_called()
        self.center.db.close.assert_called_once()

    def test_full_worker_still_drains_both_queues(self):
        config = copy.deepcopy(self.config)
        config.pop('deployment_profile')
        with self.invocation('worker', config):
            ops.main()
        self.mail.assert_called_once()
        self.message.assert_called_once()

    def test_serve_forwards_profile(self):
        with self.invocation('serve'):
            ops.main()
        self.assertEqual(self.serve.call_args.kwargs, {'deployment_profile': LOGIN_ONLY})
        self.mail.assert_not_called()
        self.message.assert_not_called()

    def test_security_maintenance_actions_remain_available(self):
        for action in ('integrity', 'backup', 'restore-isolated'):
            self.factory.reset_mock()
            with self.subTest(action=action), self.invocation(action), \
                    patch.object(ops, 'backup', return_value={'backed_up': True}) as backup, \
                    patch.object(ops, 'restore', return_value={'restored': 'ISOLATED_MAINTENANCE'}) as restore:
                ops.main()
                self.assertEqual(self.factory.call_count, int(action != 'restore-isolated'))
                self.assertEqual(backup.call_count, int(action == 'backup'))
                self.assertEqual(restore.call_count, int(action == 'restore-isolated'))
        self.publisher.assert_not_called()
        self.message.assert_not_called()

    def test_full_publisher_retains_existing_entry(self):
        config = copy.deepcopy(self.config)
        config['deployment_profile'] = FULL
        with self.invocation('publisher', config):
            ops.main()
        self.publisher.assert_called_once()
        self.factory.assert_not_called()

    def test_profile_mismatch_and_non_smtp_runtime_fail_closed(self):
        runtime = {key: self.config[key] for key in ('deployment_profile', 'keys', 'active_key', 'providers')}
        self.assertTrue(ops.validate_runtime_contexts(self.config, runtime))
        for case in ('missing_profile', 'unknown_profile', 'business_provider', 'smtp_drift'):
            value = copy.deepcopy(runtime)
            if case == 'missing_profile':
                value.pop('deployment_profile')
            elif case == 'unknown_profile':
                value['deployment_profile'] = 'LOGIN_PLUS_PREVIEW'
            elif case == 'business_provider':
                value['providers']['telegram'] = {'token': 'fixture'}
            else:
                value['providers']['smtp']['host'] = 'different.invalid'
            with self.subTest(case=case), self.assertRaises(Denied):
                ops.validate_runtime_contexts(self.config, value)

    def test_factory_login_does_not_construct_business_callbacks(self):
        with patch.object(ops, 'Center', return_value=self.center) as center, \
                patch.object(ops, 'ClamScanner', side_effect=AssertionError('Scanner unavailable')), \
                patch.object(ops, 'SecretRefMetadata', side_effect=AssertionError('Secretref unavailable')), \
                patch.object(Path, 'exists', return_value=False):
            self.assertIs(ops.factory(self.config), self.center)
        for name in ('scanner', 'secretref', 'evidence_context', 'privacy_policy_context', 'privacy_processing_context'):
            self.assertIsNone(center.call_args.kwargs[name])


    def test_restore_isolated_recovers_without_constructing_corrupt_live_center(self):
        import json
        import tempfile
        from cryptography.exceptions import InvalidTag
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / 'backup-source'
            target = root / 'isolated-restored'
            backup_file = root / 'center.backup'
            live_root = root / 'synthetic-live-root'
            live_root.mkdir(mode=0o700)
            live_db = live_root / 'center.sqlite'
            live_db.write_bytes(b'corrupt synthetic live sqlite bytes')
            live_before = live_db.read_bytes()
            keys = {'v1': b'k' * 32}
            source = ops.Center(source_root, keys, 'v1')
            try:
                ops.backup(source, backup_file, b'b' * 32, 'fixture-backup-key')
            finally:
                source.db.close()

            config = copy.deepcopy(self.config)
            stdout = io.StringIO()
            with ExitStack() as stack:
                stack.enter_context(patch('sys.argv', ['operator', 'restore-isolated',
                    '--input', str(backup_file), '--output', str(target)]))
                stack.enter_context(patch.object(ops, 'ROOT', live_root))
                stack.enter_context(patch.object(ops.os, 'geteuid', return_value=0))
                stack.enter_context(patch.object(ops.os, 'uname', return_value=SimpleNamespace(nodename=ops.HOST)))
                stack.enter_context(patch.object(ops, 'load_config', return_value=config))
                factory = stack.enter_context(patch.object(ops, 'factory', side_effect=AssertionError('corrupt live DB factory must not run')))
                stack.enter_context(patch('pwd.getpwnam', return_value=SimpleNamespace(pw_uid=12345, pw_gid=12345)))
                stack.enter_context(patch.object(ops.os, 'umask'))
                stack.enter_context(patch.object(ops.os, 'setgroups'))
                stack.enter_context(patch.object(ops.os, 'setgid'))
                stack.enter_context(patch.object(ops.os, 'setuid'))
                stack.enter_context(patch('sys.stdout', stdout))
                ops.main()

            result = json.loads(stdout.getvalue())
            self.assertEqual(result['restored'], 'ISOLATED_MAINTENANCE')
            self.assertTrue(result['old_sessions_invalid'])
            self.assertTrue(target.is_dir())
            self.assertEqual(live_db.read_bytes(), live_before)
            factory.assert_not_called()
            db = __import__('sqlite3').connect(target / 'center.sqlite')
            try:
                self.assertEqual(db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0], '1')
            finally:
                db.close()

    def test_restore_rejects_missing_live_root_normalized_alias_and_symlink_before_output(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            root = parent / 'synthetic-live-root'
            backup = parent / 'unused-backup'
            backup.write_bytes(b'not read for forbidden target')
            keys = {'v1': b'k' * 32}
            with patch.object(ops, 'ROOT', root):
                self.assertFalse(root.exists())
                for target in (root, parent / 'nested' / '..' / root.name):
                    with self.subTest(target=target), self.assertRaisesRegex(Denied, 'RESTORE_LIVE_ROOT_FORBIDDEN'):
                        ops.restore(backup, target, b'b' * 32, keys, 'v1')
                    self.assertFalse(root.exists())
                alias = parent / 'root-alias'
                alias.symlink_to(root, target_is_directory=True)
                with self.assertRaisesRegex(Denied, 'SYMLINK_PATH'):
                    ops.restore(backup, alias, b'b' * 32, keys, 'v1')
                self.assertFalse(root.exists())

    def test_restore_key_material_rejects_bad_ids_lengths_and_active_key_before_output(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'must-not-exist'
            cases = []
            bad_id = copy.deepcopy(self.config); bad_id['keys'] = {'bad key': base64.b64encode(b'k' * 32).decode()}
            cases.append(bad_id)
            short = copy.deepcopy(self.config); short['keys'] = {'v1': base64.b64encode(b'k' * 31).decode()}
            cases.append(short)
            inactive = copy.deepcopy(self.config); inactive['active_key'] = 'missing'
            cases.append(inactive)
            for config in cases:
                with self.subTest(config=config), self.assertRaises(Denied):
                    ops.restore_key_material(config)
                self.assertFalse(output.exists())

    def test_restore_isolated_bad_key_config_never_calls_restore_or_creates_output(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'must-not-exist'
            config = copy.deepcopy(self.config)
            config['keys'] = {'v1': base64.b64encode(b'k' * 31).decode()}
            with self.invocation('restore-isolated', config), \
                    patch('sys.argv', ['operator', 'restore-isolated', '--input', str(Path(td) / 'backup'), '--output', str(output)]), \
                    patch.object(ops, 'restore', side_effect=AssertionError('restore must not run')) as restore, \
                    self.assertRaises(Denied):
                ops.main()
            restore.assert_not_called()
            self.assertFalse(output.exists())

    def test_invalid_encrypted_backup_never_leaves_restore_output(self):
        import tempfile
        from cryptography.exceptions import InvalidTag
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backup = root / 'bad.backup'
            backup.write_bytes(b'0' * 64)
            target = root / 'must-not-exist'
            with self.assertRaises(InvalidTag):
                ops.restore(backup, target, b'b' * 32, {'v1': b'k' * 32}, 'v1')
            self.assertFalse(target.exists())



if __name__ == '__main__':
    unittest.main()
