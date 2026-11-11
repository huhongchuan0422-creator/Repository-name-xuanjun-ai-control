import unittest
from accept_native_atomic_copy import native_factory


class NativeExtractionTests(unittest.TestCase):
    def test_missing_native_method_stops_extraction(self):
        with self.assertRaises((RuntimeError, StopIteration)):
            native_factory(b'class CredentialStore:\n    pass\n')

    def test_extraction_does_not_run_business_imports_or_constructor(self):
        source = b'''
raise RuntimeError('must not execute business module')
def fingerprint_api_key(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12]
class CredentialStore:
    ENV_MASTER_KEY = 'TEST_ONLY'
    def __init__(self, repository=None, master_key=None, key_version='v1'):
        raise RuntimeError('must not run business constructor')
    def _load_master_key(self, key):
        return key.encode()
    def _encrypt(self, plaintext, aad):
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.master_key).encrypt(nonce, plaintext.encode(), aad.encode())
        return base64.b64encode(ciphertext).decode(), base64.b64encode(nonce).decode()
    def _decrypt(self, ciphertext, nonce, aad):
        return AESGCM(self.master_key).decrypt(base64.b64decode(nonce), base64.b64decode(ciphertext), aad.encode()).decode()
    def save_credential(self, **values):
        return self.repository.save(values)
    def load_credential(self, credential_id):
        return self.repository.get(credential_id)
'''
        store = native_factory(source)(repository=object(), master_key='a'*32)
        ciphertext, nonce = store._encrypt('synthetic', 'fixture-aad')
        self.assertEqual(store._decrypt(ciphertext, nonce, 'fixture-aad'), 'synthetic')
        self.assertEqual(store.key_version, 'v1')


if __name__ == '__main__':
    unittest.main()
