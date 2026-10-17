"""Synthetic, offline evidence tests against the real customer core and HTTP app.

Reuse fixture helpers without importing or inheriting their existing test cases.
No sockets, provider calls, server changes, real identities, or new ledger.
"""
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

from scripts.pr122_customer_core import Center, Denied, Unavailable, canonical
from scripts.pr122_customer_evidence import export_project, verify as verify_evidence
from scripts.pr122_customer_http import App
from scripts.pr122_customer_providers import Providers, ai_reply, drain_message, enqueue
from tests import test_pr122_customer_center as customer_fixtures
from tests import test_pr122_customer_providers as provider_fixtures
from tests import test_pr122_site_hub_identity_integration as http_fixtures


CONTEXT_FIELDS = ('conversation_id', 'module_id', 'preview_version', 'task_ref',
                  'consent_version', 'retention_policy')
ZERO_DIGEST = '0' * 64


class EvidenceFixture(unittest.TestCase):
    setUp = customer_fixtures.CustomerTests.setUp
    imported = customer_fixtures.CustomerTests.imported

    def reopen(self, evidence_context=None):
        self.c.db.close()
        self.c = Center(self.root, {'v1': self.key}, 'v1',
                        clock=lambda: self.now, mail_ready=True,
                        scanner=lambda raw: True, evidence_context=evidence_context)

    def evidence_rows(self):
        return [tuple(row) for row in self.c.db.execute(
            'SELECT * FROM message_evidence ORDER BY seq')]

    def mutation_snapshot(self):
        return {table: [tuple(row) for row in self.c.db.execute(
            'SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in ('messages', 'message_evidence', 'audit',
                              'rate_limits', 'events')}

    def bind_channel(self, channel='TELEGRAM', subject='123'):
        challenge = self.c.binding_challenge(
            self.owner, 'project-a', channel, subject)['challenge']
        self.c.channel_event(channel, 'bind_' + channel, subject,
                             '/bind ' + challenge)
        pending = self.c.pending_links(self.owner, 'project-a')
        link = next(row for row in pending if row['channel'] == channel)
        self.c.confirm_link(self.owner, 'project-a', link['id'])

    def reused_legacy_orphan(self, channel='WEB', status='ARCHIVED'):
        pid, mid = 'reused-orphan-project', 'm_same_owner_orphan'
        body = 'private history without proven tenant or customer'
        self.c.db.execute("DELETE FROM settings WHERE k='message_evidence_schema'")
        self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',
                          (mid, pid, self.owner, channel,
                           self.c.encrypt(body.encode(), mid), status, self.now - 50))
        self.reopen()
        self.imported(2, [self.p, {**self.p, 'id': pid,
                                  'tenant': 'new-tenant', 'customer': 'new-customer'}])
        self.c.project(self.owner, pid)
        return pid, mid, body

    def assert_chain(self, result, bodies):
        self.assertEqual(result['assurance'],
                         'LOCAL_HASH_CHAIN_NOT_EXTERNAL_ATTESTATION')
        self.assertEqual([row['body'] for row in result['records']], bodies)
        previous = ZERO_DIGEST
        for record in result['records']:
            evidence = record['evidence']
            self.assertEqual(evidence['previous_record_digest'], previous)
            self.assertEqual(evidence['content_sha256'], hashlib.sha256(
                record['body'].encode()).hexdigest())
            unsigned = {key: value for key, value in evidence.items()
                        if key != 'record_digest'}
            self.assertEqual(evidence['record_digest'],
                             hashlib.sha256(canonical(unsigned)).hexdigest())
            previous = evidence['record_digest']
        self.assertEqual(result['chain_head'], previous)


class MessageEvidenceTests(EvidenceFixture):
    def test_history_cap_precedes_message_and_evidence_decrypt_for_every_consumer(self):
        source = self.c.message(self.owner, 'project-a', 'bounded source fixture')
        self.bind_channel()
        enqueue(self.c, self.owner, 'project-a', 'TELEGRAM', 'bounded outbound fixture')
        provider = Mock()
        ai_provider = Providers({'web_ai': {'provider': 'openai', 'model_key': 'approved-fixture'}})
        rpc = Mock(return_value='must not run')
        operations = (
            ('read', lambda: self.c.messages(self.owner, 'project-a')),
            ('write', lambda: self.c.message(self.owner, 'project-a', 'must not append')),
            ('export', lambda: export_project(self.c, self.owner, 'project-a')),
            ('enqueue', lambda: enqueue(self.c, self.owner, 'project-a', 'TELEGRAM', 'must not queue')),
            ('send', lambda: drain_message(self.c, provider)),
            ('ai', lambda: ai_reply(self.c, self.owner, 'project-a', source['id'], ai_provider, rpc=rpc)),
        )
        before = self.mutation_snapshot()
        with patch('scripts.pr122_customer_evidence.MAX_HISTORY', 0), \
                patch.object(self.c, 'decrypt', wraps=self.c.decrypt) as decrypt, \
                patch('scripts.pr122_customer_evidence.verify',
                      side_effect=AssertionError('FULL_HISTORY_VERIFY_MUST_NOT_RUN')):
            for name, operation in operations:
                with self.subTest(operation=name):
                    decrypt.reset_mock()
                    with self.assertRaisesRegex(Unavailable, 'BOUNDED_HISTORY_REQUIRES_OPERATOR'):
                        operation()
                    self.assertGreaterEqual(decrypt.call_count, 1)
                    self.assertTrue(all(call.args[1] == 'project:project-a'
                                        for call in decrypt.call_args_list))
                    self.assertEqual(self.mutation_snapshot(), before)
        provider.send.assert_not_called()
        rpc.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM ai_jobs').fetchone()[0], 0)

    def test_ai_revalidates_content_changed_during_rpc_before_archiving_reply(self):
        source = self.c.message(self.owner, 'project-a', 'original RPC source')
        evidence_before = self.evidence_rows()
        audit_before = [tuple(row) for row in self.c.db.execute('SELECT * FROM audit ORDER BY seq')]
        provider = Providers({'web_ai': {'provider': 'openai', 'model_key': 'approved-fixture'}})

        def tamper_during_rpc(config, context):
            self.assertEqual(context['body'], 'original RPC source')
            self.c.db.execute('UPDATE messages SET payload=? WHERE id=?',
                              (self.c.encrypt(b'altered while RPC was running', source['id']),
                               source['id']))
            return 'must not archive after source changed'

        rpc = Mock(side_effect=tamper_during_rpc)
        result = ai_reply(self.c, self.owner, 'project-a', source['id'], provider, rpc=rpc)
        self.assertEqual(result, {'state': 'UNKNOWN'})
        rpc.assert_called_once()
        self.assertEqual(tuple(self.c.db.execute(
            'SELECT state,result_id FROM ai_jobs WHERE message_id=?', (source['id'],)).fetchone()),
                         ('UNKNOWN', None))
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM messages WHERE channel='WEB_AI'").fetchone()[0], 0)
        self.assertEqual(self.evidence_rows(), evidence_before)
        self.assertEqual([tuple(row) for row in self.c.db.execute('SELECT * FROM audit ORDER BY seq')],
                         audit_before)
        with self.assertRaisesRegex(Denied, 'MESSAGE_CONTENT_INTEGRITY'):
            self.c.check_integrity()

    def test_messages_read_audit_binds_actor_project_head_in_same_transaction(self):
        self.imported(2, [self.p, {**self.p, 'id': 'project-b',
                                  'tenant': 'tenant-b', 'customer': 'customer-b',
                                  'owner_email': 'other@example.com'}])
        self.c.message(self.owner, 'project-a', 'read project-a fixture')
        self.c.message(self.other, 'project-b', 'private project-b fixture')
        head = self.c.db.execute(
            'SELECT sha FROM message_evidence WHERE project=? ORDER BY seq DESC LIMIT 1',
            ('project-a',)).fetchone()[0]
        audit_before = self.c.db.execute('SELECT max(seq) FROM audit').fetchone()[0]
        observed = []
        original_audit = self.c.audit

        def spy_audit(project, actor, event, object_id):
            observed.append((project, actor, event, object_id, self.c.db.in_transaction))
            return original_audit(project, actor, event, object_id)

        with patch.object(self.c, 'audit', side_effect=spy_audit):
            messages = self.c.messages(self.reviewer, 'project-a')
        self.assertEqual([message['body'] for message in messages], ['read project-a fixture'])
        self.assertEqual(observed, [('project-a', self.reviewer, 'MESSAGES_READ', head, True)])
        self.assertFalse(self.c.db.in_transaction)
        row = self.c.db.execute('SELECT * FROM audit WHERE seq=?', (audit_before + 1,)).fetchone()
        self.assertEqual((row['project'], row['actor'], row['event'], row['object_id'], row['at']),
                         ('project-a', self.reviewer, 'MESSAGES_READ', head, self.now))
        self.assertEqual(self.c.db.execute('SELECT max(seq) FROM audit').fetchone()[0], audit_before + 1)
        self.c.check_integrity()

    def test_empty_export_is_explicitly_local_and_project_scoped(self):
        result = export_project(self.c, self.owner, 'project-a')
        self.assertEqual(result['schema'], 1)
        self.assertEqual(result['project_id'], 'project-a')
        self.assert_chain(result, [])

    def test_export_receipt_matches_current_actor_time_and_exact_audit_row(self):
        self.imported(2, [self.p, {**self.p, 'id': 'project-b',
                                  'tenant': 'tenant-b', 'customer': 'customer-b',
                                  'owner_email': 'other@example.com'}])
        self.c.message(self.owner, 'project-a', 'exported project-a fixture')
        self.c.message(self.other, 'project-b', 'other-project private body')
        with self.c.tx():
            self.c.audit('project-b', self.other, 'OTHER_PROJECT_PRIVATE_EVENT',
                         'other-private-audit-object')
        previous_seq = self.c.db.execute('SELECT max(seq) FROM audit').fetchone()[0]
        self.now += 7
        result = export_project(self.c, self.reviewer, 'project-a')
        receipt = result['export_receipt']
        self.assertEqual(set(receipt), {'project_id', 'actor_id', 'exported_at',
                                      'audit_seq', 'audit_digest', 'message_chain_head'})
        self.assertEqual(receipt['project_id'], 'project-a')
        self.assertEqual(receipt['actor_id'], self.reviewer)
        self.assertEqual(receipt['exported_at'], self.now)
        self.assertEqual(receipt['audit_seq'], previous_seq + 3)
        self.assertEqual([r[0] for r in self.c.db.execute('SELECT event FROM audit WHERE seq>? ORDER BY seq',(previous_seq,))], ['ACTIVITY_EVIDENCE_READ','PRIVACY_STATUS_READ','MESSAGE_EVIDENCE_EXPORTED'])
        self.assertEqual(receipt['message_chain_head'], result['chain_head'])
        row = self.c.db.execute('SELECT * FROM audit WHERE seq=?', (receipt['audit_seq'],)).fetchone()
        self.assertEqual((row['project'], row['actor'], row['at'], row['sha']),
                         (receipt['project_id'], receipt['actor_id'],
                          receipt['exported_at'], receipt['audit_digest']))
        self.assertEqual(row['event'], 'MESSAGE_EVIDENCE_EXPORTED')
        self.assertEqual(row['object_id'], result['chain_head'])
        self.assertEqual(row['sha'], hashlib.sha256(canonical([
            row['project'], row['actor'], row['event'], row['object_id'],
            row['at'], row['parent']])).hexdigest())
        self.assertEqual(self.c.db.execute('SELECT max(seq) FROM audit').fetchone()[0],
                         receipt['audit_seq'])
        serialized = json.dumps(result)
        for private in ('project-b', 'tenant-b', 'customer-b',
                        'OTHER_PROJECT_PRIVATE_EVENT', 'other-private-audit-object',
                        'other-project private body'):
            self.assertNotIn(private, serialized)
        self.assert_chain(result, ['exported project-a fixture'])

    def test_new_message_chain_binds_actual_utf8_body_and_identity(self):
        bodies = ['第一条私有消息。', 'second synthetic message']
        first = self.c.message(self.owner, 'project-a', bodies[0])
        # Equal creation timestamps must not randomize append order by message ID.
        with self.c.tx():
            second = self.c.message(self.owner, 'project-a', bodies[1])
        result = export_project(self.c, self.owner, 'project-a')
        self.assert_chain(result, bodies)
        self.assertEqual([r['evidence']['message_id'] for r in result['records']],
                         [first['id'], second['id']])
        for record in result['records']:
            evidence = record['evidence']
            for field, expected in (
                    ('customer_id', 'customer-a'), ('tenant_id', 'tenant-a'),
                    ('project_id', 'project-a'), ('source_channel', 'WEB'),
                    ('sender_role', 'OWNER'), ('server_received_at', self.now),
                    ('provenance', 'SERVER_CAPTURED')):
                self.assertEqual(evidence[field], expected)
            self.assertIsNone(evidence['provider_occurred_at'])
            self.assertIsNone(evidence['external_event_id'])
            for field in CONTEXT_FIELDS:
                self.assertIsNone(evidence[field])
            self.assertEqual(record['delivery_status'], 'ARCHIVED')
            self.assertIsNone(record['provider_ref'])
        self.c.check_integrity()

    def test_trusted_context_is_bound_and_encrypted_without_policy_invention(self):
        refs = {field: 'private-fixture-' + field for field in CONTEXT_FIELDS}
        callback = Mock(return_value=refs)
        self.reopen(callback)
        message = self.c.message(self.owner, 'project-a', 'private fixture body',
                                 'TELEGRAM', 'provider_event_fixture',
                                 provider_occurred_at=self.now - 7)
        callback.assert_called_once_with(self.owner, 'project-a')
        result = export_project(self.c, self.owner, 'project-a')
        evidence = result['records'][0]['evidence']
        self.assertEqual({field: evidence[field] for field in CONTEXT_FIELDS}, refs)
        self.assertEqual(evidence['external_event_id'], 'provider_event_fixture')
        self.assertEqual(evidence['provider_occurred_at'], self.now - 7)
        row = self.c.db.execute('SELECT * FROM message_evidence').fetchone()
        self.assertEqual(row['message_id'], message['id'])
        self.assertEqual(row['sha'], evidence['record_digest'])
        self.assertEqual(json.loads(self.c.decrypt(
            row['payload'], 'message-evidence:' + message['id'])), evidence)
        for value in (*refs.values(), 'private fixture body',
                      'provider_event_fixture', 'SERVER_CAPTURED'):
            self.assertNotIn(value.encode(), row['payload'])
        self.c.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        disk = b''.join(path.read_bytes() for path in self.root.glob('center.sqlite*'))
        for value in (*refs.values(), 'private fixture body', 'provider_event_fixture'):
            self.assertNotIn(value.encode(), disk)

    def test_partial_context_leaves_missing_references_null(self):
        self.reopen(lambda uid, pid: {'module_id': 'module-fixture'})
        self.c.message(self.owner, 'project-a', 'partial context')
        evidence = export_project(self.c, self.owner, 'project-a')['records'][0]['evidence']
        self.assertEqual(evidence['module_id'], 'module-fixture')
        for field in set(CONTEXT_FIELDS) - {'module_id'}:
            self.assertIsNone(evidence[field])

    def test_append_only_blocks_update_delete_and_replace(self):
        self.c.message(self.owner, 'project-a', 'immutable evidence')
        before = self.evidence_rows()
        row = self.c.db.execute('SELECT * FROM message_evidence').fetchone()
        statements = (
            ('UPDATE message_evidence SET sha=?', ('f' * 64,)),
            ('DELETE FROM message_evidence', ()),
            ('INSERT OR REPLACE INTO message_evidence(seq,message_id,project,payload,sha) '
             'VALUES(?,?,?,?,?)', tuple(row)),
        )
        for sql, parameters in statements:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                with self.c.tx():
                    self.c.db.execute(sql, parameters)
            self.assertEqual(self.evidence_rows(), before)
        self.c.check_integrity()

    def test_validly_reencrypted_body_tampering_fails_integrity_and_export(self):
        message = self.c.message(self.owner, 'project-a', 'original actual content')
        # A ciphertext authentication check alone would accept this replacement.
        self.c.db.execute('UPDATE messages SET payload=? WHERE id=?',
                          (self.c.encrypt(b'altered actual content', message['id']),
                           message['id']))
        with self.assertRaises(Denied):
            self.c.check_integrity()
        with self.assertRaises(Denied):
            export_project(self.c, self.owner, 'project-a')

    def test_reopen_does_not_rewrite_or_duplicate_captured_evidence(self):
        self.c.message(self.owner, 'project-a', 'existing server capture')
        before = self.evidence_rows()
        for _ in range(2):
            self.now += 1
            self.reopen()
            self.assertEqual(self.evidence_rows(), before)
            self.assertEqual(self.c.db.execute('SELECT count(*) FROM messages').fetchone()[0], 1)
            self.c.check_integrity()

    def test_legacy_migration_preserves_unknown_context_and_is_idempotent(self):
        # A pre-extension database has no migration marker or evidence records.
        self.c.db.execute("DELETE FROM settings WHERE k='message_evidence_schema'")
        originals = []
        for mid, channel, body, created in (
                ('m_legacy_z', 'WEB', 'old web body', self.now - 20),
                ('m_legacy_a', 'TELEGRAM', 'old channel body', self.now - 10)):
            payload = self.c.encrypt(body.encode(), mid)
            self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',
                              (mid, 'project-a', self.owner, channel, payload,
                               'ARCHIVED', None, created))
            originals.append((mid, payload, created))
        callback = Mock(side_effect=AssertionError('historical context cannot be invented'))
        self.reopen(callback)
        callback.assert_not_called()
        result = export_project(self.c, self.owner, 'project-a')
        self.assert_chain(result, ['old web body', 'old channel body'])
        for record, (mid, payload, created) in zip(result['records'], originals):
            evidence = record['evidence']
            self.assertEqual(evidence['message_id'], mid)
            self.assertEqual(evidence['provenance'], 'LEGACY_BACKFILL_UNKNOWN_CONTEXT')
            self.assertEqual(evidence['server_received_at'], created)
            self.assertIsNone(evidence['provider_occurred_at'])
            self.assertIsNone(evidence['external_event_id'])
            self.assertIsNone(evidence['sender_role'])
            for field in CONTEXT_FIELDS:
                self.assertIsNone(evidence[field])
            stored = self.c.db.execute('SELECT payload,created FROM messages WHERE id=?', (mid,)).fetchone()
            self.assertEqual(tuple(stored), (payload, created))
        before = self.evidence_rows()
        self.now += 100
        self.reopen(callback)
        self.assertEqual(self.evidence_rows(), before)
        callback.assert_not_called()
        self.c.check_integrity()

    def test_postmigration_untracked_message_is_not_silently_blessed(self):
        mid = 'm_untracked_fixture'
        self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',
                          (mid, 'project-a', self.owner, 'WEB',
                           self.c.encrypt(b'untracked content', mid), 'ARCHIVED', self.now))
        with self.assertRaises(Denied):
            self.c.check_integrity()
        with self.assertRaises(Denied):
            Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now)
        self.assertEqual(self.evidence_rows(), [])

    def test_verification_reads_share_one_transaction_and_reuse_caller_lock(self):
        self.c.message(self.owner, 'project-a', 'snapshot-bound fixture')
        connection = self.c.db
        queries = []

        class ConnectionSpy:
            def __getattr__(self, name):
                return getattr(connection, name)

            def execute(self, sql, parameters=()):
                queries.append((sql, connection.in_transaction))
                return connection.execute(sql, parameters)

        self.c.db = ConnectionSpy()
        try:
            self.assertFalse(connection.in_transaction)
            records, heads = verify_evidence(self.c, 'project-a')
            self.assertEqual([record['body'] for record in records], ['snapshot-bound fixture'])
            self.assertEqual(heads['project-a'], records[0]['evidence']['record_digest'])
            self.assertFalse(connection.in_transaction)
            self.assertEqual([sql for sql, _ in queries if sql.startswith('BEGIN')],
                             ['BEGIN IMMEDIATE'])
            reads = [(sql, active) for sql, active in queries if sql.startswith('SELECT')]
            self.assertEqual(len(reads), 3)
            self.assertTrue(all(active for _, active in reads), reads)

            queries.clear()
            with self.c.tx():
                verify_evidence(self.c, 'project-a')
                # The verifier must neither nest BEGIN nor commit its caller's lock.
                self.assertTrue(connection.in_transaction)
                self.assertEqual([sql for sql, _ in queries if sql.startswith('BEGIN')],
                                 ['BEGIN IMMEDIATE'])
                reads = [(sql, active) for sql, active in queries if sql.startswith('SELECT')]
                self.assertEqual(len(reads), 3)
                self.assertTrue(all(active for _, active in reads), reads)
            self.assertFalse(connection.in_transaction)
        finally:
            self.c.db = connection

    def test_legacy_orphan_stays_unknown_and_project_id_reuse_cannot_export_it(self):
        pid, mid = 'orphan-project', 'm_legacy_orphan'
        self.c.db.execute("DELETE FROM settings WHERE k='message_evidence_schema'")
        self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',
                          (mid, pid, self.other, 'WEB',
                           self.c.encrypt(b'unknown-origin private history', mid),
                           'ARCHIVED', self.now - 50))
        self.reopen()
        row = self.c.db.execute('SELECT * FROM message_evidence WHERE message_id=?', (mid,)).fetchone()
        evidence = json.loads(self.c.decrypt(row['payload'], 'message-evidence:' + mid))
        self.assertEqual(evidence['provenance'], 'LEGACY_BACKFILL_UNKNOWN_CONTEXT')
        self.assertIsNone(evidence['tenant_id'])
        self.assertIsNone(evidence['customer_id'])
        self.c.check_integrity()

        self.imported(2, [self.p, {**self.p, 'id': pid,
                                  'tenant': 'new-tenant', 'customer': 'new-customer'}])
        self.c.project(self.owner, pid)  # New authority legitimately grants this ID.
        before = self.mutation_snapshot()
        with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
            export_project(self.c, self.owner, pid)
        self.assertEqual(self.mutation_snapshot(), before)
        self.reopen()
        current = self.c.db.execute('SELECT * FROM message_evidence WHERE message_id=?', (mid,)).fetchone()
        self.assertEqual(tuple(current), tuple(row))
        with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
            export_project(self.c, self.owner, pid)

    def test_same_owner_orphan_ai_cannot_start_job_or_call_rpc(self):
        pid, mid, _ = self.reused_legacy_orphan()
        provider = Providers({'web_ai': {'provider': 'openai', 'model_key': 'approved-fixture'}})
        rpc = Mock(return_value='must not see orphan history')
        before = self.mutation_snapshot()
        with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
            ai_reply(self.c, self.owner, pid, mid, provider, rpc=rpc)
        rpc.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM ai_jobs').fetchone()[0], 0)
        self.assertEqual(self.mutation_snapshot(), before)

    def test_pending_orphan_cannot_send_or_advance_with_new_legitimate_binding(self):
        pid, mid, _ = self.reused_legacy_orphan('TELEGRAM', 'PENDING')
        challenge = self.c.binding_challenge(self.owner, pid, 'TELEGRAM', '123')['challenge']
        self.c.channel_event('TELEGRAM', 'new_orphan_binding', '123', '/bind ' + challenge)
        pending = self.c.pending_links(self.owner, pid)
        self.c.confirm_link(self.owner, pid, pending[0]['id'])
        self.assertEqual(self.c.db.execute(
            'SELECT active FROM links WHERE project=? AND user_id=?',
            (pid, self.owner)).fetchone()[0], 1)
        provider = Mock()
        provider.send.return_value = ('ACCEPTED', 'must-not-be-used')
        before = self.mutation_snapshot()
        with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
            drain_message(self.c, provider)
        provider.send.assert_not_called()
        self.assertEqual(tuple(self.c.db.execute(
            'SELECT status,provider_ref FROM messages WHERE id=?', (mid,)).fetchone()),
                         ('PENDING', None))
        with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
            enqueue(self.c, self.owner, pid, 'TELEGRAM', 'must not add new outbound')
        self.assertEqual(self.mutation_snapshot(), before)

    def test_nonnull_project_subject_mismatch_blocks_reads_and_new_messages(self):
        self.c.message(self.owner, 'project-a', 'known original subject')
        for field, original in (('tenant', 'tenant-a'), ('customer', 'customer-a')):
            with self.subTest(field=field):
                # Simulate subject drift in stored state; authority import rejects it.
                self.c.db.execute('UPDATE projects SET ' + field + '=? WHERE id=?',
                                  ('different-subject', 'project-a'))
                before = self.mutation_snapshot()
                try:
                    with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
                        self.c.messages(self.owner, 'project-a')
                    with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
                        export_project(self.c, self.owner, 'project-a')
                    with self.assertRaisesRegex(Denied, 'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
                        self.c.message(self.owner, 'project-a', 'must not extend mismatched history')
                    self.assertEqual(self.mutation_snapshot(), before)
                finally:
                    self.c.db.execute('UPDATE projects SET ' + field + '=? WHERE id=?',
                                      (original, 'project-a'))
        self.assertEqual(self.c.messages(self.owner, 'project-a')[0]['body'], 'known original subject')

    def test_project_chains_and_exports_do_not_cross_customer_boundaries(self):
        self.imported(2, [self.p, {**self.p, 'id': 'project-b'},
                          {**self.p, 'id': 'project-c', 'tenant': 'tenant-c',
                           'customer': 'customer-c', 'owner_email': 'other@example.com'}])
        self.c.message(self.owner, 'project-a', 'A1')
        self.c.message(self.owner, 'project-b', 'B1')
        self.c.message(self.other, 'project-c', 'C1')
        self.c.message(self.owner, 'project-a', 'A2')
        for uid, pid, bodies in ((self.owner, 'project-a', ['A1', 'A2']),
                                 (self.owner, 'project-b', ['B1']),
                                 (self.other, 'project-c', ['C1'])):
            self.assert_chain(export_project(self.c, uid, pid), bodies)
        before = self.mutation_snapshot()
        for uid, pid in ((self.owner, 'project-c'), (self.other, 'project-a'),
                         (self.other, 'project-b'), (self.owner, 'missing-project')):
            with self.subTest(uid=uid, pid=pid), self.assertRaises(Denied):
                export_project(self.c, uid, pid)
        self.assertEqual(self.mutation_snapshot(), before)

    def test_revoked_or_expired_grants_deny_evidence_despite_live_session(self):
        token = self.c.invite(self.owner, 'project-a', 'member@example.com', 'VIEWER')['invitation']
        self.c.accept_invite(self.member, token)
        self.c.message(self.owner, 'project-a', 'private before revocation')
        self.assert_chain(export_project(self.c, self.member, 'project-a'),
                          ['private before revocation'])
        self.c.revoke(self.owner, 'project-a', self.member)
        self.assertEqual(self.c.session(self.users['member']['token']), self.member)
        with self.assertRaises(Denied):
            export_project(self.c, self.member, 'project-a')
        self.now += 3601
        with self.assertRaises(Denied):
            export_project(self.c, self.owner, 'project-a')

    def test_malformed_or_spoofed_trusted_context_rolls_back_every_write(self):
        invalid = [[], 'client-supplied', True, {'tenant_id': 'tenant-other'},
                   {'customer_id': 'customer-other'}, {'project_id': 'project-b'},
                   {'record_digest': '0' * 64}, {'sender_role': 'REVIEWER'},
                   {'content_sha256': 'f' * 64}, {'external_event_id': 'forged'},
                   {'module_id': 12}, {'conversation_id': ['nested']},
                   {'retention_policy': True}, {'task_ref': 'unsafe\nreference'}]
        for supplied in invalid:
            with self.subTest(supplied=supplied):
                self.c.evidence_context = lambda uid, pid: supplied
                before = self.mutation_snapshot()
                with self.assertRaises((Denied, ValueError, TypeError)):
                    self.c.message(self.owner, 'project-a', 'must roll back')
                self.assertEqual(self.mutation_snapshot(), before)
        self.c.evidence_context = Mock(side_effect=RuntimeError('trusted resolver unavailable'))
        before = self.mutation_snapshot()
        with self.assertRaises(RuntimeError):
            self.c.message(self.owner, 'project-a', 'must also roll back')
        self.assertEqual(self.mutation_snapshot(), before)

    def test_invalid_provider_timestamp_rolls_back_new_message(self):
        for timestamp in (True, -1, '1792137000', self.now + 301):
            with self.subTest(timestamp=timestamp):
                before = self.mutation_snapshot()
                with self.assertRaises((Denied, ValueError, TypeError)):
                    self.c.message(self.owner, 'project-a', 'bad provider time',
                                   'TELEGRAM', 'fixture_event',
                                   provider_occurred_at=timestamp)
                self.assertEqual(self.mutation_snapshot(), before)

    def test_failed_channel_capture_does_not_consume_provider_event(self):
        self.bind_channel()
        self.c.evidence_context = lambda uid, pid: {'tenant_id': 'spoofed-tenant'}
        before = self.mutation_snapshot()
        with self.assertRaises(Denied):
            self.c.channel_event('TELEGRAM', 'retryable_fixture_event', '123',
                                 '/project project-a transactional channel fixture')
        self.assertEqual(self.mutation_snapshot(), before)
        self.c.evidence_context = None
        saved = self.c.channel_event('TELEGRAM', 'retryable_fixture_event', '123',
                                     '/project project-a transactional channel fixture')
        self.assertEqual(saved['status'], 'ARCHIVED')
        result = export_project(self.c, self.owner, 'project-a')
        self.assert_chain(result, ['transactional channel fixture'])
        self.assertEqual(result['records'][0]['evidence']['external_event_id'],
                         'retryable_fixture_event')

    def test_failed_outbound_capture_rolls_back_queue_and_audit(self):
        self.bind_channel()
        self.c.evidence_context = lambda uid, pid: {'customer_id': 'spoofed-customer'}
        before = self.mutation_snapshot()
        with self.assertRaises(Denied):
            enqueue(self.c, self.owner, 'project-a', 'TELEGRAM', 'must not queue')
        self.assertEqual(self.mutation_snapshot(), before)

    def test_failed_ai_capture_leaves_no_reply_or_partial_evidence(self):
        source = self.c.message(self.owner, 'project-a', 'source remains intact')
        before = self.mutation_snapshot()
        self.c.evidence_context = lambda uid, pid: {'sender_role': 'OWNER'}
        provider = Providers({'web_ai': {'provider': 'openai', 'model_key': 'approved-fixture'}})
        rpc = Mock(return_value='must not archive')
        with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            outcome = ai_reply(self.c, self.owner, 'project-a', source['id'], provider, rpc=rpc)
            repeated = ai_reply(self.c, self.owner, 'project-a', source['id'], provider, rpc=rpc)
        self.assertEqual(outcome, {'state': 'UNKNOWN'})
        self.assertEqual(repeated['state'], 'UNKNOWN')
        rpc.assert_called_once()
        self.assertEqual(self.mutation_snapshot(), before)
        self.assertEqual(tuple(self.c.db.execute('SELECT state,result_id FROM ai_jobs').fetchone()),
                         ('UNKNOWN', None))
        self.c.check_integrity()

    def test_ai_reply_has_distinct_role_related_source_and_immutable_capture(self):
        source = self.c.message(self.owner, 'project-a', 'synthetic question')
        provider = Providers({'web_ai': {'provider': 'openai', 'model_key': 'approved-fixture'}})
        rpc = Mock(return_value='synthetic AI answer')
        with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            reply = ai_reply(self.c, self.owner, 'project-a', source['id'], provider, rpc=rpc)
            repeated = ai_reply(self.c, self.owner, 'project-a', source['id'], provider, rpc=rpc)
        self.assertEqual(reply, repeated)
        self.assertEqual(reply['state'], 'ANSWERED')
        rpc.assert_called_once()
        result = export_project(self.c, self.owner, 'project-a')
        self.assert_chain(result, ['synthetic question', 'synthetic AI answer'])
        evidence = result['records'][1]['evidence']
        self.assertEqual(evidence['message_id'], reply['result_id'])
        self.assertEqual(evidence['source_channel'], 'WEB_AI')
        self.assertEqual(evidence['sender_role'], 'AI')
        self.assertEqual(evidence['related_message_id'], source['id'])
        self.assertIsNone(evidence['external_event_id'])
        self.assertIsNone(evidence['provider_occurred_at'])
        self.c.check_integrity()

    def test_outbound_receipt_updates_status_without_rewriting_evidence(self):
        self.bind_channel()
        message = enqueue(self.c, self.owner, 'project-a', 'TELEGRAM', 'outbound fixture')
        before = self.evidence_rows()
        initial = export_project(self.c, self.owner, 'project-a')
        self.assert_chain(initial, ['outbound fixture'])
        self.assertEqual(initial['records'][0]['delivery_status'], 'PENDING')
        provider = Mock()
        provider.send.return_value = ('ACCEPTED', 'fixture-provider-ref')
        with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            outcome = drain_message(self.c, provider)
        self.assertEqual(outcome, {'status': 'ACCEPTED', 'provider_ref': 'fixture-provider-ref'})
        provider.send.assert_called_once_with('TELEGRAM', '123', 'outbound fixture', message['id'])
        self.assertEqual(self.evidence_rows(), before)
        exported = export_project(self.c, self.owner, 'project-a')
        self.assertEqual(exported['records'][0]['evidence'], initial['records'][0]['evidence'])
        self.assertEqual(exported['records'][0]['delivery_status'], 'ACCEPTED')
        self.assertEqual(exported['records'][0]['provider_ref'], 'fixture-provider-ref')
        self.c.check_integrity()


class MessageEvidenceHTTPTests(EvidenceFixture):
    request = http_fixtures.IdentityIntegrationTests.request

    def setUp(self):
        super().setUp()
        self.context_callback = None
        self.providers = Providers({}, clock=lambda: self.now)
        self.app = App(
            lambda: Center(self.root, {'v1': self.key}, 'v1',
                           clock=lambda: self.now, mail_ready=True,
                           scanner=lambda raw: True,
                           evidence_context=self.context_callback),
            self.providers, 'https://wenwenwenyiyiyi.work',
            'deploy/pr122-customer-center/ui',
            source_identity=lambda connection, headers: 'memory-fixture')

    def test_http_reused_orphan_messages_and_write_are_denied_without_body_leak(self):
        pid, _, body = self.reused_legacy_orphan()
        before = self.mutation_snapshot()
        status, _, response = self.request('messages/' + pid, auth=self.users['owner'])
        self.assertEqual(status, 403)
        self.assertEqual(set(response), {'error'})
        self.assertNotIn(body, json.dumps(response))
        status, _, response = self.request('message',
            {'project': pid, 'body': 'must not extend orphan history'}, self.users['owner'])
        self.assertEqual(status, 403)
        self.assertNotIn(body, json.dumps(response))
        self.assertEqual(self.mutation_snapshot(), before)

    def test_http_known_legacy_messages_remain_readable(self):
        mid, body = 'm_known_legacy_http', 'known legacy body remains accessible'
        self.c.db.execute("DELETE FROM settings WHERE k='message_evidence_schema'")
        self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',
                          (mid, 'project-a', self.owner, 'WEB',
                           self.c.encrypt(body.encode(), mid), 'ARCHIVED', self.now - 50))
        self.reopen()
        status, _, response = self.request('messages/project-a', auth=self.users['owner'])
        self.assertEqual(status, 200)
        self.assertEqual(response['messages'], [{'id': mid, 'channel': 'WEB',
            'body': body, 'status': 'ARCHIVED', 'created': self.now - 50}])
        exported = self.request('evidence/project-a', auth=self.users['owner'])
        self.assertEqual(exported[0], 200)
        self.assertEqual(exported[2]['records'][0]['evidence']['provenance'],
                         'LEGACY_BACKFILL_UNKNOWN_CONTEXT')

    def test_http_export_is_no_store_and_rechecks_current_rbac(self):
        self.c.message(self.owner, 'project-a', 'owner-only fixture')
        status, headers, result = self.request('evidence/project-a', auth=self.users['owner'])
        self.assertEqual(status, 200)
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertIn('private', headers['Cache-Control'])
        self.assert_chain(result, ['owner-only fixture'])
        self.assertEqual(self.request('evidence/project-a')[0], 403)
        self.assertEqual(self.request('evidence/project-a', auth=self.users['other'])[0], 403)
        self.assertEqual(self.request('evidence/project-b', auth=self.users['owner'])[0], 403)
        token = self.c.invite(self.owner, 'project-a', 'member@example.com', 'VIEWER')['invitation']
        self.c.accept_invite(self.member, token)
        self.assertEqual(self.request('evidence/project-a', auth=self.users['member'])[0], 200)
        self.c.revoke(self.owner, 'project-a', self.member)
        self.assertEqual(self.request('evidence/project-a', auth=self.users['member'])[0], 403)
        self.imported(2, [])
        self.assertEqual(self.request('evidence/project-a', auth=self.users['owner'])[0], 403)

    def test_http_message_rejects_client_provenance_and_uses_trusted_context(self):
        self.context_callback = Mock(return_value={'task_ref': 'server-approved-task'})
        for field, value in (('tenant_id', 'tenant-other'), ('sender_role', 'REVIEWER'),
                             ('provider_occurred_at', 1), ('external_event_id', 'forged'),
                             ('evidence_context', {'task_ref': 'forged'}),
                             ('task_ref', 'forged'), ('consent_version', 'forged')):
            with self.subTest(field=field):
                status, _, _ = self.request('message',
                    {'project': 'project-a', 'body': 'spoofed fixture', field: value},
                    self.users['owner'])
                self.assertEqual(status, 400)
        self.context_callback.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        self.assertEqual(self.evidence_rows(), [])
        status, _, _ = self.request('message',
            {'project': 'project-a', 'body': 'valid web fixture'}, self.users['owner'])
        self.assertEqual(status, 200)
        self.context_callback.assert_called_once_with(self.owner, 'project-a')
        result = self.request('evidence/project-a', auth=self.users['owner'])[2]
        self.assert_chain(result, ['valid web fixture'])
        evidence = result['records'][0]['evidence']
        self.assertEqual(evidence['task_ref'], 'server-approved-task')
        self.assertIsNone(evidence['consent_version'])
        self.assertIsNone(evidence['external_event_id'])

    def test_verified_telegram_http_preserves_event_time_id_and_replay(self):
        self.bind_channel()
        self.providers.config = {'telegram': {'webhook_secret': 'w' * 32}}
        body = {'update_id': 99, 'message': {
            'from': {'id': 123, 'is_bot': False}, 'chat': {'id': 123, 'type': 'private'},
            'date': self.now - 9, 'text': '/project project-a telegram fixture'}}
        headers = {'X-Telegram-Bot-Api-Secret-Token': 'w' * 32}
        parsed = self.providers.telegram(headers, canonical(body))
        self.assertIsInstance(parsed, tuple)
        self.assertEqual(parsed, ('99', '123', body['message']['text']))
        self.assertEqual(parsed.occurred_at, self.now - 9)
        self.assertEqual(self.request('webhooks/telegram', body, extra_headers=headers)[0], 200)
        before = self.evidence_rows()
        body['message']['text'] = '/project project-a replay cannot change original'
        self.assertEqual(self.request('webhooks/telegram', body, extra_headers=headers)[0], 200)
        self.assertEqual(self.evidence_rows(), before)
        result = self.request('evidence/project-a', auth=self.users['owner'])[2]
        self.assert_chain(result, ['telegram fixture'])
        evidence = result['records'][0]['evidence']
        self.assertEqual(evidence['external_event_id'], '99')
        self.assertEqual(evidence['provider_occurred_at'], self.now - 9)
        self.assertEqual(evidence['server_received_at'], self.now)
        self.assertEqual(evidence['source_channel'], 'TELEGRAM')
        body['update_id'] = 100
        self.assertEqual(self.request('webhooks/telegram', body, extra_headers={
            'X-Telegram-Bot-Api-Secret-Token': 'x' * 32})[0], 403)
        self.assertEqual(self.evidence_rows(), before)

    def test_verified_encrypted_feishu_http_preserves_event_time_id_and_replay(self):
        self.bind_channel('FEISHU', 'ou_user')
        self.providers.config = {'feishu': {'encrypt_key': 'encrypt-key',
            'verification_token': 'verification-token', 'app_id': 'app-id'}}
        event = provider_fixtures.ProviderTests.event(self)
        event['header']['event_id'] = 'feishu_evidence_fixture'
        event['header']['create_time'] = str((self.now - 7) * 1000)
        event['event']['message']['content'] = json.dumps({'text': '/project project-a feishu fixture'})
        headers, body = provider_fixtures.ProviderTests.signed(self, event)
        parsed = self.providers.feishu(headers, body)
        self.assertIsInstance(parsed, tuple)
        self.assertEqual(parsed, ('feishu_evidence_fixture', 'ou_user', '/project project-a feishu fixture'))
        self.assertEqual(parsed.occurred_at, self.now - 7)
        self.assertEqual(self.request('webhooks/feishu', body, extra_headers=headers)[0], 200)
        before = self.evidence_rows()
        self.assertEqual(self.request('webhooks/feishu', body, extra_headers=headers)[0], 200)
        self.assertEqual(self.evidence_rows(), before)
        result = self.request('evidence/project-a', auth=self.users['owner'])[2]
        self.assert_chain(result, ['feishu fixture'])
        evidence = result['records'][0]['evidence']
        self.assertEqual(evidence['external_event_id'], 'feishu_evidence_fixture')
        self.assertEqual(evidence['provider_occurred_at'], self.now - 7)
        self.assertEqual(evidence['server_received_at'], self.now)
        self.assertEqual(evidence['source_channel'], 'FEISHU')
        self.assertEqual(self.request('webhooks/feishu', body, extra_headers={
            **headers, 'X-Lark-Signature': '0' * 64})[0], 403)
        self.assertEqual(self.evidence_rows(), before)


if __name__ == '__main__':
    unittest.main()
