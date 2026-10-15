"""Concrete read-only Linux IO for epoch7 collection; never run by fixture tests.

No CLI or network. The only writes are a private temporary SQLite inspection copy.
Existing install/activation locks are opened read-only and flocked, never created.
All queried system tools must have explicit protected executable pins.
"""
import grp
import pwd
import contextlib
import errno
import fcntl
import hashlib
import os
import selectors
import signal
import socket
import stat
import subprocess
import time

import epoch7_snapshot as c
import epoch7_delta as d
import reviewed_scanner as reviewed
import reviewed_database
import reviewed_publisher
import epoch7_python_identity as python_identity

MAXIMUM = 16777216
PYTHON_REFERENCES = ('/usr/bin/python3', '/usr/bin/python3.6', '/etc/alternatives/python3',
                     '/usr/libexec/platform-python', python_identity.PYTHON_PATHS[0])
FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0)
DIRFLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
CONTROL_GIT = '/var/lib/xuanjun-development/control.git'
CONTROL_GIT_ARGS = ['--git-dir='+CONTROL_GIT, '-c', 'core.hooksPath=/dev/null',
    '-c', 'core.fsmonitor=false', '-c', 'credential.helper=', '-c',
    'safe.directory='+CONTROL_GIT, 'rev-parse', 'HEAD^{commit}', 'HEAD^{tree}']
TLS_TIMER_FIELDS = {
    'xuanjun-p2-tls-renew.timer': ('NextElapseUSecMonotonic','LastTriggerUSecMonotonic','ActiveEnterTimestampMonotonic'),
    'xuanjun-p2-tls-renew.service': ('ActiveEnterTimestampMonotonic','ExecMainStartTimestampMonotonic')}
CONTROL_GIT_ENV = {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LANG':'C', 'LC_ALL':'C',
    'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_CONFIG_SYSTEM':'/dev/null', 'GIT_CONFIG_NOSYSTEM':'1',
    'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_TERMINAL_PROMPT':'0', 'GIT_OPTIONAL_LOCKS':'0',
    'GIT_NO_LAZY_FETCH':'1', 'GIT_ALLOW_PROTOCOL':''}


def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def metadata(s):
    return {'uid': s.st_uid, 'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode),
        'dev': s.st_dev, 'ino': s.st_ino, 'nlink': s.st_nlink, 'size': s.st_size,
        'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}


def manager_ids(status):
    result={}
    for line in status.splitlines():
        key,sep,value=line.partition(b':')
        if key in (b'Uid',b'Gid',b'Groups'):
            c.need(key not in result and sep and all(x.isdigit() for x in value.split()),'ROOT_MANAGER_ID_FIELDS')
            result[key]=[int(x) for x in value.split()]
    c.need(set(result)=={b'Uid',b'Gid',b'Groups'} and result[b'Uid']==result[b'Gid']==[0]*4 and
           len(result[b'Groups'])<=128 and all(0<=x<2**32 for x in result[b'Groups']),'ROOT_MANAGER_IDS')
    return {'uids':result[b'Uid'],'gids':result[b'Gid'],'groups':sorted(set(result[b'Groups']))}


def xattr(fd, name):
    try:
        return os.getxattr(fd, name)
    except OSError as error:
        if error.errno in (errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP): return None
        raise


class DescriptorReader(object):
    """Anchored no-follow reader. root override exists only for local IO fixtures."""
    def __init__(self, directory_pins, root='/'):
        self.pins = directory_pins
        c.need(os.path.isabs(root) and os.path.realpath(root) == root, 'READER_ROOT_ALIAS')
        self.root = root
        self.root_identity = stamp(os.lstat(root))[:5]

    def _authority(self, fd, logical):
        s = os.fstat(fd)
        c.need(stat.S_ISDIR(s.st_mode), 'ANCESTOR_DIRECTORY')
        pin = self.pins.get(logical)
        c.need(pin is not None and all(metadata(s)[k] == v for k, v in pin.items()), 'ANCESTOR_UNMEASURED_OR_CHANGED')
        c.need(xattr(fd, 'system.posix_acl_access') is None and
               xattr(fd, 'system.posix_acl_default') is None, 'UNREVIEWED_ANCESTOR_ACL')
        return s

    @contextlib.contextmanager
    def parent(self, logical, missing=False):
        c.path(logical)
        held, links = [], []
        primary = None
        try:
            current = os.open(self.root, DIRFLAGS); held.append(current)
            c.need(stamp(os.fstat(current))[:5] == self.root_identity, 'READER_ROOT_CHANGED')
            self._authority(current, '/')
            at = ''
            for part in logical.strip('/').split('/')[:-1]:
                at += '/' + part
                try:
                    before = os.stat(part, dir_fd=current, follow_symlinks=False)
                except FileNotFoundError:
                    c.need(missing, 'ANCESTOR_MISSING')
                    first = stamp(os.fstat(current)); names = sorted(os.listdir(current))
                    c.need(part not in names, 'ABSENCE_RACE')
                    yield None, None
                    c.need(sorted(os.listdir(current)) == names and stamp(os.fstat(current)) == first,
                           'ABSENCE_PARENT_CHANGED')
                    # Missing descendants still require the same held
                    # ancestor/root identity reread as an existing leaf.
                    break
                child = os.open(part, DIRFLAGS, dir_fd=current); held.append(child)
                c.need(stamp(before) == stamp(os.fstat(child)), 'ANCESTOR_OPEN_RACE')
                self._authority(child, at)
                links.append((current, part, before, child)); current = child
            else:
                yield current, logical.rsplit('/', 1)[1]
            for parent, name, before, child in reversed(links):
                c.need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False))[:5] == stamp(before)[:5] and
                       stamp(os.fstat(child))[:5] == stamp(before)[:5], 'ANCESTOR_REPLACED')
            c.need(stamp(os.lstat(self.root))[:5] == self.root_identity, 'READER_ROOT_REPLACED')
        except BaseException as error:
            primary = error; raise
        finally:
            failure = None
            for fd in reversed(held):
                # Every owned descriptor gets one independent attempt. A close
                # interrupted after release is ambiguous, so never retry it.
                try: os.close(fd)
                except BaseException as error:
                    if failure is None: failure = error
            if failure is not None:
                raise (primary if primary is not None else failure) from ValueError('READER_PARENT_CLEANUP_UNKNOWN')

    def read(self, logical, maximum=MAXIMUM):
        c.need(type(maximum) is int and 0 < maximum <= 536870912, 'READ_LIMIT')
        with self.parent(logical) as (parent, name):
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            c.need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                   before.st_size <= maximum and not before.st_mode & 0o7022, 'REGULAR_PROTECTED_FILE')
            fd = os.open(name, FLAGS, dir_fd=parent)
            try:
                c.need(stamp(os.fstat(fd)) == stamp(before), 'FILE_OPEN_RACE')
                c.need(xattr(fd, 'system.posix_acl_access') is None, 'UNREVIEWED_FILE_ACL')
                chunks, count = [], 0
                while True:
                    chunk = os.read(fd, min(65536, maximum + 1 - count))
                    if not chunk: break
                    chunks.append(chunk); count += len(chunk)
                    c.need(count <= maximum, 'FILE_BOUND')
                c.need(count == before.st_size and stamp(os.fstat(fd)) == stamp(before), 'FILE_READ_RACE')
            finally: os.close(fd)
            c.need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == stamp(before), 'FILE_PATH_RACE')
            data = b''.join(chunks)
            row = metadata(before); row.update(kind='FILE', sha256=c.sha(data))
            return data, row

    def file_info(self, logical):
        """Metadata-only bounded-file decision; never follows a leaf symlink."""
        with self.parent(logical) as (parent,name):
            before=os.stat(name,dir_fd=parent,follow_symlinks=False)
            c.need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
                   not before.st_mode & 0o7022,'PROBE_REGULAR_FILE_AUTHORITY')
            fd=os.open(name,FLAGS,dir_fd=parent)
            try:
                c.need(stamp(os.fstat(fd))==stamp(before) and xattr(fd,'system.posix_acl_access') is None,
                       'PROBE_FILE_METADATA_OR_ACL')
            finally:os.close(fd)
            c.need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==stamp(before),'PROBE_FILE_METADATA_RACE')
            return dict(metadata(before),kind='FILE')

    def _python_pair_round(self):
        """One fixed no-follow pair round; no generic file rule is relaxed."""
        held, directories, files, links, raw_files = [], {}, {}, [], {}
        def attributes(fd):
            values = {key: xattr(fd, name) for key, name in (
                ('access_acl','system.posix_acl_access'),
                ('default_acl','system.posix_acl_default'),
                ('capability','security.capability'))}
            c.need(all(value is None for value in values.values()), 'PYTHON_PAIR_XATTR_PRESENT_OR_UNKNOWN')
            return {key: False for key in values}
        try:
            root = os.open(self.root, DIRFLAGS); held.append(root)
            first = os.fstat(root)
            c.need(stamp(first)[:5] == self.root_identity, 'PYTHON_PAIR_ROOT_CHANGED')
            self._authority(root, '/')
            directories['/'] = (root, first)
            current = root
            for part, logical in (('usr','/usr'), ('libexec','/usr/libexec')):
                before = os.stat(part, dir_fd=current, follow_symlinks=False)
                fd = os.open(part, DIRFLAGS, dir_fd=current); held.append(fd)
                c.need(stamp(os.fstat(fd)) == stamp(before), 'PYTHON_PAIR_ANCESTOR_OPEN_RACE')
                self._authority(fd, logical)
                directories[logical] = (fd, before)
                links.append((current,part,before)); current = fd
            sample = {'ancestors': {}, 'files': {}}
            for path, (fd, before) in directories.items():
                sample['ancestors'][path] = dict(metadata(before), kind='DIRECTORY', **attributes(fd))
            for path in python_identity.PYTHON_PATHS:
                name = path.rsplit('/',1)[1]
                before = os.stat(name, dir_fd=current, follow_symlinks=False)
                c.need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0 and
                       stat.S_IMODE(before.st_mode) == 0o755 and before.st_nlink == 2 and
                       before.st_size == python_identity.RETAINED_SIZE, 'PYTHON_PAIR_FIXED_FILE_AUTHORITY')
                fd = os.open(name, FLAGS, dir_fd=current); held.append(fd)
                c.need(stamp(os.fstat(fd)) == stamp(before), 'PYTHON_PAIR_FILE_OPEN_RACE')
                attrs = attributes(fd); chunks, count = [], 0
                while True:
                    chunk = os.read(fd, min(65536, python_identity.RETAINED_SIZE + 1 - count))
                    if not chunk: break
                    chunks.append(chunk); count += len(chunk)
                    c.need(count <= python_identity.RETAINED_SIZE, 'PYTHON_PAIR_CONTENT_BOUND')
                raw = b''.join(chunks)
                c.need(count == before.st_size and raw.startswith(b'\x7fELF'), 'PYTHON_PAIR_ELF_OR_SIZE')
                sample['files'][path] = dict(metadata(before), kind='FILE', sha256=c.sha(raw),
                                              elf_header=True, **attrs)
                raw_files[path] = raw; files[path] = (fd, before)
            for path, (fd, before) in files.items():
                c.need(stamp(os.fstat(fd)) == stamp(before) and
                       stamp(os.stat(path.rsplit('/',1)[1],dir_fd=current,follow_symlinks=False)) == stamp(before),
                       'PYTHON_PAIR_FILE_REREAD_RACE')
                c.need(attributes(fd) == {key:sample['files'][path][key] for key in python_identity.XATTR_FIELDS},
                       'PYTHON_PAIR_FILE_XATTR_RACE')
            for parent, name, before in reversed(links):
                c.need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False)) == stamp(before),
                       'PYTHON_PAIR_ANCESTOR_PATH_RACE')
            for path, (fd, before) in directories.items():
                c.need(stamp(os.fstat(fd)) == stamp(before), 'PYTHON_PAIR_ANCESTOR_FD_RACE')
                c.need(attributes(fd) == {key:sample['ancestors'][path][key] for key in python_identity.XATTR_FIELDS},
                       'PYTHON_PAIR_ANCESTOR_XATTR_RACE')
            c.need(stamp(os.lstat(self.root)) == stamp(first), 'PYTHON_PAIR_ROOT_PATH_RACE')
            return python_identity.validate_pair_sample(sample), raw_files
        finally:
            failure = None
            for fd in reversed(held):
                try: os.close(fd)
                except OSError as error:
                    if failure is None: failure = error
            if failure is not None: raise failure

    def read_python(self, logical, maximum=33554432):
        """Dedicated retained-pair API. Ordinary read/file_info still require nlink1."""
        c.need(logical in python_identity.PYTHON_PATHS and type(maximum) is int and
               python_identity.RETAINED_SIZE <= maximum <= 536870912, 'PYTHON_PAIR_READ_SCOPE')
        before, first = self._python_pair_round()
        after, last = self._python_pair_round()
        c.need(first == last, 'PYTHON_PAIR_CONTENT_CHANGED')
        proof = python_identity.build_pair_proof(before, after, python_identity.package_claim())
        row = dict(proof['sample']['files'][logical], python_identity=proof)
        return last[logical], row

    def absent(self, logical):
        with self.parent(logical, missing=True) as (parent, name):
            if parent is None: return True
            before = stamp(os.fstat(parent)); names = sorted(os.listdir(parent))
            if name in names: return False
            try: os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError: pass
            else: return False
            c.need(sorted(os.listdir(parent)) == names and stamp(os.fstat(parent)) == before, 'ABSENCE_RACE')
            return True

    def mask(self, logical):
        with self.parent(logical) as (parent, name):
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            c.need(stat.S_ISLNK(before.st_mode) and (before.st_uid, before.st_gid, before.st_nlink) == (0, 0, 1)
                   and os.readlink(name, dir_fd=parent) == '/dev/null', 'EXACT_MASK_REQUIRED')
            c.need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == stamp(before), 'MASK_READ_RACE')
            value = metadata(before); value.update(kind='MASK', link='/dev/null')
            return value

    def directory(self, logical):
        with self.parent(logical) as (parent, name):
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            fd = os.open(name, DIRFLAGS, dir_fd=parent)
            try:
                self._authority(fd, logical)
                c.need(stamp(os.fstat(fd)) == stamp(before), 'DIRECTORY_RACE')
            finally: os.close(fd)
            c.need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == stamp(before), 'DIRECTORY_RACE')
            value = metadata(before); mode = value['mode']
            def bits(n): return ''.join(ch if n & bit else '-' for ch, bit in (('r', 4), ('w', 2), ('x', 1)))
            acl = 'user::' + bits((mode >> 6) & 7) + '\ngroup::' + bits((mode >> 3) & 7) + '\nother::' + bits(mode & 7) + '\n'
            value.update(path=logical, kind='DIRECTORY', access_acl=acl, default_acl='')
            return value


def _query_group_signal(process):
    """Signal a session only while a live/unreaped direct child pins its PID."""
    if process.returncode is not None:return False
    lock=getattr(process,'_waitpid_lock',None)
    if lock is None or not lock.acquire(False):return False
    try:
        exited=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        if exited is not None and exited.si_pid!=process.pid:return False
        if os.getpgid(process.pid)!=process.pid or os.getsid(process.pid)!=process.pid:return False
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        return True
    except ChildProcessError:return False
    finally:lock.release()


def _query_reap(process, deadline):
    """Use explicit WNOHANG ownership and a single shared absolute deadline."""
    while True:
        if process.returncode is not None:return True
        lock=getattr(process,'_waitpid_lock',None)
        if lock is not None and lock.acquire(False):
            try:
                pid,status=os.waitpid(process.pid,os.WNOHANG)
                if pid==process.pid:
                    if os.WIFEXITED(status):process.returncode=os.WEXITSTATUS(status)
                    elif os.WIFSIGNALED(status):process.returncode=-os.WTERMSIG(status)
                    else:raise ValueError('QUERY_CHILD_STATUS_UNSUPPORTED')
                    return True
                c.need(pid==0,'QUERY_CHILD_WAIT_IDENTITY')
            except ChildProcessError:return False
            finally:lock.release()
        remaining=deadline-time.monotonic()
        if remaining<=0:return False
        time.sleep(min(remaining,0.01))


def _query_cleanup(process, selector, deadline):
    """Independent signal/close/reap attempts; no secondary error skips a step."""
    failures=[];interrupted=None
    def attempt(label,operation):
        nonlocal interrupted
        try:
            result=operation()
            if result is False:failures.append(label)
        except BaseException as error:
            failures.append(label)
            if interrupted is None and isinstance(error,(KeyboardInterrupt,SystemExit)):interrupted=error
    attempt('signal',lambda:_query_group_signal(process))
    if selector is not None:attempt('selector_close',selector.close)
    for name in ('stdout','stderr'):
        stream=getattr(process,name,None)
        if stream is not None:attempt(name+'_close',stream.close)
    attempt('reap',lambda:_query_reap(process,deadline))
    if interrupted is not None:raise interrupted
    c.need(not failures,'READ_ONLY_COMMAND_CLEANUP_UNKNOWN')


def bounded_query(argv, timeout=15.0, maximum=1048576, git_environment=False):
    """Read-only exact argv; one wall budget includes startup and owned cleanup.

    No poll/communicate/Popen.wait and no signalling after reaping. Exclusive
    wait ownership is required; an external SIGCHLD/raw waitpid reaper is not
    supported. Kernel-blocked calls or suspension are not real-time guarantees.
    """
    import math
    c.need(type(timeout) in (int,float) and math.isfinite(timeout) and 0<timeout<=60 and
           type(maximum) is int and 0<maximum<=1048576,'READ_ONLY_QUERY_BOUNDS')
    c.need(all(hasattr(os,name) for name in ('waitid','P_PID','WEXITED','WNOHANG','WNOWAIT','set_blocking')),
           'READ_ONLY_QUERY_PLATFORM')
    c.need(type(git_environment) is bool and (not git_environment or
           argv == ['/usr/bin/git'] + CONTROL_GIT_ARGS), 'EXACT_READ_ONLY_GIT_QUERY')
    environment = CONTROL_GIT_ENV if git_environment else {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
    deadline=time.monotonic()+timeout;work_deadline=deadline-min(1.0,timeout/5.0)
    process=None;selector=None;failure=None;cleanup_failure=None
    streams={'stdout':bytearray(),'stderr':bytearray()};exited=None
    try:
        process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,start_new_session=True,cwd='/',env=dict(environment),
            bufsize=0,close_fds=True,shell=False)
        c.need(time.monotonic()<work_deadline,'READ_ONLY_COMMAND_DEADLINE')
        selector=selectors.DefaultSelector()
        for name in streams:
            stream=getattr(process,name);os.set_blocking(stream.fileno(),False)
            selector.register(stream,selectors.EVENT_READ,name)
        while selector.get_map():
            remaining=work_deadline-time.monotonic();c.need(remaining>0,'READ_ONLY_COMMAND_DEADLINE')
            for key,unused in selector.select(remaining):
                try:chunk=os.read(key.fd,65536)
                except BlockingIOError:continue
                if not chunk:selector.unregister(key.fileobj)
                else:
                    streams[key.data].extend(chunk)
                    c.need(len(streams[key.data])<=maximum,'READ_ONLY_COMMAND_OUTPUT_BOUND')
        while True:
            remaining=work_deadline-time.monotonic();c.need(remaining>0,'READ_ONLY_COMMAND_DEADLINE')
            exited=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if exited is not None:
                c.need(exited.si_pid==process.pid,'QUERY_CHILD_EXIT_IDENTITY');break
            time.sleep(min(remaining,0.01))
    except BaseException as error:failure=error
    finally:
        if process is not None:
            try:_query_cleanup(process,selector,deadline)
            except BaseException as error:cleanup_failure=error
    # Preserve interruption only after every independent cleanup was attempted.
    for error in (failure,cleanup_failure):
        if isinstance(error,(KeyboardInterrupt,SystemExit)):raise error
    if failure is not None:
        if cleanup_failure is not None:
            raise failure from ValueError('READ_ONLY_COMMAND_CLEANUP_UNKNOWN')
        raise failure
    if cleanup_failure is not None:raise ValueError('READ_ONLY_COMMAND_CLEANUP_UNKNOWN') from None
    c.need(time.monotonic()<=deadline,'READ_ONLY_COMMAND_DEADLINE')
    c.need(exited is not None and process.returncode==0,'READ_ONLY_COMMAND_FAILED')
    return bytes(streams['stdout'])


class LocalReadOnlyIO(DescriptorReader):
    def __init__(self, policy, locks):
        c.need(os.geteuid() == 0 and socket.gethostname().split('.')[0] == c.HOST, 'FIXED_HOST_ROOT_REQUIRED')
        super(LocalReadOnlyIO, self).__init__(policy['directories'])
        self.policy, self.locks = policy, locks
        self.deadline = time.monotonic() + 240

    def identity(self):
        return {'hostname': socket.gethostname().split('.')[0], 'euid': os.geteuid()}

    def check_locks(self):
        c.need(time.monotonic() < self.deadline, 'COLLECTOR_TOTAL_DEADLINE')
        c.need(set(self.locks) == {c.INSTALL_LOCK, c.ACTIVATION_LOCK}, 'EXISTING_LOCKS_REQUIRED')
        for name, pair in self.locks.items():
            fd, first = pair
            c.need(stamp(os.fstat(fd)) == first and stamp(os.lstat(name)) == first, 'LOCK_REPLACED')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def read(self, *args, **kwargs):
        self.check_locks()
        return super(LocalReadOnlyIO, self).read(*args, **kwargs)

    def read_python(self, *args, **kwargs):
        self.check_locks()
        result = super(LocalReadOnlyIO, self).read_python(*args, **kwargs)
        self.check_locks()
        return result

    def command(self, label, args):
        self.check_locks()
        pin = self.policy['executables'][label]
        data, row = self.read(pin['path'])
        c.pin_matches(row, self.policy['files'][pin['path']])
        if label == 'git':
            c.need(pin['path'] == '/usr/bin/git' and args == CONTROL_GIT_ARGS, 'CONTROL_GIT_QUERY_SCOPE')
        output = bounded_query([pin['path']] + args, timeout=min(15, self.deadline - time.monotonic()),
                               maximum=1024 if label == 'git' else 1048576, git_environment=label == 'git')
        c.need(self.read(pin['path'])[1] == row, 'QUERY_BINARY_CHANGED')
        return output

    def inventory(self, root):
        self.check_locks()
        return reviewed.bounded_file_inventory(root)

    def directory_inventory(self, root):
        self.check_locks(); result = {}
        def failed(error): raise error
        for parent, dirs, files in os.walk(root, followlinks=False, onerror=failed):
            result[parent] = self.directory(parent)
            c.need(len(result) <= 8192, 'DIRECTORY_INVENTORY_BOUND')
            for name in dirs:
                c.need(not os.path.islink(parent + '/' + name), 'DIRECTORY_INVENTORY_LINK')
        return result

    def publisher(self, row):
        self.check_locks()
        return reviewed_publisher.verify_row(row)

    def control_git_source(self, reference, row, journal_sha256):
        """Measure one retained bare HEAD/tree without selecting future source."""
        import re
        self.check_locks()
        d.keys(reference, ('path','sha256','source_commit','source_tree'), 'CONTROL_PUBLISHER_REFERENCE')
        c.need(reference['path'] == c.BASE + '/publisher-realm-38503014520/protected-publisher-inputs.json',
               'CONTROL_PUBLISHER_REFERENCE_PATH')
        for key in ('source_commit','source_tree'):
            c.need(isinstance(reference[key],str) and re.fullmatch(r'[0-9a-f]{40}',reference[key]),
                   'CONTROL_PUBLISHER_SOURCE_FORMAT')
        d.hash_value(reference['sha256']);d.hash_value(journal_sha256)
        c.need(row['target'] == CONTROL_GIT, 'CONTROL_PUBLISHER_TARGET')
        # The reviewed publisher verifier authenticates all repository bytes,
        # including config/object files, and rejects symlinks/hardlinks/modes.
        before=self.publisher(row)
        for suffix in ('/objects/info/alternates','/objects/info/http-alternates'):
            c.need(self.absent(CONTROL_GIT+suffix),'CONTROL_EXTERNAL_OBJECT_STORE')
        output=self.command('git',list(CONTROL_GIT_ARGS))
        c.need(re.fullmatch(br'[0-9a-f]{40}\n[0-9a-f]{40}\n',output), 'CONTROL_GIT_OUTPUT')
        for suffix in ('/objects/info/alternates','/objects/info/http-alternates'):
            c.need(self.absent(CONTROL_GIT+suffix),'CONTROL_EXTERNAL_OBJECT_STORE')
        c.need(self.publisher(row)==before,'CONTROL_PUBLISHER_QUERY_RACE')
        commit,tree=output.decode('ascii').splitlines()
        return {'schema':1,'path':CONTROL_GIT,'head_commit':commit,'head_tree':tree,
            'publisher_reference_sha256':d.digest(reference),'publisher_journal_sha256':journal_sha256,
            'publisher_fingerprint_sha256':row['fingerprint'],
            'git_sha256':self.policy['executables']['git']['sha256']}

    def logical_manifest(self, raw):
        self.check_locks()
        return reviewed.manifest_from_copy(raw, reviewed_database.database_manifest)

    def native_identity(self, retained, effective):
        ledger, gateway = retained['ledger'], retained['gatewayIdentity']
        current = effective['ledger']
        d.keys(ledger, ('python','pythonSha256','bridge','config','files'), 'NATIVE_LEDGER_KEYS')
        d.keys(current, ledger.keys(), 'NATIVE_CURRENT_LEDGER_KEYS')
        d.keys(gateway, ('user','exe','sha256','cgroup'), 'NATIVE_GATEWAY_KEYS')
        c.need(gateway['user'] == 'xuanjun_dev' and
               pwd.getpwnam(gateway['user']).pw_uid == 1002 and
               gateway['cgroup'] == '/system.slice/xuanjun-uk-openclaw.service', 'NATIVE_GATEWAY_IDENTITY')
        client = '/etc/xuanjun-development/p2-native-ledger-client.json'
        old_bridge = '/opt/xuanjun-control-releases/integration-' + d.OLD_MANIFEST[:16] + '/stage1/native_ledger_bridge.py'
        live_bridge = '/opt/xuanjun-control-releases/integration-' + d.OLD_MANIFEST[:16] + '/stage1/native_ledger_bridge.py'
        c.need(ledger['bridge'] == old_bridge and current['bridge'] == live_bridge and
               ledger['config'] == current['config'] == client and
               set(ledger['files']) == {old_bridge,client} and set(current['files']) == {live_bridge,client} and
               ledger['python'] == current['python'] and ledger['pythonSha256'] == current['pythonSha256'],
               'NATIVE_RETAINED_AND_CURRENT_BINDING')
        # The current client file belongs to the retained v4 target receipt. The
        # completed owned epoch5 rebind changed only the bridge path to153653.
        # Its historical client hash is unchanged. The central transition gate
        # authenticates this rebind; current client bytes remain receipt-bound.
        expected = [(gateway['exe'],gateway['sha256'],1002), (ledger['python'],ledger['pythonSha256'],0),
                    (old_bridge,ledger['files'][old_bridge],0)]
        expected += [(name,digest,0) for name,digest in current['files'].items()]
        result = {}; python_reference = None
        for name,digest,uid in expected:
            c.path(name); d.hash_value(digest)
            if name == ledger['python']:
                c.need(name in PYTHON_REFERENCES, 'NATIVE_PYTHON_REFERENCE_SCOPE')
                python_reference = self.executable_reference(name)
                final = python_reference['final']; row = final['metadata']
                c.need(final['sha256'] == digest and row['sha256'] == digest and row['uid'] == uid,
                       'NATIVE_COMPONENT_PIN')
                if final['path'] in python_identity.PYTHON_PATHS:
                    c.need(final['path'] == python_identity.PYTHON_PATHS[0] and digest == python_identity.RETAINED_SHA256,
                           'NATIVE_EXACT_PYTHON_PAIR_BINDING')
                    proof = python_identity.validate_pair_proof(row['python_identity'])
                    for member in python_identity.PYTHON_PATHS:
                        result[member] = dict(proof['sample']['files'][member], python_identity=proof)
                else:result[final['path']] = row
                continue
            else:
                raw, row = self.read(name, maximum=268435456)
            c.need(row['sha256'] == digest and row['uid'] == uid, 'NATIVE_COMPONENT_PIN')
            result[name] = row
        return {'components':result, 'python_reference':python_reference,
                'retained_sidefile_release_sha256':d.OLD_MANIFEST,
                'effective_target_release_sha256':d.OLD_MANIFEST,
                'retained_client_sha256':ledger['files'][client],
                'current_client_sha256':current['files'][client],
                'identity_admission':'NOT_GRANTED'}

    def prerequisites(self, plan, receipt, rpm):
        c.need(receipt.get('schema') == 1 and receipt.get('plan_sha256') == d.digest(plan) and
               receipt.get('restored') is not True and all(a.get('state') == 'DONE' for a in receipt.get('actions', [])),
               'PREREQUISITE_JOURNAL')
        identities = {}
        for name, gid in plan['groups'].items():
            group = grp.getgrnam(name)
            allowed = {'xuanjun-dispatcher', 'xuanjun-callback'} if name == 'xuanjun-control-db' else (set() if name == 'xuanjun-ledger-client' else {name})
            c.need(group.gr_gid == gid and set(group.gr_mem) <= allowed, 'GLOBAL_GROUP_DRIFT')
            identities['group:' + name] = {'gid': gid, 'members': sorted(group.gr_mem)}
        for name, value in plan['users'].items():
            user = pwd.getpwnam(name)
            c.need((user.pw_uid, user.pw_gid, user.pw_dir, user.pw_shell) ==
                   (value['uid'], value['gid'], value['home'], '/sbin/nologin'), 'NSS_USER_DRIFT')
            groups = sorted(os.getgrouplist(name, value['gid']))
            c.need(set(groups) == {value['gid']} | {plan['groups'][g] for g in value['groups']}, 'NSS_MEMBERSHIP_DRIFT')
            identities['user:' + name] = {'uid': user.pw_uid, 'gid': user.pw_gid, 'groups': groups}
        directories = {}
        for row in plan['directories']:
            got = self.directory(row['path'])
            c.need(all(got[k] == row[k] for k in ('uid', 'gid', 'mode')), 'PREREQUISITE_DIRECTORY_DRIFT')
            directories[row['path']] = got
        binaries = {}
        for row in plan['binaries']:
            raw, got = self.read(row['target'], maximum=536870912)
            c.need(got['sha256'] == row['sha256'] and (got['uid'], got['gid'], got['mode']) == (0, 0, 0o555), 'PREREQUISITE_BINARY_DRIFT')
            binaries[row['target']] = got
        rows = rpm.get('packages')
        c.need(rpm.get('state') == 'INSTALLED' and isinstance(rows, list) and len(rows) == 16 and
               len({r['name'] for r in rows}) == 16, 'RPM_RETAINED_JOURNAL')
        versions,nevra = {},{}
        for row in rows:
            name = row['name']; c.need(__import__('re').fullmatch(r'[a-zA-Z0-9_.+-]+', name), 'RPM_NAME')
            output = self.command('rpm', ['-q', '--qf', '%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}', name])
            c.need(output.decode('utf-8', 'strict').split() == row['candidate'], 'RPM_VERSION_DRIFT')
            versions[name] = c.sha(output);nevra[name]=output.decode('utf-8','strict').split()
        return {'identities': identities, 'directories': directories, 'binaries': binaries, 'rpm_versions': versions,'rpm_nevra':nevra}

    def cache_staging(self, root, source_rel, cache, source, source_meta):
        source_stat = os.lstat(root + '/' + source_rel)
        c.need(metadata(source_stat) == {k:source_meta[k] for k in metadata(source_stat)}, 'CACHE_SOURCE_RACE')
        return reviewed.verify_cache_bytes(cache, source, source_rel, source_stat)

    def release(self, root, pin):
        self.check_locks()
        manifest_raw, manifest_meta = self.read(root + '/INTEGRATION_MANIFEST.json')
        c.need(manifest_meta['sha256'] == pin['manifest_sha256'], 'INSTALLED_MANIFEST_PIN')
        manifest = c.decode(manifest_raw)
        c.need(set(manifest['files']) == set(pin['payloads']), 'RELEASE_MANIFEST_FILE_SET')
        expected = {root + '/' + name: value for name, value in pin['payloads'].items()}
        expected.update({root + '/' + name: value for name, value in pin['caches'].items()})
        expected[root + '/INTEGRATION_MANIFEST.json'] = pin['manifest_sha256']
        c.need(self.inventory(root) == expected, 'RELEASE_INVENTORY_CHANGED')
        directories = self.directory_inventory(root)
        c.need(set(directories) == {n for n in self.policy['directories'] if n == root or n.startswith(root + '/')},
               'RELEASE_DIRECTORY_SET')
        c.need(all((r['uid'], r['gid'], r['mode']) == (0, 0, 0o555) for r in directories.values()), 'RELEASE_DIRECTORY_AUTHORITY')
        identities = set(manifest['rendering']['identity_files'])
        result, cache_rows = {}, {}
        for rel, wanted in sorted(pin['payloads'].items()):
            data, info = self.read(root + '/' + rel)
            c.need(info['sha256'] == wanted and (info['uid'], info['gid'], info['mode']) == (0, 0, 0o555 if rel in {'scripts/xj-root-broker-client', 'scripts/uk-owner-workbench-config.py'} else 0o444), 'RELEASE_FILE_AUTHORITY')
            c.need(rel in identities or wanted == manifest['files'][rel], 'UNRENDERED_SOURCE_HASH')
            result[rel] = info
        for rel, wanted in sorted(pin['caches'].items()):
            data, info = self.read(root + '/' + rel)
            c.need(info['sha256'] == wanted and (info['uid'], info['gid'], info['mode']) == (0, 0, 0o444), 'CACHE_FILE_AUTHORITY')
            source_rel = 'stage1/' + os.path.basename(rel)[:-len('.cpython-36.pyc')] + '.py'
            c.need(source_rel in result, 'CACHE_SOURCE_REQUIRED')
            source, source_meta = self.read(root + '/' + source_rel)
            source_stat = os.lstat(root + '/' + source_rel)
            c.need(metadata(source_stat) == {k: source_meta[k] for k in metadata(source_stat)}, 'CACHE_SOURCE_RACE')
            staging = reviewed.verify_cache_bytes(data, source, source_rel, source_stat)
            c.need(staging == pin['cache_staging'], 'CACHE_STAGING_CHANGED')
            cache_rows[rel] = {'file': info, 'source_sha256': c.sha(source), 'staging': staging}
        c.need(self.inventory(root) == expected, 'RELEASE_INVENTORY_RACE')
        return {'manifest_sha256': pin['manifest_sha256'], 'files': result, 'caches': cache_rows, 'directories': directories}

    def tls(self, policy):
        self.check_locks()
        # Preserve the existing lifecycle fingerprint representation, strengthen
        # descriptor/path stability, and never invoke certbot or contact ACME.
        root = c.TLS; self.directory(root); rows, meta_rows, total = [], {}, 0
        def failed(error): raise error
        for parent, dirs, files in os.walk(root, followlinks=False, onerror=failed):
            before = self.directory(parent)
            for name in sorted(dirs + files):
                logical = parent + '/' + name; info = os.lstat(logical); rel = os.path.relpath(logical, root)
                c.need(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022), 'TLS_AUTHORITY')
                if stat.S_ISLNK(info.st_mode):
                    target = os.path.realpath(logical)
                    c.need(target.startswith(root + '/') and os.path.isfile(target), 'TLS_LINK_ESCAPE')
                    value = os.readlink(logical); rows.append([rel, 'LINK', value])
                    self.read(target)
                    c.need(stamp(info) == stamp(os.lstat(logical)) and os.readlink(logical) == value, 'TLS_LINK_RACE')
                    meta_rows[rel] = dict(metadata(info), kind='LINK', target_sha256=c.sha(value.encode()))
                elif stat.S_ISDIR(info.st_mode):
                    meta_rows[rel] = self.directory(logical); rows.append([rel, 'DIR', stat.S_IMODE(info.st_mode)])
                else:
                    raw, meta = self.read(logical); total += len(raw); c.need(total <= 67108864, 'TLS_CONTENT_BOUND')
                    meta_rows[rel] = meta; rows.append([rel, 'FILE', meta['mode'], meta['sha256']])
                c.need(len(rows) <= 4096, 'TLS_ENTRY_BOUND')
            c.need(self.directory(parent) == before, 'TLS_DIRECTORY_RACE')
        domain = 'uk.wenwenwenyiyiyi.work'; archive = root + '/config/archive/' + domain + '/'
        cert = root + '/config/live/' + domain + '/fullchain.pem'; key = root + '/config/live/' + domain + '/privkey.pem'
        real_cert, real_key = os.path.realpath(cert), os.path.realpath(key)
        c.need(real_cert.startswith(archive) and real_key.startswith(archive), 'TLS_LINEAGE')
        cert_before = self.read(real_cert)[1]; key_before = self.read(real_key)[1]
        host = self.command('openssl', ['x509', '-in', real_cert, '-noout', '-checkhost', domain])
        c.need(b'does match certificate' in host, 'TLS_CERT_DOMAIN')
        self.command('openssl', ['x509', '-in', real_cert, '-noout', '-checkend', '86400'])
        pub = self.command('openssl', ['x509', '-in', real_cert, '-pubkey', '-noout'])
        c.need(pub == self.command('openssl', ['pkey', '-in', real_key, '-pubout']), 'TLS_KEY_PAIR')
        der = self.command('openssl', ['x509', '-in', real_cert, '-outform', 'DER'])
        c.need(self.read(real_cert)[1] == cert_before and self.read(real_key)[1] == key_before and
               (os.path.realpath(cert), os.path.realpath(key)) == (real_cert, real_key), 'TLS_CERT_RACE')
        c.need(self.read(root + '/client.ini')[0] == b'', 'TLS_CLIENT_CONFIG')
        return {'tree_fingerprint_sha256': c.sha(__import__('json').dumps(sorted(rows), separators=(',', ':')).encode()),
                'certificate_sha256': c.sha(der), 'file_metadata': meta_rows, 'domain_verified': True,
                'valid_at_least_seconds': 86400, 'key_pair_verified': True, 'acme_calls': 0}

    def _unit(self, name):
        props = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlPID', 'ControlGroup',
                 'UnitFileState', 'ConditionResult', 'FragmentPath', 'DropInPaths', 'NeedDaemonReload')
        raw = self.command('systemctl', ['show', name, '--property=' + ','.join(props)])
        result = {}
        for line in raw.decode('utf-8', 'strict').splitlines():
            c.need('=' in line, 'UNIT_QUERY_FORMAT'); key, value = line.split('=', 1)
            c.need(key in props and key not in result, 'UNIT_QUERY_KEYS'); result[key] = value
        unused, optional = c.unit_process_fields(name)
        required = set(props) - optional
        main_pid, control_pid = c.validate_unit_process_fields(name, result)
        c.need(required <= set(result) and result['Id'] == name and
               result['ActiveState'] in ('inactive', 'failed') and
               main_pid == control_pid == 0 and
               result['NeedDaemonReload'] == 'no', 'UNIT_NOT_EXCLUDED')
        if name == c.RUNNER:
            c.need(result['ConditionResult'] == 'no' and not self.absent(c.RUNNER_GUARD), 'RUNNER_GUARD')
        return result

    def _ssh_image(self,pid):
        """Hash the opened proc image and bind it to the protected canonical SSH file."""
        canonical,expected=self.read('/usr/bin/ssh',maximum=33554432)
        c.need(expected['uid']==expected['gid']==0 and expected['mode']&0o111,'BACKGROUND_SSH_IMAGE_AUTHORITY')
        path='/proc/'+str(pid)+'/exe';first=os.readlink(path)
        c.need(first=='/usr/bin/ssh','BACKGROUND_SSH_IMAGE_PATH')
        fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            before=os.fstat(fd)
            c.need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
                   all(metadata(before)[k]==expected[k] for k in metadata(before)), 'BACKGROUND_SSH_IMAGE_IDENTITY')
            value=hashlib.sha256();count=0
            while True:
                part=os.read(fd,min(65536,33554433-count))
                if not part:break
                count+=len(part);c.need(count<=33554432,'BACKGROUND_SSH_IMAGE_BOUND');value.update(part)
            c.need(count==before.st_size and stamp(os.fstat(fd))==stamp(before) and
                   os.readlink(path)==first and value.hexdigest()==expected['sha256'],'BACKGROUND_SSH_IMAGE_RACE')
            return value.hexdigest(),[before.st_dev,before.st_ino]
        finally:os.close(fd)

    def _ssh_identity(self,pid,procfile):
        first=procfile('stat',65536);end=first.rfind(b')');fields=first[end+2:].split()
        c.need(first.startswith((str(pid)+' (').encode()) and end>0 and len(fields)>=20,'BACKGROUND_SSH_STAT')
        started=int(fields[19]);kernel=bool(int(fields[6])&0x00200000)
        c.need(started>0 and not kernel,'BACKGROUND_SSH_KERNEL_FLAG')
        status=procfile('status',65536);values={}
        for line in status.splitlines():
            key,sep,value=line.partition(b':')
            if key in (b'Uid',b'Gid',b'Groups'):
                c.need(key not in values and sep and all(x.isdigit() for x in value.split()),'BACKGROUND_SSH_IDS')
                values[key]=[int(x) for x in value.split()]
        c.need(set(values)=={b'Uid',b'Gid',b'Groups'} and values[b'Uid']==[1002]*4 and
               len(values[b'Gid'])==4 and len(values[b'Groups'])<=128 and
               len(set(values[b'Groups']))==len(values[b'Groups']) and
               all(0<=x<2**32 for x in values[b'Gid']+values[b'Groups']),'BACKGROUND_SSH_ID_FIELDS')
        comm=procfile('comm',256).rstrip(b'\n');c.need(comm==b'ssh','BACKGROUND_SSH_COMM')
        argv=procfile('cmdline',65536);c.need(argv and argv.endswith(b'\0'),'BACKGROUND_SSH_ARGV')
        cgroup=procfile('cgroup',65536);systemd=[]
        for line in cgroup.decode('utf-8','strict').splitlines():
            parts=line.split(':',2);c.need(len(parts)==3,'BACKGROUND_SSH_CGROUP')
            if parts[1]=='name=systemd':systemd.append(parts[2])
        c.need(len(systemd)==1,'BACKGROUND_SSH_SYSTEMD_CGROUP_REQUIRED')
        if systemd[0]!='/':c.path(systemd[0])
        c.need(not set(systemd[0].split('/'))&set(c.WRITER_UNITS),'BACKGROUND_SSH_WRITER_CGROUP')
        digest,image_identity=self._ssh_image(pid)
        last=procfile('stat',65536);tail=last[last.rfind(b')')+2:].split()
        c.need(len(tail)>=20 and int(tail[19])==started and not int(tail[6])&0x00200000,'BACKGROUND_SSH_PID_REUSE')
        identity={'pid':int(pid),'starttime':started,'uids':values[b'Uid'],'gids':values[b'Gid'],
            'groups':sorted(set(values[b'Groups'])),'comm':'ssh','executable':'/usr/bin/ssh',
            'executable_sha256':digest,'argv_sha256':c.sha(argv),'unit':None,'kernel_thread':False}
        return identity,{'cgroup_sha256':c.sha(cgroup),'executable_identity':image_identity}

    def _process_scan(self, database_paths):
        identities = {(os.lstat(p).st_dev, os.lstat(p).st_ino) for root in database_paths
                      for p in (root, root+'-wal', root+'-shm', root+'-journal') if os.path.lexists(p)}
        pids = sorted(n for n in os.listdir('/proc') if n.isdigit()); c.need(len(pids) <= 65536, 'PROCESS_BOUND')
        result, fd_count, background = {}, 0, []
        for pid in pids:
            if int(pid) == os.getpid(): continue
            base = '/proc/' + pid
            def procfile(name, limit):
                with open(base + '/' + name, 'rb') as stream:
                    raw = stream.read(limit+1)
                c.need(len(raw) <= limit, 'PROC_BOUND'); return raw
            first = procfile('stat', 65536); status = procfile('status', 65536); comm = procfile('comm', 256).strip()
            close = first.rfind(b')'); fields = first[close+2:].split()
            c.need(close > 0 and len(fields) >= 20, 'PROC_STAT'); started = int(fields[19])
            uidlines = [r.split()[1:] for r in status.splitlines() if r.startswith(b'Uid:')]
            c.need(len(uidlines) == 1 and len(uidlines[0]) == 4 and all(v.isdigit() for v in uidlines[0]), 'PROC_UID')
            uids = tuple(int(v) for v in uidlines[0])
            c.need(not comm.startswith((b'Runner.Listener', b'Runner.Worker')) and
                   not set(uids) & {1003,1004,1005,1008}, 'WRITER_ACCOUNT_PROCESS')
            ssh_before=None
            if 1002 in uids:
                c.need(set(uids) == {1002} and os.readlink(base + '/exe') == '/usr/bin/ssh', 'OLD_WORKER_PROCESS')
                c.need(len(background)<128,'BACKGROUND_SSH_COUNT_BOUND')
                ssh_before=self._ssh_identity(int(pid),procfile)
            fd_names = sorted(os.listdir(base + '/fd'))
            for name in fd_names:
                fd_count += 1; c.need(fd_count <= 1000000, 'FD_SCAN_BOUND')
                info = os.stat(base + '/fd/' + name)
                c.need((info.st_dev, info.st_ino) not in identities, 'DATABASE_FD_HOLDER')
            c.need(sorted(os.listdir(base + '/fd')) == fd_names and procfile('status', 65536).split(b'Uid:',1)[1].splitlines()[0] == status.split(b'Uid:',1)[1].splitlines()[0], 'PROC_FD_OR_UID_RACE')
            last = procfile('stat', 65536); tail = last[last.rfind(b')')+2:].split()
            c.need(len(tail) >= 20 and int(tail[19]) == started, 'PID_REUSE')
            if ssh_before is not None:
                ssh_after=self._ssh_identity(int(pid),procfile)
                c.need(ssh_before==ssh_after and ssh_before[0]['starttime']==started,'BACKGROUND_SSH_IDENTITY_CHANGED')
                background.append({'before':ssh_before[0],'after':ssh_after[0]})
            result[pid] = {'starttime': started, 'uids': list(uids)}
        c.need(sorted(n for n in os.listdir('/proc') if n.isdigit()) == pids, 'PROCESS_SCAN_RACE')
        return {'process_identity_sha256': d.digest(result), 'fd_count': fd_count,
                'background_processes':background,'background_processes_sha256':d.digest(background)}

    def full_hostname(self):
        return socket.gethostname()

    def canonical_python(self, reference):
        c.need(reference in PYTHON_REFERENCES, 'PROBE_PYTHON_REFERENCE_SCOPE')
        # A bounded descriptor-checked alias chain, never realpath authority.
        return self.executable_reference(reference)['final']['path']

    def probe_manager(self):
        target = os.readlink('/proc/1/exe')
        c.need(target in ('/usr/lib/systemd/systemd','/lib/systemd/systemd') and
               os.path.realpath(target) == target, 'PROBE_CANONICAL_MANAGER')
        return self._manager(probe_path=target)

    def unit_nss(self):
        pairs=(('root','root'),('xuanjun-dispatcher','xuanjun-dispatcher'),
            ('xuanjun-dispatcher','xuanjun-control-db'),('xuanjun-callback','xuanjun-control-db'),
            ('xuanjun_dev','xuanjun_dev'),('nginx','nginx'))
        expected={'root':0,'xuanjun-dispatcher':1003,'xuanjun-callback':1004,'xuanjun_dev':1002}
        accounts={};groups={};by_primary={};rows=[];unsupported={}
        for name in ('root','xuanjun-dispatcher','xuanjun-control-db','xuanjun-ledger-client','xuanjun_dev','docker','nginx'):
            try:
                row=grp.getgrnam(name);c.need(row.gr_name==name and type(row.gr_gid) is int and row.gr_gid>=0,'UNIT_NSS_GROUP')
                groups[name]=row.gr_gid
            except (KeyboardInterrupt,SystemExit):raise
            except Exception as error:
                from probe_metadata import error_label
                unsupported['group:'+name]=error_label(error)
        for user,group in pairs:
            try:
                account=pwd.getpwnam(user);primary=groups[group]
                c.need(pwd.getpwuid(account.pw_uid).pw_name==user and
                       (account.pw_uid==expected[user] if user in expected else account.pw_uid>0),'UNIT_NSS_UID')
                actual=sorted(set(os.getgrouplist(user,primary)))
                c.need(actual==sorted(set(os.getgrouplist(user,primary))) and primary in actual,'UNIT_NSS_GROUP_RACE')
                by_primary.setdefault(user,{})[str(primary)]=actual
                rows.append({'user':user,'uid':account.pw_uid,'group':group,'gid':primary,'groups':actual})
                accounts[user]={'uid':account.pw_uid,'primary_gid':account.pw_gid,
                    'global_group_gids':sorted(set(os.getgrouplist(user,account.pw_gid)))}
            except (KeyboardInterrupt,SystemExit):raise
            except Exception as error:
                from probe_metadata import error_label
                unsupported[user+':'+group]=error_label(error)
        return {'accounts':accounts,'named_groups':groups,'nss_by_primary':by_primary,
                'unit_pairs':rows,'unsupported':unsupported}

    def online_cpus(self):
        first=os.sysconf('SC_NPROCESSORS_ONLN')
        c.need(type(first) is int and 1<=first<=4096 and os.sysconf('SC_NPROCESSORS_ONLN')==first,
               'ONLINE_CPU_COUNT_OR_RACE')
        return first

    def python_reference(self):return self.executable_reference('/usr/bin/python3')

    def executable_reference(self,reference):
        scopes={path:set(PYTHON_REFERENCES) for path in PYTHON_REFERENCES}
        scopes.update({'/usr/sbin/runuser':{'/usr/sbin/runuser','/usr/bin/runuser'},
                '/usr/sbin/nginx':{'/usr/sbin/nginx','/usr/bin/nginx'}}
        )
        c.need(reference in scopes,'EXECUTABLE_REFERENCE_SCOPE');allowed=scopes[reference]
        def walk():
            current=reference;links=[];seen=set()
            while True:
                c.need(current in allowed and current not in seen and len(seen)<8,'EXECUTABLE_ALIAS_SCOPE_OR_LOOP')
                seen.add(current)
                with self.parent(current) as (parent,name):
                    before=os.stat(name,dir_fd=parent,follow_symlinks=False)
                    pair = reference in PYTHON_REFERENCES and current == python_identity.PYTHON_PATHS[0]
                    c.need(before.st_uid==before.st_gid==0 and
                           (before.st_nlink==2 if pair and stat.S_ISREG(before.st_mode) else before.st_nlink==1),
                           'EXECUTABLE_ALIAS_AUTHORITY')
                    if stat.S_ISLNK(before.st_mode):
                        link=os.readlink(name,dir_fd=parent)
                        c.need(type(link) is str and 0<len(link)<=4096 and
                               __import__('re').fullmatch(r'/?[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*',link) and
                               all(part not in ('.','..') for part in link.split('/')), 'EXECUTABLE_ALIAS_TARGET_FORM')
                        c.need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==stamp(before),'EXECUTABLE_ALIAS_RACE')
                        links.append({'path':current,'link':link,'metadata':metadata(before)})
                    else:
                        c.need(stat.S_ISREG(before.st_mode),'EXECUTABLE_ALIAS_FINAL_TYPE');link=None
                if link is None:
                    raw,row=(self.read_python(current,maximum=33554432) if pair else
                             self.read(current,maximum=33554432))
                    c.need(all(row.get(k)==v for k,v in metadata(before).items()),'EXECUTABLE_ALIAS_FINAL_RACE')
                    c.need(raw.startswith(b'\x7fELF') and row['uid']==row['gid']==0 and row['mode']&0o111,'EXECUTABLE_ALIAS_FINAL_ELF')
                    return {'reference_path':reference,'links':links,
                        'final':{'path':current,'sha256':row['sha256'],'format':'ELF','metadata':row}}
                current=os.path.normpath(link if link.startswith('/') else os.path.join(os.path.dirname(current),link))
        first=walk();c.need(walk()==first,'EXECUTABLE_ALIAS_CHAIN_CHANGED');return first

    def unit_dropins(self, units):
        expected={'xuanjun-uk-openclaw.service','xuanjun-p2-gateway-relay.service',
            'xuanjun-development-dispatcher.service','xuanjun-ledger.service',
            'xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service','xj-root-broker.service','nginx.service'}
        sockets={'xj-root-broker.socket','xuanjun-ledger.socket','xuanjun-p2-gateway-relay.socket'}
        # Existing quiet/startup callers retain their exact service-only scope.
        # The collector additionally measures all three fixed socket closures.
        requested=set(units)
        c.need(requested==expected or requested==expected|sockets,'UNIT_DROPIN_SCOPE')
        expected=requested
        def inventory(root):
            if self.absent(root):return {'present':False,'files':{}}
            with self.parent(root) as (parent,name):
                before=os.stat(name,dir_fd=parent,follow_symlinks=False)
                fd=os.open(name,DIRFLAGS,dir_fd=parent)
                try:
                    self._authority(fd,root);c.need(stamp(os.fstat(fd))==stamp(before),'DROPIN_DIRECTORY_RACE')
                    names=sorted(os.listdir(fd));c.need(len(names)<=16,'DROPIN_FILE_BOUND')
                    files={}
                    for leaf in names:
                        c.need(__import__('re').fullmatch(r'[A-Za-z0-9_.-]+\.conf',leaf),'DROPIN_FILENAME')
                        raw,row=self.read(root+'/'+leaf,maximum=65536)
                        c.need(row['uid']==row['gid']==0,'DROPIN_FILE_OWNER');files[root+'/'+leaf]=(raw,row)
                    c.need(sorted(os.listdir(fd))==names and stamp(os.fstat(fd))==stamp(before),'DROPIN_DIRECTORY_CHANGED')
                finally:os.close(fd)
            return {'present':True,'files':files}
        result={}
        for unit in sorted(expected):
            result[unit]={}
            for prefix in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system'):
                root=prefix+'/'+unit+'.d'
                try:result[unit][root]=inventory(root)
                except (KeyboardInterrupt,SystemExit):raise
                except Exception as error:
                    from probe_metadata import error_label
                    result[unit][root]={'present':None,'files':{},'state':'UNKNOWN','reason':error_label(error)}
        return result

    def verify_node_descriptor(self,path,expected):
        """Rebind a full-hashed retained component and inspect ELF magic without executing it."""
        c.path(path);c.need(path.startswith('/home/xuanjun_dev/') and path.endswith('/node'),'OPENCLAW_NODE_SCOPE')
        c.need(expected['kind']=='FILE' and expected['uid']==expected['gid']==1002 and expected['nlink']==1 and
               expected['mode']&0o100 and not expected['mode']&0o7022 and 0<expected['size']<=268435456,
               'OPENCLAW_NODE_AUTHORITY')
        with self.parent(path) as (parent,name):
            before=os.stat(name,dir_fd=parent,follow_symlinks=False)
            c.need(stat.S_ISREG(before.st_mode) and all(metadata(before)[k]==expected[k] for k in metadata(before)),
                   'OPENCLAW_NODE_METADATA_CHANGED')
            fd=os.open(name,FLAGS,dir_fd=parent)
            try:
                c.need(stamp(os.fstat(fd))==stamp(before) and os.read(fd,4)==b'\x7fELF' and
                       stamp(os.fstat(fd))==stamp(before),'OPENCLAW_NODE_ELF_OR_RACE')
            finally:os.close(fd)
            c.need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==stamp(before),'OPENCLAW_NODE_PATH_RACE')
        return {'path':path,'sha256':expected['sha256'],'metadata':{k:expected[k] for k in
            ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns')}}

    def _node_directory_reference(self, expected_exe, expected_sha256, measurement_only=False):
        """Measure the one fixed directory alias; never follow a discovered path.

        Each round opens the canonical fixed chain with O_NOFOLLOW, streams at
        most256MiB, and rechecks all held descriptors, path links and xattrs.
        Unknown target, writable ancestry or any race remains a HOLD.
        """
        import unit_metadata as u
        c.need(expected_exe==u.NODE_CANONICAL_PATH,'NODE_REFERENCE_CANONICAL_SCOPE');d.hash_value(expected_sha256)
        def attributes(fd):
            names=(('access_acl','system.posix_acl_access'),('default_acl','system.posix_acl_default'),
                   ('capability','security.capability'))
            c.need(all(xattr(fd,name) is None for key,name in names),'NODE_REFERENCE_XATTR_PRESENT_OR_UNKNOWN')
            return {key:False for key,name in names}
        def round_():
            self.check_locks();held=[];directories={};links=[];primary=None
            try:
                current=os.open(self.root,DIRFLAGS);held.append(current);root=current
                first=os.fstat(root)
                c.need(stamp(first)[:5]==self.root_identity,'NODE_REFERENCE_ROOT_CHANGED')
                self._authority(root,'/');directories['/']=(root,first)
                at='';tools_fd=None;alias_before=None;target=None
                for part in ('home','xuanjun_dev','.openclaw','tools','node-v24.21.0','bin'):
                    at+='/'+part
                    before=os.stat(part,dir_fd=current,follow_symlinks=False)
                    child=os.open(part,DIRFLAGS,dir_fd=current);held.append(child)
                    c.need(stamp(os.fstat(child))==stamp(before),'NODE_REFERENCE_DIRECTORY_OPEN_RACE')
                    narrowable=(measurement_only and at in (u.NODE_TOOLS,u.NODE_VERSION_DIRECTORY) and
                                stat.S_ISDIR(before.st_mode) and
                                (before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode))==(1002,1002,0o775))
                    if not narrowable:self._authority(child,at)
                    directories[at]=(child,before)
                    links.append((current,part,before));current=child
                    if at==u.NODE_TOOLS:
                        tools_fd=current;alias_before=os.stat('node',dir_fd=tools_fd,follow_symlinks=False)
                        c.need(stat.S_ISLNK(alias_before.st_mode),'NODE_REFERENCE_DIRECTORY_ALIAS_TYPE')
                        target=os.readlink('node',dir_fd=tools_fd)
                        c.need(target in ('node-v24.21.0',u.NODE_VERSION_DIRECTORY),'NODE_REFERENCE_EXACT_TARGET')
                        c.need(stamp(os.stat('node',dir_fd=tools_fd,follow_symlinks=False))==stamp(alias_before),
                               'NODE_REFERENCE_ALIAS_OPEN_RACE')
                ancestor_rows={path:dict(metadata(info),kind='DIRECTORY',**attributes(fd))
                               for path,(fd,info) in directories.items()}
                before=os.stat('node',dir_fd=current,follow_symlinks=False)
                c.need(stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==1002 and
                       before.st_nlink==1 and before.st_mode&0o100 and not before.st_mode&0o7022 and
                       0<before.st_size<=u.NODE_MAXIMUM,'NODE_REFERENCE_ELF_AUTHORITY')
                fd=os.open('node',FLAGS,dir_fd=current);held.append(fd)
                c.need(stamp(os.fstat(fd))==stamp(before),'NODE_REFERENCE_FILE_OPEN_RACE')
                attrs=attributes(fd);digest=hashlib.sha256();count=0;magic=b''
                while True:
                    self.check_locks()
                    chunk=os.read(fd,min(65536,u.NODE_MAXIMUM+1-count))
                    if not chunk:break
                    if len(magic)<4:magic=(magic+chunk)[:4]
                    count+=len(chunk);c.need(count<=u.NODE_MAXIMUM,'NODE_REFERENCE_FILE_BOUND');digest.update(chunk)
                c.need(count==before.st_size and magic==b'\x7fELF' and digest.hexdigest()==expected_sha256,
                       'NODE_REFERENCE_RETAINED_ELF_HASH')
                row=dict(metadata(before),kind='FILE',sha256=digest.hexdigest(),elf_header=True,**attrs)
                c.need(stamp(os.fstat(fd))==stamp(before) and
                       stamp(os.stat('node',dir_fd=current,follow_symlinks=False))==stamp(before) and
                       attributes(fd)==attrs,'NODE_REFERENCE_FILE_REREAD_RACE')
                c.need(os.readlink('node',dir_fd=tools_fd)==target and
                       stamp(os.stat('node',dir_fd=tools_fd,follow_symlinks=False))==stamp(alias_before),
                       'NODE_REFERENCE_ALIAS_REREAD_RACE')
                for parent,name,info in reversed(links):
                    c.need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==stamp(info),
                           'NODE_REFERENCE_DIRECTORY_PATH_RACE')
                for path,(directory,info) in directories.items():
                    c.need(stamp(os.fstat(directory))==stamp(info) and
                           attributes(directory)=={key:ancestor_rows[path][key] for key in ('access_acl','default_acl','capability')},
                           'NODE_REFERENCE_DIRECTORY_REREAD_RACE')
                c.need(stamp(os.lstat(self.root))==stamp(first),'NODE_REFERENCE_ROOT_PATH_RACE')
                value={'schema':1,'kind':'FIXED_NODE_DIRECTORY_ALIAS','reference_path':u.NODE_REFERENCE_PATH,
                    'link':{'path':u.NODE_ALIAS_PATH,'target':target,'metadata':dict(metadata(alias_before),kind='SYMLINK')},
                    'final':{'path':expected_exe,'sha256':expected_sha256,'metadata':row},
                    'ancestors':ancestor_rows,'reread':'EXACT_PRE_POST'}
                if measurement_only:
                    value.update(kind='FIXED_NODE_DIRECTORY_ALIAS_MEASUREMENT',admission='NOT_GRANTED',
                        unsafe_ancestors=sorted(path for path,row in ancestor_rows.items() if row['mode']&0o022))
                    return u.validate_node_reference_measurement(value,expected_exe,expected_sha256)
                return u.validate_node_reference(value,expected_exe,expected_sha256)
            except BaseException as error:
                primary=error;raise
            finally:
                failure=None
                for fd in reversed(held):
                    # A signal can interrupt close after the kernel released
                    # this descriptor. Never retry that ambiguous descriptor.
                    try:os.close(fd)
                    except BaseException as error:
                        if failure is None:failure=error
                if failure is not None:
                    raise (primary if primary is not None else failure) from ValueError('NODE_REFERENCE_CLEANUP_UNKNOWN')
        first=round_();last=round_();self.check_locks()
        c.need(first==last,'NODE_REFERENCE_COMPLETE_ROUND_RACE');return last

    def node_directory_reference(self, expected_exe, expected_sha256):
        return self._node_directory_reference(expected_exe,expected_sha256)

    def measure_node_directory_reference(self, expected_exe, expected_sha256):
        return self._node_directory_reference(expected_exe,expected_sha256,measurement_only=True)

    def gateway_account_home(self):
        first=pwd.getpwnam('xuanjun_dev');second=pwd.getpwnam('xuanjun_dev')
        expected=('xuanjun_dev',1002,1002,'/home/xuanjun_dev')
        def selected(value):return (value.pw_name,value.pw_uid,value.pw_gid,value.pw_dir)
        c.need(selected(first)==selected(second)==expected,'OPENCLAW_ACCOUNT_HOME_REQUIRED')
        return {'user':'xuanjun_dev','uid':1002,'gid':1002,'home':first.pw_dir}

    def gateway_manager_environment(self):
        """Finite selected startup fields only. Never retain the raw manager environment."""
        from openclaw_metadata import ENV_KEYS,SELECTORS
        import shlex
        self.check_locks();manager=self.probe_manager();unused,tool=self.read('/usr/bin/systemctl',maximum=33554432)
        c.need(tool['uid']==tool['gid']==0 and tool['mode']&0o111,'OPENCLAW_MANAGER_TOOL_AUTHORITY')
        names=set(ENV_KEYS+SELECTORS)
        def query():
            raw=bounded_query(['/usr/bin/systemctl','show-environment'],timeout=min(5,self.deadline-time.monotonic()),maximum=65536)
            values={name:None for name in names};seen=set()
            for line in raw.decode('utf-8','strict').splitlines():
                name,sep,unused=line.partition('=')
                if name not in names:continue
                c.need(sep and name not in seen and len(line)<=4096,'OPENCLAW_MANAGER_ENVIRONMENT_FIELDS');seen.add(name)
                parsed=shlex.split(line);c.need(len(parsed)==1 and parsed[0].startswith(name+'='),'OPENCLAW_MANAGER_ENVIRONMENT_SYNTAX')
                values[name]=parsed[0][len(name)+1:]
            return values
        values=query();c.need(query()==values,'OPENCLAW_MANAGER_ENVIRONMENT_CHANGED')
        c.need(self.probe_manager()==manager and self.read('/usr/bin/systemctl',maximum=33554432)[1]==tool,
               'OPENCLAW_MANAGER_ENVIRONMENT_AUTHORITY_CHANGED')
        return {'selected':{k:values[k] for k in ENV_KEYS},'selectors':{k:values[k] for k in SELECTORS},
            'manager_sha256':d.digest(manager),'systemctl_sha256':tool['sha256'],
            'source':'SYSTEM_MANAGER_CHILD_ENVIRONMENT'}

    def dispatcher_manager_path(self):
        """Read only PATH from current system-manager child environment, never /proc environ."""
        self.check_locks();manager=self.probe_manager()
        unused,tool=self.read('/usr/bin/systemctl',maximum=33554432)
        c.need(tool['uid']==tool['gid']==0 and tool['mode']&0o111,'PATH_SYSTEMCTL_AUTHORITY')
        def query():
            import shlex
            raw=bounded_query(['/usr/bin/systemctl','show-environment'],timeout=min(5,self.deadline-time.monotonic()),maximum=65536)
            rows=[line for line in raw.decode('utf-8','strict').splitlines() if line.startswith('PATH=')]
            c.need(len(rows)==1 and len(rows[0])<=4096,'MANAGER_PATH_REQUIRED')
            parts=shlex.split(rows[0]);c.need(len(parts)==1 and parts[0].startswith('PATH='),'MANAGER_PATH_FORMAT')
            path=parts[0][5:];names=path.split(':')
            c.need(0<len(names)<=16 and len(set(names))==len(names) and
                   all(name in ('/usr/local/sbin','/usr/local/bin','/usr/sbin','/usr/bin','/sbin','/bin') for name in names),
                   'MANAGER_PATH_SCOPE')
            return path
        path=query();c.need(query()==path,'MANAGER_PATH_CHANGED');entries=[];first=None
        for directory in path.split(':'):
            c.need(os.path.realpath(directory)==directory,'MANAGER_PATH_NONCANONICAL_DIRECTORY')
            meta=self.directory(directory)
            c.need(meta['uid']==meta['gid']==0 and not meta['mode']&0o7022,'MANAGER_PATH_DIRECTORY_AUTHORITY')
            target=directory+'/git';git=None
            if not self.absent(target):
                c.need(target=='/usr/bin/git','MANAGER_PATH_GIT_SHADOWED_OR_UNSUPPORTED')
                raw,row=self.read(target,maximum=33554432)
                c.need(row['uid']==row['gid']==0 and row['mode']&0o111 and raw.startswith(b'\x7fELF'),'MANAGER_PATH_GIT_AUTHORITY')
                git={k:row[k] for k in ('sha256','dev','ino')};git['path']=target
                if first is None:first=target
            entries.append(dict({k:meta[k] for k in ('uid','gid','mode','dev','ino')},directory=directory,git=git))
        c.need(first=='/usr/bin/git','MANAGER_PATH_GIT_MISSING')
        c.need(self.read('/usr/bin/systemctl',maximum=33554432)[1]==tool and self.probe_manager()==manager,
               'MANAGER_PATH_AUTHORITY_CHANGED')
        return {'command':'git','path_environment':path,'entries':entries,
            'provenance':{'source':'SYSTEM_MANAGER_CHILD_ENVIRONMENT','systemctl_sha256':tool['sha256'],
                'manager_sha256':d.digest(manager),'upstream_version':'239','distro_matching_build':'NOT_VERIFIED'}}

    def boot_links(self):
        """Finite link evidence only; masking never implies restored enablement."""
        roots=('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system',
            '/run/systemd/system.control','/run/systemd/transient','/run/systemd/generator.early',
            '/run/systemd/generator','/run/systemd/generator.late')
        selected={'xuanjun-uk-openclaw.service','xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service'}
        result={};unsupported=[]
        def scan(root):
            if self.absent(root):return {'present':False,'directories':{},'links':[]}
            directories={};links={};selected_nonlinks={};count=[0]
            def directory(path,dependencies=False,depth=0):
                c.need(depth<=8 and len(directories)<1024,'BOOT_RECURSION_BOUND')
                with self.parent(path) as (parent,name):
                    before=os.stat(name,dir_fd=parent,follow_symlinks=False);fd=os.open(name,DIRFLAGS,dir_fd=parent)
                    try:
                        self._authority(fd,path);c.need(stamp(os.fstat(fd))==stamp(before),'BOOT_DIRECTORY_RACE')
                        names=sorted(os.listdir(fd));c.need(len(names)<=4096,'BOOT_DIRECTORY_ENTRY_BOUND')
                        children=[];rows=[]
                        for leaf in names:
                            c.need('/' not in leaf and leaf not in ('.','..'),'BOOT_ENTRY_NAME')
                            logical=path+'/'+leaf;info=os.stat(leaf,dir_fd=fd,follow_symlinks=False)
                            count[0]+=1;c.need(count[0]<=16384,'BOOT_INVENTORY_TOTAL_BOUND')
                            row={'name':leaf,'metadata':metadata(info),'kind':'OTHER'}
                            if stat.S_ISLNK(info.st_mode):
                                target=os.readlink(leaf,dir_fd=fd)
                                c.need(info.st_uid==info.st_gid==0 and info.st_nlink==1 and
                                       len(target)<=4096 and '\0' not in target,'BOOT_LINK_AUTHORITY')
                                c.need(stamp(os.stat(leaf,dir_fd=fd,follow_symlinks=False))==stamp(info),'BOOT_LINK_RACE')
                                links[logical]={'path':logical,'link':target,'metadata':metadata(info),
                                    'kind':'DEPENDENCY' if dependencies else 'ALIAS_OR_BASE'}
                                row.update(kind='LINK',target_sha256=c.sha(target.encode()))
                            elif dependencies and leaf in selected:
                                c.need(False,'BOOT_SELECTED_DEPENDENCY_NOT_LINK')
                            elif leaf in selected:
                                selected_nonlinks[logical]={'metadata':metadata(info),
                                    'kind':'FILE' if stat.S_ISREG(info.st_mode) else 'UNSUPPORTED_NONLINK'}
                            if leaf.endswith(('.wants','.requires')):
                                c.need(stat.S_ISDIR(info.st_mode),'BOOT_DEPENDENCY_DIRECTORY_TYPE')
                            if stat.S_ISDIR(info.st_mode):children.append(logical)
                            rows.append(row)
                        c.need(len(children)<=256,'BOOT_DEPENDENCY_DIRECTORY_BOUND')
                        c.need(sorted(os.listdir(fd))==names and stamp(os.fstat(fd))==stamp(before),'BOOT_DIRECTORY_CHANGED')
                        directories[path]={'metadata':metadata(before),'entry_count':len(names),'inventory_sha256':d.digest(rows)}
                    finally:os.close(fd)
                for child in children:directory(child,dependencies or child.endswith(('.wants','.requires')),depth+1)
            directory(root)
            selected_paths={prefix+'/'+unit for prefix in roots for unit in selected};matched=[]
            for path,row in sorted(links.items()):
                target=os.path.normpath(row['link'] if row['link'].startswith('/') else os.path.join(os.path.dirname(path),row['link']))
                visited=set()
                while target in links and target not in selected_paths:
                    c.need(target not in visited and len(visited)<8,'BOOT_ALIAS_CHAIN_UNSUPPORTED');visited.add(target)
                    link=links[target]['link'];target=os.path.normpath(link if link.startswith('/') else os.path.join(os.path.dirname(target),link))
                if os.path.basename(path) in selected or os.path.basename(target) in selected:
                    unit=os.path.basename(target) if os.path.basename(target) in selected else os.path.basename(path)
                    value=dict(row,unit=unit,resolved_reference=target)
                    if path==root+'/'+unit and target=='/dev/null':value['kind']='BASE_MASK'
                    matched.append(value)
            return {'present':True,'directories':directories,'links':matched,
                    'selected_nonlinks':selected_nonlinks,'scan_scope':'BOUNDED_RECURSIVE_NOFOLLOW',
                    'all_link_inventory_sha256':d.digest(links)}
        for root in roots:
            try:
                first=scan(root);c.need(scan(root)==first,'BOOT_LINK_INVENTORY_CHANGED');result[root]=first
            except (KeyboardInterrupt,SystemExit):raise
            except Exception as error:
                from probe_metadata import error_label
                result[root]={'state':'UNKNOWN','reason':error_label(error)};unsupported.append(root)
        return {'units':sorted(selected),'roots':result,'unsupported_roots':unsupported,
                'restored_enablement':'NOT_INFERRED','runtime_alias_semantics':'REQUIRES_SYSTEMD239_REVIEW'}

    def timer_schedule(self):
        """Exact stopped-renewal baseline properties, without timer operations."""
        self.check_locks()
        raw,tool=self.read('/usr/bin/systemctl',maximum=33554432)
        c.need(tool['uid']==tool['gid']==0 and tool['mode']&0o111,'TIMER_SYSTEMCTL_AUTHORITY')
        rows={}
        for unit,fields in sorted(TLS_TIMER_FIELDS.items()):
            args=['/usr/bin/systemctl','show',unit,'--property=Id,'+','.join(fields),'--no-pager']
            def query():
                self.check_locks()
                data=bounded_query(args,timeout=min(5,self.deadline-time.monotonic()),maximum=4096)
                values={}
                for line in data.decode('utf-8','strict').splitlines():
                    c.need('=' in line,'TIMER_PROPERTY_LINE')
                    key,value=line.split('=',1)
                    c.need(key in ('Id',)+fields and key not in values and len(value)<=128 and
                           not any(ord(ch)<32 for ch in value),'TIMER_PROPERTY_SCOPE_OR_BOUND')
                    values[key]=value
                c.need(values.pop('Id',None)==unit,'TIMER_PROPERTY_UNIT_IDENTITY')
                return values
            first=query();c.need(query()==first,'TIMER_PROPERTY_RACE');rows[unit]=first
        c.need(self.read('/usr/bin/systemctl',maximum=33554432)[1]==tool,'TIMER_SYSTEMCTL_RACE')
        return {'raw':rows,'systemctl_sha256':tool['sha256']}

    def probe_nss(self):
        profiles, accounts = {}, {}
        specs = {
            'ledger':('xuanjun-dispatcher',1003,'xuanjun-control-db',('xuanjun-dispatcher',),'yes'),
            'broker':('root',0,'root',('xuanjun-ledger-client',),'yes'),
            'dashboard':('xuanjun-callback',1004,'xuanjun-control-db',('xuanjun-ledger-client',),'yes'),
            'callback':('xuanjun-callback',1004,'xuanjun-control-db',('xuanjun-ledger-client',),'yes'),
            'native':('xuanjun_dev',1002,None,('docker','xuanjun-ledger-client'),'read-only')}
        for role, spec in specs.items():
            name, uid, primary_name, supplements, protect = spec
            user = pwd.getpwnam(name)
            c.need(user.pw_uid == uid and pwd.getpwuid(uid).pw_name == name, 'PROBE_NSS_UID')
            primary = grp.getgrgid(user.pw_gid) if primary_name is None else grp.getgrnam(primary_name)
            extra = {n:grp.getgrnam(n).gr_gid for n in supplements}
            profiles[role] = {'user':name,'uid':uid,'group':primary.gr_name,'gid':primary.gr_gid,
                'supplementary_groups':extra,'protect_home':protect}
            actual = sorted(set(os.getgrouplist(name,user.pw_gid)))
            accounts[name] = {'uid':uid,'primary_gid':user.pw_gid,'global_group_gids':actual}
        return {'profiles':profiles,'existing_accounts':accounts,
                'profile_group_semantics':'PROPOSED_UNIT_SCOPED_GROUPS_NO_NSS_CHANGE'}

    def _manager(self, probe_path=None):
        if probe_path is None:
            pin = self.policy['executables']['systemd']
        else:
            c.need(probe_path in ('/usr/lib/systemd/systemd','/lib/systemd/systemd'), 'PROBE_MANAGER_PATH')
            pin = {'path':probe_path}
        binary, meta = self.read(pin['path'], maximum=33554432)
        if probe_path is None: c.pin_matches(meta, self.policy['files'][pin['path']])
        else: c.need(meta['uid'] == meta['gid'] == 0 and meta['mode'] & 0o111, 'PROBE_MANAGER_AUTHORITY')
        c.need(os.readlink('/proc/1/exe') == pin['path'], 'ROOT_MANAGER_EXE_PATH')
        fd = os.open('/proc/1/exe', os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0))
        try:
            first = os.fstat(fd)
            c.need((first.st_dev, first.st_ino) == (meta['dev'], meta['ino']), 'ROOT_MANAGER_EXE_IDENTITY')
            c.need(stamp(os.fstat(fd)) == stamp(first), 'ROOT_MANAGER_EXE_RACE')
        finally: os.close(fd)
        def read_proc(name, limit):
            with open(name, 'rb') as stream: raw = stream.read(limit+1)
            c.need(len(raw) <= limit, 'ROOT_MANAGER_PROC_BOUND'); return raw
        status = read_proc('/proc/1/status', 65536)
        ids=manager_ids(status)
        process = read_proc('/proc/1/stat', 65536); fields = process[process.rfind(b')')+2:].split()
        c.need(len(fields) >= 20, 'ROOT_MANAGER_STAT')
        boot = read_proc('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip()
        c.need(str(__import__('uuid').UUID(boot)) == boot, 'BOOT_ID')
        channels = {}
        for name in ('/run/systemd/private', '/run/dbus/system_bus_socket'):
            with self.parent(name) as (parent, leaf):
                info = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                c.need(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0 and info.st_gid == 0, 'MANAGER_CHANNEL_AUTHORITY')
                channels[name] = metadata(info)
        last=read_proc('/proc/1/stat',65536);tail=last[last.rfind(b')')+2:].split()
        c.need(len(tail)>=20 and tail[19]==fields[19] and manager_ids(read_proc('/proc/1/status',65536))==ids and
               os.readlink('/proc/1/exe')==pin['path'] and self.read(pin['path'],maximum=33554432)[1]==meta,
               'ROOT_MANAGER_IDENTITY_RACE')
        return dict(ids,boot_id=boot,pid=1,starttime=int(fields[19]),binary_sha256=meta['sha256'],binary_path=pin['path'],
                binary_identity=[meta['dev'],meta['ino']],channels=channels)

    def writers(self, policy, database_paths):
        self.check_locks()
        manager = self._manager()
        with open('/proc/self/mountinfo', 'rb') as stream: reviewed.validate_systemd_mountinfo(stream.read(1048577))
        units = {}
        for name in sorted(c.WRITER_UNITS):
            first = self._unit(name)
            cg = reviewed.bounded_file_inventory('/sys/fs/cgroup/systemd/system.slice/' + name, optional=True, cgroup=True)
            c.need(self._unit(name) == first, 'UNIT_CGROUP_RACE')
            units[name] = {'state': first, 'cgroup_entries': cg}
        masks = {name: self.mask(name) for name in c.LEGACY_MASKS}
        for name in c.LEGACY_MASKS:
            c.need(units[os.path.basename(name)]['state']['UnitFileState'] == 'masked', 'LEGACY_MASK_MANAGER')
        scheduler = {}
        for root in sorted(c.SCHEDULER_ROOTS): scheduler.update(reviewed.bounded_file_inventory(root, optional=True))
        c.need(scheduler == policy['scheduler_files'], 'SCHEDULER_CHANGED')
        listed = self.command('systemctl', ['list-unit-files', '--no-legend', '--no-pager']).decode('utf-8', 'strict')
        names = set(line.split()[0] for line in listed.splitlines() if line.split() and line.split()[0].startswith(('xj-', 'xuanjun-')))
        c.need(names == set(policy['control_units']), 'CONTROL_UNIT_INVENTORY_CHANGED')
        control = {}
        for unit, paths in policy['control_units'].items():
            for name, digest in paths.items():
                if name in c.LEGACY_MASKS:
                    control[name] = self.mask(name)
                else:
                    data, info = self.read(name); c.need(c.sha(data) == digest, 'CONTROL_SCRIPT_CHANGED'); control[name] = info
        c.need(all(h==c.sha(b'') for row in units.values() for h in row['cgroup_entries'].values()),
               'BACKGROUND_FIXED_WRITER_CGROUP_NOT_EMPTY')
        processes = self._process_scan(database_paths)
        with open('/proc/self/mountinfo', 'rb') as stream: reviewed.validate_systemd_mountinfo(stream.read(1048577))
        c.need(self._manager() == manager, 'ROOT_MANAGER_CHANGED')
        return {'manager': manager, 'units': units, 'masks': masks, 'scheduler_sha256': d.digest(scheduler),
                'control_files': control, 'processes': processes}


@contextlib.contextmanager
def existing_locks(reader, policy):
    locks = {}; held = []; primary = None
    try:
        for name in (c.INSTALL_LOCK, c.ACTIVATION_LOCK):
            data, row = reader.read(name); c.pin_matches(row, policy['files'][name])
            with reader.parent(name) as (parent, leaf):
                fd = os.open(leaf, FLAGS, dir_fd=parent); held.append(fd)
                first = stamp(os.fstat(fd)); c.need(metadata(os.fstat(fd)) == {k: row[k] for k in metadata(os.fstat(fd))}, 'LOCK_OPEN_RACE')
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locks[name] = (fd, first)
        yield locks
    except BaseException as error:
        primary = error; raise
    finally:
        failure = None
        for fd in reversed(held):
            # One attempt per owned descriptor, including failed setup. An
            # interrupted close is ambiguous and must never be retried.
            try: os.close(fd)
            except BaseException as error:
                if failure is None: failure = error
        if failure is not None:
            raise (primary if primary is not None else failure) from ValueError('EXISTING_LOCKS_CLEANUP_UNKNOWN')


def collect_host(policy_path, policy_sha256):
    """Explicit callable only. Missing current expected pins prevents all collection.

    The outer reviewed loader must authenticate these source bytes before import
    and preserve the private returned evidence. This does not grant admission.
    """
    c.need(os.geteuid() == 0 and socket.gethostname().split('.')[0] == c.HOST, 'FIXED_HOST_ROOT_REQUIRED')
    d.hash_value(policy_sha256); c.path(policy_path)
    c.need(policy_path.startswith(c.CAND + '/') and os.path.realpath(policy_path) == policy_path, 'PROTECTED_POLICY_SCOPE')
    # Bootstrap only the root-owned policy ancestry; no historical pins reused.
    pins = {}; parent = os.path.dirname(policy_path)
    while True:
        info = os.lstat(parent)
        c.need(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022, 'POLICY_ANCESTOR')
        pins[parent] = {k: metadata(info)[k] for k in ('uid', 'gid', 'mode')}
        if parent == '/': break
        parent = os.path.dirname(parent)
    bootstrap = DescriptorReader(pins); raw, info = bootstrap.read(policy_path)
    c.pin_matches(info, {'sha256': policy_sha256, 'uid': 0, 'gid': 0, 'mode': 0o600})
    policy = c.validate_policy(c.decode(raw)); reader = DescriptorReader(policy['directories'])
    with existing_locks(reader, policy) as locks:
        backend = LocalReadOnlyIO(policy, locks)
        result = c.collect(policy, backend)
        c.need(bootstrap.read(policy_path) == (raw, info), 'POLICY_CHANGED_DURING_COLLECTION')
        return result
