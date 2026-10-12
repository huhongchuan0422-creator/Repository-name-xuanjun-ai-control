import os
import sqlite3
import tempfile
import unittest

from ledger_install_stage import stage_existing_registry, PROOF_KEYS

CORE = """CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,
lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL);
CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT,requested_at REAL,decided_at REAL);
CREATE TABLE events(id INTEGER PRIMARY KEY,task_id TEXT,event TEXT,created REAL,details TEXT);
CREATE TABLE owner_callback_requests(request_id TEXT PRIMARY KEY,task_id TEXT,fence INTEGER);
"""


class LedgerInstallStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = os.path.realpath(self.temp.name)
        self.source, self.rollback, self.generation = [self.root + '/' + x for x in
                                                      ('old.sqlite', 'rollback.sqlite', 'next.sqlite')]
        with sqlite3.connect(self.source) as db:
            db.execute('PRAGMA page_size=8192')
            db.executescript(CORE)
            for index, state in enumerate(['DONE'] * 7 + ['PENDING'] + ['WAITING_HUMAN'] * 2):
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                           (str(index), 'LEGACY', state, '[]', None, None, 17, '{"keep":true}', 1))
            db.execute("INSERT INTO owner_callback_requests VALUES('request','8',17)")
        self.proof = {key: True for key in PROOF_KEYS}

    def stage(self):
        return stage_existing_registry(self.source, self.rollback, self.generation,
                                       'owner/repo', self.proof)

    def test_preserves_ten_existing_tasks_and_callback_while_adding_only_side_tables(self):
        with open(self.source, 'rb') as f: original = f.read()
        result = self.stage()
        self.assertEqual(result['status'], 'STAGED_NOT_ACTIVE')
        self.assertEqual(result['new_tables'], ['execution_specs', 'worker_heartbeats'])
        self.assertEqual(result['generation']['counts']['tasks'], 10)
        self.assertEqual(result['generation']['counts']['execution_specs'], 0)
        self.assertEqual(result['rollback']['pragmas']['page_size'], 8192)
        self.assertEqual(result['generation']['pragmas']['page_size'], 8192)
        with open(self.source, 'rb') as f: self.assertEqual(f.read(), original)
        self.assertEqual(result['rollback']['counts']['owner_callback_requests'], 1)

    def test_missing_quiescence_proof_writes_nothing(self):
        self.proof['cgroups_empty'] = False
        with self.assertRaisesRegex(ValueError, 'QUIESCENCE'):
            self.stage()
        self.assertFalse(os.path.exists(self.rollback))
        self.assertFalse(os.path.exists(self.generation))

    def test_wal_committed_rows_are_included_without_raw_main_file_copy(self):
        writer = sqlite3.connect(self.source)
        self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute("INSERT INTO tasks VALUES('wal','LEGACY','DONE','[]',NULL,NULL,19,'{}',2)")
        writer.commit()
        self.assertTrue(os.path.exists(self.source + '-wal'))
        result = self.stage()
        self.assertEqual(result['rollback']['counts']['tasks'], 11)
        self.assertEqual(result['generation']['counts']['tasks'], 11)

    def test_unreconciled_lease_retains_snapshot_without_creating_generation(self):
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE tasks SET lease_owner='old-worker' WHERE id='7'")
        with self.assertRaisesRegex(ValueError, 'UNRECONCILED'):
            self.stage()
        self.assertTrue(os.path.exists(self.rollback))
        self.assertFalse(os.path.exists(self.generation))

    def test_target_sidecar_and_symlink_rejected_before_backup(self):
        with open(self.generation + '-wal', 'w') as f: f.write('retain')
        with self.assertRaisesRegex(ValueError, 'SIDECAR'):
            self.stage()
        self.assertFalse(os.path.exists(self.rollback))
        os.unlink(self.generation + '-wal')
        os.symlink(self.source, self.generation)
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse(os.path.exists(self.rollback))


if __name__ == '__main__':
    unittest.main()
