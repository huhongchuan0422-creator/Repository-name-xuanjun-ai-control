"""Durable canonical source authority for supervised development tasks.

This ledger can issue and revoke source-level writer authority used by the
local fencing framework.  It does not grant production credentials,
resource-native capability, deployment permission, or production takeover.
"""
from __future__ import print_function

import hashlib
import json
import math
import os
import re
import sqlite3
import time


UNKNOWN = 'UNKNOWN'
TERMINAL = frozenset(('SUCCESS', 'FAILURE', 'CANCELLED', 'HOLD',
                      'CAPABILITY_UNAVAILABLE'))
REAL_PROGRESS = frozenset(('SOURCE_COMMIT', 'TEST_RUN', 'ARTIFACT',
                           'PHASE_EXECUTION'))
ACTIVE = frozenset(('RECEIVED', 'STARTED', 'RUNNING', 'HANDOFF_PENDING'))
SUPERVISOR_APPLICATION_ID = 0x58534A31
SUPERVISOR_SCHEMA_VERSION = 3
AUTHORITY_STATES = frozenset(('NONE', 'VALID', 'REVOKING', 'REVOKED',
                              UNKNOWN))
V2_TASK_COLUMNS = (
    'task_id', 'parent_task_id', 'stage', 'writer_scope', 'state', 'owner',
    'entry', 'run_id', 'session_id', 'attempt_id', 'checkpoint_sha256',
    'spec_sha256', 'lease_id', 'fence', 'epoch', 'next_action',
    'dependencies_json', 'completion_json', 'last_real_progress_at',
    'received_at', 'started_at', 'handoff_requested_at', 'last_event_at',
    'max_fence', 'max_epoch', 'progress_deadline', 'receipt_deadline',
    'started_deadline', 'terminal_deadline', 'handoff_deadline',
    'writer_stopped', 'effects_reconciled', 'receiver_accepted',
    'old_fence_invalidated', 'recovery_level', 'recovery_generation',
    'created_at', 'updated_at',
)
TASK_COLUMNS = V2_TASK_COLUMNS + (
    'authority_state', 'authority_valid_until', 'authority_run_id',
    'authority_session_id', 'authority_gateway_id', 'resource_scope_json',
    'receiver_ack_json', 'receiver_ack_sha256', 'resource_scope_digest',
    'coverage_digest', 'authority_caller_id', 'authority_lock_provider_id',
    'last_trusted_time',
)
PERSISTENT_COLUMNS = {
    'events': ('task_id', 'attempt_id', 'event_id', 'kind',
               'observed_at', 'evidence_kind', 'evidence_ref',
               'payload_json'),
    'outbox': ('outbox_id', 'task_id', 'attempt_id', 'event_id',
               'payload_json', 'attempts', 'next_attempt_at',
               'delivered_at', 'dead_lettered_at', 'last_error'),
    'supervisor_heartbeats': ('instance_id', 'observed_at', 'process_ref',
                              'evidence_ref', 'updated_at'),
    'writer_operations': ('operation_id', 'task_id', 'attempt_id', 'event_id',
                          'resource_key', 'ticket_sha256', 'caller_sha256',
                          'payload_json', 'state', 'created_at', 'updated_at'),
    'writer_reconcile_evidence': ('operation_id', 'evidence_id', 'outcome',
                                  'evidence_json', 'observed_at'),
    'writer_receipts': ('operation_id', 'receipt_json', 'receipt_sha256',
                        'created_at'),
    'resource_claims': ('resource_key', 'task_id', 'attempt_id', 'fence',
                        'epoch', 'state', 'updated_at'),
    'resource_invalidation_receipts': ('task_id', 'old_attempt_id',
                                       'resource_key', 'receipt_json',
                                       'receipt_sha256', 'created_at'),
    'authority_recovery_evidence': ('task_id', 'attempt_id', 'evidence_id',
                                    'evidence_json', 'created_at'),
    'revocation_drains': ('task_id', 'attempt_id', 'provider_id',
                          'receipt_json', 'receipt_sha256', 'created_at'),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class Supervisor(object):
    """SQLite-backed state machine; one instance is enough per ledger DB."""

    migration_fail_at = None

    @classmethod
    def _readonly_preflight(cls, path):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return
        uri = 'file:%s?mode=ro&immutable=1' % os.path.abspath(path)
        db = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            app = db.execute('PRAGMA application_id').fetchone()[0]
            ver = db.execute('PRAGMA user_version').fetchone()[0]
            tasks = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).fetchone()
            any_table = db.execute("""SELECT 1 FROM sqlite_master
              WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1""").fetchone()
            if tasks is not None:
                if app != SUPERVISOR_APPLICATION_ID:
                    raise ValueError('SUPERVISOR_DATABASE_ID_MISMATCH')
                if ver in (1, 2):
                    raise ValueError('HOLD_MIGRATION_REQUIRED')
                if ver != SUPERVISOR_SCHEMA_VERSION:
                    raise ValueError('UNSUPPORTED_SUPERVISOR_SCHEMA')
            elif any_table is not None:
                raise ValueError('SUPERVISOR_DATABASE_ID_MISMATCH')
        finally:
            db.close()

    def __init__(self, path, clock=None):
        self.path = path
        self.clock = clock or time.time
        # Read-only immutable preflight prevents an old WAL-mode v1/v2 ledger
        # from creating wal/shm/journal sidecars merely because normal runtime
        # attempted to open it.
        self._readonly_preflight(path)
        self.db = sqlite3.connect(path, timeout=10, isolation_level='IMMEDIATE')
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('PRAGMA foreign_keys=ON')
            self._schema()
            self.db.execute('PRAGMA journal_mode=WAL')
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def _migration_failpoint(self, name):
        """No-op production hook overridden only by fault-injection tests."""
        return None

    def _index_columns(self, name):
        return tuple(row['name'] for row in
                     self.db.execute('PRAGMA index_info("%s")' %
                                     name.replace('"', '""')))

    def _validate_schema(self, allow_previous=False):
        task_columns = tuple(row['name'] for row in
                             self.db.execute('PRAGMA table_info(tasks)'))
        if task_columns != TASK_COLUMNS:
            raise ValueError('SUPERVISOR_TASK_SCHEMA_MISMATCH')
        for table, expected in PERSISTENT_COLUMNS.items():
            actual = tuple(row['name'] for row in self.db.execute(
                'PRAGMA table_info("%s")' % table))
            if actual != expected:
                raise ValueError('SUPERVISOR_AUX_SCHEMA_MISMATCH')

        def primary_key(table):
            rows = self.db.execute(
                'PRAGMA table_info("%s")' % table).fetchall()
            return tuple(row['name'] for row in
                         sorted((r for r in rows if r['pk']),
                                key=lambda r: r['pk']))

        if (primary_key('tasks') != ('task_id',)
                or primary_key('events') !=
                   ('task_id', 'attempt_id', 'event_id')
                or primary_key('outbox') != ('outbox_id',)
                or primary_key('writer_operations') != ('operation_id',)
                or primary_key('writer_receipts') != ('operation_id',)
                or primary_key('resource_claims') != ('resource_key',)
                or primary_key('authority_recovery_evidence') !=
                   ('task_id','attempt_id','evidence_id')
                or primary_key('revocation_drains') !=
                   ('task_id','attempt_id')):
            raise ValueError('SUPERVISOR_PRIMARY_KEY_MISMATCH')

        def unique_sets(table):
            values = []
            for row in self.db.execute('PRAGMA index_list("%s")' % table):
                if row['unique']:
                    values.append(self._index_columns(row['name']))
            return values

        if (('writer_scope',) not in unique_sets('tasks')
                or ('task_id', 'attempt_id', 'event_id')
                   not in unique_sets('outbox')
                or ('task_id', 'attempt_id', 'event_id')
                   not in unique_sets('writer_operations')
                or ('task_id', 'old_attempt_id', 'resource_key')
                   not in unique_sets('resource_invalidation_receipts')):
            raise ValueError('SUPERVISOR_UNIQUE_KEY_MISMATCH')
        foreign_expected = {
            'events': ('tasks','task_id','task_id'),
            'outbox': ('tasks','task_id','task_id'),
            'writer_operations': ('tasks','task_id','task_id'),
            'writer_reconcile_evidence':
                ('writer_operations','operation_id','operation_id'),
            'writer_receipts':
                ('writer_operations','operation_id','operation_id'),
            'resource_claims': ('tasks','task_id','task_id'),
            'resource_invalidation_receipts':
                ('tasks','task_id','task_id'),
            'authority_recovery_evidence':
                ('tasks','task_id','task_id'),
            'revocation_drains': ('tasks','task_id','task_id'),
        }
        for table, expected in foreign_expected.items():
            rows = list(self.db.execute(
                'PRAGMA foreign_key_list("%s")' % table))
            if len(rows) != 1:
                raise ValueError('SUPERVISOR_FOREIGN_KEY_MISMATCH')
            row = rows[0]
            if (row['table'], row['from'], row['to']) != expected:
                raise ValueError('SUPERVISOR_FOREIGN_KEY_MISMATCH')
        required_indexes = {
            'task_ready_idx': ('state', 'updated_at', 'task_id'),
            'outbox_due_idx': ('delivered_at', 'next_attempt_at', 'outbox_id'),
            'writer_operations_state_idx':
                ('task_id', 'state', 'updated_at', 'operation_id'),
        }
        for name, expected in required_indexes.items():
            if self._index_columns(name) != expected:
                raise ValueError('SUPERVISOR_INDEX_MISMATCH')
        return False

    @staticmethod
    def _v3_schema_statements():
        return (
        '''CREATE TABLE IF NOT EXISTS tasks(
          task_id TEXT PRIMARY KEY,
          parent_task_id TEXT NOT NULL,
          stage TEXT NOT NULL,
          writer_scope TEXT NOT NULL UNIQUE,
          state TEXT NOT NULL,
          owner TEXT NOT NULL,
          entry TEXT NOT NULL,
          run_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          attempt_id TEXT NOT NULL,
          checkpoint_sha256 TEXT NOT NULL,
          spec_sha256 TEXT NOT NULL,
          lease_id TEXT NOT NULL,
          fence INTEGER,
          epoch INTEGER,
          next_action TEXT NOT NULL,
          dependencies_json TEXT NOT NULL,
          completion_json TEXT NOT NULL,
          last_real_progress_at REAL,
          received_at REAL,
          started_at REAL,
          handoff_requested_at REAL,
          last_event_at REAL NOT NULL,
          max_fence INTEGER NOT NULL DEFAULT 0,
          max_epoch INTEGER NOT NULL DEFAULT 0,
          progress_deadline REAL NOT NULL,
          receipt_deadline REAL NOT NULL,
          started_deadline REAL NOT NULL,
          terminal_deadline REAL NOT NULL,
          handoff_deadline REAL NOT NULL,
          writer_stopped TEXT NOT NULL,
          effects_reconciled TEXT NOT NULL,
          receiver_accepted TEXT NOT NULL,
          old_fence_invalidated TEXT NOT NULL,
          recovery_level INTEGER NOT NULL DEFAULT 0,
          recovery_generation INTEGER NOT NULL DEFAULT 0,
          created_at REAL NOT NULL,
          updated_at REAL NOT NULL,
          authority_state TEXT NOT NULL DEFAULT 'NONE',
          authority_valid_until REAL,
          authority_run_id TEXT NOT NULL DEFAULT 'UNKNOWN',
          authority_session_id TEXT NOT NULL DEFAULT 'UNKNOWN',
          authority_gateway_id TEXT NOT NULL DEFAULT 'UNKNOWN',
          resource_scope_json TEXT NOT NULL DEFAULT '[]',
          receiver_ack_json TEXT NOT NULL DEFAULT '{}',
          receiver_ack_sha256 TEXT NOT NULL DEFAULT 'UNKNOWN',
          resource_scope_digest TEXT NOT NULL DEFAULT 'UNKNOWN',
          coverage_digest TEXT NOT NULL DEFAULT 'UNKNOWN',
          authority_caller_id TEXT NOT NULL DEFAULT 'UNKNOWN',
          authority_lock_provider_id TEXT NOT NULL DEFAULT 'UNKNOWN',
          last_trusted_time REAL
        )''',
        '''CREATE TABLE IF NOT EXISTS events(
          task_id TEXT NOT NULL, attempt_id TEXT NOT NULL, event_id TEXT NOT NULL,
          kind TEXT NOT NULL, observed_at REAL NOT NULL, evidence_kind TEXT NOT NULL,
          evidence_ref TEXT NOT NULL, payload_json TEXT NOT NULL,
          PRIMARY KEY(task_id,attempt_id,event_id),
          FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
        '''CREATE TABLE IF NOT EXISTS outbox(
          outbox_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
          attempt_id TEXT NOT NULL,event_id TEXT NOT NULL,payload_json TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,next_attempt_at REAL NOT NULL,
          delivered_at REAL,dead_lettered_at REAL,last_error TEXT NOT NULL DEFAULT '',
          UNIQUE(task_id,attempt_id,event_id),
          FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
        '''CREATE TABLE IF NOT EXISTS supervisor_heartbeats(
          instance_id TEXT PRIMARY KEY,observed_at REAL NOT NULL,
          process_ref TEXT NOT NULL,evidence_ref TEXT NOT NULL,
          updated_at REAL NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS writer_operations(
          operation_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,
          attempt_id TEXT NOT NULL,event_id TEXT NOT NULL,resource_key TEXT NOT NULL,
          ticket_sha256 TEXT NOT NULL,caller_sha256 TEXT NOT NULL,
          payload_json TEXT NOT NULL,state TEXT NOT NULL,
          created_at REAL NOT NULL,updated_at REAL NOT NULL,
          UNIQUE(task_id,attempt_id,event_id),
          FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
        '''CREATE TABLE IF NOT EXISTS writer_reconcile_evidence(
          operation_id TEXT NOT NULL,evidence_id TEXT NOT NULL,outcome TEXT NOT NULL,
          evidence_json TEXT NOT NULL,observed_at REAL NOT NULL,
          PRIMARY KEY(operation_id,evidence_id),
          FOREIGN KEY(operation_id) REFERENCES writer_operations(operation_id))''',
        '''CREATE TABLE IF NOT EXISTS writer_receipts(
          operation_id TEXT PRIMARY KEY,receipt_json TEXT NOT NULL,
          receipt_sha256 TEXT NOT NULL,created_at REAL NOT NULL,
          FOREIGN KEY(operation_id) REFERENCES writer_operations(operation_id))''',
        '''CREATE TABLE IF NOT EXISTS resource_claims(
          resource_key TEXT PRIMARY KEY,task_id TEXT NOT NULL,
          attempt_id TEXT NOT NULL,fence INTEGER NOT NULL,epoch INTEGER NOT NULL,
          state TEXT NOT NULL,updated_at REAL NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
        '''CREATE TABLE IF NOT EXISTS resource_invalidation_receipts(
          task_id TEXT NOT NULL,old_attempt_id TEXT NOT NULL,
          resource_key TEXT NOT NULL,receipt_json TEXT NOT NULL,
          receipt_sha256 TEXT NOT NULL,created_at REAL NOT NULL,
          UNIQUE(task_id,old_attempt_id,resource_key),
          FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
        '''CREATE TABLE IF NOT EXISTS authority_recovery_evidence(
          task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,evidence_id TEXT NOT NULL,
          evidence_json TEXT NOT NULL,created_at REAL NOT NULL,
          PRIMARY KEY(task_id,attempt_id,evidence_id),
          FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
        '''CREATE TABLE IF NOT EXISTS revocation_drains(
          task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,provider_id TEXT NOT NULL,
          receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,
          created_at REAL NOT NULL,PRIMARY KEY(task_id,attempt_id),
          FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
        '''CREATE INDEX IF NOT EXISTS task_ready_idx
           ON tasks(state,updated_at,task_id)''',
        '''CREATE INDEX IF NOT EXISTS outbox_due_idx
           ON outbox(delivered_at,next_attempt_at,outbox_id)''',
        '''CREATE INDEX IF NOT EXISTS writer_operations_state_idx
           ON writer_operations(task_id,state,updated_at,operation_id)''',
        )

    def _schema(self):
        application_id = self.db.execute(
            'PRAGMA application_id').fetchone()[0]
        user_version = self.db.execute('PRAGMA user_version').fetchone()[0]
        existing = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).fetchone()
        if existing is not None:
            if application_id != SUPERVISOR_APPLICATION_ID:
                raise ValueError('SUPERVISOR_DATABASE_ID_MISMATCH')
            if user_version in (1, 2):
                # Normal opens never migrate an existing ledger.
                raise ValueError('HOLD_MIGRATION_REQUIRED')
            if user_version != SUPERVISOR_SCHEMA_VERSION:
                raise ValueError('UNSUPPORTED_SUPERVISOR_SCHEMA')
            self._validate_schema()
            return
        unexpected = self.db.execute("""SELECT name FROM sqlite_master
          WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1""").fetchone()
        if unexpected is not None:
            raise ValueError('SUPERVISOR_DATABASE_ID_MISMATCH')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for statement in self._v3_schema_statements():
                self.db.execute(statement)
            self.db.execute('PRAGMA application_id=%d' %
                            SUPERVISOR_APPLICATION_ID)
            self.db.execute('PRAGMA user_version=%d' %
                            SUPERVISOR_SCHEMA_VERSION)
            self._validate_schema()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    @classmethod
    def _offline_migration_failpoint(cls, name):
        if cls.migration_fail_at == name:
            raise RuntimeError('injected migration interruption:' + name)

    @classmethod
    def offline_migrate_v2_to_v3(cls, path, clock=None):
        """Explicit fixture/offline migration; normal opens never migrate."""
        db = sqlite3.connect(path, timeout=10, isolation_level='IMMEDIATE')
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            app = db.execute('PRAGMA application_id').fetchone()[0]
            ver = db.execute('PRAGMA user_version').fetchone()[0]
            cols = tuple(r['name'] for r in db.execute(
                'PRAGMA table_info(tasks)'))
            if app != SUPERVISOR_APPLICATION_ID or ver != 2:
                raise ValueError('V2_LEDGER_REQUIRED')
            if cols != V2_TASK_COLUMNS:
                raise ValueError('V2_TASK_SCHEMA_MISMATCH')
            db.execute('BEGIN IMMEDIATE')
            additions = (
                "authority_state TEXT NOT NULL DEFAULT 'NONE'",
                'authority_valid_until REAL',
                "authority_run_id TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "authority_session_id TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "authority_gateway_id TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "resource_scope_json TEXT NOT NULL DEFAULT '[]'",
                "receiver_ack_json TEXT NOT NULL DEFAULT '{}'",
                "receiver_ack_sha256 TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "resource_scope_digest TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "coverage_digest TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "authority_caller_id TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "authority_lock_provider_id TEXT NOT NULL DEFAULT 'UNKNOWN'",
                'last_trusted_time REAL',
            )
            for definition in additions:
                db.execute('ALTER TABLE tasks ADD COLUMN ' + definition)
            cls._offline_migration_failpoint('after_task_alter')
            for statement in cls._v3_schema_statements()[4:]:
                db.execute(statement)
            cls._offline_migration_failpoint('after_fence_tables')
            db.execute("""UPDATE tasks SET authority_state='UNKNOWN',state='HOLD'
              WHERE state IN ('RECEIVED','STARTED','RUNNING','HANDOFF_PENDING')""")
            db.execute("""UPDATE tasks SET authority_state='NONE'
              WHERE authority_state!='UNKNOWN'""")
            cls._offline_migration_failpoint('after_authority_mapping')
            db.execute('PRAGMA user_version=%d' % SUPERVISOR_SCHEMA_VERSION)
            cls._offline_migration_failpoint('after_user_version')
            probe = cls.__new__(cls)
            probe.db = db
            probe._validate_schema()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _tx(self):
        return self.db

    def register(self, value, now=None):
        required = {'task_id', 'parent_task_id', 'stage', 'owner', 'entry',
                    'checkpoint_sha256', 'spec_sha256', 'next_action',
                    'dependencies', 'completion_conditions',
                    'progress_deadline', 'receipt_deadline',
                    'started_deadline', 'terminal_deadline',
                    'handoff_deadline'}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError('EXACT_TASK_REGISTRATION_REQUIRED')
        now = self.clock() if now is None else now
        if not finite(now):
            raise ValueError('FINITE_TIME_REQUIRED')
        for name in ('task_id', 'parent_task_id', 'stage',
                     'owner', 'entry', 'next_action'):
            if not isinstance(value[name], str) or not value[name].strip():
                raise ValueError('NONEMPTY_TASK_IDENTITY_REQUIRED')
        for name in ('checkpoint_sha256', 'spec_sha256'):
            if (not isinstance(value[name], str) or len(value[name]) != 64
                    or any(c not in '0123456789abcdef' for c in value[name])):
                raise ValueError('CANONICAL_DIGEST_REQUIRED')
        if (not isinstance(value['dependencies'], list)
                or not isinstance(value['completion_conditions'], list)):
            raise ValueError('TASK_ARRAYS_REQUIRED')
        deadlines = [value[n] for n in ('progress_deadline',
                     'receipt_deadline', 'started_deadline',
                     'terminal_deadline', 'handoff_deadline')]
        if any(not finite(v) or v < now for v in deadlines):
            raise ValueError('FUTURE_DEADLINES_REQUIRED')
        args = (value['task_id'], value['parent_task_id'], value['stage'],
                '%s:%s:%s' % (value['parent_task_id'], value['task_id'],
                                value['stage']), 'READY',
                value['owner'], value['entry'],
                UNKNOWN, UNKNOWN, UNKNOWN, value['checkpoint_sha256'],
                value['spec_sha256'], UNKNOWN, None, None,
                value['next_action'], canonical(value['dependencies']),
                canonical(value['completion_conditions']), None,
                None, None, None, now, 0, 0,
                value['progress_deadline'], value['receipt_deadline'],
                value['started_deadline'], value['terminal_deadline'],
                value['handoff_deadline'], UNKNOWN, UNKNOWN, UNKNOWN,
                UNKNOWN, 0, 0, now, now)
        # sqlite3's context manager does not itself begin a transaction.
        # Acquire the write lock before any state read so validation and
        # event/task/outbox mutation share one serialization point.
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''INSERT INTO tasks(
              task_id,parent_task_id,stage,writer_scope,state,owner,entry,
              run_id,session_id,attempt_id,checkpoint_sha256,spec_sha256,
              lease_id,fence,epoch,next_action,dependencies_json,completion_json,
              last_real_progress_at,received_at,started_at,handoff_requested_at,
              last_event_at,max_fence,max_epoch,progress_deadline,
              receipt_deadline,started_deadline,terminal_deadline,
              handoff_deadline,writer_stopped,effects_reconciled,
              receiver_accepted,old_fence_invalidated,recovery_level,
              recovery_generation,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            args)

    def _task(self, task_id):
        row = self.db.execute('SELECT * FROM tasks WHERE task_id=?',
                              (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return dict(row)

    def _dependencies_done(self, task):
        for dep in json.loads(task['dependencies_json']):
            row = self.db.execute('SELECT state FROM tasks WHERE task_id=?',
                                  (dep,)).fetchone()
            if row is None or row['state'] != 'SUCCESS':
                return False
        return True

    def ready(self, limit=100):
        rows = self.db.execute('''SELECT * FROM tasks WHERE state='READY'
                                  ORDER BY updated_at, task_id''').fetchall()
        eligible = [dict(row) for row in rows
                    if self._dependencies_done(dict(row))]
        return eligible[:limit]

    @staticmethod
    def _development_contract_shape(contract):
        required = {'task_id','spec_sha256','checkpoint_sha256',
                    'target_repository','target_base_sha','entry',
                    'developer','allowed_files','trusted_reviewers'}
        if not isinstance(contract, dict) or set(contract) != required:
            raise ValueError('EXACT_DEVELOPMENT_CONTRACT_REQUIRED')
        for name in ('task_id','entry'):
            if not isinstance(contract[name], str) or not contract[name]:
                raise ValueError('EXACT_DEVELOPMENT_CONTRACT_REQUIRED')
        for name in ('spec_sha256','checkpoint_sha256'):
            if (not isinstance(contract[name], str)
                    or re.fullmatch(r'[0-9a-f]{64}', contract[name]) is None):
                raise ValueError('EXACT_DEVELOPMENT_CONTRACT_REQUIRED')
        if (not isinstance(contract['target_repository'], str)
                or re.fullmatch(
                    r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',
                    contract['target_repository']) is None
                or not isinstance(contract['target_base_sha'], str)
                or re.fullmatch(
                    r'[0-9a-f]{40}', contract['target_base_sha']) is None):
            raise ValueError('EXACT_DEVELOPMENT_CONTRACT_REQUIRED')
        if (not isinstance(contract['allowed_files'], list)
                or not contract['allowed_files']
                or len(contract['allowed_files'])
                   != len(set(contract['allowed_files']))
                or any(not isinstance(path, str)
                       or re.fullmatch(r'[A-Za-z0-9_./-]+', path) is None
                       or any(part in ('','.','..') for part in path.split('/'))
                       for path in contract['allowed_files'])
                or not isinstance(contract['developer'], dict)
                or not isinstance(contract['trusted_reviewers'], list)
                or len(contract['trusted_reviewers']) != 2):
            raise ValueError('EXACT_DEVELOPMENT_CONTRACT_REQUIRED')
        return contract

    def register_development_contract(self, task_id, contract, now=None):
        contract = self._development_contract_shape(contract)
        now = self.clock() if now is None else now
        if not finite(now):
            raise ValueError('FINITE_TIME_REQUIRED')
        body = canonical(contract)
        evidence_ref = hashlib.sha256(body.encode('utf-8')).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if (task['state'] != 'READY' or task['authority_state'] != 'NONE'
                    or contract['task_id'] != task_id
                    or contract['spec_sha256'] != task['spec_sha256']
                    or contract['checkpoint_sha256']
                       != task['checkpoint_sha256']
                    or contract['entry'] != task['entry']):
                raise ValueError('CANONICAL_DEVELOPMENT_CONTRACT_MISMATCH')
            prior = self.db.execute('''SELECT * FROM events
              WHERE task_id=? AND attempt_id=? AND event_id=?''',
              (task_id, UNKNOWN, 'development-contract-v1')).fetchone()
            if prior is not None:
                if (prior['kind'] == 'DEVELOPMENT_CONTRACT'
                        and prior['payload_json'] == body
                        and prior['evidence_ref'] == evidence_ref):
                    return {'duplicate': True,
                            'contract_sha256': evidence_ref}
                raise ValueError('DEVELOPMENT_CONTRACT_CONFLICT')
            self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                (task_id, UNKNOWN, 'development-contract-v1',
                 'DEVELOPMENT_CONTRACT', now, 'PHASE_EXECUTION',
                 evidence_ref, body))
            return {'duplicate': False, 'contract_sha256': evidence_ref}

    def development_contract(self, task_id):
        row = self.db.execute('''SELECT * FROM events
          WHERE task_id=? AND attempt_id=? AND event_id=?''',
          (task_id, UNKNOWN, 'development-contract-v1')).fetchone()
        if row is None or row['kind'] != 'DEVELOPMENT_CONTRACT':
            raise ValueError('DEVELOPMENT_CONTRACT_REQUIRED')
        return json.loads(row['payload_json'])

    def bind_development_candidate(self, receipt, file_manifest, now=None):
        now = self.clock() if now is None else now
        if not finite(now):
            raise ValueError('FINITE_TIME_REQUIRED')
        required = {'schema','entry','execution_path','task_id','spec_sha256',
                    'checkpoint_sha256','target_repository','target_base_sha',
                    'code_commit','event','attempt_id','lease_id','fence',
                    'epoch','source_comment_id','status','native_identity',
                    'quota_attribution','authority_effect','required_gate'}
        if (not isinstance(receipt, dict)
                or not required.issubset(set(receipt))
                or receipt.get('status') != 'RECEIPT_VALIDATED_NOT_ADMITTED'
                or receipt.get('authority_effect') != 'NONE'
                or receipt.get('event') != 'CODE_READY'):
            raise ValueError('VALIDATED_CODE_READY_RECEIPT_REQUIRED')
        if (not isinstance(file_manifest, dict) or not file_manifest
                or any(not isinstance(path, str)
                       or not isinstance(value, str)
                       or re.fullmatch(r'[0-9a-f]{64}', value) is None
                       for path, value in file_manifest.items())):
            raise ValueError('EXACT_CANDIDATE_FILE_MANIFEST_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(receipt['task_id'])
            contract = self.development_contract(receipt['task_id'])
            expected_core = {
                'task_id': task['task_id'],
                'spec_sha256': task['spec_sha256'],
                'checkpoint_sha256': task['checkpoint_sha256'],
                'target_repository': contract['target_repository'],
                'target_base_sha': contract['target_base_sha'],
                'entry': task['entry'],
                'attempt_id': task['attempt_id'],
                'lease_id': task['lease_id'],
                'fence': task['fence'],
                'epoch': task['epoch'],
            }
            if (task['authority_state'] != 'VALID'
                    or task['state'] not in ACTIVE
                    or task['attempt_id'] == UNKNOWN
                    or any(receipt.get(k) != v
                           for k, v in expected_core.items())):
                raise ValueError('CANONICAL_CODE_READY_BINDING_MISMATCH')
            if set(file_manifest) != set(contract['allowed_files']):
                raise ValueError('EXACT_CANDIDATE_FILE_SET_REQUIRED')
            contract_body = canonical(contract)
            candidate = {
                'schema': 1,
                'task_id': task['task_id'],
                'attempt_id': task['attempt_id'],
                'lease_id': task['lease_id'],
                'fence': task['fence'],
                'epoch': task['epoch'],
                'spec_sha256': task['spec_sha256'],
                'checkpoint_sha256': task['checkpoint_sha256'],
                'target_repository': contract['target_repository'],
                'target_base_sha': contract['target_base_sha'],
                'entry': task['entry'],
                'code_commit': receipt['code_commit'],
                'source_comment_id': receipt['source_comment_id'],
                'contract_sha256': hashlib.sha256(
                    contract_body.encode('utf-8')).hexdigest(),
                'files': {path: file_manifest[path]
                          for path in sorted(file_manifest)},
            }
            body = canonical(candidate)
            candidate_sha = hashlib.sha256(
                body.encode('utf-8')).hexdigest()
            event_id = 'development-candidate:%s' % receipt['source_comment_id']
            prior = self.db.execute('''SELECT * FROM events
              WHERE task_id=? AND attempt_id=? AND event_id=?''',
              (task['task_id'], task['attempt_id'], event_id)).fetchone()
            if prior is not None:
                if (prior['kind'] == 'DEVELOPMENT_CANDIDATE'
                        and prior['payload_json'] == body
                        and prior['evidence_ref'] == candidate_sha):
                    return {'duplicate': True, 'candidate_event_id': event_id,
                            'candidate_sha256': candidate_sha,
                            'candidate': candidate}
                raise ValueError('DEVELOPMENT_CANDIDATE_CONFLICT')
            self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                (task['task_id'], task['attempt_id'], event_id,
                 'DEVELOPMENT_CANDIDATE', now, 'SOURCE_COMMIT',
                 candidate_sha, body))
            return {'duplicate': False, 'candidate_event_id': event_id,
                    'candidate_sha256': candidate_sha,
                    'candidate': candidate}

    def complete_development_candidate(self, task_id, candidate_event_id,
                                       bundle_sha256, review_record_ids,
                                       completion_event_id,
                                       next_action='DEPENDENCIES_RECHECK',
                                       now=None):
        now = self.clock() if now is None else now
        if (not finite(now)
                or not isinstance(bundle_sha256, str)
                or re.fullmatch(r'[0-9a-f]{64}', bundle_sha256) is None
                or not isinstance(review_record_ids, dict)
                or set(review_record_ids) != {'QA','SECURITY'}
                or any(not isinstance(value, str)
                       or re.fullmatch(r'[0-9a-f]{64}', value) is None
                       for value in review_record_ids.values())
                or review_record_ids['QA'] == review_record_ids['SECURITY']
                or not isinstance(completion_event_id, str)
                or not completion_event_id.strip()
                or not isinstance(next_action, str)
                or not next_action.strip()):
            raise ValueError('EXACT_DEVELOPMENT_COMPLETION_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            prior = self.db.execute('''SELECT * FROM events
              WHERE task_id=? AND attempt_id=? AND event_id=?''',
              (task_id, task['attempt_id'], completion_event_id)).fetchone()
            candidate_row = self.db.execute('''SELECT * FROM events
              WHERE task_id=? AND attempt_id=? AND event_id=?''',
              (task_id, task['attempt_id'], candidate_event_id)).fetchone()
            if candidate_row is None or candidate_row['kind'] != 'DEVELOPMENT_CANDIDATE':
                raise ValueError('CURRENT_DEVELOPMENT_CANDIDATE_REQUIRED')
            candidate = json.loads(candidate_row['payload_json'])
            payload = {
                'schema': 1,
                'state': 'SUCCESS',
                'task_id': task_id,
                'attempt_id': task['attempt_id'],
                'lease_id': task['lease_id'],
                'fence': task['fence'],
                'epoch': task['epoch'],
                'candidate_event_id': candidate_event_id,
                'candidate_sha256': candidate_row['evidence_ref'],
                'code_commit': candidate['code_commit'],
                'bundle_sha256': bundle_sha256,
                'review_record_ids': {
                    'QA': review_record_ids['QA'],
                    'SECURITY': review_record_ids['SECURITY'],
                },
                'writer_stopped': True,
                'effects_reconciled': True,
                'next_action': next_action,
            }
            body = canonical(payload)
            if prior is not None:
                if (prior['kind'] == 'DEVELOPMENT_COMPLETION'
                        and prior['payload_json'] == body
                        and prior['evidence_ref'] == bundle_sha256):
                    return {'duplicate': True, 'state': task['state'],
                            'completion': payload}
                raise ValueError('DEVELOPMENT_COMPLETION_EVENT_CONFLICT')
            if (task['state'] not in ACTIVE
                    or task['authority_state'] != 'VALID'
                    or candidate['attempt_id'] != task['attempt_id']
                    or candidate['lease_id'] != task['lease_id']
                    or candidate['fence'] != task['fence']
                    or candidate['epoch'] != task['epoch']):
                raise ValueError('CURRENT_DEVELOPMENT_ATTEMPT_REQUIRED')
            accepted_at = self.clock()
            if (not finite(accepted_at) or now < task['last_event_at']
                    or now > accepted_at + 300):
                raise ValueError('EVENT_TIME_RECONCILIATION_REQUIRED')
            self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                (task_id, task['attempt_id'], completion_event_id,
                 'DEVELOPMENT_COMPLETION', now, 'TEST_RUN',
                 bundle_sha256, body))
            self._enqueue(task_id, task['attempt_id'], completion_event_id,
                          payload, now)
            self.db.execute('''UPDATE tasks SET state='SUCCESS',
              writer_stopped='TRUE',effects_reconciled='TRUE',
              next_action=?,last_event_at=?,updated_at=? WHERE task_id=?
              AND attempt_id=? AND state IN
              ('RECEIVED','STARTED','RUNNING','HANDOFF_PENDING')''',
              (next_action, now, now, task_id, task['attempt_id']))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('DEVELOPMENT_COMPLETION_CAS_FAILED')
            return {'duplicate': False, 'state': 'SUCCESS',
                    'completion': payload}

    def claim(self, task_id, attempt_id, owner, entry, run_id, session_id,
              lease_id, fence, epoch, now=None, deadlines=None):
        now = self.clock() if now is None else now
        if (any(not isinstance(v, str) or not v for v in
                (attempt_id, owner, entry, run_id, session_id, lease_id))
                or type(fence) is not int or fence < 1
                or type(epoch) is not int or epoch < 1):
            raise ValueError('EXACT_EXECUTION_AUTHORITY_REQUIRED')
        # sqlite3's context manager does not itself begin a transaction.
        # Acquire the write lock before any state read so validation and
        # event/task/outbox mutation share one serialization point.
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if (task['state'] != 'READY' or task['authority_state'] != 'NONE'
                    or not self._dependencies_done(task)):
                raise ValueError('TASK_NOT_READY')
            if task['owner'] != owner or task['entry'] != entry:
                raise ValueError('ASSIGNED_RESPONSIBILITY_MISMATCH')
            deadline_names = ('progress_deadline','receipt_deadline',
                              'started_deadline','terminal_deadline',
                              'handoff_deadline')
            if deadlines is not None:
                if (not isinstance(deadlines, dict)
                        or set(deadlines) != set(deadline_names)
                        or any(not finite(deadlines[n]) or deadlines[n] <= now
                               for n in deadline_names)):
                    raise ValueError('FRESH_ATTEMPT_DEADLINES_REQUIRED')
            elif any(task[n] <= now for n in deadline_names):
                raise ValueError('FRESH_ATTEMPT_DEADLINES_REQUIRED')
            if fence <= task['max_fence'] or epoch <= task['max_epoch']:
                raise ValueError('MONOTONIC_FENCE_EPOCH_REQUIRED')
            values = deadlines or {n: task[n] for n in deadline_names}
            # Same task+stage is represented by one primary row, so a second
            # writer cannot be claimed concurrently.
            self.db.execute('''UPDATE tasks SET state='RECEIVED',attempt_id=?,
              owner=?,entry=?,run_id=?,session_id=?,lease_id=?,fence=?,epoch=?,
              progress_deadline=?,receipt_deadline=?,started_deadline=?,
              terminal_deadline=?,handoff_deadline=?,last_real_progress_at=NULL,
              writer_stopped=?,effects_reconciled=?,receiver_accepted=?,
              old_fence_invalidated=?,recovery_level=0,received_at=?,
              started_at=NULL,handoff_requested_at=NULL,last_event_at=?,
              max_fence=?,max_epoch=?,updated_at=?
              WHERE task_id=? AND state='READY' ''',
              (attempt_id, owner, entry, run_id, session_id, lease_id, fence,
               epoch, values['progress_deadline'], values['receipt_deadline'],
               values['started_deadline'], values['terminal_deadline'],
               values['handoff_deadline'], UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN,
               now, now, fence, epoch, now, task_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('SINGLE_WRITER_CAS_FAILED')

    def record(self, task_id, attempt_id, event_id, kind, observed_at,
               evidence_kind=UNKNOWN, evidence_ref=UNKNOWN, payload=None):
        if kind not in ('RECEIVED', 'STARTED', 'PROGRESS', 'HEARTBEAT',
                        'TERMINAL', 'HANDOFF_REQUESTED',
                        'HANDOFF_ACKNOWLEDGED'):
            raise ValueError('UNKNOWN_EVENT_KIND')
        if not finite(observed_at):
            raise ValueError('FINITE_TIME_REQUIRED')
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError('EVENT_ID_REQUIRED')
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise ValueError('EVENT_PAYLOAD_REQUIRED')
        if (len(event_id) > 200 or not isinstance(evidence_ref, str)
                or len(evidence_ref) > 1024
                or len(canonical(payload).encode('utf-8')) > 65536):
            raise ValueError('BOUNDED_EVENT_REQUIRED')
        # sqlite3's context manager does not itself begin a transaction.
        # Acquire the write lock before any state read so validation and
        # event/task/outbox mutation share one serialization point.
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if (task['authority_state'] == 'REVOKING'
                    and kind in ('STARTED','PROGRESS','TERMINAL',
                                 'HANDOFF_REQUESTED','HANDOFF_ACKNOWLEDGED')):
                raise ValueError('REVOKING_OLD_ATTEMPT_MUTATION_FORBIDDEN')
            if (task['authority_state'] in ('REVOKED', UNKNOWN)
                    and kind in ('STARTED','PROGRESS','TERMINAL',
                                 'HANDOFF_REQUESTED','HANDOFF_ACKNOWLEDGED')):
                raise ValueError('INACTIVE_AUTHORITY_MUTATION_FORBIDDEN')
            if (task['authority_state'] == 'VALID'
                    and kind == 'HANDOFF_ACKNOWLEDGED'):
                raise ValueError('FENCED_HANDOFF_REQUIRES_REVOCATION')
            # Exact replays are idempotent even when a newer event has since
            # advanced last_event_at.  Conflicting reuse still fails closed.
            encoded = canonical(payload)
            prior = self.db.execute('''SELECT kind,observed_at,evidence_kind,
              evidence_ref,payload_json FROM events
              WHERE task_id=? AND attempt_id=? AND event_id=?''',
              (task_id, attempt_id, event_id)).fetchone()
            if prior is not None:
                exact = (prior['kind'] == kind
                         and prior['observed_at'] == observed_at
                         and prior['evidence_kind'] == evidence_kind
                         and prior['evidence_ref'] == evidence_ref
                         and prior['payload_json'] == encoded)
                if not exact:
                    raise ValueError('EVENT_ID_REUSE_CONFLICT')
                return {'duplicate': True, 'state': task['state']}
            if task['attempt_id'] != attempt_id:
                raise ValueError('ATTEMPT_BINDING_MISMATCH')
            accepted_at = self.clock()
            if (not finite(accepted_at) or observed_at < task['last_event_at']
                    or observed_at > accepted_at + 300):
                raise ValueError('EVENT_TIME_RECONCILIATION_REQUIRED')
            self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                (task_id, attempt_id, event_id, kind, observed_at,
                 evidence_kind, evidence_ref, encoded))
            state = task['state']
            progress = task['last_real_progress_at']
            if kind == 'STARTED':
                if state != 'RECEIVED':
                    raise ValueError('START_REQUIRES_RECEIPT')
                state = 'STARTED'
                self.db.execute('UPDATE tasks SET started_at=? WHERE task_id=?',
                                (observed_at, task_id))
            elif kind == 'PROGRESS':
                if (state not in ('STARTED', 'RUNNING')
                        or evidence_kind not in REAL_PROGRESS
                        or not isinstance(evidence_ref, str)
                        or evidence_ref in ('', UNKNOWN)):
                    raise ValueError('REAL_PROGRESS_EVIDENCE_REQUIRED')
                state = 'RUNNING'; progress = observed_at
                self.db.execute('''UPDATE tasks SET recovery_level=0,
                  recovery_generation=recovery_generation+1 WHERE task_id=?''',
                  (task_id,))
                next_deadline = payload.get('next_progress_deadline')
                if next_deadline is not None:
                    if not finite(next_deadline) or next_deadline <= observed_at:
                        raise ValueError('FUTURE_PROGRESS_DEADLINE_REQUIRED')
                    self.db.execute('UPDATE tasks SET progress_deadline=? WHERE task_id=?',
                                    (next_deadline, task_id))
            elif kind == 'HEARTBEAT':
                pass  # intentionally does not refresh progress
            elif kind == 'HANDOFF_REQUESTED':
                if state not in ACTIVE:
                    raise ValueError('ACTIVE_ATTEMPT_REQUIRED')
                state = 'HANDOFF_PENDING'
                self.db.execute('UPDATE tasks SET handoff_requested_at=? WHERE task_id=?',
                                (observed_at, task_id))
            elif kind == 'HANDOFF_ACKNOWLEDGED':
                exact = {'receiver_accepted': True, 'old_writer_stopped': True,
                         'old_fence_invalidated': True,
                         'effects_reconciled': True,
                         'new_owner': payload.get('new_owner'),
                         'new_entry': payload.get('new_entry'),
                         'lease_id': task['lease_id'], 'fence': task['fence'],
                         'epoch': task['epoch']}
                if (state != 'HANDOFF_PENDING' or payload != exact
                        or not isinstance(payload.get('new_owner'), str)
                        or not payload['new_owner'].strip()
                        or not isinstance(payload.get('new_entry'), str)
                        or not payload['new_entry'].strip()
                        or evidence_kind != 'PHASE_EXECUTION'
                        or evidence_ref in ('', UNKNOWN)):
                    raise ValueError('EXACT_HANDOFF_PROOF_REQUIRED')
                state = 'READY'
                self.db.execute('''UPDATE tasks SET receiver_accepted='TRUE',
                  writer_stopped='TRUE',old_fence_invalidated='TRUE',
                  effects_reconciled='TRUE',owner=?,entry=?,attempt_id=?,
                  run_id=?,session_id=?,lease_id=?,fence=NULL,epoch=NULL
                  WHERE task_id=?''',
                  (payload['new_owner'], payload['new_entry'], UNKNOWN,
                   UNKNOWN, UNKNOWN, UNKNOWN, task_id))
            elif kind == 'TERMINAL':
                terminal = payload.get('state')
                required = {'state', 'artifact_sha256', 'writer_stopped',
                            'effects_reconciled', 'next_action',
                            'completion_evidence'}
                artifact = payload.get('artifact_sha256')
                artifact_ok = (artifact == UNKNOWN or
                    (isinstance(artifact, str) and len(artifact) == 64 and
                     all(c in '0123456789abcdef' for c in artifact)))
                completion = json.loads(task['completion_json'])
                if (set(payload) != required or terminal not in TERMINAL
                        or not artifact_ok
                        or not isinstance(payload['completion_evidence'], list)
                        or payload['writer_stopped'] not in
                           (True, False, UNKNOWN)
                        or payload['effects_reconciled'] not in
                           (True, False, UNKNOWN)):
                    raise ValueError('EXACT_TERMINAL_EVIDENCE_REQUIRED')
                if state not in ACTIVE or attempt_id == UNKNOWN:
                    raise ValueError('ACTIVE_ATTEMPT_TERMINAL_REQUIRED')
                if terminal == 'SUCCESS' and (
                        artifact == UNKNOWN
                        or payload['writer_stopped'] is not True
                        or payload['effects_reconciled'] is not True
                        or payload['completion_evidence'] != completion):
                    raise ValueError('SAFE_COMPLETION_EVIDENCE_REQUIRED')
                state = terminal
                self._enqueue(task_id, attempt_id, event_id, payload,
                              observed_at)
                self.db.execute('''UPDATE tasks SET writer_stopped=?,
                  effects_reconciled=?,next_action=? WHERE task_id=?''',
                  (str(payload['writer_stopped']).upper(),
                   str(payload['effects_reconciled']).upper(),
                   payload['next_action'], task_id))
            self.db.execute('''UPDATE tasks SET state=?,
              last_real_progress_at=?,last_event_at=?,updated_at=?
              WHERE task_id=?''',
              (state, progress, observed_at, observed_at, task_id))
            return {'duplicate': False, 'state': state}

    def _authority_ticket(self, task):
        return {
            'schema': 2,
            'task_id': task['task_id'],
            'writer_scope': task['writer_scope'],
            'attempt_id': task['attempt_id'],
            'lease_id': task['lease_id'],
            'fence': task['fence'],
            'epoch': task['epoch'],
            'valid_until': task['authority_valid_until'],
            'checkpoint_sha256': task['checkpoint_sha256'],
            'spec_sha256': task['spec_sha256'],
            'assigned_caller_id': task['authority_caller_id'],
            'lock_provider_id': task['authority_lock_provider_id'],
            'assigned_run_id': task['authority_run_id'],
            'assigned_session_id': task['authority_session_id'],
            'gateway_id': task['authority_gateway_id'],
            'resource_scope_digest': task['resource_scope_digest'],
            'resource_keys': json.loads(task['resource_scope_json']),
        }

    @staticmethod
    def _scope_digest(resource_keys):
        return hashlib.sha256(canonical(
            list(sorted(resource_keys))).encode('utf-8')).hexdigest()

    @staticmethod
    def _exact_resource_keys(resource_keys):
        if not isinstance(resource_keys, list) or not resource_keys:
            raise ValueError('RESOURCE_SCOPE_REQUIRED')
        normalized = []
        for value in resource_keys:
            if (not isinstance(value, str) or not value
                    or value != value.strip()
                    or any(ord(ch) < 33 or ord(ch) == 127 for ch in value)
                    or '\\x00' in value
                    or not re.fullmatch(r'[A-Za-z0-9._:/@+\\-]+', value)
                    or '//' in value
                    or any(part in ('', '.', '..') for part in value.split('/'))):
                raise ValueError('CANONICAL_RESOURCE_KEY_REQUIRED')
            normalized.append(value)
        if len(normalized) != len(set(normalized)):
            raise ValueError('DUPLICATE_RESOURCE_KEY')
        return tuple(sorted(normalized))

    def ticket_resource_keys(self, ticket):
        if not isinstance(ticket, dict):
            raise ValueError('EXACT_WRITER_TICKET_REQUIRED')
        return self._exact_resource_keys(ticket.get('resource_keys'))

    @staticmethod
    def _caller(caller):
        required = {'caller_id', 'run_id', 'session_id', 'gateway_id'}
        if (not isinstance(caller, dict) or set(caller) != required
                or any(not isinstance(caller[x], str) or not caller[x]
                       for x in required)):
            raise ValueError('TRUSTED_CALLER_CONTEXT_REQUIRED')
        return caller

    @staticmethod
    def _ticket_sha(ticket):
        return hashlib.sha256(canonical(ticket).encode('utf-8')).hexdigest()

    def claim_writer(self, task_id, attempt_id, owner, entry, caller,
                     lease_id, lock_provider_id, resource_keys, valid_until):
        now = self.clock()
        caller = self._caller(caller)
        keys = self._exact_resource_keys(resource_keys)
        if (not finite(now) or not finite(valid_until) or now >= valid_until
                or any(not isinstance(x, str) or not x for x in
                       (attempt_id, owner, entry, lease_id,
                        lock_provider_id))):
            raise ValueError('EXACT_EXECUTION_AUTHORITY_REQUIRED')
        scope_digest = self._scope_digest(keys)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if (task['authority_state'] != 'NONE' or task['state'] != 'READY'
                    or not self._dependencies_done(task)):
                raise ValueError('WRITER_AUTHORITY_NOT_CLAIMABLE')
            conflicts = self.db.execute(
                'SELECT resource_key FROM resource_claims WHERE resource_key IN (%s)'
                % ','.join('?' for _ in keys), keys).fetchall()
            if conflicts:
                raise ValueError('RESOURCE_SCOPE_CONFLICT')
            fence = task['max_fence'] + 1
            epoch = task['max_epoch'] + 1
            for key in keys:
                self.db.execute('''INSERT INTO resource_claims
                  VALUES (?,?,?,?,?,?,?)''',
                  (key, task_id, attempt_id, fence, epoch, 'VALID', now))
            self.db.execute('''UPDATE tasks SET state='RECEIVED',owner=?,entry=?,
              run_id=?,session_id=?,attempt_id=?,lease_id=?,fence=?,epoch=?,
              max_fence=?,max_epoch=?,authority_state='VALID',
              authority_valid_until=?,authority_caller_id=?,
              authority_lock_provider_id=?,authority_run_id=?,
              authority_session_id=?,authority_gateway_id=?,resource_scope_json=?,
              resource_scope_digest=?,coverage_digest=?,
              receiver_ack_json='{}',receiver_ack_sha256=?,
              last_trusted_time=?,received_at=?,last_event_at=?,updated_at=?
              WHERE task_id=? AND authority_state='NONE' ''',
              (owner, entry, caller['run_id'], caller['session_id'], attempt_id,
               lease_id, fence, epoch, fence, epoch, valid_until,
               caller['caller_id'], lock_provider_id, caller['run_id'],
               caller['session_id'], caller['gateway_id'],
               canonical(list(keys)), scope_digest,
               UNKNOWN, UNKNOWN, now, now, now, now, task_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('SINGLE_WRITER_CAS_FAILED')
            return self._authority_ticket(self._task(task_id))

    def _validate_writer_locked(self, ticket, caller, lock_provider_id):
        now = self.clock()
        caller = self._caller(caller)
        if not isinstance(ticket, dict):
            raise ValueError('EXACT_WRITER_TICKET_REQUIRED')
        task = self._task(ticket.get('task_id'))
        expected = self._authority_ticket(task)
        if canonical(ticket) != canonical(expected):
            raise ValueError('STALE_WRITER_TICKET')
        if task['authority_state'] != 'VALID':
            raise ValueError('WRITER_AUTHORITY_NOT_VALID')
        if task['state'] not in ACTIVE:
            raise ValueError('TASK_NOT_ACTIVE_FOR_WRITE')
        if lock_provider_id != task['authority_lock_provider_id']:
            raise ValueError('LOCK_PROVIDER_MISMATCH')
        if (caller['caller_id'] != task['authority_caller_id']
                or caller['run_id'] != task['authority_run_id']
                or caller['session_id'] != task['authority_session_id']
                or caller['gateway_id'] != task['authority_gateway_id']):
            raise ValueError('CALLER_CONTEXT_MISMATCH')
        if not finite(now):
            raise ValueError('FINITE_TIME_REQUIRED')
        if (task['last_trusted_time'] is not None
                and now < task['last_trusted_time']):
            raise ValueError('CLOCK_ROLLBACK_HOLD')
        if (task['authority_valid_until'] is None
                or not now < task['authority_valid_until']):
            raise ValueError('WRITER_TICKET_EXPIRED')
        self.db.execute('UPDATE tasks SET last_trusted_time=? WHERE task_id=?',
                        (now, task['task_id']))
        return task, now

    def _validate_inflight_result_locked(self, ticket, caller, operation_id,
                                         lock_provider_id):
        now = self.clock()
        caller = self._caller(caller)
        if not isinstance(ticket, dict):
            raise ValueError('EXACT_WRITER_TICKET_REQUIRED')
        task = self._task(ticket.get('task_id'))
        expected = self._authority_ticket(task)
        if canonical(ticket) != canonical(expected):
            raise ValueError('STALE_WRITER_TICKET')
        if task['authority_state'] not in ('VALID', 'REVOKING'):
            raise ValueError('INFLIGHT_RESULT_AUTHORITY_NOT_VALID')
        if lock_provider_id != task['authority_lock_provider_id']:
            raise ValueError('LOCK_PROVIDER_MISMATCH')
        if (caller['caller_id'] != task['authority_caller_id']
                or caller['run_id'] != task['authority_run_id']
                or caller['session_id'] != task['authority_session_id']
                or caller['gateway_id'] != task['authority_gateway_id']):
            raise ValueError('CALLER_CONTEXT_MISMATCH')
        row = self.db.execute(
            'SELECT * FROM writer_operations WHERE operation_id=?',
            (operation_id,)).fetchone()
        if (row is None or row['task_id'] != task['task_id']
                or row['attempt_id'] != task['attempt_id']
                or row['state'] not in ('DISPATCHING', 'UNKNOWN')):
            raise ValueError('OPERATION_NOT_INFLIGHT')
        return task, row, now

    def prepare_operation(self, ticket, caller, operation, lock_provider_id):
        required = {'operation_id', 'event_id', 'resource_key',
                    'operation_kind', 'expected_before', 'requested_after',
                    'request_sha256', 'operation_marker'}
        if not isinstance(operation, dict) or set(operation) != required:
            raise ValueError('EXACT_OPERATION_REQUIRED')
        for name in ('operation_id','event_id','resource_key','operation_kind',
                     'request_sha256','operation_marker'):
            if not isinstance(operation[name], str) or not operation[name]:
                raise ValueError('EXACT_OPERATION_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task, now = self._validate_writer_locked(
                ticket, caller, lock_provider_id)
            if operation['resource_key'] not in json.loads(
                    task['resource_scope_json']):
                raise ValueError('RESOURCE_OUTSIDE_WRITER_SCOPE')
            payload = canonical(operation)
            ticket_sha = self._ticket_sha(ticket)
            caller_sha = hashlib.sha256(
                canonical(self._caller(caller)).encode('utf-8')).hexdigest()
            existing = self.db.execute('''SELECT * FROM writer_operations
              WHERE operation_id=? OR (task_id=? AND attempt_id=? AND event_id=?)''',
              (operation['operation_id'], task['task_id'], task['attempt_id'],
               operation['event_id'])).fetchall()
            if existing:
                if (len(existing) == 1 and existing[0]['payload_json'] == payload
                        and existing[0]['ticket_sha256'] == ticket_sha
                        and existing[0]['caller_sha256'] == caller_sha):
                    return {'duplicate': True, 'state': existing[0]['state']}
                raise ValueError('OPERATION_IDENTITY_CONFLICT')
            self.db.execute('''INSERT INTO writer_operations
              VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
              (operation['operation_id'], task['task_id'], task['attempt_id'],
               operation['event_id'], operation['resource_key'], ticket_sha,
               caller_sha, payload, 'PREPARED', now, now))
            return {'duplicate': False, 'state': 'PREPARED'}

    def begin_dispatch(self, ticket, caller, operation_id, lock_provider_id):
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task, now = self._validate_writer_locked(
                ticket, caller, lock_provider_id)
            row = self.db.execute(
                'SELECT * FROM writer_operations WHERE operation_id=?',
                (operation_id,)).fetchone()
            if (row is None or row['task_id'] != task['task_id']
                    or row['attempt_id'] != task['attempt_id']):
                raise ValueError('OPERATION_IDENTITY_MISMATCH')
            self.db.execute("""UPDATE writer_operations SET state='DISPATCHING',
              updated_at=? WHERE operation_id=? AND state='PREPARED'""",
              (now, operation_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('OPERATION_NOT_PREPARED')
            return {'state': 'DISPATCHING'}

    @staticmethod
    def _validate_operation_receipt(row, outcome, receipt):
        if not isinstance(receipt, dict):
            raise ValueError('FINAL_RECEIPT_REQUIRED')
        base_required = {'schema','outcome','operation_id','resource_key',
                         'operation_marker','attribution'}
        operation = json.loads(row['payload_json'])
        attribution = receipt.get('attribution')
        git_operation = operation.get('operation_kind') == 'GIT_CAS'
        required = set(base_required)
        if git_operation:
            required.add('observed_revision')
        if set(receipt) != required or receipt.get('schema') != 1:
            raise ValueError('FINAL_RECEIPT_SCHEMA_REQUIRED')
        if (receipt['outcome'] != outcome
                or receipt['operation_id'] != row['operation_id']
                or receipt['resource_key'] != row['resource_key']
                or receipt['operation_marker'] != operation['operation_marker']):
            raise ValueError('FINAL_RECEIPT_BINDING_MISMATCH')
        if (not isinstance(attribution, dict)
                or set(attribution) != {'kind','before','after'}):
            raise ValueError('FINAL_RECEIPT_ATTRIBUTION_REQUIRED')
        if outcome == 'CONFIRMED':
            if (attribution['kind'] not in ('FAKE_TXN','GIT_CAS')
                    or attribution['before'] != operation['expected_before']
                    or attribution['after'] != operation['requested_after']):
                raise ValueError('CONFIRMED_ATTRIBUTION_REQUIRED')
            if git_operation and attribution['kind'] != 'GIT_CAS':
                raise ValueError('GIT_CONFIRMED_ATTRIBUTION_REQUIRED')
            if not git_operation and 'observed_revision' in receipt:
                raise ValueError('UNEXPECTED_OBSERVED_REVISION')
        elif outcome == 'NOT_APPLIED':
            if (attribution['kind'] != 'READBACK'
                    or attribution['before'] != operation['expected_before']
                    or attribution['after'] != operation['expected_before']):
                raise ValueError('NOT_APPLIED_ATTRIBUTION_REQUIRED')
            if not git_operation and 'observed_revision' in receipt:
                raise ValueError('UNEXPECTED_OBSERVED_REVISION')
        elif outcome == 'CONFLICT':
            if attribution['kind'] != 'READBACK':
                raise ValueError('CONFLICT_ATTRIBUTION_REQUIRED')
            if not git_operation and 'observed_revision' in receipt:
                raise ValueError('UNEXPECTED_OBSERVED_REVISION')
        if git_operation:
            observed = receipt.get('observed_revision')
            if (not isinstance(observed, str)
                    or re.fullmatch(
                        r'[0-9a-f]{40}(?:[0-9a-f]{24})?', observed)
                       is None):
                raise ValueError('GIT_OBSERVED_REVISION_REQUIRED')
        return receipt

    def _append_receipt_locked(self, row, outcome, receipt, now):
        self._validate_operation_receipt(row, outcome, receipt)
        body = canonical(receipt)
        sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
        existing = self.db.execute(
            'SELECT * FROM writer_receipts WHERE operation_id=?',
            (row['operation_id'],)).fetchone()
        if existing is not None:
            if existing['receipt_sha256'] == sha and existing['receipt_json'] == body:
                return {'duplicate': True}
            raise ValueError('FINAL_RECEIPT_CONFLICT')
        self.db.execute('INSERT INTO writer_receipts VALUES (?,?,?,?)',
                        (row['operation_id'], body, sha, now))
        return {'duplicate': False}

    def confirm_operation(self, ticket, caller, operation_id, receipt,
                          lock_provider_id):
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task, row, now = self._validate_inflight_result_locked(
                ticket, caller, operation_id, lock_provider_id)
            self._validate_operation_receipt(row, 'CONFIRMED', receipt)
            self.db.execute("""UPDATE writer_operations SET state='CONFIRMED',
              updated_at=? WHERE operation_id=? AND task_id=? AND attempt_id=?
              AND state='DISPATCHING'""",
              (now, operation_id, task['task_id'], task['attempt_id']))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('OPERATION_NOT_DISPATCHING')
            self._append_receipt_locked(row, 'CONFIRMED', receipt, now)
            return {'state': 'CONFIRMED'}

    def mark_operation_unknown(self, ticket, caller, operation_id, evidence,
                               lock_provider_id):
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task, row, now = self._validate_inflight_result_locked(
                ticket, caller, operation_id, lock_provider_id)
            self.db.execute("""UPDATE writer_operations SET state='UNKNOWN',
              updated_at=? WHERE operation_id=? AND task_id=? AND attempt_id=?
              AND state='DISPATCHING'""",
              (now, operation_id, task['task_id'], task['attempt_id']))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                current = self.db.execute(
                    'SELECT state FROM writer_operations WHERE operation_id=?',
                    (operation_id,)).fetchone()
                if current is None or current['state'] != 'UNKNOWN':
                    raise ValueError('OPERATION_NOT_DISPATCHING')
            evidence_id = hashlib.sha256(canonical({
                'operation_id': operation_id, 'evidence': evidence
            }).encode('utf-8')).hexdigest()
            self.db.execute('''INSERT OR IGNORE INTO writer_reconcile_evidence
              VALUES (?,?,?,?,?)''',
              (operation_id, evidence_id, 'UNKNOWN',
               canonical(evidence), now))
            return {'state': 'UNKNOWN'}

    def reconcile_operation(self, operation_id, context, outcome, evidence,
                            receipt=None):
        now = self.clock()
        required = {'role', 'evidence_id', 'caller_id'}
        if (not isinstance(context, dict) or set(context) != required
                or context['role'] != 'RECONCILER'
                or any(not isinstance(context[x], str) or not context[x]
                       for x in required)):
            raise ValueError('TRUSTED_RECONCILER_REQUIRED')
        if outcome not in ('UNKNOWN','CONFIRMED','NOT_APPLIED','CONFLICT'):
            raise ValueError('RECONCILE_OUTCOME_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            row = self.db.execute(
                'SELECT * FROM writer_operations WHERE operation_id=?',
                (operation_id,)).fetchone()
            if row is None or row['state'] not in (
                    'PREPARED','DISPATCHING','UNKNOWN'):
                raise ValueError('OPERATION_NOT_RECONCILABLE')
            if row['state'] == 'PREPARED' and outcome != 'NOT_APPLIED':
                raise ValueError('UNDISPATCHED_OPERATION_ONLY_NOT_APPLIED')
            body = canonical(evidence)
            existing = self.db.execute('''SELECT * FROM writer_reconcile_evidence
              WHERE operation_id=? AND evidence_id=?''',
              (operation_id, context['evidence_id'])).fetchone()
            if existing is not None:
                if existing['outcome'] == outcome and existing['evidence_json'] == body:
                    return {'duplicate': True, 'state': row['state']}
                raise ValueError('RECONCILE_EVIDENCE_CONFLICT')
            self.db.execute('''INSERT INTO writer_reconcile_evidence
              VALUES (?,?,?,?,?)''',
              (operation_id, context['evidence_id'], outcome, body, now))
            if outcome == 'UNKNOWN':
                if row['state'] == 'DISPATCHING':
                    self.db.execute("""UPDATE writer_operations SET state='UNKNOWN',
                      updated_at=? WHERE operation_id=?""", (now, operation_id))
                return {'duplicate': False, 'state': 'UNKNOWN'}
            if receipt is None:
                raise ValueError('FINAL_RECEIPT_REQUIRED')
            self._validate_operation_receipt(row, outcome, receipt)
            self.db.execute('''UPDATE writer_operations SET state=?,updated_at=?
              WHERE operation_id=? AND state IN
              ('PREPARED','DISPATCHING','UNKNOWN')''',
              (outcome, now, operation_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('RECONCILE_CAS_FAILED')
            self._append_receipt_locked(row, outcome, receipt, now)
            return {'duplicate': False, 'state': outcome}

    def unresolved_operations(self, task_id):
        return [dict(r) for r in self.db.execute('''SELECT * FROM
          writer_operations WHERE task_id=? AND state IN
          ('PREPARED','DISPATCHING','UNKNOWN') ORDER BY operation_id''',
          (task_id,))]

    @staticmethod
    def _controller(caller):
        if (not isinstance(caller, dict)
                or set(caller) != {'role','caller_id'}
                or caller['role'] not in
                   ('REVOCATION_CONTROLLER','SOURCE_INVENTORY_CONTROLLER')
                or not isinstance(caller['caller_id'], str)
                or not caller['caller_id']):
            raise ValueError('TRUSTED_REVOCATION_CONTROLLER_REQUIRED')
        return caller

    def begin_revocation(self, task_id, caller):
        self._controller(caller)
        now = self.clock()
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if task['authority_state'] == 'REVOKING':
                return self._exact_resource_keys(
                    json.loads(task['resource_scope_json']))
            if task['authority_state'] != 'VALID':
                raise ValueError('VALID_AUTHORITY_REQUIRED')
            keys = self._exact_resource_keys(
                json.loads(task['resource_scope_json']))
            self.db.execute("""UPDATE tasks SET authority_state='REVOKING',
              updated_at=? WHERE task_id=? AND authority_state='VALID'""",
              (now, task_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('REVOCATION_CAS_FAILED')
            self.db.execute("""UPDATE resource_claims SET state='REVOKING',
              updated_at=? WHERE task_id=?""", (now, task_id))
            return keys

    def recover_unknown_from_inventory(self, task_id, caller, inventory):
        caller = self._controller(caller)
        if caller['role'] != 'SOURCE_INVENTORY_CONTROLLER':
            raise ValueError('TRUSTED_SOURCE_INVENTORY_CONTROLLER_REQUIRED')
        required = {'schema','source','provider_id','evidence_id','task_id',
                    'old_attempt_id','resource_keys','resource_scope_digest'}
        if (not isinstance(inventory, dict) or set(inventory) != required
                or inventory.get('schema') != 1
                or inventory.get('source') != 'TRUSTED_SOURCE_INVENTORY'
                or inventory.get('task_id') != task_id):
            raise ValueError('TRUSTED_SOURCE_INVENTORY_REQUIRED')
        keys = self._exact_resource_keys(inventory['resource_keys'])
        scope_digest = self._scope_digest(keys)
        if inventory['resource_scope_digest'] != scope_digest:
            raise ValueError('SOURCE_INVENTORY_SCOPE_DIGEST_MISMATCH')
        now = self.clock()
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if task['authority_state'] != UNKNOWN or task['state'] != 'HOLD':
                raise ValueError('UNKNOWN_AUTHORITY_REQUIRED')
            if inventory['old_attempt_id'] != task['attempt_id']:
                raise ValueError('SOURCE_INVENTORY_ATTEMPT_MISMATCH')
            conflicts = self.db.execute(
                'SELECT resource_key FROM resource_claims WHERE resource_key IN (%s)'
                % ','.join('?' for _ in keys), keys).fetchall()
            if conflicts:
                raise ValueError('RESOURCE_SCOPE_CONFLICT')
            for key in keys:
                self.db.execute('''INSERT INTO resource_claims
                  VALUES (?,?,?,?,?,?,?)''',
                  (key, task_id, task['attempt_id'],
                   task['max_fence'], task['max_epoch'], 'REVOKING', now))
            evidence_body = canonical(inventory)
            self.db.execute('''INSERT INTO authority_recovery_evidence
              VALUES (?,?,?,?,?)''',
              (task_id, task['attempt_id'], inventory['evidence_id'],
               evidence_body, now))
            self.db.execute("""UPDATE tasks SET authority_state='REVOKING',
              authority_lock_provider_id=?,resource_scope_json=?,
              resource_scope_digest=?,updated_at=?
              WHERE task_id=? AND authority_state=?""",
              (inventory['provider_id'], canonical(list(keys)), scope_digest,
               now, task_id, UNKNOWN))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('UNKNOWN_RECOVERY_CAS_FAILED')
            return {'state': 'REVOKING',
                    'resource_scope_digest': scope_digest}

    def record_revocation_drain(self, task_id, provider_id, receipt):
        now = self.clock()
        required = {'schema','kind','capability','task_id','old_attempt_id',
                    'old_lease_id','old_fence','old_epoch','ticket_sha256',
                    'spec_sha256','provider_id','resource_scope_digest',
                    'outcome'}
        if (not isinstance(receipt, dict) or set(receipt) != required
                or receipt.get('schema') != 1
                or receipt.get('kind') != 'LOCAL_DRAIN'
                or receipt.get('capability') != 'LOCAL_ONLY'
                or receipt.get('outcome') != 'DRAINED'
                or receipt.get('task_id') != task_id
                or receipt.get('provider_id') != provider_id):
            raise ValueError('LOCAL_DRAIN_RECEIPT_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if task['authority_state'] != 'REVOKING':
                raise ValueError('REVOKING_AUTHORITY_REQUIRED')
            if provider_id != task['authority_lock_provider_id']:
                raise ValueError('LOCAL_DRAIN_PROVIDER_MISMATCH')
            expected = {
                'old_attempt_id': task['attempt_id'],
                'old_lease_id': task['lease_id'],
                'old_fence': task['fence'],
                'old_epoch': task['epoch'],
                'ticket_sha256': self._ticket_sha(
                    self._authority_ticket(task)),
                'spec_sha256': task['spec_sha256'],
                'resource_scope_digest': task['resource_scope_digest'],
            }
            if any(receipt[k] != v for k, v in expected.items()):
                raise ValueError('LOCAL_DRAIN_BINDING_MISMATCH')
            body = canonical(receipt)
            sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
            existing = self.db.execute('''SELECT * FROM revocation_drains
              WHERE task_id=? AND attempt_id=?''',
              (task_id, task['attempt_id'])).fetchone()
            if existing is not None:
                if existing['receipt_sha256'] == sha:
                    return {'duplicate': True}
                raise ValueError('LOCAL_DRAIN_RECEIPT_CONFLICT')
            self.db.execute('INSERT INTO revocation_drains VALUES (?,?,?,?,?,?)',
                (task_id, task['attempt_id'], provider_id, body, sha, now))
            return {'duplicate': False, 'receipt_sha256': sha}

    def record_resource_invalidation(self, task_id, receipt):
        now = self.clock()
        required = {'schema','kind','capability','adapter_id','provider_id',
                    'task_id','old_attempt_id','old_lease_id','old_fence',
                    'old_epoch','ticket_sha256','spec_sha256',
                    'resource_scope_digest','resource_key','outcome',
                    'evidence_id'}
        if (not isinstance(receipt, dict) or set(receipt) != required
                or receipt.get('schema') != 1
                or receipt.get('kind') != 'RESOURCE_INVALIDATION'
                or receipt.get('capability') != 'LOCAL_ONLY'
                or receipt.get('outcome') != 'INVALIDATED'
                or receipt.get('task_id') != task_id):
            raise ValueError('RESOURCE_INVALIDATION_RECEIPT_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if task['authority_state'] != 'REVOKING':
                raise ValueError('REVOKING_AUTHORITY_REQUIRED')
            keys = self._exact_resource_keys(
                json.loads(task['resource_scope_json']))
            drain = self.db.execute('''SELECT * FROM revocation_drains
              WHERE task_id=? AND attempt_id=?''',
              (task_id, task['attempt_id'])).fetchone()
            if (drain is None
                    or receipt.get('provider_id') != drain['provider_id']
                    or receipt.get('provider_id')
                       != task['authority_lock_provider_id']):
                raise ValueError('LOCAL_DRAIN_PROVIDER_REQUIRED')
            if receipt.get('adapter_id') != 'source-resource-adapter-v1':
                raise ValueError('SOURCE_ADAPTER_RECEIPT_REQUIRED')
            resource_key = receipt['resource_key']
            if resource_key not in keys:
                raise ValueError('RESOURCE_OUTSIDE_WRITER_SCOPE')
            expected_ticket = self._authority_ticket(task)
            expected = {
                'old_attempt_id': task['attempt_id'],
                'old_lease_id': task['lease_id'],
                'old_fence': task['fence'],
                'old_epoch': task['epoch'],
                'ticket_sha256': self._ticket_sha(expected_ticket),
                'spec_sha256': task['spec_sha256'],
                'resource_scope_digest': task['resource_scope_digest'],
            }
            if any(receipt[k] != v for k, v in expected.items()):
                raise ValueError('RESOURCE_INVALIDATION_BINDING_MISMATCH')
            body = canonical(receipt)
            sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
            existing = self.db.execute('''SELECT * FROM
              resource_invalidation_receipts WHERE task_id=? AND
              old_attempt_id=? AND resource_key=?''',
              (task_id, task['attempt_id'], resource_key)).fetchone()
            if existing is not None:
                if existing['receipt_sha256'] == sha and existing['receipt_json'] == body:
                    return {'duplicate': True}
                raise ValueError('RESOURCE_INVALIDATION_CONFLICT')
            self.db.execute('''INSERT INTO resource_invalidation_receipts
              VALUES (?,?,?,?,?,?)''',
              (task_id, task['attempt_id'], resource_key, body, sha, now))
            return {'duplicate': False, 'receipt_sha256': sha}

    def complete_revocation(self, task_id):
        now = self.clock()
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if task['authority_state'] != 'REVOKING':
                raise ValueError('REVOKING_AUTHORITY_REQUIRED')
            if self.unresolved_operations(task_id):
                raise ValueError('REVOCATION_NOT_COMPLETED')
            drain = self.db.execute('''SELECT * FROM revocation_drains
              WHERE task_id=? AND attempt_id=?''',
              (task_id, task['attempt_id'])).fetchone()
            if drain is None:
                raise ValueError('LOCAL_DRAIN_REQUIRED')
            keys = self._exact_resource_keys(
                json.loads(task['resource_scope_json']))
            rows = [dict(r) for r in self.db.execute('''SELECT * FROM
              resource_invalidation_receipts WHERE task_id=? AND
              old_attempt_id=? ORDER BY resource_key''',
              (task_id, task['attempt_id']))]
            if [r['resource_key'] for r in rows] != list(keys):
                raise ValueError('RESOURCE_COVERAGE_INCOMPLETE')
            coverage_object = {
                'task_id': task_id,
                'old_attempt_id': task['attempt_id'],
                'old_lease_id': task['lease_id'],
                'old_fence': task['fence'],
                'old_epoch': task['epoch'],
                'spec_sha256': task['spec_sha256'],
                'resource_scope_digest': task['resource_scope_digest'],
                'drain_provider_id': drain['provider_id'],
                'drain_receipt_sha256': drain['receipt_sha256'],
                'receipts': [
                    {'resource_key': r['resource_key'],
                     'receipt_sha256': r['receipt_sha256']} for r in rows],
            }
            coverage = hashlib.sha256(
                canonical(coverage_object).encode('utf-8')).hexdigest()
            self.db.execute("""UPDATE tasks SET authority_state='REVOKED',
              authority_valid_until=NULL,coverage_digest=?,updated_at=?
              WHERE task_id=? AND authority_state='REVOKING'""",
              (coverage, now, task_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('REVOCATION_CAS_FAILED')
            self.db.execute("""UPDATE resource_claims SET state='REVOKED',
              updated_at=? WHERE task_id=?""", (now, task_id))
            return {'state': 'REVOKED',
                    'resource_scope_digest': task['resource_scope_digest'],
                    'coverage_digest': coverage}

    def record_receiver_ack(self, task_id, ack):
        now = self.clock()
        required = {'schema','task_id','old_attempt_id','new_attempt_id',
                    'new_owner','new_entry','new_caller_id','new_run_id',
                    'new_session_id','new_lease_id','new_gateway_id',
                    'new_lock_provider_id',
                    'resource_scope_digest','coverage_digest','spec_sha256',
                    'checkpoint_sha256'}
        if (not isinstance(ack, dict) or set(ack) != required
                or ack.get('schema') != 1
                or any(not isinstance(ack[x], str) or not ack[x]
                       for x in required if x != 'schema')):
            raise ValueError('EXACT_RECEIVER_ACK_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            if task['authority_state'] != 'REVOKED':
                raise ValueError('REVOKED_AUTHORITY_REQUIRED')
            expected = {
                'task_id': task_id,
                'old_attempt_id': task['attempt_id'],
                'resource_scope_digest': task['resource_scope_digest'],
                'coverage_digest': task['coverage_digest'],
                'spec_sha256': task['spec_sha256'],
                'checkpoint_sha256': task['checkpoint_sha256']}
            if any(ack[k] != v for k, v in expected.items()):
                raise ValueError('RECEIVER_ACK_BINDING_MISMATCH')
            body = canonical(ack)
            sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
            if task['receiver_ack_sha256'] != UNKNOWN:
                if (task['receiver_ack_sha256'] == sha
                        and task['receiver_ack_json'] == body):
                    return {'duplicate': True,
                            'receiver_ack_sha256': sha}
                raise ValueError('RECEIVER_ACK_CONFLICT')
            self.db.execute('''UPDATE tasks SET receiver_ack_json=?,
              receiver_ack_sha256=?,updated_at=? WHERE task_id=? AND
              receiver_ack_sha256=?''',
              (body, sha, now, task_id, UNKNOWN))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('RECEIVER_ACK_CAS_FAILED')
            return {'duplicate': False, 'receiver_ack_sha256': sha}

    def takeover_claim(self, task_id, ack, valid_until):
        now = self.clock()
        if not finite(now) or not finite(valid_until) or now >= valid_until:
            raise ValueError('FRESH_AUTHORITY_DEADLINE_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self._task(task_id)
            body = canonical(ack)
            ack_sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
            if (task['authority_state'] != 'REVOKED'
                    or task['receiver_ack_sha256'] != ack_sha
                    or task['receiver_ack_json'] != body
                    or ack.get('resource_scope_digest')
                       != task['resource_scope_digest']
                    or ack.get('coverage_digest') != task['coverage_digest']):
                raise ValueError('TAKEOVER_PREREQUISITES_INCOMPLETE')
            keys = self._exact_resource_keys(
                json.loads(task['resource_scope_json']))
            claims = [dict(r) for r in self.db.execute('''SELECT * FROM
              resource_claims WHERE task_id=? ORDER BY resource_key''',
              (task_id,))]
            if ([r['resource_key'] for r in claims] != list(keys)
                    or any(r['state'] != 'REVOKED' for r in claims)):
                raise ValueError('RESOURCE_COVERAGE_INCOMPLETE')
            fence = task['max_fence'] + 1
            epoch = task['max_epoch'] + 1
            self.db.execute('''UPDATE tasks SET state='RECEIVED',owner=?,entry=?,
              run_id=?,session_id=?,attempt_id=?,lease_id=?,fence=?,epoch=?,
              max_fence=?,max_epoch=?,authority_state='VALID',
              authority_valid_until=?,authority_caller_id=?,
              authority_lock_provider_id=?,authority_run_id=?,
              authority_session_id=?,authority_gateway_id=?,
              receiver_ack_json='{}',
              receiver_ack_sha256=?,coverage_digest=?,last_trusted_time=?,
              received_at=?,last_event_at=?,updated_at=?
              WHERE task_id=? AND authority_state='REVOKED' ''',
              (ack['new_owner'], ack['new_entry'], ack['new_run_id'],
               ack['new_session_id'], ack['new_attempt_id'], ack['new_lease_id'],
               fence, epoch, fence, epoch, valid_until, ack['new_caller_id'],
               ack['new_lock_provider_id'], ack['new_run_id'],
               ack['new_session_id'], ack['new_gateway_id'], UNKNOWN, UNKNOWN,
               now, now, now, now, task_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('TAKEOVER_CAS_FAILED')
            self.db.execute('''UPDATE resource_claims SET attempt_id=?,
              fence=?,epoch=?,state='VALID',updated_at=? WHERE task_id=?''',
              (ack['new_attempt_id'], fence, epoch, now, task_id))
            return self._authority_ticket(self._task(task_id))

    def _enqueue(self, task_id, attempt_id, event_id, payload, now):
        seed = canonical({'task_id': task_id, 'attempt_id': attempt_id,
                          'event_id': event_id}).encode('utf-8')
        outbox_id = hashlib.sha256(seed).hexdigest()
        self.db.execute('''INSERT OR IGNORE INTO outbox
          (outbox_id,task_id,attempt_id,event_id,payload_json,next_attempt_at)
          VALUES (?,?,?,?,?,?)''',
          (outbox_id, task_id, attempt_id, event_id, canonical(payload), now))

    def scan(self, now=None):
        now = self.clock() if now is None else now
        if not finite(now):
            raise ValueError('FINITE_TIME_REQUIRED')
        actions = []
        # sqlite3's context manager does not itself begin a transaction.
        # Acquire the write lock before any state read so validation and
        # event/task/outbox mutation share one serialization point.
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            rows = [dict(r) for r in self.db.execute(
                "SELECT * FROM tasks WHERE state IN ('READY','RECEIVED','STARTED','RUNNING','HANDOFF_PENDING')")]
            for task in rows:
                if task['state'] == 'READY':
                    base = task['created_at']
                elif task['state'] == 'RECEIVED':
                    base = task['received_at']
                elif task['state'] in ('STARTED','RUNNING'):
                    base = task['last_real_progress_at']
                    if base is None:
                        base = task['started_at']
                else:
                    base = task['handoff_requested_at']
                if base is None:
                    base = task['created_at']
                age = now - base
                deadline_name = {
                    'READY': 'receipt_deadline',
                    'RECEIVED': 'started_deadline',
                    'STARTED': 'progress_deadline',
                    'RUNNING': 'progress_deadline',
                    'HANDOFF_PENDING': 'handoff_deadline',
                }[task['state']]
                # A live heartbeat or later phase deadline cannot hide a
                # separately registered terminal deadline.
                if (task['state'] in ACTIVE and
                        task['terminal_deadline'] < task[deadline_name]):
                    deadline_name = 'terminal_deadline'
                overdue = now >= task[deadline_name]
                action = None; level = 0
                if age >= 900:
                    action = 'VISIBLE_HOLD_OR_CONTROLLED_REASSIGN'; level = 3
                elif age >= 600:
                    action = 'RECONCILE_AND_RESUME_SAME_ATTEMPT'; level = 2
                elif age >= 300 or overdue:
                    action = 'CHECK_RECEIPT_AND_PROGRESS'; level = 1
                if action and level > task['recovery_level']:
                    event_id = 'supervision-G%d-L%d-%s-%s' % (
                        task['recovery_generation'], level,
                        task['task_id'], task['attempt_id'])
                    payload = {
                        'state': 'HOLD' if level == 3 else task['state'],
                        'action': action, 'deadline_kind': deadline_name,
                        'deadline': task[deadline_name],
                        'last_real_progress_at': task['last_real_progress_at'],
                        'checkpoint_sha256': task['checkpoint_sha256'],
                        'recovery_generation': task['recovery_generation'],
                        'takeover_allowed': False,
                        'requires_effect_reconciliation': True,
                    }
                    self.db.execute('''INSERT OR IGNORE INTO events
                      VALUES (?,?,?,?,?,?,?,?)''',
                      (task['task_id'], task['attempt_id'], event_id,
                       'SUPERVISION_ACTION', now, 'PHASE_EXECUTION',
                       action, canonical(payload)))
                    self._enqueue(task['task_id'], task['attempt_id'],
                                  event_id, payload, now)
                    if level == 3:
                        self.db.execute('''UPDATE tasks SET state='HOLD',
                          next_action=?,recovery_level=? WHERE task_id=?
                          AND state=? AND recovery_level<?''',
                          ('RECONCILE_BEFORE_CONTROLLED_REASSIGN', level,
                           task['task_id'], task['state'], level))
                    else:
                        self.db.execute('''UPDATE tasks SET recovery_level=?
                          WHERE task_id=? AND state=? AND recovery_level<?''',
                          (level, task['task_id'], task['state'], level))
                    if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                        continue
                    actions.append({'task_id': task['task_id'],
                        'attempt_id': task['attempt_id'], 'action': action,
                        'takeover_allowed': False,
                        'requires_effect_reconciliation': True,
                        'outbox_event_id': event_id})
        return sorted(actions, key=lambda x: x['task_id'])

    def supervisor_heartbeat(self, instance_id, process_ref, evidence_ref,
                             now=None):
        now = self.clock() if now is None else now
        accepted_at = self.clock()
        if (not finite(now) or not finite(accepted_at)
                or now > accepted_at + 5 or now < accepted_at - 300
                or not isinstance(instance_id, str)
                or not instance_id.strip()
                or not isinstance(process_ref, str)
                or not re.fullmatch(r'(pid:[1-9][0-9]*|unit:[A-Za-z0-9_.@-]+)',
                                    process_ref)
                or not isinstance(evidence_ref, str)
                or not re.fullmatch(r'[0-9a-f]{64}', evidence_ref)):
            raise ValueError('EXACT_SUPERVISOR_LIVENESS_REQUIRED')
        # sqlite3's context manager does not itself begin a transaction.
        # Acquire the write lock before any state read so validation and
        # event/task/outbox mutation share one serialization point.
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''INSERT OR REPLACE INTO supervisor_heartbeats
              (instance_id,observed_at,process_ref,evidence_ref,updated_at)
              VALUES (?,?,?,?,?)''',
              (instance_id, now, process_ref, evidence_ref, accepted_at))

    def supervisor_health(self, now=None, max_age=300):
        now = self.clock() if now is None else now
        if not finite(now) or not finite(max_age) or max_age <= 0:
            raise ValueError('FINITE_LIVENESS_WINDOW_REQUIRED')
        rows = [dict(r) for r in self.db.execute(
            'SELECT * FROM supervisor_heartbeats ORDER BY instance_id')]
        return [{'instance_id': row['instance_id'],
                 'process_ref': row['process_ref'],
                 'observed_at': row['observed_at'],
                 'evidence_ref': row['evidence_ref'],
                 'state': ('FRESH_RECORD_NOT_PROCESS_VERIFIED'
                           if 0 <= now - row['observed_at'] <= max_age
                           else 'SUPERVISOR_UNAVAILABLE')}
                for row in rows]

    def due_outbox(self, now=None, limit=100):
        now = self.clock() if now is None else now
        return [dict(r) for r in self.db.execute('''SELECT * FROM outbox
          WHERE delivered_at IS NULL AND dead_lettered_at IS NULL
            AND next_attempt_at<=?
          ORDER BY next_attempt_at,outbox_id LIMIT ?''', (now, limit))]

    def outbox_result(self, outbox_id, delivered, now=None, error=''):
        now = self.clock() if now is None else now
        # sqlite3's context manager does not itself begin a transaction.
        # Acquire the write lock before any state read so validation and
        # event/task/outbox mutation share one serialization point.
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            row = self.db.execute('SELECT * FROM outbox WHERE outbox_id=?',
                                  (outbox_id,)).fetchone()
            if row is None:
                raise KeyError(outbox_id)
            if row['delivered_at'] is not None:
                return {'duplicate': True}
            if delivered:
                self.db.execute('UPDATE outbox SET delivered_at=? WHERE outbox_id=?',
                                (now, outbox_id))
                return {'delivered': True}
            attempts = row['attempts'] + 1
            if attempts >= 5:
                next_at = now
                self.db.execute("UPDATE tasks SET state='HOLD',next_action=? WHERE task_id=?",
                                ('OWNER_VISIBLE_OUTBOX_FAILURE', row['task_id']))
                self.db.execute('''UPDATE outbox SET attempts=?,dead_lettered_at=?,
                  last_error=? WHERE outbox_id=?''',
                  (attempts, now, error[:256], outbox_id))
                return {'delivered': False, 'attempts': attempts,
                        'dead_lettered': True}
            else:
                next_at = now + min(300, 30 * (2 ** (attempts - 1)))
            self.db.execute('''UPDATE outbox SET attempts=?,next_attempt_at=?,
              last_error=? WHERE outbox_id=?''',
              (attempts, next_at, error[:256], outbox_id))
            return {'delivered': False, 'attempts': attempts,
                    'next_attempt_at': next_at}


