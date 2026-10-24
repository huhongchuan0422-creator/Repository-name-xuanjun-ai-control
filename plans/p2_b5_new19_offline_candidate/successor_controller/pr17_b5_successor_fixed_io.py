"""Fixed B5 R2 host primitives.  This module does not select a job or grant.

Every operation is restricted to the reviewed successor spec.  It is a new
implementation of the backend's I/O contract, not an imported historical R2
entry point.  The live caller remains disabled until its protected bindings
and original authority are enrolled independently.
"""
import os
import http.client
import json
import stat
import subprocess
import time
import re

import pr17_b5_successor_review as c53


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_nlink)


class FixedR2IO:
    def __init__(self, spec):
        c53.require(type(spec) is dict and
                    spec.get('schema') == 'PR17_B5_STAGED_SUCCESSOR_V1',
                    'FIXED_IO_SPEC')
        self.spec = spec
        paths = spec['fixed_paths']
        self.job = paths['job_proposed']
        self.stage = tuple(paths['stage_proposed'])
        self.target = tuple(paths['target_release'])
        self.files = frozenset(paths['configs'] + paths['protected_slots'] +
                               paths['current'] + [c53.DB])
        self.bases = tuple(c53.BASES)
        self.runtime_files = frozenset(
            row['path'] for row in spec['source']['source_records']) | {
                c53.binder.MANIFEST_PATH}
        self.runtime_dirs = frozenset(
            root+'/'+part for root in self.stage for name in self.runtime_files
            for part in self._parents(name))
        self.journal_names = frozenset((
            'reservation.json', 'window-open.json', 'activation-identity.json',
            'NEW_WORKER_START_ATTEMPT.json',
            'CLOSEOUT_WORKER_START_ATTEMPT.json',
            'b5-exposure-closed.json'))
        self.backup_names = frozenset(
            ['original-links.json'] +
            ['original-%d.bin'%n for n in range(3)] +
            ['protected-original-%d.bin'%n for n in range(3)])
        self.ids = frozenset(spec['batch']['draft_request_ids'])
        c53.require(self.job == '/opt/xuanjun-cloud-connection/l2-b5-staged-'+
                    c53.COMMIT[:12] and self.stage == tuple(
                        b+'/releases/.l2-b5-staged-'+c53.COMMIT[:12]
                        for b in self.bases) and self.target == tuple(
                        b+'/releases/'+c53.COMMIT for b in self.bases),
                    'FIXED_IO_PATHS')

    @staticmethod
    def _parents(name):
        parts = name.split('/')[:-1]
        return ('/'.join(parts[:n]) for n in range(1,len(parts)+1))

    def _path(self, path, directory=False):
        c53.require(type(path) is str and path.startswith('/') and
                    os.path.normpath(path) == path and '\x00' not in path,
                    'FIXED_IO_PATH')
        job_name = path[len(self.job)+1:] if path.startswith(self.job+'/') else ''
        checkpoint = re.fullmatch(r'checkpoint-(\d{3})\.json',job_name)
        journal = (job_name in self.journal_names or
                   job_name in self.backup_names or
                   (checkpoint is not None and
                    1 <= int(checkpoint.group(1)) <= 64) or
                   any(job_name == 'intake-'+rid+suffix for rid in self.ids
                       for suffix in ('.intent.json','.sent.json')))
        runtime = any(path == root+'/'+name for root in self.stage
                      for name in self.runtime_files)
        temp = any(path == original+'.l2-b5-staged-'+c53.COMMIT[:12] or
                   path == original+'.l2-b5-staged-'+c53.COMMIT[:12]+'-close'
                   for original in c53.CONFIGS+c53.SLOTS)
        temp = temp or any(path == base+'/current.l2-b5-staged-'+c53.COMMIT[:12]
                           for base in self.bases)
        allowed = path in self.files or path == self.job or path in self.stage
        allowed = allowed or path in self.target or journal or runtime or temp
        allowed = allowed or path in (c53.DB+'-wal', c53.DB+'-shm',
                                     c53.DB+'-journal')
        if directory:
            allowed = allowed or path in self.runtime_dirs
            allowed = allowed or path in self.bases or path in tuple(
                b+'/releases' for b in self.bases) or path == os.path.dirname(c53.DB)
            allowed = allowed or path == os.path.dirname(c53.CONFIGS[0])
            allowed = allowed or path == os.path.dirname(self.job)
        c53.require(allowed, 'FIXED_IO_SCOPE')
        return path

    def parent(self, path):
        """Open a fixed directory, rejecting links and writable ancestors."""
        self._path(path, directory=True)
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in path.split('/')[1:]:
                if not part:
                    continue
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY |
                              os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                st = os.fstat(fd)
                c53.require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and
                            not st.st_mode & 0o022, 'FIXED_IO_PARENT')
            result, fd = fd, None
            return result
        finally:
            if fd is not None:
                os.close(fd)

    def identity(self, st):
        return _identity(st)

    def state_directory(self):
        return self.parent(os.path.dirname(c53.DB))

    def database_identity(self, st):
        pin = self.spec['observed_baseline']['db']
        c53.require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                    st.st_uid == st.st_gid == 0 and
                    stat.S_IMODE(st.st_mode) in (0o600, 0o400) and
                    (st.st_dev, st.st_ino) == (pin['dev'], pin['ino']),
                    'FIXED_IO_DATABASE_IDENTITY')

    def read(self, path):
        self._path(path)
        parent = self.parent(os.path.dirname(path))
        fd = None
        try:
            fd = os.open(os.path.basename(path), os.O_RDONLY | os.O_NOFOLLOW |
                         os.O_NONBLOCK, dir_fd=parent)
            before = os.fstat(fd)
            source_file = any(path == root+'/'+name for root in self.stage
                              for name in self.runtime_files)
            c53.require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                        before.st_nlink == 1 and
                        stat.S_IMODE(before.st_mode) in
                        ((0o644,) if source_file else (0o600,0o400)) and
                        before.st_size <= 262144,
                        'FIXED_IO_READ_METADATA')
            raw = os.read(fd, 262145)
            after = os.fstat(fd)
            named = os.stat(os.path.basename(path), dir_fd=parent,
                            follow_symlinks=False)
            c53.require(len(raw) == before.st_size and len(raw) <= 262144 and
                        _identity(before) == _identity(after) == _identity(named),
                        'FIXED_IO_READ_CHANGED')
            return raw, _identity(before)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def absent(self, path):
        self._path(path)
        parent = self.parent(os.path.dirname(path))
        try:
            try:
                os.stat(os.path.basename(path), dir_fd=parent,
                        follow_symlinks=False)
            except FileNotFoundError:
                return True
            raise c53.Hold('FIXED_IO_PRESENT')
        finally:
            os.close(parent)

    def mkdir(self, path, mode):
        self._path(path, directory=True)
        c53.require((path == self.job and mode == 0o700) or
                    ((path in self.stage or path in self.runtime_dirs) and
                     mode == 0o755), 'FIXED_IO_DIR_MODE')
        parent = self.parent(os.path.dirname(path))
        try:
            os.mkdir(os.path.basename(path), mode, dir_fd=parent)
            os.fsync(parent)
        finally:
            os.close(parent)

    def newfile(self, path, raw, mode=0o600):
        self._path(path)
        source_file = any(path == root+'/'+name for root in self.stage
                          for name in self.runtime_files)
        c53.require(type(raw) is bytes and len(raw) <= 262144 and
                    mode == (0o644 if source_file else 0o600),
                    'FIXED_IO_WRITE_SCOPE')
        parent = self.parent(os.path.dirname(path))
        fd = None
        try:
            fd = os.open(os.path.basename(path), os.O_WRONLY | os.O_CREAT |
                         os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
            os.fchmod(fd, mode)
            st = os.fstat(fd)
            c53.require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and
                        st.st_nlink == 1, 'FIXED_IO_NEWFILE_IDENTITY')
            remaining = memoryview(raw)
            while remaining:
                count = os.write(fd, remaining)
                c53.require(count > 0, 'FIXED_IO_SHORT_WRITE')
                remaining = remaining[count:]
            os.fsync(fd)
            os.fsync(parent)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def check_original_database(self):
        root = self.state_directory()
        try:
            st = os.stat('queue.sqlite', dir_fd=root, follow_symlinks=False)
            self.database_identity(st)
            c53.require(st.st_size == self.spec['observed_baseline']['db']['bytes'],
                        'FIXED_IO_DATABASE_SIZE')
        finally:
            os.close(root)

    def command(self, argv, timeout, acceptable=(0,)):
        unit = 'xuanjun-cloud-connection.service'
        resource = 'xuanjun-cloud-oauth-resource.service'
        tunnel = 'xuanjun-cloud-oauth-tunnel.service'
        allowed = {(('/usr/bin/systemctl', action, name), seconds)
                   for action, name, seconds in (
                       ('stop', unit, 60), ('start', unit, 20),
                       ('restart', resource, 20), ('restart', tunnel, 20),
                       ('stop', tunnel, 60), ('stop', resource, 60))}
        allowed.update({(('/usr/bin/systemctl', 'is-active', '--quiet', name), seconds)
                        for name, seconds in ((unit, 10), (tunnel, 10))})
        c53.require(type(argv) is list and (tuple(argv), timeout) in allowed and
                    type(acceptable) is tuple and acceptable in ((0,), (3,)) and
                    (acceptable != (3,) or
                     tuple(argv[1:3]) == ('is-active','--quiet')),
                    'FIXED_IO_COMMAND_SCOPE')
        result = subprocess.run(argv, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=timeout,
                                check=False, close_fds=True)
        c53.require(result.returncode in acceptable, 'FIXED_IO_COMMAND_FAILED')
        return result.returncode

    def stable_unit(self, name):
        c53.require(name == 'xuanjun-cloud-connection.service',
                    'FIXED_IO_UNIT_SCOPE')
        self.command(['/usr/bin/systemctl','is-active','--quiet',name],10)
        time.sleep(0.1)
        self.command(['/usr/bin/systemctl','is-active','--quiet',name],10)

    def resource_ready(self):
        # The existing resource serves this public metadata on a fixed
        # loopback port.  A live process alone is insufficient: compare the
        # advertised audience and issuer with the protected activated config.
        from production.cloud_connection.oauth_entrypoint import private_bytes
        raw = private_bytes(c53.CONFIGS[1], 262144)
        try:
            config = json.loads(raw.decode('utf-8'))
            expected = config['settings']
            c53.require(config['enabled'] is True and
                        config['hostname'] == c53.HOST and
                        type(expected['issuer']) is str and
                        type(expected['audience']) is str,
                        'FIXED_IO_RESOURCE_CONFIG')
            conn = http.client.HTTPConnection('127.0.0.1', 18769, timeout=2)
            try:
                conn.request('GET', '/.well-known/oauth-protected-resource',
                             headers={'Host':'127.0.0.1','Connection':'close'})
                response = conn.getresponse()
                body = response.read(2049)
                c53.require(response.status == 200 and len(body) <= 2048 and
                            response.getheader('Content-Type','').startswith('application/json'),
                            'FIXED_IO_RESOURCE_RESPONSE')
            finally:
                conn.close()
            metadata = json.loads(body.decode('utf-8'))
            c53.require(metadata == {
                'resource': expected['audience'],
                'authorization_servers': [expected['issuer']],
                'scopes_supported': ['connection.status','project.files.read'],
                'bearer_methods_supported': ['header']},
                'FIXED_IO_RESOURCE_BINDING')
        except (OSError, ValueError, KeyError, UnicodeError, TypeError) as exc:
            raise c53.Hold('FIXED_IO_RESOURCE_READINESS_UNKNOWN') from exc
