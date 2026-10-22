"""Own original community stores for an explicitly admitted first installation.

No LocalStage, fixture data, accounts, authority, credentials, listener or money IO.
The caller owns Center separately and must configure original identity/commerce.
Initialization and reopening are deliberately separate; partial initialization is
preserved for inspection and never automatically completed or deleted.
"""
import fcntl
import os
import sqlite3
import stat
from pathlib import Path
from scripts.community_stage_runtime import StageRuntime
from scripts.community_saas_phase2 import OfflineSaas
from scripts.community_demo_api import DemoService
from scripts.community_stage_migration import SPECS, _catalog, _template, _integrity

NAMES = ('orders', 'merchants', 'ads', 'refunds', 'modules', 'saas-orders')


def _directory(path):
    raw = os.fspath(path)
    if (type(raw) is not str or not Path(raw).is_absolute()
            or '..' in Path(raw).parts or str(Path(raw)) != raw):
        raise ValueError('EXACT_ABSOLUTE_RUNTIME_DIRECTORY_REQUIRED')
    root = Path(raw)
    for part in reversed((root, *root.parents)):
        info = part.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o022):
            raise PermissionError('PROTECTED_RUNTIME_ANCESTRY_REQUIRED')
    info = root.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError('PRIVATE_RUNTIME_DIRECTORY_REQUIRED')
    return root


def _file(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise PermissionError('PRIVATE_RUNTIME_FILE_REQUIRED')
    return info


class PersistentRuntime:
    """Serial same-thread store owner; not a deployment or approval mechanism."""
    def __init__(self):
        self.handles = []
        self.lock_fd = None
        self.runtime = None

    @classmethod
    def initialize(cls, directory, bindings, *, clock):
        """Create a NEW child directory using original schemas; never seed data.

        The existing parent must be private. Existing/partial destinations are
        refused even when empty. Explicit site admission belongs to the caller.
        """
        path = Path(directory)
        _directory(str(path.parent))
        if not path.is_absolute() or str(path) != os.fspath(directory) or '..' in path.parts:
            raise ValueError('EXACT_ABSOLUTE_RUNTIME_DIRECTORY_REQUIRED')
        # Validate bindings/clock before creating any persistent file.
        cls._bindings(bindings, clock)
        path.mkdir(mode=0o700)
        owner = cls()
        try:
            owner.root = _directory(str(path))
            owner._lock(create=True)
            from scripts.community_order_store import connect
            from scripts.community_merchant_store import open_store
            from scripts.community_ad_store import open_offline
            from scripts.community_refund_preview_store import open_refund_store
            from scripts.community_saas_modules import connect as modules
            from scripts.community_saas_offer_catalog import install as offers
            from scripts.community_saas_order_preparation import install, install_lifecycle
            from scripts.community_saas_offline_handoff import install_reviews
            def orders(path):
                db = sqlite3.connect(path)
                try:
                    install(db); install_lifecycle(db); install_reviews(db)
                    return db
                except BaseException:
                    db.close()
                    raise
            for name, opener in zip(NAMES, (connect, open_store, open_offline,
                                            open_refund_store, modules, orders)):
                target = path / (name + '.sqlite')
                fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                os.close(fd)
                db = opener(str(target))
                owner.handles.append(db)
                if name == 'modules':
                    offers(db)
                db.commit()
                owner._schema(name, db)
            owner._compose(bindings, clock)
            return owner
        except BaseException:
            owner.close()  # Keep partial state; never silently restart initialization.
            raise

    @staticmethod
    def _bindings(bindings, clock):
        if not callable(clock):
            raise ValueError('SERVER_CLOCK_REQUIRED')
        StageRuntime(None, None, bindings, clock)  # Original type/tenant/scope checks.

    def _lock(self, create=False):
        path = self.root / 'runtime.lock'
        if not create:
            _file(path)
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        self.lock_fd = os.open(str(path), flags, 0o600)
        info = os.fstat(self.lock_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise PermissionError('PRIVATE_RUNTIME_LOCK_REQUIRED')
        fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _schema(name, db):
        schema, versions, _ = SPECS[name]
        if db.execute('PRAGMA user_version').fetchone()[0] not in versions or _catalog(db) != _template(schema):
            raise ValueError('CURRENT_RUNTIME_SCHEMA_REQUIRED:' + name)
        _integrity(db)

    @classmethod
    def open(cls, directory, bindings, *, clock):
        """Open only existing current-schema stores. No DDL/migration/repair."""
        cls._bindings(bindings, clock)
        owner = cls()
        try:
            owner.root = _directory(directory)
            owner._lock()
            for name in NAMES:
                target = owner.root / (name + '.sqlite')
                _file(target)
                for suffix in ('-wal', '-shm', '-journal'):
                    sidecar = Path(str(target) + suffix)
                    if sidecar.exists() or sidecar.is_symlink():
                        _file(sidecar)
            for name in NAMES:
                target = owner.root / (name + '.sqlite')
                before = _file(target)
                db = sqlite3.connect(target.as_uri() + '?mode=rw', uri=True, timeout=15)
                owner.handles.append(db)
                after = _file(target)
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise PermissionError('RUNTIME_FILE_CHANGED')
                db.execute('PRAGMA foreign_keys=ON')
                owner._schema(name, db)
            owner._compose(bindings, clock)
            return owner
        except BaseException:
            owner.close()
            raise

    def _compose(self, bindings, clock):
        o, m, a, r, q, s = self.handles
        # Reuse original store container without demo QR or local admin policy.
        self.runtime = StageRuntime(DemoService(o, m, a, None, r),
                                    OfflineSaas(q, s, q), bindings, clock)

    def close(self):
        error = None
        try:
            while self.handles:
                try:
                    self.handles.pop().close()
                except BaseException as exc:
                    if error is None:
                        error = exc
        finally:
            self.runtime = None
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None
        if error is not None:
            raise error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
