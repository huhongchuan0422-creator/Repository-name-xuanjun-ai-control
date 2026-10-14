import unittest
import sqlite3
from scripts.community_merchant_store import open_store,upsert_profile,put_item
from scripts.community_ad_store import open_offline
from scripts.community_storefront_snapshot import storefront_snapshot
from scripts.community_ad_contract import AMOUNT,SUCCESS
S={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
A={"authenticated":True,"tenant_id":"t1","merchant_id":"m1","role":"MERCHANT_ADMIN"}
P={"name":"示例门店","description":"简介","contact":"电话","status":"ACTIVE"}
class SnapshotTests(unittest.TestCase):
 def setUp(self):
  self.m=open_store();self.a=open_offline()
  upsert_profile(self.m,S,A,P)
  put_item(self.m,S,A,{"id":"service1","name":"服务","status":"ACTIVE","sort":0})
 def tearDown(self):
  self.m.close()
  try:self.a.close()
  except sqlite3.Error:pass
 def test_merchant_catalog_and_two_ad_fallbacks(self):
  result=storefront_snapshot(self.m,self.a,S,100)
  self.assertEqual(result["merchant"]["name"],"示例门店")
  self.assertEqual(result["products"][0]["id"],"service1")
  self.assertIsNone(result["ads"][AMOUNT]);self.assertIsNone(result["ads"][SUCCESS])
  self.assertFalse(result["payment_started"]);self.assertFalse(result["provider_settlement_verified"])
 def test_cross_scope_rejected(self):
  for field in S:
   with self.assertRaises(ValueError):storefront_snapshot(self.m,self.a,dict(S,**{field:"other"}),100)
 def test_paused_merchant_hidden(self):
  upsert_profile(self.m,S,A,dict(P,status="PAUSED"),1)
  with self.assertRaises(ValueError):storefront_snapshot(self.m,self.a,S,100)
 def test_invalid_time(self):
  with self.assertRaises(ValueError):storefront_snapshot(self.m,self.a,S,True)
 def test_ad_failure_nonblocking(self):
  for failing_db in (None,self.a):
   if failing_db is self.a:self.a.close()
   result=storefront_snapshot(self.m,failing_db,S,100)
   self.assertEqual(result["merchant"]["name"],"示例门店")
   self.assertEqual(result["products"][0]["id"],"service1")
   self.assertIsNone(result["ads"][AMOUNT])
   self.assertIsNone(result["ads"][SUCCESS])
 def test_missing_ad_table_nonblocking(self):
  broken=sqlite3.connect(":memory:")
  try:
   result=storefront_snapshot(self.m,broken,S,100)
   self.assertEqual(result["merchant"]["name"],"示例门店")
   self.assertEqual(len(result["products"]),1)
   self.assertIsNone(result["ads"][AMOUNT])
   self.assertIsNone(result["ads"][SUCCESS])
  finally:broken.close()
if __name__=="__main__":unittest.main()
