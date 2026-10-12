"""One mechanical supervision tick on an admitted canonical ledger.

Never creates or migrates a ledger, loads submitted code, starts a worker, or
grants authority.  The independently admitted provider consumes the outbox.
"""
from __future__ import print_function

import argparse
import fcntl
import hashlib
import json
import math
import re
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



# Contract 6134558596: bounded adapter, no canonical writer grant.
CANONICAL_TASK_COLUMNS = ('id', 'kind', 'state', 'depends', 'lease_owner', 'lease_until',
                'fence', 'checkpoint', 'updated')
CANONICAL_READ_COLUMNS = ('id', 'kind', 'state', 'depends', 'lease_owner', 'lease_until', 'fence')
CANONICAL_RUN_COLUMNS = ('task_id', 'executor', 'run_id', 'session_id', 'spec_hash',
               'checkpoint_hash', 'writer_fence', 'writer_epoch', 'status',
               'last_progress', 'start_deadline', 'progress_deadline',
               'result_deadline', 'started_at', 'effects', 'native_state')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _columns(db, table):
    # Table names are fixed constants, never supplied by task content.
    return tuple(row[1] for row in db.execute('PRAGMA table_info(' + table + ')'))


def canonical_inventory_page(db, now, after_id=None, limit=100,
                             activation_binding=None, ledger_identity=None, task_id=None):
    if not db.in_transaction:
        raise ValueError('CANONICAL_READ_TRANSACTION_REQUIRED')
    if not _finite(now) or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('INVALID_SCAN_BOUND')
    if after_id is not None and (not isinstance(after_id, str) or not after_id):
        raise ValueError('INVALID_CURSOR')
    if _columns(db, 'tasks') != CANONICAL_TASK_COLUMNS:
        raise ValueError('EXISTING_EXECUTION_LEDGER_SCHEMA_REQUIRED')
    run_columns = _columns(db, 'supervised_runs')
    if run_columns and not set(CANONICAL_RUN_COLUMNS).issubset(run_columns):
        raise ValueError('SUPERVISION_SCHEMA_UNRECOGNIZED')
    activation = {key: 'UNKNOWN' for key in
                  ('ledger_uuid', 'generation', 'epoch', 'instance', 'db_path')}
    if activation_binding is not None:
        if not isinstance(activation_binding, dict) or set(activation_binding) != set(activation):
            raise ValueError('ACTIVATION_BINDING_SHAPE')
        for key in ('ledger_uuid', 'instance'):
            value = activation_binding[key]
            if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value) is None:
                raise ValueError('ACTIVATION_IDENTITY')
        for key in ('generation', 'epoch'):
            if type(activation_binding[key]) is not int or activation_binding[key] < 1:
                raise ValueError('ACTIVATION_GENERATION')
        path = activation_binding['db_path']
        if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
            raise ValueError('ACTIVATION_PATH')
        activation = dict(activation_binding)
    if ledger_identity is not None:
        parts = ledger_identity.split(':') if isinstance(ledger_identity, str) else []
        if len(parts) != 2 or any(not x.isdigit() for x in parts):
            raise ValueError('LEDGER_FILE_IDENTITY')
    if task_id is not None and (after_id is not None or not isinstance(task_id, str) or not task_id):
        raise ValueError('EXACT_TASK_SELECTOR')
    query = 'SELECT ' + ','.join(CANONICAL_READ_COLUMNS) + ' FROM tasks'
    args = []
    if task_id is not None:
        query += ' WHERE id = ?'
        args.append(task_id)
    elif after_id is not None:
        query += ' WHERE id > ?'
        args.append(after_id)
    query += ' ORDER BY id LIMIT ?'
    args.append(limit + 1)
    source_rows = db.execute(query, args).fetchall()
    specs = _columns(db, 'execution_specs')
    if specs and not {'task_id', 'hash'}.issubset(specs):
        raise ValueError('SPEC_SCHEMA_UNRECOGNIZED')
    deliveries = _columns(db, 'supervision_delivery')
    events = _columns(db, 'supervision_events')
    delivery_fields = ('event_key', 'destination', 'state', 'attempts', 'next_attempt_at',
                       'authority_fence', 'authority_epoch')
    if deliveries and (not set(delivery_fields).issubset(deliveries)
                       or not {'event_key', 'task_id'}.issubset(events)):
        raise ValueError('DELIVERY_SCHEMA_UNRECOGNIZED')
    rows = []
    for values in source_rows[:limit]:
        task = dict(zip(CANONICAL_READ_COLUMNS, values))
        flags = []
        try:
            if not isinstance(task['depends'], str) or len(task['depends']) > 8192:
                raise ValueError('dependency data limit')
            dependencies = json.loads(task['depends'])
            if (not isinstance(dependencies, list) or len(dependencies) > 32
                    or any(not isinstance(x, str) or not x for x in dependencies)
                    or len(set(dependencies)) != len(dependencies)):
                raise ValueError('bad dependencies')
        except (TypeError, ValueError):
            dependencies = None
            flags.append('DEPENDENCIES_UNVERIFIED')
        if dependencies:
            states = dict(db.execute('SELECT id,state FROM tasks WHERE id IN (' +
                          ','.join('?' for unused in dependencies) + ')', dependencies))
            if any(states.get(x) != 'DONE' for x in dependencies):
                flags.append('DEPENDENCIES_NOT_DONE')
        run = None
        if run_columns:
            value = db.execute('SELECT ' + ','.join(CANONICAL_RUN_COLUMNS) +
                               ' FROM supervised_runs WHERE task_id=?',
                               (task['id'],)).fetchone()
            if value is not None:
                run = dict(zip(CANONICAL_RUN_COLUMNS, value))
        if task['state'] == 'RUNNING':
            if not task['lease_owner'] or not _finite(task['lease_until']):
                flags.append('LEASE_UNVERIFIED')
            elif task['lease_until'] <= now:
                flags.append('LEASE_EXPIRED')
        if run is None:
            flags.append('SUPERVISION_RECORD_MISSING')
        else:
            if run['effects'] == 'UNKNOWN':
                flags.append('UNKNOWN_EFFECT_NO_REPLAY')
            if (run['native_state'] in ('EXITED', 'FAILED', 'CANCELLED', 'NOT_FOUND')
                    and task['state'] in ('PENDING', 'RUNNING') and run['status'] != 'COMPLETED'):
                flags.append('TERMINAL_WITHOUT_RESULT')
            if run['status'] == 'COMPLETED':
                flags.append('TERMINAL_CONTINUATION_UNVERIFIED')
            if task['state'] == 'RUNNING':
                for field, label in (('progress_deadline', 'PROGRESS'),
                                     ('result_deadline', 'RESULT')):
                    if not _finite(run[field]):
                        flags.append(label + '_DEADLINE_UNVERIFIED')
                    elif run[field] < now:
                        flags.append(label + '_DEADLINE_EXCEEDED')
            if task['state'] == 'PENDING' and run['started_at'] is None:
                if not _finite(run['start_deadline']):
                    flags.append('START_DEADLINE_UNVERIFIED')
                elif run['start_deadline'] < now:
                    flags.append('START_DEADLINE_EXCEEDED')
        if task['state'] in ('DONE', 'FAILED') and 'TERMINAL_CONTINUATION_UNVERIFIED' not in flags:
            flags.append('TERMINAL_CONTINUATION_UNVERIFIED')
        row = {key: task[key] for key in ('id', 'kind', 'state', 'lease_owner',
                                          'lease_until', 'fence')}
        spec_hash = None
        if specs:
            spec = db.execute('SELECT hash FROM execution_specs WHERE task_id=?', (task['id'],)).fetchone()
            spec_hash = spec[0] if spec else None
        delivery_rows = []
        if deliveries:
            found = db.execute('SELECT ' + ','.join('d.' + x for x in delivery_fields) +
                ' FROM supervision_delivery d JOIN supervision_events e USING(event_key)'
                ' WHERE e.task_id=? ORDER BY d.event_key,d.destination LIMIT 101',
                (task['id'],)).fetchall()
            delivery_rows = [dict(zip(delivery_fields, x)) for x in found[:100]]
            if len(found) > 100:
                flags.append('DELIVERY_INVENTORY_TRUNCATED')
            if any(x['authority_fence'] != task['fence'] for x in delivery_rows):
                flags.append('STALE_DELIVERY_RECONCILE_ONLY')
        checkpoint_hash = 'UNKNOWN'
        native = {}
        raw_checkpoint = db.execute('SELECT CASE WHEN length(checkpoint)<=65536'
            ' THEN checkpoint ELSE NULL END FROM tasks WHERE id=?', (task['id'],)).fetchone()[0]
        try:
            value = json.loads(raw_checkpoint)
            if not isinstance(value, dict):
                raise ValueError('checkpoint object required')
            native = value.get('native_execution', {})
            if not isinstance(native, dict):
                native = {}
            checkpoint_hash = hashlib.sha256(json.dumps(value, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        except (TypeError, ValueError):
            flags.append('CHECKPOINT_UNVERIFIED')
        if run and run['checkpoint_hash'] and run['checkpoint_hash'] != checkpoint_hash:
            flags.append('CHECKPOINT_LINEAGE_MISMATCH')
        if not _finite(task['lease_until']) and task['lease_until'] is not None:
            task['lease_until'] = 'UNKNOWN'
            row['lease_until'] = 'UNKNOWN'
        attempt = native.get('idempotency_key')
        if not isinstance(attempt, str) or len(attempt) != 64 or any(c not in '0123456789abcdef' for c in attempt):
            attempt = 'UNKNOWN'
        lease_id = 'UNKNOWN'
        request = native.get('request')
        if isinstance(request, dict) and isinstance(request.get('lease'), str):
            try:
                if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', request['lease']):
                    lease_id = request['lease']
            except ValueError:
                pass
        binding = {'task_id': task['id'], 'fence': task['fence'],
                   'lease_owner': task['lease_owner'], 'lease_until': task['lease_until'],
                   'spec_sha256': spec_hash or ((run['spec_hash'] or 'UNKNOWN') if run else 'UNKNOWN'),
                   'checkpoint_sha256': checkpoint_hash,
                   'run_id': (run['run_id'] or 'UNKNOWN') if run else 'UNKNOWN',
                   'session_id': (run['session_id'] or 'UNKNOWN') if run else 'UNKNOWN',
                   'epoch': run['writer_epoch'] if run and run['writer_epoch'] is not None else 'UNKNOWN',
                   'entry': (run['executor'] or 'UNKNOWN') if run else 'UNKNOWN',
                   'entry_authenticated': False,
                   'attempt_id': attempt,
                   'lease_id': lease_id, 'task_state': task['state'],
                   'supervision_status': run['status'] if run else 'UNKNOWN',
                   'effects': run['effects'] if run else 'UNKNOWN',
                   'activation': activation, 'ledger_identity': ledger_identity or 'UNKNOWN'}
        if activation_binding is None or ledger_identity is None:
            flags.append('ACTIVATION_IDENTITY_UNVERIFIED')
        elif run and run['writer_epoch'] != activation['epoch']:
            flags.append('ACTIVATION_EPOCH_MISMATCH')
        if run and spec_hash and run['spec_hash'] != spec_hash:
            flags.append('SPEC_LINEAGE_MISMATCH')
        decision = 'INSPECT_ONLY'
        if flags:
            decision = 'HOLD_AND_NOTIFY_REQUIRES_ADMISSION'
        elif task['state'] == 'PENDING' and run and run['status'] == 'RESUMABLE':
            decision = 'RESUME_REQUIRES_ATOMIC_CANONICAL_CHECK'
        key = hashlib.sha256(json.dumps({'binding': binding, 'attention': flags,
            'decision': decision}, sort_keys=True, separators=(',', ':'),
            allow_nan=False).encode('utf-8')).hexdigest()
        row.update({'supervision': run, 'attention': flags, 'binding': binding,
                    'deliveries': delivery_rows, 'decision': decision,
                    'decision_key': key, 'provider': 'CAPABILITY_UNAVAILABLE',
                    'next_action': 'UNKNOWN', 'receiver_ack': 'UNKNOWN',
                    'execution_authority': 'NOT_GRANTED'})
        # Deliberately omit raw checkpoint/prompt content and task.updated: a
        # heartbeat or dashboard update is not evidence of real progress.
        rows.append(row)
    return {'schema': 1, 'observed_at': now, 'tasks': rows,
            'next_cursor': rows[-1]['id'] if len(source_rows) > limit else None,
            'complete': len(source_rows) <= limit, 'dispatch_performed': False,
            'canonical_mutation': False, 'authority': 'READ_ONLY_OBSERVATION'}



def receiver_continuation_policy(entry, route):
    """Data-only selection under policy6134670620; no provider is invoked.

    A model-backed native entry is never callable through this adapter. Actual
    current native chats continue themselves; mechanical work needs its own
    reviewed executor. Unknown routes deny, with no fallback.
    """
    if entry not in ('WORK', 'CHATGPT', 'DOTS'):
        return {'state': 'CAPABILITY_UNAVAILABLE', 'reason': 'UNKNOWN_ENTRY',
                'dispatch': False, 'fallback': None}
    mechanical = ('READ_ONLY_COLLECTION', 'HASH_SYNTAX_TEST', 'PACKAGE',
                  'RECEIPT_COLLECTION', 'DEADLINE_SCAN')
    if route in mechanical:
        return {'state': 'MECHANICAL_REVIEW_REQUIRED', 'reason': 'NO_INFERENCE_ROUTE',
                'dispatch': False, 'fallback': None}
    return {'state': 'CAPABILITY_UNAVAILABLE', 'reason': 'DELEGATED_MODEL_ROUTE_DENIED',
            'dispatch': False, 'fallback': None}


def assert_inventory_lineage(expected, current, notice_only=False):
    """Comparison primitive for an EXISTING admitted mutation transaction.

    This function neither opens a transaction nor grants permission. Integrator
    must re-read current inside its transaction and apply existing operation
    authorization/effect/stop guards; never call an external callback from here.
    """
    required = ('task_id', 'fence', 'spec_sha256', 'checkpoint_sha256',
                'run_id', 'session_id', 'epoch', 'attempt_id', 'ledger_identity',
                'entry', 'lease_id')
    if type(notice_only) is not bool:
        raise ValueError('INVALID_NOTICE_MODE')
    if notice_only:
        required = ('task_id', 'fence', 'checkpoint_sha256', 'ledger_identity')
    for value in (expected, current):
        if not isinstance(value, dict):
            raise ValueError('CANONICAL_LINEAGE_REQUIRED')
        if any(value.get(key) in (None, '', 'UNKNOWN') for key in required):
            raise ValueError('CAPABILITY_UNAVAILABLE_MISSING_LINEAGE')
        activation = value.get('activation')
        if not isinstance(activation, dict) or any(activation.get(key) in (None, '', 'UNKNOWN')
                for key in ('ledger_uuid', 'generation', 'epoch', 'instance', 'db_path')):
            raise ValueError('CAPABILITY_UNAVAILABLE_MISSING_ACTIVATION')
    # Matching observations still do not authorize a state transition.
    if canonical(expected) != canonical(current):
        raise ValueError('STALE_CANONICAL_INVENTORY')
    return 'MATCHED_OBSERVATION_NOT_AUTHORITY'


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
