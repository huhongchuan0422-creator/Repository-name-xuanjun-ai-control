"""Synthetic encrypted events and original PR122 DB/HTTP, no provider network."""
import base64
import copy
import hashlib
import http.client
import json
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import Mock

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from scripts.pr122_customer_core import Center, Denied, Unavailable, canonical
from scripts.pr122_customer_evidence import verify
from scripts.pr122_customer_profile import FULL, LOGIN_ONLY
from scripts.pr122_customer_providers import drain_message
from scripts.pr122_feishu_customer import (CustomerFeishuProviders, admit_scope,
    make_app, prepare_next_reply, require_scope)
from tests.test_pr122_customer_center import CustomerTests


class FeishuCustomerTests(CustomerTests):
    def setUp(self):
        super().setUp()
        self.scope = {'schema': 1, 'purpose': 'PLATFORM_CUSTOMER_SUPPORT',
            'app_id': 'cli_customer', 'tenant_key': 'tenant_customer',
            'allowed_sender_tenants': ['tenant_customer', 'tenant_partner'],
            'reserved_app_ids': {'owner_gateway': 'cli_owner',
                'development': 'cli_dev', 'authentication_notifications': 'cli_auth'}}
        self.config = {'feishu': {'app_id': 'cli_customer',
            'encrypt_key': 'synthetic-encrypt-key', 'verification_token': 'synthetic-verify-token',
            'app_secret': 'synthetic-app-secret'},
            'web_ai': {'provider': 'openai', 'model_key': 'approved-fixture'}}
        self.post = Mock(side_effect=AssertionError('Unconfigured provider network'))
        self.pv = self.providers()
        admit_scope(self.c, self.pv, deployment_profile=FULL)

    def providers(self, config=None, scope=None):
        return CustomerFeishuProviders(config or self.config, scope or self.scope,
            post=self.post, clock=lambda: self.now)

    def signed(self, document):
        iv = b'f' * 16
        key = hashlib.sha256(b'synthetic-encrypt-key').digest()
        pad = padding.PKCS7(128).padder()
        payload = pad.update(canonical(document)) + pad.finalize()
        enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        raw = canonical({'encrypt': base64.b64encode(iv + enc.update(payload) + enc.finalize()).decode()})
        stamp, nonce = str(self.now), 'synthetic_nonce_1234'
        signature = hashlib.sha256(stamp.encode() + nonce.encode() + b'synthetic-encrypt-key' + raw).hexdigest()
        return {'X-Lark-Request-Timestamp': stamp, 'X-Lark-Request-Nonce': nonce,
                'X-Lark-Signature': signature}, raw

    def event(self, text, *, mid='om_message_1', eid='event_1', subject='ou_customer'):
        return {'schema': '2.0', 'header': {'app_id': 'cli_customer',
            'tenant_key': 'tenant_customer', 'token': 'synthetic-verify-token',
            'event_type': 'im.message.receive_v1', 'event_id': eid,
            'create_time': str(self.now * 1000)}, 'event': {
                'sender': {'sender_type': 'user', 'sender_id': {'open_id': subject},
                           'tenant_key': 'tenant_customer'},
                'message': {'message_id': mid, 'chat_type': 'p2p',
                            'message_type': 'text', 'content': json.dumps({'text': text})}}}

    def ingest(self, document):
        value = self.pv.feishu(*self.signed(document))
        return self.c.channel_event('FEISHU', *value, provider_occurred_at=value.occurred_at)

    def bind(self, *, uid=None, pid='project-a', subject='ou_customer', mid='om_bind'):
        uid = uid or self.owner
        t = self.c.binding_challenge(uid, pid, 'FEISHU', subject)['challenge']
        self.ingest(self.event('/bind ' + t, mid=mid, eid=mid, subject=subject))
        pending = self.c.pending_links(uid, pid)[0]
        self.c.confirm_link(uid, pid, pending['id'])

    def source(self):
        self.bind()
        return self.ingest(self.event('/project project-a hello from Feishu'))

    def step(self, rpc):
        return prepare_next_reply(self.c, self.pv, deployment_profile=FULL, rpc=rpc)

    def test_original_customer_identity_and_evidence_used_for_ai_and_outbox(self):
        source = self.source()
        rpc = Mock(return_value='合成回复，仅供测试。')
        result = self.step(rpc)
        self.assertEqual(result['state'], 'ANSWERED')
        self.assertEqual(result['delivery_status'], 'PENDING')
        context = rpc.call_args.args[1]
        self.assertEqual(context['customer_id'], 'customer-a')
        self.assertEqual(context['tenant_id'], 'tenant-a')
        self.assertEqual(context['project_id'], 'project-a')
        self.assertEqual(context['user_id'], self.owner)
        self.assertEqual(context['message_id'], source['id'])
        self.assertEqual(context['body'], 'hello from Feishu')
        records, _ = verify(self.c, 'project-a')
        by_id = {r['evidence']['message_id']: r for r in records}
        reply = by_id[result['result_id']]['evidence']
        self.assertEqual(reply['sender_role'], 'AI')
        self.assertEqual(reply['related_message_id'], source['id'])
        outbound = by_id[result['outbound_id']]['evidence']
        self.assertEqual(outbound['related_message_id'], result['result_id'])
        self.assertEqual(outbound['source_channel'], 'FEISHU')
        self.assertEqual(self.step(rpc), {'state': 'IDLE'})
        rpc.assert_called_once()
        self.c.check_integrity()

    def test_feishu_api_acceptance_is_not_recipient_delivery(self):
        self.source()
        self.step(Mock(return_value='synthetic reply'))
        self.post.side_effect = [
            {'code': 0, 'tenant_access_token': 'synthetic-access-token'},
            {'code': 0, 'data': {'message_id': 'om_sent'}}]
        self.assertEqual(drain_message(self.c, self.pv), {'status': 'ACCEPTED', 'provider_ref': 'om_sent'})
        self.assertEqual(self.post.call_args.args[1]['receive_id'], 'ou_customer')
        self.assertEqual(self.post.call_args.args[1]['content'], json.dumps({'text': 'synthetic reply'}, ensure_ascii=False))
        self.assertEqual(drain_message(self.c, self.pv), {'pending': False})
        self.assertEqual(self.post.call_count, 2)

    def test_message_id_deduplicates_different_event_ids_across_reopen(self):
        self.source()
        document = self.event('/project project-a hello from Feishu', eid='event_retry')
        self.c.db.close()
        self.c = Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now, mail_ready=True)
        self.assertEqual(self.ingest(document), {'duplicate': True, 'saved': True})
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM messages WHERE channel='FEISHU'").fetchone()[0], 1)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0], 4)

    def test_binding_requires_provider_then_authenticated_web_confirmation(self):
        token = self.c.binding_challenge(self.owner, 'project-a', 'FEISHU', 'ou_customer')['challenge']
        self.ingest(self.event('/bind ' + token, mid='om_bind'))
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM links').fetchone()[0], 0)
        with self.assertRaises(Denied):
            self.ingest(self.event('/project project-a denied', mid='om_unconfirmed'))
        pending = self.c.pending_links(self.owner, 'project-a')[0]
        self.c.confirm_link(self.owner, 'project-a', pending['id'])
        self.assertEqual(self.ingest(self.event('/project project-a allowed'))['status'], 'ARCHIVED')

    def test_wrong_open_id_cannot_bind_or_address_another_customer(self):
        token = self.c.binding_challenge(self.owner, 'project-a', 'FEISHU', 'ou_customer')['challenge']
        with self.assertRaises(Denied):
            self.ingest(self.event('/bind ' + token, subject='ou_attacker', mid='om_attacker'))
        self.bind()
        with self.assertRaises(Denied):
            self.ingest(self.event('/project project-a private', subject='ou_attacker'))
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM messages').fetchone()[0], 0)

    def test_tenant_app_sender_bot_group_and_attachment_fail_before_crm_write(self):
        transforms = [
            lambda d: d['header'].update(app_id='cli_owner'),
            lambda d: d['header'].update(tenant_key='tenant_other'),
            lambda d: d['event']['sender'].update(tenant_key='tenant_other'),
            lambda d: d['event']['sender'].update(sender_type='app'),
            lambda d: d['event']['message'].update(chat_type='group'),
            lambda d: d['event']['message'].update(message_type='file'),
            lambda d: d['event']['message'].pop('message_id'),
            lambda d: d.update(schema='1.0'),
        ]
        for transform in transforms:
            d = self.event('/project project-a blocked')
            transform(d)
            with self.subTest(transform=transform), self.assertRaises(Denied):
                self.pv.feishu(*self.signed(d))
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM events').fetchone()[0], 0)

    def test_reserved_owner_dev_auth_bots_cannot_be_customer_app(self):
        for app_id in self.scope['reserved_app_ids'].values():
            with self.subTest(app_id=app_id), self.assertRaises(Unavailable):
                self.providers({**self.config, 'feishu': {**self.config['feishu'], 'app_id': app_id}},
                    {**self.scope, 'app_id': app_id})
        for missing in self.scope:
            scope = copy.deepcopy(self.scope)
            del scope[missing]
            with self.subTest(missing=missing), self.assertRaises(Unavailable):
                self.providers(scope=scope)

    def test_scope_is_pinned_not_silently_rebound_and_existing_history_not_adopted(self):
        self.assertEqual(admit_scope(self.c, self.pv, deployment_profile=FULL), {'state': 'SCOPE_PIN_REUSED'})
        other = self.providers(scope={**self.scope, 'tenant_key': 'tenant_new'})
        with self.assertRaises(Denied):
            require_scope(self.c, other)
        with self.assertRaises(Denied):
            admit_scope(self.c, other, deployment_profile=FULL)
        self.bind()
        self.c.db.execute("DELETE FROM settings WHERE k='feishu_customer_app_scope_v1'")
        with self.assertRaisesRegex(Denied, 'HISTORY'):
            admit_scope(self.c, self.pv, deployment_profile=FULL)

    def test_mutable_input_config_cannot_change_app_and_runtime_drift_is_rejected(self):
        self.config['feishu']['app_id'] = 'cli_owner'
        self.scope['app_id'] = 'cli_owner'
        self.pv.feishu(*self.signed(self.event('hello')))
        self.pv.config['feishu']['app_id'] = 'cli_owner'
        with self.assertRaises(Denied):
            self.pv.feishu(*self.signed(self.event('hello')))

    def test_original_signature_and_expiration_guards_preserved(self):
        headers, raw = self.signed(self.event('hello'))
        with self.assertRaises(Denied):
            self.pv.feishu({**headers, 'X-Lark-Signature': '0' * 64}, raw)
        self.now += 301
        with self.assertRaises(Denied):
            self.pv.feishu(headers, raw)

    def test_url_verification_is_challenge_only_not_identity(self):
        headers, raw = self.signed({'type': 'url_verification',
            'token': 'synthetic-verify-token', 'challenge': 'synthetic-challenge'})
        self.assertEqual(self.pv.feishu(headers, raw), {'challenge': 'synthetic-challenge'})
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM events').fetchone()[0], 0)
        self.assertFalse(self.pv.status()['feishu']['accepted'])

    def test_login_only_rejects_before_factory_or_model(self):
        factory, rpc = Mock(), Mock()
        with self.assertRaises(Denied):
            make_app(factory, self.pv, 'https://wenwenwenyiyiyi.work', '.', deployment_profile=LOGIN_ONLY)
        factory.assert_not_called()
        with self.assertRaises(Denied):
            prepare_next_reply(None, self.pv, deployment_profile=LOGIN_ONLY, rpc=rpc)
        rpc.assert_not_called()

    def test_ai_timeout_and_process_interrupt_keep_original_job_unknown(self):
        self.source()
        self.assertEqual(self.step(Mock(side_effect=TimeoutError('synthetic'))), {'state': 'UNKNOWN'})
        self.c.db.close()
        self.c = Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now, mail_ready=True)
        rpc = Mock()
        self.assertEqual(self.step(rpc), {'state': 'IDLE'})
        rpc.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT state FROM ai_jobs').fetchone()[0], 'UNKNOWN')
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM messages WHERE status='PENDING'").fetchone()[0], 0)

    def test_hard_interruption_after_claim_never_replays_model(self):
        self.source()
        with self.assertRaises(KeyboardInterrupt):
            self.step(Mock(side_effect=KeyboardInterrupt()))
        rpc = Mock()
        self.assertEqual(self.step(rpc), {'state': 'IDLE'})
        rpc.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT state FROM ai_jobs').fetchone()[0], 'UNKNOWN')

    def test_revoke_or_rebind_during_model_does_not_queue_reply(self):
        self.source()
        def rpc(config, context):
            self.c.unlink(self.owner, 'project-a', 'FEISHU')
            return 'must not send'
        self.assertEqual(self.step(rpc), {'state': 'UNKNOWN'})
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM messages WHERE status='PENDING'").fetchone()[0], 0)

    def test_member_revocation_before_model_keeps_zero_model_calls(self):
        token = self.c.invite(self.owner, 'project-a', 'member@example.com', 'EDITOR')['invitation']
        self.c.accept_invite(self.member, token)
        self.bind(uid=self.member)
        self.ingest(self.event('/project project-a member message'))
        self.c.revoke(self.owner, 'project-a', self.member)
        rpc = Mock()
        with self.assertRaises(Denied):
            self.step(rpc)
        rpc.assert_not_called()

    def test_provider_missing_does_not_consume_claim(self):
        self.source()
        self.pv.config.pop('web_ai')
        rpc = Mock()
        self.assertEqual(self.step(rpc), {'state': 'PENDING_PROVIDER'})
        rpc.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM ai_jobs').fetchone()[0], 0)

    def test_outbound_timeout_unknown_is_not_resent_after_restart(self):
        self.source()
        self.step(Mock(return_value='synthetic reply'))
        self.post.side_effect = TimeoutError('synthetic unknown')
        self.assertEqual(drain_message(self.c, self.pv), {'status': 'UNKNOWN'})
        self.c.db.close()
        self.c = Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now, mail_ready=True)
        self.assertEqual(drain_message(self.c, self.pv), {'pending': False})
        self.post.assert_called_once()

    def test_second_connection_cannot_reclaim_inflight_model(self):
        self.source()
        other = Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now, mail_ready=True)
        self.addCleanup(other.db.close)
        second_rpc = Mock()
        def rpc(config, context):
            self.assertEqual(prepare_next_reply(other, self.pv,
                deployment_profile=FULL, rpc=second_rpc), {'state': 'IDLE'})
            return 'one reply'
        self.assertEqual(self.step(rpc)['state'], 'ANSWERED')
        second_rpc.assert_not_called()
        self.assertEqual(other.db.execute('SELECT count(*) FROM ai_jobs').fetchone()[0], 1)

    def test_existing_http_route_archives_only_without_model_in_callback(self):
        self.bind()
        app = make_app(lambda: Center(self.root, {'v1': self.key}, 'v1',
            clock=lambda: self.now, mail_ready=True), self.pv,
            'https://wenwenwenyiyiyi.work', Path('.'), deployment_profile=FULL)
        server = HTTPServer(('127.0.0.1', 0), app.handler())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            headers, raw = self.signed(self.event('/project project-a via real local HTTP'))
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            conn.request('POST', '/customer/center/webhooks/feishu', raw,
                {**headers, 'Host': 'wenwenwenyiyiyi.work', 'Content-Type': 'application/json'})
            result = conn.getresponse()
            self.assertEqual(result.status, 200)
            self.assertEqual(json.loads(result.read()), {'ok': True})
            conn.close()
            self.post.assert_not_called()
            self.assertEqual(self.c.db.execute('SELECT count(*) FROM ai_jobs').fetchone()[0], 0)
            self.assertEqual(self.c.messages(self.owner, 'project-a')[0]['body'], 'via real local HTTP')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


# Reuse the fixture, not inherited tests/duplicate counts.
for _name in CustomerTests.__dict__:
    if _name.startswith('test_') and _name not in FeishuCustomerTests.__dict__:
        setattr(FeishuCustomerTests, _name, None)
