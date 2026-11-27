"""Source-preserving TEST_ONLY -> project-isolated FORMAL authority handoff.

Implements ONLY the Owner-approved initial activation for the original task
tc-real-development-20261123-4d99c26f2b07 (spec 4d99c26f2b07beebb2863f141cfa0d959ef1e6144830d85da84e6451c77b2e7c,
checkpoint b4fed6497d0cebe9042b3456c28feb4b45c59ffd61adcd62be49818a32129a00).
Offline, executed by the designated custodian (小维ed43); this module never
talks to a service, never signs anything itself, and never mutates the
TEST_ONLY source ledger.

Pipeline (each step leaves a verifiable artifact):
1. create-freeze  reconcile writers/effects, consistent SQLite snapshot via
   the backup API, exact before manifest (per-table row count + digest),
   HMAC-signed bounded freeze receipt.
2. handoff        validate the Owner decision, trust anchor, the three real
   host principal bindings and the signed caller context, then CREATE A NEW
   FORMAL TARGET by legitimate construction (Supervisor +
   TrustedRegistrationVerifier; no SQL profile flip, no relabel of a copied
   DB). Approved non-grant wiring rows are carried over for the SAME task id;
   every source row is preserved as provenance with row/event digest
   invariants; grant/session/credential tables are never carried; a commit
   receipt binds all digests.
3. switch         atomically install the single canonical authority reference
   and isolate the former TEST_ONLY view (marker + identity pin, not delete).
4. reconcile      detect any post-switch write to the isolated old ledger.
5. rollback       revert the reference only; preserves all data and receipts.

Signed first registration/claim happens AFTERwards through the already
installed F4 entry (task_center_first_claim.py) on the FORMAL target; this
module does not register, claim, or fabricate authority, and it fails closed
on legacy-schema or unknown ledgers (legacy_authority_migration.py stays
unused for this modern path).
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
import sys
import time

from host_principal_bindings import (load_anchor, require_task_bindings,
                                     verify_caller_context)
from secure_file_input import read_owned_secret_file

SCHEMA_VERSION = 3
APPLICATION_ID = 0x58534A31
FREEZE_KIND = 'MODERN_AUTHORITY_FREEZE_V1'
POINTER_KIND = 'CANONICAL_AUTHORITY_REFERENCE_V1'
DECISION_KIND = 'OWNER_INITIAL_AUTHORITY_DECISION_V1'
ORIGINAL_TASK_ID = 'tc-real-development-20261123-4d99c26f2b07'
ORIGINAL_SPEC = '4d99c26f2b07beebb2863f141cfa0d959ef1e6144830d85da84e6451c77b2e7c'
ORIGINAL_CHECKPOINT = 'b4fed6497d0cebe9042b3456c28feb4b45c59ffd61adcd62be49818a32129a00'
APPROVED_SCOPE = ['READ_SOURCE', 'WRITE_SOURCE', 'RUN_TEST']
APPROVED_FILES = ['scripts/development_entry_intake.py',
                  'tests/test_development_entry_intake.py']
# Rows that carry writer/claim/session/credential authority are never imported
# into the formal target; they survive only as digest-pinned provenance. The
# subsequent register/claim must be the single signed F4 fact.
DISALLOWED_CARRY = frozenset((
    'authority_runtime_profile', 'events', 'outbox', 'writer_operations',
    'writer_receipts', 'writer_reconcile_evidence', 'resource_claims',
    'resource_invalidation_receipts', 'authority_recovery_evidence',
    'revocation_drains', 'supervisor_heartbeats', 'task_center_sessions',
    'sessions', 'accounts', 'challenges', 'oauth_flows', 'mcp_oauth_clients',
    'mcp_oauth_client_grants', 'mcp_oauth_codes', 'mcp_oauth_tokens',
    'mcp_oauth_refresh_tokens', 'identity_grants', 'identity_mappings',
    'identity_mapping_history', 'change_authority', 'change_authority_history',
    'change_events', 'consumed_authority_requests', 'gateway_resume_grants',
    'gateway_delivery_receipts', 'audit', 'model_requests', 'model_call_attempts',
    'model_call_reservations', 'codex_execution_events', 'codex_execution_intents',
    'execution_action_requests', 'ai_jobs', 'authority_handoff_provenance',
    'authority_handoff_receipts'))
EFFECT_TABLES = ('writer_operations', 'resource_claims', 'revocation_drains',
                 'outbox')


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


# BUG-3147: the real ledger carries BLOB cells (model_providers.
# secret_cipher / service_connections.secret_cipher etc.). Rows are pinned
# with a deterministic type-tag encoding: NULL/text/int/float keep their
# distinct tags; BLOB is pinned by ["b", byte-length, sha256] so ciphertext
# CONTENT never enters the before manifest, freeze receipt, or target
# provenance rows, while any same-length byte change still flips the digest.
# str(bytes), skipped columns, or dropped rows are never used to pass tests.
def encode_cell(value):
    if value is None:
        return ['n']
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        return ['b', len(raw), hashlib.sha256(raw).hexdigest()]
    if isinstance(value, bool):
        return ['i', int(value)]
    if isinstance(value, int):
        return ['i', value]
    if isinstance(value, float):
        return ['f', value]
    if isinstance(value, str):
        return ['s', value]
    raise ValueError('CELL_TYPE_UNSUPPORTED')


def encode_row(values):
    return canon([encode_cell(value) for value in values])


def digest(value):
    return hashlib.sha256(canon(value).encode('utf-8')).hexdigest()


def sha_file(path):
    stream = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            stream.update(chunk)
    return stream.hexdigest()


def regular(path, label):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(label + '_REGULAR_FILE_REQUIRED')
    return info


def file_identity(path):
    path = os.path.realpath(path)
    info = regular(path, 'FREEZE_BOUND_FILE')
    return {'path': path, 'device': info.st_dev, 'inode': info.st_ino,
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
            'sha256': sha_file(path)}


def load_key(path):
    regular(path, 'FREEZE_TRUST_KEY')
    with open(path, 'rb') as handle:
        key = handle.read()
    if len(key) < 32:
        raise ValueError('FREEZE_TRUST_KEY_TOO_SHORT')
    return key


def _readonly(path):
    return sqlite3.connect('file:%s?mode=ro' % os.path.realpath(path), uri=True)


def classify(path):
    if not os.path.lexists(path):
        raise ValueError('SOURCE_LEDGER_ABSENT')
    db = _readonly(path)
    try:
        app = db.execute('PRAGMA application_id').fetchone()[0]
        ver = db.execute('PRAGMA user_version').fetchone()[0]
        row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='authority_runtime_profile'").fetchone()
        profile = (db.execute('SELECT profile FROM authority_runtime_profile WHERE singleton=1').fetchone()
                   if row else None)
        if app != APPLICATION_ID or ver != SCHEMA_VERSION or profile is None:
            raise ValueError('EXPECTED_MODERN_SUPERVISOR_TEST_ONLY_SCHEMA')
        if profile[0] != 'TEST_ONLY':
            raise ValueError('SOURCE_NOT_TEST_ONLY' if profile[0] != 'FORMAL'
                             else 'SOURCE_ALREADY_FORMAL_NO_HANDOFF_NEEDED')
        tables = {name for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if {'tasks', 'events', 'writer_operations'} - tables:
            raise ValueError('EXPECTED_MODERN_SUPERVISOR_TEST_ONLY_SCHEMA')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SOURCE_FOREIGN_KEY_CHECK_FAILED')
        return {'application_id': app, 'user_version': ver, 'profile': profile[0],
                'schema_fingerprint': schema_fingerprint(db),
                'integrity': db.execute('PRAGMA quick_check').fetchone()[0]}
    finally:
        db.close()


def schema_fingerprint(db):
    rows = db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    return digest([{'type': r[0], 'name': r[1],
                    'sql': ' '.join((r[2] or '').split())} for r in rows])


def columns_of(db, table):
    return [row[1] for row in db.execute(
        'PRAGMA table_info("%s")' % table.replace('"', '""'))]


def ordered_rows(db, table, columns):
    statement = 'SELECT %s FROM "%s" ORDER BY rowid' % (
        ','.join('"%s"' % c.replace('"', '""') for c in columns),
        table.replace('"', '""'))
    try:
        return [list(row) for row in db.execute(statement)]
    except sqlite3.OperationalError:
        raise ValueError('WITHOUT_ROWID_TABLE_UNSUPPORTED')


def table_manifest(db):
    manifest = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        columns = columns_of(db, name)
        if not columns:
            raise ValueError('TABLE_COLUMNS_REQUIRED')
        rows = [encode_row(row) for row in ordered_rows(db, name, columns)]
        manifest[name] = {'count': len(rows),
                          'digest': hashlib.sha256(''.join(rows).encode('utf-8')).hexdigest()}
    return manifest


def effects_inventory(db):
    effects = {}
    for table in EFFECT_TABLES:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            effects[table] = db.execute('SELECT count(*) FROM "%s"' % table).fetchone()[0]
        else:
            effects[table] = None
    return effects


def task_pins(db, task_id):
    row = db.execute('SELECT task_id,spec_sha256,checkpoint_sha256,owner,entry,state FROM tasks WHERE task_id=?',
                     (task_id,)).fetchone()
    if row is None:
        raise ValueError('ORIGINAL_TASK_ABSENT_IN_SOURCE')
    # Owner-alias liveness is checked by the signed F4 registration subject
    # binding; the handoff pins only the immutable task/spec/checkpoint.
    if row[1] != ORIGINAL_SPEC or row[2] != ORIGINAL_CHECKPOINT:
        raise ValueError('ORIGINAL_TASK_PIN_MISMATCH')
    return {'task_id': row[0], 'spec_sha256': row[1], 'checkpoint_sha256': row[2],
            'owner': row[3], 'entry': row[4], 'state': row[5]}


def create_freeze(db_path, backup, operation_id, trust_key_file, output,
                  manifest_output, task_id=ORIGINAL_TASK_ID, ttl=300,
                  service_state='STOPPED', writer_state='NO_WRITER',
                  lock_state='EXCLUSIVE_AVAILABLE'):
    if not operation_id or len(operation_id) > 200:
        raise ValueError('BOUNDED_OPERATION_ID_REQUIRED')
    classification = classify(db_path)
    if classification['integrity'] != 'ok':
        raise ValueError('SOURCE_INTEGRITY_CHECK_FAILED')
    pinned = _readonly(db_path)
    try:
        task_pins(pinned, task_id)
    finally:
        pinned.close()
    if os.path.lexists(backup):
        raise ValueError('BACKUP_MUST_NOT_EXIST')
    source = _readonly(db_path)
    try:
        target = sqlite3.connect(backup)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    backup_sha = sha_file(backup)
    snapshot = _readonly(backup)
    try:
        if schema_fingerprint(snapshot) != classification['schema_fingerprint']:
            raise ValueError('SNAPSHOT_SCHEMA_DRIFT')
        manifest = table_manifest(snapshot)
        effects = effects_inventory(snapshot)
        pins = task_pins(snapshot, task_id)
    finally:
        snapshot.close()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(manifest_output, flags, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write(canon({'kind': 'BEFORE_MANIFEST_V1', 'operation_id': operation_id,
                            'tables': manifest, 'effects': effects,
                            'schema_fingerprint': classification['schema_fingerprint'],
                            'task_pins': pins}) + '\n')
    now = int(time.time())
    body = {'kind': FREEZE_KIND, 'schema_version': SCHEMA_VERSION,
            'operation_id': operation_id, 'created_at': now,
            'expires_at': now + int(ttl), 'database': file_identity(db_path),
            'wal': file_identity(db_path + '-wal') if os.path.exists(db_path + '-wal') else None,
            'shm': file_identity(db_path + '-shm') if os.path.exists(db_path + '-shm') else None,
            'backup': {'path': os.path.realpath(backup), 'sha256': backup_sha},
            'manifest_digest': digest(manifest), 'effects': effects,
            'task_pins': pins, 'profile': 'TEST_ONLY',
            'service_state': service_state, 'writer_state': writer_state,
            'lock_state': lock_state}
    signed = {'payload': body, 'hmac_sha256': hmac.new(load_key(trust_key_file),
            canon(body).encode(), hashlib.sha256).hexdigest()}
    descriptor = os.open(output, flags, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write(canon(signed) + '\n')
    return body


def verify_freeze(path, trust_key_file, db_path, backup, operation_id, manifest_path):
    regular(path, 'FREEZE_RECEIPT')
    try:
        with open(path, encoding='utf-8') as handle:
            signed = json.load(handle)
        body = signed['payload']
        signature = signed['hmac_sha256']
    except Exception as exc:
        raise ValueError('FREEZE_INTEGRITY_INVALID') from exc
    if not hmac.compare_digest(hmac.new(load_key(trust_key_file), canon(body).encode(),
                                        hashlib.sha256).hexdigest(), signature):
        raise ValueError('FREEZE_INTEGRITY_INVALID')
    if (body.get('kind') != FREEZE_KIND or body.get('schema_version') != SCHEMA_VERSION
            or body.get('operation_id') != operation_id):
        raise ValueError('FREEZE_BINDING_MISMATCH')
    if int(time.time()) > body.get('expires_at', 0):
        raise ValueError('FREEZE_EXPIRED')
    if (body.get('service_state') != 'STOPPED' or body.get('writer_state') != 'NO_WRITER'
            or body.get('lock_state') != 'EXCLUSIVE_AVAILABLE'):
        raise ValueError('FREEZE_UNSAFE_STATE')
    if (body.get('database') or {}).get('path') != os.path.realpath(db_path):
        raise ValueError('FREEZE_DATABASE_STATE_CHANGED')
    if body.get('backup') != {'path': os.path.realpath(backup), 'sha256': sha_file(backup)}:
        raise ValueError('FREEZE_BACKUP_MISMATCH')
    with open(manifest_path, encoding='utf-8') as handle:
        manifest = json.load(handle)
    if (manifest.get('kind') != 'BEFORE_MANIFEST_V1'
            or manifest.get('operation_id') != operation_id
            or digest(manifest['tables']) != body.get('manifest_digest')
            or manifest.get('effects') != body.get('effects')
            or manifest.get('task_pins') != body.get('task_pins')):
        raise ValueError('FREEZE_MANIFEST_MISMATCH')
    # Content-level revalidation: WAL/-shm coordination files legitimately
    # change on any read open, so the live ledger is pinned by its exact
    # per-table manifest and schema fingerprint instead of file mtimes. A real
    # post-freeze write (service not stopped, drifted effects, changed rows)
    # still fails closed here.
    live = classify(db_path)
    if live['schema_fingerprint'] != manifest.get('schema_fingerprint'):
        raise ValueError('FREEZE_DATABASE_STATE_CHANGED')
    handle = _readonly(db_path)
    try:
        live_manifest = table_manifest(handle)
    finally:
        handle.close()
    if digest(live_manifest) != body.get('manifest_digest'):
        raise ValueError('FREEZE_DATABASE_STATE_CHANGED')
    return body, manifest


def validate_decision(value, anchor_fingerprint, task_id=ORIGINAL_TASK_ID):
    required = {'kind', 'approval', 'task_id', 'immutable_spec_sha256',
                'checkpoint_sha256', 'project_isolation_only', 'scope',
                'allowed_files', 'initial_trust', 'business_binding', 'caller',
                'data_handoff', 'secrets_in_response',
                'creates_grant_or_signature',
                'requires_author_installation_permission'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('DECISION_FIELDS_EXACT')
    if value['kind'] != DECISION_KIND:
        raise ValueError('DECISION_KIND_INVALID')
    approval = value['approval']
    if (not isinstance(approval, dict) or set(approval) != {'decision', 'approval_ref', 'approved_at', 'decided_by'}
            or approval['decision'] != 'APPROVE'
            or not isinstance(approval['approval_ref'], str) or not approval['approval_ref'].strip()
            or not isinstance(approval['decided_by'], str) or not approval['decided_by'].strip()
            or not isinstance(approval['approved_at'], (int, float))):
        raise ValueError('OWNER_APPROVAL_FACT_REQUIRED')
    if (value['task_id'] != task_id or value['immutable_spec_sha256'] != ORIGINAL_SPEC
            or value['checkpoint_sha256'] != ORIGINAL_CHECKPOINT):
        raise ValueError('DECISION_TASK_PIN_MISMATCH')
    if value['project_isolation_only'] is not True or sorted(value['scope']) != sorted(APPROVED_SCOPE) \
            or sorted(value['allowed_files']) != sorted(APPROVED_FILES):
        raise ValueError('DECISION_SCOPE_NOT_PROJECT_ISOLATED')
    trust = value['initial_trust']
    if (not isinstance(trust, dict) or trust.get('canonical_owner_alias') != 'developer'
            or not trust.get('named_signer_custodian')
            or bool(trust.get('existing_authorized_public_key_ref')) == bool(trust.get('or_authorize_first_project_root'))):
        raise ValueError('DECISION_TRUST_ANCHOR_UNBOUND')
    if trust.get('existing_authorized_public_key_ref') and trust['existing_authorized_public_key_ref'] != anchor_fingerprint:
        raise ValueError('DECISION_ANCHOR_FINGERPRINT_MISMATCH')
    binding = value['business_binding']
    if (not isinstance(binding, dict) or sorted(binding) != sorted(
            ('developer_identity_ref', 'qa_identity_and_key_ref', 'security_identity_and_key_ref'))
            or any(not binding[key] for key in binding)):
        raise ValueError('DECISION_BUSINESS_IDENTITIES_UNBOUND')
    caller = value['caller']
    if (not isinstance(caller, dict)
            or not (caller.get('trusted_host_source_ref') or caller.get('or_authorize_project_local_python_caller_issuer'))
            or not isinstance(caller.get('grant_or_lease_valid_until'), (int, float))
            or caller['grant_or_lease_valid_until'] <= time.time()):
        raise ValueError('DECISION_CALLER_HOST_OR_LEASE_UNBOUND')
    handoff = value['data_handoff']
    if (not isinstance(handoff, dict)
            or handoff.get('approve_source_preserving_same_task_handoff') is not True
            or handoff.get('create_new_task') is not False
            or handoff.get('sql_profile_flip') is not False
            or handoff.get('promote_test_credentials_or_history') is not False
            or not isinstance(handoff.get('carry_over_tables'), list) or not handoff['carry_over_tables']):
        raise ValueError('DECISION_HANDOFF_TERMS_INVALID')
    if (value['secrets_in_response'] is not False
            or value['creates_grant_or_signature'] is not False
            or value['requires_author_installation_permission'] is not False):
        raise ValueError('DECISION_SCOPE_ESCAPED')
    return {'decision_digest': digest(value),
            'carry_over_tables': sorted(handoff['carry_over_tables']),
            'grant_or_lease_valid_until': float(caller['grant_or_lease_valid_until'])}


def read_json_file(path, label):
    regular(path, label)
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)

def _carry_order(snapshot, carry):
    """Deterministic FK-respecting import order (stable on ties)."""
    carry_set = set(carry)
    deps = {}
    for name in carry:
        refs = {row[2] for row in snapshot.execute(
            'PRAGMA foreign_key_list("%s")' % name.replace('"', '""'))}
        deps[name] = sorted((refs & carry_set) - {name})
    order = []
    placed = set()

    def visit(name, stack):
        if name in placed:
            return
        if name in stack:
            raise ValueError('CARRY_OVER_FK_CYCLE_REQUIRES_EXPLICIT_ORDER')
        for dep in deps[name]:
            visit(dep, stack | {name})
        placed.add(name)
        order.append(name)
    for name in carry:
        visit(name, frozenset())
    return order


def handoff(db_path, backup, freeze_path, manifest_path, trust_key_file,
            decision_file, anchor_public_key_file, bindings_file, caller_file,
            target, operation_id):
    if not operation_id or len(operation_id) > 200:
        raise ValueError('BOUNDED_OPERATION_ID_REQUIRED')
    if os.path.lexists(target):
        existing = _query(target, operation_id, allow_missing=True)
        if existing is not None and existing['operation_id'] == operation_id:
            return existing
        raise ValueError('TARGET_OCCUPIED_OR_INCOMPLETE')
    body, manifest = verify_freeze(freeze_path, trust_key_file, db_path, backup,
                                   operation_id, manifest_path)
    anchor, anchor_fingerprint = load_anchor(anchor_public_key_file)
    pins = body['task_pins']
    decision = validate_decision(read_json_file(decision_file, 'OWNER_DECISION'),
                                 anchor_fingerprint, pins['task_id'])
    bindings = require_task_bindings(read_json_file(bindings_file, 'HOST_BINDINGS'),
                                     anchor, anchor_fingerprint, pins['task_id'])
    caller = verify_caller_context(read_json_file(caller_file, 'HOST_CALLER'),
                                   anchor, anchor_fingerprint, pins['task_id'])
    if caller['expires_at'] > decision['grant_or_lease_valid_until']:
        raise ValueError('CALLER_LEASE_EXCEEDS_APPROVED_GRANT')
    # Principal attestations must also stay inside the real approved original
    # grant/renewal epoch; the code adds no separate invented term.
    if any(value['expires_at'] > decision['grant_or_lease_valid_until']
           for value in bindings.values()):
        raise ValueError('PRINCIPAL_LEASE_EXCEEDS_APPROVED_GRANT')
    from development_identity_adapter import TrustedRegistrationVerifier
    from task_supervisor import Supervisor
    request = {'operation_id': operation_id, 'backup_sha256': body['backup']['sha256'],
               'manifest_digest': body['manifest_digest'],
               'decision_digest': decision['decision_digest'],
               'trust_root_fingerprint': anchor_fingerprint,
               'target': os.path.realpath(target)}
    request_digest = digest(request)
    supervisor = Supervisor(target, clock=time.time,
                            development_identity_verifier=TrustedRegistrationVerifier(anchor))
    db = supervisor.db
    snapshot = None
    try:
        stored = db.execute('SELECT profile FROM authority_runtime_profile WHERE singleton=1').fetchone()
        if stored[0] != 'FORMAL':
            raise ValueError('FORMAL_TARGET_LEGITIMATE_INITIALIZATION_REQUIRED')
        snapshot = _readonly(backup)
        if (schema_fingerprint(snapshot) != manifest['schema_fingerprint']
                or table_manifest(snapshot) != manifest['tables']):
            raise ValueError('SNAPSHOT_CHANGED_AFTER_FREEZE')
        db.execute('BEGIN IMMEDIATE')
        _failpoint('after_lock')
        db.execute('''CREATE TABLE authority_handoff_provenance(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,source_table TEXT NOT NULL,
          row_ordinal INTEGER NOT NULL,row_json TEXT NOT NULL,row_sha256 TEXT NOT NULL,
          UNIQUE(source_table,row_ordinal))''')
        db.execute('''CREATE TABLE authority_handoff_receipts(
          operation_id TEXT PRIMARY KEY,request_digest TEXT NOT NULL,
          backup_sha256 TEXT NOT NULL,receipt_json TEXT NOT NULL,
          receipt_sha256 TEXT NOT NULL,created_at REAL NOT NULL)''')
        _failpoint('after_tables')
        carry = decision['carry_over_tables']
        if set(carry) & DISALLOWED_CARRY:
            raise ValueError('CARRY_OVER_TABLE_DENIED')
        source_tables = {name for (name,) in snapshot.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if set(carry) - source_tables:
            raise ValueError('CARRY_OVER_TABLE_ABSENT_IN_SOURCE')
        for name in _carry_order(snapshot, carry):
            exists = db.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?', (name,)).fetchone()
            if exists is None:
                statement = snapshot.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?', (name,)).fetchone()[0]
                db.execute(statement)
            columns = columns_of(db, name)
            if columns != columns_of(snapshot, name):
                raise ValueError('CARRY_OVER_COLUMNS_MISMATCH')
            for row in ordered_rows(snapshot, name, columns):
                if name == 'tasks':
                    grant = dict(zip(columns, row))
                    if grant.get('task_id') == pins['task_id']:
                        # Same-task invariant, unchanged: the pinned task being
                        # handed over must arrive grant-free.
                        if (grant.get('authority_state') not in (None, 'NONE')
                                or grant.get('lease_id') not in (None, 'UNKNOWN')
                                or grant.get('started_at') is not None):
                            raise ValueError(
                                'SOURCE_TASK_GRANT_HISTORY_RECONCILIATION_REQUIRED')
                    elif grant.get('authority_state') not in (None, 'NONE',
                                                              'REVOKED'):
                        # BUG-3147C same-task carry scope: an unrelated task's
                        # terminal REVOKED row is preserved history and carries
                        # verbatim (all history stays intact here and byte-
                        # identical in authority_handoff_provenance). A live,
                        # in-flight or unknown grant (VALID/REVOKING/UNKNOWN or
                        # anything outside the reconciled set) is never
                        # promoted into the project-isolated FORMAL ledger; the
                        # real window must first close it through the original
                        # supervisor/fence revocation channel. No row is
                        # deleted or rewritten to fake a pass.
                        raise ValueError(
                            'SOURCE_TASK_GRANT_HISTORY_RECONCILIATION_REQUIRED')
                db.execute('INSERT INTO "%s" (%s) VALUES(%s)' % (
                    name.replace('"', '""'),
                    ','.join('"%s"' % c.replace('"', '""') for c in columns),
                    ','.join('?' * len(columns))), row)
            _failpoint('carry_' + name)
        carried = {}
        ordinal_total = 0
        for name in sorted(manifest['tables']):
            rows_sha = hashlib.sha256()
            count = 0
            for values in ordered_rows(snapshot, name, columns_of(snapshot, name)):
                row = encode_row(values)
                db.execute('INSERT INTO authority_handoff_provenance(source_table,row_ordinal,row_json,row_sha256) VALUES(?,?,?,?)',
                           (name, count, row, hashlib.sha256(row.encode('utf-8')).hexdigest()))
                rows_sha.update(row.encode('utf-8'))
                count += 1
            ordinal_total += count
            if count != manifest['tables'][name]['count'] or rows_sha.hexdigest() != manifest['tables'][name]['digest']:
                raise ValueError('PRESERVATION_INVARIANT_MISMATCH')
            carried[name] = {'count': count, 'digest': rows_sha.hexdigest()}
        _failpoint('after_provenance')
        for table in ('events', 'writer_operations', 'writer_receipts',
                      'resource_claims', 'revocation_drains'):
            if db.execute('SELECT count(*) FROM "%s"' % table).fetchone()[0] != 0:
                raise ValueError('PROMOTED_TEST_AUTHORITY_DETECTED')
        task_row = db.execute('SELECT task_id,spec_sha256,checkpoint_sha256,authority_state,lease_id FROM tasks WHERE task_id=?',
                              (pins['task_id'],)).fetchone()
        if (task_row is None or task_row[1] != pins['spec_sha256']
                or task_row[2] != pins['checkpoint_sha256']
                or task_row[3] not in (None, 'NONE')
                or task_row[4] not in (None, 'UNKNOWN')):
            raise ValueError('SAME_TASK_CARRY_OVER_INVARIANT_MISMATCH')
        receipt = {'state': 'COMMITTED', 'operation_id': operation_id,
                   'request_digest': request_digest,
                   'source_ledger_sha256': body['database']['sha256'],
                   'backup_sha256': body['backup']['sha256'],
                   'schema_fingerprint': manifest['schema_fingerprint'],
                   'manifest_digest': body['manifest_digest'],
                   'preserved_tables': carried,
                   'preserved_row_count': ordinal_total,
                   'carry_over_tables': carry, 'effects': body['effects'],
                   'task_id': pins['task_id'], 'spec_sha256': pins['spec_sha256'],
                   'checkpoint_sha256': pins['checkpoint_sha256'],
                   'decision_digest': decision['decision_digest'],
                   'trust_root_fingerprint': anchor_fingerprint,
                   'principal_digests': {role: digest(bindings[role]) for role in sorted(bindings)},
                   'caller_digest': digest(caller),
                   'caller_valid_until': caller['expires_at'],
                   'profile': 'FORMAL',
                   'promoted_authority': 'NONE',
                   'first_registration': 'REQUIRED_VIA_SIGNED_F4_REGISTER',
                   'generation': 1}
        raw = canon(receipt)
        db.execute('INSERT INTO authority_handoff_receipts VALUES(?,?,?,?,?,?)',
                   (operation_id, request_digest, body['backup']['sha256'], raw,
                    hashlib.sha256(raw.encode('utf-8')).hexdigest(), time.time()))
        _failpoint('before_commit')
        db.execute('COMMIT')
        return receipt
    except Exception:
        try:
            db.execute('ROLLBACK')
        except sqlite3.Error:
            pass
        raise
    finally:
        if snapshot is not None:
            snapshot.close()
        supervisor.close()


def _failpoint(name):
    if os.environ.get('XUANJUN_HANDOFF_FAIL_AT') == name:
        raise RuntimeError('INJECTED_' + name)


RECEIPT_FIELDS = {'state', 'operation_id', 'request_digest', 'source_ledger_sha256',
                  'backup_sha256', 'schema_fingerprint', 'manifest_digest',
                  'preserved_tables', 'preserved_row_count', 'carry_over_tables',
                  'effects', 'task_id', 'spec_sha256', 'checkpoint_sha256',
                  'decision_digest', 'trust_root_fingerprint', 'principal_digests',
                  'caller_digest', 'caller_valid_until', 'profile',
                  'promoted_authority', 'first_registration', 'generation'}


def _query(target, operation_id, allow_missing=False):
    if not os.path.lexists(target):
        if allow_missing:
            return None
        raise ValueError('TARGET_ABSENT')
    db = _readonly(target)
    try:
        row = db.execute('SELECT request_digest,backup_sha256,receipt_json,receipt_sha256 FROM authority_handoff_receipts WHERE operation_id=?',
                         (operation_id,)).fetchone()
        if row is None:
            if allow_missing:
                return None
            raise ValueError('HANDOFF_RECEIPT_MISSING')
        receipt = json.loads(row[2])
        raw = canon(receipt)
        if row[2] != raw or not hmac.compare_digest(hashlib.sha256(raw.encode('utf-8')).hexdigest(), row[3]):
            raise ValueError('HANDOFF_RECEIPT_SHA256_MISMATCH')
        if set(receipt) != RECEIPT_FIELDS or receipt['state'] != 'COMMITTED' or receipt['operation_id'] != operation_id:
            raise ValueError('HANDOFF_RECEIPT_BINDING_MISMATCH')
        profile = db.execute('SELECT profile FROM authority_runtime_profile WHERE singleton=1').fetchone()
        if profile[0] != 'FORMAL':
            raise ValueError('FORMAL_TARGET_LEGITIMATE_INITIALIZATION_REQUIRED')
        for name, expected in receipt['preserved_tables'].items():
            stream = hashlib.sha256()
            count = 0
            for row_json, row_sha256 in db.execute(
                    'SELECT row_json,row_sha256 FROM authority_handoff_provenance WHERE source_table=? ORDER BY row_ordinal',
                    (name,)).fetchall():
                if not hmac.compare_digest(
                        hashlib.sha256(row_json.encode('utf-8')).hexdigest(), row_sha256):
                    raise ValueError('PROVENANCE_ROW_TAMPERED')
                stream.update(row_json.encode('utf-8'))
                count += 1
            if count != expected['count'] or stream.hexdigest() != expected['digest']:
                raise ValueError('PRESERVATION_INVARIANT_MISMATCH')
        return receipt
    except sqlite3.OperationalError:
        if allow_missing:
            return None
        raise
    finally:
        db.close()


def query(target, operation_id):
    return _query(target, operation_id)


def switch(pointer_file, trust_key_file, target, source_db, operation_id):
    receipt = _query(target, operation_id)
    if os.path.lexists(pointer_file):
        body = _read_pointer(pointer_file, trust_key_file)
        if body['operation_id'] != operation_id or body['target']['path'] != os.path.realpath(target):
            raise ValueError('AUTHORITY_REFERENCE_ALREADY_SWITCHED')
        return body
    regular(source_db, 'SOURCE_LEDGER')
    now = int(time.time())
    body = {'kind': POINTER_KIND, 'operation_id': operation_id,
            'receipt_sha256': digest(receipt), 'switched_at': now,
            'target': file_identity(target),
            'former_authority_view': dict(file_identity(source_db), isolation='ISOLATED_READ_ONLY'),
            'single_authority_reference': True,
            'next_step': 'SIGNED_F4_REGISTER_ONCE_THEN_CLAIM_ONCE_BY_CUSTODIAN'}
    signed = {'payload': body, 'hmac_sha256': hmac.new(load_key(trust_key_file),
            canon(body).encode(), hashlib.sha256).hexdigest()}
    descriptor = os.open(pointer_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write(canon(signed) + '\n')
    return body


def _read_pointer(pointer_file, trust_key_file):
    if not os.path.lexists(pointer_file):
        raise ValueError('AUTHORITY_REFERENCE_ABSENT_OR_ROLLED_BACK')
    regular(pointer_file, 'AUTHORITY_REFERENCE')
    with open(pointer_file, encoding='utf-8') as handle:
        signed = json.load(handle)
    body = signed['payload']
    if body.get('kind') != POINTER_KIND or not hmac.compare_digest(
            hmac.new(load_key(trust_key_file), canon(body).encode(), hashlib.sha256).hexdigest(),
            signed['hmac_sha256']):
        raise ValueError('AUTHORITY_REFERENCE_INTEGRITY_INVALID')
    return body


def reconcile(pointer_file, trust_key_file):
    body = _read_pointer(pointer_file, trust_key_file)
    former = body['former_authority_view']
    path = former['path']
    if not os.path.lexists(path):
        return {'state': 'ISOLATED', 'former_ledger': 'ABSENT_RETAIN_ARCHIVE',
                'operation_id': body['operation_id']}
    current = file_identity(path)
    changed = any(current[name] != former[name] for name in ('sha256', 'size', 'mtime_ns'))
    if changed:
        raise ValueError('TEST_WRITE_AFTER_SWITCH_DETECTED')
    target = body['target']
    if file_identity(target['path'])['sha256'] != target['sha256']:
        return {'state': 'TARGET_WRITE_EXPECTED_BY_F4', 'operation_id': body['operation_id']}
    return {'state': 'ISOLATED', 'operation_id': body['operation_id']}


def rollback(pointer_file, trust_key_file):
    body = _read_pointer(pointer_file, trust_key_file)
    reverted = pointer_file + '.reverted'
    if os.path.lexists(reverted):
        raise ValueError('ROLLBACK_ALREADY_RECORDS')
    record = {'kind': 'AUTHORITY_REFERENCE_ROLLBACK_V1', 'operation_id': body['operation_id'],
              'reverted_at': int(time.time()), 'previous_pointer': body,
              'data_destructive': False,
              'instruction': 'custodian restores the pre-switch reference; target and source ledgers stay intact'}
    descriptor = os.open(reverted, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write(canon(record) + '\n')
    os.rename(pointer_file, reverted + '.pointer')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline source-preserving authority handoff; executed by the designated custodian')
    sub = parser.add_subparsers(dest='cmd')
    p = sub.add_parser('probe'); p.add_argument('--db', required=True)
    f = sub.add_parser('create-freeze')
    for name in ('db', 'backup', 'operation-id', 'trust-key-file', 'output', 'manifest-output'):
        f.add_argument('--' + name, required=True)
    f.add_argument('--ttl-seconds', type=int, default=300)
    h = sub.add_parser('handoff')
    for name in ('source-db', 'backup', 'freeze-receipt', 'manifest-file', 'trust-key-file',
                 'decision-file', 'anchor-public-key-file', 'bindings-file',
                 'caller-file', 'target', 'operation-id'):
        h.add_argument('--' + name, required=True)
    q = sub.add_parser('query')
    q.add_argument('--target', required=True)
    q.add_argument('--operation-id', required=True)
    s = sub.add_parser('switch')
    for name in ('pointer-file', 'trust-key-file', 'target', 'source-db', 'operation-id'):
        s.add_argument('--' + name, required=True)
    r = sub.add_parser('reconcile'); r.add_argument('--pointer-file', required=True); r.add_argument('--trust-key-file', required=True)
    b = sub.add_parser('rollback'); b.add_argument('--pointer-file', required=True); b.add_argument('--trust-key-file', required=True)
    x = parser.parse_args(argv)
    try:
        if x.cmd == 'probe':
            out = classify(x.db); out['state'] = 'CLASSIFIED'
        elif x.cmd == 'create-freeze':
            out = create_freeze(x.db, x.backup, x.operation_id, x.trust_key_file,
                                x.output, x.manifest_output, ttl=x.ttl_seconds)
        elif x.cmd == 'handoff':
            out = handoff(x.source_db, x.backup, x.freeze_receipt, x.manifest_file,
                          x.trust_key_file, x.decision_file, x.anchor_public_key_file,
                          x.bindings_file, x.caller_file, x.target, x.operation_id)
        elif x.cmd == 'query':
            out = query(x.target, x.operation_id)
        elif x.cmd == 'switch':
            out = switch(x.pointer_file, x.trust_key_file, x.target, x.source_db, x.operation_id)
        elif x.cmd == 'reconcile':
            out = reconcile(x.pointer_file, x.trust_key_file)
        elif x.cmd == 'rollback':
            out = rollback(x.pointer_file, x.trust_key_file)
        else:
            parser.error('a command is required')
        print(canon(out))
        return 0
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r'[A-Z_0-9]{1,160}', code):
            code = 'HANDOFF_REJECTED'
        print(canon({'state': 'REJECTED', 'error': code}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
