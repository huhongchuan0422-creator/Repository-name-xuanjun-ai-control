"""Local-only capability authentication and role isolation, actual HTTP/SQLite."""
import json
import os
import threading
import time
import unittest
from http.client import HTTPConnection
from unittest.mock import patch
from scripts.community_demo_api import serve_local

MERCHANT="merchant-local-integration-test-capability-000000000001"
PLATFORM="platform-local-integration-test-capability-000000000001"
S={"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"}
OTHER={"tenant_id":"tenant1","merchant_id":"merchant2","store_id":"store1"}

class LocalAdminHTTP(unittest.TestCase):
 def setUp(self):
  with patch.dict(os.environ,{"XJ_STAGE5_DEMO_MERCHANT_TOKEN":MERCHANT,
                             "XJ_STAGE5_DEMO_PLATFORM_TOKEN":PLATFORM}):
   self.server=serve_local(port=0)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
  self.thread.start()
  self.port=self.server.server_address[1]
 def tearDown(self):
  self.server.shutdown();self.thread.join(5);self.server.server_close()
 def post(self,path,data,capability=None):
  conn=HTTPConnection("127.0.0.1",self.port,timeout=4)
  headers={"Content-Type":"application/json"}
  if capability is not None: headers["X-Local-Admin-Capability"]=capability
  conn.request("POST",path,body=json.dumps(data),headers=headers)
  res=conn.getresponse();status=res.status;payload=json.loads(res.read());conn.close()
  return status,payload
 def request(self,identity,operation):
  return {"identity":identity,"operation":operation}
 def test_disabled_unknown_wrong_role_and_scope(self):
  cmd=self.request(S,{"item":{"id":"new","name":"Demo Item","sort":5,"status":"ACTIVE"}})
  self.assertEqual(self.post("/demo/admin/item",cmd)[0],403)
  self.assertEqual(self.post("/demo/admin/item",cmd,"unknown"*8)[0],403)
  self.assertEqual(self.post("/demo/admin/item",cmd,PLATFORM)[0],403)
  self.assertEqual(self.post("/demo/admin/item",self.request(OTHER,cmd["operation"]),MERCHANT)[0],403)
  self.assertEqual(self.post("/demo/admin/campaign/review",
     self.request(S,{"campaign_id":"ad","approved":True,"expected_version":2}),MERCHANT)[0],403)
 def test_authentic_merchant_profile_and_catalog_edits(self):
  update=self.request(S,{"record":{"name":"Demo New Name","description":"Offline only",
                                      "contact":"n/a","status":"ACTIVE"},"expected_version":1})
  status,data=self.post("/demo/admin/profile",update,MERCHANT)
  self.assertEqual(status,200);self.assertEqual(data["result"]["version"],2)
  put=self.request(S,{"item":{"id":"new_item","name":"New Item","sort":0,"status":"ACTIVE"}})
  self.assertEqual(self.post("/demo/admin/item",put,MERCHANT)[0],200)
  status,view=self.post("/demo/storefront",S)
  self.assertEqual(status,200)
  self.assertEqual(view["merchant"]["name"],"Demo New Name")
  self.assertIn("New Item",[x["name"] for x in view["products"]])
  self.assertIsNone(view["ads"]["AD_SLOT_PAYMENT_SUCCESS"])
 def test_platform_moderation_required_before_activation(self):
  now=int(time.time())
  campaign={"id":"real_demo_ad","slot":"AD_SLOT_PAYMENT_AMOUNT","starts_at":now-5,
            "ends_at":now+1000,"title":"New Approved Creative",
            "target_url":"https://example.org/sale","priority":15}
  self.assertEqual(self.post("/demo/admin/campaign/create",
      self.request(S,{"record":campaign}),MERCHANT)[0],200)
  status,_=self.post("/demo/admin/campaign/state",
       self.request(S,{"campaign_id":"real_demo_ad","state":"ACTIVE","expected_version":1}),MERCHANT)
  self.assertEqual(status,400)
  self.assertEqual(self.post("/demo/admin/campaign/state",
      self.request(S,{"campaign_id":"real_demo_ad","state":"REVIEW","expected_version":1}),MERCHANT)[0],200)
  self.assertEqual(self.post("/demo/admin/campaign/review",
      self.request(S,{"campaign_id":"real_demo_ad","approved":True,"expected_version":2}),PLATFORM)[0],200)
  self.assertEqual(self.post("/demo/admin/campaign/state",
      self.request(S,{"campaign_id":"real_demo_ad","state":"APPROVED","expected_version":3}),MERCHANT)[0],200)
  self.assertEqual(self.post("/demo/admin/campaign/state",
      self.request(S,{"campaign_id":"real_demo_ad","state":"ACTIVE","expected_version":4}),MERCHANT)[0],200)
  self.assertEqual(self.post("/demo/storefront",S)[1]["ads"]["AD_SLOT_PAYMENT_AMOUNT"]["id"],"real_demo_ad")
 def test_actors_cannot_be_injected_from_body(self):
  body=self.request(S,{"item":{"id":"exploit","name":"Unsafe","sort":0,"status":"ACTIVE"}})
  body["actor"]={"authenticated":True,"role":"PLATFORM_ADMIN"}
  self.assertEqual(self.post("/demo/admin/item",body,MERCHANT)[0],400)
if __name__=="__main__":unittest.main()
