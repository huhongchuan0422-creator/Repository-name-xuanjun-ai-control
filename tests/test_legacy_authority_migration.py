import json, os, shutil, sqlite3, tempfile, time, unittest
from unittest import mock
from scripts import legacy_authority_migration as migration

class LegacyAuthorityMigrationTest(unittest.TestCase):
 def setUp(self):
  self.root=tempfile.mkdtemp(); self.backup=os.path.join(self.root,'backup.db'); self.ledger=os.path.join(self.root,'ledger.db'); self.freeze=os.path.join(self.root,'freeze.json'); self.key=os.path.join(self.root,'key')
  open(self.key,'wb').write(b'k'*32)
  db=sqlite3.connect(self.backup); db.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,depends TEXT NOT NULL,lease_owner TEXT,lease_until REAL,fence INTEGER NOT NULL DEFAULT 0,checkpoint TEXT NOT NULL DEFAULT '{}',updated REAL NOT NULL)"); db.execute("CREATE INDEX legacy_state ON tasks(state)"); db.execute("INSERT INTO tasks VALUES('old','K','READY','[]',NULL,NULL,7,'{\"x\":1}',1)"); db.commit(); self.fp=migration.schema_fingerprint(db); db.close(); shutil.copyfile(self.backup,self.ledger); self.sha=migration.sha_file(self.backup); self.make_freeze()
 def tearDown(self): shutil.rmtree(self.root)
 def make_freeze(self,op='op',**kw):
  if os.path.exists(self.freeze): os.unlink(self.freeze)
  return migration.create_freeze(self.ledger,self.backup,self.sha,op,self.key,self.freeze,**kw)
 def apply(self,op='op'):
  with mock.patch.object(migration,'LEGACY_FINGERPRINT',self.fp): return migration.apply(self.ledger,self.backup,self.sha,self.fp,self.freeze,op,self.key)
 def test_success_is_conservative_idempotent_and_fk_indexed(self):
  first=self.apply(); self.make_freeze(); self.assertEqual(self.apply(),first); db=sqlite3.connect(self.ledger); self.assertEqual(db.execute('SELECT id,checkpoint,fence,task_id,authority_state,attempt_id,lease_id,epoch FROM tasks').fetchone(),('old','{"x":1}',7,'old','NONE','UNKNOWN','UNKNOWN',None)); self.assertEqual(db.execute('SELECT count(*) FROM authority_registrations').fetchone()[0],0); db.execute('PRAGMA foreign_keys=ON')
  with self.assertRaises(sqlite3.IntegrityError): db.execute("INSERT INTO resource_claims VALUES('r','missing','a',1,1,'HELD',1)")
  self.assertTrue(migration.FORMAL_INDEXES <= {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}); db.close()
 def test_receipt_attacks_fail_integrity(self):
  receipt=self.apply(); self.assertEqual(migration.query(self.ledger,'op'),receipt)
  for sql,args,error in [("UPDATE authority_migration_receipts SET receipt_json=?",('{}',),'INTEGRITY'),("UPDATE authority_migration_receipts SET receipt_sha256=?",('0'*64,),'INTEGRITY')]:
   shutil.copyfile(self.ledger,self.ledger+'.good'); db=sqlite3.connect(self.ledger); db.execute(sql,args); db.commit(); db.close()
   with self.assertRaisesRegex(ValueError,error): migration.query(self.ledger,'op')
   shutil.copyfile(self.ledger+'.good',self.ledger)
  with self.assertRaisesRegex(ValueError,'INTEGRITY_RECEIPT_MISSING'): migration.query(self.ledger,'other')
 def test_receipt_noncanonical_and_cross_binding_rejected(self):
  self.apply(); db=sqlite3.connect(self.ledger); raw=db.execute('SELECT receipt_json FROM authority_migration_receipts').fetchone()[0]; value=json.loads(raw); pretty=json.dumps(value,indent=2); db.execute('UPDATE authority_migration_receipts SET receipt_json=?,receipt_sha256=?',(pretty,__import__('hashlib').sha256(pretty.encode()).hexdigest())); db.commit(); db.close()
  with self.assertRaisesRegex(ValueError,'INTEGRITY'): migration.query(self.ledger,'op')
 def test_freeze_empty_stale_wrong_operation_tamper_and_state_change(self):
  open(self.freeze,'w').close()
  with self.assertRaisesRegex(ValueError,'FREEZE_INTEGRITY'): self.apply()
  self.make_freeze(ttl=-1)
  with self.assertRaisesRegex(ValueError,'FREEZE_EXPIRED'): self.apply()
  self.make_freeze('other')
  with self.assertRaisesRegex(ValueError,'FREEZE_BINDING'): self.apply()
  self.make_freeze(); data=json.load(open(self.freeze)); data['payload']['writer_state']='WRITER'; open(self.freeze,'w').write(json.dumps(data))
  with self.assertRaisesRegex(ValueError,'FREEZE_INTEGRITY'): self.apply()
  self.make_freeze(); os.utime(self.ledger,None)
  with self.assertRaisesRegex(ValueError,'FREEZE_DATABASE_STATE_CHANGED'): self.apply()
 def test_schema_spoof_and_partial_are_unknown(self):
  self.apply(); db=sqlite3.connect(self.ledger); db.execute("DELETE FROM authority_runtime_profile"); db.commit(); db.close(); self.assertEqual(migration.inspect(self.ledger)['classification'],'UNKNOWN_OR_PARTIAL')
  shutil.copyfile(self.backup,self.ledger); db=sqlite3.connect(self.ledger); db.execute('PRAGMA application_id=%d'%migration.APPLICATION_ID); db.execute('PRAGMA user_version=%d'%migration.SCHEMA_VERSION); db.commit(); db.close(); self.assertEqual(migration.inspect(self.ledger)['classification'],'UNKNOWN_OR_PARTIAL')
 def test_every_step_failure_rolls_back(self):
  points=['after_lock']+['ddl_'+x[0] for x in migration.ADDITIONS]+['after_backfill','after_tables','before_commit']
  for point in points:
   shutil.copyfile(self.backup,self.ledger); self.make_freeze()
   with mock.patch.object(migration,'LEGACY_FINGERPRINT',self.fp),mock.patch.dict(os.environ,{'XUANJUN_MIGRATION_FAIL_AT':point}):
    with self.assertRaises(RuntimeError): migration.apply(self.ledger,self.backup,self.sha,self.fp,self.freeze,'op',self.key)
   db=sqlite3.connect(self.ledger); self.assertEqual(migration.schema_fingerprint(db),self.fp); db.close()
 def test_concurrent_writer_rejected(self):
  holder=sqlite3.connect(self.ledger,isolation_level=None); holder.execute('BEGIN IMMEDIATE')
  try:
   with self.assertRaises(sqlite3.OperationalError): self.apply()
  finally: holder.execute('ROLLBACK'); holder.close()
 def test_probe_contains_no_rows(self):
  out=migration.probe(self.backup); self.assertEqual(out['task_count'],1); self.assertNotIn('old',json.dumps(out))

if __name__=='__main__': unittest.main()
