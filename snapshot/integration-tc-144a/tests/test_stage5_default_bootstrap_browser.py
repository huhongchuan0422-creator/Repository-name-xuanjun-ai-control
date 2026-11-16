"""Actual default serve_local startup / browser path, no injected test database."""
import threading
import unittest
from playwright.sync_api import sync_playwright, expect
from scripts.community_demo_api import serve_local

class DefaultBootstrapBrowser(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.http=serve_local(port=0)
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
 def test_default_bootstrap_loads_actual_browser_and_ad(self):
  page=self.ctx.new_page()
  page.goto(self.base+"/demo/")
  page.locator("#loadStorefront").click()
  expect(page.locator("#storefrontName")).to_have_text("Demo Merchant A")
  expect(page.locator("#storefrontProducts")).to_contain_text("Demo Merchant A Sample Item")
  expect(page.locator("#adAmount")).to_contain_text("DEMO APPROVED AMOUNT AD")
  self.assertTrue(page.locator("#successAd").is_hidden())
  page.locator("#merchant").fill("merchant2")
  page.locator("#loadStorefront").click()
  expect(page.locator("#storefrontName")).to_have_text("Demo Merchant B")
  expect(page.locator("#adAmount")).to_contain_text("当前无广告")
 def test_default_bootstrap_simulated_success_no_approved_receipt_ad(self):
  page=self.ctx.new_page()
  page.goto(self.base+"/demo/")
  page.locator("#reference").fill("bootstrap_test_unique")
  page.locator("#loadStorefront").click()
  expect(page.locator("#adAmount")).to_contain_text("DEMO APPROVED AMOUNT AD")
  page.locator("#create").click()
  expect(page.locator("#status")).to_contain_text("PENDING")
  page.locator("#complete").click()
  expect(page.locator("#status")).to_contain_text("SUCCESS")
  self.assertNotIn("DEMO SUCCESS AD MUST STAY HIDDEN",page.locator("body").inner_text())
  self.assertTrue(page.locator("#successAd").is_visible())

if __name__=="__main__":unittest.main()
