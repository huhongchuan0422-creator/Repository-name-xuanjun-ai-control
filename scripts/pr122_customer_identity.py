"""Explicit evidence-backed linkage and one-use project authorization, never IAM.

No network calls, identity creation, store grants, credential generation or defaults.
See PR122_CUSTOMER_CENTER_IDENTITY_CONTRACT_V1.md for the shared wire contract.
"""
import hashlib
import hmac
import json
import re
import secrets

from scripts.pr122_customer_core import Denied, Conflict, Unavailable, canonical

SCHEMA = 'PR122_IDENTITY_AUTHORIZATION_V1'
MAPPING_SCHEMA = 'PR122_IDENTITY_MAPPING_V1'
CONSUME_PATH = '/customer/center/api/authorization/consume'
OPERATIONS = {'community.access', 'crm.customer.read'}
ROLES = {'OWNER', 'EDITOR', 'VIEWER', 'REVIEWER'}
SCOPE = {'schema', 'request_id', 'caller', 'audience', 'user_id', 'tenant_id',
         'project_id', 'operation', 'issued_unix', 'expires_unix'}
EVIDENCE = {'project_evidence': 'PROJECT_AUTHORITY',
            'local_identity_evidence': 'LOCAL_IDENTITY',
            'domestic_identity_evidence': 'DOMESTIC_IDENTITY'}
SUBJECT = ('user_id', 'tenant_id', 'project_id', 'domestic_customer_id')
MAPPING_FIELDS = {'schema', 'mapping_id', 'version', 'status', 'confirmed_by',
                  'issued_unix', 'expires_unix', *SUBJECT, *EVIDENCE}
DDL = """
CREATE TABLE IF NOT EXISTS identity_mappings(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL,tenant_id TEXT NOT NULL,
 project_id TEXT NOT NULL,domestic_customer_id TEXT NOT NULL,
 version INTEGER NOT NULL,status TEXT NOT NULL,expires INTEGER NOT NULL,
 authority_revision INTEGER NOT NULL,payload BLOB NOT NULL,
 UNIQUE(user_id,tenant_id,project_id));
CREATE TABLE IF NOT EXISTS identity_mapping_history(
 id TEXT NOT NULL,version INTEGER NOT NULL,payload BLOB NOT NULL,
 PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS identity_grants(
 token TEXT PRIMARY KEY,caller TEXT NOT NULL,request_id TEXT NOT NULL,
 user_id TEXT NOT NULL,project_id TEXT NOT NULL,mapping_id TEXT NOT NULL,
 expires INTEGER NOT NULL,used INTEGER NOT NULL,payload BLOB NOT NULL,
 UNIQUE(caller,request_id));
"""
EVIDENCE_ROOT = '/etc/xuanjun-customer-center/identity-evidence'


def need(ok, reason):
    if not ok:
        raise Denied('IDENTITY_' + reason)


def name(value):
    need(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value), 'ID')
    return value


def sha(value):
    need(type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value), 'SHA256')
    return value


def strict(raw):
    from scripts.pr122_customer_http import strict_json
    return strict_json(raw)


def signature(key, domain, payload):
    return hmac.new(key, domain.encode() + b'\n' + canonical(payload), hashlib.sha256).hexdigest()


def install(c):
    c.db.executescript(DDL)


def verified_mapping(c, row):
    value = json.loads(c.decrypt(row['payload'], 'identity-mapping:' + row['id']))
    p = value['mapping']
    need(p['mapping_id'] == row['id'] and all(p[f] == row[f] for f in SUBJECT)
         and p['version'] == row['version'] and p['status'] == row['status']
         and p['expires_unix'] == row['expires']
         and value['authority_revision'] == row['authority_revision'], 'MAPPING_INTEGRITY')
    history = c.db.execute('SELECT payload FROM identity_mapping_history WHERE id=? AND version=?',
                           (row['id'], row['version'])).fetchone()
    need(history is not None and bytes(history['payload']) == bytes(row['payload']), 'MAPPING_HISTORY')
    return p


def import_mapping(c, document, key, confirmers, evidence):
    """Protected operator only; evidence resolves preloaded root-private bytes."""
    need(type(key) is bytes and len(key) >= 32, 'AUTHORITY_KEY')
    need(type(confirmers) in (list, tuple) and bool(confirmers)
         and all(type(v) is str and name(v) for v in confirmers), 'CONFIRMER_TRUST')
    need(type(document) is dict and set(document) == {'payload', 'signature'}, 'ENVELOPE')
    p = document['payload']
    need(type(p) is dict and set(p) == MAPPING_FIELDS and p['schema'] == MAPPING_SCHEMA, 'MAPPING_SCHEMA')
    need(hmac.compare_digest(sha(document['signature']), signature(key, MAPPING_SCHEMA, p)), 'MAPPING_SIGNATURE')
    for field in (*SUBJECT, 'mapping_id', 'confirmed_by'):
        name(p[field])
    need(p['confirmed_by'] in confirmers, 'CONFIRMER_TRUST')
    need(type(p['version']) is int and p['version'] > 0, 'MAPPING_VERSION')
    need(type(p['issued_unix']) is int and type(p['expires_unix']) is int
         and c.now() - 300 <= p['issued_unix'] <= c.now()
         and c.now() < p['expires_unix'] <= p['issued_unix'] + 86400, 'MAPPING_TIME')
    need(p['status'] in ('ACTIVE', 'REVOKED'), 'MAPPING_STATUS')
    with c.tx():
        old = c.db.execute('SELECT * FROM identity_mappings WHERE id=?', (p['mapping_id'],)).fetchone()
        if old:
            verified_mapping(c, old)
            need(all(old[f] == p[f] for f in SUBJECT), 'MAPPING_SUBJECT_CHANGE')
            if p['version'] <= old['version']:
                raise Conflict('IDENTITY_MAPPING_REPLAY')
        else:
            need(p['status'] == 'ACTIVE', 'REVOKE_UNKNOWN')
        if p['status'] == 'ACTIVE':
            project, _, _ = c.project(p['user_id'], p['project_id'])
            need(project['tenant'] == p['tenant_id'], 'MAPPING_TENANT')
            need(callable(evidence), 'EVIDENCE_REQUIRED')
            seen = set()
            for field, kind in EVIDENCE.items():
                proof = p[field]
                need(type(proof) is dict and set(proof) == {'ref', 'sha256'}, 'EVIDENCE_SCHEMA')
                ref = name(proof['ref'])
                need(ref not in seen, 'EVIDENCE_DISTINCT')
                seen.add(ref)
                raw = evidence(ref)
                need(type(raw) is bytes and 0 < len(raw) <= 65536
                     and hashlib.sha256(raw).hexdigest() == sha(proof['sha256']), 'EVIDENCE_BYTES')
                value = strict(raw)
                expected = {'schema': 'PR122_IDENTITY_EVIDENCE_V1', 'kind': kind,
                            'confirmed_by': p['confirmed_by'], 'verified': True,
                            **{f: p[f] for f in SUBJECT}}
                need(type(value) is dict and set(value) == set(expected) | {'expires_unix'}
                     and canonical({k: value[k] for k in expected}) == canonical(expected)
                     and type(value['expires_unix']) is int
                     and value['expires_unix'] >= p['expires_unix'], 'EVIDENCE_SUBJECT')
            revision = project['revision']
        else:
            # Revocation must remain possible after project/session expiry or removal.
            revision = old['authority_revision']
            prior = verified_mapping(c, old)
            need(all(p[f] == prior[f] for f in EVIDENCE), 'REVOKE_EVIDENCE_BINDING')
        need(not c.db.execute('SELECT 1 FROM identity_mappings WHERE user_id=? AND tenant_id=? AND project_id=? AND id!=?',
                             (p['user_id'], p['tenant_id'], p['project_id'], p['mapping_id'])).fetchone(), 'MAPPING_CONFLICT')
        raw = c.encrypt(canonical({'mapping': p, 'authority_revision': revision}), 'identity-mapping:' + p['mapping_id'])
        c.db.execute('INSERT OR REPLACE INTO identity_mappings VALUES(?,?,?,?,?,?,?,?,?,?)',
                     (p['mapping_id'], *(p[f] for f in SUBJECT), p['version'], p['status'], p['expires_unix'], revision, raw))
        c.db.execute('INSERT INTO identity_mapping_history VALUES(?,?,?)', (p['mapping_id'], p['version'], raw))
        c.db.execute('UPDATE identity_grants SET used=1 WHERE mapping_id=?', (p['mapping_id'],))
        c.audit(p['project_id'], p['confirmed_by'], 'IDENTITY_MAPPING_' + p['status'],
                p['mapping_id'] + ':' + str(p['version']))
    return {'mapping_id': p['mapping_id'], 'version': p['version'], 'status': p['status']}


class Boundary:
    """Purpose-scoped service trust supplied only by the protected runtime input."""
    def __init__(self, callers):
        need(type(callers) is dict and bool(callers) and len(callers) <= 32, 'CALLER_TRUST')
        self.callers = {}
        for caller, item in callers.items():
            name(caller)
            need(type(item) is dict and set(item) == {'key', 'audience', 'operations'}, 'CALLER_CONFIG')
            need(type(item['key']) is bytes and len(item['key']) == 32, 'CALLER_KEY')
            need(all(item['key'] != previous['key'] for previous in self.callers.values()), 'CALLER_KEY_REUSE')
            name(item['audience'])
            need(type(item['operations']) is dict and bool(item['operations']), 'OPERATIONS')
            for op, roles in item['operations'].items():
                need(op in OPERATIONS and type(roles) is list and bool(roles)
                     and len(roles) == len(set(roles)) and set(roles) <= ROLES, 'OPERATIONS')
            self.callers[caller] = {'key': item['key'], 'audience': item['audience'],
                                    'operations': {op: tuple(roles) for op, roles in item['operations'].items()}}

    def scope(self, c, p, extra=frozenset()):
        need(type(p) is dict and set(p) == SCOPE | set(extra) and p['schema'] == SCHEMA, 'REQUEST_SCHEMA')
        for f in SCOPE - {'schema', 'issued_unix', 'expires_unix'}:
            name(p[f])
        need(type(p['issued_unix']) is int and type(p['expires_unix']) is int
             and p['issued_unix'] <= c.now() < p['expires_unix'] <= p['issued_unix'] + 30, 'REQUEST_TIME')
        item = self.callers.get(p['caller'])
        need(item is not None and p['audience'] == item['audience']
             and p['operation'] in item['operations'], 'CALLER_SCOPE')
        return item

    def current(self, c, p, token):
        item = self.scope(c, p)
        need(c.session(token) == p['user_id'], 'SESSION_SUBJECT')
        project, role, _ = c.project(p['user_id'], p['project_id'], item['operations'][p['operation']])
        need(project['tenant'] == p['tenant_id'], 'TENANT')
        m = c.db.execute('SELECT * FROM identity_mappings WHERE user_id=? AND tenant_id=? AND project_id=?',
                         (p['user_id'], p['tenant_id'], p['project_id'])).fetchone()
        need(m is not None and m['status'] == 'ACTIVE' and m['expires'] > c.now()
             and m['authority_revision'] == project['revision'], 'MAPPING_UNAVAILABLE')
        verified_mapping(c, m)
        return project, role, m

    def issue(self, c, token, csrf, p):
        with c.tx():
            c.session(token, csrf)
            project, role, m = self.current(c, p, token)
            if c.db.execute('SELECT 1 FROM identity_grants WHERE caller=? AND request_id=?',
                            (p['caller'], p['request_id'])).fetchone():
                raise Conflict('IDENTITY_REQUEST_REPLAY')
            if c.db.execute('SELECT count(*) FROM identity_grants').fetchone()[0] >= 100000:
                raise Unavailable('IDENTITY_GRANT_HISTORY_BOUND')
            c.limit('identity-issue:' + p['user_id'], 30, 60)
            grant = secrets.token_urlsafe(32)
            key = hashlib.sha256(grant.encode()).hexdigest()
            stored = {'scope': p, 'session_token': token, 'mapping_version': m['version'],
                      'authority_revision': project['revision'], 'role': role}
            c.db.execute('INSERT INTO identity_grants VALUES(?,?,?,?,?,?,?,0,?)',
                         (key, p['caller'], p['request_id'], p['user_id'], p['project_id'], m['id'],
                          p['expires_unix'], c.encrypt(canonical(stored), 'identity-grant:' + key)))
            c.audit(p['project_id'], p['user_id'], 'IDENTITY_AUTHORIZATION_ISSUED', p['request_id'])
        return {**p, 'authorization_token': grant, 'store_authorized': False}

    def consume(self, c, document):
        need(type(document) is dict and set(document) == {'payload', 'signature'}, 'ENVELOPE')
        p = document['payload']
        item = self.scope(c, p, {'authorization_token'})
        need(type(p['authorization_token']) is str and 32 <= len(p['authorization_token']) <= 128, 'TOKEN')
        need(hmac.compare_digest(sha(document['signature']), signature(item['key'], CONSUME_PATH, p)), 'CALLER_SIGNATURE')
        key = hashlib.sha256(p['authorization_token'].encode()).hexdigest()
        scope = {f: p[f] for f in SCOPE}
        with c.tx():
            r = c.db.execute('SELECT * FROM identity_grants WHERE token=?', (key,)).fetchone()
            need(r is not None and not r['used'] and r['expires'] > c.now(), 'GRANT_UNAVAILABLE')
            stored = json.loads(c.decrypt(r['payload'], 'identity-grant:' + key))
            need(canonical(stored['scope']) == canonical(scope), 'GRANT_SCOPE')
            project, role, m = self.current(c, scope, stored['session_token'])
            need(m['id'] == r['mapping_id'] and m['version'] == stored['mapping_version']
                 and project['revision'] == stored['authority_revision'] and role == stored['role'], 'GRANT_STALE')
            need(c.db.execute('UPDATE identity_grants SET used=1 WHERE token=? AND used=0', (key,)).rowcount == 1, 'REPLAY')
            result = {**scope, 'domestic_customer_id': m['domestic_customer_id'],
                      'mapping_id': m['id'], 'mapping_version': m['version'],
                      'authority_revision': project['revision'], 'project_role': role,
                      'store_authorized': False, 'decision': 'PROJECT_AUTHORIZED'}
            signed = {'payload': result, 'signature': signature(item['key'], SCHEMA + ':response', result)}
            c.audit(p['project_id'], p['caller'], 'IDENTITY_AUTHORIZATION_CONSUMED',
                    p['request_id'] + ':' + m['id'] + ':' + str(m['version']))
        return signed


def boundary_from_config(config):
    """Optional, disabled by absence. Never generate or resolve new credentials."""
    value = config.get('identity_authorization')
    if value is None:
        return None
    import base64
    need(type(value) is dict, 'CALLER_CONFIG')
    callers = {}
    for caller, item in value.items():
        need(type(item) is dict and set(item) == {'key', 'audience', 'operations'}, 'CALLER_CONFIG')
        try:
            key = base64.b64decode(item['key'], validate=True)
        except (TypeError, ValueError):
            raise Denied('IDENTITY_CALLER_KEY') from None
        # Existing data/backup/authority material must never become a service MAC key.
        need(base64.b64encode(key).decode() == item['key'], 'CALLER_KEY_ENCODING')
        forbidden = list(config.get('keys', {}).values()) + [config.get('backup_key'), config.get('authority_verify_key')]
        for value in forbidden:
            if value is not None:
                need(key != base64.b64decode(value, validate=True), 'KEY_SEPARATION')
        callers[caller] = {**item, 'key': key}
    return Boundary(callers)


def read_root_file(path):
    """Bounded, descriptor-walked root-private input. No symlink/TOCTOU fallback."""
    import os
    import stat
    from pathlib import PurePosixPath
    need(os.geteuid() == 0 and type(path) is str, 'PROTECTED_OPERATOR_REQUIRED')
    parts = PurePosixPath(path).parts
    need(path.startswith('/') and len(parts) > 1 and str(PurePosixPath(path)) == path
         and '..' not in parts, 'PROTECTED_PATH')
    fds = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(parent)
        chain = []
        for part in parts[1:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            st = os.fstat(fd)
            need(st.st_uid == 0 and not st.st_mode & 0o022, 'PROTECTED_DIRECTORY')
            chain.append((parent, part, fd, st.st_dev, st.st_ino))
            fds.append(fd); parent = fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        fds.append(fd); before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
             and not before.st_mode & 0o077 and 0 < before.st_size <= 65536, 'PROTECTED_FILE')
        raw = b''
        while len(raw) <= 65536:
            chunk = os.read(fd, 65537 - len(raw))
            if not chunk:break
            raw += chunk
        fields = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
                            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(len(raw) == before.st_size and fields(before) == fields(os.fstat(fd))
             and fields(before) == fields(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)), 'INPUT_CHANGED')
        for parent, part, fd, dev, ino in chain:
            current = os.stat(part, dir_fd=parent, follow_symlinks=False)
            need(stat.S_ISDIR(current.st_mode) and current.st_uid == 0 and not current.st_mode & 0o022
                 and (current.st_dev, current.st_ino) == (dev, ino), 'DIRECTORY_CHANGED')
        return raw
    finally:
        for fd in reversed(fds):os.close(fd)


def load_operator_mapping(path):
    document = strict(read_root_file(path))
    need(type(document) is dict and type(document.get('payload')) is dict, 'ENVELOPE')
    p = document['payload']
    evidence = {}
    if p.get('status') == 'ACTIVE':
        for field in EVIDENCE:
            proof = p.get(field)
            need(type(proof) is dict, 'EVIDENCE_SCHEMA')
            ref = name(proof.get('ref'))
            evidence[ref] = read_root_file(EVIDENCE_ROOT + '/' + ref + '.json')
    return document, evidence
