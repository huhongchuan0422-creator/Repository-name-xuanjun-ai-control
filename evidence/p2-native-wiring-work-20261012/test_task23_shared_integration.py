from __future__ import print_function
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest

SOURCE=pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'
sys.path.insert(0,str(SOURCE))
from execution_supervision import ExecutionSupervisor,SCHEMA
from task_supervisor_inventory_adapter import canonical_inventory_page

class Activation(object):
    def __init__(self,binding): self.binding=dict(binding)
    def read(self,require_active=True): return dict(self.binding)

class SharedIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=os.path.join(self.tmp.name,'ledger.sqlite')
        db=sqlite3.connect(self.path,isolation_level=None);db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL)')
        db.execute('CREATE TABLE execution_specs(task_id TEXT PRIMARY KEY,hash TEXT NOT NULL)')
        db.executescript(SCHEMA)
        db.execute("INSERT INTO tasks VALUES('t','CODEX_EXEC','PENDING','[]',NULL,NULL,4,'{}',9999)")
        db.execute("INSERT INTO execution_specs VALUES('t',?)",('b'*64,))
        db.close()
        self.binding={'ledger_uuid':'00000000-0000-0000-0000-000000000001',
                      'generation':1,'epoch':2,'instance':'00000000-0000-0000-0000-000000000002',
                      'db_path':os.path.realpath(self.path)}
        self.supervisor=ExecutionSupervisor(self.path,lambda:100,activation_store=Activation(self.binding))
        info=os.stat(self.path);self.identity='%d:%d'%(info.st_dev,info.st_ino)

    def tearDown(self): self.tmp.cleanup()

    def _db(self):
        db=sqlite3.connect(self.path,isolation_level=None);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON');return db

    def observe(self):
        db=self._db();db.execute('BEGIN')
        try:return canonical_inventory_page(db,100,task_id='t',activation_binding=self.binding,ledger_identity=self.identity)['tasks'][0]
        finally:db.rollback();db.close()

    def record(self,intent):
        db=self._db();db.execute('BEGIN IMMEDIATE')
        try:
            result=self.supervisor.record_inventory_notice(db,intent,self.binding,self.identity)
            self.supervisor._assert_activation();db.execute('COMMIT');return result
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise
        finally:db.close()

    def test_unsupervised_notice_uses_existing_tables_only(self):
        db=self._db()
        before=[tuple(x) for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        db.close()
        intent=self.observe();result=self.record(intent)
        self.assertFalse(result['dispatch_performed']);self.assertEqual(result['receiver_ack'],'NOT_PROVEN')
        db=self._db()
        self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],1)
        self.assertEqual(db.execute('SELECT count(*) FROM supervision_delivery').fetchone()[0],2)
        after=[tuple(x) for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        db.close();self.assertEqual(before,after)

    def test_duplicate_notice_preserves_dead_letter(self):
        intent=self.observe();self.record(intent)
        db=self._db();db.execute("UPDATE supervision_delivery SET state='DEAD_LETTER',attempts=5");db.close()
        self.record(intent)
        db=self._db();rows=list(db.execute('SELECT state,attempts FROM supervision_delivery'));db.close()
        self.assertTrue(rows and all(tuple(x)==('DEAD_LETTER',5) for x in rows))

    def test_stale_fence_rejected_without_event(self):
        intent=self.observe()
        db=self._db();db.execute("UPDATE tasks SET fence=5 WHERE id='t'");db.close()
        with self.assertRaises(ValueError): self.record(intent)
        db=self._db();count=db.execute('SELECT count(*) FROM supervision_events').fetchone()[0];db.close()
        self.assertEqual(count,0)

if __name__=='__main__':unittest.main(verbosity=2)
