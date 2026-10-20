"""B3 read-only contracts. No service launch, Store mutation or grant operation.

These validators are not CP04--09 installation receipts. An unavailable runtime
contract must remain HOLD; passing unit tests does not close that dependency.
"""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys


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


def identity(expected, observed):
    """Compare configuration identity separately from a live process identity."""
    need(set(expected) == set(IDENTITY), 'EXPECTED_IDENTITY_FIELDS')
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
    program = '''import errno,os,sys
try:
 os.setgroups([])
 os.setgid(int(sys.argv[3]))
 os.setuid(int(sys.argv[2]))
except PermissionError:
 sys.exit(77)
try:
 fd=os.open(sys.argv[1],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 os.close(fd)
except OSError as e:
 sys.exit(0 if e.errno in (errno.EACCES,errno.EPERM) else 3)
sys.exit(4)
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', program,
                             str(path), str(denied_uid), str(denied_gid)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=5)
    if result.returncode == 77:
        return {'status': 'UNAVAILABLE', 'reason': 'INDEPENDENT_SUBJECT_REQUIRED'}
    need(result.returncode == 0, 'UNAUTHORIZED_DENIAL_NOT_PROVEN')
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
