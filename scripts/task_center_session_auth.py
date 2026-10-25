"""Server-side TEST_ONLY sessions over an injected identity verifier.

The verifier is deliberately replaceable: the file-backed implementation is
only an isolated test fixture, not a second production identity system.
"""
from __future__ import print_function

import base64
import hashlib
import hmac
import json
import os
import secrets
import time


def password_hash(password, salt=None, rounds=240000):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError('TEST_PASSWORD_MIN_12_REQUIRED')
    salt = os.urandom(16) if salt is None else salt
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt,
                                 rounds)
    return 'pbkdf2_sha256$%d$%s$%s' % (
        rounds, base64.urlsafe_b64encode(salt).decode('ascii').rstrip('='),
        base64.urlsafe_b64encode(digest).decode('ascii').rstrip('='))


def _decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


class FileTestIdentityProvider(object):
    """Verify isolated fixture users from an owner-only JSON file."""
    def __init__(self, path):
        from task_center_app import _read_owned_secret_file
        value = json.loads(_read_owned_secret_file(path, 'TEST_IDENTITY'))
        if not isinstance(value, dict) or set(value) != {'users'}:
            raise ValueError('EXACT_TEST_IDENTITY_FILE_REQUIRED')
        self.users = value['users']

    def verify(self, username, password):
        entry = self.users.get(username)
        if not isinstance(entry, dict) or not entry.get('enabled', False):
            return None
        encoded = entry.get('password_hash', '')
        try:
            scheme, rounds, salt, expected = encoded.split('$')
            if scheme != 'pbkdf2_sha256':
                return None
            actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                         _decode(salt), int(rounds))
            if not hmac.compare_digest(actual, _decode(expected)):
                return None
        except (ValueError, TypeError):
            return None
        roles = entry.get('roles')
        if (not isinstance(roles, list) or not roles or
                any(not isinstance(x, str) or not x for x in roles)):
            return None
        return {'tenant_id': entry.get('tenant_id'),
                'principal_id': entry.get('principal_id'),
                'roles': sorted(set(roles))}


class SessionStore(object):
    COOKIE = 'xuanjun_task_center_session'
    CSRF_COOKIE = 'xuanjun_task_center_csrf'

    def __init__(self, connection_factory, tenant_id, ttl_seconds=1800,
                 clock=time.time):
        self.connection_factory = connection_factory
        self.tenant_id = tenant_id
        self.ttl_seconds = int(ttl_seconds)
        self.clock = clock
        db = self.connection_factory()
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS task_center_sessions(
              tenant_id TEXT NOT NULL,session_hash TEXT NOT NULL,
              principal_id TEXT NOT NULL,roles_json TEXT NOT NULL,
              csrf_hash TEXT NOT NULL,created_at REAL NOT NULL,
              expires_at REAL NOT NULL,revoked_at REAL,
              PRIMARY KEY(tenant_id,session_hash))''')
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _hash(value):
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def create(self, identity):
        if identity.get('tenant_id') != self.tenant_id:
            raise ValueError('SESSION_TENANT_MISMATCH')
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = self.clock()
        db = self.connection_factory()
        try:
            db.execute('''INSERT INTO task_center_sessions VALUES
              (?,?,?,?,?,?,?,NULL)''', (self.tenant_id, self._hash(token),
              identity['principal_id'], json.dumps(identity['roles'],
              separators=(',', ':')), self._hash(csrf), now,
              now + self.ttl_seconds))
            db.commit()
        finally:
            db.close()
        return token, csrf, now + self.ttl_seconds

    def get(self, token):
        if not token:
            return None
        db = self.connection_factory()
        try:
            row = db.execute('''SELECT * FROM task_center_sessions WHERE
              tenant_id=? AND session_hash=?''',
              (self.tenant_id, self._hash(token))).fetchone()
            if row is None or row['revoked_at'] is not None:
                return None
            if float(row['expires_at']) <= self.clock():
                return None
            return {'tenant_id': row['tenant_id'],
                    'principal_id': row['principal_id'],
                    'roles': json.loads(row['roles_json']),
                    'session_hash': row['session_hash'],
                    'csrf_hash': row['csrf_hash'],
                    'expires_at': row['expires_at']}
        finally:
            db.close()

    def verify_csrf(self, session, supplied):
        return bool(supplied and hmac.compare_digest(
            session['csrf_hash'], self._hash(supplied)))

    def revoke(self, token):
        if not token:
            return False
        db = self.connection_factory()
        try:
            changed = db.execute('''UPDATE task_center_sessions SET
              revoked_at=? WHERE tenant_id=? AND session_hash=? AND
              revoked_at IS NULL''', (self.clock(), self.tenant_id,
              self._hash(token))).rowcount
            db.commit()
            return bool(changed)
        finally:
            db.close()
