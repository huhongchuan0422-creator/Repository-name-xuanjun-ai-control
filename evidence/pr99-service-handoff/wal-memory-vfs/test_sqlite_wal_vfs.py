"""Private synthetic SQLite data only; no directory replacement or host calls."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sqlite_wal_vfs import recover, WalHold, MemoryVfs, _library, LIMIT


def schema_hash(connection):
    rows = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    return hashlib.sha256((json.dumps(rows, sort_keys=True, separators=(',', ':'))+'\n').encode()).hexdigest()


def fixture(rows=17, page_size=4096):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'fixture.db'
        c = sqlite3.connect(p)
        try:
            c.execute('PRAGMA page_size=' + str(page_size))
            c.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, value TEXT)')
            c.commit()
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA wal_autocheckpoint=0')
            c.executemany('INSERT INTO events(value) VALUES(?)', [('row-'+str(i),) for i in range(rows)])
            c.commit()
            main = p.read_bytes(); wal = p.with_name(p.name+'-wal').read_bytes()
            assert len(wal) > 32
            return main, wal, schema_hash(c)
        finally:
            c.close()


def restored_rows(raw):
    c = sqlite3.connect(':memory:')
    try:
        c.deserialize(raw)
        return c.execute('SELECT value FROM events ORDER BY id').fetchall()
    finally:
        c.close()


class WalTests(unittest.TestCase):
    def test_committed_rows_exist_only_in_nonempty_wal(self):
        main, wal, sha = fixture()
        original = (hashlib.sha256(main).hexdigest(), hashlib.sha256(wal).hexdigest())
        result, receipt = recover(main, wal, sha)
        self.assertEqual(restored_rows(result), [('row-'+str(i),) for i in range(17)])
        self.assertTrue(receipt['nonempty_wal_supplied'])
        self.assertEqual(receipt['vfs_opened_slots'], [0, 1])
        self.assertFalse(receipt['source_database_opened'])
        self.assertEqual(original, (hashlib.sha256(main).hexdigest(), hashlib.sha256(wal).hexdigest()))

    def test_no_wal_input_does_not_invent_wal_rows(self):
        main, _, sha = fixture()
        result, receipt = recover(main, None, sha)
        self.assertEqual(restored_rows(result), [])

    def test_schema_mismatch_holds(self):
        main, wal, _ = fixture()
        with self.assertRaisesRegex(WalHold, 'SCHEMA_MISMATCH'):
            recover(main, wal, 'a'*64)

    def test_progress_failure_does_not_return_partial_success(self):
        main, wal, sha = fixture()
        def denied(): raise WalHold('CALLER_FENCE_CHANGED')
        with self.assertRaises(WalHold): recover(main, wal, sha, denied)

    def test_bad_inputs_hold(self):
        main, wal, sha = fixture()
        for a, b, c in ((b'x'*100, wal, sha), (main, 'not-bytes', sha), (main, wal, 'bad')):
            with self.assertRaises(WalHold): recover(a, b, c)

    def test_other_page_sizes(self):
        for size in (512, 8192, 65536):
            main, wal, sha = fixture(3, size)
            result, _ = recover(main, wal, sha)
            self.assertEqual(len(restored_rows(result)), 3)

    def test_multiple_distinct_recoveries_not_global_default_vfs(self):
        for n in (1, 5, 2):
            main, wal, sha = fixture(n)
            result, _ = recover(main, wal, sha)
            self.assertEqual(len(restored_rows(result)), n)

    def test_vfs_rejects_any_unlisted_file_name(self):
        main, wal, _ = fixture()
        lib = _library(); handle = C.c_void_p()
        with MemoryVfs(lib, main, wal, lambda: None) as vfs:
            rc = lib.sqlite3_open_v2(b'/arbitrary/private.db', C.byref(handle), 2|4, vfs.name)
            self.assertNotEqual(rc, 0)
            if handle: self.assertEqual(lib.sqlite3_close(handle), 0)
            self.assertGreater(vfs.denied, 0)

    def test_truncated_wal_holds_instead_of_returning_old_main(self):
        main, wal, sha = fixture()
        for bad in (wal[:-1], wal[:31], b'x'*len(wal)):
            with self.assertRaises(WalHold): recover(main, bad, sha)

    def test_bad_frame_checksum_holds_instead_of_dropping_commit(self):
        main, wal, sha = fixture()
        bad = bytearray(wal); bad[-1] ^= 1
        with self.assertRaises(WalHold): recover(main, bytes(bad), sha)

    def test_uncommitted_tail_holds_conservatively(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'fixture.db'; c = sqlite3.connect(p)
            try:
                c.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, value TEXT)'); c.commit()
                c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0')
                c.execute('PRAGMA cache_size=5'); c.execute('PRAGMA cache_spill=ON')
                c.execute("INSERT INTO events(value) VALUES('committed')"); c.commit()
                sha = schema_hash(c)
                before = p.with_name(p.name+'-wal').stat().st_size
                c.executemany('INSERT INTO events(value) VALUES(?)', [('x'*6000,)]*30)
                wal = p.with_name(p.name+'-wal').read_bytes()
                self.assertGreater(len(wal), before)
                with self.assertRaises(WalHold): recover(p.read_bytes(), wal, sha)
            finally:
                c.close()

    def test_deadline_bound_and_expiry(self):
        main, wal, sha = fixture()
        for duration in (0, 91, True, '30'):
            with self.assertRaises(WalHold): recover(main, wal, sha, seconds=duration)
        with self.assertRaises(WalHold): recover(main, wal, sha, seconds=1e-12)

    def test_threaded_calls_are_serial_private_contexts(self):
        from concurrent.futures import ThreadPoolExecutor
        items = [fixture(n) for n in (2, 4, 6)]
        def run(item): return len(restored_rows(recover(*item)[0]))
        with ThreadPoolExecutor(max_workers=3) as p:
            self.assertEqual(list(p.map(run, items)), [2, 4, 6])


if __name__ == '__main__': unittest.main()
