"""Durable 5/15/30 minute recovery actions over the canonical ledger.

This module never creates a second task queue.  Every action is durably
claimed before an external adapter is invoked so a crash becomes visible
``EFFECT_UNKNOWN`` instead of causing a duplicate writer.
"""
import json
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS mechanical_wake_events(
 task_id TEXT NOT NULL REFERENCES tasks(id), attempt TEXT NOT NULL,
 threshold_seconds INTEGER NOT NULL, triggered_at REAL NOT NULL,
 action TEXT NOT NULL, run_id TEXT, session_id TEXT, last_progress REAL,
 checkpoint TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
 error TEXT, next_check REAL NOT NULL,
 PRIMARY KEY(task_id,attempt,threshold_seconds));
"""


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


class MechanicalWakeController(object):
    THRESHOLDS = (300, 900, 1800)

    def __init__(self, db_path, clock, adapter):
        self.db_path, self.clock, self.adapter = db_path, clock, adapter
        db = self._db()
        try:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone():
                raise ValueError('canonical task registry missing')
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='supervised_runs'").fetchone():
                raise ValueError('supervised run registry missing')
            db.execute('BEGIN IMMEDIATE')
            db.execute(SCHEMA)
            db.execute('COMMIT')
        finally:
            db.close()

    def _db(self):
        db = sqlite3.connect(Path(self.db_path).resolve().as_uri() + '?mode=rw',
                             uri=True, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @staticmethod
    def _stale(now, row, seconds):
        reference = row['last_progress'] or row['started_at'] or row['accepted_at']
        if reference is None:
            reference = row['dispatched_at']
        return now - reference >= seconds

    def _due(self, now, row, fired):
        if row['terminal_receipt'] or row['status'] in ('COMPLETED', 'HOLD'):
            return None
        age = now - row['dispatched_at']
        if 300 not in fired and row['accepted_at'] is None and age >= 300:
            return 300
        if (900 not in fired
                and ((row['started_at'] is None and age >= 900)
                or (row['started_at'] is not None and self._stale(now, row, 900)))):
            if age < 1800 or not self._stale(now, row, 1800):
                return 900
        if (1800 not in fired
                and ((row['started_at'] is None and age >= 1800)
                or (row['started_at'] is not None and self._stale(now, row, 1800)))):
            return 1800
        return None

    def evaluate(self, task_id):
        """Execute at most one due action for the current immutable attempt."""
        now = float(self.clock())
        db = self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM supervised_runs WHERE task_id=?',
                             (task_id,)).fetchone()
            task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None or task is None:
                raise ValueError('unknown supervised task')
            attempt = row['run_id']
            fired = {value[0] for value in db.execute(
                'SELECT threshold_seconds FROM mechanical_wake_events '
                'WHERE task_id=? AND attempt=?', (task_id, attempt)).fetchall()}
            threshold = self._due(now, row, fired)
            if threshold is None:
                db.execute('COMMIT')
                return {'state': 'HEALTHY_OR_NOT_DUE', 'task_id': task_id,
                        'attempt': attempt}
            previous = db.execute("""SELECT status FROM mechanical_wake_events
              WHERE task_id=? AND attempt=? AND threshold_seconds=?""",
              (task_id, attempt, threshold)).fetchone()
            if previous is not None:
                db.execute('COMMIT')
                return {'state': 'IDEMPOTENT', 'task_id': task_id,
                        'attempt': attempt, 'threshold_seconds': threshold,
                        'status': previous['status']}
            action = {300: 'RECOVER_INTAKE', 900: 'RESUME_ORIGINAL',
                      1800: 'CONTROLLED_RECOVERY_OR_HOLD'}[threshold]
            checkpoint = row['checkpoint']
            db.execute("""INSERT INTO mechanical_wake_events
              (task_id,attempt,threshold_seconds,triggered_at,action,run_id,
               session_id,last_progress,checkpoint,status,result,error,next_check)
              VALUES(?,?,?,?,?,?,?,?,?,'ACTION_REQUESTED_EFFECT_UNKNOWN',NULL,NULL,?)""",
              (task_id, attempt, threshold, now, action, row['run_id'],
               row['session_id'], row['last_progress'], checkpoint,
               now + (600 if threshold < 1800 else 1800)))
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            db.close()
            raise
        db.close()

        context = {'task_id': task_id, 'attempt': attempt,
                   'run_id': row['run_id'], 'session_id': row['session_id'],
                   'fence': task['fence'], 'lease_owner': task['lease_owner'],
                   'lease_until': task['lease_until'],
                   'checkpoint': json.loads(checkpoint),
                   'last_progress': row['last_progress']}
        try:
            if threshold == 300:
                result = self.adapter.recover_intake(context)
            else:
                observed = self.adapter.inspect_writer(context)
                if (not isinstance(observed, dict)
                        or set(observed) != {'state', 'same_attempt', 'fence_stale'}):
                    raise ValueError('INVALID_WRITER_OBSERVATION')
                if threshold == 900:
                    if observed != {'state': 'RUNNING', 'same_attempt': True,
                                    'fence_stale': False}:
                        result = {'state': 'HOLD_ORIGINAL_WRITER_NOT_RESUMABLE'}
                    else:
                        result = self.adapter.resume_original(context)
                elif (observed['state'] == 'STOPPED'
                      and observed['same_attempt'] is True
                      and observed['fence_stale'] is True):
                    result = self.adapter.controlled_recovery(context)
                else:
                    result = {'state': 'HOLD_WRITER_OR_FENCE_NOT_PROVEN'}
            if (not isinstance(result, dict) or not isinstance(result.get('state'), str)):
                raise ValueError('INVALID_WAKE_RECEIPT')
            status, error = result['state'], None
        except Exception as exc:
            result, status, error = None, 'HOLD_ACTION_ERROR', type(exc).__name__

        db = self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute("""UPDATE mechanical_wake_events
              SET status=?,result=?,error=? WHERE task_id=? AND attempt=?
              AND threshold_seconds=? AND status='ACTION_REQUESTED_EFFECT_UNKNOWN'""",
              (status, _dump(result) if result is not None else None, error,
               task_id, attempt, threshold)).rowcount
            if changed != 1:
                raise RuntimeError('wake receipt CAS lost')
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()
        return {'state': status, 'task_id': task_id, 'attempt': attempt,
                'threshold_seconds': threshold, 'action': action,
                'result': result, 'error': error}

