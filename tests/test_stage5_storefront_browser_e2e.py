"""Real Chromium against server-injected local SQLite merchant and ads.
Simulation-only; never provider proof, authenticated session, or deployment.
"""
import json
import sqlite3
import threading
import unittest
from http.server import HTTPServer
from playwright.sync_api import sync_playwright, expect
from scripts.community_demo_api import DemoService, handler, server_database
from scripts.community_merchant_store import open_store, upsert_profile, put_item
from scripts.community_ad_store import open_offline, create_campaign, change_campaign_state, review_creative
from scripts.community_ad_contract import AMOUNT, SUCCESS

S={"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"}
T={"tenant_id":"tenant1","merchant_id":"merchant2","store_id":"store1"}
def actor(scope):
 return {"authenticated":True,"actor_id":"local-test-admin","role":"MERCHANT_ADMIN",
         "tenant_id":scope["tenant_id"],"merchant_id":scope["merchant_id"]}
def setup_store(db,scope,name):
 upsert_profile(db,scope,actor(scope),
  {"name":name,"description":"Fixture","contact":"offline","status":"ACTIVE"})
 put_item(db,scope,actor(scope),{"id":"item1","name":name+" product","status":"ACTIVE","sort":1})
def campaign(db,slot,cid):
 create_campaign(db,S,{"id":cid,"slot":slot,"starts_at":100,"ends_at":300,
   "title":"Sale s creative","target_url":"https://example.org/sale","priority":2},actor(S),100)
 change_campaign_state(db,S,cid,"REVIEW",actor(S),101,1)
 review_creative(db,S,cid,True,{"authenticated":True,"role":"PLATFORM_ADMIN","actor_id":"mod"},102,2)
 change_campaign_state(db,S,cid,"APPROVED",actor(S),103,3)
 change_campaign_state(db,S,cid,"ACTIVE",actor(S),104,4)

class StorefrontBrowser(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.m=open_store()
  cls.a=open_offline()
  cls.o=server_database(":memory:")
  setup_store(cls.m,S,"Store Alpha")
  setup_store(cls.m,T,"Store Beta")
  campaign(cls.a,AMOUNT,"amount_ad")
  campaign(cls.a,SUCCESS,"success_ad")
  # Test runner/thread requires explicit cross-thread connections, still one serial server.
  cls.m.backup(cls._copy_m:=sqlite3.connect(":memory:",check_same_thread=False))
  cls.a.backup(cls._copy_a:=sqlite3.connect(":memory:",check_same_thread=False))
  cls.http=HTTPServer(("127.0.0.1",0),handler(DemoService(cls.o,cls._copy_m,cls._copy_a,150)))
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
  cls.thread.start()
  cls.base="http://127.0.0.1:"+str(cls.http.server_address[1])
  cls.pw=sync_playwright().start()
  cls.browser=cls.pw.chromium.launch(headless=True)
 @classmethod
 def tearDownClass(cls):
  cls.browser.close();cls.pw.stop()
  cls.http.shutdown();cls.thread.join(5);cls.http.server_close()
  for db in (cls.m,cls.a,cls.o,cls._copy_m,cls._copy_a):db.close()
 def setUp(self): self.ctx=self.browser.new_context()
 def tearDown(self): self.ctx.close()
 def test_real_http_sqlite_browser_storefront_and_approved_amount_ad(self):
  page=self.ctx.new_page();page.goto(self.base+"/demo/")
  page.locator("#loadStorefront").click()
  expect(page.locator("#storefrontName")).to_have_text("Store Alpha")
  expect(page.locator("#storefrontProducts")).to_contain_text("Store Alpha product")
  expect(page.locator("#adAmount")).to_contain_text("Sale s creative")
  self.assertTrue(page.locator("#successAd").is_hidden())
  page.locator("#merchant").fill("merchant2")
  expect(page.locator("#storefrontName")).to_have_text("")
  page.locator("#loadStorefront").click()
  expect(page.locator("#storefrontName")).to_have_text("Store Beta")
  expect(page.locator("#storefrontProducts")).to_contain_text("Store Beta product")
  expect(page.locator("#adAmount")).to_contain_text("当前无广告")
  self.assertTrue(page.locator("#successAd").is_hidden())
 def test_simulated_success_never_reveals_real_success_campaign(self):
  page=self.ctx.new_page();page.goto(self.base+"/demo/")
  page.locator("#loadStorefront").click()
  expect(page.locator("#adAmount")).to_contain_text("Sale s creative")
  page.locator("#reference").fill("browser_storefront_receipt")
  page.locator("#create").click()
  expect(page.locator("#status")).to_contain_text("PENDING")
  page.locator("#complete").click()
  expect(page.locator("#status")).to_contain_text("SUCCESS")
  self.assertNotIn("success_ad",page.locator("body").inner_text())
  self.assertNotIn("Sale s creative",page.locator("#successAd").inner_text())
if __name__=="__main__":unittest.main()
