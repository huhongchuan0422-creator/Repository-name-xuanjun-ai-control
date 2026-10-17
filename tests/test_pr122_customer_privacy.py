"""Synthetic offline privacy receipts; no providers, production, or deletion."""
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

from scripts.pr122_customer_core import Center, Conflict, Denied, Unavailable
from scripts import pr122_customer_privacy as privacy
from tests import test_pr122_customer_center as fixtures


class PrivacyTests(unittest.TestCase):
    imported = fixtures.CustomerTests.imported

    def setUp(self):
        fixtures.CustomerTests.setUp(self)
        privacy.install(self.c)
        self.policy = {key: key + '-v1' for key in privacy.POLICY_FIELDS}
        self.policy['notice_text'] = 'Synthetic fixture notice, not an approved policy.'
        self.policy['notice_sha256'] = hashlib.sha256(self.policy['notice_text'].encode()).hexdigest()

    def configured(self):
        self.c.privacy_policy_context = lambda uid, pid: dict(self.policy)

    def request(self, key='request_key_00001', **kwargs):
        return privacy.submit_request(self.c, self.owner, 'project-a',
                                      kwargs.pop('kind', 'DELETION'), kwargs.pop('text', 'Please review my request'),
                                      idempotency_key=key, **kwargs)

    def test_unknown_policy_still_receives_request_without_execution(self):
        row = self.request()
        result = privacy.status(self.c, self.owner, 'project-a')
        self.assertEqual(row['status'], 'RECEIVED')
        self.assertFalse(row['execution_enabled'])
        self.assertEqual(result['policy_status'], 'UNKNOWN')
        self.assertEqual(result['consent_status'], 'UNKNOWN')
        self.assertEqual(result['retention_compliance'], 'UNKNOWN')
        self.assertTrue(all(v is None for v in row['policy'].values()))
        self.assertEqual(self.c.db.execute('SELECT event FROM audit ORDER BY seq DESC LIMIT 1').fetchone()[0], 'PRIVACY_STATUS_READ')

    def test_explicit_notice_choice_binds_trusted_policy_no_legal_acceptance(self):
        self.configured()
        for i, decision in enumerate(('ACKNOWLEDGED', 'DECLINED')):
            row = privacy.acknowledge(self.c, self.owner, 'project-a', self.policy['notice_ref'], self.policy['notice_sha256'],
                                      decision, idempotency_key='notice_key_00000' + str(i))
            self.assertEqual(row['decision'], decision)
            self.assertEqual(row['policy'], self.policy)
            self.assertEqual(row['status'], 'RECORDED_NOT_LEGAL_ACCEPTANCE')
            self.assertEqual(row['consent_status'], 'UNKNOWN')
        self.assertEqual(privacy.status(self.c, self.owner, 'project-a')['policy_status'], 'REFERENCES_ONLY')

    def test_unknown_or_forged_notice_rejected_atomically(self):
        for configured, ref, sha in ((False, 'fake', 'a'*64), (True, 'fake', 'a'*64), (True, self.policy['notice_ref'], 'b'*64)):
            if configured:
                self.configured()
            with self.assertRaises(Denied):
                privacy.acknowledge(self.c, self.owner, 'project-a', ref, sha, 'ACKNOWLEDGED', idempotency_key='notice_key_000001')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM privacy_receipts').fetchone()[0], 0)

    def test_policy_rejects_untrusted_fields_and_invalid_values(self):
        for bad in ({'accepted': True}, {'retention_policy': 30}, {'notice_sha256': 'bad'}):
            self.c.privacy_policy_context = lambda uid, pid: bad
            with self.assertRaises(Denied):
                self.request()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM privacy_receipts').fetchone()[0], 0)

    def test_retry_conflict_and_monotonic_amendments(self):
        first = self.request()
        second = self.request('request_key_00002', request_id=first['request_id'], expected_revision=1, text='Corrected request')
        self.assertEqual(second['revision'], 2)
        self.assertEqual(self.request(), first)
        with self.assertRaises(Conflict):
            self.request(text='different payload')
        with self.assertRaises(Conflict):
            self.request('request_key_00003', request_id=first['request_id'], expected_revision=1)
        with self.assertRaises(Conflict):
            self.request('request_key_00003', request_id=first['request_id'], expected_revision=2, kind='QUERY')
        self.assertEqual(len(privacy.status(self.c, self.owner, 'project-a')['receipts']), 2)

    def test_requester_privacy_includes_owner_and_reviewer(self):
        row = self.request()
        self.assertEqual(privacy.status(self.c, self.reviewer, 'project-a')['receipts'], [])
        with self.assertRaises(Denied):
            privacy.submit_request(self.c, self.reviewer, 'project-a', 'DELETION', 'Change another request',
                                   idempotency_key='request_key_00002', request_id=row['request_id'], expected_revision=1)
        with self.assertRaises(Denied):
            privacy.status(self.c, self.other, 'project-a')
        with self.assertRaises(Denied):
            privacy.submit_request(self.c, self.other, 'project-a', 'QUERY', 'Read private data', idempotency_key='request_key_00001')

    def test_revoked_membership_checked_on_every_read_and_write(self):
        token = self.c.invite(self.owner, 'project-a', 'member@example.com', 'VIEWER')['invitation']
        self.c.accept_invite(self.member, token)
        privacy.submit_request(self.c, self.member, 'project-a', 'QUERY', 'My request', idempotency_key='request_key_00001')
        self.assertEqual(privacy.status(self.c, self.owner, 'project-a')['receipts'], [])
        self.c.revoke(self.owner, 'project-a', self.member)
        with self.assertRaises(Denied):
            privacy.status(self.c, self.member, 'project-a')
        with self.assertRaises(Denied):
            privacy.submit_request(self.c, self.member, 'project-a', 'QUERY', 'My request', idempotency_key='request_key_00001')

    def test_reused_project_identity_denies_reads_and_replays(self):
        self.request()
        # Simulate an orphan restored under a reused ID, not a permitted authority update.
        self.c.db.execute("DELETE FROM projects WHERE id='project-a'")
        self.imported(2, [{**self.p, 'tenant': 'replacement-tenant', 'customer': 'replacement-customer'}])
        with self.assertRaisesRegex(Denied, 'IDENTITY_OR_INTEGRITY'):
            privacy.status(self.c, self.owner, 'project-a')
        with self.assertRaises(Denied):
            self.request()

    def test_append_only_no_replace_and_encrypted_text(self):
        self.request(text='private-unique-correction-text')
        row = self.c.db.execute('SELECT * FROM privacy_receipts').fetchone()
        self.assertNotIn(b'private-unique-correction-text', row['payload'])
        for sql, args in [('UPDATE privacy_receipts SET sha=?', ('x',)),
                          ('DELETE FROM privacy_receipts', ()),
                          ('INSERT OR REPLACE INTO privacy_receipts VALUES(?,?,?,?,?,?,?)', tuple(row))]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.c.db.execute(sql, args)
        self.assertEqual(len(privacy.status(self.c, self.owner, 'project-a')['receipts']), 1)

    def test_restart_preserves_receipts_and_install_idempotency(self):
        row = self.request()
        self.c.db.close()
        self.c = Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now)
        privacy.install(self.c)
        privacy.install(self.c)
        self.assertEqual(privacy.status(self.c, self.owner, 'project-a')['receipts'], [row])
        self.assertEqual(self.request(), row)

    def test_audit_failure_rolls_back_receipt_and_no_source_change(self):
        self.c.message(self.owner, 'project-a', 'Immutable source remains retained')
        before = [tuple(r) for r in self.c.db.execute('SELECT * FROM messages')]
        evidence_before = [tuple(r) for r in self.c.db.execute('SELECT * FROM message_evidence')]
        with patch.object(self.c, 'audit', side_effect=RuntimeError('fixture audit failure')):
            with self.assertRaises(RuntimeError):
                self.request()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM privacy_receipts').fetchone()[0], 0)
        self.request()
        self.assertEqual([tuple(r) for r in self.c.db.execute('SELECT * FROM messages')], before)
        self.assertEqual([tuple(r) for r in self.c.db.execute('SELECT * FROM message_evidence')], evidence_before)

    def test_expired_authority_denies_read_and_retry(self):
        self.request()
        self.now += 3601
        with self.assertRaises(Denied):
            privacy.status(self.c, self.owner, 'project-a')
        with self.assertRaises(Denied):
            self.request()

    def test_forged_history_digest_rejected(self):
        self.request()
        # Synthetic corruption fixture deliberately bypasses SQL append-only guard.
        self.c.db.execute('DROP TRIGGER privacy_no_update')
        self.c.db.execute("UPDATE privacy_receipts SET sha=?", ('0' * 64,))
        with self.assertRaisesRegex(Denied, 'IDENTITY_OR_INTEGRITY'):
            privacy.status(self.c, self.owner, 'project-a')

    def test_notice_retry_survives_policy_change_but_rejects_changed_inputs(self):
        self.configured()
        ref, sha = self.policy['notice_ref'], self.policy['notice_sha256']
        def acknowledge(ref=ref, sha=sha, decision='ACKNOWLEDGED', key='notice_key_000001'):
            return privacy.acknowledge(self.c, self.owner, 'project-a', ref, sha, decision, idempotency_key=key)
        old = acknowledge()
        self.c.privacy_policy_context = lambda uid, pid: {'malformed': 'new source'}
        self.assertEqual(acknowledge(), old)
        for changes in ({'ref': 'different'}, {'sha': 'b'*64}, {'decision': 'DECLINED'}):
            with self.assertRaises(Conflict):
                acknowledge(**changes)
        with self.assertRaises(Denied):
            acknowledge(key='notice_key_000002')
        self.c.privacy_policy_context = lambda uid, pid: {}
        self.request()
        with self.assertRaises(Conflict):
            acknowledge(key='request_key_00001')

    def test_notice_text_required_and_digest_verified(self):
        self.configured()
        for text in (None, 'Changed text'):
            self.policy['notice_text'] = text
            with self.assertRaises(Denied):
                privacy.acknowledge(self.c, self.owner, 'project-a', self.policy['notice_ref'],
                                    self.policy['notice_sha256'], 'ACKNOWLEDGED', idempotency_key='notice_key_000001')
        self.policy['notice_text'] = None
        self.assertEqual(privacy.status(self.c, self.owner, 'project-a')['policy_status'], 'UNKNOWN')

    def processing_value(self, request):
        return {'requester_id': self.owner, 'project_id': 'project-a', 'tenant_id': 'tenant-a',
                'customer_id': 'customer-a', 'request_id': request['request_id'], 'revision': request['revision'],
                'status': 'UNDER_REVIEW', 'status_ref': 'fixture-status-1', 'actor_ref': 'fixture-operator',
                'occurred_at': self.now, 'outcome_ref': None}

    def test_protected_processing_source_unknown_and_scoped(self):
        request = self.request()
        result = privacy.status(self.c, self.owner, 'project-a')
        self.assertEqual(result['processing'][0]['status'], 'UNKNOWN')
        value = self.processing_value(request)
        self.c.privacy_processing_context = lambda uid, pid, rid: dict(value)
        result = privacy.status(self.c, self.owner, 'project-a')
        self.assertEqual(result['processing'][0]['status'], 'UNDER_REVIEW')
        self.assertEqual(result['receipts'][0]['processing_status'], 'UNKNOWN')
        self.assertFalse(result['processing'][0]['execution_enabled'])
        value.update(status='CLOSED', outcome_ref='fixture-outcome-1')
        self.assertEqual(privacy.status(self.c, self.owner, 'project-a')['processing'][0]['status'], 'CLOSED')
        self.assertEqual(privacy.status(self.c, self.reviewer, 'project-a')['processing'], [])

    def test_processing_scope_spoof_staleness_and_bad_status_rejected(self):
        request = self.request()
        valid = self.processing_value(request)
        cases = ({'requester_id': self.reviewer}, {'project_id': 'project-b'}, {'tenant_id': 'tenant-b'},
                 {'customer_id': 'customer-b'}, {'request_id': 'req_'+'0'*32}, {'revision': 2}, {'revision': True},
                 {'status': 'DELETED'}, {'occurred_at': self.now+1}, {'occurred_at': self.now-1},
                 {'status_ref': None}, {'actor_ref': None}, {'status': 'CLOSED'}, {'unexpected': 'field'})
        for changes in cases:
            with self.subTest(changes=changes):
                self.c.privacy_processing_context = lambda uid, pid, rid: {**valid, **changes}
                with self.assertRaises(Denied):
                    privacy.status(self.c, self.owner, 'project-a')
        self.c.privacy_processing_context = lambda uid, pid, rid: dict(valid)
        self.request('request_key_00002', request_id=request['request_id'], expected_revision=1)
        with self.assertRaises(Denied):
            privacy.status(self.c, self.owner, 'project-a')

    def test_status_reuses_outer_transaction_and_rolls_back_audit(self):
        receipt = self.request()
        before = self.c.db.execute('SELECT count(*) FROM audit').fetchone()[0]
        with self.assertRaisesRegex(RuntimeError, 'rollback fixture'):
            with self.c.tx():
                result = privacy.status(self.c, self.owner, 'project-a')
                self.assertEqual(result['receipts'], [receipt])
                self.assertTrue(self.c.db.in_transaction)
                self.assertEqual(self.c.db.execute('SELECT count(*) FROM audit').fetchone()[0], before + 1)
                raise RuntimeError('rollback fixture')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM audit').fetchone()[0], before)
        self.assertFalse(self.c.db.in_transaction)
        privacy.status(self.c, self.owner, 'project-a')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM audit').fetchone()[0], before + 1)
        self.assertFalse(self.c.db.in_transaction)

    def test_global_verify_preserves_revoked_and_orphan_history(self):
        self.assertEqual(privacy.verify(self.c)['count'], 0)
        token = self.c.invite(self.owner, 'project-a', 'member@example.com', 'VIEWER')['invitation']
        self.c.accept_invite(self.member, token)
        privacy.submit_request(self.c, self.member, 'project-a', 'QUERY', 'My request', idempotency_key='request_key_00001')
        self.request()
        self.c.revoke(self.owner, 'project-a', self.member)
        self.assertEqual(privacy.verify(self.c)['count'], 2)
        self.c.db.execute("DELETE FROM projects WHERE id='project-a'")
        with self.c.tx():
            result = privacy.verify(self.c)
            self.assertTrue(self.c.db.in_transaction)
            self.assertEqual(result['count'], 2)
            self.assertEqual(result['chains'], 2)
        with self.assertRaises(Denied):
            privacy.status(self.c, self.owner, 'project-a')

    def test_global_verify_rejects_ciphertext_and_row_corruption(self):
        self.request()
        original = self.c.db.execute('SELECT * FROM privacy_receipts').fetchone()
        self.c.db.execute('DROP TRIGGER privacy_no_update')
        for field, invalid in (('sha', '0'*64), ('payload', b'not-encrypted'),
                               ('project', 'other-project'), ('requester', 'other-user'),
                               ('idem', '0'*64), ('id', 'privacy_'+'0'*32)):
            with self.subTest(field=field):
                self.c.db.execute('UPDATE privacy_receipts SET '+field+'=?', (invalid,))
                with self.assertRaisesRegex(Denied, 'PRIVACY_HISTORY_INTEGRITY'):
                    privacy.verify(self.c)
                self.c.db.execute('UPDATE privacy_receipts SET '+field+'=?', (original[field],))
        self.assertEqual(privacy.verify(self.c)['count'], 1)
        value = json.loads(self.c.decrypt(original['payload'], 'privacy:' + original['id']))
        value['tenant_id'] = ''
        value['record_digest'] = privacy.digest(privacy.canonical({k: v for k, v in value.items() if k != 'record_digest'}))
        self.c.db.execute('UPDATE privacy_receipts SET payload=?,sha=?',
                          (self.c.encrypt(privacy.canonical(value), 'privacy:' + original['id']), value['record_digest']))
        with self.assertRaisesRegex(Denied, 'PRIVACY_HISTORY_INTEGRITY'):
            privacy.verify(self.c)

    def test_bounds_validation_and_no_consent_autoaccept(self):
        for kwargs in ({'kind': 'PURGE'}, {'expected_revision': True}, {'expected_revision': 1}, {'request_id': '../private'}):
            with self.assertRaises((ValueError, Conflict)):
                self.request(**kwargs)
        with self.assertRaises(ValueError):
            self.request(key='short')
        self.configured()
        with self.assertRaises(ValueError):
            privacy.acknowledge(self.c, self.owner, 'project-a', self.policy['notice_ref'], self.policy['notice_sha256'],
                                'ACCEPT_LEGAL_AGREEMENT', idempotency_key='notice_key_000001')
        with patch.object(privacy, 'MAX_HISTORY', 1):
            self.request()
            with self.assertRaises(Unavailable):
                self.request('request_key_00002')


if __name__ == '__main__':
    unittest.main()
