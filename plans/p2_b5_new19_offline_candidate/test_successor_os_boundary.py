"""Test-only fixed-path OS boundary.  No production module is patched here.

Only files present when the boundary is sealed inherit a recorded UK identity.
New or replaced inodes retain their real identity and fail the original pins.
"""
import contextlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE/'successor_controller'), str(HERE/'reused-6825'),
                str(HERE/'new19-source')]
from pr17_b5_successor_fixed_io import FixedR2IO
from pr17_b5_successor_backend import R2HostBackend
import pr17_b5_successor_review as c53


class StatView:
    def __init__(self, real, dev, ino, uid=0, gid=0):
        self.real, self.st_dev, self.st_ino = real, dev, ino
        self.st_uid, self.st_gid = uid, gid

    def __getattr__(self, name):
        return getattr(self.real, name)


class SealedOSBoundary:
    """Redirect only the fixed absolute root and translate sealed identities.

    The original fds, flock and SQLite operations run on actual temporary files.
    A newly created inode never inherits a pin from its pathname.
    """
    def __init__(self, root, allowed, pins):
        self.root = pathlib.Path(root)
        self.allowed = frozenset(allowed)
        self.directories = frozenset({'/'} | {
            str(parent) for path in self.allowed
            for parent in pathlib.PurePosixPath(path).parents})
        self.pins = {}
        self.sealed_paths = {}
        for path, identity in pins.items():
            real = self.root/path.lstrip('/')
            st = real.lstat()
            self.pins[(st.st_dev, st.st_ino)] = identity
            self.sealed_paths[(st.st_dev, st.st_ino)] = path
        self._open, self._stat, self._fstat = os.open, os.stat, os.fstat
        self._readlink = os.readlink

    def _mapped(self, st):
        identity = self.pins.get((st.st_dev, st.st_ino))
        if identity:
            return StatView(st, *identity)
        # The disposable fixture models UK root ownership on both prepared
        # directories and files atomically published after sealing. New files
        # retain their real dev/ino, so they cannot inherit a baseline pin.
        if (st.st_mode & 0o170000) in (0o040000,0o100000):
            return StatView(st, st.st_dev, st.st_ino)
        return st

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        path = os.fspath(path)
        if path == '/' and dir_fd is None:
            return self._open(str(self.root), flags, mode)
        if dir_fd is None and path.startswith('/'):
            if path not in self.allowed and path not in self.directories:
                raise PermissionError('UNLISTED_OS_PATH')
            return self._open(str(self.root/path.lstrip('/')), flags, mode)
        return self._open(path, flags, mode, dir_fd=dir_fd)

    def stat(self, path, *, dir_fd=None, follow_symlinks=True):
        path = os.fspath(path)
        if dir_fd is None and path.startswith('/'):
            if path not in self.allowed and path not in self.directories:
                raise PermissionError('UNLISTED_OS_PATH')
            path = str(self.root/path.lstrip('/'))
        return self._mapped(self._stat(path, dir_fd=dir_fd,
                                       follow_symlinks=follow_symlinks))

    def fstat(self, fd):
        return self._mapped(self._fstat(fd))

    def readlink(self, path, *, dir_fd=None):
        path = os.fspath(path)
        if dir_fd is None and path.startswith('/proc/self/fd/'):
            suffix = path[len('/proc/self/fd/'):]
            if not suffix.isdecimal():
                raise PermissionError('UNLISTED_PROC_FD')
            fd = int(suffix)
            try:
                st = self._fstat(fd)
            except OSError as exc:
                raise PermissionError('UNLISTED_PROC_FD') from exc
            sealed = self.sealed_paths.get((st.st_dev, st.st_ino))
            if sealed is None or self._readlink(path) != str(self.root/sealed.lstrip('/')):
                raise PermissionError('UNLISTED_PROC_FD')
            return sealed
        if dir_fd is None and path.startswith('/'):
            if path not in self.allowed and path not in self.directories:
                raise PermissionError('UNLISTED_OS_PATH')
            path = str(self.root/path.lstrip('/'))
        return self._readlink(path, dir_fd=dir_fd)

    @contextlib.contextmanager
    def active(self):
        with patch.object(os, 'open', self.open), patch.object(os, 'stat', self.stat), \
             patch.object(os, 'fstat', self.fstat), patch.object(os, 'readlink', self.readlink):
            yield


class IdentityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.spec = json.loads((HERE/'SUCCESSOR_SPEC.json').read_bytes())
        self.io = FixedR2IO(self.spec)
        db = self.root/c53.DB.lstrip('/')
        db.parent.mkdir(parents=True)
        connection = sqlite3.connect(str(db))
        connection.execute('CREATE TABLE fixture(x BLOB)')
        connection.commit(); connection.close()
        db.chmod(0o600)
        lock = self.root/c53.LOCK.lstrip('/')
        lock.write_bytes(b'')
        lock.chmod(0o600)
        self.db, self.lock = db, lock
        self.boundary = SealedOSBoundary(self.root, [c53.DB, c53.LOCK], {
            c53.DB:(self.spec['observed_baseline']['db']['dev'],
                    self.spec['observed_baseline']['db']['ino']),
            c53.LOCK:(self.spec['observed_baseline']['worker_lock']['dev'],
                      self.spec['observed_baseline']['worker_lock']['ino'])})

    def test_original_database_identity_with_real_fd_and_growth(self):
        with self.boundary.active():
            fd = os.open(c53.DB, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                self.io.database_identity(os.fstat(fd))
            finally:
                os.close(fd)
        con = sqlite3.connect(str(self.db))
        con.execute('INSERT INTO fixture VALUES (?)', (b'x'*100000,))
        con.commit(); con.close()
        with self.boundary.active():
            fd = os.open(c53.DB, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                self.io.database_identity(os.fstat(fd))
            finally:
                os.close(fd)

    def test_replaced_inode_cannot_inherit_sealed_identity(self):
        self.db.rename(self.db.with_suffix('.old'))
        con = sqlite3.connect(str(self.db)); con.execute('CREATE TABLE fixture(x)'); con.close()
        self.db.chmod(0o600)
        with self.boundary.active():
            fd = os.open(c53.DB, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                with self.assertRaisesRegex(c53.Hold,'FIXED_IO_DATABASE_IDENTITY'):
                    self.io.database_identity(os.fstat(fd))
            finally:
                os.close(fd)

    def test_unlisted_path_denied(self):
        with self.boundary.active():
            with self.assertRaisesRegex(PermissionError,'UNLISTED_OS_PATH'):
                os.open('/etc/passwd', os.O_RDONLY)
            with self.assertRaisesRegex(PermissionError,'UNLISTED_PROC_FD'):
                os.readlink('/proc/self/fd/999999')

    def test_proc_fd_resolves_only_same_sealed_inode(self):
        with self.boundary.active():
            fd=os.open(c53.DB, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                self.assertEqual(os.readlink('/proc/self/fd/%d'%fd),c53.DB)
                self.assertEqual((os.stat(c53.DB).st_dev,os.stat(c53.DB).st_ino),
                                 (os.fstat(fd).st_dev,os.fstat(fd).st_ino))
            finally:
                os.close(fd)

    def test_synthetic_six_bytes_cannot_pass_original_digest_guard(self):
        # Device/inode translation never supplies or authenticates file bytes.
        # The original six protected records are not in this checkout.
        from test_successor_bundle_offline import SyntheticSixSlotTests
        sample = SyntheticSixSlotTests()
        sample.setUp()
        with self.assertRaisesRegex(c53.Hold,'BASELINE_HASH_CHANGED'):
            c53.verify_observed_bytes(self.spec, sample.baselines)

    def test_actual_backend_reads_six_fds_then_rejects_wrong_bytes(self):
        from test_successor_bundle_offline import SyntheticSixSlotTests
        sample=SyntheticSixSlotTests();sample.setUp()
        pins={c53.DB:(self.spec['observed_baseline']['db']['dev'],
                       self.spec['observed_baseline']['db']['ino']),
              c53.LOCK:(self.spec['observed_baseline']['worker_lock']['dev'],
                         self.spec['observed_baseline']['worker_lock']['ino'])}
        for path,raw in sample.baselines.items():
            target=self.root/path.lstrip('/')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o600)
            st=target.stat()
            pins[path]=(st.st_dev,st.st_ino)
        boundary=SealedOSBoundary(self.root, list(pins), pins)
        backend=R2HostBackend(legacy_io=self.io,spec=self.spec,
                              source_blobs=sample.source,
                              observed_bytes=sample.baselines)
        with boundary.active(), patch.object(os,'uname',
                return_value=type('Host',(),{'nodename':c53.HOST})()),\
             patch.dict(os.environ,{'SUDO_UID':'1000'}):
            with self.assertRaisesRegex(c53.Hold,'BASELINE_HASH_CHANGED'):
                backend.get_generator_inputs_verified(self.spec)
        self.assertFalse(backend.generator_inputs_verified)

    def test_original_lock_uses_real_flock_and_rejects_replaced_inode(self):
        backend = R2HostBackend(legacy_io=self.io, spec=self.spec,
                                source_blobs={}, observed_bytes={})
        backend.worker_stopped = True
        with self.boundary.active():
            backend.acquire_original_lock_once()
            self.assertIsNotNone(backend.lock_fd)
            os.close(backend.lock_fd)
            backend.lock_fd = None
        self.lock.rename(self.lock.with_suffix('.old'))
        self.lock.write_bytes(b'')
        self.lock.chmod(0o600)
        with self.boundary.active():
            with self.assertRaisesRegex(c53.Hold,'ORIGINAL_LOCK_IDENTITY'):
                backend.acquire_original_lock_once()
        self.assertIsNone(backend.lock_fd)


if __name__ == '__main__':
    unittest.main()
