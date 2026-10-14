import unittest
from scripts.community_merchant_store import open_store,upsert_profile
from scripts.community_ad_store import open_offline
from scripts.community_order_store import connect,create_order,simulated_transition
from scripts.community_refund_preview_store import open_refund_store,record_preview
from scripts.community_checkout_refund_preview_read import checkout_with_refund_preview
from scripts.community_ad_contract import SUCCESS
S={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
OTHER={"tenant_id":"t2","merchant_id":"m2","store_id":"s2"}
P={"name":"A","description":"B","contact":"C","status":"ACTIVE"}
def actor(s):return {"authenticated":True,"role":"MERCHANT_ADMIN","tenant_id":s["tenant_id"],"merchant_id":s["merchant_id"]}
class PreviewReadTests(unittest.TestCase):
 def setUp(self):
  self.m=open_store();self.a=open_offline();self.o=connect();self.r=open_refund_store()
  for s,amount in ((S,120),(OTHER,200)):
   upsert_profile(self.m,s,actor(s),dict(P,name=s["tenant_id"]))
   create_order(self.o,s,"r1",amount)
 def tearDown(self):self.m.close();self.a.close();self.o.close();self.r.close()
 def read(self,s=S):return checkout_with_refund_preview(self.m,self.a,self.o,self.r,s,"r1",150)
 def paid(self,s=S,amount=120):
  simulated_transition(self.o,s,"r1","evt_"+s["tenant_id"],"SUCCESS",{
   "simulation_only":True,"scope":s,"reference":"r1","amount_minor":amount,
   "provider_transaction_id":"tx_"+s["tenant_id"]})
 def test_read_pending_does_not_claim_refund(self):
  d=self.read()
  self.assertEqual(d["refund_preview"]["total_minor"],0)
  self.assertEqual(d["refund_preview"]["remaining_preview_minor"],120)
  self.assertFalse(d["financial_receipt_issued"])
  self.assertFalse(d["cross_database_atomic_snapshot"])
 def test_recorded_preview_is_scoped_without_receipt(self):
  self.paid()
  record_preview(self.r,self.o,S,"r1","rev1",45)
  d=self.read()
  self.assertEqual(d["refund_preview"]["total_minor"],45)
  self.assertEqual(d["refund_preview"]["remaining_preview_minor"],75)
  self.assertFalse(d["refund_preview"]["provider_refund_executed"])
  self.assertIsNone(d["ads"][SUCCESS])
  self.assertFalse(d["success_receipt_ad_allowed"])
  self.assertFalse(d["order"]["provider_settlement_verified"])
 def test_other_existing_scope_has_distinct_total(self):
  self.paid();self.paid(OTHER,200)
  record_preview(self.r,self.o,S,"r1","rev1",40)
  record_preview(self.r,self.o,OTHER,"r1","rev2",70)
  self.assertEqual(self.read()["refund_preview"]["total_minor"],40)
  self.assertEqual(self.read(OTHER)["refund_preview"]["total_minor"],70)
  self.assertEqual(self.read(OTHER)["order"]["amount_minor"],200)
 def test_missing_order_or_paused_merchant_fail_closed(self):
  with self.assertRaises(ValueError):
   checkout_with_refund_preview(self.m,self.a,self.o,self.r,S,"missing",150)
  upsert_profile(self.m,S,actor(S),dict(P,status="PAUSED"),1)
  with self.assertRaises(ValueError):self.read()
 def test_broken_optional_ad_does_not_drop_refund_summary(self):
  self.paid();record_preview(self.r,self.o,S,"r1","rev1",30)
  self.a.close()
  d=self.read()
  self.assertIsNone(d["ads"][SUCCESS])
  self.assertEqual(d["refund_preview"]["total_minor"],30)
 def test_closed_refund_database_fails_closed(self):
  self.r.close()
  with self.assertRaises(Exception):self.read()
 def test_corrupted_preview_total_rejected(self):
  self.paid()
  # A separate raw SQLite caller may have mutated rows; reject instead of issuing
  # a misleading remaining balance. The append-only journal itself forbids edits.
  self.r.execute("INSERT INTO refund_events VALUES(?,?,?,?,?,?,'OFFLINE_PREVIEW')",
                 ("t1","m1","s1","r1","manual_invalid",121))
  self.r.commit()
  with self.assertRaisesRegex(ValueError,"INVALID_REFUND_PREVIEW_TOTAL"):self.read()
if __name__=="__main__":unittest.main()
