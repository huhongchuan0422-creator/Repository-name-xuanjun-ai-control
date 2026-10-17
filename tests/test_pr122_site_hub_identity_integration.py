"""Real HTTP handler/Core/SQLite integration with in-memory HTTP transport.

Synthetic identities, keys, documents and provider events only. No sockets,
external mail/channel calls, real accounts, production inputs or server changes.
"""
import base64
import io
import json
from http.client import HTTPResponse
from types import SimpleNamespace
from unittest.mock import patch

from scripts.pr122_customer_core import Center, Denied
from scripts.pr122_customer_http import App, COOKIE
from scripts.pr122_customer_providers import Providers
from tests.test_pr122_customer_center import CustomerTests
from tests.test_pr122_customer_providers import ProviderTests


class MemoryConnection:
    def __init__(self, request):
        self.request = request
        self.output = bytearray()

    def makefile(self, mode, *args):
        return io.BytesIO(self.request)

    def sendall(self, data):
        self.output.extend(data)

    def settimeout(self, timeout):
        pass


class IdentityIntegrationTests(CustomerTests):
    def setUp(self):
        super().setUp()
        self.providers = Providers({})
        self.app = App(
            lambda: Center(self.root, {'v1': self.key}, 'v1',
                           clock=lambda: self.now, mail_ready=True,
                           scanner=lambda raw: True),
            self.providers, 'https://wenwenwenyiyiyi.work',
            'deploy/pr122-customer-center/ui',
            source_identity=lambda connection, headers: 'memory-fixture')

    def request(self, operation, body=None, auth=None, extra_headers=None):
        raw = b'' if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = {'Host': 'wenwenwenyiyiyi.work', 'Connection': 'close'}
        if body is not None:
            headers.update({'Origin': 'https://wenwenwenyiyiyi.work',
                            'Content-Type': 'application/json',
                            'Content-Length': str(len(raw))})
        if auth:
            headers.update({'Cookie': COOKIE + '=' + auth['token'],
                            'X-CSRF-Token': auth['csrf']})
        headers.update(extra_headers or {})
        prefix = '/customer/center/' if operation.startswith('webhooks/') else '/customer/center/api/'
        start = ('POST' if body is not None else 'GET') + ' ' + prefix + operation + ' HTTP/1.1\r\n'
        wire = (start + ''.join(k + ': ' + v + '\r\n' for k, v in headers.items()) + '\r\n').encode() + raw
        connection = MemoryConnection(wire)
        # Any accidental network expansion fails this test, rather than falling
        # back from the in-memory transport to an actual listener/provider.
        with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            self.app.handler()(connection, ('127.0.0.1', 0), SimpleNamespace(server_name='fixture', server_port=0))
        response = HTTPResponse(MemoryConnection(bytes(connection.output)))
        response.begin()
        data = response.read()
        return response.status, dict(response.getheaders()), json.loads(data)

    def challenge_token(self, kind):
        row = self.c.db.execute('SELECT * FROM outbox WHERE kind=? ORDER BY rowid DESC LIMIT 1', (kind,)).fetchone()
        return json.loads(self.c.decrypt(row['payload'], 'outbox:' + row['id']))['token']

    def test_http_reset_revokes_all_sessions_and_confirmed_channel(self):
        owner = self.users['owner']
        second = self.c.login('owner@example.com', 'correct-password-123')
        challenge = self.c.binding_challenge(self.owner, 'project-a', 'TELEGRAM', '123')['challenge']
        self.c.channel_event('TELEGRAM', 'bind-before-reset', '123', '/bind ' + challenge)
        self.c.confirm_link(self.owner, 'project-a', self.c.pending_links(self.owner, 'project-a')[0]['id'])
        self.assertEqual(self.request('request_reset', {'email': 'owner@example.com'})[0], 200)
        token = self.challenge_token('RESET')
        self.assertEqual(self.request('reset', {'token': token, 'password': 'replacement-password-123'})[0], 200)
        for session in (owner, second):
            self.assertEqual(self.request('me', auth=session)[0], 403)
        with self.assertRaises(Denied):
            self.c.channel_event('TELEGRAM', 'message-after-reset', '123', '/project project-a forbidden')
        self.assertEqual(self.request('reset', {'token': token, 'password': 'another-password-123'})[0], 403)
        self.assertEqual(self.request('login', {'email': 'owner@example.com', 'password': 'correct-password-123'})[0], 403)
        status, headers, result = self.request('login', {'email': 'owner@example.com', 'password': 'replacement-password-123'})
        self.assertEqual(status, 200)
        self.assertNotIn('token', result)
        self.assertIn('Secure; HttpOnly; SameSite=Strict', headers['Set-Cookie'])
        self.c.check_integrity()

    def test_http_registration_has_no_projects_without_authority(self):
        address = 'new-fixture@example.com'
        self.assertEqual(self.request('register', {'email': address, 'password': 'initial-password-123'})[2], {'status': 'CHECK_VERIFICATION_CHANNEL'})
        token = self.challenge_token('VERIFY')
        self.assertEqual(self.request('login', {'email': address, 'password': 'initial-password-123'})[0], 403)
        self.assertEqual(self.request('verify', {'token': token, 'password': 'verified-password-123'})[0], 200)
        self.assertEqual(self.request('login', {'email': address, 'password': 'initial-password-123'})[0], 403)
        session = self.c.login(address, 'verified-password-123')
        self.assertEqual(self.request('me', auth=session)[2]['projects'], [])
        self.assertEqual(self.request('checklist/project-a', auth=session)[0], 403)
        self.assertEqual(self.request('verify', {'token': token, 'password': 'verified-password-123'})[0], 403)

    def test_http_viewer_editor_and_revocation_keep_identity_separate(self):
        invite = self.request('invite', {'project': 'project-a', 'email': 'member@example.com', 'role': 'VIEWER'}, self.users['owner'])
        self.assertEqual(invite[0], 200)
        self.assertEqual(self.request('accept_invite', {'invitation': invite[2]['invitation']}, self.users['member'])[0], 200)
        self.assertEqual(self.request('checklist/project-a', auth=self.users['member'])[0], 200)
        payload = {'project': 'project-a', 'item': 'license', 'revision': 0, 'kind': 'DOCUMENT', 'content': base64.b64encode(b'%PDF-synthetic').decode(), 'expires': None}
        self.assertEqual(self.request('save', payload, self.users['member'])[0], 403)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects').fetchone()[0], 0)
        invite = self.request('invite', {'project': 'project-a', 'email': 'member@example.com', 'role': 'EDITOR'}, self.users['owner'])
        self.assertEqual(self.request('accept_invite', {'invitation': invite[2]['invitation']}, self.users['member'])[0], 200)
        self.assertEqual(self.request('save', payload, self.users['member'])[0], 200)
        self.assertEqual(self.request('revoke', {'project': 'project-a', 'user_id': self.member}, self.users['owner'])[0], 200)
        self.assertEqual(self.request('me', auth=self.users['member'])[0], 200)
        self.assertEqual(self.request('me', auth=self.users['member'])[2]['projects'], [])
        self.assertEqual(self.request('checklist/project-a', auth=self.users['member'])[0], 403)
        self.c.check_integrity()

    def test_http_material_review_separation_and_incremental_versions(self):
        payload = {'project': 'project-a', 'item': 'license', 'revision': 0, 'kind': 'DOCUMENT', 'content': base64.b64encode(b'%PDF-synthetic-authorization').decode(), 'expires': None}
        self.assertEqual(self.request('save', payload, self.users['reviewer'])[0], 403)
        saved = self.request('save', payload, self.users['owner'])
        self.assertEqual(saved[0], 200)
        transition = {'project': 'project-a', 'item': 'license', 'revision': saved[2]['revision'], 'action': 'submit', 'reason': ''}
        submitted = self.request('transition', transition, self.users['owner'])
        self.assertEqual(submitted[0], 200)
        transition.update(revision=submitted[2]['revision'], action='begin_review')
        self.assertEqual(self.request('transition', transition, self.users['owner'])[0], 403)
        review = self.request('transition', transition, self.users['reviewer'])
        self.assertEqual(review[0], 200)
        transition.update(revision=review[2]['revision'], action='approve', reason='Synthetic independent verification')
        accepted = self.request('transition', transition, self.users['reviewer'])
        self.assertEqual(accepted[0], 200)
        self.assertEqual(accepted[2]['state'], 'ACCEPTED')
        self.assertEqual(self.request('transition', transition, self.users['reviewer'])[0], 409)
        payload.update(revision=accepted[2]['revision'], content=base64.b64encode(b'%PDF-synthetic-replacement').decode())
        self.assertEqual(self.request('save', payload, self.users['owner'])[0], 200)
        items = self.request('checklist/project-a', auth=self.users['owner'])[2]['items']
        item = next(item for item in items if item['id'] == 'license')
        self.assertEqual(item['accepted_revision'], accepted[2]['accepted_revision'])
        self.assertEqual(item['state'], 'PARTIAL')
        self.assertEqual(len(item['versions']), 5)
        self.c.check_integrity()

    def test_authority_subject_change_is_atomic_and_preserves_existing_grants(self):
        original = self.request('me', auth=self.users['owner'])[2]['projects']
        revision = self.c.db.execute("SELECT v FROM settings WHERE k='authority_revision'").fetchone()[0]
        with self.assertRaises(Denied):
            self.imported(2, [{**self.p, 'tenant': 'different-tenant', 'customer': 'different-customer', 'owner_email': 'other@example.com'}])
        self.assertEqual(self.request('me', auth=self.users['owner'])[2]['projects'], original)
        self.assertEqual(self.request('checklist/project-a', auth=self.users['other'])[0], 403)
        self.assertEqual(self.c.db.execute("SELECT v FROM settings WHERE k='authority_revision'").fetchone()[0], revision)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM project_history').fetchone()[0], 1)
        self.c.check_integrity()

    def channel_http_roundtrip(self, channel):
        subject = '123' if channel == 'TELEGRAM' else 'ou_user'
        self.providers.config = {'telegram': {'webhook_secret': 'w' * 32},
                                 'feishu': {'encrypt_key': 'encrypt-key', 'verification_token': 'verification-token', 'app_id': 'app-id'}}
        self.providers.clock = lambda: self.now
        sequence = 0

        def callback(text, invalid_signature=False, event_id=None):
            nonlocal sequence
            sequence += 1
            if channel == 'TELEGRAM':
                body = {'update_id': event_id or sequence, 'message': {
                    'from': {'id': 123, 'is_bot': False}, 'chat': {'id': 123, 'type': 'private'},
                    'date': self.now, 'text': text}}
                headers = {'X-Telegram-Bot-Api-Secret-Token': ('x' if invalid_signature else 'w') * 32}
            else:
                event = ProviderTests.event(self)
                event['header']['event_id'] = 'fixture_' + str(event_id or sequence)
                event['event']['message']['content'] = json.dumps({'text': text})
                headers, body = ProviderTests.signed(self, event)
                if invalid_signature:
                    headers['X-Lark-Signature'] = '0' * 64
            return self.request('webhooks/' + channel.lower(), body, extra_headers=headers)

        challenge = self.request('bind', {'project': 'project-a', 'channel': channel, 'subject': subject}, self.users['owner'])[2]['challenge']
        self.assertEqual(callback('/bind ' + challenge, invalid_signature=True)[0], 403)
        self.assertEqual(self.c.pending_links(self.owner, 'project-a'), [])
        status, _, response = callback('/bind ' + challenge)
        self.assertEqual((status, response), (200, {'ok': True}))
        self.assertEqual(callback('/project project-a premature')[0], 403)
        pending = self.request('pending_links/project-a', auth=self.users['owner'])[2]['links']
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.request('confirm_link', {'project': 'project-a', 'challenge_id': pending[0]['id']}, self.users['other'])[0], 403)
        self.assertEqual(self.request('confirm_link', {'project': 'project-a', 'challenge_id': pending[0]['id']}, self.users['owner'])[0], 200)
        self.assertEqual(callback('/project project-a integration-message', event_id=99)[0], 200)
        self.assertEqual(callback('/project project-a integration-message', event_id=99)[0], 200)
        messages = self.request('messages/project-a', auth=self.users['owner'])[2]['messages']
        self.assertEqual([(m['channel'], m['body']) for m in messages], [(channel, 'integration-message')])
        self.assertEqual(callback('/project project-other forbidden')[0], 403)
        self.assertEqual(self.request('unlink', {'project': 'project-a', 'channel': channel}, self.users['owner'])[0], 200)
        self.assertEqual(callback('/project project-a forbidden-after-unlink')[0], 403)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM messages').fetchone()[0], 1)
        self.c.check_integrity()

    def test_signed_telegram_http_identity_project_and_replay_roundtrip(self):
        self.channel_http_roundtrip('TELEGRAM')

    def test_encrypted_feishu_http_identity_project_and_replay_roundtrip(self):
        self.channel_http_roundtrip('FEISHU')

    def test_authority_withdrawal_denies_existing_session_and_channels(self):
        challenge = self.c.binding_challenge(self.owner, 'project-a', 'TELEGRAM', '123')['challenge']
        self.c.channel_event('TELEGRAM', 'authority-bind', '123', '/bind ' + challenge)
        self.c.confirm_link(self.owner, 'project-a', self.c.pending_links(self.owner, 'project-a')[0]['id'])
        self.imported(2, [])
        self.assertEqual(self.request('me', auth=self.users['owner'])[2]['projects'], [])
        self.assertEqual(self.request('checklist/project-a', auth=self.users['owner'])[0], 403)
        with self.assertRaises(Denied):
            self.c.channel_event('TELEGRAM', 'withdrawn-message', '123', '/project project-a forbidden')
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM messages").fetchone()[0], 0)
        self.c.check_integrity()


# Reuse established fixture setup, never re-run its already-covered core tests.
for _name in CustomerTests.__dict__:
    if _name.startswith('test_'):
        setattr(IdentityIntegrationTests, _name, None)

if __name__ == '__main__':
    import unittest
    unittest.main()
