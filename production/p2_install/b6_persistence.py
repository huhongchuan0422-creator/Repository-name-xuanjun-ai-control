"""B6 isolated existing application DB observation; no bootstrap or activation.

CP12 reuses the pinned ExecutionLedger schema validators. CP13 additionally
uses its original ACTIVE transaction fence. No DDL/DML, migration, WAL removal,
activation transition, service start or automatic replay is performed here.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import types
import time

SOURCE_ROOT = Path(__file__).resolve().parents[2] / 'evidence/p2-epoch7-access-repair-20261014/runtime/stage1'
PINS = {'execution_ledger.py': '8c607f0e2222d906b8450b302dad014a69dfedcb710a257731454e0d97aaf8c6',
        'activation_control.py': '169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4'}


def need(ok, code):
    if not ok:
        raise ValueError(code)


def application_contract():
    modules = {}
    for name, pin in PINS.items():
        raw = (SOURCE_ROOT / name).read_bytes()
        need(hashlib.sha256(raw).hexdigest() == pin, 'APPLICATION_SOURCE_SHA')
        module = types.ModuleType('b6_original_' + name[:-3])
        module.__file__ = str(SOURCE_ROOT / name)
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        modules[name] = module
    return modules['execution_ledger.py'].ExecutionLedger, modules['activation_control.py'].ActivationStore


def _regular(path, uid):
    s = os.lstat(str(path))
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == uid and
         not s.st_mode & 0o022, 'DATABASE_FILE_PROTECTION')
    return s.st_dev, s.st_ino


def observe(request, stage, previous_outcome='KNOWN'):
    """Read-only CP12/CP13 proof, never a persisted installation commit.

    UNKNOWN produces a fresh reconciliation observation, no task replay or
    migration. SQLite may create/update its own SHM coordination file; DB/WAL
    remain in place. Caller persists this result in the existing receipt layer.
    """
    result = {'scope': 'ISOLATED_TEST_ONLY', 'status': 'HOLD', 'stage': stage,
              'site_complete': False, 'service_started': False, 'database_created': False,
              'replay_performed': False, 'previous_outcome': previous_outcome}
    fd = None
    conn = None
    try:
        need(stage in ('CP12', 'CP13'), 'STAGE')
        need(previous_outcome in ('KNOWN', 'UNKNOWN'), 'OUTCOME')
        need(set(request) == {'scope', 'profile', 'root', 'db_path', 'uid', 'gid',
                             'activation', 'expected', 'task_ids'}, 'REQUEST_FIELDS')
        need(request['scope'] == 'ISOLATED_TEST_ONLY' and
             request['profile'] == 'B6_EXISTING_APPLICATION_DATABASE_OBSERVATION', 'B6_PROFILE_REQUIRED')
        need(type(request['uid']) is int and type(request['gid']) is int and
             (os.geteuid(), os.getegid()) == (request['uid'], request['gid']), 'SUBJECT_IDENTITY')
        root = Path(request['root'])
        need(root.is_absolute() and str(root.resolve()) == str(root) and '..' not in root.parts,
             'ROOT_CANONICAL')
        need(str(root).startswith('/var/lib/xuanjun-p2-isolated-test/') or
             str(root).startswith('/tmp/p2-b6-test-'), 'ISOLATED_ROOT_REQUIRED')
        s = os.lstat(str(root))
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == request['uid'] and
             stat.S_IMODE(s.st_mode) == 0o700, 'ROOT_PRIVATE')
        db = Path(request['db_path'])
        need(db.is_absolute() and str(db.resolve()) == str(db) and '..' not in db.parts and
             root in db.parents, 'DATABASE_PATH')
        p = db.parent
        while p != root:
            s = os.lstat(str(p))
            need(stat.S_ISDIR(s.st_mode) and s.st_uid == request['uid'] and not s.st_mode & 0o022,
                 'DATABASE_PARENT_PROTECTION')
            p = p.parent
        Ledger, Activation = application_contract()
        need(set(request['activation']) == {'descriptor', 'epoch_journal', 'lock_path', 'owner_uid'},
             'ACTIVATION_FIELDS')
        for key in ('descriptor', 'epoch_journal', 'lock_path'):
            path = Path(request['activation'][key])
            need(root in path.parents and path.is_absolute() and str(path.resolve()) == str(path),
                 'ACTIVATION_PATH')
        expected = Activation.validate(request['expected'])
        need(expected['db_path'] == str(db), 'DATABASE_IDENTITY')
        store = Activation(**request['activation'])
        active = store.read(require_active=stage == 'CP13')
        need(active == expected, 'ACTIVATION_IDENTITY')
        need(type(request['task_ids']) is list and len(request['task_ids']) <= 100 and
             all(type(x) is str and 0 < len(x) <= 256 for x in request['task_ids']) and
             len(set(request['task_ids'])) == len(request['task_ids']), 'TASK_IDS')
        identity = _regular(db, request['uid'])
        side_identities = {}
        for suffix in ('-wal', '-shm'):
            path = Path(str(db) + suffix)
            if os.path.lexists(str(path)):
                side_identities[suffix] = _regular(path, request['uid'])
        fd = os.open(str(db), os.O_RDONLY | os.O_NOFOLLOW)
        need((os.fstat(fd).st_dev, os.fstat(fd).st_ino) == identity, 'DATABASE_RACE')
        conn = sqlite3.connect('file:/proc/self/fd/%d?mode=ro' % fd, uri=True, timeout=1)
        deadline = time.monotonic() + 5
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        Ledger._validate_schema(conn)
        Ledger._validate_side_schema(conn)
        need(conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'DATABASE_INTEGRITY')
        # Native CP13 fence is preserved; no __init__ side-table creation.
        if stage == 'CP13':
            ledger = Ledger.__new__(Ledger)
            ledger.db_path = str(db)
            ledger.activation_store = store
            ledger.activation_binding = {k: active[k] for k in
                                         ('ledger_uuid', 'generation', 'epoch', 'instance', 'db_path')}
            ledger._assert_activation()
        tasks = []
        for task_id in request['task_ids']:
            row = conn.execute('SELECT id,kind,state,depends,lease_owner,lease_until,fence,checkpoint,updated '
                               'FROM tasks WHERE id=?', (task_id,)).fetchone()
            need(row is not None, 'EXPECTED_TASK_ABSENT')
            tasks.append(dict(row))
        events = []
        for task_id in request['task_ids']:
            events.extend(dict(row) for row in conn.execute(
                'SELECT id,task_id,event,created,details FROM events WHERE task_id=? ORDER BY id DESC LIMIT 20',
                (task_id,)).fetchall())
        need(store.read(require_active=stage == 'CP13') == active, 'ACTIVATION_CHANGED')
        need(_regular(db, request['uid']) == identity, 'DATABASE_PATH_CHANGED')
        for suffix, before in side_identities.items():
            need(_regular(Path(str(db)+suffix), request['uid']) == before, 'DATABASE_SIDECAR_CHANGED')
        result.update(status='RECONCILED_READBACK' if previous_outcome == 'UNKNOWN' else 'OBSERVED',
                      activation_state=active['state'], ledger_identity='%s:%s' % identity,
                      task_rows=tasks, event_rows=events, task_rows_sha256=hashlib.sha256(json.dumps(
                          tasks, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
                      access='READ_ONLY_APPLICATION_DB_NOT_SOCKET_OR_WRITE_AUTHORIZATION',
                      original_active_guard='PASSED' if stage == 'CP13' else 'NOT_REQUESTED_CP12_ONLY')
    except Exception as exc:
        result['error'] = {'type': type(exc).__name__, 'code': str(exc)[:300]}
    finally:
        if conn is not None:
            conn.close()
        if fd is not None:
            os.close(fd)
    return result
