"""Pinned root-manager endpoint authentication. Python 3.6, fail closed.

Trusts approved root/systemd descriptor delivery, not an asserted acceptor PID.
No runtime /proc/PID/exe access or capability is required. The creator's image
was measured when the root-protected policy was approved; runtime checks its
protected file, boot/lifetime/IDs/cgroup. Trusted root exec/reexec is explicit.
"""
import errno
import hashlib
import json
import math
import os
import re
import selectors
import signal
import stat
import struct
import subprocess
import time

POLICY_PATH = '/etc/xuanjun-development/p2-ledger-server-identity.json'
SOCKET_PATH = '/run/xuanjun-development/ledger.sock'
CONFIG_PATH = '/etc/xuanjun-development/dispatcher.json'
ACTIVATION_ROOT = '/var/lib/xuanjun-development/activation/'
SOCKET_UNIT = 'xuanjun-ledger.socket'
SERVICE_UNIT = 'xuanjun-ledger.service'
COMMON = ('Id', 'LoadState', 'NeedDaemonReload', 'FragmentPath', 'DropInPaths')
UNIT_PROPERTIES = {
    SOCKET_UNIT: COMMON + ('Listen', 'Accept', 'Triggers', 'SocketUser',
                          'SocketGroup', 'SocketMode', 'DirectoryMode', 'RemoveOnStop'),
    SERVICE_UNIT: COMMON + ('User', 'Group', 'ExecStart', 'WorkingDirectory', 'TriggeredBy')}
DYNAMIC = {SOCKET_UNIT: ('ActiveState', 'SubState'),
           SERVICE_UNIT: ('ActiveState', 'SubState', 'MainPID', 'InvocationID')}
HEX = re.compile(r'^[0-9a-f]{64}$')
BOOT = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
POLICY_KEYS = {'schema', 'trust_model', 'exclusive_delivery_reviewed', 'activation_binding',
               'creator', 'endpoint', 'files', 'units'}
CREATOR_KEYS = {'pid', 'uid', 'gid', 'exe', 'cgroup_sha256',
                'pid_namespace_role', 'topology_evidence_sha256'}
ENDPOINT_KEYS = {'path', 'uid', 'gid', 'mode'}
BINDING_KEYS = {'release_sha256', 'binary_sha256', 'ledger_uuid', 'generation',
                'epoch', 'instance', 'db_path', 'ledger_socket'}


def _fail(reason):
    raise ValueError('LEDGER_SERVER_PIN_' + reason)


def _owned_command_signal(process):
    """Keep a live/unreaped direct child's PID pinned until group signalling."""
    if process.returncode is not None: return False
    lock = getattr(process, '_waitpid_lock', None)
    if lock is None or not lock.acquire(False): return False
    try:
        if process.returncode is not None: return False
        row = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if row is not None and row.si_pid != process.pid: return False
        if os.getpgid(process.pid) != process.pid or os.getsid(process.pid) != process.pid:
            return False
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        return True
    except ChildProcessError:
        return False
    finally:
        lock.release()


def _owned_command_reap(process, deadline):
    """Nonblocking wait ownership and WNOHANG only, including expired budgets."""
    while True:
        if process.returncode is not None: return True
        lock = getattr(process, '_waitpid_lock', None)
        if lock is not None and lock.acquire(False):
            try:
                if process.returncode is not None: return True
                pid, status = os.waitpid(process.pid, os.WNOHANG)
                if pid == process.pid:
                    if os.WIFEXITED(status): process.returncode = os.WEXITSTATUS(status)
                    elif os.WIFSIGNALED(status): process.returncode = -os.WTERMSIG(status)
                    else: _fail('COMMAND_EXIT_STATUS')
                    return True
                if pid != 0: _fail('COMMAND_CHILD_IDENTITY')
            except ChildProcessError:
                return False
            finally:
                lock.release()
        remaining = deadline - time.monotonic()
        if remaining <= 0: return False
        time.sleep(min(remaining, 0.005))


def _owned_command_cleanup(process, selector, deadline):
    failures, interrupted = [], []
    def attempt(label, action):
        try:
            if action() is False: failures.append(label)
        except BaseException as error:
            failures.append(label)
            if isinstance(error, (KeyboardInterrupt, SystemExit)): interrupted.append(error)
    attempt('signal', lambda: _owned_command_signal(process))
    if selector is not None: attempt('selector_close', selector.close)
    for name in ('stdout', 'stderr'):
        stream = getattr(process, name, None)
        if stream is not None: attempt(name + '_close', stream.close)
    attempt('reap', lambda: _owned_command_reap(process, deadline))
    if interrupted: raise interrupted[0]
    if failures: _fail('COMMAND_CLEANUP_UNKNOWN')


def _bounded_owned_command(argv, environment, timeout, maximum=32768):
    """Private shared runtime primitive; no command retries or authority checks.

    Callers supply their already-authorized exact command. One wall budget covers
    spawn, both finite streams, exit and cleanup. Exclusive child wait ownership
    is required; no external SIGCHLD/raw waitpid reaper is supported. Synchronous
    kernel stalls and suspension are not hard real-time guarantees.
    """
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or
            not 0 < timeout <= 30 or type(maximum) is not int or
            not 0 < maximum <= 1048576): _fail('COMMAND_BOUNDS')
    if not all(hasattr(os, name) for name in
            ('waitid', 'P_PID', 'WEXITED', 'WNOHANG', 'WNOWAIT', 'set_blocking')):
        _fail('COMMAND_PLATFORM')
    deadline = time.monotonic() + timeout
    work_end = deadline - min(0.2, timeout / 5.0)
    process = selector = failure = cleanup_failure = None
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(environment),
            close_fds=True, bufsize=0, cwd='/', start_new_session=True, shell=False)
        if time.monotonic() >= work_end: _fail('COMMAND_DEADLINE')
        selector = selectors.DefaultSelector()
        for name in streams:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = work_end - time.monotonic()
            if remaining <= 0: _fail('COMMAND_DEADLINE')
            for key, unused in selector.select(remaining):
                try: part = os.read(key.fd, min(65536, maximum + 1 - len(streams[key.data])))
                except BlockingIOError: continue
                if not part: selector.unregister(key.fileobj)
                else:
                    streams[key.data].extend(part)
                    if len(streams[key.data]) > maximum: _fail('COMMAND_OUTPUT_BOUND')
        while True:
            remaining = work_end - time.monotonic()
            if remaining <= 0: _fail('COMMAND_DEADLINE')
            row = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if row is not None:
                if row.si_pid != process.pid: _fail('COMMAND_CHILD_IDENTITY')
                break
            time.sleep(min(remaining, 0.005))
    except BaseException as error:
        failure = error
    finally:
        if process is not None:
            try: _owned_command_cleanup(process, selector, deadline)
            except BaseException as error: cleanup_failure = error
    for error in (failure, cleanup_failure):
        if isinstance(error, (KeyboardInterrupt, SystemExit)): raise error
    if failure is not None:
        if cleanup_failure is not None: raise failure from cleanup_failure
        raise failure
    if cleanup_failure is not None: raise cleanup_failure
    if time.monotonic() > deadline: _fail('COMMAND_DEADLINE')
    if process.returncode != 0: _fail('COMMAND_FAILED')
    return bytes(streams['stdout'])


def _canonical(path):
    return (type(path) is str and path.startswith('/') and '\x00' not in path
            and len(path) <= 4096 and os.path.normpath(path) == path)


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value or key in ('__proto__', 'constructor', 'prototype'):
                _fail('JSON_KEYS')
            value[key] = item
        return value
    def constant(unused): _fail('JSON_NONFINITE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _unit_path(path, unit):
    prefix = '/etc/systemd/system/' + unit
    return (path == prefix or (path.startswith(prefix + '.d/') and
        re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf', path[len(prefix) + 3:])))


def expected_exec_start(release):
    return ('path=/usr/bin/python3;argv[]=/usr/bin/python3 ' + release +
            '/ledger_service.py --config ' + CONFIG_PATH + ';ignore_errors=no')


def normalize_exec_start(raw):
    # systemctl serializes transient PID/timestamps alongside the immutable
    # command. Strip only this known runtime suffix; reject multiple/unknown
    # command forms rather than treating arbitrary output as a configured argv.
    pattern = (r'\{ path=([^;\n]+?) ; argv\[\]=([^;\n]+?) ; ignore_errors=(yes|no) ; '
               r'start_time=\[[^\]\n]*\] ; stop_time=\[[^\]\n]*\] ; pid=[0-9]+ ; '
               r'code=[A-Za-z()]+ ; status=[-0-9A-Za-z/]+ \}')
    match = re.fullmatch(pattern, raw)
    if not match: _fail('EXEC_START_FORMAT')
    return 'path=' + match.group(1) + ';argv[]=' + match.group(2) + ';ignore_errors=' + match.group(3)


def validate_policy(value):
    from activation_control import ActivationStore
    if (type(value) is not dict or set(value) != POLICY_KEYS or type(value['schema']) is not int
            or value['schema'] != 2 or value['trust_model'] != 'ROOT_MANAGER_DELIVERY_V1'
            or value['exclusive_delivery_reviewed'] is not True): _fail('EXACT_POLICY_REQUIRED')
    binding = value['activation_binding']
    if type(binding) is not dict or set(binding) != BINDING_KEYS: _fail('ACTIVATION_BINDING')
    # The aggregate config hash may include this policy. Pin public unit/image
    # bytes, trust existing root ACTIVE configuration authority, and avoid a
    # recursive hash. Private dispatcher contents are never read; full descriptor
    # (including config_sha256) must remain identical throughout each session.
    active = ActivationStore.validate(dict(binding, schema=1, state='ACTIVE', config_sha256='0' * 64))
    if active['ledger_socket'] != SOCKET_PATH: _fail('ACTIVE_BINDING_REQUIRED')
    creator = value['creator']
    if type(creator) is not dict or set(creator) != CREATOR_KEYS: _fail('CREATOR_FIELDS')
    for field in ('pid', 'uid', 'gid'):
        minimum = 1 if field == 'pid' else 0
        if type(creator[field]) is not int or not minimum <= creator[field] < 2**63: _fail('CREATOR_INTEGER')
    # Explicit values are mandatory; zero UID is a constraint, never a default.
    if (creator['pid'] != 1 or creator['uid'] != 0 or not _canonical(creator['exe'])
            or creator['pid_namespace_role'] != 'SYSTEM_INIT_SHARED_WITH_CLIENTS'
            or not isinstance(creator['topology_evidence_sha256'], str)
            or not HEX.fullmatch(creator['topology_evidence_sha256'])): _fail('MEASURED_INIT_MANAGER_REQUIRED')
    if creator['exe'] not in ('/usr/lib/systemd/systemd', '/lib/systemd/systemd'):
        _fail('MANAGER_IMAGE_PATH')
    if not isinstance(creator['cgroup_sha256'], str) or not HEX.fullmatch(creator['cgroup_sha256']):
        _fail('CREATOR_CGROUP')
    endpoint = value['endpoint']
    if (type(endpoint) is not dict or set(endpoint) != ENDPOINT_KEYS or endpoint['path'] != SOCKET_PATH
            or type(endpoint['mode']) is not int or endpoint['mode'] != 0o660): _fail('ENDPOINT_FIELDS')
    for field in ('uid', 'gid'):
        if type(endpoint[field]) is not int or endpoint[field] < 0:
            _fail('ENDPOINT_INTEGER')
    units, files = value['units'], value['files']
    if type(units) is not dict or set(units) != set(UNIT_PROPERTIES) or type(files) is not dict:
        _fail('UNITS_FILES')
    release = '/opt/xuanjun-control-releases/integration-' + active['release_sha256'][:16] + '/stage1'
    needed = {release + '/ledger_service.py', '/usr/bin/systemctl', creator['exe']}
    for unit, fields in UNIT_PROPERTIES.items():
        item = units[unit]
        if type(item) is not dict or set(item) != set(fields): _fail('UNIT_PROPERTIES')
        if any(type(v) is not str or len(v) > 8192 or '\n' in v or '[unprintable]' in v
               for v in item.values()): _fail('UNIT_VALUE')
        if (item['Id'] != unit or item['LoadState'] != 'loaded' or item['NeedDaemonReload'] != 'no'
                or item['FragmentPath'] != '/etc/systemd/system/' + unit): _fail('UNIT_LOADED_BINDING')
        paths = [item['FragmentPath']] + item['DropInPaths'].split()
        if len(paths) > 9 or len(paths) != len(set(paths)) or any(not _unit_path(p, unit) for p in paths):
            _fail('UNIT_FILE_PATHS')
        needed.update(paths)
    socket_unit = units[SOCKET_UNIT]
    if any(socket_unit[key] != expected for key, expected in {
            'Listen': SOCKET_PATH + ' (Stream)', 'Accept': 'no', 'Triggers': SERVICE_UNIT,
            'SocketUser': 'xuanjun-dispatcher', 'SocketGroup': 'xuanjun-ledger-client',
            'SocketMode': '0660', 'DirectoryMode': '0711', 'RemoveOnStop': 'yes'}.items()):
        _fail('SOCKET_UNIT_BINDING')
    service = units[SERVICE_UNIT]
    if (service['User'] != 'xuanjun-dispatcher' or service['Group'] != 'xuanjun-control-db'
            or service['TriggeredBy'] != SOCKET_UNIT or service['WorkingDirectory'] != release
            or service['ExecStart'] != expected_exec_start(release)): _fail('SERVICE_UNIT_BINDING')
    if set(files) != needed or any(not isinstance(v, str) or not HEX.fullmatch(v) for v in files.values()):
        _fail('EXACT_FILE_PINS')
    # Defensive deep copy: caller mutations never change an admitted policy.
    return _json(json.dumps(value, sort_keys=True, allow_nan=False).encode('utf-8'))


class OSBackend(object):
    """Fixed bounded reads only. No service starts or cross-UID proc exe opens."""
    def acl(self, path, deadline):
        deadline.check()
        try: raw = os.getxattr(path, 'system.posix_acl_access', follow_symlinks=False)
        except OSError as error:
            if error.errno == errno.ENODATA: return b''
            raise
        if (len(raw) < 4 or len(raw) > 1028 or (len(raw)-4) % 8
                or struct.unpack('<I', raw[:4])[0] != 2): _fail('ACL_FORMAT')
        deadline.check()
        return raw

    def chain(self, path, deadline):
        if not _canonical(path) or os.path.realpath(path) != path: _fail('CANONICAL_PATH')
        result, parent = [], os.path.dirname(path)
        while True:
            deadline.check(); info = os.lstat(parent)
            # Linux ACL effective group permissions are reflected by mode's mask.
            # We also read/hash ACLs, so unreadable or raced ACL evidence rejects.
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                _fail('ROOT_PROTECTED_ANCESTRY')
            acl = self.acl(parent, deadline)
            result.append((parent, _identity(info)[:5], _digest(acl)))
            if parent == '/': break
            parent = os.path.dirname(parent)
        deadline.check()
        return tuple(result)

    def read(self, path, maximum, deadline, protected=False):
        before_chain = self.chain(path, deadline) if protected else None
        deadline.check()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0))
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum: _fail('FILE_TYPE_SIZE')
            if protected and (before.st_uid != 0 or before.st_mode & 0o022 or before.st_nlink != 1):
                _fail('ROOT_FILE_REQUIRED')
            raw = bytearray()
            while len(raw) <= maximum:
                deadline.check(); part = os.read(fd, min(65536, maximum + 1 - len(raw)))
                if not part: break
                raw.extend(part)
            if len(raw) > maximum: _fail('FILE_SIZE')
            if _identity(before) != _identity(os.fstat(fd)): _fail('FILE_RACE')
            if protected and len(raw) != before.st_size: _fail('FILE_READ_SIZE')
            if protected:
                self.acl(path, deadline)
                if before_chain != self.chain(path, deadline) or _identity(before) != _identity(os.lstat(path)):
                    _fail('FILE_PATH_RACE')
            deadline.check(); return bytes(raw), _identity(before)
        finally: os.close(fd)

    def private_config_metadata(self, deadline):
        # Never open/hash private dispatcher bytes in dashboard/native clients.
        chain = self.chain(CONFIG_PATH, deadline)
        info = os.lstat(CONFIG_PATH)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or info.st_nlink != 1 or info.st_size > 65536): _fail('PRIVATE_CONFIG_PROTECTION')
        acl = self.acl(CONFIG_PATH, deadline)
        if _identity(info) != _identity(os.lstat(CONFIG_PATH)) or chain != self.chain(CONFIG_PATH, deadline):
            _fail('PRIVATE_CONFIG_RACE')
        deadline.check()
        return _identity(info), _digest(acl), chain

    def endpoint(self, deadline):
        chain = self.chain(SOCKET_PATH, deadline)
        info = os.lstat(SOCKET_PATH)
        if not stat.S_ISSOCK(info.st_mode): _fail('ENDPOINT_SOCKET_REQUIRED')
        acl = self.acl(SOCKET_PATH, deadline)
        if _identity(info) != _identity(os.lstat(SOCKET_PATH)) or chain != self.chain(SOCKET_PATH, deadline):
            _fail('ENDPOINT_RACE')
        deadline.check()
        return {'path': SOCKET_PATH, 'dev': info.st_dev, 'inode': info.st_ino,
                'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode),
                'acl_sha256': _digest(acl)}, chain

    def creator(self, creator, deadline):
        prefix = '/proc/' + str(creator['pid']) + '/'
        boot = self.read('/proc/sys/kernel/random/boot_id', 64, deadline)[0].decode('ascii').strip()
        before = self.read(prefix + 'stat', 8192, deadline)[0]
        raw = self.read(prefix + 'status', 65536, deadline)[0]
        cgroup = self.read(prefix + 'cgroup', 8192, deadline)[0]
        after = self.read(prefix + 'stat', 8192, deadline)[0]
        def start(value):
            close = value.rfind(b')')
            if close < 0 or value.split(b' ', 1)[0] != str(creator['pid']).encode(): _fail('PROC_STAT')
            fields = value[close + 2:].split()
            if len(fields) < 20 or not fields[19].isdigit(): _fail('PROC_STAT')
            return int(fields[19])
        first, last = start(before), start(after)
        if first != last: _fail('CREATOR_RESTART')
        ids = {}
        for line in raw.decode('ascii').splitlines():
            key, separator, value = line.partition(':')
            if key in ('Uid', 'Gid'):
                if key in ids or not re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s+\d+\s*', value): _fail('PROC_IDS')
                ids[key] = tuple(int(item) for item in value.split())
        if ids != {'Uid': (creator['uid'],) * 4, 'Gid': (creator['gid'],) * 4}: _fail('CREATOR_IDS')
        return {'boot_id': boot, 'starttime': first, 'cgroup_sha256': _digest(cgroup)}

    def manager_channel(self, deadline):
        # v239 may fall back from private manager transport to system D-Bus for
        # root. Protect BOTH possible channels, never assume which succeeded.
        paths = ['/run/dbus/system_bus_socket']
        if os.geteuid() == 0: paths.append('/run/systemd/private')
        observed = []
        for path in paths:
            chain = self.chain(path, deadline)
            info = os.lstat(path)
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0: _fail('MANAGER_CHANNEL')
            observed.append((path, _identity(info)[:6], chain))
        deadline.check()
        return tuple(observed)

    def unit(self, unit, deadline):
        if unit not in UNIT_PROPERTIES: _fail('FIXED_UNIT_REQUIRED')
        channel = self.manager_channel(deadline)
        properties = UNIT_PROPERTIES[unit] + DYNAMIC[unit]
        # No inherited DBUS address, remote host, pager, HOME or PATH override.
        argv = ['/usr/bin/systemctl', '--system', 'show', '--no-pager',
                '--property=' + ','.join(properties), unit]
        raw = _bounded_owned_command(argv, {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
            'SYSTEMD_PAGER': ''}, min(1.0, deadline.check()), 32768)
        value = {}
        for line in raw.decode('utf-8').splitlines():
            key, separator, item = line.partition('=')
            if not separator or key not in properties or key in value or len(item) > 8192:
                _fail('MANAGER_PROPERTIES')
            value[key] = normalize_exec_start(item) if key == 'ExecStart' else item
        if set(value) != set(properties): _fail('MANAGER_PROPERTIES_MISSING')
        if self.manager_channel(deadline) != channel: _fail('MANAGER_CHANNEL_CHANGED')
        deadline.check(); return value


def canonical_activation():
    from activation_control import ActivationStore
    return ActivationStore(ACTIVATION_ROOT + 'active.json', ACTIVATION_ROOT + 'epochs.jsonl',
                           ACTIVATION_ROOT + 'activation.lock')


def load_server_verifier(activation=None, policy_path=POLICY_PATH, _backend=None):
    """Mandatory fixed protected policy; no automatic pin creation or guessing.

    _backend is an offline test seam. Runtime entrypoints never supply it.
    Runtime paths remain fixed; a caller-supplied alternative policy is rejected.
    """
    if policy_path != POLICY_PATH: _fail('FIXED_POLICY_REQUIRED')
    from ledger_read_transport import MonotonicIODeadline
    backend, deadline = _backend or OSBackend(), MonotonicIODeadline(5)
    raw, identity = backend.read(POLICY_PATH, 65536, deadline, protected=True)
    if stat.S_IMODE(identity[2]) != 0o644 or identity[3:6] != (0, 0, 1): _fail('ROOT_ROOT_0644_POLICY')
    policy = validate_policy(_json(raw))
    deadline.check()
    return RootManagerVerifier(policy, _digest(raw), identity, activation or canonical_activation(), backend)


def _delivery_phase(dynamic):
    """Only the two paired Accept=no states in the reviewed systemd lifecycle.

    listening is a pre-activation state, not proof of a live response sender.
    A running socket must be associated with the already-pinned live service.
    Transitional/inconsistent observations fail closed; no request is retried.
    """
    listener, service = dynamic[SOCKET_UNIT], dynamic[SERVICE_UNIT]
    if listener['ActiveState'] != 'active': _fail('LISTENER_NOT_ACTIVE')
    if (service['ActiveState'], service['SubState']) == ('inactive', 'dead'):
        if (service['MainPID'] != '0' or type(service['InvocationID']) is not str
                or (service['InvocationID'] != '' and
                    not re.fullmatch('[0-9a-f]{32}', service['InvocationID']))):
            _fail('SERVICE_NOT_ACTIVE')
        if listener['SubState'] != 'listening': _fail('SOCKET_SERVICE_STATE')
        return 'IDLE'
    if (service['ActiveState'] != 'active' or service['SubState'] != 'running'
            or type(service['MainPID']) is not str
            or not re.fullmatch('[1-9][0-9]*', service['MainPID'])
            or type(service['InvocationID']) is not str
            or not re.fullmatch('[0-9a-f]{32}', service['InvocationID'])):
        _fail('SERVICE_NOT_ACTIVE')
    if listener['SubState'] != 'running': _fail('SOCKET_SERVICE_STATE')
    return 'RUNNING'


def _delivery_transition(before, after):
    """One-way activation; an observed running invocation cannot be replaced."""
    prior, current = _delivery_phase(before), _delivery_phase(after)
    if prior == 'RUNNING' or current == 'IDLE':
        if before[SERVICE_UNIT] != after[SERVICE_UNIT]:
            _fail('SERVICE_RESTART_DURING_REQUEST')


class RootManagerVerifier(object):
    def __init__(self, policy, policy_sha256, policy_identity, activation, backend):
        self.policy = validate_policy(policy)
        self.policy_sha256, self.policy_identity = policy_sha256, policy_identity
        self.activation, self.backend = activation, backend

    def __call__(self, *unused):
        _fail('LIFECYCLE_SESSION_REQUIRED')

    def session(self, path, deadline):
        if path != SOCKET_PATH: _fail('FIXED_ENDPOINT_REQUIRED')
        return RootManagerSession(self, deadline)

    def checkpoint(self, deadline):
        p, b = self.policy, self.backend
        raw, identity = b.read(POLICY_PATH, 65536, deadline, protected=True)
        if _digest(raw) != self.policy_sha256 or identity != self.policy_identity: _fail('POLICY_CHANGED')
        endpoint, chain = b.endpoint(deadline)
        if ({key: endpoint[key] for key in ENDPOINT_KEYS} != p['endpoint']
                or endpoint['acl_sha256'] != _digest(b'')):
            _fail('ENDPOINT_CHANGED')
        # v2 deliberately admits only the ordinary mode ACL. A newly introduced
        # extended ACL requires a separately reviewed schema, never an inference.
        active = self.activation.read(require_active=True)
        deadline.check()
        from activation_control import ActivationStore, ActivationError
        try:
            ActivationStore.validate(active)
        except ActivationError:
            _fail('ACTIVATION_CHANGED')
        if (type(active['schema']) is not int or active['state'] != 'ACTIVE'
                or json.dumps({key: active[key] for key in BINDING_KEYS}, sort_keys=True)
                != json.dumps(p['activation_binding'], sort_keys=True)):
            _fail('ACTIVATION_CHANGED')
        creator = b.creator(p['creator'], deadline)
        if (type(creator) is not dict or set(creator) != {'boot_id', 'starttime', 'cgroup_sha256'}
                or not isinstance(creator['boot_id'], str) or not BOOT.fullmatch(creator['boot_id'])
                or type(creator['starttime']) is not int or creator['starttime'] < 0
                or creator['cgroup_sha256'] != p['creator']['cgroup_sha256']):
            _fail('CREATOR_LIFETIME_CHANGED')
        # Fresh boot/start/inode/ACL observations are session-bound, not stored
        # in the immutable policy. PID1 cannot be reused while that boot survives;
        # the approved topology evidence must establish shared init namespace.
        return endpoint, chain, creator, json.dumps(active, sort_keys=True), b.private_config_metadata(deadline)

    def snapshot(self, deadline):
        p, b = self.policy, self.backend
        before = self.checkpoint(deadline)
        for path, digest in sorted(p['files'].items()):
            maximum = 32 * 1024 * 1024 if path in (p['creator']['exe'], '/usr/bin/systemctl') else 262144
            content, unused = b.read(path, maximum, deadline, protected=True)
            if _digest(content) != digest: _fail('PROTECTED_FILE_CHANGED')
        dynamic = {}
        for unit, expected in p['units'].items():
            observed = b.unit(unit, deadline)
            if {key: observed[key] for key in UNIT_PROPERTIES[unit]} != expected: _fail('LOADED_UNIT_CHANGED')
            dynamic[unit] = {key: observed[key] for key in DYNAMIC[unit]}
        _delivery_phase(dynamic)
        if before != self.checkpoint(deadline): _fail('SNAPSHOT_CHANGED')
        deadline.check()
        return before + (dynamic,)


class RootManagerSession(object):
    def __init__(self, verifier, deadline):
        self.verifier, self.deadline = verifier, deadline
        self.before = verifier.snapshot(deadline)
        self.peer = None
        self.connected = None

    def verify(self, credentials):
        p = self.verifier.policy['creator']
        if (any(type(item) is not int for item in credentials)
                or tuple(credentials) != (p['pid'], p['uid'], p['gid'])): _fail('PEER_CREDENTIALS')
        # Bind a service invocation observed after connect too. Socket activation
        # may have occurred since the initial idle snapshot; any later restart
        # must be rejected even when that initial snapshot was inactive.
        check = self.verifier.snapshot(self.deadline)
        if self.before[:5] != check[:5]: _fail('CONNECT_RACE')
        _delivery_transition(self.before[5], check[5])
        self.connected = check
        self.peer = tuple(credentials)
        return True

    def finish(self, credentials):
        if (self.peer is None or any(type(item) is not int for item in credentials)
                or tuple(credentials) != self.peer): _fail('PEER_CHANGED')
        after = self.verifier.snapshot(self.deadline)
        if self.connected[:5] != after[:5]: _fail('RESPONSE_RACE')
        if _delivery_phase(after[5]) != 'RUNNING': _fail('SERVICE_NOT_ACTIVE')
        _delivery_transition(self.connected[5], after[5])
        return True
