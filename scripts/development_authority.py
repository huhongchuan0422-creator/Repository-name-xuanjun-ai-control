"""Ed25519 development-authority issuer and fail-closed reader primitives."""
from __future__ import print_function

import base64
import hashlib
import json
import math
import os
import sqlite3
import stat
import time
from urllib.parse import quote

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)


SCHEMA = 3
KIND = 'DEVELOPMENT_WRITER_AUTHORITY'
ALGORITHM = 'Ed25519'
ACTIVE_TASK_STATES = frozenset(('RECEIVED', 'STARTED', 'RUNNING',
                                'HANDOFF_PENDING'))
EXPECTED_KEYS = frozenset(('issuer', 'instance_id', 'version', 'service_id',
                           'task_id', 'attempt_id', 'lease_id', 'fence',
                           'epoch', 'resource_scope_digest', 'request_id',
                           'now', 'max_age', 'purpose', 'target_sha256'))
PURPOSES = frozenset(('AUTHORIZATION_CONSUME', 'STATUS_QUERY', 'INSPECT',
                      'RECOVER'))


class SQLiteReplayGuard(object):
    """Durably consume a replay tuple with one SQLite uniqueness CAS."""

    def __init__(self, path):
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError('REPLAY_DB_ABSOLUTE_PATH_REQUIRED')
        self.path = path
        if not os.path.exists(path):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.close(descriptor)
        info = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError('UNSAFE_REPLAY_DB')
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS consumed_authority_requests(
          issuer TEXT NOT NULL,instance_id TEXT NOT NULL,purpose TEXT NOT NULL,
          target_sha256 TEXT NOT NULL,request_id TEXT NOT NULL,consumed_at REAL NOT NULL,
          PRIMARY KEY(issuer,instance_id,purpose,target_sha256,request_id))''')

    def __call__(self, key):
        if (not isinstance(key, tuple) or len(key) != 5
                or any(not isinstance(x, str) or not x for x in key)):
            raise ValueError('EXACT_REPLAY_KEY_REQUIRED')
        try:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('INSERT INTO consumed_authority_requests VALUES(?,?,?,?,?,?)',
                            key + (time.time(),))
            self.db.execute('COMMIT')
            return True
        except sqlite3.IntegrityError:
            self.db.execute('ROLLBACK')
            return False
        except Exception:
            try: self.db.execute('ROLLBACK')
            except Exception: pass
            raise

    def close(self):
        self.db.close()


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _owned_regular_nofollow(path, label):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError(label + '_ABSOLUTE_PATH_REQUIRED')
    before = os.lstat(path)
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError(label + '_REGULAR_FILE_REQUIRED')
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    after = os.fstat(fd)
    if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or after.st_nlink != 1):
        os.close(fd)
        raise ValueError(label + '_FILE_IDENTITY_REJECTED')
    return fd, after


def open_verified_ledger(path, forbidden_paths=(), formal_only=False):
    """Open exactly the checked inode and reject aliases to test ledgers."""
    fd, identity = _owned_regular_nofollow(path, 'FORMAL_LEDGER')
    try:
        for forbidden in forbidden_paths:
            if forbidden and os.path.exists(forbidden):
                # Follow a configured symlink here: it is the target inode that
                # must never be accepted as the formal ledger.
                other = os.stat(forbidden)
                if (identity.st_dev, identity.st_ino) == (other.st_dev, other.st_ino):
                    raise ValueError('FORMAL_LEDGER_FILE_IDENTITY_REQUIRED')
        proc_path = '/proc/self/fd/%d' % fd
        uri = 'file:%s?mode=ro&immutable=0' % quote(proc_path, safe='/')
        connection = sqlite3.connect(uri, uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        opened_path = connection.execute('PRAGMA database_list').fetchone()[2]
        opened = os.stat(opened_path)
        if (opened.st_dev, opened.st_ino) != (identity.st_dev, identity.st_ino):
            raise ValueError('FORMAL_LEDGER_OPENED_FILE_IDENTITY_REJECTED')
        actual = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'tasks', 'resource_claims'}.issubset(actual):
            raise ValueError('FORMAL_LEDGER_SCHEMA_REQUIRED')
        if formal_only:
            if 'authority_runtime_profile' not in actual:
                raise ValueError('FORMAL_LEDGER_PROFILE_REQUIRED')
            profile = connection.execute(
                'SELECT profile FROM authority_runtime_profile WHERE singleton=1').fetchone()
            if profile is None or profile[0] != 'FORMAL':
                raise ValueError('TEST_ONLY_LEDGER_FORBIDDEN')
        current = os.stat(path, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
            raise ValueError('FORMAL_LEDGER_TOCTOU_REJECTED')
        return connection, fd, (identity.st_dev, identity.st_ino)
    except Exception:
        try:
            connection.close()
        except Exception:
            pass
        os.close(fd)
        raise


def close_verified_ledger(connection, fd):
    try:
        connection.close()
    finally:
        os.close(fd)


def load_private_key(raw):
    if raw.startswith(b'-----BEGIN'):
        key = serialization.load_pem_private_key(raw, password=None)
    else:
        key = Ed25519PrivateKey.from_private_bytes(raw)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('ED25519_PRIVATE_KEY_REQUIRED')
    return key


def load_public_key(raw):
    if raw.startswith(b'-----BEGIN'):
        key = serialization.load_pem_public_key(raw)
    else:
        key = Ed25519PublicKey.from_public_bytes(raw)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('ED25519_PUBLIC_KEY_REQUIRED')
    return key


def sign_payload(payload, anchor_id, private_key):
    raw = canonical_bytes(payload)
    return {'payload': payload, 'signature': {
        'algorithm': ALGORITHM, 'anchor_id': anchor_id,
        'canonical_sha256': hashlib.sha256(raw).hexdigest(),
        'value': base64.b64encode(private_key.sign(raw)).decode('ascii')}}


def authority_payload(connection, request, trust, now=None):
    """Issuer-only projection. Request values select; ledger values bind."""
    if not isinstance(request, dict) or set(request) != {
            'task_id', 'request_id', 'service_id', 'purpose', 'target_sha256'}:
        raise ValueError('EXACT_AUTHORITY_REQUEST_REQUIRED')
    now = time.time() if now is None else now
    if not _finite(now):
        raise ValueError('TRUSTED_TIME_REQUIRED')
    row = connection.execute('SELECT * FROM tasks WHERE task_id=?',
                             (request['task_id'],)).fetchone()
    if row is None:
        raise KeyError(request['task_id'])
    task = dict(row)
    claims = [dict(x) for x in connection.execute('''SELECT resource_key,
      task_id,attempt_id,fence,epoch,state FROM resource_claims
      WHERE task_id=? ORDER BY resource_key''', (task['task_id'],))]
    try:
        resource_keys = json.loads(task['resource_scope_json'])
    except (TypeError, ValueError):
        resource_keys = None
    canonical_keys = (isinstance(resource_keys, list) and resource_keys
        and all(isinstance(x, str) and x for x in resource_keys)
        and resource_keys == sorted(set(resource_keys)))
    scope_digest = (hashlib.sha256(canonical_bytes(resource_keys)).hexdigest()
                    if canonical_keys else None)
    valid_claims = (canonical_keys and len(claims) == len(resource_keys)
        and [x['resource_key'] for x in claims] == resource_keys
        and scope_digest == task['resource_scope_digest'] and all(x['state'] == 'VALID'
        and x['attempt_id'] == task['attempt_id'] and x['fence'] == task['fence']
        and x['epoch'] == task['epoch'] for x in claims))
    legal = (task['state'] in ACTIVE_TASK_STATES
             and task['authority_state'] == 'VALID' and valid_claims
             and _finite(task['authority_valid_until'])
             and now < task['authority_valid_until']
             and (_finite(task['last_trusted_time'])
                  and now >= task['last_trusted_time']))
    return {
      'schema': SCHEMA, 'kind': KIND,
      'issuer': trust['issuer'],
      'provider': {'instance_id': trust['instance_id'],
                   'version': trust['version']},
      'reader': {'service_identity': request['service_id'],
                 'permission': 'development-authority:read'},
      'request': {'request_id': request['request_id'], 'purpose': request['purpose'],
                  'target_sha256': request['target_sha256'],
                  'task_id': request['task_id']},
      'observed_at': now,
      'task': {'task_id': task['task_id'], 'state': task['state'],
               'spec_sha256': task['spec_sha256'],
               'checkpoint_sha256': task['checkpoint_sha256']},
      'writer': {'owner': task['owner'], 'entry': task['entry'],
                 'caller_id': task['authority_caller_id'],
                 'run_id': task['authority_run_id'],
                 'session_id': task['authority_session_id'],
                 'gateway_id': task['authority_gateway_id']},
      'assignment': {'attempt_id': task['attempt_id'],
                     'lease_id': task['lease_id'], 'fence': task['fence'],
                     'epoch': task['epoch'],
                     'lock_provider_id': task['authority_lock_provider_id'],
                     'resource_scope_digest': task['resource_scope_digest'],
                     'resource_keys': resource_keys},
      'authority': {'state': task['authority_state'],
                    'valid_until': task['authority_valid_until'],
                    'authorized': bool(legal)},
      'revocation': {'state': task['authority_state'],
                     'old_fence_invalidated': task['old_fence_invalidated']}}


def verify_envelope(envelope, public_key, trust, expected, replay_guard=None):
    """Verify crypto, trusted metadata, exact request binding and freshness."""
    if (not isinstance(expected, dict) or set(expected) != EXPECTED_KEYS
            or not isinstance(trust, dict) or set(trust) != {'anchor_id'}
            or not isinstance(trust['anchor_id'], str) or not trust['anchor_id']
            or not isinstance(public_key, Ed25519PublicKey)
            or replay_guard is None or not callable(replay_guard)):
        raise ValueError('TRUSTED_EXPECTATIONS_REQUIRED')
    if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
        raise ValueError('AUTHORITY_ENVELOPE_REQUIRED')
    signature = envelope['signature']; payload = envelope['payload']
    if (not isinstance(signature, dict) or set(signature) !=
            {'algorithm', 'anchor_id', 'canonical_sha256', 'value'}
            or signature['algorithm'] != ALGORITHM
            or signature['anchor_id'] != trust['anchor_id']):
        raise ValueError('AUTHORITY_TRUST_ANCHOR_MISMATCH')
    raw = canonical_bytes(payload)
    if signature['canonical_sha256'] != hashlib.sha256(raw).hexdigest():
        raise ValueError('AUTHORITY_CANONICAL_DIGEST_MISMATCH')
    try:
        public_key.verify(base64.b64decode(signature['value'], validate=True), raw)
    except Exception:
        raise ValueError('AUTHORITY_SIGNATURE_INVALID')
    if payload.get('schema') != SCHEMA or payload.get('kind') != KIND:
        raise ValueError('AUTHORITY_SCHEMA_KIND_MISMATCH')
    bindings = {
      'issuer': payload.get('issuer'),
      'instance_id': payload.get('provider', {}).get('instance_id'),
      'version': payload.get('provider', {}).get('version'),
      'service_id': payload.get('reader', {}).get('service_identity'),
      'task_id': payload.get('task', {}).get('task_id'),
      'attempt_id': payload.get('assignment', {}).get('attempt_id'),
      'lease_id': payload.get('assignment', {}).get('lease_id'),
      'fence': payload.get('assignment', {}).get('fence'),
      'epoch': payload.get('assignment', {}).get('epoch'),
      'resource_scope_digest': payload.get('assignment', {}).get('resource_scope_digest'),
      'request_id': payload.get('request', {}).get('request_id'),
      'purpose': payload.get('request', {}).get('purpose'),
      'target_sha256': payload.get('request', {}).get('target_sha256')}
    expected_bindings = {key: expected[key] for key in bindings}
    if bindings != expected_bindings or payload.get('request', {}).get('task_id') != expected['task_id']:
        raise ValueError('AUTHORITY_REQUEST_BINDING_MISMATCH')
    authority = payload.get('authority', {})
    observed_at = payload.get('observed_at')
    if (authority.get('state') != 'VALID' or authority.get('authorized') is not True
            or not _finite(authority.get('valid_until'))
            or not _finite(expected['now']) or not _finite(expected['max_age'])
            or expected['max_age'] <= 0 or not _finite(observed_at)
            or observed_at > expected['now']
            or expected['now'] - observed_at > expected['max_age']
            or expected['now'] >= authority['valid_until']
            or payload.get('task', {}).get('state') not in ACTIVE_TASK_STATES
            or payload.get('revocation', {}).get('state') != 'VALID'):
        raise ValueError('AUTHORITY_NOT_AUTHORIZED')
    if expected['purpose'] not in PURPOSES:
        raise ValueError('AUTHORITY_PURPOSE_REJECTED')
    replay_key = (expected['issuer'], expected['instance_id'], expected['purpose'],
                  expected['target_sha256'], expected['request_id'])
    try:
        consumed = replay_guard(replay_key)
    except Exception:
        raise ValueError('AUTHORITY_REPLAY_GUARD_FAILED')
    if consumed is not True:
        raise ValueError('AUTHORITY_REPLAY_REJECTED')
    return payload
