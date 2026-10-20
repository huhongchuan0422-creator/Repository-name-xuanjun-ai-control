"""B3 read-only contracts. No service launch, Store mutation or grant operation.

These validators are not CP04--09 installation receipts. An unavailable runtime
contract must remain HOLD; passing unit tests does not close that dependency.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import errno
import signal
import time
import uuid


class Hold(ValueError):
    pass


def need(value, code):
    if not value:
        raise Hold(code)


def pinned_file(path, expected, limit=1048576):
    """Read through no-follow descriptors, preserving the source unchanged."""
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'PATH_ABSOLUTE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        item = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=fd)
        with os.fdopen(item, 'rb') as stream:
            before = os.fstat(stream.fileno())
            need(stat.S_ISREG(before.st_mode) and before.st_size <= limit,
                 'SOURCE_REGULAR_BOUND')
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
                      'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            need(all(getattr(before, k) == getattr(after, k) for k in fields)
                 and len(raw) == before.st_size, 'SOURCE_CHANGED')
            need(hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_SHA')
            return raw
    finally:
        os.close(fd)


IDENTITY = ('installation_id', 'instance', 'ledger_uuid', 'generation',
            'release_sha256', 'config_sha256', 'binary_sha256',
            'db_path', 'ledger_socket')


def cp03_identity(root, receipt_sha256):
    """Read the original CP03 receipt/config/descriptor/journal; never reconcile."""
    root = Path(root)
    receipt = json.loads(pinned_file(root/'commit-receipt.json', receipt_sha256))
    need(receipt['status'] == 'COMMITTED' and receipt['scope'] == 'ISOLATED_TEST_ONLY'
         and receipt['origin'] == 'ISOLATED_NEW'
         and receipt['full_b3_complete'] is False, 'CP03_RECEIPT_IDENTITY')
    cfg = json.loads(pinned_file(root/'binding-config.json', receipt['config_sha256']))
    desc = json.loads(pinned_file(root/'activation/active.json', receipt['descriptor_file_sha256']))
    pinned_file(root/'activation/epochs.jsonl', receipt['journal_sha256'])
    need(desc['state'] == 'PREPARED' and desc['epoch'] == 1 and
         desc['generation'] == 1 and cfg['initial_state'] == 'PREPARED' and
         cfg['initial_epoch'] == 1, 'CP03_PREPARED_ONLY')
    need(receipt['installation_id'] == cfg['installation_id'] and
         desc['config_sha256'] == receipt['config_sha256'] and
         desc['binary_sha256'] == receipt['binary_sha256'] and
         desc['release_sha256'] == cfg['release_manifest_sha256'] and
         all(desc[k] == cfg[k] for k in ('instance','ledger_uuid','generation',
                                         'db_path','ledger_socket')), 'CP03_BINDING_CONFLICT')
    need(cfg['db_path'] == str(root/'data/ledger.sqlite3') and
         cfg['ledger_socket'] == str(root/'run/ledger.sock'), 'CP03_RESERVED_PATHS')
    need(not os.path.lexists(cfg['db_path']) and not os.path.lexists(cfg['ledger_socket']),
         'B3_UNEXPECTED_DATABASE_OR_SOCKET')
    return {k: (receipt[k] if k == 'installation_id' else desc[k]) for k in IDENTITY}


def identity(expected, observed):
    """Compare configuration identity separately from a live process identity."""
    need(set(expected) == set(IDENTITY), 'EXPECTED_IDENTITY_FIELDS')
    need(isinstance(expected['installation_id'],str) and bool(expected['installation_id'])
         and type(expected['generation']) is int and expected['generation'] == 1,
         'EXPECTED_IDENTITY_TYPES')
    for name in ('instance','ledger_uuid'):
        need(str(uuid.UUID(expected[name])) == expected[name], 'EXPECTED_UUID')
    for name in ('release_sha256','config_sha256','binary_sha256'):
        value = expected[name]
        need(isinstance(value,str) and len(value) == 64 and
             all(x in '0123456789abcdef' for x in value), 'EXPECTED_SHA')
    for name in ('db_path','ledger_socket'):
        value = Path(expected[name])
        need(value.is_absolute() and '..' not in value.parts, 'EXPECTED_PATH')
    need(isinstance(observed, dict) and set(observed) == {'identity', 'process'},
         'OBSERVED_FIELDS')
    need(observed['identity'] == expected, 'IDENTITY_CONFLICT')
    need(observed['process'] == {'state': 'NOT_STARTED', 'pid': None,
                                 'peer_uid': None}, 'B3_PROCESS_NOT_STARTED')
    return {'identity': 'MATCH', 'process': 'NOT_STARTED',
            'live_process_verified': False}


def path_contract(root, entries, uid, gid):
    """Validate an exact allowlist, not a recursive chmod or access grant."""
    root = Path(root)
    need(root.is_absolute() and '..' not in root.parts
         and str(root.resolve()) == str(root), 'ROOT_CANONICAL')
    need(type(uid) is int and type(gid) is int and uid >= 0 and gid >= 0,
         'SUBJECT_ID')
    allowed = {'data': 'RESERVED_DATABASE', 'run': 'RESERVED_SOCKET'}
    need(isinstance(entries, list) and len(entries) == 2, 'PATH_COUNT')
    seen = set()
    for row in entries:
        need(set(row) == {'path', 'uid', 'gid', 'mode', 'purpose'}, 'PATH_FIELDS')
        name = Path(row['path']).name
        need(name in allowed and name not in seen and
             row['path'] == str(root / name), 'PATH_SCOPE')
        need((row['uid'], row['gid'], row['mode'], row['purpose']) ==
             (uid, gid, 0o700, allowed[name]), 'PATH_SUBJECT_OR_MODE')
        seen.add(name)
    return True


def effective_access(path, uid, gid):
    """Observe access as the actual caller; never impersonate another subject."""
    need((os.geteuid(), os.getegid()) == (uid, gid), 'PROBE_SUBJECT')
    path = Path(path)
    need(str(path.resolve()) == str(path), 'ACCESS_LINK')
    s = os.lstat(path)
    need(stat.S_ISDIR(s.st_mode) and s.st_uid == uid and s.st_gid == gid
         and stat.S_IMODE(s.st_mode) == 0o700, 'ACCESS_PRIVATE_DIRECTORY')
    need(os.access(str(path), os.R_OK | os.W_OK | os.X_OK, effective_ids=True),
         'ACCESS_DENIED')
    # Actual unauthorized-subject denial requires an independent OS process.
    return {'authorized_access': 'PASS', 'unauthorized_denial': 'NOT_EXECUTED'}


def unauthorized_access(path, uid, gid, denied_uid, denied_gid):
    """Bounded OS-level denial probe; no files, sockets or credentials created.

UID changes are available only to an already privileged local test runner.
The UID1002 installation process returns UNAVAILABLE instead of inventing proof.
"""
    effective_access(path, uid, gid)
    need(type(denied_uid) is int and type(denied_gid) is int and
         denied_uid > 0 and denied_gid > 0 and denied_uid != uid, 'DENIED_SUBJECT')
    if os.geteuid() != 0:
        return {'status': 'UNAVAILABLE', 'reason': 'INDEPENDENT_SUBJECT_REQUIRED'}
    child = os.fork()
    if child == 0:
        code = 3
        try:
            try:
                os.setgroups([]); os.setgid(denied_gid); os.setuid(denied_uid)
            except PermissionError:
                os._exit(77)
            try:
                fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                os.close(fd); code = 4
            except OSError as exc:
                code = 0 if exc.errno in (errno.EACCES, errno.EPERM) else 3
        finally:
            os._exit(code)
    deadline = time.monotonic() + 5
    while True:
        observed, status = os.waitpid(child, os.WNOHANG)
        if observed:
            break
        if time.monotonic() >= deadline:
            os.kill(child, signal.SIGKILL); os.waitpid(child, 0)
            raise Hold('DENIAL_PROBE_TIMEOUT')
        time.sleep(.01)
    code = os.waitstatus_to_exitcode(status)
    if code == 77:
        return {'status': 'UNAVAILABLE', 'reason': 'INDEPENDENT_SUBJECT_REQUIRED'}
    need(code == 0, 'UNAUTHORIZED_DENIAL_NOT_PROVEN')
    return {'status': 'PASS', 'uid': denied_uid, 'gid': denied_gid,
            'operation': 'OPEN_DIRECTORY', 'scope': 'EXACT_PATH_ONLY'}


def tls_applicability(runtime):
    """Unknown configuration cannot establish a scoped TLS exemption."""
    need(isinstance(runtime, dict) and runtime.get('status') == 'BOUND',
         'RUNTIME_UNAVAILABLE')
    need(set(runtime) == {'status', 'listeners', 'outbound', 'tls_required'},
         'TLS_CONTRACT_FIELDS')
    need(type(runtime['tls_required']) is bool, 'TLS_REQUIREMENT_UNKNOWN')
    endpoints = runtime['listeners'] + runtime['outbound']
    need(bool(endpoints), 'TRANSPORT_UNKNOWN')
    for endpoint in endpoints:
        need(isinstance(endpoint, dict) and set(endpoint) == {'transport', 'address'},
             'TRANSPORT_FIELDS')
        need(endpoint['transport'] in ('unix', 'tcp', 'tls') and
             isinstance(endpoint['address'], str) and bool(endpoint['address']),
             'TRANSPORT_UNKNOWN')
    if not runtime['tls_required'] and all(e['transport'] == 'unix' for e in endpoints):
        return {'status': 'NOT_APPLICABLE', 'scope': 'BOUND_UNIX_ENDPOINTS_ONLY'}
    return {'status': 'HOLD', 'reason': 'TLS_MATERIAL_AND_CONSUMER_NOT_VERIFIED'}
