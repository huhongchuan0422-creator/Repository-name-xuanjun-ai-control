"""Offline HTTP isolation checks for the explicitly selected login profile.

Only disposable SQLite databases and a loopback test server are used. Provider
transports and subprocesses are forbidden. No production login or deployment is
performed, and existing verified fixture accounts are not target-host evidence.
"""
import grp
import json
import os
import pwd
import subprocess
import threading
import unittest
from contextlib import ExitStack
from http.server import HTTPServer
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import pr122_customer_http as http
from scripts.pr122_customer_core import Center, Denied
from scripts.pr122_customer_providers import Providers
from tests import test_pr122_customer_center as core_tests
from tests import test_pr122_customer_http as http_tests


LOGIN = 'OFFICIAL_LOGIN_ONLY_V1'
ORIGIN = 'https://wenwenwenyiyiyi.work'
ASSETS = Path(http.__file__).resolve().parent.parent / 'deploy/pr122-customer-center/ui'


class LoginProfileTests(unittest.TestCase):
    # Borrow fixture helpers, never inherit the original TestCase's tests.
    imported = core_tests.CustomerTests.imported
    request = http_tests.HttpTests.request
    auth_headers = http_tests.HttpTests.auth_headers
    finish = http_tests.HttpTests.finish

    def setUp(self):
        core_tests.CustomerTests.setUp(self)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(subprocess, 'run', side_effect=AssertionError('Actual commands forbidden')))
        self.stack.enter_context(patch.object(os, 'system', side_effect=AssertionError('Actual shell forbidden')))
        self.mail_ready = True
        self.providers = Providers({
            'smtp': {'fixture': 'configured'}, 'telegram': {'fixture': 'configured'},
            'feishu': {'fixture': 'configured'}, 'secretref': {'fixture': 'configured'},
            'web_ai': {'fixture': 'configured'},
        }, post=Mock(side_effect=AssertionError('Provider request forbidden')),
            telegram_transport=Mock(side_effect=AssertionError('Telegram request forbidden')))
        self.provider_calls = []
        for name in ('telegram', 'feishu', 'send', 'mail'):
            self.provider_calls.append(self.stack.enter_context(patch.object(
                self.providers, name, side_effect=AssertionError('Provider action forbidden'))))
        self.factory = Mock(side_effect=lambda: Center(self.root, {'v1': self.key}, 'v1',
            clock=lambda: self.now, mail_ready=self.mail_ready,
            scanner=Mock(side_effect=AssertionError('Scanner forbidden'))))
        self.source_identity = Mock(return_value='offline-test-source')
        self.app = http.App(self.factory, self.providers, ORIGIN, ASSETS,
                            source_identity=self.source_identity, deployment_profile=LOGIN)
        self.server = HTTPServer(('127.0.0.1', 0), self.app.handler())
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.addCleanup(self.finish)

    def switch_full(self, explicit=False):
        kwargs = {'deployment_profile': 'FULL'} if explicit else {}
        app = http.App(self.factory, self.providers, ORIGIN, ASSETS,
                       source_identity=self.source_identity, **kwargs)
        self.server.RequestHandlerClass = app.handler()

    def assert_no_providers(self):
        for method in self.provider_calls: method.assert_not_called()
        self.providers.post.assert_not_called()
        self.providers.telegram_transport.assert_not_called()

    def assert_blocked(self, paths, methods=('GET', 'HEAD', 'POST'), authenticated=True):
        before = self.c.db.total_changes
        self.factory.reset_mock()
        headers = self.auth_headers() if authenticated else {}
        for path in paths:
            for method in methods:
                with self.subTest(path=path, method=method, authenticated=authenticated):
                    status, reply_headers, raw = self.request(path, {} if method == 'POST' else None,
                                                              headers, method=method)
                    self.assertEqual(status, 403)
                    self.assertNotIn('Set-Cookie', reply_headers)
                    if method == 'HEAD': self.assertEqual(raw, b'')
        self.factory.assert_not_called()
        self.assertEqual(self.c.db.total_changes, before)
        self.assert_no_providers()

    def test_project_and_private_data_reads_are_denied_before_factory(self):
        self.assert_blocked(('api/projects', 'api/checklist/project-a',
            'api/download/project-a/o_existing', 'api/messages/project-a',
            'api/pending_links/project-a', 'api/privacy/project-a', 'api/evidence/project-a'))

    def test_callbacks_are_denied_for_all_methods_even_when_providers_configured(self):
        self.assert_blocked(('webhooks/telegram', 'webhooks/feishu'))

    def test_preview_publication_and_edit_reads_are_denied_for_all_methods(self):
        self.assert_blocked(('preview/project-a/home/v1', 'api/previews/project-a',
            'api/publication/project-a/job-1', 'api/edit_candidate/project-a/job-1',
            'api/changes/project-a'))

    def test_project_membership_material_and_message_writes_are_denied(self):
        self.assert_blocked(('api/invite', 'api/accept_invite', 'api/revoke', 'api/save',
            'api/transition', 'api/message', 'api/send', 'api/bind', 'api/confirm_link', 'api/unlink'))

    def test_change_privacy_and_ai_business_actions_are_denied(self):
        self.assert_blocked(('api/privacy_acknowledge', 'api/privacy_request',
            'api/change_small_edit', 'api/change_delivery_report', 'api/change_updates',
            'api/change_retest', 'api/change_context', 'api/change_submit', 'api/change_baseline',
            'api/change_confirm_new_scope', 'api/change_assess', 'api/change_respond', 'api/ai_reply'))

    def test_anonymous_business_and_unknown_routes_are_also_denied(self):
        self.assert_blocked(('api/checklist/project-a', 'api/message', 'webhooks/telegram',
                            'preview/project-a/home/v1', 'api/unknown'), authenticated=False)

    def test_auth_route_names_are_exact_not_prefix_matches(self):
        self.assert_blocked(('api/login/extra', 'api/me/extra', 'api/register_extra',
                            'api/verify/extra', 'api/LOGIN', 'api/../me', 'api/me?project=project-a'))

    def test_client_headers_cannot_select_full_profile(self):
        headers = {**self.auth_headers(), 'X-Deployment-Profile': 'FULL',
                   'X-Xuanjun-Profile': 'FULL', 'X-Feature-Scope': 'FULL'}
        self.factory.reset_mock()
        self.assertEqual(self.request('api/message', {'project': 'project-a', 'body': 'fixture'}, headers)[0], 403)
        self.factory.assert_not_called()

    def test_business_route_is_rejected_without_reading_declared_request_body(self):
        self.factory.reset_mock()
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        try:
            connection.putrequest('POST', '/customer/center/api/save', skip_host=True)
            connection.putheader('Host', 'wenwenwenyiyiyi.work')
            connection.putheader('Origin', ORIGIN)
            connection.putheader('Content-Type', 'application/json')
            connection.putheader('Content-Length', '7000000')
            connection.endheaders()  # Deliberately send no body at all.
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        finally: connection.close()
        self.factory.assert_not_called()
        self.assert_no_providers()

    def test_me_post_is_rejected_before_factory(self):
        self.factory.reset_mock()
        self.assertEqual(self.request('api/me', {}, self.auth_headers())[0], 403)
        self.factory.assert_not_called()

    def test_static_login_assets_remain_available_without_factory(self):
        self.factory.reset_mock()
        for name in ('', 'app.css', 'app.js'):
            for method in ('GET', 'HEAD'):
                with self.subTest(name=name, method=method):
                    status, headers, raw = self.request(name, method=method)
                    self.assertEqual(status, 200)
                    self.assertIn('no-store', headers['Cache-Control'])
                    if method == 'HEAD': self.assertEqual(raw, b'')
        self.factory.assert_not_called()

    def test_me_returns_only_verified_account_status_without_business_reads(self):
        with patch.object(Center, 'projects', side_effect=AssertionError('Project enumeration forbidden')) as projects, \
             patch.object(self.providers, 'status', side_effect=AssertionError('Provider enumeration forbidden')) as providers:
            status, headers, raw = self.request('api/me', headers=self.auth_headers())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {'user_id': self.owner, 'account_status': 'VERIFIED'})
        self.assertIn('no-store', headers['Cache-Control'])
        projects.assert_not_called()
        providers.assert_not_called()
        self.assert_no_providers()

    def test_me_head_has_no_body_and_still_does_not_read_business_data(self):
        with patch.object(Center, 'projects', side_effect=AssertionError('Project enumeration forbidden')):
            status, headers, raw = self.request('api/me', headers=self.auth_headers(), method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(raw, b'')
        self.assertGreater(int(headers['Content-Length']), 0)

    def test_me_requires_valid_unexpired_session(self):
        self.assertEqual(self.request('api/me')[0], 403)
        self.assertEqual(self.request('api/me', headers={'Cookie': http.COOKIE + '=invalid'})[0], 403)
        self.now += 3601
        self.assertEqual(self.request('api/me', headers=self.auth_headers())[0], 403)

    def test_login_retains_secure_cookie_and_token_is_not_in_body(self):
        status, headers, raw = self.request('api/login', {'email': 'owner@example.com', 'password': 'correct-password-123'})
        self.assertEqual(status, 200)
        value = json.loads(raw)
        self.assertEqual(set(value), {'csrf', 'user_id'})
        self.assertEqual(value['user_id'], self.owner)
        cookie = headers['Set-Cookie']
        self.assertTrue(cookie.startswith(http.COOKIE + '='))
        for required in ('Path=/', 'Secure', 'HttpOnly', 'SameSite=Strict', 'Max-Age=3600'):
            self.assertIn(required, cookie)
        self.source_identity.assert_called_once()
        self.assert_no_providers()

    def test_login_keeps_origin_host_source_identity_and_exact_fields_guards(self):
        body = {'email': 'owner@example.com', 'password': 'correct-password-123'}
        self.assertEqual(self.request('api/login', body, {'Origin': 'https://foreign.invalid'})[0], 403)
        self.assertEqual(self.request('api/login', body, {'Host': 'foreign.invalid'})[0], 403)
        self.assertEqual(self.request('api/login', {**body, 'deployment_profile': 'FULL'})[0], 400)
        self.source_identity.side_effect = Denied('UNTRUSTED_SOURCE')
        self.assertEqual(self.request('api/login', body)[0], 403)
        self.assert_no_providers()

    def test_authentication_operations_remain_post_only(self):
        self.factory.reset_mock()
        for operation in ('register', 'verify', 'login', 'request_reset', 'reset', 'logout'):
            for method in ('GET', 'HEAD'):
                with self.subTest(operation=operation, method=method):
                    self.assertEqual(self.request('api/' + operation, method=method)[0], 403)
        self.factory.assert_not_called()

    def test_registration_verification_and_login_remain_available(self):
        address, password = 'login-profile@example.com', 'fixture-password-123'
        status, _, raw = self.request('api/register', {'email': address, 'password': password})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {'status': 'CHECK_VERIFICATION_CHANNEL'})
        self.assertEqual(self.request('api/login', {'email': address, 'password': password})[0], 403)
        row = self.c.db.execute('SELECT * FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone()
        token = json.loads(self.c.decrypt(row['payload'], 'outbox:' + row['id']))['token']
        self.assertEqual(self.request('api/verify', {'token': token, 'password': password})[0], 200)
        self.assertEqual(self.request('api/verify', {'token': token, 'password': password})[0], 403)
        self.assertEqual(self.request('api/login', {'email': address, 'password': password})[0], 200)
        self.assert_no_providers()  # SMTP delivery itself is outside this HTTP test.

    def test_reset_remains_single_use_and_revokes_old_sessions(self):
        self.assertEqual(self.request('api/request_reset', {'email': 'owner@example.com'})[0], 200)
        row = self.c.db.execute("SELECT * FROM outbox WHERE kind='RESET' ORDER BY rowid DESC LIMIT 1").fetchone()
        token = json.loads(self.c.decrypt(row['payload'], 'outbox:' + row['id']))['token']
        body = {'token': token, 'password': 'changed-fixture-password-123'}
        self.assertEqual(self.request('api/reset', body)[0], 200)
        self.assertEqual(self.request('api/reset', body)[0], 403)
        self.assertEqual(self.request('api/me', headers=self.auth_headers())[0], 403)
        self.assertEqual(self.request('api/login', {'email': 'owner@example.com', 'password': body['password']})[0], 200)
        self.assert_no_providers()

    def test_missing_smtp_blocks_registration_and_reset_but_not_existing_login(self):
        self.mail_ready = False
        self.assertEqual(self.request('api/register', {'email': 'new@example.com', 'password': 'fixture-password-123'})[0], 503)
        self.assertEqual(self.request('api/request_reset', {'email': 'owner@example.com'})[0], 503)
        self.assertEqual(self.request('api/login', {'email': 'owner@example.com', 'password': 'correct-password-123'})[0], 200)

    def test_logout_clears_revoked_cookie_and_rejects_cross_origin(self):
        self.c.logout(self.users['owner']['token'])
        status, headers, _ = self.request('api/logout', {}, self.auth_headers())
        self.assertEqual(status, 200)
        self.assertIn('Max-Age=0', headers['Set-Cookie'])
        self.assertEqual(self.request('api/logout', {}, {**self.auth_headers(), 'Origin': 'https://foreign.invalid'})[0], 403)

    def test_login_failure_limits_remain_effective(self):
        for _ in range(9):
            self.assertEqual(self.request('api/login', {'email': 'owner@example.com', 'password': 'wrong-fixture-password'})[0], 403)
        self.assertEqual(self.request('api/login', {'email': 'owner@example.com', 'password': 'correct-password-123'})[0], 403)
        self.assert_no_providers()

    def test_default_full_profile_keeps_existing_project_me_response(self):
        self.switch_full()
        status, _, raw = self.request('api/me', headers=self.auth_headers())
        self.assertEqual(status, 200)
        value = json.loads(raw)
        self.assertEqual(set(value), {'user_id', 'projects', 'channels'})
        self.assertEqual(value['projects'][0]['id'], 'project-a')
        self.assertEqual(set(value['channels']), {'smtp', 'telegram', 'feishu', 'secretref', 'web_ai'})

    def test_explicit_full_keeps_business_read_and_write_routes(self):
        self.switch_full(explicit=True)
        self.assertEqual(self.request('api/checklist/project-a', headers=self.auth_headers())[0], 200)
        body = {'project': 'project-a', 'email': 'member@example.com', 'role': 'EDITOR'}
        self.assertEqual(self.request('api/invite', body, self.auth_headers())[0], 200)


class LoginProfileConstructionTests(unittest.TestCase):
    def test_unknown_profile_is_rejected_at_construction(self):
        for value in ('LOGIN_ONLY', '', None, {'profile': LOGIN}):
            with self.subTest(value=value), self.assertRaises((ValueError, Denied, TypeError)):
                http.App(Mock(), Providers({}), ORIGIN, ASSETS, deployment_profile=value)

    def test_pinned_origin_remains_required_with_login_profile(self):
        with self.assertRaisesRegex(ValueError, 'PINNED_ORIGIN_REQUIRED'):
            http.App(Mock(), Providers({}), 'https://foreign.invalid', ASSETS, deployment_profile=LOGIN)

    def test_serve_forwards_explicit_profile_without_real_socket_or_host_mutations(self):
        factory, providers = Mock(), Providers({})
        with patch.object(Path, 'exists', return_value=False), \
             patch.object(Path, 'is_symlink', return_value=False), \
             patch.object(http, 'CustomerUnixServer') as server, \
             patch.object(http, 'App') as app, \
             patch.object(os, 'chown') as chown, patch.object(os, 'chmod') as chmod, \
             patch.object(Path, 'unlink') as unlink, \
             patch.object(pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1234)), \
             patch.object(grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=1234)):
            http.serve(factory, providers, ASSETS, deployment_profile=LOGIN)
        self.assertEqual(app.call_args.args[:4], (factory, providers, ORIGIN, ASSETS))
        self.assertEqual(app.call_args.kwargs['deployment_profile'], LOGIN)
        server.return_value.serve_forever.assert_called_once_with()
        server.return_value.server_close.assert_called_once_with()
        chown.assert_called_once()
        chmod.assert_called_once()
        unlink.assert_called_once()


if __name__ == '__main__':
    unittest.main()
