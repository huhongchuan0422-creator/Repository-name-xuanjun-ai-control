import base64
import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from credential_atomic_write import (AtomicCredentialWriter, BoundCredentialStore,
                                     SCHEMA_SQL, request_digest)
from credential_key_binding import CredentialBindingHold, fingerprint


class CryptoFixture:
    """Synthetic app interface, real AES-GCM; not Tokyo source acceptance."""
    def __init__(self, repository, master_key):
        self.repository = repository
        self.key = hashlib.sha256(master_key.encode()).digest()

    def save_credential(self, **kw):
        row = dict(credential_id=kw['credential_id'], customer_id='customer',
                   account_id='account', algorithm='AES-GCM', key_version='v1',
                   legacy_migration_required=0, metadata={'fixture': True})
        aad = row['credential_id']+':customer:account'
        for field, value in [('key', kw['api_key']), ('secret', kw['api_secret'])]:
            nonce = os.urandom(12)
            row[field+'_nonce'] = base64.b64encode(nonce).decode()
            row[field+'_ciphertext'] = base64.b64encode(AESGCM(self.key).encrypt(
                nonce, value.encode(), (aad+':'+field).encode())).decode()
        return self.repository.save(row)

    def load_credential(self, credential_id):
        row = self.repository.get(credential_id)
        aad = row['credential_id']+':'+row['customer_id']+':'+row['account_id']
        result = {}
        for field, out in [('key', 'api_key'), ('secret', 'api_secret')]:
            result[out] = AESGCM(self.key).decrypt(
                base64.b64decode(row[field+'_nonce']),
                base64.b64decode(row[field+'_ciphertext']),
                (aad+':'+field).encode()).decode()
        return result


class AtomicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name)/'existing.sqlite')
        self.db = sqlite3.connect(self.path)
        self.db.execute('CREATE TABLE credential_records ('
                        'credential_id TEXT PRIMARY KEY,customer_id TEXT,account_id TEXT,'
                        'algorithm TEXT,key_version TEXT,legacy_migration_required INTEGER,'
                        'key_ciphertext TEXT,key_nonce TEXT,secret_ciphertext TEXT,'
                        'secret_nonce TEXT,metadata_json TEXT)')
        for statement in SCHEMA_SQL:
            self.db.execute(statement)
        self.db.commit()
        self.held = True
        self.writer = AtomicCredentialWriter(self.db, lambda: self.held)
        self.store = BoundCredentialStore(self.writer, CryptoFixture,
                                          {'project': 'fixture-master'}, 'project')
        self.prepared = self.store.prepare_save(credential_id='id-1',
                                                api_key='api-fixture', api_secret='secret-fixture')

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def commit(self):
        return self.writer.commit('operation-1', self.prepared, None)

    def test_real_sqlite_commit_and_native_interface_read(self):
        self.assertEqual(self.commit()['status'], 'COMMITTED')
        self.assertEqual(self.store.load_credential('id-1')['api_secret'], 'secret-fixture')
        self.assertNotIn('secret-fixture', self.db.execute('SELECT sql FROM sqlite_master').fetchall())

    def test_restart_queries_lost_result_without_write(self):
        self.commit()
        self.db.close()
        self.db = sqlite3.connect(self.path)
        writer = AtomicCredentialWriter(self.db, lambda: True)
        before = self.db.total_changes
        result = writer.query('operation-1', request_digest(self.prepared, None))
        self.assertEqual(result['status'], 'COMMITTED')
        self.assertEqual(before, self.db.total_changes)

    def test_binding_failure_rolls_back_record_and_result(self):
        self.db.execute("CREATE TRIGGER fail_binding BEFORE INSERT ON pr99_credential_key_bindings BEGIN SELECT RAISE(ABORT,'fixture'); END")
        self.db.commit()
        with self.assertRaises(CredentialBindingHold): self.commit()
        self.assertIsNone(self.writer.get('id-1'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM pr99_credential_write_results').fetchone()[0], 0)

    def test_result_failure_rolls_back_binding_and_record(self):
        self.db.execute("CREATE TRIGGER fail_result BEFORE INSERT ON pr99_credential_write_results BEGIN SELECT RAISE(ABORT,'fixture'); END")
        self.db.commit()
        with self.assertRaises(CredentialBindingHold): self.commit()
        self.assertIsNone(self.writer.get('id-1'))
        self.assertIsNone(self.writer.binding('id-1'))

    def test_duplicate_exact_operation_does_not_write(self):
        self.commit(); before = self.db.total_changes
        self.assertEqual(self.commit()['status'], 'COMMITTED')
        self.assertEqual(self.db.total_changes, before)

    def test_wrong_operation_digest_rejected(self):
        self.commit()
        with self.assertRaises(CredentialBindingHold):
            self.writer.query('operation-1', 'wrong')

    def test_unknown_does_not_create_result(self):
        self.assertEqual(self.writer.query('absent', 'digest')['status'], 'UNKNOWN_QUERY_ONLY')
        self.assertIsNone(self.writer.get('id-1'))

    def test_writer_loss_prevents_commit(self):
        self.held = False
        with self.assertRaises(CredentialBindingHold): self.commit()
        self.assertFalse(self.db.in_transaction)

    def test_outer_transaction_not_committed(self):
        self.db.execute('BEGIN')
        with self.assertRaises(CredentialBindingHold): self.commit()
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()

    def test_create_cannot_overwrite_existing(self):
        self.commit()
        changed = self.store.prepare_save(credential_id='id-1',api_key='new',api_secret='new')
        with self.assertRaises(CredentialBindingHold):
            self.writer.commit('operation-2', changed, None)
        self.assertEqual(self.store.load_credential('id-1')['api_key'], 'api-fixture')

    def test_compare_and_swap_updates_binding_with_record(self):
        self.commit()
        old = fingerprint(self.writer.get('id-1'))
        changed = self.store.prepare_save(credential_id='id-1',api_key='new',api_secret='new')
        self.writer.commit('operation-2', changed, old)
        self.assertEqual(self.store.load_credential('id-1')['api_key'], 'new')
        self.assertEqual(self.writer.binding('id-1')['record_sha256'], fingerprint(self.writer.get('id-1')))

    def test_writer_loss_before_commit_rolls_back_all(self):
        calls = [0]
        def guard():
            calls[0] += 1
            return calls[0] < 4
        self.writer.guard = guard
        with self.assertRaises(CredentialBindingHold): self.commit()
        self.assertIsNone(self.writer.get('id-1'))
        self.assertIsNone(self.writer.binding('id-1'))

    def test_commit_acknowledgement_loss_is_query_only(self):
        class LostAck(sqlite3.Connection):
            def commit(connection):
                super(LostAck, connection).commit()
                raise OSError('fixture lost acknowledgement')
        other = sqlite3.connect(self.path, factory=LostAck)
        try:
            writer = AtomicCredentialWriter(other, lambda: True)
            with self.assertRaisesRegex(CredentialBindingHold, 'WRITE_UNKNOWN_QUERY_ONLY'):
                writer.commit('operation-1', self.prepared, None)
        finally:
            other.close()
        self.assertEqual(self.writer.query('operation-1', request_digest(self.prepared, None))['status'], 'COMMITTED')

    def test_missing_schema_not_initialized(self):
        self.db.execute('DROP TABLE pr99_credential_write_results'); self.db.commit()
        with self.assertRaises(CredentialBindingHold):
            AtomicCredentialWriter(self.db, lambda: True)
        self.assertIsNone(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='pr99_credential_write_results'").fetchone())


if __name__ == '__main__': unittest.main()
