"""Resumable installation metadata; no execution or authorization authority.

Runtime adapters must authenticate permissions and verify actual effects. This
journal never treats process exit, an operator assertion, or a stored receipt
alone as proof that installation succeeded. Python 3.6 standard library.
"""
import fcntl
import hashlib
import json
import os
import sqlite3
import stat
import time


class Hold(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(value, reason):
    if not value:
        raise Hold(reason)


class Journal(object):
    """One process holds the lock for its whole installation session.

    The directory must be provisioned privately by the deployment layer. An
    interrupted RUNNING operation remains blocked until external reconciliation.
    Earlier commits are append-only metadata; rollback is never global.
    """
    def __init__(self, directory, plan):
        require(type(plan) is dict and set(plan) == {'schema', 'release', 'batches'}
                and type(plan['schema']) is int and plan['schema'] == 1,
                'PLAN_SCHEMA')
        require(type(plan['release']) is str and len(plan['release']) == 64 and
                all(c in '0123456789abcdef' for c in plan['release']), 'RELEASE_PIN')
        batches = plan['batches']
        require(type(batches) is list and 0 < len(batches) <= 64 and
                all(type(x) is str and x and len(x) <= 80 and
                    all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in x)
                    for x in batches) and len(set(batches)) == len(batches),
                'BATCH_IDS')
        self.batches = tuple(batches)
        self.plan_sha = digest(plan)
        self.db = None
        self.lock = None
        require(os.path.isabs(directory) and os.path.normpath(directory) == directory,
                'ABSOLUTE_DIRECTORY')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in directory.strip('/').split('/'):
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            require(info.st_uid == os.geteuid() and
                    stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')
            lock = os.open('install.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
            self.lock = lock
            info = os.fstat(lock)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                    info.st_uid == os.geteuid() and
                    stat.S_IMODE(info.st_mode) == 0o600, 'LOCK_PROTECTION')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Pin sqlite's directory via our held descriptor. Do not remove or
            # truncate an existing database or its sidecars, including on error.
            for name in ('journal.sqlite3', 'journal.sqlite3-wal',
                         'journal.sqlite3-shm', 'journal.sqlite3-journal'):
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                        info.st_uid == os.geteuid() and
                        not stat.S_IMODE(info.st_mode) & 0o077,
                        'DATABASE_PROTECTION')
            created = os.open('journal.sqlite3', os.O_CREAT | os.O_RDWR |
                              os.O_NOFOLLOW, 0o600, dir_fd=fd)
            os.close(created)
            self.directory_fd = fd
            fd = None
            self.db = sqlite3.connect('/proc/self/fd/%s/journal.sqlite3' %
                                      self.directory_fd, isolation_level=None)
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS binding (plan TEXT PRIMARY KEY)')
            self.db.execute('CREATE TABLE IF NOT EXISTS events ('
                            'seq INTEGER PRIMARY KEY, batch TEXT NOT NULL, '
                            'attempt TEXT NOT NULL, state TEXT NOT NULL, '
                            'evidence TEXT NOT NULL, utc INTEGER NOT NULL)')
            self.db.execute('BEGIN IMMEDIATE')
            rows = self.db.execute('SELECT plan FROM binding').fetchall()
            require(not rows or rows == [(self.plan_sha,)], 'PLAN_CHANGED')
            if not rows:
                self.db.execute('INSERT INTO binding VALUES (?)', (self.plan_sha,))
            self.db.execute('COMMIT')
        except BaseException:
            self.close()
            raise
        finally:
            if fd is not None:
                os.close(fd)

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if getattr(self, 'directory_fd', None) is not None:
            os.close(self.directory_fd)
            self.directory_fd = None
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def latest(self, batch):
        require(batch in self.batches, 'UNKNOWN_BATCH')
        return self.db.execute('SELECT attempt,state,evidence FROM events '
            'WHERE batch=? ORDER BY seq DESC LIMIT 1', (batch,)).fetchone()

    def append(self, batch, attempt, state, evidence):
        require(type(evidence) is dict and 0 < len(canonical(evidence)) <= 262144,
                'EVIDENCE_BOUND')
        self.db.execute('INSERT INTO events(batch,attempt,state,evidence,utc) '
            'VALUES (?,?,?,?,?)', (batch, attempt, state,
             canonical(evidence).decode('ascii'), int(time.time())))

    def begin(self, batch, attempt, verify_previous):
        require(type(attempt) is str and 0 < len(attempt) <= 128, 'ATTEMPT_ID')
        require(batch in self.batches and callable(verify_previous), 'BATCH_OR_VERIFIER')
        # No effects may run until this durable RUNNING event has committed.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for predecessor in self.batches[:self.batches.index(batch)]:
                row = self.latest(predecessor)
                require(row is not None and row[1] == 'COMMITTED', 'PREDECESSOR_PENDING')
                require(verify_previous(predecessor, json.loads(row[2])) is True,
                        'PREDECESSOR_DRIFT')
            row = self.latest(batch)
            require(row is None or row[1] == 'RETRYABLE', 'RECONCILE_OR_ALREADY_COMMITTED')
            require(not self.db.execute('SELECT 1 FROM events WHERE attempt=?',
                                       (attempt,)).fetchone(), 'ATTEMPT_REUSED')
            self.append(batch, attempt, 'RUNNING', {'plan_sha256': self.plan_sha})
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def finish(self, batch, attempt, evidence, verify_effects):
        self._resolve(batch, attempt, evidence, verify_effects, 'COMMITTED')

    def reconcile_no_effect(self, batch, attempt, evidence, verify_no_effect):
        # Only authenticated adapter readback can allow a new attempt. A failed
        # exit code or an empty log does not establish absence of side effects.
        self._resolve(batch, attempt, evidence, verify_no_effect, 'RETRYABLE')

    def _resolve(self, batch, attempt, evidence, verifier, state):
        require(callable(verifier), 'VERIFIER_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.latest(batch)
            require(row is not None and row[:2] == (attempt, 'RUNNING'), 'ATTEMPT_STATE')
            require(verifier(batch, attempt, evidence) is True, 'UNVERIFIED_EFFECTS')
            self.append(batch, attempt, state, evidence)
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
