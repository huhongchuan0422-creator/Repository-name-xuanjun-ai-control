import unittest
import tempfile
import os
import sqlite3
from scripts.community_merchant_store import open_store,upsert_profile,profile,put_item,list_items
S={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
A={"authenticated":True,"tenant_id":"t1","merchant_id":"m1","role":"MERCHANT_ADMIN"}
P={"name":"社区商家","description":"简介","contact":"123456","status":"ACTIVE"}
class StoreTests(unittest.TestCase):
 def setUp(self):
  self.db=open_store()
 def tearDown(self):self.db.close()
 def create(self):upsert_profile(self.db,S,A,P)
 def test_profile(self):
  self.create();self.assertEqual(profile(self.db,S)["name"],"社区商家")
 def test_cross_scope(self):
  self.create()
  for field in S:
   with self.assertRaises(ValueError):profile(self.db,dict(S,**{field:"other"}))
 def test_update_version(self):
  self.create();self.assertEqual(upsert_profile(self.db,S,A,P,1)["version"],2)
  with self.assertRaises(ValueError):upsert_profile(self.db,S,A,P,1)
 def test_admin_gate(self):
  with self.assertRaises(ValueError):upsert_profile(self.db,S,dict(A,role="STORE_STAFF"),P)
 def test_catalog(self):
  self.create()
  put_item(self.db,S,A,{"id":"p1","name":"产品","status":"ACTIVE","sort":2})
  put_item(self.db,S,A,{"id":"p2","name":"隐藏","status":"HIDDEN","sort":1})
  self.assertEqual([x["id"] for x in list_items(self.db,S)],["p1"])
 def test_foreign_key(self):
  with self.assertRaises(sqlite3.IntegrityError):put_item(self.db,S,A,{"id":"p1","name":"产品","status":"ACTIVE","sort":1})
 def test_bool_sort_rejected(self):
  self.create()
  with self.assertRaises(ValueError):put_item(self.db,S,A,{"id":"p1","name":"产品","status":"ACTIVE","sort":True})
 def test_persistence(self):
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"merchant.sqlite")
   db=open_store(path);upsert_profile(db,S,A,P);db.close()
   db=open_store(path);self.assertEqual(profile(db,S)["name"],"社区商家");db.close()
 def test_bad_schema_rejected_without_data_loss(self):
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"bad.sqlite")
   raw=sqlite3.connect(path);raw.execute("CREATE TABLE merchant_profiles(sentinel TEXT)");raw.execute("INSERT INTO merchant_profiles VALUES('keep')");raw.commit();raw.close()
   with self.assertRaises(ValueError):open_store(path)
   raw=sqlite3.connect(path);self.assertEqual(raw.execute("SELECT sentinel FROM merchant_profiles").fetchone()[0],"keep");raw.close()
 def test_paused_hidden(self):
  upsert_profile(self.db,S,A,dict(P,status="PAUSED"))
  with self.assertRaises(ValueError):profile(self.db,S)
if __name__=="__main__":unittest.main()
