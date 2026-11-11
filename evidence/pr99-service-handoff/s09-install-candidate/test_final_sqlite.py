from pathlib import Path
import sqlite3
import tempfile
import unittest
import final_materials as f
from migration_transaction import Hold, encode


class SqliteTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.source=self.root/'fixture.db';self.dest=self.root/'snapshot'
  self.db=sqlite3.connect(self.source);self.addCleanup(self.db.close)
  self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA wal_autocheckpoint=0')
  self.db.execute('CREATE TABLE fixture (id INTEGER PRIMARY KEY, value TEXT)');self.db.commit()
  self.db.execute('INSERT INTO fixture(value) VALUES (?)',('wal-only-row',));self.db.commit()
  schema=self.db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
  self.schema=f.sha(encode(schema))
 def snapshot(self,proof=lambda:'a'*64,**kwargs):
  return f.snapshot_sqlite_fenced(self.source,self.dest,proof,self.schema,**kwargs)
 def test_actual_wal_row_preserved_and_source_unchanged(self):
  main=self.source.read_bytes();wal=Path(str(self.source)+'-wal').read_bytes()
  r=self.snapshot();self.assertTrue(r['source_wal_captured']);self.assertFalse(r['source_database_opened'])
  with sqlite3.connect(f'file:{self.dest}/final.db?mode=ro',uri=True) as db:
   self.assertEqual(db.execute('SELECT value FROM fixture').fetchall(),[('wal-only-row',)])
   self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
  self.assertEqual(main,self.source.read_bytes());self.assertEqual(wal,Path(str(self.source)+'-wal').read_bytes())
  self.assertEqual((self.dest/'captured'/'source.db').read_bytes(),main)
  self.assertEqual((self.dest/'captured'/'source.db-wal').read_bytes(),wal)
 def test_no_wal_snapshot(self):
  self.db.close();r=self.snapshot();self.assertFalse(r['source_wal_captured'])
 def test_schema_mismatch_preserves_copy(self):
  self.schema='f'*64
  with self.assertRaisesRegex(Hold,'SQLITE_SCHEMA_MISMATCH'):self.snapshot()
  self.assertTrue((self.dest/'final.db').exists());self.assertFalse((self.dest/'sqlite-checkpoint.receipt.json').exists())
 def test_changed_source_fence_rejected(self):
  calls=iter(['a'*64,'b'*64])
  with self.assertRaisesRegex(Hold,'FENCE_CHANGED'):self.snapshot(lambda:next(calls))
 def test_source_changes_under_claimed_fence_rejected(self):
  count=0
  def fence():
   nonlocal count
   count+=1
   if count==2:self.db.execute('INSERT INTO fixture(value) VALUES (?)',('drift',));self.db.commit()
   return 'a'*64
  with self.assertRaisesRegex(Hold,'SOURCE_CHANGED'):self.snapshot(fence)
 def test_replay_refused(self):
  self.snapshot()
  with self.assertRaises(FileExistsError):self.snapshot()
 def test_timeout_preserves_partial(self):
  clock=iter([0,91])
  with self.assertRaisesRegex(Hold,'SQLITE_BACKUP_TIMEOUT'):self.snapshot(clock=lambda:next(clock))
  self.assertTrue((self.dest/'final.db').exists())
 def test_wal_symlink_rejected(self):
  self.db.close();other=self.root/'other';other.write_bytes(b'bad');Path(str(self.source)+'-wal').symlink_to(other)
  with self.assertRaisesRegex(Hold,'INPUT_SYMLINK'):self.snapshot()

if __name__=='__main__':unittest.main()
