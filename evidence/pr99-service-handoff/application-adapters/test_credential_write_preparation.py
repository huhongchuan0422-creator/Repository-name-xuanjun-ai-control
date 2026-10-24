import unittest
from credential_write_preparation import prepare_native_save
from credential_key_binding import CredentialBindingHold, FIELDS


class NativeFixture:
    def __init__(self, repository, master_key):
        self.repository = repository

    def save_credential(self, **kw):
        row = {k: 'encrypted-fixture' for k in FIELDS}
        row.update(credential_id=kw['credential_id'], legacy_migration_required=0)
        return self.repository.save(row)

    def load_credential(self, credential_id):
        assert self.repository.get(credential_id)
        return {'api_key': 'fixture-key', 'api_secret': 'fixture-secret'}


class PreparationTests(unittest.TestCase):
    def test_native_false_normalized_to_sqlite_integer(self):
        from credential_write_preparation import _CaptureRepository
        from credential_key_binding import fingerprint
        capture = _CaptureRepository()
        row = {k: 'encrypted-fixture' for k in FIELDS}
        row['legacy_migration_required'] = False
        saved = capture.save(row)
        self.assertIs(type(saved['legacy_migration_required']), int)
        stored = dict(saved, legacy_migration_required=0)
        self.assertEqual(fingerprint(saved), fingerprint(stored))

    def call(self, factory=NativeFixture, **changes):
        args = dict(credential_id='explicit-id', api_key='fixture-key',
                    api_secret='fixture-secret')
        args.update(changes)
        return prepare_native_save(factory, 'project', 'fixture-master', **args)

    def test_private_envelope_no_plaintext_and_no_commit(self):
        result = self.call()
        self.assertEqual(result['state'], 'PREPARED_NOT_COMMITTED')
        self.assertNotIn('fixture-secret', repr(result))
        self.assertNotIn('fixture-key', repr(result))
        self.assertEqual(result['binding']['key_ref'], 'project')

    def test_requires_stable_id(self):
        with self.assertRaises(CredentialBindingHold):
            self.call(credential_id=None)

    def test_failed_roundtrip_rejected(self):
        with self.assertRaises(CredentialBindingHold):
            self.call(api_secret='different')

    def test_multiple_native_writes_rejected(self):
        class Twice(NativeFixture):
            def save_credential(self, **kw):
                super().save_credential(**kw)
                return super().save_credential(**kw)
        with self.assertRaises(CredentialBindingHold):
            self.call(Twice)

    def test_native_error_sanitized(self):
        def bad(**kw):
            raise RuntimeError('private-master-value')
        with self.assertRaisesRegex(CredentialBindingHold,
                                    '^NATIVE_WRITE_PREPARATION_FAILED$'):
            self.call(bad)


if __name__ == '__main__':
    unittest.main()
