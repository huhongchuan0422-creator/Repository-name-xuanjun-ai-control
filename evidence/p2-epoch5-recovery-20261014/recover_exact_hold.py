"""One separately reviewed recovery of the frozen P2 QUIESCED failure.

verify-only reads host evidence. resume requires a NEW independent approval
bound to this file and the exact verification snapshot; old approval is never
treated as a second install grant. No receipt deletion, restaging, NSS replay,
release overwrite, historical notification replay or legacy writer restart.
"""
import argparse
import hashlib
import importlib.util
import json
import io
import marshal
import os
import re
import socket
import stat
import sys
import struct
import tempfile
import types
import urllib.request

BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
TX = 'c529c379-9341-4510-8384-fc6be1e412e5'
CAND = BASE + '/complete-install-candidate-38503014520'
DIRECTORY = BASE + '/legacy-isolation-' + TX
PLAN_SHA = 'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'
MANIFEST_SHA = '9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
SOURCE = 'd75b5b6deea22b7e66569096f72f81c639516133'
TREE = '60e0e41ac84ca17db96b5057ff9b2a341a4ec1f3'
DB_SHA = 'a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
MARKER = 'CHATGPT_NATIVE_TASK5_EXACT_HOLD_RECOVERY_ACCEPTANCE\n'
RUNNER = 'actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.iZd7oeikknn1z21sq6ji6zZ.service'

RETAINED_CACHE_HASHES = {
    'stage1/__pycache__/activation_control.cpython-36.pyc': 'c29a1b0253fe6c7a2034f280cc7958b5c4d098ede58f44bc10c2fc0035e48632',
    'stage1/__pycache__/codex_worker.cpython-36.pyc': '74c832ab2c24722dd69c980a6592b2870505f2c0d38ddcb11b02c76fbbd0f709',
    'stage1/__pycache__/dependency_evidence_view.cpython-36.pyc': '50fc476ec33f2b2eee8f0344877ff3f8ea0cad0627cec16d9702ff81139f8b1b',
    'stage1/__pycache__/development_loop.cpython-36.pyc': '9c59dff852906f1bdfccd8f70eeebc81ae612af867b3cd9e80f427f4705eec0f',
    'stage1/__pycache__/development_pipeline.cpython-36.pyc': 'cf93ef0b6f5f2edcdddb0af4a5f90909072136dec629332b2c8b4176c1315758',
    'stage1/__pycache__/development_service.cpython-36.pyc': '34d3e4471bc09d44d13f1936b0ae24487e0a1f570c22c416fb5e8f865daa5c91',
    'stage1/__pycache__/execution_ledger.cpython-36.pyc': 'b2cca1d331ed5d8c909318344522c373ad1d9dea4ac212a78f2daac09970c555',
    'stage1/__pycache__/native_child_adapter.cpython-36.pyc': 'd5381afcb72307cabc29e775b18801e6a724fdf950c8b3c2eaa5c01d7d349c4b',
    'stage1/__pycache__/native_peer_identity.cpython-36.pyc': '6c2f9e047e30f53ee70d506ea41628b138b49d3c36463db09cdf605f06d7bd13',
    'stage1/__pycache__/native_pipeline_runtime.cpython-36.pyc': '518a3e1a0733bfe1e832bc480a7aa2ae9c5eef46e4d1529efe48f33a2128edf5',
    'stage1/__pycache__/run_usage_projection.cpython-36.pyc': 'dff62a81e062a09d16345552e45d2db4eae01e135ca6cc3d2a8120216c4c5542',
    'stage1/__pycache__/task_cost_projection.cpython-36.pyc': '2674e1de7e3ad1ad270ccfa50346a886942f0e621154cf719f3ff15b687216b9',
    'stage1/__pycache__/uk_owner_callback_core.cpython-36.pyc': '898b3fcb3709eb0df456bfe23202077d54e86075aeef8840e738e83cdd95c88a',
}
RETAINED_SIDECARS = {'-wal': (0, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'), '-shm': (32768, 'fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb')}


def require(value, code):
    if not value:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, private=False, maximum=16777216, owner_uid=0):
    require(os.path.realpath(path) == path, 'RECOVERY_PATH_ALIAS')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        data = stream.read(maximum + 1)
        end = os.fstat(stream.fileno())
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
            len(data) <= maximum and info.st_uid == owner_uid and
            not info.st_mode & 0o022, 'RECOVERY_FILE_AUTHORITY')
    require((info.st_size, info.st_mtime_ns) == (end.st_size, end.st_mtime_ns),
            'RECOVERY_FILE_CHANGED_DURING_READ')
    if private:
        require(info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                'RECOVERY_PRIVATE_AUTHORITY')
    return data, info


def load_renderer(root, manifest):
    path = root + '/scripts/uk-integration-install.py'
    data, unused = read(path)
    require(sha(data) == manifest['files']['scripts/uk-integration-install.py'],
            'RECOVERY_RENDERER_HASH')
    namespace = {'__name__': 'recovery_reviewed_renderer', '__file__': path}
    exec(compile(data, path, 'exec'), namespace)
    return namespace


def validate_release(root, release, manifest, manifest_sha, reader=read):
    """Verify frozen inputs AND deterministic identity-rendered release bytes."""
    renderer = load_renderer(root, manifest)
    payloads = {}
    for relative, wanted in sorted(manifest['files'].items()):
        require(not relative.startswith('/') and '..' not in relative.split('/'),
                'RECOVERY_MANIFEST_PATH')
        original, unused = reader(root + '/' + relative)
        require(sha(original) == wanted, 'RECOVERY_ORIGINAL_HASH')
        expected = renderer['render_identity_bytes'](relative, original, manifest_sha, manifest)
        installed, unused = reader(release + '/' + relative)
        require(installed == expected, 'RECOVERY_RELEASE_RENDERED_HASH')
        payloads[release + '/' + relative] = (original, expected)
    return payloads


def source_reader(payloads, original_reader):
    """Only provision's exact validated release source paths yield raw inputs.

    Target, backup, receipt and other reads always use the original reader.
    Recheck installed bytes before accepting the captured source. Caller must
    validate all release bytes under the install lock before constructing this.
    """
    def controlled(path, limit=1024 * 1024):
        observed, info = original_reader(path, limit)
        if path in payloads:
            value, expected = payloads[path]
            require(observed == expected, 'RECOVERY_SOURCE_CHANGED_AFTER_VERIFICATION')
            require(len(value) <= limit, 'RECOVERY_SOURCE_BOUND')
            return value, info
        return observed, info
    return controlled


def validate_hold(receipt, plan, active, cutover):
    require(receipt.get('schema') == 1 and receipt.get('transaction_id') == TX and
            receipt.get('stage') == 'HOLD' and receipt.get('failed_stage') == 'LEGACY_QUIESCED' and
            receipt.get('epoch') == 1 and receipt.get('error_type') == 'ValueError' and
            receipt.get('rollback_error_type') == 'ValueError' and
            receipt.get('rollback') == ['ACTIVATION_FENCED_EPOCH_2'] and
            receipt.get('legacy_writer_restarted') is False and
            receipt.get('oauth_copied') is False and receipt.get('new_paid_api_usage') == 'NONE' and
            receipt.get('recovery') == 'MANUAL_RECONCILIATION_REQUIRED_NO_RESTART' and
            receipt.get('plan_sha256') == sha(canonical(plan)) and
            receipt.get('release') == '/opt/xuanjun-control-releases/' + plan['runtime']['release_directory'],
            'RECOVERY_EXACT_HOLD_REQUIRED')
    expected = dict(plan['activation'])
    expected.pop('expected_epoch')
    expected.update(schema=1, state='PREPARED', epoch=2)
    require(active == expected, 'RECOVERY_EXACT_FENCED_IDENTITY')
    require(cutover.get('transaction_id') == TX and cutover.get('stage') == 'STAGED' and
            cutover.get('plan_sha256') == sha(canonical(plan['cutover'])) and
            cutover.get('source_replaced') is False and cutover.get('activation_executed') is False and
            cutover.get('task_replay') is False and
            receipt.get('cutover_receipt_sha256') == sha(canonical(cutover)),
            'RECOVERY_EXACT_STAGED_CUTOVER')


def verify_prerequisites(manager, plan):
    import grp
    import pwd
    data, unused = read(manager.path, private=True)
    receipt = json.loads(data.decode())
    require(receipt.get('schema') == 1 and receipt.get('plan_sha256') == sha(canonical(plan)) and
            receipt.get('restored') is not True and
            all(a.get('state') == 'DONE' for a in receipt.get('actions', [])),
            'RECOVERY_PREREQUISITE_JOURNAL')
    for name, gid in plan['groups'].items():
        group = grp.getgrnam(name)
        require(group.gr_gid == gid, 'RECOVERY_GROUP_IDENTITY')
        allowed = {'xuanjun-dispatcher', 'xuanjun-callback'} if name == 'xuanjun-control-db' else {name}
        require(set(group.gr_mem).issubset(allowed), 'RECOVERY_GROUP_MEMBERS')
    for name, value in plan['users'].items():
        user = pwd.getpwnam(name)
        require((user.pw_uid, user.pw_gid, user.pw_dir, user.pw_shell) ==
                (value['uid'], value['gid'], value['home'], '/sbin/nologin'), 'RECOVERY_USER_IDENTITY')
        require(set(os.getgrouplist(name, value['gid'])) ==
                {value['gid']} | {plan['groups'][g] for g in value['groups']},
                'RECOVERY_USER_MEMBERSHIP')
    for value in plan['directories']:
        manager.directory_matches(value)
    for value in plan['binaries']:
        data, info = read(value['target'], maximum=536870912)
        require(sha(data) == value['sha256'] and info.st_gid == 0 and
                stat.S_IMODE(info.st_mode) == 0o555, 'RECOVERY_BINARY_IDENTITY')
    return sha(read(manager.path, private=True)[0])


def validate_directories(root, retained_cache=False):
    for parent, dirs, files in os.walk(root, followlinks=False):
        info = os.lstat(parent)
        require(os.path.realpath(parent) == parent and stat.S_ISDIR(info.st_mode) and
                info.st_uid == 0 and not info.st_mode & 0o022, 'RECOVERY_DIRECTORY_AUTHORITY')
        require(not any(os.path.islink(parent + '/' + name) for name in dirs), 'RECOVERY_DIRECTORY_ALIAS')
        require(retained_cache or not any(name.endswith('.pyc') for name in files),
                'RECOVERY_BYTECODE_PRESENT')


def validate_file_inventory(root, allowed):
    observed = set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in files:
            path = parent + '/' + name
            relative = os.path.relpath(path, root)
            require(relative in allowed and stat.S_ISREG(os.lstat(path).st_mode),
                    'RECOVERY_UNCLASSIFIED_RELEASE_FILE')
            observed.add(relative)
    require(observed == set(allowed), 'RECOVERY_FILE_INVENTORY_INCOMPLETE')


def validate_release_metadata(release):
    executable = {'scripts/xj-root-broker-client', 'scripts/uk-owner-workbench-config.py'}
    for parent, dirs, files in os.walk(release, followlinks=False):
        info = os.lstat(parent)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0 and
                stat.S_IMODE(info.st_mode) == 0o555, 'RECOVERY_RELEASE_DIRECTORY_METADATA')
        for name in files:
            path = parent + '/' + name
            info = os.lstat(path)
            mode = 0o555 if os.path.relpath(path, release) in executable else 0o444
            require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0 and
                    info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == mode,
                    'RECOVERY_RELEASE_FILE_METADATA')


def code_identity(value):
    """Compare bytecode without executing it; include every Python 3.6 code field."""
    if isinstance(value, types.CodeType):
        names = ('co_argcount', 'co_kwonlyargcount', 'co_nlocals', 'co_stacksize',
                 'co_flags', 'co_code', 'co_consts', 'co_names', 'co_varnames',
                 'co_filename', 'co_name', 'co_firstlineno', 'co_lnotab',
                 'co_freevars', 'co_cellvars')
        return ('code', tuple((n, code_identity(getattr(value, n))) for n in names))
    if isinstance(value, tuple):
        return ('tuple', tuple(code_identity(v) for v in value))
    if isinstance(value, frozenset):
        return ('frozenset', frozenset(code_identity(v) for v in value))
    # repr distinguishes signed zero, NaN and values of different primitive types.
    return (type(value).__name__, repr(value))


def verify_cache_bytes(data, source, relative, source_info):
    require(sys.version_info[:2] == (3, 6) and sys.flags.optimize == 0,
            'RECOVERY_CACHE_REQUIRES_CPYTHON36_UNOPTIMIZED')
    require(len(data) >= 12 and data[:4] == importlib.util.MAGIC_NUMBER,
            'RECOVERY_CACHE_MAGIC')
    timestamp, size = struct.unpack('<II', data[4:12])
    require(size == len(source) and timestamp == int(source_info.st_mtime) & 0xffffffff,
            'RECOVERY_CACHE_SOURCE_METADATA')
    stream = io.BytesIO(data[12:])
    try:
        value = marshal.load(stream)
    except (EOFError, ValueError, TypeError):
        raise ValueError('RECOVERY_CACHE_MARSHAL')
    require(isinstance(value, types.CodeType) and stream.read() == b'',
            'RECOVERY_CACHE_CODE_BOUNDARY')
    suffix = '/' + relative
    filename = value.co_filename
    require(isinstance(filename, str) and filename.endswith(suffix),
            'RECOVERY_CACHE_SOURCE_FILENAME')
    staging = filename[:-len(suffix)]
    require(re.fullmatch(r'/opt/xuanjun-control-releases/\.integration-[0-9a-f]{16}', staging),
            'RECOVERY_CACHE_STAGING_IDENTITY')
    expected = compile(source, filename, 'exec', dont_inherit=True, optimize=0)
    require(code_identity(value) == code_identity(expected), 'RECOVERY_CACHE_SOURCE_CODE_MISMATCH')
    return staging


def validate_retained_caches(release, payloads):
    """Only the exact 13 observed smoke caches, each reproduced from verified source.

    No cache is imported, deleted, rewritten, or accepted by filename alone.
    This evidence is additional to (never a substitute for) all 102 source hashes.
    """
    observed = {}
    staging_ids = set()
    for parent, dirs, files in os.walk(release, followlinks=False):
        for name in files:
            if not name.endswith('.pyc'):
                continue
            path = parent + '/' + name
            relative = os.path.relpath(path, release)
            require(relative in RETAINED_CACHE_HASHES, 'RECOVERY_UNCLASSIFIED_CACHE')
            data, info = read(path)
            require(info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o444 and
                    sha(data) == RETAINED_CACHE_HASHES[relative], 'RECOVERY_CACHE_HASH_AUTHORITY')
            source_relative = 'stage1/' + name[:-len('.cpython-36.pyc')] + '.py'
            source_path = release + '/' + source_relative
            require(source_path in payloads, 'RECOVERY_CACHE_UNBOUND_SOURCE')
            source, source_info = read(source_path)
            require(source == payloads[source_path][1], 'RECOVERY_CACHE_SOURCE_DRIFT')
            staging_ids.add(verify_cache_bytes(data, source, source_relative, source_info))
            observed[relative] = {'sha256': sha(data), 'source_sha256': sha(source)}
    require(set(observed) == set(RETAINED_CACHE_HASHES) and len(staging_ids) == 1,
            'RECOVERY_CACHE_SET_MISMATCH')
    return observed


def database_file_set(path, owner_uid, retained_source=False):
    """Observe DB and sidecars without ever opening production SQLite."""
    data, info = read(path, owner_uid=owner_uid, maximum=67108864)
    evidence = {'database_sha256': sha(data), 'database_size': len(data), 'sidecars': {}}
    for suffix in ('-wal', '-shm', '-journal'):
        side = path + suffix
        if not os.path.lexists(side):
            evidence['sidecars'][suffix] = None
            continue
        require(retained_source and suffix in RETAINED_SIDECARS,
                'RECOVERY_DATABASE_SIDECAR')
        content, meta = read(side, owner_uid=owner_uid, maximum=65536)
        wanted_size, wanted_hash = RETAINED_SIDECARS[suffix]
        require(len(content) == wanted_size and sha(content) == wanted_hash and
                meta.st_gid == 1002 and stat.S_IMODE(meta.st_mode) == 0o644,
                'RECOVERY_RETAINED_SIDECAR_DRIFT')
        evidence['sidecars'][suffix] = {'sha256': sha(content), 'size': len(content)}
    if retained_source:
        require(evidence['database_sha256'] == DB_SHA and
                all(evidence['sidecars'][s] is not None for s in RETAINED_SIDECARS),
                'RECOVERY_RETAINED_DATABASE_SET')
    return evidence, data


def manifest_from_copy(data, manifest_function):
    """SQLite may create sidecars even on read-only opens: inspect a private copy."""
    with tempfile.TemporaryDirectory(prefix='xuanjun-recovery-db-inspection-') as directory:
        path = directory + '/snapshot.sqlite'
        with open(path, 'xb') as stream:
            stream.write(data)
        os.chmod(path, 0o600)
        result = manifest_function(path)
    require(result['sha256'] == sha(data) and result['size'] == len(data),
            'RECOVERY_DATABASE_INSPECTION_CHANGED_COPY')
    return result


def no_runner_or_old_worker():
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/' + pid + '/comm') as stream:
                name = stream.read(256).strip()
            require(not name.startswith(('Runner.Listener', 'Runner.Worker')), 'RECOVERY_RUNNER_PROCESS')
            with open('/proc/' + pid + '/status') as stream:
                status = stream.read(65537)
            uid = next(line.split()[1] for line in status.splitlines() if line.startswith('Uid:'))
            if uid == '1002':
                require(os.readlink('/proc/' + pid + '/exe') == '/usr/bin/ssh', 'RECOVERY_OLD_WORKER_PROCESS')
            if uid in ('1003', '1004', '1005', '1008'):
                raise ValueError('RECOVERY_RETAINED_ACCOUNT_HAS_PROCESS')
        except FileNotFoundError:
            raise ValueError('RECOVERY_PROCESS_SCAN_RACE')


def scan_fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def bounded_file_inventory(root, optional=False, cgroup=False):
    """FD-anchored, fail-closed collector. Never suppress traversal errors.

    Only ENOENT at an optional fixed path is admissible, after successfully
    listing its existing parent twice. Descendant ENOENT is always a race.
    All ancestor descriptors remain open and names/identities are rechecked.
    """
    require(root.startswith('/') and os.path.normpath(root) == root and root != '/',
            'RECOVERY_SCAN_PATH')
    held = []
    links = []
    count = [0]
    observed = {}
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    def same(left, right):
        require(scan_fingerprint(left) == scan_fingerprint(right), 'RECOVERY_SCAN_RACE')
    def metadata(parent, name):
        return os.stat(name, dir_fd=parent, follow_symlinks=False)
    def listing(fd):
        names = sorted(os.listdir(fd))  # Permission/race errors propagate.
        require(len(names) <= 8192, 'RECOVERY_SCAN_BOUND')
        return names
    def visit(fd, path, before, depth):
        count[0] += 1
        require(count[0] <= 8192 and depth <= 32, 'RECOVERY_SCAN_BOUND')
        same(before, os.fstat(fd))
        if stat.S_ISDIR(before.st_mode):
            names = listing(fd)
            if cgroup:
                require('cgroup.procs' in names, 'RECOVERY_CGROUP_PROCS_MISSING')
            for name in names:
                info = metadata(fd, name)
                require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),
                        'RECOVERY_SCAN_ENTRY_TYPE')
                require(info.st_dev == before.st_dev, 'RECOVERY_SCAN_MOUNT_CHANGE')
                if cgroup and stat.S_ISREG(info.st_mode) and name != 'cgroup.procs':
                    count[0] += 1
                    require(count[0] <= 8192, 'RECOVERY_SCAN_BOUND')
                    same(info, metadata(fd, name))
                    continue
                child_flags = flags | (os.O_DIRECTORY if stat.S_ISDIR(info.st_mode) else os.O_NONBLOCK)
                child = os.open(name, child_flags, dir_fd=fd)
                try:
                    visit(child, path + '/' + name, info, depth + 1)
                    same(info, metadata(fd, name))
                finally:
                    os.close(child)
            require(listing(fd) == names, 'RECOVERY_SCAN_ENTRIES_CHANGED')
        else:
            require(stat.S_ISREG(before.st_mode), 'RECOVERY_SCAN_ENTRY_TYPE')
            if not cgroup or os.path.basename(path) == 'cgroup.procs':
                chunks = []
                total = 0
                while True:
                    data = os.read(fd, min(65536, 1048577 - total))
                    if not data:
                        break
                    chunks.append(data); total += len(data)
                    require(total <= 1048576, 'RECOVERY_SCAN_FILE_BOUND')
                data = b''.join(chunks)
                if cgroup:
                    require(not data.strip(), 'RECOVERY_NOTIFIER_CGROUP_BUSY')
                observed[path] = sha(data)
        same(before, os.fstat(fd))
    try:
        current = os.open('/', flags | os.O_DIRECTORY)
        held.append(current)
        parts = root.strip('/').split('/')
        missing = None
        for index, name in enumerate(parts):
            try:
                info = metadata(current, name)
            except FileNotFoundError:
                require(optional, 'RECOVERY_SCAN_ROOT_MISSING')
                parent_before = os.fstat(current)
                require(name not in listing(current), 'RECOVERY_SCAN_ABSENCE_RACE')
                missing = (current, name, parent_before)
                break
            final = index == len(parts) - 1
            require(stat.S_ISDIR(info.st_mode) or
                    (final and not cgroup and stat.S_ISREG(info.st_mode)),
                    'RECOVERY_SCAN_ROOT_TYPE')
            child_flags = flags | (os.O_DIRECTORY if stat.S_ISDIR(info.st_mode) else os.O_NONBLOCK)
            child = os.open(name, child_flags, dir_fd=current)
            held.append(child)
            same(info, os.fstat(child))
            links.append((current, name, info, child))
            current = child
        if missing is None:
            visit(current, root, os.fstat(current), 0)
        else:
            parent, name, info = missing
            require(name not in listing(parent), 'RECOVERY_SCAN_ABSENCE_RACE')
            same(info, os.fstat(parent))
        for parent, name, info, fd in reversed(links):
            # Ancestor contents may change for unrelated services; identity/type
            # must remain bound. The scanned root/subtree gets full metadata checks.
            now = metadata(parent, name)
            require((now.st_dev, now.st_ino, now.st_mode, now.st_uid, now.st_gid) ==
                    (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid),
                    'RECOVERY_SCAN_ANCESTOR_CHANGED')
            require((os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (info.st_dev, info.st_ino),
                    'RECOVERY_SCAN_ANCESTOR_CHANGED')
        return observed
    finally:
        for fd in reversed(held):
            os.close(fd)


def validate_systemd_mountinfo(data):
    require(len(data) <= 1048576, 'RECOVERY_CGROUP_MOUNT_BOUND')
    matches = []
    for line in data.decode('utf-8', 'strict').splitlines():
        require(' - ' in line, 'RECOVERY_CGROUP_MOUNT_FORMAT')
        left, right = line.split(' - ', 1)
        fields, filesystem = left.split(), right.split()
        require(len(fields) >= 6 and len(filesystem) >= 3, 'RECOVERY_CGROUP_MOUNT_FORMAT')
        if fields[4] == '/sys/fs/cgroup/systemd':
            matches.append((fields, filesystem))
    require(len(matches) == 1, 'RECOVERY_CGROUP_CONTROLLER_MOUNT')
    fields, filesystem = matches[0]
    require(fields[3] == '/' and filesystem[0] == 'cgroup' and
            'name=systemd' in filesystem[2].split(','), 'RECOVERY_CGROUP_CONTROLLER_KIND')


def verify_systemd_controller_mount():
    with open('/proc/self/mountinfo', 'rb') as stream:
        validate_systemd_mountinfo(stream.read(1048577))


def notifier_cgroup_empty(name, controller='/sys/fs/cgroup/systemd/system.slice'):
    import subprocess
    require(name in ('xj-uk-owner-notify.timer', 'xj-uk-owner-notify.service'),
            'RECOVERY_NOTIFIER_NAME')
    def inactive():
        value = subprocess.run(['/usr/bin/systemctl', 'show', name,
                                '--property=ActiveState,MainPID,UnitFileState'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        states = dict(line.split('=', 1) for line in value.stdout.decode().splitlines() if '=' in line)
        require(value.returncode == 0 and states.get('ActiveState') == 'inactive' and
                states.get('MainPID', '0' if name.endswith('.timer') else None) == '0' and
                states.get('UnitFileState') == 'masked',
                'RECOVERY_NOTIFIER_STATE')
    verify_systemd_controller_mount()
    # Controller/system.slice must genuinely exist and be readable, even when
    # systemd has removed an inactive unit's cgroup. Never infer this from isdir.
    require(os.path.realpath(controller) == controller, 'RECOVERY_CGROUP_CONTROLLER_ALIAS')
    fd = os.open(controller, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISDIR(before.st_mode) and before.st_uid == 0,
                'RECOVERY_CGROUP_CONTROLLER_TYPE')
        os.listdir(fd)
        inactive()
        observed = bounded_file_inventory(controller + '/' + name, optional=True, cgroup=True)
        inactive()
        verify_systemd_controller_mount()
        now = os.stat(controller, follow_symlinks=False)
        require((before.st_dev, before.st_ino, before.st_mode) ==
                (now.st_dev, now.st_ino, now.st_mode), 'RECOVERY_CGROUP_CONTROLLER_CHANGED')
        return observed
    finally:
        os.close(fd)


def scheduler_exclusion():
    import subprocess
    path = BASE + '/consolidated-readiness-38503324102/protected-readiness-snapshot.json'
    data, unused = read(path, private=True)
    require(sha(data) == '2eeb429cc186b25f41f00217b6710a0a055d00058418ded0c187e350c6f27fab',
            'RECOVERY_BASELINE_AUDIT_DRIFT')
    baseline = json.loads(data.decode())['sections']['remaining_control_entry_inventory']
    expected = {r['path']: r['sha256'] for r in baseline['scheduler_metadata']}
    observed = {}
    for root in ('/etc/crontab','/etc/cron.d','/etc/cron.hourly','/etc/cron.daily',
                 '/etc/cron.weekly','/etc/cron.monthly','/var/spool/cron','/var/spool/at',
                 '/home/xuanjun_dev/.config/systemd/user'):
        observed.update(bounded_file_inventory(root, optional=True))
    require(observed == expected, 'RECOVERY_SCHEDULER_DRIFT')
    result = subprocess.run(['/usr/bin/systemctl','list-unit-files','--no-legend','--no-pager'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    require(result.returncode == 0, 'RECOVERY_UNIT_INVENTORY_FAILED')
    names = {line.split()[0] for line in result.stdout.decode().splitlines()
             if line.split() and line.split()[0].startswith(('xj-','xuanjun-'))}
    require(names == set(baseline['registered_control_units']), 'RECOVERY_CONTROL_UNIT_DRIFT')
    for unit, old in baseline['registered_control_units'].items():
        if 'unit_sha256' in old:
            require(sha(read(old['FragmentPath'])[0]) == old['unit_sha256'], 'RECOVERY_CONTROL_SCRIPT_DRIFT')
        for script in old.get('script_metadata', []):
            require(sha(read(script['path'], owner_uid=os.stat(script['path']).st_uid)[0]) == script['sha256'],
                    'RECOVERY_CONTROL_SCRIPT_DRIFT')
    return sha(canonical(observed))


def verified_postchecker():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'complete_install_executor.py')
    code, info = read(path)
    require(sha(code) == 'e83b769b64547d75e130423b88684459d62f247ee1bd9b604d6740e3445bdb78',
            'RECOVERY_ORIGINAL_POSTCHECK_HASH')
    require(info.st_gid == 0, 'RECOVERY_POSTCHECK_GROUP')
    return path, code


def original_postcheck(plan, root, result):
    path, code = verified_postchecker()
    ns = {'__name__': 'recovery_original_postcheck', '__file__': path}
    exec(compile(code, path, 'exec'), ns)
    return ns['post_install_checks'](plan, root, result)


def fd_exclusion(paths):
    identities = {(os.stat(p).st_dev, os.stat(p).st_ino) for p in paths if os.path.exists(p)}
    checked = 0
    for pid in os.listdir('/proc'):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        directory = '/proc/' + pid + '/fd'
        try:
            names = os.listdir(directory)
            for name in names:
                checked += 1
                require(checked <= 1000000, 'RECOVERY_FD_BOUND')
                info = os.stat(directory + '/' + name)
                require((info.st_dev, info.st_ino) not in identities, 'RECOVERY_DATABASE_HOLDER')
        except (FileNotFoundError, PermissionError):
            raise ValueError('RECOVERY_FD_SCAN_INCOMPLETE')
    return checked


def snapshot():
    import subprocess
    unused, postchecker_code = verified_postchecker()
    plan_bytes, unused = read(CAND + '/protected-core-install-plan.json', private=True)
    require(sha(plan_bytes) == PLAN_SHA, 'RECOVERY_ORIGINAL_PLAN_HASH')
    plan = json.loads(plan_bytes.decode())
    root = plan['artifact']['root']
    require(root == CAND + '/xuanjun-p2-package' and plan['transaction_id'] == TX and
            plan['artifact']['source_commit'] == SOURCE and plan['artifact']['source_tree'] == TREE,
            'RECOVERY_ORIGINAL_BUNDLE')
    manifest_bytes, unused = read(plan['artifact']['manifest'])
    require(sha(manifest_bytes) == MANIFEST_SHA, 'RECOVERY_MANIFEST_HASH')
    manifest = json.loads(manifest_bytes.decode())
    require(len(manifest['files']) == 102, 'RECOVERY_RUNTIME_COUNT')
    release = '/opt/xuanjun-control-releases/' + plan['runtime']['release_directory']
    validate_directories(root)
    validate_directories(release, retained_cache=True)
    validate_file_inventory(root, set(manifest['files']) |
                            {'P2_PACKAGE_PROVENANCE.json', 'tools/p2-package-freeze.py',
                             'deploy/integration-manifest.json'})
    validate_file_inventory(release, set(manifest['files']) |
                            set(RETAINED_CACHE_HASHES) | {'INTEGRATION_MANIFEST.json'})
    validate_release_metadata(release)
    require(sha(read(release + '/INTEGRATION_MANIFEST.json')[0]) == MANIFEST_SHA,
            'RECOVERY_INSTALLED_MANIFEST_DRIFT')
    payloads = validate_release(root, release, manifest, MANIFEST_SHA)
    cache_evidence = validate_retained_caches(release, payloads)
    sys.path.insert(0, root + '/stage1')
    from activation_control import ActivationStore
    from ledger_backup import database_manifest
    from legacy_host_adapter import LegacyHostAdapter
    from p2_fixed_host_runtime import FixedHostRuntime
    import p2_auxiliary_isolation as auxiliary
    receipt_bytes, unused = read(CAND + '/install-receipt.json', private=True)
    cutover_bytes, unused = read(DIRECTORY + '/ledger-cutover.json', private=True)
    receipt, cutover = json.loads(receipt_bytes.decode()), json.loads(cutover_bytes.decode())
    activation = ActivationStore('/var/lib/xuanjun-development/activation/active.json',
                                 '/var/lib/xuanjun-development/activation/epochs.jsonl',
                                 '/var/lib/xuanjun-development/activation/activation.lock')
    # Mutating ActivationStore methods can create the lock; recovery must reuse it.
    # Its reviewed contract deliberately uses 0644, unlike private receipts.
    unused, activation_lock_info = read(activation.lock_path)
    require(activation_lock_info.st_gid == 0 and
            stat.S_IMODE(activation_lock_info.st_mode) == 0o644,
            'RECOVERY_ACTIVATION_LOCK_AUTHORITY')
    active = activation.read()
    validate_hold(receipt, plan, active, cutover)
    runtime = FixedHostRuntime(DIRECTORY)
    require(not os.path.lexists(runtime.receipt_path) and
            not os.path.lexists(DIRECTORY + '/recovery-execution.json'), 'RECOVERY_ALREADY_ATTEMPTED')
    for name in ('runtime-boot.json', 'tls-lifecycle.json', 'rpm-prerequisites.json',
                 'bootstrap-files.json', 'publisher-bootstrap.json', 'sandbox-profile.json'):
        require(not os.path.lexists(DIRECTORY + '/' + name), 'RECOVERY_UNCLASSIFIED_PROVISION_EFFECT')
    prerequisites_sha = verify_prerequisites(runtime.prerequisites, plan['runtime']['prerequisites'])
    auxiliary.verify(plan['runtime']['auxiliary_isolation'])
    adapter = LegacyHostAdapter(DIRECTORY)
    ref = plan['cutover']['legacy_isolation']
    for path, wanted in ((DIRECTORY + '/legacy-units.json', ref['legacy_state_sha256']),
                         (DIRECTORY + '/owner-isolation-receipt.json', ref['receipt_sha256']),
                         (ref['original_plan_path'], ref['original_plan_sha256'])):
        require(sha(read(path, private=True)[0]) == wanted, 'RECOVERY_LEGACY_ADOPTION_REFERENCE')
    for name in ('xj-uk-owner-notify.timer', 'xj-uk-owner-notify.service'):
        target = '/etc/systemd/system/' + name
        require(os.path.islink(target) and os.readlink(target) == '/dev/null', 'RECOVERY_NOTIFIER_MASK')
        notifier_cgroup_empty(name)
    observation = adapter.measure_quiescence(plan['cutover']['legacy_bindings'])
    require(all(observation['proof'].get(k) is True for k in
                ('identity_verified', 'coordinator_inactive', 'parent_unit_inactive',
                 'cgroups_empty', 'restart_inhibited')), 'RECOVERY_FRESH_QUIESCENCE')
    source, backup, generation = (plan['cutover'][k] for k in
                                   ('source', 'rollback_snapshot', 'staged_generation'))
    source_set, unused = database_file_set(source, 1002, retained_source=True)
    backup_set, backup_data = database_file_set(backup, 0)
    generation_set, generation_data = database_file_set(generation, 0)
    database_sets = {source: source_set, backup: backup_set, generation: generation_set}
    require(manifest_from_copy(backup_data, database_manifest) == cutover['migration']['rollback'] and
            manifest_from_copy(generation_data, database_manifest) == cutover['migration']['generation'],
            'RECOVERY_STAGED_DATABASE_DRIFT')
    protected_paths = tuple(p + suffix for p in (source, backup, generation)
                            for suffix in ('', '-wal', '-shm', '-journal'))
    fds = fd_exclusion(protected_paths)
    no_runner_or_old_worker()
    scheduler_sha = scheduler_exclusion()
    prior_prereq = runtime.prerequisites.preflight
    prior_gateway = runtime._verify_gateway_preflight
    def retained_preflight(value):
        require(value == plan['runtime']['prerequisites'], 'RECOVERY_PREREQUISITE_PLAN_DRIFT')
        verify_prerequisites(runtime.prerequisites, value)
        return True
    def retained_gateway(value):
        require(value.get('legacy_cutover') == plan['cutover'], 'RECOVERY_CUTOVER_PLAN_DRIFT')
        measured = adapter.measure_quiescence(plan['cutover']['legacy_bindings'])
        require(measured['proof'] == observation['proof'], 'RECOVERY_QUIESCENCE_DRIFT')
    runtime.prerequisites.preflight = retained_preflight
    runtime._verify_gateway_preflight = retained_gateway
    try:
        runtime.preflight(plan['runtime'], plan['auth'], plan['tls'])
    finally:
        runtime.prerequisites.preflight = prior_prereq
        runtime._verify_gateway_preflight = prior_gateway
    check = subprocess.run(['/usr/bin/systemctl', 'show', RUNNER,
                            '--property=MainPID,ActiveState,ConditionResult'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    states = dict(line.split('=', 1) for line in check.stdout.decode().splitlines() if '=' in line)
    require(check.returncode == 0 and states.get('MainPID') == '0' and
            states.get('ActiveState') == 'inactive' and states.get('ConditionResult') == 'no' and
            os.path.isfile('/run/xuanjun-p2-runner-isolation.guard'), 'RECOVERY_RUNNER_NOT_ISOLATED')
    require(database_file_set(source, 1002, retained_source=True)[0] == source_set and
            database_file_set(backup, 0)[0] == backup_set and
            database_file_set(generation, 0)[0] == generation_set,
            'RECOVERY_DATABASE_SET_CHANGED_DURING_PREFLIGHT')
    fd_exclusion(protected_paths)
    evidence = {'schema': 1, 'transaction_id': TX, 'artifact': 11865804223,
                'plan_sha256': PLAN_SHA, 'manifest_sha256': MANIFEST_SHA,
                'hold_receipt_sha256': sha(receipt_bytes), 'cutover_sha256': sha(cutover_bytes),
                'prerequisites_sha256': prerequisites_sha, 'active': active,
                'backup_sha256': backup_set['database_sha256'], 'generation_sha256': generation_set['database_sha256'],
                'database_file_sets': database_sets, 'retained_cache_evidence': cache_evidence,
                'original_postchecker_sha256': sha(postchecker_code),
                'epoch_journal_sha256': sha(read(activation.epoch_journal)[0]),
                'scheduler_inventory_sha256': scheduler_sha,
                'files_verified': 102, 'fd_scope_complete': True,
                'runner_isolated': True, 'historical_notification_replay': False,
                'effects': 0, 'production_acceptance': 'PENDING'}
    return evidence, (plan, root, runtime, activation, adapter, observation, payloads)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('RECOVERY_APPROVAL_REDIRECT')


def approval(review_id, expected_snapshot):
    url = 'https://api.github.com/repos/' + REPO + '/issues/comments/' + str(review_id)
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=20) as response:
        raw = response.read(65537)
    require(len(raw) <= 65536, 'RECOVERY_APPROVAL_BOUND')
    comment = json.loads(raw.decode())
    require(comment.get('id') == review_id and comment.get('user', {}).get('id') == 332398908 and
            comment.get('user', {}).get('login') == 'huhongchuan0422-creator', 'RECOVERY_APPROVAL_AUTHOR')
    body = comment.get('body', '')
    require(body.startswith(MARKER), 'RECOVERY_NEW_APPROVAL_REQUIRED')
    require(comment.get('issue_url') == 'https://api.github.com/repos/' + REPO + '/issues/58',
            'RECOVERY_REVIEW_DESTINATION')
    value = json.loads(body[len(MARKER):])
    code = sha(read(os.path.abspath(__file__))[0])
    expected = {'schema': 1, 'reviewer': 'CHATGPT_NATIVE_TASK5',
                'decision': 'APPROVED_ONE_EXACT_HOLD_RESUME_AND_FENCED_FAILURE_RECOVERY',
                'transaction_id': TX, 'artifact': 11865804223, 'plan_sha256': PLAN_SHA,
                'manifest_sha256': MANIFEST_SHA, 'recovery_executor_sha256': code,
                'snapshot_sha256': expected_snapshot, 'expected_epoch': 2,
                'retain_prerequisites_on_failure': True, 'legacy_restart': False,
                'historical_notification_replay': False}
    require(value == expected, 'RECOVERY_EXACT_NEW_APPROVAL')
    return {'review_id': review_id, 'body_sha256': sha(body.encode()), 'approval': value}


def resume(evidence, context, authorization):
    from ledger_cutover_transaction import _atomic_receipt
    import p2_fixed_host_runtime as runtime_module
    plan, root, runtime, activation, adapter, observation, payloads = context
    attempt = DIRECTORY + '/recovery-execution.json'
    require(not os.path.lexists(attempt), 'RECOVERY_ATTEMPT_ALREADY_EXISTS')
    state = {'schema': 1, 'stage': 'AUTHORIZED', 'transaction_id': TX,
             'snapshot_sha256': sha(canonical(evidence)), 'authorization': authorization,
             'legacy_writer_restarted': False, 'historical_notification_replay': False,
             'prerequisites_policy': 'RETAIN_IN_PLACE_NO_NSS_REPLAY'}
    _atomic_receipt(attempt, state)
    original, unused = read(CAND + '/install-receipt.json', private=True)
    require(sha(original) == evidence['hold_receipt_sha256'], 'RECOVERY_HOLD_CHANGED')
    fd = os.open(DIRECTORY + '/original-install-hold.json', os.O_WRONLY | os.O_CREAT |
                 os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(original); stream.flush(); os.fsync(stream.fileno())
    source_paths = {('/opt/xuanjun-control-releases/' + plan['runtime']['release_directory'] +
                    '/' + b['source']): payloads['/opt/xuanjun-control-releases/' +
                    plan['runtime']['release_directory'] + '/' + b['source']]
                    for b in plan['runtime']['provisioning']}
    original_reader = runtime_module._read_regular
    runtime_module._read_regular = source_reader(source_paths, original_reader)
    receipt = {'schema': 1, 'transaction_id': TX, 'plan_sha256': sha(canonical(plan)),
               'stage': 'LEGACY_QUIESCED', 'legacy_writer_restarted': False,
               'oauth_copied': False, 'new_paid_api_usage': 'NONE',
               'release': '/opt/xuanjun-control-releases/' + plan['runtime']['release_directory'],
               'epoch': 2, 'cutover_receipt_sha256': json.loads(original.decode())['cutover_receipt_sha256']}
    provision = None
    activation_requested = False
    stop_requested = False
    current = evidence['active']
    try:
        current = activation.transition('PREPARED', 'QUIESCED', 2, current['instance'], observation['proof'])
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        state['stage'] = 'QUIESCED'; _atomic_receipt(attempt, state)
        provision = runtime.provision(receipt['release'], plan['runtime'])
        require(isinstance(provision, dict) and set(provision) ==
                {'schema', 'receipt_sha256', 'rollback_complete'} and provision['schema'] == 1 and
                re.fullmatch('[0-9a-f]{64}', provision['receipt_sha256']) and
                provision['rollback_complete'] is True, 'RECOVERY_PROVISION_RECEIPT')
        receipt.update(stage='RUNTIME_PROVISIONED', provisioning_receipt_sha256=provision['receipt_sha256'])
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        reopened = runtime.reopen_database(current)
        require(reopened == {'database_reopened': True}, 'RECOVERY_DATABASE_REOPEN')
        current = activation.transition('QUIESCED', 'ACTIVE', 2, current['instance'], reopened)
        activation_requested = True
        require(adapter.restore_legacy_files(gateway_only=True) ==
                {'unit_files_restored': True, 'services_restarted': False}, 'RECOVERY_GATEWAY_REBIND')
        require(runtime.activate(plan['runtime'], current) == {'services_active': True},
                'RECOVERY_RUNTIME_ACTIVATION')
        receipt.update(stage='COMPLETE', status='P2_INSTALL_TRANSACTION_COMPLETE')
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        state['stage'] = 'COMPLETE_PENDING_POSTINSTALL'; _atomic_receipt(attempt, state)
        state['post_install_checks'] = original_postcheck(plan, root, receipt)
        state['stage'] = 'COMPLETE_POSTCHECKED'; _atomic_receipt(attempt, state)
        return receipt
    except Exception as error:
        state.update(stage='HOLD', error_type=type(error).__name__, automatic_retry=False,
                     prerequisites_retained=True, recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
        rollback = []
        try:
            fenced = activation.fence(current['epoch'], current['instance'])
            rollback.append('ACTIVATION_FENCED_EPOCH_' + str(fenced['epoch']))
            if activation_requested:
                stop_requested = True
                runtime.stop_new(plan['runtime']); rollback.append('NEW_RUNTIME_STOPPED')
            if provision is not None:
                runtime.restore(provision); rollback.append('PROVISIONING_RESTORED')
            adapter.restore_legacy_files(preserve_mask=True)
            rollback.append('LEGACY_MASKS_PRESERVED')
        except Exception as rollback_error:
            state['rollback_error_type'] = type(rollback_error).__name__
            if activation_requested and not stop_requested:
                stop_requested = True
                try:
                    runtime.stop_new(plan['runtime'])
                    rollback.append('NEW_RUNTIME_STOPPED_WITH_FENCE_HOLD')
                except Exception:
                    rollback.append('NEW_RUNTIME_STOP_FAILED_HOLD')
        receipt.update(stage='HOLD', failed_stage=receipt['stage'], error_type=type(error).__name__,
                       rollback=rollback, recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
        if 'rollback_error_type' in state:
            receipt['rollback_error_type'] = state['rollback_error_type']
        _atomic_receipt(CAND + '/install-receipt.json', receipt)
        state['rollback'] = rollback; _atomic_receipt(attempt, state)
        raise
    finally:
        runtime_module._read_regular = original_reader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation', choices=('verify-only', 'resume'), required=True)
    parser.add_argument('--review-id', type=int)
    parser.add_argument('--snapshot-sha256')
    args = parser.parse_args()
    require(os.geteuid() == 0 and socket.gethostname().split('.')[0] ==
            'iZd7oeikknn1z21sq6ji6zZ', 'RECOVERY_FIXED_ROOT_HOST')
    # No mutations during verify-only: even the lock must already exist.
    import fcntl
    fd = os.open('/run/xuanjun-p2-install.lock', os.O_RDONLY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and
            stat.S_IMODE(info.st_mode) == 0o600, 'RECOVERY_INSTALL_LOCK_AUTHORITY')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        evidence, context = snapshot()
        digest = sha(canonical(evidence))
        if args.operation == 'verify-only':
            print('RECOVERY_SNAPSHOT=' + canonical(evidence).decode())
            print('RECOVERY_SNAPSHOT_SHA256=' + digest)
            print('RECOVERY_VERIFY_ONLY_EFFECTS=0_INSTALL_NOT_AUTHORIZED')
            return
        require(args.review_id is not None and args.review_id > 0 and
                args.snapshot_sha256 == digest, 'RECOVERY_FRESH_APPROVED_SNAPSHOT_REQUIRED')
        authorized = approval(args.review_id, digest)
        # GitHub approval retrieval is an awaited external boundary. Reconcile
        # the complete evidence again under the same lock before any effect.
        evidence, context = snapshot()
        require(sha(canonical(evidence)) == digest, 'RECOVERY_STATE_CHANGED_DURING_APPROVAL')
        result = resume(evidence, context, authorized)
        print('RECOVERY_RESULT=' + canonical(result).decode())
        print('PRODUCTION_ACCEPTANCE=PENDING_POSTINSTALL_CHECKS')
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()

