"""Selection/race tests with a native-store fixture; not host acceptance."""
import unittest
import credential_key_binding as c


class Tests(unittest.TestCase):
    def setUp(self):
        self.rows = {}
        for i in range(3):
            row = {name: name + str(i) for name in c.FIELDS}
            row.update(credential_id=str(i), key_version='v1',
                       legacy_migration_required=0)
            self.rows[str(i)] = row
        self.calls = []
        outer = self
        class Repository:
            def get(self, identifier):
                row = outer.rows.get(identifier)
                return dict(row) if row is not None else None
        self.repo = Repository()
        class Store:
            def __init__(self, repository, master_key):
                self.repository = repository
                self.key = master_key
                outer.calls.append(master_key)
            def load_credential(self, identifier):
                expected = 'old' if identifier in ('0', '1') else 'current'
                if self.key != expected:
                    raise RuntimeError('PRIVATE_INPUT')
                self.repository.get(identifier)
                return {'fixture': identifier}
        self.factory = Store
        self.bindings = {i: {'record_sha256': c.fingerprint(r),
                            'key_ref': 'project' if i != '2' else 'portal'}
                         for i, r in self.rows.items()}

    def reader(self):
        return c.BoundCredentialReader(self.repo, self.factory, self.bindings,
                                       {'project': 'old', 'portal': 'current'})

    def test_same_version_selects_explicit_record_keys(self):
        reader = self.reader()
        for i in self.rows:
            self.assertEqual(reader.load_credential(i), {'fixture': i})
        self.assertEqual(self.calls, ['old', 'old', 'current'])

    def test_unbound_record_never_tries_a_key(self):
        with self.assertRaises(c.CredentialBindingHold):
            self.reader().load_credential('unknown')
        self.assertEqual(self.calls, [])

    def test_changed_ciphertext_rejected_before_native_call(self):
        reader = self.reader()
        self.rows['0']['key_nonce'] = 'changed'
        with self.assertRaises(c.CredentialBindingHold):
            reader.load_credential('0')
        self.assertEqual(self.calls, [])

    def test_wrong_explicit_key_does_not_fallback_or_expose_error(self):
        self.bindings['0']['key_ref'] = 'portal'
        with self.assertRaises(c.CredentialBindingHold) as error:
            self.reader().load_credential('0')
        self.assertEqual(self.calls, ['current'])
        self.assertNotIn('PRIVATE_INPUT', str(error.exception))
        self.assertIsNone(error.exception.__cause__)

    def test_source_mutation_during_decrypt_holds(self):
        factory = self.factory
        outer = self
        def mutating_factory(**kwargs):
            store = factory(**kwargs)
            original = store.load_credential
            def load(identifier):
                result = original(identifier)
                outer.rows[identifier]['account_id'] = 'changed'
                return result
            store.load_credential = load
            return store
        self.factory = mutating_factory
        with self.assertRaisesRegex(c.CredentialBindingHold, 'DURING_READ'):
            self.reader().load_credential('0')

    def test_caller_binding_mutation_does_not_change_selection(self):
        reader = self.reader()
        self.bindings['0']['key_ref'] = 'portal'
        self.assertEqual(reader.load_credential('0'), {'fixture': '0'})
        self.assertEqual(self.calls, ['old'])

    def test_missing_key_rejected(self):
        self.bindings['0']['key_ref'] = 'absent'
        with self.assertRaises(c.CredentialBindingHold):
            self.reader()

    def test_legacy_record_rejected(self):
        self.rows['0']['legacy_migration_required'] = 1
        with self.assertRaises(c.CredentialBindingHold):
            c.fingerprint(self.rows['0'])


if __name__ == '__main__':
    unittest.main()
