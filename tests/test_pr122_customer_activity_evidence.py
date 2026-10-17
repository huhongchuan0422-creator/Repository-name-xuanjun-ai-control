"""Offline synthetic material, change, and delivery evidence regressions."""
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

from scripts.pr122_customer_core import Center, Denied, Unavailable, canonical
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_evidence import export_project
from scripts.pr122_customer_activity_evidence import export_project as export_activity
from scripts.pr122_customer_activity_evidence import verify as verify_activity
from scripts.pr122_customer_providers import drain_message, enqueue
from tests import test_pr122_customer_center as fixtures


class ActivityEvidenceTests(unittest.TestCase):
    setUp = fixtures.CustomerTests.setUp
    imported = fixtures.CustomerTests.imported
    save = fixtures.CustomerTests.save
    accept = fixtures.CustomerTests.accept

    def reopen(self):
        self.c.db.close()
        self.c = Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now,
                        mail_ready=True, scanner=lambda raw: True)

    def rows(self, table='project_activity_evidence'):
        return [tuple(row) for row in self.c.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]

    def bind(self):
        challenge = self.c.binding_challenge(self.owner, 'project-a', 'TELEGRAM', '123')['challenge']
        self.c.channel_event('TELEGRAM', 'activity_binding', '123', '/bind ' + challenge)
        pending = self.c.pending_links(self.owner, 'project-a')[0]
        self.c.confirm_link(self.owner, 'project-a', pending['id'])

    def assert_proof(self, record):
        proof = record['evidence']
        unsigned = {key: value for key, value in proof.items() if key != 'record_digest'}
        self.assertEqual(proof['record_digest'], hashlib.sha256(canonical(unsigned)).hexdigest())
        if proof['audit_seq'] is not None:
            audit = self.c.db.execute('SELECT project,sha FROM audit WHERE seq=?', (proof['audit_seq'],)).fetchone()
            self.assertEqual(tuple(audit), (proof['project_id'], proof['audit_digest']))

    def test_material_save_review_refs_and_reason_are_bound_without_document_bytes(self):
        self.accept()
        result = export_project(self.c, self.owner, 'project-a')['project_activity']
        self.assertEqual(result['scope'], 'AUTHORIZED_SUBSET')
        self.assertEqual(result['assurance'], 'LOCAL_HASH_CHAIN_NOT_EXTERNAL_ATTESTATION')
        records = result['records']
        self.assertEqual([r['details']['kind'] for r in records],
                         ['SAVE', 'submit', 'begin_review', 'approve'])
        self.assertEqual(len(records), 4)
        object_id = self.c.db.execute('SELECT id FROM objects').fetchone()[0]
        self.assertEqual(records[0]['details']['object_ref'], object_id)
        self.assertEqual(records[-1]['details']['review_reason'], 'checked supplied document')
        self.assertEqual(records[-1]['details']['source_version'], records[0]['details']['id'])
        previous = '0' * 64
        for record in records:
            self.assert_proof(record)
            proof = record['evidence']
            self.assertEqual(proof['source_kind'], 'MATERIAL')
            self.assertEqual((proof['tenant_id'], proof['customer_id']), ('tenant-a', 'customer-a'))
            self.assertEqual(proof['previous_record_digest'], previous)
            previous = proof['record_digest']
        self.assertNotIn('fictional document', json.dumps(result))
        self.assertNotIn('%PDF', json.dumps(result))
        self.c.check_integrity()

    def test_internal_history_stays_hidden_after_public_reclassification(self):
        internal = {**self.q, 'id': 'internal', 'category': 'INTERNAL'}
        self.imported(2, [{**self.p, 'requirements': [internal]}])
        saved = self.c.save(self.reviewer, 'project-a', 'internal', 0,
                            'DOCUMENT', b'%PDF-private internal fixture')
        self.assertEqual(export_activity(self.c, self.owner, 'project-a')['records'], [])
        reviewer = export_activity(self.c, self.reviewer, 'project-a')['records']
        self.assertEqual([r['details']['id'] for r in reviewer], [saved['version']])
        self.imported(3, [{**self.p, 'requirements': [{**internal, 'category': 'MATERIAL'}]}])
        owner = export_project(self.c, self.owner, 'project-a')['project_activity']
        self.assertEqual(owner['records'], [])
        self.assertNotIn(saved['version'], json.dumps(owner))
        self.assertEqual(len(export_activity(self.c, self.reviewer, 'project-a')['records']), 1)
        self.c.check_integrity()

    def test_current_internal_category_hides_previously_public_history(self):
        saved = self.save()
        self.imported(2, [{**self.p, 'requirements': [{**self.q, 'category': 'INTERNAL'}]}])
        self.assertEqual(export_activity(self.c, self.owner, 'project-a')['records'], [])
        self.assertEqual(export_activity(self.c, self.reviewer, 'project-a')['records'][0]['details']['id'],
                         saved['version'])

    def test_dedicated_reference_value_is_never_exported(self):
        requirement = {**self.q, 'id': 'secret', 'submission_type': 'SECRETREF'}
        self.imported(2, [{**self.p, 'requirements': [requirement]}])
        self.c.secretref = lambda *args: True
        self.c.save(self.owner, 'project-a', 'secret', 0, 'SECRETREF', 'private-dedicated-reference-fixture')
        result = export_project(self.c, self.owner, 'project-a')
        details = result['project_activity']['records'][0]['details']
        self.assertTrue(details['dedicated_reference_recorded'])
        self.assertIsNone(details['object_ref'])
        self.assertNotIn('private-dedicated-reference-fixture', json.dumps(result))

    def test_change_capture_exports_only_refs_and_digest_and_reads_are_audited(self):
        payload = {'state': 'REQUESTED', 'request': 'private change request fixture',
                   'nested': {'dedicated_reference': 'private change reference'}}
        created = Changes(self.c)._append(self.owner, 'project-a', 'change_fixture', 0, 'REQUEST', payload)
        result = export_project(self.c, self.owner, 'project-a')['project_activity']['records']
        self.assertEqual(len(result), 1)
        record = result[0]
        self.assert_proof(record)
        self.assertEqual(record['evidence']['source_kind'], 'CHANGE')
        self.assertEqual(record['details']['id'], created['event_id'])
        self.assertEqual(record['details']['case_id'], 'change_fixture')
        self.assertEqual(record['details']['payload_sha256'], hashlib.sha256(canonical(payload)).hexdigest())
        self.assertNotIn('private change request fixture', json.dumps(result))
        self.assertNotIn('private change reference', json.dumps(result))
        listed = Changes(self.c).list(self.owner, 'project-a')
        self.assertEqual(listed['cases'][0]['events'][0]['payload'], payload)
        audit = self.c.db.execute('SELECT project,actor,event,object_id FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        self.assertEqual(tuple(audit), ('project-a', self.owner, 'CHANGE_HISTORY_READ', 'change_fixture'))
        self.assertEqual(len(self.rows()), 1)
        self.c.check_integrity()

    def test_replace_primary_and_unique_collisions_cannot_rewrite_history(self):
        self.save()
        Changes(self.c)._append(self.owner, 'project-a', 'replace_fixture', 0,
                                'REQUEST', {'state': 'REQUESTED', 'request': 'fixture'})
        for table in ('versions', 'change_events', 'audit', 'project_activity_evidence'):
            row = self.c.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid LIMIT 1').fetchone()
            names = list(row.keys())
            variants = [dict(row)]
            if table in ('versions', 'change_events'):
                variants.append({**dict(row), 'id': 'fresh_collision_fixture'})
            elif table == 'project_activity_evidence':
                variants.append({**dict(row), 'seq': 1000000})
            before = self.rows(table)
            for variant in variants:
                with self.subTest(table=table, variant=variant.get('id', variant.get('seq'))):
                    with self.assertRaises(sqlite3.DatabaseError), self.c.tx():
                        self.c.db.execute('INSERT OR REPLACE INTO ' + table + '(' + ','.join(names)
                                          + ') VALUES(' + ','.join('?' for _ in names) + ')',
                                          tuple(variant[name] for name in names))
                    self.assertEqual(self.rows(table), before)
        before = self.rows()
        for sql in ('UPDATE project_activity_evidence SET sha=sha', 'DELETE FROM project_activity_evidence'):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError), self.c.tx():
                self.c.db.execute(sql)
            self.assertEqual(self.rows(), before)
        self.c.check_integrity()

    def test_key_encrypted_source_replacement_is_detected_by_snapshot_digest(self):
        saved = self.save()
        # Simulate privileged storage corruption in this disposable fixture only.
        # Ordinary writes remain covered by the separate append-only test.
        self.c.db.execute('DROP TRIGGER versions_no_update')
        original = self.c.db.execute('SELECT payload FROM versions WHERE id=?', (saved['version'],)).fetchone()[0]
        payload = json.loads(self.c.decrypt(original, saved['version']))
        forged = self.c.encrypt(canonical({**payload, 'reason': 'forged encrypted review metadata'}), saved['version'])
        self.c.db.execute('UPDATE versions SET payload=? WHERE id=?', (forged, saved['version']))
        with self.assertRaisesRegex(Denied, 'ACTIVITY_INTEGRITY'):
            verify_activity(self.c)
        with self.assertRaisesRegex(Denied, 'ACTIVITY_INTEGRITY'):
            export_project(self.c, self.owner, 'project-a')
        with self.assertRaisesRegex(Denied, 'ACTIVITY_INTEGRITY'):
            self.c.check_integrity()

    def test_legacy_orphan_version_blocks_reused_project_checklist_download_and_export(self):
        pid, vid, oid = 'orphan-material-project', 'v_legacy_orphan', 'o_legacy_orphan'
        body = b'%PDF-orphan private material'
        self.c.db.execute("DELETE FROM settings WHERE k='activity_evidence_schema'")
        self.c.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)',
                          (vid, pid, 'license', 1, self.owner, 'SAVE',
                           self.c.encrypt(canonical({'category': 'MATERIAL', 'object_id': oid}), vid),
                           None, self.now - 50))
        self.c.db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?,?,?)',
                          (oid, vid, pid, 'application/pdf', len(body),
                           hashlib.sha256(body).hexdigest(), 'CLEAN', 'v1'))
        (self.c.objects / oid).write_bytes(self.c.encrypt(body, 'object:' + pid + ':' + oid))
        self.reopen()
        records, _ = verify_activity(self.c)
        proof = records[0][0]
        self.assertIsNone(proof['tenant_id'])
        self.assertIsNone(proof['customer_id'])
        self.assertEqual(proof['provenance'], 'LEGACY_BACKFILL_UNKNOWN_CONTEXT')
        self.imported(2, [self.p, {**self.p, 'id': pid, 'tenant': 'new-tenant', 'customer': 'new-customer'}])
        for operation in (lambda: self.c.checklist(self.owner, pid),
                          lambda: self.c.download(self.owner, pid, oid),
                          lambda: export_project(self.c, self.owner, pid),
                          lambda: Changes(self.c).list(self.owner, pid)):
            with self.assertRaisesRegex(Denied, 'ACTIVITY_PROJECT_IDENTITY_DRIFT'):
                operation()
        self.c.check_integrity()  # Quarantined history is still preservable by operators.

    def test_delivery_outcomes_are_append_only_and_unknown_is_not_retried(self):
        self.bind()
        first = enqueue(self.c, self.owner, 'project-a', 'TELEGRAM', 'accepted delivery fixture')
        initial = self.rows()
        provider = Mock()
        provider.send.return_value = ('ACCEPTED', 'fixture-receipt')
        self.assertEqual(drain_message(self.c, provider)['status'], 'ACCEPTED')
        records = export_activity(self.c, self.owner, 'project-a')['records']
        self.assertEqual([r['details']['delivery_status'] for r in records], ['PENDING', 'UNKNOWN', 'ACCEPTED'])
        self.assertEqual([r['details']['message_id'] for r in records], [first['id']] * 3)
        self.assertEqual(records[-1]['details']['provider_ref'], 'fixture-receipt')
        self.assertEqual(self.rows()[:len(initial)], initial)
        second = enqueue(self.c, self.owner, 'project-a', 'TELEGRAM', 'timeout delivery fixture')
        provider.send.side_effect = TimeoutError()
        self.assertEqual(drain_message(self.c, provider), {'status': 'UNKNOWN'})
        calls = provider.send.call_count
        self.assertEqual(drain_message(self.c, provider), {'pending': False})
        self.assertEqual(provider.send.call_count, calls)
        records = export_activity(self.c, self.owner, 'project-a')['records']
        self.assertEqual([r['details']['delivery_status'] for r in records
                          if r['details']['message_id'] == second['id']], ['PENDING', 'UNKNOWN'])
        for record in records:
            self.assert_proof(record)
        self.c.check_integrity()

    def test_legacy_activity_backfill_and_reopen_are_idempotent(self):
        self.c.db.execute("DELETE FROM settings WHERE k='activity_evidence_schema'")
        self.c.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)',
                          ('v_legacy_known', 'project-a', 'license', 1, self.owner, 'SAVE',
                           self.c.encrypt(canonical({'category': 'MATERIAL'}), 'v_legacy_known'),
                           None, self.now - 40))
        self.c.db.execute('INSERT INTO change_events VALUES(?,?,?,?,?,?,?,?)',
                          ('ce_legacy_known', 'project-a', 'legacy_case', 1, 'REQUEST', self.owner,
                           self.c.encrypt(canonical({'request': 'legacy private change'}), 'ce_legacy_known'),
                           self.now - 30))
        self.reopen()
        records = export_activity(self.c, self.owner, 'project-a')['records']
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record['evidence']['provenance'], 'LEGACY_BACKFILL_UNKNOWN_CONTEXT')
            self.assertIsNone(record['evidence']['audit_seq'])
            self.assertIsNone(record['evidence']['audit_digest'])
            self.assertEqual(record['evidence']['tenant_id'], 'tenant-a')
        before = self.rows()
        self.now += 10
        self.reopen()
        self.assertEqual(self.rows(), before)
        self.c.check_integrity()

    def test_activity_cap_rejects_before_any_bulk_or_project_decryption(self):
        self.save()
        oid = self.c.db.execute('SELECT id FROM objects').fetchone()[0]
        with patch('scripts.pr122_customer_activity_evidence.MAX_ACTIVITY', 0), \
                patch.object(self.c, 'decrypt', wraps=self.c.decrypt) as decrypt:
            for operation in (lambda: self.c.checklist(self.owner, 'project-a'),
                              lambda: self.c.download(self.owner, 'project-a', oid),
                              lambda: export_project(self.c, self.owner, 'project-a'),
                              lambda: Changes(self.c).list(self.owner, 'project-a')):
                with self.assertRaisesRegex(Unavailable, 'BOUNDED_ACTIVITY_REQUIRES_OPERATOR'):
                    operation()
            decrypt.assert_not_called()

    def test_activity_read_audit_uses_current_actor_project_and_transaction(self):
        self.save()
        observed = []
        original = self.c.audit

        def audit(project, actor, event, obj):
            observed.append((project, actor, event, obj, self.c.db.in_transaction))
            return original(project, actor, event, obj)

        with patch.object(self.c, 'audit', side_effect=audit):
            result = export_activity(self.c, self.reviewer, 'project-a')
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(observed, [('project-a', self.reviewer, 'ACTIVITY_EVIDENCE_READ', '1', True)])
        row = self.c.db.execute('SELECT project,actor,event,object_id FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        self.assertEqual(tuple(row), observed[0][:4])


if __name__ == '__main__':
    unittest.main()
