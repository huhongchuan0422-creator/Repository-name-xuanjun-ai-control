"""Strict signed AdmissionV2 validation. No trust anchors are embedded."""
import hashlib
import json
import re
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

FIELDS = frozenset(('task_id', 'spec_id', 'artifact_digest', 'attempt_id',
    'run_id', 'session_id', 'lease_id', 'fence', 'epoch', 'generation',
    'subject', 'provider_id', 'adapter_id', 'permission_scope', 'operation_id',
    'issued_at', 'expires_at'))
STATEMENT = frozenset(('id', 'binary_digest', 'instance', 'epoch',
    'capabilities', 'issued_at', 'expires_at', 'key_id', 'signature'))
HEX = re.compile(r'^[0-9a-f]{64}$')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('EXACT_V2_SCHEMA_REQUIRED')


def text(value):
    return type(value) is str and 0 < len(value) <= 512 and value == value.strip()


def window(value, now):
    if (type(now) is not int or type(value['issued_at']) is not int
            or type(value['expires_at']) is not int
            or not value['issued_at'] <= now < value['expires_at']):
        raise PermissionError('INVALID_OR_EXPIRED_IDENTITY')


def admission(value, now):
    exact(value, FIELDS)
    for key, val in value.items():
        if key in ('fence', 'epoch', 'generation', 'issued_at', 'expires_at'):
            if type(val) is not int or val < (1 if key == 'fence' else 0):
                raise ValueError('INVALID_V2_TYPE')
        elif not text(val):
            raise ValueError('INVALID_V2_TYPE')
    if not HEX.fullmatch(value['artifact_digest']):
        raise ValueError('INVALID_ARTIFACT_DIGEST')
    window(value, now)
    return value


class TrustStore:
    """Pinned Ed25519 public keys and permitted component digests.

    Keys map key_id to (raw 32-byte public key, role, principal). Allowed
    binaries map (role, principal) to a nonempty set of 64-character digests.
    Host must source this configuration from a protected, authenticated root.
    """
    def __init__(self, keys, allowed_binaries, revoked=()):
        if not isinstance(keys, dict) or not keys or not isinstance(allowed_binaries, dict):
            raise PermissionError('TRUST_STORE_REQUIRED')
        self.keys = dict(keys)
        self.allowed_binaries = dict(allowed_binaries)
        self.revoked = frozenset(revoked)

    def verify(self, envelope, role, principal, domain):
        key_id = envelope.get('key_id')
        item = self.keys.get(key_id)
        if not text(key_id) or key_id in self.revoked or not item or len(item) != 3 or item[1:] != (role, principal):
            raise PermissionError('UNKNOWN_OR_UNTRUSTED_KEY')
        signature = envelope.get('signature')
        if type(signature) is not str or len(signature) != 128:
            raise PermissionError('INVALID_SIGNATURE')
        unsigned = dict(envelope)
        del unsigned['signature']
        try:
            Ed25519PublicKey.from_public_bytes(item[0]).verify(bytes.fromhex(signature), domain + canonical(unsigned))
        except Exception:
            raise PermissionError('INVALID_SIGNATURE')

    def gate(self, value, expected, now):
        exact(value, FIELDS | {'authority_identity', 'key_id', 'signature'})
        if not text(value['authority_identity']):
            raise ValueError('AUTHORITY_IDENTITY_REQUIRED')
        self.verify(value, 'authority', value['authority_identity'], b'P3-GATE-V2\x00')
        embedded = {key: value[key] for key in FIELDS}
        admission(embedded, now)
        if canonical(embedded) != canonical(expected):
            raise PermissionError('ADMISSION_GATE_MISMATCH')
        return digest(value)

    def identity(self, value, role, principal, operation, now):
        exact(value, STATEMENT)
        if (value['id'] != principal or not text(value['id']) or not text(value['instance'])
                or type(value['epoch']) is not int or value['epoch'] < 0
                or not isinstance(value['capabilities'], list)
                or any(not text(x) for x in value['capabilities'])
                or value['capabilities'] != sorted(set(value['capabilities']))
                or operation not in value['capabilities']
                or not isinstance(value['binary_digest'], str)
                or not HEX.fullmatch(value['binary_digest'])):
            raise PermissionError('INVALID_COMPONENT_IDENTITY')
        window(value, now)
        self.verify(value, role, principal, b'P3-IDENTITY-V2\x00')
        if value['binary_digest'] not in self.allowed_binaries.get((role, principal), ()):
            raise PermissionError('UNTRUSTED_COMPONENT_DIGEST')
        return digest(value)
