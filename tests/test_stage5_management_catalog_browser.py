"""Actual two management previews consuming seeded merchant and ad SQLite over HTTP."""
import threading
import unittest
from playwright.sync_api import sync_playwright, expect
from scripts.community_demo_api import serve_local
from scripts.community_order_store import create_order

class ManagementCatalogBrowser(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.http=serve_local(port=0)
  create_order(cls.http._owned_connections[0],{"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"},"management_order_1",145)
  create_order(cls.http._owned_connections[0],{"tenant_id":"tenant1","merchant_id":"merchant2","store_id":"store1"},"management_order_2",290)
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
  cls.thread.start()
  cls.base="http://127.0.0.1:"+str(cls.http.server_address[1])
  cls.pw=sync_playwright().start()
  cls.browser=cls.pw.chromium.launch(headless=True)
 @classmethod
 def tearDownClass(cls):
  cls.browser.close();cls.pw.stop()
  cls.http.shutdown();cls.thread.join(5);cls.http.server_close()
 def setUp(self):self.ctx=self.browser.new_context()
 def tearDown(self):self.ctx.close()
 def test_merchant_console_reads_actual_storefront(self):
  page=self.ctx.new_page();page.goto(self.base+"/demo/merchant/")
  page.locator("#loadCatalog").click()
  expect(page.locator("#catalogName")).to_have_text("Demo Merchant A")
  expect(page.locator("#catalogItems")).to_contain_text("Sample Item")
  expect(page.locator("#catalogAd")).to_contain_text("DEMO APPROVED AMOUNT AD")
  page.locator("#merchant").fill("merchant2")
  page.locator("#loadCatalog").click()
  expect(page.locator("#catalogName")).to_have_text("Demo Merchant B")
  expect(page.locator("#catalogAd")).to_contain_text("无金额页广告")
 def test_platform_console_reads_same_scoped_data(self):
  page=self.ctx.new_page();page.goto(self.base+"/demo/platform/")
  page.locator("#inspectCatalog").click()
  expect(page.locator("#catalogName")).to_have_text("Demo Merchant A")
  expect(page.locator("#catalogAd")).to_contain_text("DEMO APPROVED AMOUNT AD")
  self.assertNotIn("DEMO SUCCESS AD MUST STAY HIDDEN",page.locator("body").inner_text())
 def test_scoped_order_list_visible_in_both_management_panels(self):
  for route in ("/demo/merchant/","/demo/platform/"):
   page=self.ctx.new_page();page.goto(self.base+route)
   page.locator("#listOrders").click()
   expect(page.locator("#orderList")).to_contain_text("management_order_1")
   self.assertNotIn("management_order_2",page.locator("#orderList").inner_text())
   page.locator("#merchant").fill("merchant2")
   page.locator("#listOrders").click()
   expect(page.locator("#orderList")).to_contain_text("management_order_2")
   self.assertNotIn("management_order_1",page.locator("#orderList").inner_text())
if __name__=="__main__":unittest.main()
