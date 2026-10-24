"""Explicit historical key selection for PR99 read-only credential acceptance.

No discovery, fallback, key rotation, database writes, or service hooks. The
caller supplies verified original application objects and private key inputs.
This component is not a production installation or a complete portal adapter.
"""
import hashlib
import json
from types import MappingProxyType


class CredentialBindingHold(RuntimeError):
    pass


FIELDS = ('credential_id', 'customer_id', 'account_id', 'algorithm',
          'key_version', 'legacy_migration_required', 'key_ciphertext',
          'key_nonce', 'secret_ciphertext', 'secret_nonce')


def fingerprint(record):
    try:
        payload = {name: record[name] for name in FIELDS}
        if any(not isinstance(payload[name], str) or not payload[name]
               for name in FIELDS if name != 'legacy_migration_required'):
            raise ValueError()
        if payload['legacy_migration_required'] not in (False, 0):
            raise ValueError()
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode()
        return hashlib.sha256(encoded).hexdigest()
    except Exception:
        raise CredentialBindingHold('RECORD_BINDING_INVALID') from None


class _SingleRecordRepository:
    def __init__(self, record):
        self._record = dict(record)

    def get(self, credential_id):
        if credential_id != self._record['credential_id']:
            raise CredentialBindingHold('UNEXPECTED_RECORD_REQUEST')
        return dict(self._record)


class BoundCredentialReader:
    """Read exact records with their explicit key, delegating native decryption.

    bindings is private: credential ID -> {record_sha256, key_ref}. key_inputs
    maps opaque local references to original master-key strings. Neither is a
    public receipt. No key is selected by the ambiguous historical 'v1' label.
    """
    def __init__(self, repository, native_store_factory, bindings, key_inputs):
        self._repository = repository
        self._factory = native_store_factory
        self._bindings = MappingProxyType({k: dict(v) for k, v in bindings.items()})
        self._keys = MappingProxyType(dict(key_inputs))
        if not self._bindings or not self._keys:
            raise CredentialBindingHold('EMPTY_BINDINGS')
        for binding in self._bindings.values():
            digest = binding.get('record_sha256')
            ref = binding.get('key_ref')
            if (not isinstance(digest, str) or len(digest) != 64 or
                    any(c not in '0123456789abcdef' for c in digest) or
                    ref not in self._keys or
                    not isinstance(self._keys[ref], str) or not self._keys[ref]):
                raise CredentialBindingHold('INVALID_KEY_BINDING')

    def load_credential(self, credential_id):
        try:
            binding = self._bindings.get(credential_id)
            if binding is None:
                raise CredentialBindingHold('UNBOUND_RECORD')
            record = self._repository.get(credential_id)
            if record is None or record['credential_id'] != credential_id:
                raise CredentialBindingHold('RECORD_MISSING_OR_CHANGED')
            record = dict(record)
            if fingerprint(record) != binding['record_sha256']:
                raise CredentialBindingHold('RECORD_CHANGED')
            store = self._factory(repository=_SingleRecordRepository(record),
                                  master_key=self._keys[binding['key_ref']])
            result = store.load_credential(credential_id)
            # A successful decryption is not permission to ignore concurrent
            # changes in the original repository during this bounded read.
            current = self._repository.get(credential_id)
            if current is None or fingerprint(current) != binding['record_sha256']:
                del result
                raise CredentialBindingHold('RECORD_CHANGED_DURING_READ')
            return result
        except CredentialBindingHold:
            raise
        except Exception:
            # Never forward native exceptions that may contain private inputs.
            raise CredentialBindingHold('NATIVE_CREDENTIAL_READ_FAILED') from None
