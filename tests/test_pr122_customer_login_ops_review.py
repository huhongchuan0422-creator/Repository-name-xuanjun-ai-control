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
                self.factory.assert_called_once()
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


if __name__ == '__main__':
    unittest.main()
