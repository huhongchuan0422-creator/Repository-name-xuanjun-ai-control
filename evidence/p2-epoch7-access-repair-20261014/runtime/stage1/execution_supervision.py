"""Durable native-run supervision in supplemental canonical-ledger tables.

This is not a task registry.  It requires an existing canonical ``tasks`` table,
binds every run to its immutable spec/artifact/budget identity, and persists
transition delivery before a transport is called.
"""
import hashlib
import json
import os
import sqlite3
from pathlib import Path


LIVE_NATIVE = frozenset(('STARTING', 'RUNNING'))
TERMINAL_NATIVE = frozenset(('EXITED', 'FAILED', 'CANCELLED', 'NOT_FOUND'))

SCHEMA = """
CREATE TABLE IF NOT EXISTS supervised_runs(
 task_id TEXT PRIMARY KEY REFERENCES tasks(id), spec_hash TEXT NOT NULL,
 executor TEXT NOT NULL, run_id TEXT NOT NULL, session_id TEXT NOT NULL,
 workdir TEXT NOT NULL, artifact TEXT NOT NULL, dispatched_at REAL NOT NULL,
 start_deadline REAL NOT NULL, progress_deadline REAL NOT NULL,
 result_deadline REAL NOT NULL, native_state TEXT NOT NULL,
 accepted_at REAL, started_at REAL, last_progress REAL, terminal_receipt TEXT,
 effects TEXT NOT NULL, budget_key TEXT NOT NULL, budget_spent INTEGER NOT NULL,
 writer_fence INTEGER, writer_epoch INTEGER, start_receipt TEXT,
 resume_generation INTEGER NOT NULL DEFAULT 0, resume_base_fence INTEGER,
 status TEXT NOT NULL, checkpoint TEXT NOT NULL,
 checkpoint_version INTEGER NOT NULL DEFAULT 0, checkpoint_hash TEXT);
CREATE TABLE IF NOT EXISTS supervision_events(
 event_key TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
 sequence INTEGER NOT NULL, kind TEXT NOT NULL, created_at REAL NOT NULL,
 details TEXT NOT NULL, UNIQUE(task_id,sequence));
CREATE TABLE IF NOT EXISTS supervision_delivery(
 event_key TEXT NOT NULL REFERENCES supervision_events(event_key),
 destination TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL,
 next_attempt_at REAL NOT NULL, claim_owner TEXT, claim_until REAL,
 claim_epoch INTEGER NOT NULL DEFAULT 0, authority_fence INTEGER NOT NULL,
 authority_epoch INTEGER NOT NULL, receipt_id TEXT, last_error TEXT,
 send_attempts INTEGER NOT NULL DEFAULT 0, sent_at REAL,
 reconciliation_owner TEXT, reconciliation_until REAL,
 reconciliation_epoch INTEGER NOT NULL DEFAULT 0, claim_token TEXT,
 claim_attempt INTEGER,
 PRIMARY KEY(event_key,destination));
"""


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_dump(value).encode('utf-8')).hexdigest()


class ExecutionSupervisor(object):
    def __init__(self, db_path, clock, max_delivery_attempts=3, claim_ttl=30,
                 activation_store=None):
        if not os.path.exists(db_path):
            raise ValueError('canonical ledger missing')
        self.db_path, self.clock = db_path, clock
        self.activation_store = activation_store
        self.activation_binding = None
        if activation_store is not None:
            active = activation_store.read(require_active=True)
            if os.path.realpath(db_path) != active['db_path']:
                raise ValueError('supervision database is not active generation')
            self.activation_binding = {key: active[key] for key in
                                       ('ledger_uuid','generation','epoch','instance','db_path')}
        self.max_delivery_attempts, self.claim_ttl = max_delivery_attempts, claim_ttl
        db = self._db()
        try:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone():
                raise ValueError('canonical task registry missing')
            # Keep the whole supplemental-schema upgrade atomic.  executescript()
            # commits an outstanding transaction, so execute the fixed schema
            # statements individually before inspecting or backfilling columns.
            # A failed migration consequently leaves the parent ledger in its
            # exact pre-open state and no supervisor instance is returned.
            db.execute('BEGIN IMMEDIATE')
            for statement in SCHEMA.split(';'):
                if statement.strip():
                    db.execute(statement)
            run_columns = {row['name'] for row in
                           db.execute('PRAGMA table_info(supervised_runs)')}
            for name, definition in (
                    ('writer_epoch', 'INTEGER'), ('start_receipt', 'TEXT'),
                    ('resume_generation', 'INTEGER NOT NULL DEFAULT 0'),
                    ('resume_base_fence', 'INTEGER'),
                    ('checkpoint_version', 'INTEGER NOT NULL DEFAULT 0'),
                    ('checkpoint_hash', 'TEXT')):
                if name not in run_columns:
                    db.execute('ALTER TABLE supervised_runs ADD COLUMN %s %s' %
                               (name, definition))
            for row in db.execute("SELECT task_id,checkpoint FROM supervised_runs "
                                  "WHERE checkpoint_hash IS NULL").fetchall():
                db.execute('UPDATE supervised_runs SET checkpoint_hash=? WHERE task_id=?',
                           (_hash(json.loads(row['checkpoint'])), row['task_id']))
            columns = {row['name'] for row in
                       db.execute('PRAGMA table_info(supervision_delivery)')}
            for name, definition in (
                    ('claim_epoch', 'INTEGER NOT NULL DEFAULT 0'),
                    ('authority_fence', 'INTEGER NOT NULL DEFAULT 0'),
                    ('authority_epoch', 'INTEGER NOT NULL DEFAULT 0'),
                    ('send_attempts', 'INTEGER NOT NULL DEFAULT 0'),
                    ('sent_at', 'REAL'), ('reconciliation_owner', 'TEXT'),
                    ('reconciliation_until', 'REAL'),
                    ('reconciliation_epoch', 'INTEGER NOT NULL DEFAULT 0'),
                    # These two columns must exist before the populated-parent
                    # query below can reference either of them.  Keeping them
                    # adjacent also makes either one-column interrupted state
                    # restart-safe.
                    ('claim_token', 'TEXT'), ('claim_attempt', 'INTEGER')):
                if name not in columns:
                    db.execute('ALTER TABLE supervision_delivery ADD COLUMN %s %s' %
                               (name, definition))
            for row in db.execute("""SELECT * FROM supervision_delivery
              WHERE claim_epoch>0
                AND (claim_token IS NULL OR claim_attempt IS NULL)""").fetchall():
                claim_attempt = row['claim_attempt'] or row['claim_epoch']
                db.execute("""UPDATE supervision_delivery SET claim_token=?,
                  claim_attempt=? WHERE event_key=? AND destination=?
                  AND (claim_token IS NULL OR claim_attempt IS NULL)""",
                    (self._claim_token(row, row['claim_epoch'], claim_attempt),
                     claim_attempt, row['event_key'], row['destination']))
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def _db(self):
        uri = Path(self.db_path).resolve().as_uri() + '?mode=rw'
        db = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def _tx(self):
        self._assert_activation()
        db = self._db()
        db.execute('BEGIN IMMEDIATE')
        return db

    def _assert_activation(self):
        if self.activation_store is None:
            return
        active = self.activation_store.read(require_active=True)
        if any(active[key] != value for key,value in self.activation_binding.items()):
            raise RuntimeError('supervision activation is no longer live')

    def _commit(self, db):
        self._assert_activation()
        db.execute('COMMIT')

    def _authority(self):
        binding = self.activation_binding or {}
        return binding.get('generation', 0), binding.get('epoch', 0)

    @staticmethod
    def _claim_token(row, claim_epoch, claim_attempt):
        material = {'event_key': row['event_key'],
                    'destination': row['destination'],
                    'claim_epoch': claim_epoch,
                    'claim_attempt': claim_attempt,
                    'authority_fence': row['authority_fence'],
                    'authority_epoch': row['authority_epoch']}
        return _hash(material)

    @staticmethod
    def _claim_matches(row, claim):
        keys = ('event_key', 'destination', 'claim_owner', 'claim_epoch',
                'claim_token', 'claim_attempt', 'authority_fence',
                'authority_epoch')
        return isinstance(claim, dict) and all(row[key] == claim.get(key)
                                                for key in keys)

    def _event(self, db, task_id, kind, details,
               destinations=('GITHUB_PR17', 'OWNER'), canonical=False, dedupe_key=None):
        key = ('%s:terminal:%s' % (task_id, kind)) if canonical else None
        if dedupe_key is not None:
            if (not isinstance(dedupe_key, str) or len(dedupe_key) != 64
                    or any(c not in '0123456789abcdef' for c in dedupe_key)):
                raise ValueError('INVALID_INVENTORY_EVENT_KEY')
            key = '%s:inventory:%s' % (task_id, dedupe_key)
            previous = db.execute('SELECT kind,details FROM supervision_events WHERE event_key=?',
                                  (key,)).fetchone()
            if previous is not None:
                if previous['kind'] != kind or previous['details'] != _dump(details):
                    raise ValueError('INVENTORY_EVENT_KEY_COLLISION')
                return key
        if key is not None and db.execute(
                'SELECT 1 FROM supervision_events WHERE event_key=?',
                (key,)).fetchone():
            return key
        sequence = db.execute('SELECT COUNT(*) FROM supervision_events WHERE task_id=?',
                              (task_id,)).fetchone()[0] + 1
        key = key or '%s:%s:%d' % (task_id, kind, sequence)
        now = float(self.clock())
        db.execute('INSERT INTO supervision_events VALUES(?,?,?,?,?,?)',
                   (key, task_id, sequence, kind, now, _dump(details)))
        task_fence = db.execute('SELECT fence FROM tasks WHERE id=?',
                                (task_id,)).fetchone()[0]
        authority_epoch = (self.activation_binding or {}).get('epoch', 0)
        for destination in destinations:
            db.execute("""INSERT INTO supervision_delivery
              (event_key,destination,state,attempts,next_attempt_at,claim_owner,
               claim_until,claim_epoch,authority_fence,authority_epoch,
               receipt_id,last_error,send_attempts,sent_at,
               reconciliation_owner,reconciliation_until,reconciliation_epoch)
              VALUES(?,?,'PENDING',0,?,NULL,NULL,0,?,?,NULL,NULL,0,NULL,NULL,NULL,0)""",
                       (key, destination, now, task_fence, authority_epoch))
        return key

    def record_inventory_notice(self, db, intent, activation_binding, ledger_identity):
        # Notice-only mutation inside the caller-owned pinned canonical transaction.
        from task_supervisor_inventory_adapter import canonical_inventory_page, assert_inventory_lineage
        if not db.in_transaction or self.activation_store is None:
            raise ValueError('ADMITTED_CANONICAL_TRANSACTION_REQUIRED')
        self._assert_activation()
        if activation_binding != self.activation_binding:
            raise ValueError('INVENTORY_ACTIVATION_CHANGED')
        if not isinstance(intent, dict) or not isinstance(intent.get('binding'), dict):
            raise ValueError('INVENTORY_INTENT_REQUIRED')
        task_id = intent['binding'].get('task_id')
        page = canonical_inventory_page(db, self.clock(), task_id=task_id,
            activation_binding=activation_binding, ledger_identity=ledger_identity)
        if len(page['tasks']) != 1:
            raise ValueError('INVENTORY_TASK_CHANGED')
        current = page['tasks'][0]
        assert_inventory_lineage(intent['binding'], current['binding'], notice_only=True)
        if (intent.get('decision_key') != current['decision_key']
                or intent.get('attention') != current['attention']
                or current['decision'] != 'HOLD_AND_NOTIFY_REQUIRES_ADMISSION'):
            raise ValueError('INVENTORY_DECISION_CHANGED')
        key = self._event(db, task_id, 'INVENTORY_NOTICE',
            {'decision_key': current['decision_key'], 'binding': current['binding'],
             'attention': current['attention'], 'dispatch_performed': False},
            dedupe_key=current['decision_key'])
        self._assert_activation()
        return {'state': 'NOTICE_RECORDED_NOT_DELIVERED', 'event_key': key,
                'dispatch_performed': False, 'receiver_ack': 'NOT_PROVEN'}

    def dispatch(self, task_id, spec_hash, executor, run_id, session_id, workdir,
                 artifact, start_deadline, progress_deadline, result_deadline,
                 checkpoint, budget_key, budget_spent=0):
        now = float(self.clock())
        db = self._tx()
        try:
            if not db.execute('SELECT 1 FROM tasks WHERE id=?', (task_id,)).fetchone():
                raise ValueError('unknown canonical task')
            db.execute("""INSERT INTO supervised_runs
              (task_id,spec_hash,executor,run_id,session_id,workdir,artifact,
               dispatched_at,start_deadline,progress_deadline,result_deadline,
               native_state,accepted_at,started_at,last_progress,terminal_receipt,
               effects,budget_key,budget_spent,writer_fence,writer_epoch,
               start_receipt,resume_generation,resume_base_fence,status,checkpoint,
               checkpoint_version,checkpoint_hash)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,'DISPATCHED',NULL,NULL,NULL,NULL,
                     'NONE',?,?,NULL,NULL,NULL,0,NULL,'DISPATCHED',?,0,?)""",
                       (task_id, spec_hash, executor, run_id, session_id, workdir,
                        artifact, now, start_deadline, progress_deadline,
                        result_deadline, budget_key, budget_spent,
                        _dump(checkpoint), _hash(checkpoint)))
            self._event(db, task_id, 'DISPATCHED', {'run_id': run_id,
                        'artifact': artifact, 'started_claimed': False})
            self._commit(db)
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def accept_started(self, task_id, native_state, lease_owner, lease_until,
                       fence, checkpoint, start_receipt):
        """Atomically admit STARTED evidence against the canonical lease.

        The receipt is deliberately redundant: every security-relevant value
        is compared with both the supervised dispatch and canonical registry.
        This makes identical replay idempotent and conflicting replay closed.
        """
        now = float(self.clock())
        if (native_state not in LIVE_NATIVE or not lease_owner or lease_until <= now
                or type(fence) is not int or fence < 1
                or not isinstance(checkpoint, dict)
                or not isinstance(start_receipt, dict)):
            raise ValueError('native state plus live lease/fence required')
        required = {'task_id', 'spec_hash', 'artifact', 'executor', 'run_id',
                    'session_id', 'lease_owner', 'lease_until', 'fence', 'epoch',
                    'generation', 'resume_generation', 'stop_requested',
                    'checkpoint', 'checkpoint_version', 'checkpoint_hash',
                    'budget_key', 'budget_spent', 'native_state'}
        if set(start_receipt) != required:
            raise ValueError('start receipt shape mismatch')
        packed_receipt = _dump(start_receipt)
        db = self._tx()
        try:
            row = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (task_id,)).fetchone()
            if row is None:
                raise ValueError('dispatch is not awaiting start')
            if row['status'] not in ('DISPATCHED', 'STARTED'):
                raise ValueError('dispatch is not awaiting start')
            task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            spec = db.execute('SELECT hash FROM execution_specs WHERE task_id=?',
                              (task_id,)).fetchone()
            generation, epoch = self._authority()
            checkpoint_hash = _hash(checkpoint)
            if row['status'] == 'STARTED':
                checkpoint_version = row['checkpoint_version']
            else:
                checkpoint_version = row['checkpoint_version'] + int(
                    checkpoint_hash != row['checkpoint_hash'])
            expected = {
                'task_id': task_id, 'spec_hash': row['spec_hash'],
                'artifact': row['artifact'], 'executor': row['executor'],
                'run_id': row['run_id'], 'session_id': row['session_id'],
                'lease_owner': lease_owner, 'lease_until': lease_until,
                'fence': fence, 'generation': generation, 'epoch': epoch,
                'resume_generation': row['resume_generation'],
                'stop_requested': False, 'checkpoint': checkpoint,
                'checkpoint_version': checkpoint_version,
                'checkpoint_hash': checkpoint_hash,
                'budget_key': row['budget_key'], 'budget_spent': row['budget_spent'],
                'native_state': native_state}
            if (task is None or task['kind'] != 'CODEX_EXEC'
                    or task['state'] != 'RUNNING'
                    or task['lease_owner'] != lease_owner
                    or task['lease_until'] != lease_until
                    or task['lease_until'] is None or task['lease_until'] <= now
                    or task['fence'] != fence or spec is None
                    or spec['hash'] != row['spec_hash']
                    or json.loads(task['checkpoint']) != checkpoint
                    or start_receipt != expected):
                raise ValueError('start receipt does not match canonical dispatch')
            if row['status'] == 'STARTED':
                if row['start_receipt'] != packed_receipt:
                    raise ValueError('conflicting start receipt replay')
                # Idempotence is conditional on the authority still being live.
                # A stale receipt never turns a changed task/spec/lease into a
                # successful STARTED response.
                self._commit(db)
                return 'STARTED'
            changed = db.execute("""UPDATE supervised_runs SET native_state=?,
              accepted_at=?,started_at=?,last_progress=?,writer_fence=?,
              writer_epoch=?,start_receipt=?,status='STARTED',checkpoint=?,
              checkpoint_version=?,checkpoint_hash=?
              WHERE task_id=? AND status='DISPATCHED'""",
                       (native_state, now, now, now, fence, epoch, packed_receipt,
                        _dump(checkpoint), checkpoint_version, checkpoint_hash,
                        task_id)).rowcount
            if changed != 1:
                raise RuntimeError('start admission CAS lost')
            self._event(db, task_id, 'STARTED', {'run_id': row['run_id'],
                        'session_id': row['session_id'], 'executor': row['executor'],
                        'artifact': row['artifact'], 'spec_hash': row['spec_hash'],
                        'lease_owner': lease_owner, 'lease_until': lease_until,
                        'fence': fence, 'generation': generation, 'epoch': epoch,
                        'resume_generation': row['resume_generation'],
                        'native_state': native_state})
            self._commit(db)
            return 'STARTED'
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def observe(self, task_id, task_state, native_state, lease_owner, lease_until,
                last_progress, terminal_receipt=None, effects='NONE',
                quota_available=True):
        now = float(self.clock())
        if effects not in ('NONE', 'KNOWN', 'UNKNOWN'):
            raise ValueError('invalid side-effect state')
        db = self._tx()
        try:
            row = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (task_id,)).fetchone()
            if row is None:
                raise ValueError('unknown supervised run')
            if terminal_receipt:
                status, kind = 'COMPLETED', 'COMPLETED'
            elif not quota_available:
                status, kind = 'PAUSED_RESOURCE', 'RESOURCE_PAUSED'
            elif native_state in TERMINAL_NATIVE and task_state in ('PENDING', 'RUNNING'):
                status, kind = 'RESULT_MISSING', 'RESULT_MISSING'
            elif task_state == 'PENDING' and row['started_at'] is None and now > row['start_deadline']:
                status, kind = 'STALLED', 'START_TIMEOUT'
            elif task_state == 'RUNNING' and (not lease_owner or lease_until is None or lease_until <= now):
                status, kind = 'STALLED', 'LEASE_EXPIRED'
            elif task_state == 'RUNNING' and now > row['result_deadline']:
                status, kind = 'STALLED', 'RESULT_TIMEOUT'
            elif task_state == 'RUNNING' and (last_progress is None or now > row['progress_deadline']):
                status, kind = 'STALLED', 'PROGRESS_TIMEOUT'
            else:
                db.execute('UPDATE supervised_runs SET native_state=?,last_progress=?,terminal_receipt=?,effects=? WHERE task_id=?',
                           (native_state, last_progress, terminal_receipt, effects, task_id))
                self._commit(db)
                return row['status']
            db.execute('UPDATE supervised_runs SET status=?,native_state=?,last_progress=?,terminal_receipt=?,effects=? WHERE task_id=?',
                       (status, native_state, last_progress, terminal_receipt,
                        effects, task_id))
            self._event(db, task_id, kind, {'task_state': task_state,
                        'native_state': native_state, 'lease_owner': lease_owner,
                        'lease_until': lease_until, 'effects': effects}, canonical=True)
            self._commit(db)
            return status
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def reconcile(self, task_id, writer_stopped, lease_balanced,
                  recovered_receipt=None):
        db = self._tx()
        try:
            row = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (task_id,)).fetchone()
            if row is None:
                raise ValueError('unknown supervised run')
            if recovered_receipt:
                action, status = 'RECOVER_RESULT', 'COMPLETED'
            elif row['effects'] == 'UNKNOWN':
                action, status = 'HOLD_UNKNOWN_SIDE_EFFECT', 'HOLD'
            elif not writer_stopped or not lease_balanced:
                action, status = 'HOLD_WRITER_OR_LEASE', 'HOLD'
            else:
                task = db.execute('SELECT * FROM tasks WHERE id=?',
                                  (task_id,)).fetchone()
                if (task is None or task['state'] != 'PENDING'
                        or task['lease_owner'] is not None
                        or task['lease_until'] is not None
                        or row['writer_fence'] is None
                        or task['fence'] <= row['writer_fence']
                        or _hash(json.loads(task['checkpoint'])) != row['checkpoint_hash']):
                    action, status = 'HOLD_WRITER_OR_LEASE', 'HOLD'
                else:
                    action, status = 'RESUME_SAME_TASK_BUDGET', 'RESUMABLE'
            resume_fence = task['fence'] if status == 'RESUMABLE' else None
            db.execute('UPDATE supervised_runs SET status=?,terminal_receipt=COALESCE(?,terminal_receipt),resume_base_fence=? WHERE task_id=?',
                       (status, recovered_receipt, resume_fence, task_id))
            self._event(db, task_id, 'RECONCILED', {'action': action,
                        'writer_stopped': writer_stopped,
                        'lease_balanced': lease_balanced,
                        'budget_spent_unchanged': row['budget_spent']})
            self._commit(db)
            return action
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def advance_checkpoint(self, task_id, checkpoint, expected_version,
                           expected_hash, fence, epoch):
        """Advance the canonical checkpoint exactly once along one lineage.

        Both copies participate in one transaction.  A newer or divergent
        canonical checkpoint is never overwritten, and failure leaves both
        the canonical task and supervision row byte-for-byte unchanged.
        """
        if (not isinstance(checkpoint, dict) or type(expected_version) is not int
                or expected_version < 0 or not isinstance(expected_hash, str)
                or type(fence) is not int or type(epoch) is not int):
            raise ValueError('invalid checkpoint CAS')
        packed, digest = _dump(checkpoint), _hash(checkpoint)
        if digest == expected_hash:
            raise ValueError('checkpoint must advance')
        db = self._tx()
        try:
            row = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (task_id,)).fetchone()
            task = db.execute('SELECT * FROM tasks WHERE id=?',
                              (task_id,)).fetchone()
            unused_generation, active_epoch = self._authority()
            if (row is None or task is None or task['state'] != 'RUNNING'
                    or task['fence'] != fence or row['writer_fence'] != fence
                    or row['writer_epoch'] != epoch or epoch != active_epoch
                    or row['checkpoint_version'] != expected_version
                    or row['checkpoint_hash'] != expected_hash
                    or _hash(json.loads(task['checkpoint'])) != expected_hash):
                raise ValueError('HOLD_CHECKPOINT_LINEAGE_DIVERGED')
            canonical = db.execute("""UPDATE tasks SET checkpoint=?,updated=?
              WHERE id=? AND state='RUNNING' AND fence=? AND checkpoint=?""",
                (packed, float(self.clock()), task_id, fence,
                 task['checkpoint'])).rowcount
            supervised = db.execute("""UPDATE supervised_runs SET checkpoint=?,
              checkpoint_version=?,checkpoint_hash=? WHERE task_id=?
              AND checkpoint_version=? AND checkpoint_hash=?""",
                (packed, expected_version + 1, digest, task_id,
                 expected_version, expected_hash)).rowcount
            if canonical != 1 or supervised != 1:
                raise RuntimeError('checkpoint CAS lost')
            self._commit(db)
            return {'checkpoint': checkpoint, 'checkpoint_version': expected_version + 1,
                    'checkpoint_hash': digest}
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def resume_dispatch(self, task_id, run_id, session_id, start_deadline,
                        progress_deadline, result_deadline, lease_owner,
                        lease_until, fence, generation, epoch):
        """CAS a reconciled same-task run back to DISPATCHED.

        Immutable task/spec/artifact/executor/workdir/budget fields are retained.
        The canonical task must still be the exact lease-free generation that
        reconciliation approved. A later canonical claim is admitted only by
        ``accept_started`` under its strictly newer lease/fence/epoch.
        """
        now = float(self.clock())
        if (not all(isinstance(value, str) and value for value in
                    (run_id, session_id, lease_owner))
                or type(fence) is not int or type(generation) is not int
                or type(epoch) is not int
                or lease_until <= now
                or not now < start_deadline <= progress_deadline <= result_deadline):
            raise ValueError('invalid resumed dispatch')
        db = self._tx()
        try:
            row = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (task_id,)).fetchone()
            task = db.execute('SELECT * FROM tasks WHERE id=?',
                              (task_id,)).fetchone()
            spec = db.execute('SELECT hash FROM execution_specs WHERE task_id=?',
                              (task_id,)).fetchone()
            active_generation, active_epoch = self._authority()
            if (row is None or row['status'] != 'RESUMABLE'
                    or task is None or task['state'] != 'PENDING'
                    or task['lease_owner'] is not None
                    or task['lease_until'] is not None
                    or task['fence'] != row['resume_base_fence']
                    or row['writer_fence'] is None
                    or task['fence'] <= row['writer_fence']
                    or spec is None or spec['hash'] != row['spec_hash']
                    or _hash(json.loads(task['checkpoint'])) != row['checkpoint_hash']
                    or fence != task['fence'] + 1
                    or generation != active_generation or epoch != active_epoch):
                raise ValueError('same-task resume generation is no longer admissible')
            checkpoint = json.loads(row['checkpoint'])
            task_changed = db.execute("""UPDATE tasks SET state='RUNNING',
              lease_owner=?,lease_until=?,fence=?,checkpoint=?,updated=?
              WHERE id=? AND state='PENDING' AND lease_owner IS NULL
              AND lease_until IS NULL AND fence=?""",
                       (lease_owner, lease_until, fence, _dump(checkpoint), now,
                        task_id, task['fence'])).rowcount
            if task_changed != 1:
                raise RuntimeError('canonical resume CAS lost')
            changed = db.execute("""UPDATE supervised_runs SET run_id=?,session_id=?,
              dispatched_at=?,start_deadline=?,progress_deadline=?,result_deadline=?,
              native_state='DISPATCHED',accepted_at=NULL,started_at=NULL,
              last_progress=NULL,terminal_receipt=NULL,effects='NONE',
              writer_fence=NULL,writer_epoch=NULL,start_receipt=NULL,
              resume_generation=resume_generation+1,resume_base_fence=?,
              status='DISPATCHED'
              WHERE task_id=? AND status='RESUMABLE' AND resume_base_fence=?""",
                       (run_id, session_id, now, start_deadline, progress_deadline,
                        result_deadline, fence, task_id, task['fence'])).rowcount
            if changed != 1:
                raise RuntimeError('same-task resume CAS lost')
            self._event(db, task_id, 'RESUMED_DISPATCH', {
                        'run_id': run_id, 'session_id': session_id,
                        'resume_generation': row['resume_generation'] + 1,
                        'base_fence': task['fence'], 'fence': fence,
                        'generation': generation, 'epoch': epoch,
                        'lease_owner': lease_owner,
                        'budget_spent_unchanged': row['budget_spent']})
            admitted = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                                  (task_id,)).fetchone()
            current = db.execute('SELECT * FROM tasks WHERE id=?',
                                 (task_id,)).fetchone()
            current_spec = db.execute('SELECT hash FROM execution_specs WHERE task_id=?',
                                      (task_id,)).fetchone()
            if (admitted['resume_generation'] != row['resume_generation'] + 1
                    or admitted['run_id'] != run_id
                    or current['state'] != 'RUNNING'
                    or current['lease_owner'] != lease_owner
                    or current['lease_until'] != lease_until
                    or current['fence'] != fence
                    or current_spec['hash'] != row['spec_hash']):
                raise RuntimeError('admitted generation revalidation failed')
            self._commit(db)
            return {'task_id': task_id, 'run_id': run_id,
                    'session_id': session_id,
                    'resume_generation': row['resume_generation'] + 1,
                    'base_fence': task['fence'], 'fence': fence,
                    'generation': generation, 'epoch': epoch,
                    'lease_owner': lease_owner, 'lease_until': lease_until,
                    'checkpoint': checkpoint,
                    'checkpoint_version': row['checkpoint_version'],
                    'checkpoint_hash': row['checkpoint_hash'],
                    'spec_hash': row['spec_hash'], 'artifact': row['artifact'],
                    'budget_key': row['budget_key'],
                    'budget_spent': row['budget_spent']}
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def validate_launch(self, admission):
        """Revalidate a resume admission immediately before native launch."""
        required = {'task_id', 'run_id', 'session_id', 'resume_generation',
                    'fence', 'generation', 'epoch', 'lease_owner', 'lease_until',
                    'checkpoint_hash', 'spec_hash'}
        if not isinstance(admission, dict) or not required.issubset(admission):
            raise ValueError('invalid launch admission')
        db = self._tx()
        try:
            row = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (admission['task_id'],)).fetchone()
            task = db.execute('SELECT * FROM tasks WHERE id=?',
                              (admission['task_id'],)).fetchone()
            spec = db.execute('SELECT hash FROM execution_specs WHERE task_id=?',
                              (admission['task_id'],)).fetchone()
            generation, epoch = self._authority()
            if (row is None or task is None or spec is None
                    or row['status'] != 'DISPATCHED'
                    or row['run_id'] != admission['run_id']
                    or row['session_id'] != admission['session_id']
                    or row['resume_generation'] != admission['resume_generation']
                    or row['checkpoint_hash'] != admission['checkpoint_hash']
                    or row['spec_hash'] != admission['spec_hash']
                    or task['state'] != 'RUNNING'
                    or task['lease_owner'] != admission['lease_owner']
                    or task['lease_until'] != admission['lease_until']
                    or task['fence'] != admission['fence']
                    or _hash(json.loads(task['checkpoint'])) != admission['checkpoint_hash']
                    or spec['hash'] != admission['spec_hash']
                    or generation != admission['generation']
                    or epoch != admission['epoch']):
                raise ValueError('launch admission is no longer current')
            self._commit(db)
            return True
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def claim_delivery(self, claimant, destination):
        if not claimant:
            raise ValueError('delivery claimant required')
        now = float(self.clock())
        db = self._tx()
        try:
            row = db.execute("""SELECT * FROM supervision_delivery
              WHERE destination=? AND attempts<? AND next_attempt_at<=?
              AND (state IN ('PENDING','DELIVERY_FAILED')
                   OR (state='CLAIMED' AND claim_until<=?))
              ORDER BY next_attempt_at,event_key LIMIT 1""",
                             (destination, self.max_delivery_attempts, now, now)).fetchone()
            if row is None:
                self._commit(db)
                return None
            claim_epoch = row['claim_epoch'] + 1
            claim_attempt = (row['claim_attempt'] or 0) + 1
            claim_token = self._claim_token(row, claim_epoch, claim_attempt)
            changed = db.execute("""UPDATE supervision_delivery
              SET state='CLAIMED',claim_owner=?,claim_until=?,claim_epoch=?,
                  claim_token=?,claim_attempt=?
              WHERE event_key=? AND destination=? AND claim_epoch=?
              AND (state IN ('PENDING','DELIVERY_FAILED')
                   OR (state='CLAIMED' AND claim_until<=?))""",
                       (claimant, now + self.claim_ttl, claim_epoch,
                        claim_token, claim_attempt,
                        row['event_key'], destination, row['claim_epoch'], now)).rowcount
            if changed != 1:
                raise RuntimeError('delivery claim CAS lost')
            self._commit(db)
            return {'event_key': row['event_key'], 'destination': destination,
                    'claim_owner': claimant, 'claim_epoch': claim_epoch,
                    'claim_until': now + self.claim_ttl,
                    'claim_token': claim_token, 'claim_attempt': claim_attempt,
                    'authority_fence': row['authority_fence'],
                    'authority_epoch': row['authority_epoch'],
                    'delivery_identity': row['event_key'],
                    'reclaimed': row['state'] == 'CLAIMED'}
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def delivery_failed(self, claim, error):
        now = float(self.clock())
        if not isinstance(claim, dict):
            raise ValueError('fenced delivery claim required')
        db = self._tx()
        try:
            row = db.execute("""SELECT * FROM supervision_delivery
              WHERE event_key=? AND destination=? AND state='CLAIMED'
              AND claim_until>?""", (claim.get('event_key'),
              claim.get('destination'), now)).fetchone()
            if row is None or not self._claim_matches(row, claim):
                raise ValueError('delivery claim lost')
            attempts = row['attempts'] + 1
            db.execute("UPDATE supervision_delivery SET state='DELIVERY_FAILED',attempts=?,next_attempt_at=?,last_error=? WHERE event_key=? AND destination=?",
                       (attempts, now + min(300, 2 ** attempts), str(error)[:240],
                        claim['event_key'], claim['destination']))
            self._commit(db)
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def mark_delivery_sending(self, claim):
        """Persist the external-attempt boundary before invoking transport.

        Once this commits, absence of an ACK is uncertain and cannot be
        reclaimed as an ordinary retry.  Reconciliation must decide whether a
        stable delivery identity already produced the external effect.
        """
        now = float(self.clock())
        if not isinstance(claim, dict):
            raise ValueError('fenced delivery claim required')
        db = self._tx()
        try:
            changed = db.execute("""UPDATE supervision_delivery
              SET state='SENDING',send_attempts=send_attempts+1,sent_at=?
              WHERE event_key=? AND destination=? AND state='CLAIMED'
              AND claim_owner=? AND claim_epoch=? AND claim_token=?
              AND claim_attempt=? AND authority_fence=? AND authority_epoch=?
              AND claim_until>? AND send_attempts<?""",
                (now, claim['event_key'], claim['destination'], claim['claim_owner'],
                 claim['claim_epoch'], claim['claim_token'], claim['claim_attempt'],
                 claim['authority_fence'], claim['authority_epoch'], now,
                 self.max_delivery_attempts)).rowcount
            if changed != 1:
                raise ValueError('delivery send boundary lost')
            self._commit(db)
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    # Compatibility name for callers written before the explicit SENDING state.
    def mark_delivery_sent(self, claim):
        return self.mark_delivery_sending(claim)

    def mark_delivery_uncertain(self, claim, error='UNCERTAIN_AFTER_SEND'):
        """Fence an attempted send whose authoritative receipt is unavailable."""
        if not isinstance(claim, dict):
            raise ValueError('fenced delivery claim required')
        db = self._tx()
        try:
            row = db.execute("""SELECT * FROM supervision_delivery
              WHERE event_key=? AND destination=? AND state='SENDING'""",
                (claim.get('event_key'), claim.get('destination'))).fetchone()
            if row is None or not self._claim_matches(row, claim):
                raise ValueError('delivery claim lost')
            db.execute("""UPDATE supervision_delivery SET state='SENDING_UNCERTAIN',
              last_error=? WHERE event_key=? AND destination=? AND state='SENDING'""",
                (str(error)[:240], claim['event_key'], claim['destination']))
            self._commit(db)
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def reconcile_delivery(self, event_key, destination, claimant, lookup):
        """Reconcile an uncertain send without permitting blind resend.

        ``lookup`` returns a durable external receipt, ``NOT_SENT`` when the
        idempotency key is authoritatively absent, or ``UNKNOWN``. Unknown is
        terminal/fail-closed. A short fenced reconciliation claim prevents two
        reconcilers from authorizing a second external effect.
        """
        if not all(isinstance(v, str) and v for v in
                   (event_key, destination, claimant)) or not callable(lookup):
            raise ValueError('valid reconciliation request required')
        now = float(self.clock())
        db = self._tx()
        try:
            row = db.execute("""SELECT * FROM supervision_delivery
              WHERE event_key=? AND destination=?""",
                             (event_key, destination)).fetchone()
            if row is None:
                raise ValueError('unknown delivery')
            if row['state'] == 'ACKED':
                self._commit(db)
                return row['receipt_id']
            if (row['state'] not in ('SENDING', 'SENDING_UNCERTAIN')
                    or row['claim_until'] is None or row['claim_until'] > now or (
                    row['reconciliation_owner'] is not None
                    and row['reconciliation_until'] > now)):
                raise ValueError('delivery is not reconcilable')
            reconciliation_epoch = row['reconciliation_epoch'] + 1
            changed = db.execute("""UPDATE supervision_delivery
              SET reconciliation_owner=?,reconciliation_until=?,
                  reconciliation_epoch=?
              WHERE event_key=? AND destination=? AND state IN ('SENDING','SENDING_UNCERTAIN')
              AND reconciliation_epoch=?
              AND claim_until<=?
              AND (reconciliation_owner IS NULL OR reconciliation_until<=?)""",
                       (claimant, now + self.claim_ttl, reconciliation_epoch,
                        event_key, destination, row['reconciliation_epoch'],
                        now, now)).rowcount
            if changed != 1:
                raise RuntimeError('reconciliation CAS lost')
            db.execute("""UPDATE supervision_delivery SET state='SENDING_UNCERTAIN'
              WHERE event_key=? AND destination=? AND state='SENDING'""",
                       (event_key, destination))
            identity = row['event_key']
            self._commit(db)
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()
        result = lookup(destination, identity)
        db = self._tx()
        try:
            row = db.execute("""SELECT * FROM supervision_delivery
              WHERE event_key=? AND destination=? AND state='SENDING_UNCERTAIN'
              AND reconciliation_owner=? AND reconciliation_epoch=?
              AND reconciliation_until>?""",
                             (event_key, destination, claimant, reconciliation_epoch,
                              float(self.clock()))).fetchone()
            if row is None:
                raise ValueError('reconciliation claim lost')
            if isinstance(result, str) and result not in ('', 'NOT_SENT', 'UNKNOWN'):
                db.execute("""UPDATE supervision_delivery SET state='ACKED',
                  receipt_id=?,reconciliation_owner=NULL,
                  reconciliation_until=NULL WHERE event_key=? AND destination=?""",
                           (result, event_key, destination))
                self._commit(db)
                return result
            proof_keys = ('delivery_identity', 'claim_token', 'claim_attempt',
                          'claim_epoch', 'authority_fence', 'authority_epoch')
            positive_absence = (isinstance(result, dict)
                and result.get('status') == 'NOT_SENT'
                and isinstance(result.get('proof_id'), str)
                and bool(result['proof_id'])
                and all(result.get(key) == (row['event_key'] if key == 'delivery_identity'
                        else row[key]) for key in proof_keys))
            if positive_absence and row['send_attempts'] < self.max_delivery_attempts:
                attempts = row['attempts'] + 1
                db.execute("""UPDATE supervision_delivery
                  SET state='DELIVERY_FAILED',attempts=?,next_attempt_at=?,
                  reconciliation_owner=NULL,reconciliation_until=NULL,
                  last_error='PROVED_NOT_SENT'
                  WHERE event_key=? AND destination=?""",
                           (attempts, float(self.clock()) + min(300, 2 ** attempts),
                            event_key, destination))
                self._commit(db)
                return 'RETRY_AUTHORIZED'
            db.execute("""UPDATE supervision_delivery
              SET state='HELD',reconciliation_owner=NULL,
              reconciliation_until=NULL,last_error='AMBIGUOUS_EXTERNAL_RECEIPT'
              WHERE event_key=? AND destination=?""", (event_key, destination))
            self._commit(db)
            return 'HELD'
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def ack_delivery(self, claim, receipt_id):
        if not receipt_id:
            raise ValueError('authoritative receipt required')
        if not isinstance(claim, dict):
            raise ValueError('fenced delivery claim required')
        now = float(self.clock())
        db = self._tx()
        try:
            row = db.execute("""SELECT * FROM supervision_delivery
              WHERE event_key=? AND destination=?""",
                (claim.get('event_key'), claim.get('destination'))).fetchone()
            if row is None or not self._claim_matches(row, claim):
                raise ValueError('delivery claim lost')
            if row['state'] == 'ACKED':
                if row['receipt_id'] != str(receipt_id):
                    raise ValueError('conflicting delivery receipt')
                self._commit(db)
                return
            if row['state'] not in ('SENDING', 'SENDING_UNCERTAIN', 'HELD'):
                raise ValueError('delivery is not awaiting acknowledgement')
            db.execute("""UPDATE supervision_delivery SET state='ACKED',receipt_id=?
              WHERE event_key=? AND destination=?""",
                       (str(receipt_id), claim['event_key'], claim['destination']))
            self._commit(db)
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def snapshot(self, task_id):
        db = self._db()
        try:
            run = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (task_id,)).fetchone()
            return (dict(run) if run else None,
                    [dict(row) for row in db.execute(
                        'SELECT * FROM supervision_delivery ORDER BY event_key,destination')])
        finally:
            db.close()

    def supervise_from_adapters(self, task_id, canonical_task_adapter,
                                native_child_adapter, quota_available=True):
        """Reconcile one run from independently observed task/native state."""
        run, unused = self.snapshot(task_id)
        if run is None:
            raise ValueError('unknown supervised run')
        task = canonical_task_adapter(task_id)
        native = native_child_adapter(run['run_id'], run['session_id'])
        required_task = {'state', 'lease_owner', 'lease_until', 'last_progress'}
        required_native = {'state', 'terminal_receipt', 'effects'}
        if (not isinstance(task, dict) or set(task) != required_task
                or not isinstance(native, dict) or set(native) != required_native):
            raise ValueError('adapter evidence shape mismatch')
        return self.observe(task_id, task['state'], native['state'],
                            task['lease_owner'], task['lease_until'],
                            task['last_progress'], native['terminal_receipt'],
                            native['effects'], quota_available)

    def deliver_once(self, claimant, destination, transport):
        """Deliver one persisted event; only an external receipt marks ACKED."""
        key = self.claim_delivery(claimant, destination)
        if key is None:
            return None
        db = self._db()
        try:
            row = db.execute('SELECT kind,details FROM supervision_events WHERE event_key=?',
                             (key['event_key'],)).fetchone()
        finally:
            db.close()
        self.mark_delivery_sending(key)
        try:
            receipt = transport(destination, key['delivery_identity'], row['kind'],
                                json.loads(row['details']), key)
            if not receipt:
                raise RuntimeError('delivery receipt missing')
        except Exception as error:
            # The transport may have completed before failing to return its
            # receipt.  Preserve the uncertain boundary for explicit lookup;
            # a blind retry here could duplicate the external message.
            self.mark_delivery_uncertain(key, error)
            return 'DELIVERY_UNCERTAIN'
        self.ack_delivery(key, str(receipt))
        return str(receipt)
