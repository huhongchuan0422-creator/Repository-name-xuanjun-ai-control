"""Pinned fixture inputs only; never an installed P2 acceptance assertion."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys


def dependencies():
    root = Path(os.environ['DOTS_TEST_DEPENDENCIES']).resolve()
    entries = json.loads(Path(__file__).with_name('dependencies.json').read_text())
    for entry in entries:
        data = (root / entry['name']).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('DEPENDENCY_HASH_MISMATCH')
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def package():
    root = Path(os.environ['P2_TEST_PACKAGE']).resolve()
    raw = (root / 'deploy/integration-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '9c8ded6c3c17c88e76361085b8ee752f997d947c51506656099b22e033777d4c':
        raise ValueError('HISTORICAL_PACKAGE_MANIFEST_MISMATCH')
    files = json.loads(raw.decode('utf-8'))['files']
    if len(files) != 77:
        raise ValueError('PACKAGE_FILE_COUNT')
    for name, digest in files.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError('PACKAGE_FILE_HASH')
    for path in (root / 'stage1').rglob('*.py'):
        if str(path.relative_to(root)) not in files:
            raise ValueError('UNMANIFESTED_IMPORT_SOURCE')
    sys.path.insert(0, str(root / 'stage1'))
    return root


def load_dependencies():
    dependencies()
    return {name: importlib.import_module(name) for name in
            ('owner_action_digest', 'notification_delivery_view',
             'task_supervisor_runtime', 'ci_receipt_binding', 'source_path_ownership')}


class CanonicalFixture:
    """Temporary existing-task schema + real frozen supplemental producer.

    Activation identity is an explicit fixture, never installed authority.
    """
    def __init__(self, case):
        import tempfile
        import sqlite3
        package()
        import execution_supervision
        self.module = execution_supervision
        self.tmp = tempfile.TemporaryDirectory()
        case.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'canonical.sqlite')
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        case.addCleanup(self.db.close)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL)')
        self.binding = dict(ledger_uuid='fixture-ledger',instance='fixture-instance',generation=1,epoch=2,db_path=self.path)
        owner = self
        class ActivationFixture:
            def read(self, require_active=False):
                return dict(owner.binding)
        self.activation = ActivationFixture()
        self.reopen_producer()
    def reopen_producer(self):
        self.producer = self.module.ExecutionSupervisor(self.path, lambda:100, activation_store=self.activation)
    def task(self, name, state='PENDING'):
        self.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',(name,'CODEX_EXEC',state,'[]','fixture',200,4,'{}',100))
    def event(self, name, kind='NOTICE'):
        self.db.execute('BEGIN IMMEDIATE')
        self.producer._event(self.db,name,kind,{'private':'NEVER_EXPORTED'})
        self.db.commit()
    def reader(self, case):
        import sqlite3
        db=sqlite3.connect(self.path,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        case.addCleanup(db.close)
        return db
