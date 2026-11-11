import unittest
from datetime import datetime
from credential_write_preparation import prepare_native_verified_save
from credential_key_binding import CredentialBindingHold
import test_credential_atomic_write as atomic_tests


class VerifiedFixture(atomic_tests.CryptoFixture):
    # Owner-provided native mark_verified delegation, with synthetic safe_record.
    def mark_verified(self, credential_id, status, verification_state,
                      permission_state, verified_time, metadata=None):
        return self.repository.update_status(
            credential_id, status, verification_state=verification_state,
            permission_state=permission_state, last_verified_time=verified_time,
            metadata=metadata)


class VerifiedPreparationTests(unittest.TestCase):
    def prepare(self, factory=VerifiedFixture):
        return prepare_native_verified_save(factory, 'project', 'fixture-master',
            dict(status='ACTIVE', verification_state='HEALTHY',
                 permission_state='READ_ONLY_VERIFIED',
                 verified_time=datetime(2026, 10, 19), metadata={'synthetic': True}),
            credential_id='id-1', api_key='api-fixture', api_secret='secret-fixture')

    def test_save_and_verification_share_one_envelope(self):
        record = self.prepare()['record']
        self.assertEqual(record['verification_state'], 'HEALTHY')
        self.assertEqual(record['last_verified_time'], '2026-10-19 00:00:00')
        self.assertNotIn('api_key', record)

    def test_verification_failure_produces_no_envelope(self):
        class Failing(VerifiedFixture):
            def mark_verified(self, *args, **kwargs):
                raise RuntimeError('synthetic')
        with self.assertRaises(CredentialBindingHold):
            self.prepare(Failing)

    def test_atomic_verified_commit_and_query(self):
        case = atomic_tests.AtomicTests('test_real_sqlite_commit_and_native_interface_read')
        case.setUp()
        try:
            for name in ('status', 'verification_state', 'permission_state', 'last_verified_time'):
                case.db.execute('ALTER TABLE credential_records ADD COLUMN ' + name + ' TEXT')
            case.db.commit()
            prepared = self.prepare()
            result = case.writer.commit('verified-op', prepared, None)
            self.assertEqual(result['status'], 'COMMITTED')
            self.assertEqual(case.writer.get('id-1')['verification_state'], 'HEALTHY')
            from credential_atomic_write import request_digest
            changes = case.db.total_changes
            self.assertEqual(case.writer.query('verified-op', request_digest(prepared, None))['status'], 'COMMITTED')
            self.assertEqual(case.db.total_changes, changes)
        finally:
            case.tearDown()
