"""One mechanical supervision tick on an admitted canonical ledger.

Never creates or migrates a ledger, loads submitted code, starts a worker, or
grants authority.  The independently admitted provider consumes the outbox.
"""
from __future__ import print_function

import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import time

import task_supervisor as supervisor_module
from task_supervisor import (Supervisor, SUPERVISOR_APPLICATION_ID,
                             SUPERVISOR_SCHEMA_VERSION, canonical)


def private_parent(path):
    parent = os.path.dirname(path)
    if not os.path.isabs(path) or os.path.realpath(parent) != parent:
        raise ValueError('HOLD_CANONICAL_PATH_REQUIRED')
    info = os.lstat(parent)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('HOLD_PRIVATE_LEDGER_DIRECTORY_REQUIRED')


def _identity(info):
    return '%d:%d' % (info.st_dev, info.st_ino)


def _validate_open_file(path, fd, identity):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError('HOLD_PRIVATE_REGULAR_LEDGER_REQUIRED')
    if identity != _identity(info):
        raise ValueError('HOLD_LEDGER_IDENTITY_CHANGED')
    current = os.lstat(path)
    if (not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)):
        raise ValueError('HOLD_LEDGER_IDENTITY_CHANGED')
    return info


def open_admitted_ledger(path, identity):
    """Open once with NOFOLLOW and pin the exact inode for SQLite."""
    private_parent(path)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    db = None
    try:
        info = _validate_open_file(path, fd, identity)
        uri = 'file:/proc/self/fd/%d?mode=rw' % fd
        db = sqlite3.connect(uri, uri=True, timeout=5,
                             isolation_level='IMMEDIATE')
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        if (db.execute('PRAGMA application_id').fetchone()[0]
                != SUPERVISOR_APPLICATION_ID or
                db.execute('PRAGMA user_version').fetchone()[0]
                != SUPERVISOR_SCHEMA_VERSION):
            raise ValueError('HOLD_CANONICAL_SCHEMA_MAPPING_REQUIRED')
        probe = Supervisor.__new__(Supervisor)
        probe.db = db
        probe._validate_schema(allow_previous=False)
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('HOLD_LEDGER_INTEGRITY')
        if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':
            raise ValueError('HOLD_CANONICAL_WAL_REQUIRED')
        _validate_open_file(path, fd, identity)
        return fd, db, info
    except Exception:
        if db is not None:
            db.close()
        os.close(fd)
        raise


def admitted_ledger(path, identity):
    fd, db, info = open_admitted_ledger(path, identity)
    db.close()
    os.close(fd)
    return info


def acquire_lock(path):
    private_parent(path)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        current = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or (current.st_dev, current.st_ino)
                   != (info.st_dev, info.st_ino)):
            raise ValueError('HOLD_UNSAFE_SUPERVISOR_LOCK')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except Exception:
        os.close(fd)
        raise


def publish(path, value):
    private_parent(path)
    if os.path.lexists(path):
        info = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('HOLD_UNSAFE_SNAPSHOT')
    encoded = canonical(value).encode('utf-8')
    if len(encoded) > 1024 * 1024:
        raise ValueError('HOLD_SNAPSHOT_LIMIT')
    fd, temporary = tempfile.mkstemp(prefix='.supervisor-',
                                     dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(os.path.dirname(path),
                               os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def tick(path, identity, snapshot, now=None):
    if snapshot != path + '.supervisor.json':
        raise ValueError('HOLD_FIXED_SNAPSHOT_REQUIRED')
    lock = acquire_lock(path + '.supervisor.lock')
    ledger_fd = None
    supervisor = None
    try:
        ledger_fd, db, info = open_admitted_ledger(path, identity)
        # No path reopen: all mutations use the connection pinned to ledger_fd.
        supervisor = Supervisor.__new__(Supervisor)
        supervisor.path = path
        supervisor.clock = time.time
        supervisor.db = db
        _validate_open_file(path, ledger_fd, identity)
        now = time.time() if now is None else now
        actions = supervisor.scan(now=now)
        source_hashes = {}
        sources = {
            'task_supervisor.py': supervisor_module.__file__,
            'task_supervisor_runtime.py': __file__,
            'task_supervisor_runtime_entry.py': os.path.join(
                os.path.dirname(__file__), 'task_supervisor_runtime_entry.py'),
        }
        for name, source_path in sources.items():
            with open(source_path, 'rb') as source:
                source_hashes[name] = hashlib.sha256(source.read()).hexdigest()
        supervisor.supervisor_heartbeat(
            'mechanical-tick', 'pid:%d' % os.getpid(),
            source_hashes['task_supervisor_runtime.py'], now=now)
        # One explicit read transaction gives tasks and outbox one DB snapshot.
        supervisor.db.execute('BEGIN')
        try:
            rows = supervisor.db.execute('''SELECT task_id,parent_task_id,stage,
              state,owner,entry,run_id,session_id,attempt_id,checkpoint_sha256,
              spec_sha256,lease_id,fence,epoch,next_action,last_real_progress_at,
              progress_deadline,receipt_deadline,started_deadline,terminal_deadline,
              handoff_deadline,recovery_level FROM tasks ORDER BY task_id''')
            tasks = [dict(row) for row in rows]
            outbox = supervisor.db.execute('''SELECT outbox_id,task_id,attempt_id,
              event_id,attempts,next_attempt_at,delivered_at,dead_lettered_at
              FROM outbox WHERE delivered_at IS NULL ORDER BY outbox_id''')
            pending = [dict(row) for row in outbox]
            supervisor.db.commit()
        except Exception:
            supervisor.db.rollback()
            raise
        _validate_open_file(path, ledger_fd, identity)
        report = {'schema': 1, 'state': 'SCAN_COMPLETED_PROVIDER_NOT_ADMITTED',
                  'observed_at': now, 'runtime_sha256':
                  source_hashes['task_supervisor_runtime.py'],
                  'source_sha256': source_hashes,
                  'ledger_identity': _identity(info), 'tasks': tasks,
                  'actions': actions, 'pending_outbox': pending,
                  'provider': 'CAPABILITY_UNAVAILABLE',
                  'dispatch_performed': False, 'authority_effect': 'NONE',
                  'liveness': 'TICK_OBSERVED_NOT_CONTINUOUS_SERVICE_PROOF'}
        publish(snapshot, report)
        return report
    finally:
        if supervisor is not None:
            supervisor.close()
        if ledger_fd is not None:
            os.close(ledger_fd)
        os.close(lock)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--ledger-identity', required=True)
    parser.add_argument('--release-manifest', required=True)
    parser.add_argument('--release-manifest-sha256', required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit('HOLD_NONROOT_SUPERVISOR_REQUIRED')
    try:
        if args.verify_only:
            admitted_ledger(args.ledger, args.ledger_identity)
            result = {'state': 'SCHEMA_VERIFIED_NO_ACTIVATION',
                      'authority_effect': 'NONE'}
        else:
            result = tick(args.ledger, args.ledger_identity,
                          args.ledger + '.supervisor.json')
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    except Exception as error:
        code = str(error)
        if not code.startswith('HOLD_') or not code.replace('_', '').isalnum():
            code = 'HOLD_SUPERVISOR_TICK_FAILED'
        print(json.dumps({'state': code, 'authority_effect': 'NONE'}))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
