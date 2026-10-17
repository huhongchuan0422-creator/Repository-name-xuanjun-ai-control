"""Offline validation only. A valid envelope grants no machine execution rights.
Trust must be supplied by an independently protected Owner registration, never
from the request or repository. No TTY emulation or default identity values.
"""
import base64
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HOST = 'iZvt5t8tlrm8oiZ'
PURPOSE = 'PR122_OWNER_CUSTODY_REMOTE_EVIDENCE_V1'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def require(value):
    if not value:
        raise ValueError('CUSTODY_EVIDENCE_HOLD')


def digest(value):
    return (type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def validate(envelope, trust, expected, now):
    """Validate already parsed evidence; never read secrets, write, or execute.

    expected is a protected caller's exact operation binding, not user input.
    now is supplied by the trusted host clock. Signature checks do not establish
    real-world independence: registration custody remains separately reviewed.
    """
    try:
        require(set(envelope) == {'payload', 'signature'})
        p = envelope['payload']
        fields = {'purpose', 'host', 'attempt_id', 'source_commit',
                  'launcher_sha256', 'review_zip_sha256', 'audit_body_sha256',
                  'owner_principal', 'source_writer_principal',
                  'reviewer_principal', 'external_evidence_sha256',
                  'issued_unix', 'expires_unix', 'key_id'}
        require(type(p) is dict and set(p) == fields)
        require(p['purpose'] == PURPOSE and p['host'] == HOST)
        binding = {'attempt_id', 'source_commit', 'launcher_sha256',
                   'review_zip_sha256', 'audit_body_sha256'}
        require(set(expected) == binding)
        require(all(p[k] == expected[k] for k in binding))
        require(all(digest(p[k]) for k in (
            'launcher_sha256', 'review_zip_sha256', 'audit_body_sha256',
            'external_evidence_sha256')))
        require(type(p['source_commit']) is str and len(p['source_commit']) == 40
                and all(c in '0123456789abcdef' for c in p['source_commit']))
        require(type(p['attempt_id']) is str and 1 <= len(p['attempt_id']) <= 100
                and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in p['attempt_id']))
        for k in ('owner_principal', 'source_writer_principal', 'reviewer_principal'):
            require(type(p[k]) is str and 1 <= len(p[k]) <= 128
                    and p[k] == p[k].strip() and p[k].isprintable())
        require(p['source_writer_principal'] != p['reviewer_principal'])
        require(type(p['issued_unix']) is int and type(p['expires_unix']) is int
                and p['issued_unix'] <= now < p['expires_unix']
                and 0 < p['expires_unix'] - p['issued_unix'] <= 7200)
        require(trust['purpose'] == PURPOSE and trust['enabled'] is True)
        require(trust['key_id'] == p['key_id'] and trust['owner_principal'] == p['owner_principal'])
        require(trust['source_writer_principal'] == p['source_writer_principal']
                and trust['reviewer_principal'] == p['reviewer_principal'])
        require(type(trust['revoked']) is bool and not trust['revoked'])
        require(type(trust['valid_until']) is int and now < trust['valid_until'])
        require(digest(trust['registration_evidence_sha256']))
        public = base64.b64decode(trust['public_key'], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
        require(len(public) == 32 and len(signature) == 64)
        Ed25519PublicKey.from_public_bytes(public).verify(signature, canonical(p))
        return {'state': 'EVIDENCE_SIGNATURE_VALID_AWAIT_CUSTODY_REVIEW',
                'envelope_sha256': hashlib.sha256(canonical(envelope)).hexdigest(),
                'execution_authorized': False, 'custody_independence_verified': False}
    except Exception:
        raise ValueError('CUSTODY_EVIDENCE_HOLD') from None
