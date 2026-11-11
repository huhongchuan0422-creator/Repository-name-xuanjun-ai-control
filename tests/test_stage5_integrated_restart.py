"""Phase1 integrated durable restart canary for offline per-module SQLite files.

No financial ACID guarantee across files, no provider settlement or production.
"""
import os
import tempfile
import unittest
from scripts.community_order_store import connect,create_order,simulated_transition
from scripts.community_merchant_store import open_store,upsert_profile,put_item
from scripts.community_ad_store import open_offline,create_campaign,change_campaign_state,review_creative
from scripts.community_refund_preview_store import open_refund_store,record_preview
from scripts.community_demo_api import DemoService

IDENTITY={"tenant_id":"restart_tenant","merchant_id":"restart_merchant","store_id":"restart_store"}
OWNER={"authenticated":True,"role":"MERCHANT_ADMIN","actor_id":"offline_recovery_fixture",
       "tenant_id":"restart_tenant","merchant_id":"restart_merchant"}
MOD={"authenticated":True,"role":"PLATFORM_ADMIN","actor_id":"offline_recovery_reviewer"}

class DurableLocalRecovery(unittest.TestCase):
 def test_restart_recovers_order_catalog_campaign_refund_and_split_preview(self):
  with tempfile.TemporaryDirectory() as directory:
   paths=[os.path.join(directory,x+".sqlite") for x in ("orders","merchants","ads","refunds")]
   o,m,a,refund=connect(paths[0]),open_store(paths[1]),open_offline(paths[2]),open_refund_store(paths[3])
   try:
    upsert_profile(m,IDENTITY,OWNER,{"name":"Recovered Store","description":"Local fixture",
                                      "contact":"none","status":"ACTIVE"})
    put_item(m,IDENTITY,OWNER,{"id":"persisted_item","name":"Recovered Item","status":"ACTIVE","sort":1})
    campaign={"id":"persisted_ad","slot":"AD_SLOT_PAYMENT_AMOUNT",
              "starts_at":100,"ends_at":1000,"title":"Recovered Approved Ad",
              "target_url":"https://example.org/sale","priority":5}
    create_campaign(a,IDENTITY,campaign,OWNER,150)
    change_campaign_state(a,IDENTITY,"persisted_ad","REVIEW",OWNER,151,1)
    review_creative(a,IDENTITY,"persisted_ad",True,MOD,152,2)
    change_campaign_state(a,IDENTITY,"persisted_ad","APPROVED",OWNER,153,3)
    change_campaign_state(a,IDENTITY,"persisted_ad","ACTIVE",OWNER,154,4)
    create_order(o,IDENTITY,"persisted_order",100)
    simulated_transition(o,IDENTITY,"persisted_order","persisted_event","SUCCESS",
        {"simulation_only":True,"scope":IDENTITY,"reference":"persisted_order",
         "amount_minor":100,"provider_transaction_id":"persisted_tx"})
    record_preview(refund,o,IDENTITY,"persisted_order","persisted_refund_preview",15)
   finally:
    for conn in (o,m,a,refund):conn.close()
   o,m,a,refund=connect(paths[0]),open_store(paths[1]),open_offline(paths[2]),open_refund_store(paths[3])
   try:
    service=DemoService(o,m,a,200,refund)
    storefront=service.dispatch("POST","/demo/storefront",IDENTITY)
    self.assertEqual(storefront["merchant"]["name"],"Recovered Store")
    self.assertEqual(storefront["products"][0]["name"],"Recovered Item")
    self.assertEqual(storefront["ads"]["AD_SLOT_PAYMENT_AMOUNT"]["id"],"persisted_ad")
    self.assertIsNone(storefront["ads"]["AD_SLOT_PAYMENT_SUCCESS"])
    details=service.dispatch("POST","/demo/refunds/preview",{**IDENTITY,"reference":"persisted_order"})
    self.assertEqual(details["preview_total_minor"],15)
    self.assertFalse(details["provider_refund_executed"])
    split=service.dispatch("POST","/demo/splits/preview",
             {**IDENTITY,"reference":"persisted_order",
              "shares_bps":{"merchant":8000,"platform":2000}})
    self.assertEqual(sum(split["allocations_minor"].values()),85)
    self.assertFalse(split["provider_split_executed"])
    self.assertFalse(split["financial_receipt_issued"])
    self.assertFalse(split["cross_database_atomic_snapshot"])
    with self.assertRaises(Exception):
     refund.execute("DELETE FROM refund_events WHERE event_id='persisted_refund_preview'")
   finally:
    for conn in (o,m,a,refund):conn.close()
if __name__=="__main__":unittest.main()
