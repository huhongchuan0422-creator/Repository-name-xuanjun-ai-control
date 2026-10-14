"""Review candidate only. No automatic workflow invokes this production CLI.

Scope PR17:6151722263. Execute only after exact candidate review acceptance.
No restore/restart/replay operation; partial failures preserve a HOLD journal.
"""
import argparse
import fcntl
import hashlib
import json
import os
import socket
import stat
import subprocess

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
TX = 'c529c379-9341-4510-8384-fc6be1e412e5'
OLD = BASE + '/legacy-isolation-' + TX
TIMER = 'xj-uk-owner-notify.timer'
SERVICE = 'xj-uk-owner-notify.service'
UNITS = (TIMER, SERVICE)
UNIT_HASHES = {
    TIMER: 'ee6fad9d05fe8a9e819deea7b1e2e57de86af4463d33af36290ef0380975ae31',
    SERVICE: '5ec0e6323b5f6cd3f7b1f6624273159286c18aed2bc8a9feef6dbe97ea0a65f4',
}
CODE = '/home/xuanjun_dev/uk-owner-notify/owner_notify.py'
CODE_HASH = '3b61c5b7e85848151c76166a18ecbdb9b9f88f310e9571e3b3ae833d6e8ac602'
DB = '/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
DB_HASH = 'a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60'
PRIOR_HASHES = {
    'owner-isolation-receipt.json': '70d8e244f7f72c15a16299b9eef19670cd7cdee452b1913d864af93c2f4824bc',
    'legacy-units.json': 'fe57912b31e42665a895a1e0d7c64fde5cebaff6a99394d0183a3fe3d95ab7c1',
    'xuanjun-uk-stage1-minimal.service.backup': '5fcf0cd435a1d1cc37c7721648376f04af7a82defa83936097f28084595187da',
    'xuanjun-uk-openclaw.service.backup': '6ae3a87b472242e26347de88f6ed882ed3641b3bdfa7ab9eae9e355399b23348',
    'auxiliary-owner/auxiliary-isolation-receipt.json': 'd754368b2f7357de6a38015c0be119ba9fbf16e3847ec174451273820a2ec32b',
    'auxiliary-owner/xuanjun-uk-owner-callback.service.backup': '22928c11c1e4e3e56b2d17b9d8f8f292f705b52df41072c01a6cd767cae5fbc0',
    'auxiliary-owner/xuanjun-uk-owner-dashboard.service.backup': 'bd7b554a396951020d4d7216a7926f12afc26da53af87814d308439c1a954f61',
}
PRIOR_UNITS = ('xuanjun-uk-stage1-minimal.service', 'xuanjun-uk-openclaw.service',
               'xuanjun-uk-owner-callback.service', 'xuanjun-uk-owner-dashboard.service')


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def isolate(adapter, acceptance):
    """Reviewable effect order; adapter validates fixed production identities."""
    before = adapter.preflight()
    adapter.begin(before, acceptance)
    stage = 'BACKUPS_READY'
    try:
        adapter.recheck()
        stage = 'TIMER_STOP_INTENT'
        adapter.record(stage)
        adapter.stop(TIMER)
        adapter.quiet(TIMER)
        adapter.recheck()
        stage = 'SERVICE_STOP_INTENT'
        adapter.record(stage)
        adapter.stop(SERVICE)
        adapter.quiet(SERVICE)
        adapter.recheck()
        for unit in UNITS:
            adapter.quiet(unit)
            stage = 'MASK_INTENT:' + unit
            adapter.record(stage)
            adapter.mask(unit)
        stage = 'RELOAD_INTENT'
        adapter.record(stage)
        adapter.reload()
        after = adapter.verify()
        adapter.record('AUTHORIZED_NOTIFIER_ISOLATED', after=after)
        return after
    except Exception as error:
        # Error code only; never emit subprocess output or arbitrary file contents.
        adapter.record('HOLD_NOTIFIER_ISOLATION', failed_stage=stage,
                       error_type=type(error).__name__)
        raise


class FixedHost(object):
    def __init__(self):
        self.lock = None
        self.directory = None
        self.receipt = None
        self.payloads = {}
        self.fingerprints = {}
        self.masked = set()
        self.database_files = None

    def close(self):
        for fd in (self.directory, self.lock):
            if fd is not None:
                os.close(fd)

    def read(self, path, root_private=False):
        require(os.path.realpath(path) == path, 'PATH_ALIAS_HOLD')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and info.st_size <= 1048576, 'UNSAFE_BOUNDED_FILE')
            if root_private:
                require(info.st_uid == 0 and info.st_gid == 0
                        and stat.S_IMODE(info.st_mode) == 0o600, 'PRIVATE_FILE_REQUIRED')
            raw = stream.read(1048577)
            require(len(raw) <= 1048576, 'FILE_BOUND_EXCEEDED')
        return raw, info

    def show(self, unit):
        require(unit in UNITS + PRIOR_UNITS, 'UNIT_OUTSIDE_SCOPE')
        args = ['/usr/bin/systemctl', 'show', unit,
                '--property=Id,LoadState,FragmentPath,ActiveState,SubState,MainPID,ControlGroup,UnitFileState']
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        require(result.returncode == 0 and len(result.stdout) <= 65536, 'UNIT_READ_FAILED')
        return dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)

    def members(self, unit):
        require(unit in UNITS + PRIOR_UNITS, 'CGROUP_OUTSIDE_SCOPE')
        root = '/sys/fs/cgroup/systemd/system.slice/' + unit
        require(os.path.isdir('/sys/fs/cgroup/systemd'), 'CGROUP_HIERARCHY_UNAVAILABLE')
        try:
            root_info = os.lstat(root)
        except FileNotFoundError:
            # systemd removes empty unit cgroups after a stopped/masked unit.
            # quiet() independently requires inactive/dead and PID0 before here.
            return []
        require(stat.S_ISDIR(root_info.st_mode) and not stat.S_ISLNK(root_info.st_mode),
                'CGROUP_ALIAS_OR_TYPE_HOLD')
        found = set()
        count = 0
        def fail_walk(error):
            raise error
        for directory, children, files in os.walk(root, followlinks=False, onerror=fail_walk):
            count += 1
            require(count <= 4096, 'CGROUP_SCAN_BOUND')
            require(not any(os.path.islink(os.path.join(directory, c)) for c in children),
                    'NESTED_CGROUP_ALIAS_HOLD')
            if 'cgroup.procs' in files:
                fd = os.open(directory + '/cgroup.procs', os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd) as stream:
                    raw = stream.read(65537)
                require(len(raw) <= 65536, 'CGROUP_MEMBER_BOUND')
                found.update(int(v) for v in raw.split())
        return sorted(found)

    def quiet(self, unit):
        value = self.show(unit)
        require(value.get('Id') == unit and value.get('ActiveState') == 'inactive'
                and value.get('SubState') == 'dead', 'UNIT_NOT_QUIET')
        if unit.endswith('.service'):
            require(value.get('MainPID') == '0', 'SERVICE_PID_REMAINS')
        require(not self.members(unit), 'CGROUP_MEMBERS_REMAIN')
        return value

    def evidence(self):
        for name, wanted in PRIOR_HASHES.items():
            raw, _ = self.read(OLD + '/' + name, root_private=True)
            require(sha(raw) == wanted, 'PRIOR_EVIDENCE_DRIFT')
        for unit in PRIOR_UNITS:
            value = self.quiet(unit)
            path = '/etc/systemd/system/' + unit
            require(os.path.islink(path) and os.readlink(path) == '/dev/null'
                    and value.get('UnitFileState') == 'masked', 'PRIOR_MASK_DRIFT')
        raw, _ = self.read(DB)
        require(sha(raw) == DB_HASH, 'DATABASE_DRIFT')
        for suffix in ('-wal', '-journal'):
            if os.path.lexists(DB + suffix):
                info = os.lstat(DB + suffix)
                require(stat.S_ISREG(info.st_mode) and info.st_size == 0,
                        'NONEMPTY_OR_UNSAFE_DB_JOURNAL')
        files = {}
        for path in (DB, DB + '-wal', DB + '-shm', DB + '-journal'):
            if os.path.lexists(path):
                content, info = self.read(path)
                files[path] = {'sha256': sha(content), 'size': len(content),
                               'device': info.st_dev, 'inode': info.st_ino,
                               'uid': info.st_uid, 'gid': info.st_gid,
                               'mode': stat.S_IMODE(info.st_mode)}
        if self.database_files is None:
            self.database_files = files
        else:
            require(files == self.database_files, 'DATABASE_FILE_SET_DRIFT')
        raw, _ = self.read(CODE)
        require(sha(raw) == CODE_HASH, 'NOTIFIER_CODE_DRIFT')

    def preflight(self):
        require(os.geteuid() == 0 and socket.gethostname().split('.')[0] == HOST,
                'FIXED_UK_ROOT_REQUIRED')
        for path in (BASE, OLD, OLD + '/auxiliary-owner', '/etc/systemd/system'):
            info = os.lstat(path)
            require(os.path.realpath(path) == path and stat.S_ISDIR(info.st_mode)
                    and info.st_uid == 0 and not stat.S_IMODE(info.st_mode) & 0o022,
                    'PROTECTED_PARENT_REQUIRED')
        self.lock = os.open(BASE + '/legacy-isolation.lock', os.O_RDWR | os.O_NOFOLLOW)
        info = os.fstat(self.lock)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600, 'UNSAFE_EXISTING_LOCK')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.evidence()
        before = {}
        for unit in UNITS:
            path = '/etc/systemd/system/' + unit
            raw, info = self.read(path)
            require(sha(raw) == UNIT_HASHES[unit] and info.st_uid == 0 and info.st_gid == 0
                    and not stat.S_IMODE(info.st_mode) & 0o022, 'NOTIFIER_UNIT_DRIFT')
            value = self.show(unit)
            require(value.get('Id') == unit and value.get('LoadState') == 'loaded'
                    and value.get('FragmentPath') == path, 'UNIT_BINDING_DRIFT')
            if unit == TIMER:
                require(value.get('ActiveState') == 'active' and value.get('SubState') == 'waiting'
                        and value.get('UnitFileState') == 'enabled', 'TIMER_BASELINE_DRIFT')
            else:
                require(value.get('UnitFileState') == 'static'
                        and (value.get('ActiveState'), value.get('SubState')) in
                        (('active', 'running'), ('inactive', 'dead')), 'SERVICE_BASELINE_DRIFT')
                pid = value.get('MainPID', '')
                require(pid.isdigit() and ((value['ActiveState'] == 'active' and int(pid) > 0)
                        or (value['ActiveState'] == 'inactive' and pid == '0')), 'SERVICE_PID_DRIFT')
            before[unit] = dict(value, owner_uid=info.st_uid, owner_gid=info.st_gid,
                                mode=stat.S_IMODE(info.st_mode), sha256=sha(raw))
            self.payloads[unit] = raw
            self.fingerprints[unit] = (info.st_dev, info.st_ino, info.st_uid,
                                       info.st_gid, stat.S_IMODE(info.st_mode))
        require(not os.path.lexists(OLD + '/notifier'), 'EXISTING_NOTIFIER_TRANSACTION_HOLD')
        return before

    def begin(self, before, acceptance):
        parent = os.open(OLD, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.mkdir('notifier', 0o700, dir_fd=parent)
            os.fsync(parent)
            self.directory = os.open('notifier', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=parent)
        finally:
            os.close(parent)
        info = os.fstat(self.directory)
        require(info.st_uid == 0 and info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
                'PRIVATE_JOURNAL_DIRECTORY_REQUIRED')
        # All complete original bytes are durable before the first service effect.
        for unit in UNITS:
            fd = os.open(unit + '.backup', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self.directory)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(self.payloads[unit]); stream.flush(); os.fsync(stream.fileno())
        os.fsync(self.directory)
        self.receipt = {'schema': 1, 'transaction_id': TX, 'scope_approval': 'PR17:6151722263',
                        'candidate_acceptance': acceptance, 'before': before,
                        'database_before_sha256': DB_HASH, 'code_sha256': CODE_HASH,
                        'database_before_files': self.database_files,
                        'install': False, 'fence_mutation': False, 'writer_admission': False}
        self.record('BACKUPS_READY')

    def record(self, state, **details):
        self.receipt.update(details)
        self.receipt['state'] = state
        # Fixed unique temporary name; never overwrite unknown leftovers.
        fd = os.open('receipt.pending', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.directory)
        with os.fdopen(fd, 'wb') as stream:
            stream.write((json.dumps(self.receipt, sort_keys=True, separators=(',', ':')) + '\n').encode())
            stream.flush(); os.fsync(stream.fileno())
        os.replace('receipt.pending', 'notifier-isolation-receipt.json',
                   src_dir_fd=self.directory, dst_dir_fd=self.directory)
        os.fsync(self.directory)

    def recheck(self):
        self.evidence()
        for unit in UNITS:
            path = '/etc/systemd/system/' + unit
            if unit in self.masked:
                require(os.path.islink(path) and os.readlink(path) == '/dev/null', 'MASK_DRIFT')
                continue
            raw, info = self.read(path)
            require(sha(raw) == UNIT_HASHES[unit]
                    and (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
                         stat.S_IMODE(info.st_mode)) == self.fingerprints[unit], 'UNIT_IDENTITY_DRIFT')

    def stop(self, unit):
        require(unit in UNITS, 'STOP_OUTSIDE_SCOPE')
        result = subprocess.run(['/usr/bin/systemctl', 'stop', unit],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        require(result.returncode == 0, 'STOP_FAILED')

    def mask(self, unit):
        self.recheck()
        self.quiet(unit)
        parent = os.open('/etc/systemd/system', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temporary = unit + '.p2-notifier-mask'
        try:
            os.symlink('/dev/null', temporary, dir_fd=parent)
            os.replace(temporary, unit, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
            self.masked.add(unit)
        finally:
            os.close(parent)

    def reload(self):
        result = subprocess.run(['/usr/bin/systemctl', 'daemon-reload'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        require(result.returncode == 0, 'RELOAD_FAILED')

    def verify(self):
        self.recheck()
        after = {}
        for unit in UNITS:
            after[unit] = self.quiet(unit)
            require(after[unit].get('LoadState') == 'masked'
                    and after[unit].get('UnitFileState') == 'masked', 'MASK_NOT_LOADED')
            raw, _ = self.read(OLD + '/notifier/' + unit + '.backup', root_private=True)
            require(sha(raw) == UNIT_HASHES[unit], 'NOTIFIER_BACKUP_DRIFT')
        holders = []
        count = 0
        database_inodes = {(v['device'], v['inode']) for v in self.database_files.values()}
        for pid in os.listdir('/proc'):
            if not pid.isdigit() or int(pid) == os.getpid():
                continue
            # Every denied/racing process makes the scan incomplete and HOLDs.
            directory = os.open('/proc/' + pid + '/fd', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for name in os.listdir(directory):
                    count += 1
                    require(count <= 1000000, 'FD_SCAN_BOUND')
                    target = os.readlink(name, dir_fd=directory)
                    info = os.stat(name, dir_fd=directory)
                    if target.endswith(' (deleted)'):
                        target = target[:-len(' (deleted)')]
                    if target in (DB, DB + '-wal', DB + '-shm') or (info.st_dev, info.st_ino) in database_inodes:
                        holders.append(int(pid))
            finally:
                os.close(directory)
        require(not holders, 'OLD_DATABASE_HANDLES_REMAIN')
        self.evidence()
        return {'units': after, 'fd_checked': count, 'old_database_handle_holders': [],
                'permission_denials': 0, 'process_races': 0, 'prior_evidence_unchanged': True,
                'database_unchanged': True, 'other_writers_outside_scope': 'UNKNOWN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-acceptance', required=True,
                        help='Exact independent acceptance PR17/PR58 comment reference; audit metadata, not authentication')
    args = parser.parse_args()
    require(args.candidate_acceptance.startswith(('PR17:', 'PR58:'))
            and args.candidate_acceptance.split(':')[1].isdigit(), 'EXACT_ACCEPTANCE_REFERENCE_REQUIRED')
    adapter = FixedHost()
    try:
        result = isolate(adapter, args.candidate_acceptance)
        print(json.dumps({'state': 'AUTHORIZED_NOTIFIER_ISOLATED', 'transaction_id': TX,
                          'result': result, 'install': False}, sort_keys=True))
    finally:
        adapter.close()


if __name__ == '__main__':
    main()
