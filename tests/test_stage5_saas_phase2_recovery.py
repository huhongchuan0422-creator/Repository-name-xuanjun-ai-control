import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.community_saas_phase2_recovery import backup,verify_backup
class RecoveryTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory()
    self.source=Path(self.temp.name)/"source.sqlite"
    self.target=Path(self.temp.name)/"backup.sqlite"
    db=sqlite3.connect(self.source)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO sample VALUES(1,'immutable')")
    db.commit();db.close()
 def tearDown(self):self.temp.cleanup()
 def test_01_backup_creates_verified_copy(self):
    x=backup(self.source,self.target)
    self.assertTrue(verify_backup(self.target,x["sha256"])["verified"])
 def test_02_no_in_place_overwrite(self):
    with self.assertRaises(ValueError):backup(self.source,self.source)
 def test_03_no_overwrite_existing_backup(self):
    backup(self.source,self.target)
    with self.assertRaises(ValueError):backup(self.source,self.target)
 def test_04_wrong_digest_rejected(self):
    backup(self.source,self.target)
    with self.assertRaisesRegex(ValueError,"BACKUP_DIGEST_MISMATCH"):
        verify_backup(self.target,"0"*64)
 def test_05_corrupt_backup_not_accepted(self):
    x=backup(self.source,self.target)
    self.target.write_bytes(b"not database")
    with self.assertRaises(ValueError):verify_backup(self.target,x["sha256"])
 def test_06_no_restore_side_effect(self):
    x=backup(self.source,self.target)
    self.assertFalse(x["restored"])
    a=sqlite3.connect(self.target)
    try:self.assertEqual(a.execute("SELECT value FROM sample").fetchone()[0],"immutable")
    finally:a.close()
 def test_07_missing_source_fails(self):
    with self.assertRaises(ValueError):backup(self.target,Path(self.temp.name)/"other.sqlite")
if __name__=="__main__":unittest.main()
