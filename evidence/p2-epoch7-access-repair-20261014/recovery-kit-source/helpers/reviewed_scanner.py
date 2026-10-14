"""Source-only selected read-only primitives. No historical capture/resume/pins.
Exact function provenance is recorded in reviewed_sources.json.
"""
import sys, hashlib, json, os, stat, tempfile, types, importlib.util, io, marshal, struct, re, sqlite3
def require(value, code):
    if not value:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


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

