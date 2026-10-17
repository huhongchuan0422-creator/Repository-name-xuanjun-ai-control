import sqlite3
import unittest
from scripts.community_visual_feedback_identity import install,challenge,link,append_message,history
class LinkedFeedbackTests(unittest.TestCase):
 def setUp(self):
    self.db=sqlite3.connect(":memory:");install(self.db)
 def tearDown(self):self.db.close()
 def bind(self,channel="TELEGRAM",subject="tg42",customer="customerA",project="community"):
    token=challenge(self.db,customer,"tenantA",project,100)
    return link(self.db,token,channel,subject,110,verified_provider=True)
 def test_01_tg_binding(self):self.assertEqual(self.bind()["customer_id"],"customerA")
 def test_02_feishu_same_customer(self):
    self.bind();self.bind("FEISHU","feishu99")
    self.assertEqual(append_message(self.db,"m1","TELEGRAM","tg42","community","hello",120,True)["customer_id"],
                     append_message(self.db,"m2","FEISHU","feishu99","community","reply",121,True)["customer_id"])
 def test_03_web_same_customer(self):
    self.bind();self.bind("WEB","sessionA")
    append_message(self.db,"m1","WEB","sessionA","community","feedback",120,True)
    self.assertEqual(len(history(self.db,"customerA","tenantA","community")),1)
 def test_04_nickname_only_cannot_link(self):
    with self.assertRaises(PermissionError):link(self.db,"madeup","TELEGRAM","user_name",110,False)
 def test_05_no_unverified_insert(self):
    self.bind()
    with self.assertRaises(PermissionError):append_message(self.db,"m","TELEGRAM","tg42","community","x",120)
 def test_06_wrong_project(self):
    self.bind()
    with self.assertRaises(PermissionError):append_message(self.db,"m","TELEGRAM","tg42","wrong","x",120,True)
 def test_07_one_use_token(self):
    token=challenge(self.db,"customerA","tenantA","community",100)
    link(self.db,token,"TELEGRAM","tg42",110,True)
    with self.assertRaises(ValueError):link(self.db,token,"FEISHU","open123",111,True)
 def test_08_expired_token(self):
    token=challenge(self.db,"customerA","tenantA","community",100)
    with self.assertRaises(ValueError):link(self.db,token,"TELEGRAM","tg42",401,True)
 def test_09_conflicting_customer(self):
    self.bind()
    token=challenge(self.db,"customerB","tenantB","other",100)
    with self.assertRaises(PermissionError):link(self.db,token,"TELEGRAM","tg42",110,True)
 def test_10_no_history_leak(self):
    self.bind();append_message(self.db,"msg","TELEGRAM","tg42","community","hello",120,True)
    self.assertEqual(history(self.db,"customerB","tenantA","community"),[])
 def test_11_duplicate_delivery(self):
    self.bind();append_message(self.db,"msg","TELEGRAM","tg42","community","hello",120,True)
    with self.assertRaises(ValueError):append_message(self.db,"msg","TELEGRAM","tg42","community","hello",121,True)
 def test_12_append_only(self):
    self.bind();append_message(self.db,"msg","TELEGRAM","tg42","community","hello",120,True)
    with self.assertRaises(sqlite3.IntegrityError):
        self.db.execute("DELETE FROM visual_message_evidence")
 def test_13_history_chain(self):
    self.bind()
    a=append_message(self.db,"a","TELEGRAM","tg42","community","first",120,True)
    append_message(self.db,"b","TELEGRAM","tg42","community","second",121,True)
    self.assertEqual(self.db.execute("SELECT previous_sha256 FROM visual_message_evidence WHERE event_id='b'").fetchone()[0],a["record_sha256"])
if __name__=="__main__":unittest.main()
