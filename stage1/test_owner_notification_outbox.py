import os
import sqlite3
import tempfile
import unittest
from owner_notification_outbox import stage,pending,ack

class Tests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.db=os.path.join(self.d.name,'test.sqlite')
        con=sqlite3.connect(self.db)
        con.executescript("""CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER);
          CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT);
          INSERT INTO tasks VALUES('a','WAITING_HUMAN',3);
          INSERT INTO approvals VALUES('a','PENDING');
          INSERT INTO tasks VALUES('b','DONE',1);
          INSERT INTO approvals VALUES('b','APPROVE');""")
        con.commit();con.close()
    def tearDown(self): self.d.cleanup()
    def test_stage_only_waiting(self):
        self.assertEqual(stage(self.db),1)
        self.assertEqual(pending(self.db),[{'task_id':'a','fence':3,'channel':'TELEGRAM'}])
    def test_dedup(self):
        stage(self.db);self.assertEqual(stage(self.db),0)
    def test_ack_requires_message_id(self):
        stage(self.db)
        with self.assertRaises(ValueError):ack(self.db,'a',3,'bad')
        self.assertTrue(ack(self.db,'a',3,271))
        self.assertFalse(ack(self.db,'a',3,271))
        self.assertEqual(pending(self.db),[])
    def test_fence_change_creates_distinct_event(self):
        stage(self.db)
        con=sqlite3.connect(self.db);con.execute("UPDATE tasks SET fence=4 WHERE id='a'");con.commit();con.close()
        self.assertEqual(stage(self.db),1)
        self.assertEqual(len(pending(self.db)),2)
    def test_invalid_limit(self):
        stage(self.db)
        with self.assertRaises(ValueError):pending(self.db,0)
if __name__=='__main__':unittest.main()
