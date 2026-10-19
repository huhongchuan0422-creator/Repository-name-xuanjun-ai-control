"""Offline SMTP TLS and durable outbox tests. No server or provider connection."""
import copy
import smtplib
import ssl
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts.pr122_customer_core import Center, Unavailable
from scripts.pr122_customer_providers import Providers, drain_mail


class SMTPTransportTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # Any accidental real connection fails before opening a socket.
        self.stack.enter_context(patch('socket.socket', side_effect=AssertionError('Network forbidden')))
        self.stack.enter_context(patch('socket.create_connection', side_effect=AssertionError('Network forbidden')))
        self.plain = self.stack.enter_context(patch('smtplib.SMTP'))
        self.implicit = self.stack.enter_context(patch('smtplib.SMTP_SSL'))
        self.config = {'host': 'smtp.invalid', 'username': 'sender@example.invalid',
                       'password': 'synthetic-client-password', 'sender': 'sender@example.invalid'}
        self.context = self.stack.enter_context(patch('ssl.create_default_context', wraps=ssl.create_default_context))

    def send(self, config=None, purpose='VERIFY'):
        return Providers({'smtp': copy.deepcopy(self.config if config is None else config)}).mail(
            'recipient@example.invalid', purpose, 'synthetic-one-time-code', 'https://example.invalid')

    def assert_verified_context(self, context):
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.context.assert_called_once_with()

    def test_implicit_tls_465_verifies_certificate_before_authentication(self):
        self.config.update(tls_mode='implicit_tls', port=465)
        self.assertEqual(self.send(), 'ACCEPTED')
        self.plain.assert_not_called()
        self.assertEqual(self.implicit.call_args.args, ('smtp.invalid', 465))
        self.assertEqual(self.implicit.call_args.kwargs['timeout'], 12)
        self.assert_verified_context(self.implicit.call_args.kwargs['context'])
        client = self.implicit.return_value.__enter__.return_value
        self.assertEqual([c[0] for c in client.mock_calls], ['ehlo', 'login', 'send_message'])
        client.starttls.assert_not_called()
        client.login.assert_called_once_with('sender@example.invalid', 'synthetic-client-password')

    def test_implicit_tls_mode_defaults_to_465(self):
        self.config['tls_mode'] = 'implicit_tls'
        self.send()
        self.assertEqual(self.implicit.call_args.args, ('smtp.invalid', 465))
        self.plain.assert_not_called()

    def test_explicit_starttls_defaults_to_587_and_upgrades_before_authentication(self):
        self.config['tls_mode'] = 'starttls'
        self.send()
        self.plain.assert_called_once_with('smtp.invalid', 587, timeout=12)
        self.implicit.assert_not_called()
        client = self.plain.return_value.__enter__.return_value
        self.assertEqual([c[0] for c in client.mock_calls], ['ehlo', 'starttls', 'ehlo', 'login', 'send_message'])
        self.assert_verified_context(client.starttls.call_args.kwargs['context'])

    def test_legacy_config_keeps_starttls_and_numeric_string_port(self):
        self.config['port'] = '587'
        self.send()
        self.plain.assert_called_once_with('smtp.invalid', 587, timeout=12)
        self.implicit.assert_not_called()
        self.plain.return_value.__enter__.return_value.starttls.assert_called_once()

    def test_mode_is_explicit_not_inferred_from_port(self):
        self.config.update(tls_mode='implicit_tls', port=2465)
        self.send()
        self.assertEqual(self.implicit.call_args.args, ('smtp.invalid', 2465))
        self.plain.assert_not_called()

    def test_unknown_or_plaintext_tls_modes_fail_before_any_connection(self):
        for mode in ('plain', 'ssl', 'STARTTLS', '', None, False, {}, []):
            with self.subTest(mode=mode), self.assertRaisesRegex(Unavailable, 'MAIL_TLS_MODE_INVALID'):
                self.send({**self.config, 'tls_mode': mode})
        self.plain.assert_not_called()
        self.implicit.assert_not_called()
        self.context.assert_not_called()

    def test_missing_smtp_config_never_opens_connection(self):
        with self.assertRaisesRegex(Unavailable, 'MAIL_PENDING'):
            Providers({}).mail('recipient@example.invalid', 'VERIFY', 'code', 'https://example.invalid')
        self.plain.assert_not_called()
        self.implicit.assert_not_called()

    def test_starttls_not_supported_never_authenticates_or_falls_back(self):
        client = self.plain.return_value.__enter__.return_value
        client.starttls.side_effect = smtplib.SMTPNotSupportedError('synthetic TLS unsupported')
        with self.assertRaises(smtplib.SMTPNotSupportedError):
            self.send()
        client.login.assert_not_called()
        client.send_message.assert_not_called()
        self.plain.assert_called_once()
        self.implicit.assert_not_called()

    def test_implicit_certificate_failure_never_falls_back(self):
        self.config['tls_mode'] = 'implicit_tls'
        self.implicit.side_effect = ssl.SSLCertVerificationError('synthetic certificate failure')
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.send()
        self.implicit.assert_called_once()
        self.plain.assert_not_called()

    def test_starttls_certificate_failure_never_authenticates_or_falls_back(self):
        client = self.plain.return_value.__enter__.return_value
        client.starttls.side_effect = ssl.SSLCertVerificationError('synthetic certificate failure')
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.send()
        client.login.assert_not_called()
        client.send_message.assert_not_called()
        self.implicit.assert_not_called()

    def test_login_failure_never_sends_or_opens_retry_connection(self):
        self.config['tls_mode'] = 'implicit_tls'
        client = self.implicit.return_value.__enter__.return_value
        # This checks the application boundary after login() raises. The
        # unchanged stdlib login may try multiple advertised AUTH mechanisms
        # within this one connection; one login call does not imply one AUTH.
        client.login.side_effect = smtplib.SMTPAuthenticationError(535, b'synthetic rejected')
        with self.assertRaises(smtplib.SMTPAuthenticationError):
            self.send()
        client.send_message.assert_not_called()
        self.implicit.assert_called_once()
        self.plain.assert_not_called()

    def test_message_and_acceptance_semantics_are_preserved(self):
        self.config['tls_mode'] = 'implicit_tls'
        client = self.implicit.return_value.__enter__.return_value
        for purpose, title in (('VERIFY', '验证邮箱'), ('RESET', '重置密码')):
            with self.subTest(purpose=purpose):
                self.assertEqual(self.send(purpose=purpose), 'ACCEPTED')
                message = client.send_message.call_args.args[0]
                self.assertEqual(message['From'], 'sender@example.invalid')
                self.assertEqual(message['To'], 'recipient@example.invalid')
                self.assertEqual(message['Subject'], '玄钧云汇：' + title)
                self.assertIn('https://example.invalid/customer/center/', message.get_content())
                self.assertIn('synthetic-one-time-code', message.get_content())
                self.assertNotIn('?token=', message.get_content())

    def center(self, root):
        return Center(root, {'v1': b'k' * 32}, 'v1', clock=lambda: 1792137000, mail_ready=True)

    def test_send_timeout_is_durable_unknown_without_replay_after_reopen(self):
        for mode, factory in (('implicit_tls', self.implicit), ('starttls', self.plain)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                self.plain.reset_mock()
                self.implicit.reset_mock()
                root = Path(temporary) / 'private'
                center = self.center(root)
                provider = Providers({'smtp': {**self.config, 'tls_mode': mode}})
                client = factory.return_value.__enter__.return_value
                client.send_message.side_effect = TimeoutError('synthetic uncertain send')
                try:
                    center.register('recipient@example.invalid', 'synthetic-account-password')
                    self.assertEqual(drain_mail(center, provider, 'https://example.invalid'), {'status': 'UNKNOWN'})
                    self.assertEqual(center.db.execute('SELECT status FROM outbox').fetchone()[0], 'UNKNOWN')
                finally:
                    center.db.close()
                center = self.center(root)
                try:
                    self.assertEqual(drain_mail(center, provider, 'https://example.invalid'), {'pending': False})
                finally:
                    center.db.close()
                factory.assert_called_once()
                client.send_message.assert_called_once()

    def test_accepted_outbox_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as temporary:
            center = self.center(Path(temporary) / 'private')
            try:
                center.register('recipient@example.invalid', 'synthetic-account-password')
                provider = Providers({'smtp': {**self.config, 'tls_mode': 'implicit_tls'}})
                self.assertEqual(drain_mail(center, provider, 'https://example.invalid'), {'status': 'ACCEPTED'})
                self.assertEqual(drain_mail(center, provider, 'https://example.invalid'), {'pending': False})
                self.assertEqual(center.db.execute('SELECT status FROM outbox').fetchone()[0], 'ACCEPTED')
                self.implicit.return_value.__enter__.return_value.send_message.assert_called_once()
            finally:
                center.db.close()


if __name__ == '__main__':
    unittest.main()
