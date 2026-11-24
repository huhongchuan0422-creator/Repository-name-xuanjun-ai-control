"""Community-side one-shot consumption preparation for PR122 V1.

This module reserves requests, not identities or privileges. The original Center
holds the durable marker. No remote signature, transport or grant is invented:
the exact PR122 implementation/document must be bound before adding an adapter
and exposing a business route. Browser sessions are never an input here.
"""
import hashlib
import re
from pathlib import Path
from scripts.pr122_customer_core import Center, canonical

SCHEMA = 'PR122_IDENTITY_AUTHORIZATION_V1'
FIELDS = {'schema', 'request_id', 'caller', 'audience', 'user_id', 'tenant_id',
          'project_id', 'operation', 'issued_unix', 'expires_unix', 'authorization_token'}
CHANNEL = 'COMMUNITY_AUTHORIZATION_CONSUMPTION'
PIN = 'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0'


class ConsumptionUnknown(PermissionError):
    pass


class ConsumptionReservation:
    def __init__(self, center):
        if type(center) is not Center:
            raise ValueError('EXACT_EXISTING_CENTER_REQUIRED')
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest() != PIN:
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        self.center = center

    def reserve(self, request, expected_scope, business_body, reference):
        """Persist UNKNOWN before any consume IO; never persist the raw token.

        expected_scope is supplied by the protected community composition, not
        copied from a browser body. Store ACL remains in the original business
        entry. This reservation alone never returns authorization or calls it.
        """
        if type(request) is not dict or set(request) != FIELDS:
            raise ValueError('INVALID_CONSUMPTION_REQUEST')
        if type(expected_scope) is not dict or set(expected_scope) != {'caller', 'audience', 'user_id', 'tenant_id', 'project_id', 'operation'}:
            raise ValueError('PROTECTED_EXPECTED_SCOPE_REQUIRED')
        if request['schema'] != SCHEMA or request['operation'] != 'community.access':
            raise PermissionError('COMMUNITY_AUTHORIZATION_PURPOSE_REQUIRED')
        if any(type(request[k]) is not str or not request[k] or len(request[k]) > 256 for k in FIELDS - {'issued_unix', 'expires_unix', 'authorization_token'}):
            raise ValueError('INVALID_SCOPE_VALUE')
        if any(type(expected_scope[k]) is not str or expected_scope[k] != request[k] for k in expected_scope):
            raise PermissionError('CONSUMPTION_SCOPE_MISMATCH')
        issued, expires, now = request['issued_unix'], request['expires_unix'], self.center.now()
        if type(issued) is not int or type(expires) is not int or not issued <= now < expires or not 1 <= expires - issued <= 30:
            raise PermissionError('CONSUMPTION_EXPIRED_OR_INVALID_TIME')
        token = request['authorization_token']
        if type(token) is not str or not token or len(token) > 4096:
            raise ValueError('BOUNDED_OPAQUE_TOKEN_REQUIRED')
        if type(reference) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', reference):
            raise ValueError('ORIGINAL_BUSINESS_REFERENCE_REQUIRED')
        if type(business_body) is not dict or set(business_body) != {'workspace', 'operation', 'params'} or type(business_body['workspace']) is not str or type(business_body['operation']) is not str or type(business_body['params']) is not dict:
            raise ValueError('ORIGINAL_OPERATION_BODY_REQUIRED')
        encoded = canonical(business_body)
        if len(encoded) > 16384:
            raise ValueError('BUSINESS_BODY_TOO_LARGE')
        c = self.center
        key = c.idx(CHANNEL + ':' + request['request_id'])
        refkey = c.idx(CHANNEL + ':reference:' + reference)
        safe_scope = {k: request[k] for k in FIELDS - {'authorization_token'}}
        record = {'state': 'UNKNOWN_QUERY_EXISTING_ONLY', 'reference': reference,
                  'scope': safe_scope, 'business_sha256': hashlib.sha256(encoded).hexdigest(),
                  'token_sha256': hashlib.sha256(token.encode()).hexdigest()}
        with c.tx():
            if c.db.execute('SELECT 1 FROM events WHERE channel=? AND event_id IN (?,?)', (CHANNEL, key, refkey)).fetchone():
                raise ConsumptionUnknown('CONSUMPTION_UNKNOWN_QUERY_EXISTING_ONLY')
            c.db.execute('INSERT INTO events VALUES(?,?,?)', (CHANNEL, key, now))
            c.db.execute('INSERT INTO events VALUES(?,?,?)', (CHANNEL, refkey, now))
            c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)', (CHANNEL, key, request['user_id'], request['project_id'], c.encrypt(canonical(record), CHANNEL)))
            c.audit(request['project_id'], request['user_id'], 'COMMUNITY_AUTHORIZATION_RESERVED_UNKNOWN', key)
        return {'request_id': request['request_id'], 'reference': reference, 'state': record['state']}

    def dispatch(self, *args, **kwargs):
        # Explicit fail-closed boundary until exact protocol verifier and original
        # community store ACL dispatch are joined. No permissive callback seam.
        raise PermissionError('EXACT_PR122_CONTRACT_ADAPTER_NOT_BOUND')
