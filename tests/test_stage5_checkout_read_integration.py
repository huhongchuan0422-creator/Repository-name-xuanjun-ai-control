import unittest
from scripts.community_merchant_store import open_store, upsert_profile, put_item
from scripts.community_ad_store import open_offline, create_campaign, change_campaign_state, review_creative
from scripts.community_order_store import connect,create_order,simulated_transition
from scripts.community_checkout_read_integration import merchant_checkout_view
from scripts.community_ad_contract import AMOUNT,SUCCESS
S={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
OTHER={"tenant_id":"t2","merchant_id":"m2","store_id":"s2"}
P={"name":"Merchant","description":"Description","contact":"Contact","status":"ACTIVE"}
def actor(s):return {"authenticated":True,"role":"MERCHANT_ADMIN","actor_id":"admin","tenant_id":s["tenant_id"],"merchant_id":s["merchant_id"]}
MOD={"authenticated":True,"role":"PLATFORM_ADMIN","actor_id":"mod"}
class IntegratedReadTests(unittest.TestCase):
 def setUp(self):
  self.m=open_store();self.a=open_offline();self.o=connect()
  for s in (S,OTHER):
   upsert_profile(self.m,s,actor(s),P)
   put_item(self.m,s,actor(s),{"id":"p1","name":"Product","status":"ACTIVE","sort":1})
   create_order(self.o,s,"ref1",120)
 def tearDown(self):self.m.close();self.a.close();self.o.close()
 def active_ad(self,slot):
  cid="adAmount" if slot==AMOUNT else "adSuccess"
  record={"id":cid,"slot":slot,"starts_at":100,"ends_at":300,"title":"Ad","target_url":"https://example.org/ad","priority":1}
  create_campaign(self.a,S,record,actor(S),100)
  change_campaign_state(self.a,S,cid,"REVIEW",actor(S),110,1)
  review_creative(self.a,S,cid,True,MOD,120,2)
  change_campaign_state(self.a,S,cid,"APPROVED",actor(S),121,3)
  change_campaign_state(self.a,S,cid,"ACTIVE",actor(S),122,4)
 def view(self,scope=S):return merchant_checkout_view(self.m,self.a,self.o,scope,"ref1",150)
 def test_aggregates_active_merchant_product_and_order(self):
  x=self.view();self.assertEqual(x["merchant"]["name"],"Merchant")
  self.assertEqual(x["products"][0]["id"],"p1")
  self.assertEqual(x["order"]["amount_minor"],120)
  self.assertFalse(x["success_receipt_ad_allowed"])
 def test_simulation_success_does_not_release_receipt_ad(self):
  self.active_ad(AMOUNT);self.active_ad(SUCCESS)
  simulated_transition(self.o,S,"ref1","event1","SUCCESS",{"simulation_only":True,"scope":S,"reference":"ref1","amount_minor":120,"provider_transaction_id":"fake1"})
  x=self.view()
  self.assertEqual(x["ads"][AMOUNT]["id"],"adAmount")
  self.assertIsNone(x["ads"][SUCCESS])
  self.assertEqual(x["order"]["state"],"SUCCESS")
  self.assertFalse(x["order"]["provider_settlement_verified"])
  self.assertFalse(x["success_receipt_ad_allowed"])
 def test_missing_cross_scope_order_never_exposed(self):
  with self.assertRaises(ValueError):
   merchant_checkout_view(self.m,self.a,self.o,{"tenant_id":"t1","merchant_id":"m1","store_id":"other"},"ref1",150)
  with self.assertRaises(ValueError):
   merchant_checkout_view(self.m,self.a,self.o,S,"unknown",150)
 def test_paused_merchant_denies_checkout_view(self):
  upsert_profile(self.m,S,actor(S),dict(P,status="PAUSED"),1)
  with self.assertRaises(ValueError):self.view()
 def test_broken_ads_preserve_order_catalog(self):
  self.a.close()
  x=self.view()
  self.assertEqual(x["order"]["state"],"PENDING")
  self.assertEqual(len(x["products"]),1)
  self.assertIsNone(x["ads"][AMOUNT])
  self.assertIsNone(x["ads"][SUCCESS])
 def test_real_other_tenant_order_is_scoped(self):
  x=self.view(OTHER)
  self.assertEqual(x["order"]["reference"],"ref1")
  self.assertIsNone(x["ads"][SUCCESS])
if __name__=="__main__":unittest.main()
