"""P2-packaged read-only canonical inventory adapter.

Derived from DOTS_NATIVE task2/3 source b098ec251a11611dd7f79465d89e8b854b86bc89. This module opens no database,
creates no queue, grants no authority and dispatches no model/provider.
"""
from __future__ import print_function
import hashlib
import json
import math
import os
import re

DOTS_SOURCE_COMMIT='b098ec251a11611dd7f79465d89e8b854b86bc89'

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

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


def _bounded_inventory_json(raw):
    # Stable cross-version bound before recursive decoder/encoder work. Brackets
    # inside JSON strings (including escaped quotes) are data, not nesting.
    if not isinstance(raw, str):
        raise ValueError('INVENTORY_JSON_REQUIRED')
    depth = 0
    quoted = False
    escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > 64:
                raise ValueError('INVENTORY_JSON_DEPTH_EXCEEDED')
        elif char in ']}':
            depth -= 1
    return json.loads(raw)


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
            dependencies = _bounded_inventory_json(task['depends'])
            if (not isinstance(dependencies, list) or len(dependencies) > 32
                    or any(not isinstance(x, str) or not x for x in dependencies)
                    or len(set(dependencies)) != len(dependencies)):
                raise ValueError('bad dependencies')
        except (TypeError, ValueError, RecursionError):
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
            value = _bounded_inventory_json(raw_checkpoint)
            if not isinstance(value, dict):
                raise ValueError('checkpoint object required')
            native = value.get('native_execution', {})
            if not isinstance(native, dict):
                native = {}
            checkpoint_hash = hashlib.sha256(json.dumps(value, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        except (TypeError, ValueError, RecursionError):
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
