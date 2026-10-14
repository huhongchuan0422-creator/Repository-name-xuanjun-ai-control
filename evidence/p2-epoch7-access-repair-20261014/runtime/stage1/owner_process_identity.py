"""Protected exact Owner callback process gate; Python 3.6 compatible.

No UID-only fallback. A root-provisioned policy is required before the callable
can be built. Secret-file CONTENTS are never read: full argv/config paths and
the rendered root-owned service unit are pinned, alongside the script/Python.
"""
import hashlib
import json
import os
import pwd
import re
import stat

import native_peer_identity as native

OWNER_BINDING_FILE = '/etc/xuanjun-development/p2-owner-process-identity.json'
CALLBACK_UID = 1004
CALLBACK_USER = 'xuanjun-callback'
CALLBACK_UNIT = '/etc/systemd/system/xuanjun-uk-owner-callback.service'
CALLBACK_CGROUP = '/system.slice/xuanjun-uk-owner-callback.service'
POLICY_KEYS = frozenset(('schema', 'callback_uid', 'release_sha256', 'python_exe',
    'python_sha256', 'script', 'script_sha256', 'unit_file', 'unit_sha256',
    'argv', 'cgroup'))
SCRIPT_PATTERN = re.compile(
    r'^/opt/xuanjun-control-releases/integration-([0-9a-f]{16})/stage1/owner_callback_server\.py$')


def _expected_argv(script):
    return ['/usr/bin/python3', script,
        '--activation-descriptor', '/var/lib/xuanjun-development/activation/active.json',
        '--activation-epoch-journal', '/var/lib/xuanjun-development/activation/epochs.jsonl',
        '--activation-lock', '/var/lib/xuanjun-development/activation/activation.lock',
        '--auth-file', '/etc/xuanjun-owner-callback/owner-callback-auth',
        '--hmac-key-file', '/etc/xuanjun-owner-callback/owner-callback-hmac',
        '--owner-id-file', '/etc/xuanjun-owner-callback/owner-user-id',
        '--owner-chat-id-file', '/etc/xuanjun-owner-callback/owner-chat-id',
        '--port', '18557', '--socket-timeout', '5', '--max-workers', '8']


def _protected_chain(path):
    if not native._canonical_absolute(path) or os.path.realpath(path) != path:
        raise ValueError('OWNER_PIN_CANONICAL_PATH_REQUIRED')
    parent = os.path.dirname(path)
    while True:
        info = os.stat(parent, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('OWNER_PIN_ROOT_PROTECTED_ANCESTRY_REQUIRED')
        if parent == '/':
            break
        parent = os.path.dirname(parent)


def _read_protected(path, maximum=65536):
    _protected_chain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 getattr(os, 'O_CLOEXEC', 0))
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                or before.st_mode & 0o022 or not 0 <= before.st_size <= maximum):
            raise ValueError('OWNER_PIN_ROOT_PROTECTED_FILE_REQUIRED')
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(65536, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ValueError('OWNER_PIN_SIZE_BOUND')
            chunks.append(chunk)
        after = os.fstat(fd)
        if (native._file_identity(before) != native._file_identity(after)
                or total != before.st_size):
            raise ValueError('OWNER_PIN_CHANGED_DURING_READ')
        return b''.join(chunks), native._file_identity(after)
    finally:
        os.close(fd)


def _root_file_digest(path):
    _protected_chain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 getattr(os, 'O_CLOEXEC', 0))
    try:
        return native._owned_fd_sha256(fd, 0, 256 * 1024 * 1024)
    finally:
        os.close(fd)


def _root_file_identity(path):
    _protected_chain(path)
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('OWNER_PIN_ROOT_PROTECTED_FILE_REQUIRED')
    return native._file_identity(info)


def _strict_policy(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('OWNER_PIN_DUPLICATE_KEY')
            result[key] = value
        return result
    def constant(unused):
        raise ValueError('OWNER_PIN_NONFINITE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def _validate_policy(value):
    if (not isinstance(value, dict) or set(value) != POLICY_KEYS
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['callback_uid']) is not int or value['callback_uid'] != CALLBACK_UID
            or value['unit_file'] != CALLBACK_UNIT or value['cgroup'] != CALLBACK_CGROUP):
        raise ValueError('OWNER_PIN_EXACT_POLICY_REQUIRED')
    for field in ('release_sha256', 'python_sha256', 'script_sha256', 'unit_sha256'):
        if not isinstance(value[field], str) or not native.SHA256.fullmatch(value[field]):
            raise ValueError('OWNER_PIN_DIGEST_REQUIRED')
    if not native._canonical_absolute(value['python_exe']):
        raise ValueError('OWNER_PIN_PYTHON_PATH_REQUIRED')
    match = SCRIPT_PATTERN.fullmatch(value['script']) if isinstance(value['script'], str) else None
    if not match or match.group(1) != value['release_sha256'][:16]:
        raise ValueError('OWNER_PIN_RELEASE_SCRIPT_REQUIRED')
    if (not isinstance(value['argv'], list)
            or value['argv'] != _expected_argv(value['script'])
            or any(type(item) is not str for item in value['argv'])):
        raise ValueError('OWNER_PIN_EXACT_ARGV_REQUIRED')
    return dict(value, argv=list(value['argv']))


def _validate_unit(raw, argv):
    # The reviewed standard unit uses one literal ExecStart and no continuation
    # or quoting. Reject ambiguity instead of implementing systemd's parser.
    selected, section = {}, None
    for line in raw.decode('utf-8', 'strict').splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            continue
        if section == 'Service' and '=' in line:
            key, value = line.split('=', 1)
            if key in ('User', 'Group', 'ExecStart'):
                if key in selected:
                    raise ValueError('OWNER_PIN_AMBIGUOUS_UNIT')
                selected[key] = value
    if selected != {'User': CALLBACK_USER, 'Group': 'xuanjun-control-db',
                    'ExecStart': ' '.join(argv)}:
        raise ValueError('OWNER_PIN_UNIT_INVOCATION_MISMATCH')


def _callback_cgroup(raw, expected):
    matched = False
    for line in raw.decode('utf-8', 'strict').splitlines():
        fields = line.split(':', 2)
        if len(fields) != 3:
            raise ValueError('OWNER_PIN_CGROUP_MALFORMED')
        hierarchy, controllers, path = fields
        if ((hierarchy == '0' and controllers == '')
                or 'name=systemd' in controllers.split(',')):
            if path != expected:
                return False
            matched = True
    return matched


def load_owner_process_verifier(expected_release_sha256, binding_path=OWNER_BINDING_FILE,
                                proc_root='/proc'):
    """Load mandatory root pins; missing/unsafe/inconsistent policy raises.

    proc_root is for injected local tests; production wiring must leave /proc.
    No secret file or host/service setting is modified by this function.
    """
    if (not isinstance(expected_release_sha256, str)
            or not native.SHA256.fullmatch(expected_release_sha256)):
        raise ValueError('OWNER_PIN_EXPECTED_RELEASE_REQUIRED')
    raw, binding_identity = _read_protected(binding_path)
    if (stat.S_IMODE(binding_identity[2]) != 0o644 or binding_identity[3:6] != (0, 0, 1)):
        raise ValueError('OWNER_PIN_EXACT_ROOT_ROOT_0644_SINGLE_FILE_REQUIRED')
    policy = _validate_policy(_strict_policy(raw))
    if policy['release_sha256'] != expected_release_sha256:
        raise ValueError('OWNER_PIN_ACTIVE_RELEASE_MISMATCH')
    if pwd.getpwnam(CALLBACK_USER).pw_uid != CALLBACK_UID:
        raise ValueError('OWNER_PIN_CALLBACK_NSS_MISMATCH')
    for path, expected in ((policy['python_exe'], policy['python_sha256']),
                           (policy['script'], policy['script_sha256'])):
        if _root_file_digest(path)[0] != expected:
            raise ValueError('OWNER_PIN_PROTECTED_HASH_MISMATCH')
    unit_raw, unused = _read_protected(policy['unit_file'])
    if hashlib.sha256(unit_raw).hexdigest() != policy['unit_sha256']:
        raise ValueError('OWNER_PIN_UNIT_HASH_MISMATCH')
    _validate_unit(unit_raw, policy['argv'])
    return OwnerProcessVerifier(policy, binding_path, hashlib.sha256(raw).hexdigest(),
                                binding_identity, proc_root)


class OwnerProcessVerifier(object):
    """Callable(peer_pid, peer_uid) for the ledger's Owner mutation gate.

    Construct via load_owner_process_verifier. Policy is copied, never inferred
    from a caller request. The current pin inode/hash is rechecked on each call.
    """
    def __init__(self, policy, binding_path, binding_sha256, binding_identity, proc_root):
        self._policy = _validate_policy(policy)
        self._binding_path = binding_path
        self._binding_sha256 = binding_sha256
        self._binding_identity = binding_identity
        self._proc_root = proc_root

    def __call__(self, peer_pid, peer_uid):
        p, root = self._policy, self._proc_root
        if (type(peer_pid) is not int or peer_pid < 1 or type(peer_uid) is not int
                or peer_uid != p['callback_uid']):
            return False
        try:
            pin_raw, pin_identity = _read_protected(self._binding_path)
            if (hashlib.sha256(pin_raw).hexdigest() != self._binding_sha256
                    or pin_identity != self._binding_identity):
                return False
            starttime = native._proc_starttime(root, peer_pid)
            before = native._status(native._proc_bytes(root, peer_pid, 'status'))
            uids = before.get('Uid', '').split()
            parent = int(before.get('PPid', '0'))
            if len(uids) != 4 or any(int(uid) != peer_uid for uid in uids) or parent < 1:
                return False
            exe_digest, exe_file = native._proc_exe_sha256(root, peer_pid, p['python_exe'], 0)
            if exe_digest != p['python_sha256']:
                return False
            cmdline = native._proc_bytes(root, peer_pid, 'cmdline')
            expected = b'\0'.join(arg.encode('utf-8') for arg in p['argv']) + b'\0'
            if cmdline != expected:
                return False
            cgroup = native._proc_bytes(root, peer_pid, 'cgroup', 131072)
            if not _callback_cgroup(cgroup, p['cgroup']):
                return False
            file_checks = []
            for path, expected_hash in ((p['script'], p['script_sha256']),
                                        (p['unit_file'], p['unit_sha256'])):
                observed, file_id = _root_file_digest(path)
                if observed != expected_hash:
                    return False
                file_checks.append((path, file_id))
            after = native._status(native._proc_bytes(root, peer_pid, 'status'))
            if (after.get('Uid', '').split() != uids
                    or int(after.get('PPid', '0')) != parent
                    or native._proc_bytes(root, peer_pid, 'cmdline') != cmdline
                    or native._proc_bytes(root, peer_pid, 'cgroup', 131072) != cgroup
                    or native._proc_exe_file_identity(root, peer_pid, p['python_exe']) != exe_file
                    or any(_root_file_identity(path) != file_id for path, file_id in file_checks)
                    or _root_file_identity(self._binding_path) != self._binding_identity
                    or native._proc_starttime(root, peer_pid) != starttime):
                return False
            return True
        except (IOError, OSError, ValueError, KeyError, UnicodeError, TypeError, AttributeError):
            return False
