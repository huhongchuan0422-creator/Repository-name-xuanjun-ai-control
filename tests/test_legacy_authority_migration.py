import hashlib, os, shutil, sqlite3, tempfile, unittest
from unittest import mock

from scripts import legacy_authority_migration as migration


class LegacyAuthorityMigrationTest(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp(); self.backup=os.path.join(self.root,'backup.db')
        self.ledger=os.path.join(self.root,'ledger.db'); self.freeze=os.path.join(self.root,'FROZEN')
        db=sqlite3.connect(self.backup)
        db.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,depends TEXT NOT NULL,lease_owner TEXT,lease_until REAL,fence INTEGER NOT NULL DEFAULT 0,checkpoint TEXT NOT NULL DEFAULT '{}',updated REAL NOT NULL)")
        db.execute("CREATE INDEX legacy_state ON tasks(state)")
        db.execute("INSERT INTO tasks VALUES('old','K','READY','[]',NULL,NULL,7,'{\"x\":1}',1)")
        db.commit(); self.fp=migration.schema_fingerprint(db); db.close()
        shutil.copyfile(self.backup,self.ledger)
        with open(self.freeze,'w') as marker: marker.write('frozen')
        self.sha=migration.sha_file(self.backup)
    def tearDown(self): shutil.rmtree(self.root)
    def apply(self, op='op'):
        with mock.patch.object(migration,'LEGACY_FINGERPRINT',self.fp):
            return migration.apply(self.ledger,self.backup,self.sha,self.fp,self.freeze,op)
    def test_success_preserves_legacy_and_is_idempotent(self):
        first=self.apply(); self.assertEqual(self.apply(),first)
        db=sqlite3.connect(self.ledger)
        row=db.execute('SELECT id,checkpoint,fence,task_id,authority_state,attempt_id,lease_id,epoch FROM tasks').fetchone()
        self.assertEqual(row,('old','{"x":1}',7,'old','NONE','UNKNOWN','UNKNOWN',None))
        self.assertEqual(db.execute('SELECT profile FROM authority_runtime_profile').fetchone()[0],'FORMAL')
        self.assertEqual(db.execute('SELECT count(*) FROM resource_claims').fetchone()[0],0)
        self.assertEqual(db.execute('SELECT count(*) FROM authority_registrations').fetchone()[0],0)
        db.close()
    def test_wrong_sha_unknown_partial_and_missing_freeze_rejected(self):
        with self.assertRaisesRegex(ValueError,'BACKUP_SHA256'): migration.apply(self.ledger,self.backup,'0'*64,self.fp,self.freeze,'op')
        os.unlink(self.freeze)
        with self.assertRaises(OSError): self.apply()
        open(self.freeze,'w').close()
        db=sqlite3.connect(self.ledger); db.execute('ALTER TABLE tasks ADD COLUMN partial TEXT'); db.commit(); db.close()
        with self.assertRaisesRegex(ValueError,'LEDGER_NOT_EXACT_BACKUP_COPY'): self.apply()
    def test_every_step_failure_rolls_back_and_retry_recovers(self):
        points=['after_lock']+['ddl_'+x[0] for x in migration.ADDITIONS]+['after_backfill','after_tables','before_commit']
        for point in points:
            shutil.copyfile(self.backup,self.ledger)
            with mock.patch.object(migration,'LEGACY_FINGERPRINT',self.fp), mock.patch.dict(os.environ,{'XUANJUN_MIGRATION_FAIL_AT':point}):
                with self.assertRaises(RuntimeError): migration.apply(self.ledger,self.backup,self.sha,self.fp,self.freeze,'op')
            db=sqlite3.connect(self.ledger); self.assertEqual(migration.schema_fingerprint(db),self.fp); db.close()
            self.assertEqual(self.apply()['state'],'COMMITTED')
    def test_concurrent_writer_lock_fails_closed(self):
        holder=sqlite3.connect(self.ledger,isolation_level=None); holder.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(sqlite3.OperationalError): self.apply()
        finally: holder.execute('ROLLBACK'); holder.close()

    def test_restart_recovery_unknown_reconciliation_and_constraints(self):
        receipt=self.apply('stable-op')
        # A fresh process-equivalent connection recovers the durable receipt.
        self.assertEqual(migration.query(self.ledger,'stable-op'),receipt)
        unknown=migration.query(self.ledger,'other-op')
        self.assertEqual(unknown,{'state':'UNKNOWN','operation_id':'other-op'})
        with self.assertRaisesRegex(ValueError,'DIFFERENT_OR_UNKNOWN_OPERATION'):
            self.apply('other-op')
        db=sqlite3.connect(self.ledger)
        db.execute('PRAGMA foreign_keys=ON')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO resource_claims VALUES('r','missing','a',1,1,'HELD',1)")
        indexes={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertTrue({'authority_tasks_task_id_uq','resource_claims_task_idx','authority_registrations_contract_idx'} <= indexes)
        db.close()

    @unittest.skipUnless(os.path.exists('/var/backups/xuanjun-authority/canonical-ledger-pre-authority-20261108T063834Z.sqlite'),'production backup unavailable')
    def test_observed_backup_schema_pin(self):
        # Metadata/schema/count only; never selects row content.
        self.assertEqual(migration.inspect('/var/backups/xuanjun-authority/canonical-ledger-pre-authority-20261108T063834Z.sqlite')['schema_fingerprint'],migration.LEGACY_FINGERPRINT)

if __name__=='__main__': unittest.main()
