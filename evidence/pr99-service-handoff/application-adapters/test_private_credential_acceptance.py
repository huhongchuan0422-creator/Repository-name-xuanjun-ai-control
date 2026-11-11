"""Real AES-GCM with synthetic records/source; not production host acceptance."""
import base64
import os
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import credential_key_binding as adapter
import accept_private_credential_bindings as acceptance

SOURCE = b'''
class CredentialStore:
    ENV_MASTER_KEY = 'FIXTURE_KEY'
    def __init__(self, repository=None, master_key=None, key_version='v1'):
        pass
    def _load_master_key(self, master_key):
        return base64.b64decode(master_key, validate=True)
    def _decrypt(self, ciphertext, nonce, aad):
        return AESGCM(self.master_key).decrypt(base64.b64decode(nonce),
            base64.b64decode(ciphertext), aad.encode()).decode()
    def load_credential(self, credential_id):
        row = self.repository.get(credential_id)
        aad = row['credential_id'] + ':' + row['customer_id'] + ':' + row['account_id']
        return {field: self._decrypt(row[field + '_ciphertext'],
            row[field + '_nonce'], aad + ':' + field) for field in ('key', 'secret')}
'''


class Tests(unittest.TestCase):
    def setUp(self):
        self.rawkeys = {'project': os.urandom(32), 'portal': os.urandom(32)}
        self.keys = {k: base64.b64encode(v).decode() for k, v in self.rawkeys.items()}
        self.rows = []
        self.name, self.factory = acceptance.original_pure_factory(SOURCE)
        for i in range(3):
            row = dict(credential_id=str(i), customer_id='customer', account_id='account',
                       algorithm='AES-GCM', key_version='v1', legacy_migration_required=0)
            key = self.rawkeys['project' if i < 2 else 'portal']
            for field in ('key', 'secret'):
                nonce = os.urandom(12)
                aad = (str(i) + ':customer:account:' + field).encode()
                row[field + '_nonce'] = base64.b64encode(nonce).decode()
                row[field + '_ciphertext'] = base64.b64encode(
                    AESGCM(key).encrypt(nonce, b'PRIVATE_SYNTHETIC_VALUE', aad)).decode()
            self.rows.append(row)

    def test_real_crypto_all_three_with_distinct_keys(self):
        bindings = acceptance.verify_rows(adapter, self.rows, self.factory, self.keys)
        self.assertEqual([bindings[str(i)]['key_ref'] for i in range(3)],
                         ['project', 'project', 'portal'])
        self.assertNotIn('PRIVATE_SYNTHETIC_VALUE', repr(bindings))
        for value in self.keys.values():
            self.assertNotIn(value, repr(bindings))

    def test_wrong_project_key_holds_without_portal_fallback(self):
        self.keys['project'] = self.keys['portal']
        with self.assertRaisesRegex(adapter.CredentialBindingHold, 'NATIVE_CREDENTIAL'):
            acceptance.verify_rows(adapter, self.rows, self.factory, self.keys)

    def test_changed_aad_cannot_decrypt(self):
        self.rows[0]['account_id'] = 'changed'
        with self.assertRaises(adapter.CredentialBindingHold):
            acceptance.verify_rows(adapter, self.rows, self.factory, self.keys)

    def test_duplicate_identity_rejected(self):
        self.rows[1]['credential_id'] = self.rows[0]['credential_id']
        with self.assertRaisesRegex(RuntimeError, 'EXACT_SNAPSHOT'):
            acceptance.verify_rows(adapter, self.rows, self.factory, self.keys)

    def test_read_regular_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'original'
            p.write_bytes(b'synthetic')
            link = Path(d) / 'link'
            link.symlink_to(p)
            with self.assertRaisesRegex(RuntimeError, 'SYMLINK'):
                acceptance.read_regular(link, 100)

    def test_receipt_never_overwrites_prior_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'receipt.json'
            acceptance.write_new(p, {'status': 'HOLD'})
            before = p.read_bytes()
            with self.assertRaises(FileExistsError):
                acceptance.write_new(p, {'status': 'PASS'})
            self.assertEqual(p.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
