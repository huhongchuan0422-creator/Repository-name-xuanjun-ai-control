import json,threading,unittest,sqlite3,tempfile,os
from http.client import HTTPConnection
from http.server import HTTPServer
from scripts.community_demo_api import DemoService,handler,server_database
from scripts.community_merchant_store import open_store,upsert_profile,put_item
from scripts.community_ad_store import open_offline,create_campaign,change_campaign_state,review_creative
from scripts.community_ad_contract import AMOUNT,SUCCESS
S={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
T={"tenant_id":"t2","merchant_id":"m2","store_id":"s2"}
P={"name":"Demo","description":"Intro","contact":"123","status":"ACTIVE"}
def owner(s):return {"authenticated":True,"actor_id":"local-owner","role":"MERCHANT_ADMIN","tenant_id":s["tenant_id"],"merchant_id":s["merchant_id"]}
class StorefrontHTTPTests(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory()
  mpath=os.path.join(self.dir.name,"merchants.sqlite")
  apath=os.path.join(self.dir.name,"ads.sqlite")
  initial=open_store(mpath);initial.close()
  initial=open_offline(apath);initial.close()
  # Serial HTTP handler executes in a dedicated server thread. Test database
  # handles must be explicitly opened for cross-thread use by that one thread.
  self.m=sqlite3.connect(mpath,check_same_thread=False)
  self.m.execute("PRAGMA foreign_keys=ON")
  self.a=sqlite3.connect(apath,check_same_thread=False)
  self.o=server_database(":memory:")
  for identity,name in ((S,"Shop A"),(T,"Shop B")):
   upsert_profile(self.m,identity,owner(identity),dict(P,name=name))
   put_item(self.m,identity,owner(identity),{"id":"p1","name":name+" Item","status":"ACTIVE","sort":1})
  self.http=HTTPServer(("127.0.0.1",0),handler(DemoService(self.o,self.m,self.a,150)))
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.http.shutdown();self.thread.join(3);self.http.server_close()
  for db in (self.m,self.a,self.o):db.close()
  self.dir.cleanup()
 def post(self,identity):
  con=HTTPConnection("127.0.0.1",self.http.server_address[1],timeout=3)
  con.request("POST","/demo/storefront",json.dumps(identity),headers={"Content-Type":"application/json"})
  res=con.getresponse();status=res.status;data=json.loads(res.read());con.close()
  return status,data
 def activate(self,slot,cid):
  rec={"id":cid,"slot":slot,"starts_at":100,"ends_at":300,"title":"Approved","target_url":"https://example.org/creative","priority":1}
  create_campaign(self.a,S,rec,owner(S),100)
  change_campaign_state(self.a,S,cid,"REVIEW",owner(S),101,1)
  review_creative(self.a,S,cid,True,{"authenticated":True,"role":"PLATFORM_ADMIN","actor_id":"local-mod"},102,2)
  change_campaign_state(self.a,S,cid,"APPROVED",owner(S),103,3)
  change_campaign_state(self.a,S,cid,"ACTIVE",owner(S),104,4)
 def test_actual_http_two_existing_scopes_with_different_data(self):
  a,x=self.post(S);b,y=self.post(T)
  self.assertEqual((a,b),(200,200))
  self.assertEqual((x["merchant"]["name"],y["merchant"]["name"]),("Shop A","Shop B"))
  self.assertEqual((x["products"][0]["name"],y["products"][0]["name"]),("Shop A Item","Shop B Item"))
 def test_two_ad_slots_only_amount_can_be_returned(self):
  self.activate(AMOUNT,"amount1");self.activate(SUCCESS,"success1")
  status,x=self.post(S)
  self.assertEqual(status,200);self.assertEqual(x["ads"][AMOUNT]["id"],"amount1")
  self.assertIsNone(x["ads"][SUCCESS])
  self.assertFalse(x["provider_settlement_verified"])
 def test_paused_shop_rejected(self):
  upsert_profile(self.m,S,owner(S),dict(P,status="PAUSED"),1)
  self.assertEqual(self.post(S)[0],400)
 def test_closed_ads_nonblocking(self):
  self.a.close()
  status,x=self.post(S)
  self.assertEqual(status,200);self.assertEqual(x["products"][0]["id"],"p1")
  self.assertIsNone(x["ads"][AMOUNT]);self.assertIsNone(x["ads"][SUCCESS])
 def test_missing_merchant_backend_refused(self):
  self.http.RequestHandlerClass=handler(DemoService(self.o))
  self.assertEqual(self.post(S)[0],400)
if __name__=="__main__":unittest.main()
