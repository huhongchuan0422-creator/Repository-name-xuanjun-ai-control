"""Candidate-only atomic state; never opens an existing trading database.

SQLite rollback journal + FULL synchronous commits cover sessions, credential
pairs, lifecycle and verified binding in ONE database. No file-format migration
is implicit. Locks wait at most 5 seconds. Provider calls remain disabled by
HTTP default; no secret data is included in returned errors.
"""
import json
import os
import sqlite3
import stat
import threading
from contextlib import contextmanager
from pathlib import Path


def private_directory(raw):
    path = Path(raw).absolute()
    for item in reversed((path, *path.parents)):
        if item.is_symlink():
            raise RuntimeError('STATE_SYMLINK_REJECTED')
        if not item.exists():
            item.mkdir(mode=0o700)
    info = path.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('STATE_DIRECTORY_IDENTITY')
    return path


class Database:
    def __init__(self, root):
        self.root = private_directory(root)
        self.path = self.root / 'oauth-candidate.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise RuntimeError('STATE_DATABASE_IDENTITY')
            os.fsync(fd)
        finally:
            os.close(fd)
        self.local = threading.local()
        with self.transaction() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @contextmanager
    def transaction(self):
        existing = getattr(self.local, 'connection', None)
        if existing is not None:
            yield existing
            return
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.local.connection = conn
        try:
            conn.execute('PRAGMA journal_mode=DELETE')
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('PRAGMA busy_timeout=5000')
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            self.checkpoint('before_commit')
            conn.execute('COMMIT')
            self.checkpoint('after_commit')
        except BaseException:
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise
        finally:
            self.local.connection = None
            conn.close()

    def checkpoint(self, point):
        """Fault-injection seam: no production environment switches."""

    def get(self, key):
        with self.transaction() as conn:
            row = conn.execute('SELECT value FROM records WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self.transaction() as conn:
            conn.execute('INSERT OR REPLACE INTO records VALUES (?, ?)',
                         (key, json.dumps(value, sort_keys=True)))
            self.checkpoint('write:' + key)

    def items(self, prefix):
        with self.transaction() as conn:
            return [(k, json.loads(v)) for k, v in conn.execute(
                'SELECT key,value FROM records WHERE substr(key,1,?)=? ORDER BY key',
                (len(prefix), prefix))]
