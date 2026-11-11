import os
import sqlite3
import tempfile
import unittest
from owner_approval_dispatch import prepare,ready

class TestDispatch(unittest.TestCase):
 def setUp(self):
  self.d=tempfile.TemporaryDirectory()
  self.db=os.path.join(self.d.name,'db.sqlite')
  c=sqlite3.connect(self.db)
  c.executescript("""CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER);
  CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT);
  INSERT INTO tasks VALUES('human','WAITING_HUMAN',2);
  INSERT INTO approvals VALUES('human','PENDING');""")
  c.commit();c.close()
 def tearDown(self):self.d.cleanup()
 def test_request_and_outbox_atomic(self):
  self.assertEqual(prepare(self.db,'123','123'),1)
  items=ready(self.db)
  self.assertEqual(len(items),1)
  self.assertEqual(len(items[0]['request_id']),32)
 def test_idempotent(self):
  prepare(self.db,'123','123')
  a=ready(self.db)[0]['request_id']
  self.assertEqual(prepare(self.db,'123','123'),0)
  self.assertEqual(ready(self.db)[0]['request_id'],a)
 def test_wrong_identity_rejected(self):
  with self.assertRaises(ValueError):prepare(self.db,'owner','chat')
 def test_old_fence_never_ready(self):
  prepare(self.db,'123','123')
  c=sqlite3.connect(self.db);c.execute("UPDATE tasks SET fence=3");c.commit();c.close()
  self.assertEqual(ready(self.db),[])
 def test_not_waiting_rejected(self):
  c=sqlite3.connect(self.db);c.execute("UPDATE tasks SET state='DONE'");c.commit();c.close()
  self.assertEqual(prepare(self.db,'123','123'),0)
  self.assertEqual(ready(self.db),[])
 def test_expired_acked_request_is_requeued(self):
  self.assertEqual(prepare(self.db,'123','123',now=1000,ttl=60),1)
  c=sqlite3.connect(self.db)
  first=c.execute("SELECT request_id FROM owner_notification_outbox").fetchone()[0]
  c.execute("UPDATE owner_notification_outbox SET state='ACKED',ack_message_id='45'")
  c.commit();c.close()
  self.assertEqual(prepare(self.db,'123','123',now=1030,ttl=60),0)
  self.assertEqual(prepare(self.db,'123','123',now=1061,ttl=60),1)
  c=sqlite3.connect(self.db)
  row=c.execute("SELECT request_id,state,ack_message_id FROM owner_notification_outbox").fetchone()
  c.close()
  self.assertNotEqual(row[0],first)
  self.assertEqual(row[1:3],('PENDING',None))
 def test_expired_pending_request_is_replaced(self):
  self.assertEqual(prepare(self.db,'123','123',now=1000,ttl=60),1)
  self.assertEqual(prepare(self.db,'123','123',now=1061,ttl=60),1)
  c=sqlite3.connect(self.db)
  self.assertEqual(c.execute("SELECT COUNT(*) FROM owner_notification_outbox").fetchone()[0],1)
  c.close()
if __name__=='__main__':unittest.main()
