"""Verified-evidence interface for five-attempt successor integration.

This is a fail-closed contract checker, not an authority issuer. A production
adapter MUST replace the external producer with actual independent admission,
lease/fence and cloud/host receipt sources. No UK commands are executed here.
Compatible with Python 3.6.
"""
import hashlib
import json
import re

SHA64 = re.compile(r'^[0-9a-f]{64}$')
FIELDS = frozenset(('grant_id', 'attempt_id', 'host', 'lease_epoch', 'fence_token',
                    'writer_id', 'lease_expiry_utc', 'issuer', 'evidence_sha256',
                    'issued_utc', 'source', 'bound_operation_sha256'))


def validate_authority(envelope, grant, attempt, operation_sha, now_utc):
    """Validate shape/binding only; external signature verification still required."""
    if type(envelope) is not dict or set(envelope) != FIELDS:
        raise ValueError('P2_BOUNDARY_AUTHORITY_SCHEMA')
    if envelope['source'] != 'INDEPENDENT_EXTERNAL_VERIFIED':
        raise ValueError('P2_BOUNDARY_SYNTHETIC_OR_UNVERIFIED')
    if (envelope['grant_id'] != grant['grant_id'] or
        envelope['attempt_id'] != attempt or
        envelope['host'] != grant['target_host'] or
        envelope['bound_operation_sha256'] != operation_sha):
        raise ValueError('P2_BOUNDARY_SCOPE_MISMATCH')
    if not all(type(envelope[x]) is str and len(envelope[x]) > 0 for x in
               ('writer_id', 'issuer', 'fence_token')):
        raise ValueError('P2_BOUNDARY_IDENTITY_MISSING')
    for field in ('lease_expiry_utc', 'issued_utc', 'lease_epoch'):
        if type(envelope[field]) is not int or envelope[field] < 1:
            raise ValueError('P2_BOUNDARY_TIME_OR_EPOCH')
    if envelope['issued_utc'] > now_utc or envelope['lease_expiry_utc'] <= now_utc:
        raise ValueError('P2_BOUNDARY_EXPIRED')
    if not all(type(envelope[x]) is str and SHA64.fullmatch(envelope[x]) for x in
               ('evidence_sha256', 'bound_operation_sha256')):
        raise ValueError('P2_BOUNDARY_DIGEST')
    return True


class RealAuthorityNotConnected(Exception):
    pass


def production_authority(*unused):
    # Safe default until UK/global fencing and review provenance are connected.
    raise RealAuthorityNotConnected('P2_RELEASE_HOLD_EXTERNAL_WRITER_LEASE_FENCE_UNKNOWN')
