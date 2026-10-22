"""B6 isolated existing application DB observation; no bootstrap or activation.

Database observations reuse pinned ExecutionLedger validators. The retained
activation-after-start observation keeps its original ACTIVE fence; it is NOT
the preactivation CP13 phase. No DDL/DML, migration, WAL removal,
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


def observe_database_evidence(request, stage, previous_outcome='KNOWN'):
    """Retained low-level DB observation, NOT original CP12/13 completion.

    UNKNOWN produces a fresh reconciliation observation, no task replay or
    migration. SQLite may create/update its own SHM coordination file; DB/WAL
    remain in place. Caller persists this result in the existing receipt layer.
    """
    result = {'scope': 'ISOLATED_TEST_ONLY', 'status': 'HOLD', 'stage': stage,
              'site_complete': False, 'service_started': False, 'database_created': False,
              'replay_performed': False, 'previous_outcome': previous_outcome,
              'evidence_scope': 'POST_ACTIVATION_DATABASE_OBSERVATION_NOT_B6_PHASE'
              if stage == 'CP13' else 'DATABASE_READBACK_ONLY_NOT_PHASE_COMPLETION'}
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
             str(root).startswith(('/tmp/p2-b6-test-', '/tmp/p2-b3-test-')), 'ISOLATED_ROOT_REQUIRED')
        s = os.lstat(str(root))
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == request['uid'] and
             stat.S_IMODE(s.st_mode) == 0o700, 'ROOT_PRIVATE')
        db = Path(request['db_path'])
        need(db.is_absolute() and str(db.resolve()) == str(db) and '..' not in db.parts and
             root in db.parents, 'DATABASE_PATH')
        # Retained bound B3 data/run owner+0700 guards belong to the current
        # DB/path observation, not to historical preparation evidence. No
        # ownership policy or access grant is inferred from the preparer UID.
        if db == root/'data/ledger.sqlite3':
            for folder in (root/'data', root/'run'):
                info = os.lstat(folder)
                need(stat.S_ISDIR(info.st_mode) and info.st_uid == request['uid'] and
                     stat.S_IMODE(info.st_mode) == 0o700, 'RUNTIME_DIRECTORY_PROTECTION')
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


# Original phase semantics, not an authorization generated by this adapter.
PREACTIVATION_CONTRACT = {
    'source': 'epoch7_runtime_effects.py',
    'source_git_blob': 'd3dbd171ce33d9d48ed31beaa1622ca38819b54f',
    'CP12': {'entry': 'reopen_existing_database', 'lines': [424, 455],
             'activation': 'QUIESCED', 'result': 'ledger-access.json:REOPENED'},
    'CP13': {'entry': 'verify_runtime_access', 'lines': [457, 462],
             'activation': 'QUIESCED', 'predecessor': 'ledger-access.json:REOPENED',
             'consumer': 'runtime_access_check(context, diagnostics) -> check_observation'},
}


def observe(request, stage, previous_outcome='KNOWN'):
    """Map B6 phases without falsely promoting DB reads to access acceptance.

    The current isolated request has no original REOPENED effect receipt or
    trusted preactivation role/path access consumer. Do NOT accept hand-filled
    PASS, add an activation transition, or call the ACTIVE-only observation as
    CP13. Raw readback remains useful evidence while both phase results HOLD.
    """
    if stage not in ('CP12', 'CP13'):
        return {'scope': 'ISOLATED_TEST_ONLY', 'status': 'HOLD', 'stage': stage,
                'site_complete': False, 'error': {'code': 'STAGE'}}
    # CP12 here means the retained non-activating schema/readback observation,
    # not the original stage completion or a relaxed CP13 ACTIVE guard.
    evidence = observe_database_evidence(request, 'CP12', previous_outcome)
    result = {'scope': 'ISOLATED_TEST_ONLY', 'status': 'HOLD', 'stage': stage,
              'site_complete': False, 'phase_complete': False,
              'activation_performed': False, 'replay_performed': False,
              'contract': PREACTIVATION_CONTRACT[stage],
              'database_evidence': evidence}
    if evidence['status'] == 'HOLD':
        result['error'] = evidence['error']
    elif evidence['activation_state'] != 'QUIESCED':
        result['error'] = {'code': 'B6_REQUIRES_QUIESCED_NOT_PREPARED_OR_ACTIVE'}
    else:
        result['error'] = {'code': 'PREACTIVATION_EFFECT_AND_ACCESS_CONTRACT_UNAVAILABLE'}
        result['missing'] = [
            'Trusted isolated CP12 REOPENED effect receipt bound to this DB inode and activation identity',
            'Mapped service/callback roles and path policy (B3 preparer UID is not service identity)',
            'Original preactivation runtime_access_check context/consumer and validated observation',
            'Explicit isolated WAL recovery equivalence; legacy CP12 forbids WAL/SHM and transfers ownership',
        ]
    return result


def consume_preparation(request, anchors):
    """Read original B3 history without dispatch/cp03_identity or mutation.

    Anchors are retained receipt digests supplied by the trusted caller, not
    evidence of authority by themselves. No runtime role or REOPENED is granted.
    Historical PREPARED is checked against the first native journal record;
    the current descriptor must independently remain the same QUIESCED epoch.
    """
    from production.p2_install.b3_contracts import pinned_file
    from production.p2_install import b3_ledger
    encode, digest = b3_ledger.encode, b3_ledger.sha
    need(set(anchors) == {'cp03_receipt_sha256', 'preparation_receipt_sha256'}, 'HISTORY_ANCHORS')
    for pin in anchors.values():
        need(type(pin) is str and len(pin) == 64 and all(c in '0123456789abcdef' for c in pin),
             'HISTORY_ANCHOR_SHA')
    need(set(request) == {'scope', 'profile', 'root', 'db_path', 'uid', 'gid',
                         'activation', 'task_ids'}, 'BOUND_REQUEST_FIELDS')
    need(request['scope'] == 'ISOLATED_TEST_ONLY' and
         request['profile'] == 'B6_EXISTING_APPLICATION_DATABASE_OBSERVATION', 'B6_PROFILE_REQUIRED')
    root = Path(request['root'])
    need(root.is_absolute() and str(root.resolve()) == str(root) and '..' not in root.parts,
         'HISTORY_ROOT_CANONICAL')
    need(str(root) == '/var/lib/xuanjun-p2-isolated-test/b3-initialize' or
         (str(root).startswith('/tmp/p2-b3-test-') and root.name == 'b3-initialize'), 'HISTORY_ROOT_SCOPE')
    need(type(request['uid']) is int and type(request['gid']) is int and
         (request['uid'], request['gid']) == (os.geteuid(), os.getegid()), 'SUBJECT_IDENTITY')
    # Reader is the actual current caller, not the historical provenance owner.
    # The candidate owner is confirmed below by pinned CP07/profile evidence.
    history_owner = os.lstat(root).st_uid
    def stamp(info):
        return tuple(getattr(info, k) for k in ('st_dev', 'st_ino', 'st_mode',
                     'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    directories = {}
    for folder in (root, root/'prepared', root/'activation'):
        info = os.lstat(folder)
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == history_owner and
             stat.S_IMODE(info.st_mode) == 0o700, 'HISTORY_DIRECTORY_PROTECTION')
        directories[folder] = stamp(info)
    # data/run are current runtime resources. Their owner checks remain in the
    # DB observer; they are not preparation evidence or preparation authority.
    seen = {}

    def read(path, pin, limit=1048576):
        path = Path(path)
        need(path.is_absolute() and '..' not in path.parts, 'HISTORY_PATH')
        before = os.lstat(path)
        raw = pinned_file(path, pin, limit)
        info = os.lstat(path)
        need(stamp(before) == stamp(info), 'HISTORY_PATH_CHANGED')
        need(stat.S_ISREG(info.st_mode) and info.st_nlink in (1, 2) and not info.st_mode & 0o022,
             'HISTORY_FILE_PROTECTION')
        if root in path.parents:
            need(info.st_uid == history_owner, 'HISTORY_FILE_OWNER')
        if str(path) in seen:
            need(seen[str(path)] == (pin, limit, stamp(info)), 'HISTORY_FILE_IDENTITY_CHANGED')
        seen[str(path)] = (pin, limit, stamp(info))
        return raw

    def decode(raw):
        def pairs(rows):
            value = {}
            for key, item in rows:
                need(key not in value, 'HISTORY_DUPLICATE_FIELD')
                value[key] = item
            return value
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: need(False, 'HISTORY_NONFINITE'))

    cp03 = decode(read(root/'commit-receipt.json', anchors['cp03_receipt_sha256']))
    need(cp03['schema'] == 1 and cp03['scope'] == 'ISOLATED_TEST_ONLY' and
         cp03['origin'] == 'ISOLATED_NEW' and cp03['status'] == 'COMMITTED' and
         cp03['full_b3_complete'] is False and cp03['database'] == 'RESERVED_NOT_CREATED' and
         cp03['socket'] == 'RESERVED_NOT_BOUND', 'HISTORY_CP03')
    binding = decode(read(root/'binding-config.json', cp03['config_sha256']))
    need(binding['origin'] == 'ISOLATED_NEW' and binding['scope'] == 'ISOLATED_TEST_ONLY' and
         all(binding[k] is False for k in ('start_services', 'create_database', 'bind_socket')) and
         binding['initial_state'] == 'PREPARED' and binding['initial_epoch'] == 1 and
         binding['generation'] == 1 and binding['installation_id'] == cp03['installation_id'],
         'HISTORY_PREPARED_IDENTITY')
    _, Activation = application_contract()
    fixed_activation = dict(descriptor=str(root/'activation/active.json'),
                            epoch_journal=str(root/'activation/epochs.jsonl'),
                            lock_path=str(root/'activation/activation.lock'), owner_uid=history_owner)
    need(request['activation'] == fixed_activation, 'HISTORY_ACTIVATION_PATHS')
    store = Activation(**fixed_activation)
    current = store.read(require_active=False)
    records = store._journal()  # original full chain validation, no reconcile/lock write
    initial = records[0][0]['descriptor']
    need(initial['state'] == 'PREPARED' and initial['epoch'] == initial['generation'] == 1,
         'HISTORY_INITIAL_STATE')
    need(digest(encode(initial)+b'\n') == cp03['descriptor_file_sha256'] and
         digest(encode(records[0][0])+b'\n') == cp03['journal_sha256'] and
         cp03['descriptor_head_sha256'] == records[0][0]['descriptor_sha256'], 'HISTORY_CP03_JOURNAL')
    need(current['state'] == 'QUIESCED' and len(records) == 2 and
         all(current[k] == initial[k] for k in Activation.REQUIRED - {'state'}),
         'HISTORY_CURRENT_QUIESCED_IDENTITY')
    need(initial['release_sha256'] == binding['release_manifest_sha256'] and
         initial['config_sha256'] == cp03['config_sha256'] and
         initial['binary_sha256'] == cp03['binary_sha256'] and
         all(initial[k] == binding[k] for k in ('instance', 'ledger_uuid', 'generation',
                                              'db_path', 'ledger_socket')), 'HISTORY_BINDING_IDENTITY')
    need(request['db_path'] == initial['db_path'] == str(root/'data/ledger.sqlite3') and
         initial['ledger_socket'] == str(root/'run/ledger.sock'), 'HISTORY_RESERVED_PATHS')
    final = decode(read(root/'prepared/preparation-receipt.json', anchors['preparation_receipt_sha256']))
    need(set(final) == {'schema', 'scope', 'status', 'request_sha256', 'last_checkpoint_sha256',
                        'service_started', 'production_permission', 'full_b3_complete'} and
         final['schema'] == 1 and final['scope'] == 'ISOLATED_TEST_ONLY' and
         final['status'] == 'PREPARATION_COMMITTED' and
         all(final[k] is False for k in ('service_started', 'production_permission', 'full_b3_complete')),
         'HISTORY_FINAL')
    # Walk backwards from the externally pinned terminal receipt, never hash an
    # arbitrary unanchored input and bless it as its own source.
    rows = {}
    previous = final['last_checkpoint_sha256']
    for stage in reversed(b3_ledger.STAGES):
        row = decode(read(root/'prepared'/(stage+'-committed.json'), previous))
        need(set(row) == {'schema', 'scope', 'stage', 'status', 'request_sha256',
                          'previous_receipt_sha256', 'evidence'} and row['schema'] == 1 and
             row['scope'] == 'ISOLATED_TEST_ONLY' and row['stage'] == stage and
             row['status'] == 'PREPARATION_CHECKPOINT_COMMITTED' and
             row['request_sha256'] == final['request_sha256'] and
             row['evidence']['status'] == 'VALIDATED', 'HISTORY_CHECKPOINT_CHAIN')
        rows[stage] = row['evidence']
        previous = row['previous_receipt_sha256']
    need(previous == anchors['cp03_receipt_sha256'], 'HISTORY_CP03_CHAIN')
    # intent bytes were canonical encode(request envelope), not a raw request.
    # Obtain request only from protected bounded bytes, then require its exact
    # anchored digest and canonical envelope before allowing any source paths.
    intent_path = root/'prepared/intent.json'
    raw = b3_ledger.read(intent_path)  # original bounded dirfd/NOFOLLOW reader
    intent = decode(raw)
    req = intent['request']
    need(set(intent) == {'request_sha256', 'request'} and
         digest(encode(req)) == intent['request_sha256'] == final['request_sha256'] and
         raw == encode(intent), 'HISTORY_REQUEST_SHA')
    read(intent_path, digest(raw))
    need(set(req) == {'schema', 'scope', 'root', 'application', 'binary', 'sources',
                      'operation_id', 'cp03_receipt_sha256'} and req['schema'] == 1 and
         req['scope'] == 'ISOLATED_TEST_ONLY' and req['root'] == str(root) and
         req['cp03_receipt_sha256'] == anchors['cp03_receipt_sha256'] and
         set(req['sources']) == set(b3_ledger.NAMES), 'HISTORY_REQUEST_BINDING')
    if str(root).startswith('/var/lib/'):
        need(history_owner == 1002 and req['cp03_receipt_sha256'] == b3_ledger.RECEIPT and
             req['application'] == '/application/stage1' and
             req['operation_id'] == 'p2-uk-isolated-20261020:b3-ledger-prepare-a1', 'HISTORY_FIXED_SOURCE')
    expected = {k: (cp03['installation_id'] if k == 'installation_id' else initial[k])
                for k in ('installation_id', 'instance', 'ledger_uuid', 'generation',
                          'release_sha256', 'config_sha256', 'binary_sha256', 'db_path', 'ledger_socket')}
    need(type(rows['CP07']['subject_uid']) is int and
         rows['CP07']['subject_uid'] == history_owner, 'HISTORY_PREPARER_OWNER')
    cfg, profile, invocation, _, identity = b3_ledger.documents(req, expected)
    # documents() uses the calling UID when generating NEW preparation files.
    # Here compare HISTORY: restore only its anchored preparer field, preserving
    # original service/callback policy, configuration and all source digests.
    profile['preparation_uid'] = history_owner
    profile['roles'] = dict(profile['roles'], preparer_uid=history_owner)
    identity['roles'] = profile['roles']
    identity['profile_sha256'] = digest(encode(profile))
    files = rows['CP07']['files']
    need(set(files) == {'ledger-config.json', 'profile.json', 'runtime-invocation.json',
                        'expected-identity.json'}, 'HISTORY_DOCUMENT_FILES')
    for name, value in zip(('ledger-config.json', 'profile.json', 'runtime-invocation.json',
                            'expected-identity.json'), (cfg, profile, invocation, identity)):
        need(read(root/'prepared'/name, files[name]) == encode(value), 'HISTORY_DOCUMENT_CONFLICT')
    need(rows['CP04']['cp03_receipt_sha256'] == anchors['cp03_receipt_sha256'] and
         rows['CP05']['invocation_sha256'] == digest(encode(invocation)) and
         rows['CP06']['identity_sha256'] == digest(encode(identity)) and
         rows['CP07']['subject_uid'] == history_owner and
         rows['CP07']['private_root'] == str(root/'prepared') and
         rows['CP07']['service_uid'] == 'UNKNOWN' and
         rows['CP07']['runtime_roles_granted_access'] is False, 'HISTORY_EVIDENCE_BINDING')
    consumer = rows['CP05']['consumer']
    need(consumer['status'] == 'PREPARED_CONFIG_VALIDATED' and
         consumer['config_sha256'] == digest(encode(cfg)) and
         consumer['profile_sha256'] == digest(encode(profile)) and
         consumer['operation_id'] == req['operation_id'] and consumer['instance'] == initial['instance'] and
         consumer['activation_state'] == 'PREPARED' and
         all(consumer[k] is False for k in ('service_started', 'database_opened', 'socket_bound',
                                          'roles_verified_for_start')) and
         rows['CP09']['tls'] == consumer['tls'] and
         rows['CP08']['denial']['status'] == 'PASS', 'HISTORY_CONSUMER_BINDING')
    app = Path(req['application'])
    need(app.is_absolute() and '..' not in app.parts and str(app.resolve()) == str(app), 'HISTORY_APPLICATION_PATH')
    for name, pin in req['sources'].items():
        read(app/name, pin)
    binary = req['binary']
    need(set(binary) == {'path', 'bytes', 'sha256'} and binary['sha256'] == initial['binary_sha256'],
         'HISTORY_BINARY_BINDING')
    need(len(read(binary['path'], binary['sha256'], 32*1024*1024)) == binary['bytes'], 'HISTORY_BINARY_SIZE')
    # Re-read all pins and the native current chain to refuse concurrent drift.
    for path, (pin, limit, _) in list(seen.items()):
        read(path, pin, limit)
    for folder, before in directories.items():
        need(stamp(os.lstat(folder)) == before, 'HISTORY_DIRECTORY_CHANGED')
    need(store.read(require_active=False) == current and store._journal() == records,
         'HISTORY_ACTIVATION_DRIFT')
    return {'status': 'BOUND_HISTORY_ONLY', 'scope': 'ISOLATED_TEST_ONLY',
            'anchors': dict(anchors), 'identity': expected, 'current': current,
            'historical_state': 'PREPARED', 'current_state': 'QUIESCED',
            'history_owner_uid': history_owner,
            'reader': {'uid': request['uid'], 'gid': request['gid']},
            'configuration_sha256': digest(encode(cfg)), 'sources': req['sources'],
            'roles': profile['roles'], 'runtime_roles_granted_access': False,
            'service_access': 'UNKNOWN', 'phase_complete': False,
            'files_sha256': {path: pin for path, (pin, _, _) in seen.items()}}


def observe_prepared(request, anchors, stage, previous_outcome='KNOWN'):
    """B6 history-bound entry; no caller-supplied expected/PASS is accepted."""
    try:
        need(stage in ('CP12', 'CP13'), 'STAGE')
        history = consume_preparation(request, anchors)
        # Explicit current observing-subject request, not an inferred service
        # role or an ownership transfer from the historical preparer. Retained
        # DB/root/ancestor/inode/sidecar guards must independently accept it.
        derived = {k: request[k] for k in ('scope', 'profile', 'root', 'db_path',
                   'uid', 'gid', 'activation', 'task_ids')}
        derived['expected'] = history['current']
        result = observe(derived, stage, previous_outcome)
        # DB observation revalidates this exact identity. History is evidence,
        # never a REOPENED receipt or a service/callback access authorization.
        _, Activation = application_contract()
        need(Activation(**request['activation']).read() == history['current'], 'HISTORY_ACTIVATION_DRIFT')
        result['preparation_evidence'] = history
        result['database_subject'] = {'uid': request['uid'], 'gid': request['gid'],
                                      'role_verified': False,
                                      'scope': 'CURRENT_OBSERVER_NOT_RUNTIME_AUTHORIZATION'}
        return result
    except Exception as exc:
        return {'scope': 'ISOLATED_TEST_ONLY', 'status': 'HOLD', 'stage': stage,
                'phase_complete': False, 'site_complete': False,
                'error': {'type': type(exc).__name__, 'code': str(exc)[:300]}}
