"""Real in-memory HTTP privacy boundaries using synthetic, offline fixtures."""
import hashlib
import json
import unittest
from unittest.mock import Mock

from scripts.pr122_customer_core import Center
from scripts.pr122_customer_http import App
from scripts.pr122_customer_privacy import POLICY_FIELDS
from scripts.pr122_customer_providers import Providers
from tests import test_pr122_customer_center as customer_fixtures
from tests import test_pr122_site_hub_identity_integration as http_fixtures


class PrivacyHTTPTests(unittest.TestCase):
    imported = customer_fixtures.CustomerTests.imported
    save = customer_fixtures.CustomerTests.save
    request = http_fixtures.IdentityIntegrationTests.request

    def setUp(self):
        customer_fixtures.CustomerTests.setUp(self)
        self.policy_callback = None
        self.processing_callback = None
        self.policy = {field: field + '-fixture-v1' for field in POLICY_FIELDS}
        self.policy['notice_text'] = '合成测试告知：记录查询与更正申请。\nThis is fixture text, not an approved policy.'
        self.policy['notice_sha256'] = hashlib.sha256(self.policy['notice_text'].encode()).hexdigest()
        self.app = App(
            lambda: Center(self.root, {'v1': self.key}, 'v1',
                           clock=lambda: self.now, mail_ready=True,
                           scanner=lambda raw: True,
                           privacy_policy_context=self.policy_callback,
                           privacy_processing_context=self.processing_callback),
            Providers({}), 'https://wenwenwenyiyiyi.work',
            'deploy/pr122-customer-center/ui',
            source_identity=lambda connection, headers: 'privacy-memory-fixture')

    def body(self, key='privacy_key_000001', **changes):
        return {'project': 'project-a', 'kind': 'QUERY', 'text': 'Synthetic private request',
                'idempotency_key': key, 'request_id': None, 'expected_revision': 0, **changes}

    def submit(self, key='privacy_key_000001', auth=None, **changes):
        return self.request('privacy_request', self.body(key, **changes),
                            auth or self.users['owner'])

    def authorize_member(self):
        token = self.c.invite(self.owner, 'project-a', 'member@example.com', 'EDITOR')['invitation']
        self.c.accept_invite(self.member, token)

    def receipts(self):
        return [tuple(row) for row in self.c.db.execute('SELECT * FROM privacy_receipts ORDER BY seq')]

    def protected_processing(self, request):
        return {'requester_id': self.owner, 'project_id': 'project-a',
                'tenant_id': 'tenant-a', 'customer_id': 'customer-a',
                'request_id': request['request_id'], 'revision': request['revision'],
                'status': 'CLOSED', 'status_ref': 'status-fixture-v1',
                'actor_ref': 'protected-processor-fixture', 'occurred_at': self.now,
                'outcome_ref': 'outcome-fixture-v1'}

    def test_unknown_default_is_private_no_store_and_does_not_imply_consent(self):
        status, headers, result = self.request('privacy/project-a', auth=self.users['owner'])
        self.assertEqual(status, 200)
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertEqual(result['policy_status'], 'UNKNOWN')
        self.assertEqual(result['consent_status'], 'UNKNOWN')
        self.assertEqual(result['retention_compliance'], 'UNKNOWN')
        self.assertEqual(result['processing_status'], 'UNKNOWN')
        self.assertFalse(result['execution_enabled'])
        self.assertTrue(all(value is None for value in result['policy'].values()))
        self.assertEqual(result['receipts'], [])
        self.assertEqual(result['processing'], [])
        self.assertEqual(result['assurance'], 'LOCAL_RECEIPTS_NOT_LEGAL_DETERMINATION')

    def test_readable_notice_ack_decline_and_idempotency_bind_current_protected_hash(self):
        self.policy_callback = Mock(return_value=dict(self.policy))
        status, _, result = self.request('privacy/project-a', auth=self.users['owner'])
        self.assertEqual(status, 200)
        self.assertEqual(result['policy']['notice_text'], self.policy['notice_text'])
        self.assertEqual(hashlib.sha256(result['policy']['notice_text'].encode()).hexdigest(),
                         result['policy']['notice_sha256'])
        for index, choice in enumerate(('ACKNOWLEDGED', 'DECLINED')):
            body = {'project': 'project-a', 'policy_ref': self.policy['notice_ref'],
                    'notice_sha256': self.policy['notice_sha256'], 'decision': choice,
                    'idempotency_key': 'notice_key_00000' + str(index)}
            first = self.request('privacy_acknowledge', body, self.users['owner'])
            replay = self.request('privacy_acknowledge', body, self.users['owner'])
            self.assertEqual(first[0], 200)
            self.assertEqual(first[2], replay[2])
            self.assertEqual(first[2]['decision'], choice)
            self.assertEqual(first[2]['policy'], self.policy)
            self.assertEqual(first[2]['status'], 'RECORDED_NOT_LEGAL_ACCEPTANCE')
            self.assertEqual(first[2]['consent_status'], 'UNKNOWN')
            conflict = {**body, 'decision': 'DECLINED' if choice == 'ACKNOWLEDGED' else 'ACKNOWLEDGED'}
            self.assertEqual(self.request('privacy_acknowledge', conflict, self.users['owner'])[0], 409)
        self.assertEqual(len(self.receipts()), 2)
        self.policy_callback.assert_called_with(self.owner, 'project-a')

    def test_forged_or_inconsistent_notice_is_rejected_without_receipt(self):
        body = {'project': 'project-a', 'policy_ref': self.policy['notice_ref'],
                'notice_sha256': self.policy['notice_sha256'], 'decision': 'ACKNOWLEDGED',
                'idempotency_key': 'notice_key_000001'}
        self.assertEqual(self.request('privacy_acknowledge', body, self.users['owner'])[0], 403)
        self.policy_callback = lambda uid, pid: dict(self.policy)
        for change in ({'policy_ref': 'forged-policy'}, {'notice_sha256': 'f' * 64}):
            self.assertEqual(self.request('privacy_acknowledge', {**body, **change}, self.users['owner'])[0], 403)
        self.policy_callback = lambda uid, pid: {**self.policy, 'notice_text': 'Changed without matching hash'}
        self.assertEqual(self.request('privacy/project-a', auth=self.users['owner'])[0], 403)
        self.assertEqual(self.request('privacy_acknowledge', body, self.users['owner'])[0], 403)
        self.assertEqual(self.receipts(), [])

    def test_requests_are_requester_private_even_from_owner_and_reviewer(self):
        self.authorize_member()
        secret = 'member-only privacy concern fixture'
        response = self.submit(auth=self.users['member'], text=secret)
        self.assertEqual(response[0], 200)
        row = response[2]
        self.assertEqual(row['requester_id'], self.member)
        self.assertEqual(row['status'], 'RECEIVED')
        own = self.request('privacy/project-a', auth=self.users['member'])
        self.assertEqual([receipt['text'] for receipt in own[2]['receipts']], [secret])
        for name in ('owner', 'reviewer'):
            other = self.request('privacy/project-a', auth=self.users[name])
            self.assertEqual(other[0], 200)
            self.assertEqual(other[2]['receipts'], [])
            self.assertNotIn(secret, json.dumps(other[2]))
            amendment = self.submit('cross_actor_key_001', auth=self.users[name],
                                    request_id=row['request_id'], expected_revision=1,
                                    text='must not amend another requester')
            self.assertEqual(amendment[0], 403)
        self.assertEqual(len(self.receipts()), 1)

    def test_unified_export_contains_only_current_requesters_privacy_receipts(self):
        self.authorize_member()
        private_text = {'member': 'member-only unified-export privacy fixture',
                        'owner': 'owner-only unified-export privacy fixture'}
        created = {}
        for name in ('member', 'owner'):
            # The same idempotency key is independently scoped to each requester.
            response = self.submit(auth=self.users[name], text=private_text[name])
            self.assertEqual(response[0], 200)
            created[name] = response[2]
        self.assertNotEqual(created['member']['id'], created['owner']['id'])
        before = self.receipts()
        for name in ('member', 'owner', 'reviewer'):
            with self.subTest(requester=name):
                own_status = self.request('privacy/project-a', auth=self.users[name])
                self.assertEqual(own_status[0], 200)
                status, headers, exported = self.request('evidence/project-a', auth=self.users[name])
                self.assertEqual(status, 200)
                self.assertIn('no-store', headers['Cache-Control'])
                self.assertEqual(exported['privacy'], own_status[2])
                expected = [created[name]] if name in created else []
                self.assertEqual(exported['privacy']['receipts'], expected)
                self.assertEqual(exported['export_receipt']['actor_id'], self.users[name]['user_id'])
                self.assertFalse(exported['privacy']['execution_enabled'])
                for other, text in private_text.items():
                    if other != name:
                        self.assertNotIn(text, json.dumps(exported))
                        self.assertNotIn(created[other]['id'], json.dumps(exported))
        self.assertEqual(self.receipts(), before)

    def test_request_idempotency_amendment_revision_and_old_retry(self):
        first = self.submit()
        self.assertEqual(first[0], 200)
        row = first[2]
        amended = self.submit('privacy_key_000002', request_id=row['request_id'],
                              expected_revision=1, text='Amended private request')
        self.assertEqual(amended[0], 200)
        self.assertEqual(amended[2]['revision'], 2)
        self.assertEqual(self.submit()[2], row)
        self.assertEqual(self.submit(text='changed payload with reused key')[0], 409)
        self.assertEqual(self.submit('privacy_key_000003', request_id=row['request_id'], expected_revision=1)[0], 409)
        self.assertEqual(self.submit('privacy_key_000003', request_id=row['request_id'], expected_revision=2,
                                     kind='DELETION')[0], 409)
        self.assertEqual(len(self.receipts()), 2)

    def test_forged_actor_tenant_processing_fields_are_rejected_at_http_boundary(self):
        self.policy_callback = lambda uid, pid: dict(self.policy)
        base_ack = {'project': 'project-a', 'policy_ref': self.policy['notice_ref'],
                    'notice_sha256': self.policy['notice_sha256'], 'decision': 'ACKNOWLEDGED',
                    'idempotency_key': 'notice_key_000001'}
        for field, value in (('requester_id', self.other), ('actor_id', self.reviewer),
                             ('tenant_id', 'tenant-b'), ('customer_id', 'customer-b'),
                             ('status', 'CLOSED'), ('processing_status', 'CLOSED'),
                             ('execution_enabled', True)):
            with self.subTest(field=field):
                self.assertEqual(self.request('privacy_request', {**self.body(), field: value}, self.users['owner'])[0], 400)
                self.assertEqual(self.request('privacy_acknowledge', {**base_ack, field: value}, self.users['owner'])[0], 400)
        missing = self.body()
        missing.pop('expected_revision')
        self.assertEqual(self.request('privacy_request', missing, self.users['owner'])[0], 400)
        self.assertEqual(self.receipts(), [])

    def test_crossproject_csrf_and_revoked_session_membership_are_checked(self):
        self.imported(2, [self.p, {**self.p, 'id': 'project-b', 'tenant': 'tenant-b',
                                  'customer': 'customer-b', 'owner_email': 'other@example.com'}])
        self.assertEqual(self.request('privacy/project-a')[0], 403)
        self.assertEqual(self.request('privacy/project-b', auth=self.users['owner'])[0], 403)
        self.assertEqual(self.submit(project='project-b')[0], 403)
        self.assertEqual(self.request('privacy_request', self.body(), self.users['owner'],
                                      {'X-CSRF-Token': 'wrong-csrf'})[0], 403)
        self.authorize_member()
        self.assertEqual(self.submit(auth=self.users['member'])[0], 200)
        self.c.revoke(self.owner, 'project-a', self.member)
        self.assertEqual(self.c.session(self.users['member']['token']), self.member)
        self.assertEqual(self.request('privacy/project-a', auth=self.users['member'])[0], 403)
        self.assertEqual(self.submit('privacy_key_000002', auth=self.users['member'])[0], 403)
        self.assertEqual(len(self.receipts()), 1)

    def test_correction_and_deletion_only_record_requests_preserving_source_data(self):
        self.save()
        self.c.message(self.owner, 'project-a', 'original message must remain')
        tables = ('messages', 'message_evidence', 'versions', 'objects', 'change_events',
                  'project_activity_evidence', 'projects', 'members')
        before = {table: [tuple(row) for row in self.c.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                  for table in tables}
        files = {path.name: path.read_bytes() for path in self.c.objects.iterdir()}
        for index, kind in enumerate(('CORRECTION', 'DELETION')):
            status, _, row = self.submit('request_kind_0000' + str(index), kind=kind,
                                         text='Please review ' + kind.lower() + ' of stored evidence')
            self.assertEqual(status, 200)
            self.assertEqual(row['status'], 'RECEIVED')
            self.assertEqual(row['processing_status'], 'UNKNOWN')
            self.assertFalse(row['execution_enabled'])
        after = {table: [tuple(row) for row in self.c.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                 for table in tables}
        self.assertEqual(after, before)
        self.assertEqual({path.name: path.read_bytes() for path in self.c.objects.iterdir()}, files)
        self.assertEqual(len(self.receipts()), 2)
        self.c.check_integrity()

    def test_protected_processing_scope_mismatch_is_rejected_atomically(self):
        row = self.submit()[2]
        good = self.protected_processing(row)
        before = self.receipts()
        for changes in ({'requester_id': self.other}, {'project_id': 'project-b'},
                        {'tenant_id': 'tenant-b'}, {'customer_id': 'customer-b'},
                        {'request_id': 'req_' + 'a' * 32}, {'revision': 2},
                        {'revision': True}, {'status': 'DELETED'}):
            with self.subTest(changes=changes):
                self.processing_callback = lambda uid, pid, rid: {**good, **changes}
                status, _, result = self.request('privacy/project-a', auth=self.users['owner'])
                self.assertEqual(status, 403)
                self.assertEqual(set(result), {'error'})
                self.assertNotIn(good['outcome_ref'], json.dumps(result))
                self.assertEqual(self.receipts(), before)

    def test_protected_closed_status_remains_external_reference_without_execution(self):
        row = self.submit(kind='DELETION')[2]
        self.processing_callback = Mock(return_value=self.protected_processing(row))
        before = self.receipts()
        status, _, result = self.request('privacy/project-a', auth=self.users['owner'])
        self.assertEqual(status, 200)
        self.processing_callback.assert_called_once_with(self.owner, 'project-a', row['request_id'])
        self.assertEqual(result['processing_status'], 'EXTERNAL_REFERENCES_ONLY')
        self.assertEqual(result['processing'][0]['status'], 'CLOSED')
        self.assertFalse(result['processing'][0]['execution_enabled'])
        self.assertFalse(result['execution_enabled'])
        self.assertEqual(result['processing'][0]['assurance'],
                         'EXTERNAL_STATUS_NOT_LEGAL_OR_EXECUTION_ATTESTATION')
        self.assertEqual(result['receipts'][0]['status'], 'RECEIVED')
        self.assertEqual(self.receipts(), before)


if __name__ == '__main__':
    unittest.main()
