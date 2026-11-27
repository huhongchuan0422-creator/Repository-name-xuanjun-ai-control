"""Trusted-host provenance source and principal mapper (real authenticated refs).

This is the original Python project's task-scoped host context implementation
the Owner decision authorized: it satisfies the existing
GuardedProvenanceConsumer protocol (verify_login/current_provenance/
assert_effect_current plus the principal mapper callable) without introducing
a second session or role authority.

Authentication facts, not names: each host principal must present a login
secret checked against a digest stored only in the protected 0600 config file,
and an Ed25519 attestation that verifies against the pinned project trust
anchor for exactly the approved task with bounded validity. An agent name in
plain JSON is never accepted; roles come exclusively from the signed binding,
never from request-supplied role lists. Restart or anchor/config rotation
drops formal status (never reconstructed from a row or a string reference).
"""
import copy
import hashlib
import hmac
import json
import os
import stat
import time

from development_authority import canonical_bytes
from host_principal_bindings import (ROLES, fingerprint_of, load_anchor,
                                     verify_principal_binding)
from secure_file_input import read_owned_secret_file

CONFIG_KIND = 'TC_HOST_PROVENANCE_CONFIG_V1'
SOURCE_REF = 'project-trust-root'
ERROR = 'HOST_PRINCIPAL_ATTESTATION_INVALID'
STALE = 'HOST_PRINCIPAL_CONTEXT_STALE'
CONFIG_FIELDS = {'kind', 'tenant_id', 'task_id', 'trust_root_fingerprint', 'principals'}
PRINCIPAL_FIELDS = {'username', 'secret_sha256', 'role', 'binding'}
# Same binding shape the shipped consumer admits; any extra request-side
# field (roles, scopes, admin flags) is not part of the authenticated shape.
BINDING_FIELDS = {'source_ref', 'source_version', 'subject', 'incarnation',
                  'tenant_id', 'principal_id', 'expires_at'}


def _file_identity(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(ERROR)
    return {'path': os.path.realpath(path), 'device': info.st_dev,
            'inode': info.st_ino, 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns,
            'sha256': _read_bytes(path)}


def _read_bytes(path):
    with open(path, 'rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest()


class HostProvenanceSource(object):
    """Host-owned live context; constructor receives paths, never secrets."""

    def __init__(self, anchor_public_key_file, config_file, clock=time.time):
        if not isinstance(anchor_public_key_file, str) or not isinstance(config_file, str):
            raise ValueError(ERROR)
        self.clock = clock
        self.anchor, self.fingerprint = load_anchor(anchor_public_key_file)
        self._anchor_file = anchor_public_key_file
        self._config_file = config_file
        self._principals, self._identity = self._read_live()

    def _read_live(self):
        identity = {'anchor': _file_identity(self._anchor_file),
                    'config': _file_identity(self._config_file)}
        config = json.loads(read_owned_secret_file(self._config_file, 'HOST_PROVENANCE_CONFIG'))
        if not isinstance(config, dict) or set(config) != CONFIG_FIELDS:
            raise ValueError(ERROR)
        if (config['kind'] != CONFIG_KIND or config['trust_root_fingerprint'] != self.fingerprint
                or not isinstance(config['task_id'], str) or not config['task_id']
                or not isinstance(config['tenant_id'], str) or not config['tenant_id']):
            raise ValueError(ERROR)
        principals = {}
        rows = config['principals']
        if not isinstance(rows, list) or not rows:
            raise ValueError(ERROR)
        for row in rows:
            if not isinstance(row, dict) or set(row) != PRINCIPAL_FIELDS:
                raise ValueError(ERROR)
            username = row['username']
            secret = row['secret_sha256']
            if (not isinstance(username, str) or not username or username in principals
                    or not isinstance(secret, str) or len(secret) != 64):
                raise ValueError(ERROR)
            verified = verify_principal_binding(row['binding'], self.anchor,
                                                self.fingerprint, config['task_id'], self.clock())
            if verified['tenant_id'] != config['tenant_id']:
                raise ValueError(ERROR)
            principals[username] = {'secret_sha256': secret.lower(),
                                    'role': verified['role'], 'verified': verified,
                                    'raw': copy.deepcopy(row['binding'])}
        if len({row['role'] for row in principals.values()}) != len(principals):
            raise ValueError(ERROR)
        return principals, identity

    def _live(self):
        # Every formal admission re-reads the protected files: rotation or
        # expiry revokes liveness immediately; nothing is cached as authority.
        principals, identity = self._read_live()
        if identity != self._identity:
            raise ValueError(STALE)
        return principals

    def _task_id(self):
        config = json.loads(read_owned_secret_file(self._config_file, 'HOST_PROVENANCE_CONFIG'))
        return config['task_id']

    def verify_login(self, username, password):
        principals = self._live()
        row = principals.get(username)
        if row is None or not isinstance(password, str) or not password:
            # Unknown users still consume a digest comparison timing shape.
            hmac.compare_digest('0' * 64, hashlib.sha256(
                (password or '').encode('utf-8')).hexdigest())
            raise ValueError(ERROR)
        if not hmac.compare_digest(row['secret_sha256'],
                                   hashlib.sha256(password.encode('utf-8')).hexdigest()):
            raise ValueError(ERROR)
        verified = row['verified']
        return {'source_ref': SOURCE_REF, 'source_version': verified['kind'],
                'subject': verified['subject'],
                'incarnation': verified['trust_root_fingerprint'],
                'tenant_id': verified['tenant_id'],
                'principal_id': verified['principal_id'],
                'expires_at': verified['expires_at']}

    def current_provenance(self, binding, session):
        principals = self._live()
        for row in principals.values():
            candidate = {'source_ref': SOURCE_REF,
                         'source_version': row['verified']['kind'],
                         'subject': row['verified']['subject'],
                         'incarnation': row['verified']['trust_root_fingerprint'],
                         'tenant_id': row['verified']['tenant_id'],
                         'principal_id': row['verified']['principal_id'],
                         'expires_at': row['verified']['expires_at']}
            if candidate == binding:
                return copy.deepcopy(binding)
        raise ValueError(STALE)

    def assert_effect_current(self):
        self._live()
        return None

    def roles_for(self, binding):
        for row in self._live().values():
            if row['verified']['principal_id'] == binding['principal_id']:
                return [row['role']]
        raise ValueError(STALE)


class HostPrincipalMapper(object):
    """Maps an authenticated host binding to session roles; issues nothing."""

    def __init__(self, source):
        if not isinstance(source, HostProvenanceSource):
            raise ValueError(ERROR)
        self.source = source

    def __call__(self, binding):
        if (not isinstance(binding, dict) or set(binding) != BINDING_FIELDS
                or binding.get('source_ref') != SOURCE_REF):
            raise ValueError(ERROR)
        roles = self.source.roles_for(binding)
        if sorted(roles) not in ([role] for role in ROLES):
            raise ValueError(ERROR)
        return {'tenant_id': binding['tenant_id'],
                'principal_id': binding['principal_id'], 'roles': roles}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Read-only host binding probe; never a login oracle')
    parser.add_argument('--anchor-public-key-file', required=True)
    parser.add_argument('--config-file', required=True)
    args = parser.parse_args(argv)
    try:
        source = HostProvenanceSource(args.anchor_public_key_file, args.config_file)
        mapper = HostPrincipalMapper(source)
        print(json.dumps({'state': 'LOADED', 'task_id': source._task_id(),
                          'trust_root_fingerprint': source.fingerprint,
                          'principals': sorted(source._principals),
                          'mapper_ready': callable(mapper)}, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'state': 'REJECTED', 'error': ERROR}, sort_keys=True))
        return 69


if __name__ == '__main__':
    raise SystemExit(main())
