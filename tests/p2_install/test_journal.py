import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('install_journal',
    str(ROOT / 'production/p2_install/journal.py'))
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.plan = {'schema': 1, 'release': 'a' * 64,
                     'batches': ['release', 'backup', 'plugin']}

    def open(self):
        return j.Journal(self.directory.name, self.plan)

    def commit(self, db, batch, attempt):
        db.begin(batch, attempt, lambda *unused: True)
        db.finish(batch, attempt, {'receipt_sha256': 'b' * 64}, lambda *unused: True)

    def test_later_failure_preserves_commits_across_restart(self):
        with self.open() as db:
            self.commit(db, 'release', 'r1')
            self.commit(db, 'backup', 'b1')
            before = [db.latest(x) for x in ('release', 'backup')]
            db.begin('plugin', 'p1', lambda *unused: True)
        with self.open() as db:
            self.assertEqual(before, [db.latest(x) for x in ('release', 'backup')])
            self.assertEqual(db.latest('plugin')[1], 'RUNNING')
            with self.assertRaises(j.Hold):
                db.begin('plugin', 'p2', lambda *unused: True)
            db.reconcile_no_effect('plugin', 'p1', {'readback': 'NO_EFFECT'},
                                   lambda *unused: True)
            self.commit(db, 'plugin', 'p2')
            self.assertEqual(before, [db.latest(x) for x in ('release', 'backup')])

    def test_unknown_effect_cannot_enable_retry(self):
        with self.open() as db:
            db.begin('release', 'r1', lambda *unused: True)
            with self.assertRaises(j.Hold):
                db.reconcile_no_effect('release', 'r1', {'status': 'UNKNOWN'},
                                       lambda *unused: False)
            self.assertEqual(db.latest('release')[1], 'RUNNING')

    def test_previous_drift_blocks_next_batch(self):
        with self.open() as db:
            self.commit(db, 'release', 'r1')
            with self.assertRaises(j.Hold):
                db.begin('backup', 'b1', lambda *unused: False)
            self.assertIsNone(db.latest('backup'))

    def test_no_skipping_and_no_reinstall_of_committed_batch(self):
        with self.open() as db:
            with self.assertRaises(j.Hold):
                db.begin('plugin', 'p1', lambda *unused: True)
            self.commit(db, 'release', 'r1')
            with self.assertRaises(j.Hold):
                db.begin('release', 'r2', lambda *unused: True)

    def test_changed_plan_does_not_reset_history(self):
        with self.open() as db:
            self.commit(db, 'release', 'r1')
        self.plan['release'] = 'c' * 64
        with self.assertRaises(j.Hold):
            self.open()
        self.plan['release'] = 'a' * 64
        with self.open() as db:
            self.assertEqual(db.latest('release')[1], 'COMMITTED')

    def test_second_session_cannot_acquire_writer_lock(self):
        with self.open():
            with self.assertRaises(BlockingIOError):
                self.open()
        with self.open() as db:
            self.assertIsNone(db.latest('release'))

    def test_receipt_without_effect_verification_cannot_commit(self):
        with self.open() as db:
            db.begin('release', 'r1', lambda *unused: True)
            with self.assertRaises(j.Hold):
                db.finish('release', 'r1', {'receipt': 'present'}, lambda *unused: False)
            self.assertEqual(db.latest('release')[1], 'RUNNING')


if __name__ == '__main__':
    unittest.main()
