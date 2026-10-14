"""Actual headless Chromium smoke against the one-process loopback Stage5 demo.
Requires: pip install playwright && python -m playwright install chromium.
Simulation only; never valid for payment or production acceptance.
"""
import json
import threading
import unittest
from http.server import HTTPServer
from playwright.sync_api import sync_playwright, expect
from scripts.community_demo_api import DemoService,handler,server_database

class BrowserE2E(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=server_database(":memory:")
  cls.http=HTTPServer(("127.0.0.1",0),handler(DemoService(cls.db)))
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
  cls.thread.start()
  cls.base="http://127.0.0.1:"+str(cls.http.server_address[1])
  cls.pw=sync_playwright().start()
  cls.browser=cls.pw.chromium.launch(headless=True)
 @classmethod
 def tearDownClass(cls):
  cls.browser.close()
  cls.pw.stop()
  cls.http.shutdown()
  cls.thread.join(timeout=5)
  cls.http.server_close()
  cls.db.close()
 def setUp(self):
  self.context=self.browser.new_context()
 def tearDown(self):
  self.context.close()
 def test_consumer_merchant_platform_use_same_order(self):
  consumer=self.context.new_page()
  consumer.goto(self.base+"/demo/")
  consumer.locator("#reference").fill("browser_demo_ref")
  consumer.locator("#amount").fill("150")
  consumer.locator("#create").click()
  expect(consumer.locator("#status")).to_contain_text("PENDING")
  self.assertTrue(consumer.locator("#successAd").is_hidden())
  merchant=self.context.new_page()
  merchant.goto(self.base+"/demo/merchant/")
  merchant.locator("#reference").fill("browser_demo_ref")
  merchant.locator("#load").click()
  expect(merchant.locator("#state")).to_contain_text("PENDING")
  platform=self.context.new_page()
  platform.goto(self.base+"/demo/platform/")
  platform.locator("#reference").fill("browser_demo_ref")
  platform.locator("#inspect").click()
  expect(platform.locator("#state")).to_contain_text("PENDING")
  consumer.locator("#complete").click()
  expect(consumer.locator("#status")).to_contain_text("SUCCESS")
  expect(consumer.locator("#successAd")).to_be_visible()
  merchant.locator("#load").click()
  platform.locator("#inspect").click()
  expect(merchant.locator("#state")).to_contain_text("SUCCESS")
  expect(platform.locator("#state")).to_contain_text("SUCCESS")
  self.assertEqual(platform.locator("#verified").inner_text(),"否")
  self.assertEqual(merchant.locator("#verified").inner_text(),"否")
 def test_change_input_removes_success_and_blocks_old_order(self):
  page=self.context.new_page()
  page.goto(self.base+"/demo/")
  page.locator("#reference").fill("browser_changed_ref")
  page.locator("#create").click()
  page.locator("#complete").click()
  expect(page.locator("#successAd")).to_be_visible()
  page.locator("#reference").fill("other_order")
  expect(page.locator("#successAd")).to_be_hidden()
  self.assertEqual(page.locator("#status").inner_text(),"未核实当前订单")
  page.locator("#complete").click()
  expect(page.locator("#error")).to_contain_text("请先创建")
 def test_malformed_simulation_browser_receipt_denied(self):
  page=self.context.new_page()
  page.route("**/demo/orders/simulate",lambda route:route.fulfill(
   status=200,content_type="application/json",
   body=json.dumps({"state":"SUCCESS","duplicate":"false"})))
  page.goto(self.base+"/demo/")
  page.locator("#reference").fill("browser_forged_ref")
  page.locator("#create").click()
  page.locator("#complete").click()
  expect(page.locator("#successAd")).to_be_hidden()
  expect(page.locator("#error")).to_contain_text("不匹配")
 def test_non_allowlisted_assets_and_fake_host_denied(self):
  page=self.context.new_page()
  response=page.goto(self.base+"/scripts/community_order_store.py")
  self.assertEqual(response.status,404)
  response=page.request.get(self.base+"/demo/",headers={"Host":"evil.example"})
  self.assertEqual(response.status,403)

if __name__=="__main__":unittest.main()
