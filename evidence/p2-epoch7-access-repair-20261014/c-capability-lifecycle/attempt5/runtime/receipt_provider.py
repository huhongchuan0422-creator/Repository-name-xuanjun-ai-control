"""Authenticated RPC receipts; no network, issuer, key discovery or live fallback.

The transport is the existing trusted channel supplied by deployment. A public
RSA key must be pinned by the separately reviewed version/host configuration.
No caller-provided verified=True flag is authentication. Python 3.6 stdlib.
"""
import base64
import hashlib
import json
import re
import time
import uuid

class Hold(RuntimeError):
    pass

def need(ok, code):
    if not ok:
        raise Hold('P2_ATTEMPT5_PROVIDER_' + code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

class ReceiptProvider(object):
    """Verify RSA PKCS#1 v1.5 SHA256 against an explicitly pinned public key.

    Key provenance and server-side global fencing are external admission gates.
    This verifier alone does not prove those gates or authorize production.
    Every response binds a fresh nonce and the complete request digest.
    """
    def __init__(self, transport, modulus, exponent, issuer, clock=None):
        need(callable(transport), 'TRANSPORT_NOT_CONNECTED')
        need(type(modulus) is int and 2048 <= modulus.bit_length() <= 4096 and
             modulus % 2 == 1 and type(exponent) is int and exponent == 65537,
             'PINNED_PUBLIC_KEY')
        need(type(issuer) is str and re.fullmatch('[A-Za-z0-9_.-]{1,80}', issuer), 'ISSUER')
        self.transport, self.modulus, self.exponent = transport, modulus, exponent
        self.issuer, self.clock = issuer, clock or time.time

    def _signature(self, body, signature):
        need(type(signature) is str and len(signature) <= 1024, 'SIGNATURE')
        try:
            raw = base64.b64decode(signature.encode('ascii'), validate=True)
        except Exception:
            raise Hold('P2_ATTEMPT5_PROVIDER_SIGNATURE') from None
        width = (self.modulus.bit_length() + 7) // 8
        need(len(raw) == width and int.from_bytes(raw, 'big') < self.modulus, 'SIGNATURE_WIDTH')
        encoded = pow(int.from_bytes(raw, 'big'), self.exponent, self.modulus).to_bytes(width, 'big')
        suffix = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(canonical(body)).digest()
        expected = b'\x00\x01' + b'\xff' * (width - len(suffix) - 3) + b'\x00' + suffix
        need(encoded == expected, 'SIGNATURE_UNVERIFIED')

    def request(self, grant, attempt, operation, payload=None):
        need(type(grant) is dict and type(attempt) is str and bool(attempt), 'BINDING')
        need(type(operation) is str and re.fullmatch('[a-z][a-z0-9_]{1,63}', operation), 'OPERATION')
        request = {'schema': 1, 'grant_sha256': digest(grant), 'attempt_id': attempt,
                   'operation': operation, 'nonce': uuid.uuid4().hex,
                   'payload': {} if payload is None else payload}
        try:
            envelope = self.transport(json.loads(canonical(request).decode('utf-8')))
        except BaseException:
            raise Hold('P2_ATTEMPT5_PROVIDER_TRANSPORT_UNKNOWN') from None
        need(type(envelope) is dict and set(envelope) == {'body', 'signature'}, 'ENVELOPE')
        body = envelope['body']
        need(type(body) is dict and set(body) == {'schema', 'issuer', 'request_sha256',
            'issued_utc', 'expires_utc', 'result'}, 'BODY')
        need(len(canonical(envelope)) <= 262144, 'RECEIPT_BOUND')
        self._signature(body, envelope['signature'])
        need(type(body['schema']) is int and body['schema'] == 1 and
             body['issuer'] == self.issuer and body['request_sha256'] == digest(request), 'RECEIPT_BINDING')
        now = self.clock()
        need(type(body['issued_utc']) is int and type(body['expires_utc']) is int and
             body['issued_utc'] <= now < body['expires_utc'] and
             0 < body['expires_utc'] - body['issued_utc'] <= 60, 'LEASE_EXPIRED')
        need(type(body['result']) is dict and body['result'].get('status') != 'UNKNOWN', 'RESULT_UNKNOWN')
        return json.loads(canonical(body['result']).decode('utf-8'))
