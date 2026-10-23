"""Real Chromium merchant editing and platform creative approval with local capabilities.
Never valid as live merchant account login or production financial permission.
"""
import os
import threading
import unittest
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
from scripts.community_demo_api import serve_local

M="stage5-browser-merchant-operator-capability-0123456789"
P="stage5-browser-platform-reviewer-capability-0123456789"

class AdminBrowser(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  with patch.dict(os.environ,{"XJ_STAGE5_DEMO_MERCHANT_TOKEN":M,
                              "XJ_STAGE5_DEMO_PLATFORM_TOKEN":P}):
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
 def test_real_browser_role_bound_catalog_and_moderation(self):
  merchant=self.ctx.new_page();merchant.goto(self.base+"/demo/merchant/")
  merchant.locator("#adminCapability").fill(M)
  merchant.locator("#editName").fill("Edited Demo Shop")
  merchant.locator("#saveProfile").click()
  expect(merchant.locator("#adminStatus")).to_contain_text("version")
  merchant.locator("#itemId").fill("edited_product")
  merchant.locator("#itemName").fill("Edited Product")
  merchant.locator("#saveItem").click()
  expect(merchant.locator("#adminStatus")).to_contain_text("written")
  merchant.locator("#adId").fill("new_approved_ad")
  merchant.locator("#adTitle").fill("New Approved Amount Creative")
  merchant.locator("#createAd").click()
  expect(merchant.locator("#adminStatus")).to_contain_text("campaign_id")
  merchant.locator("#submitAd").click()
  expect(merchant.locator("#adminStatus")).to_contain_text("REVIEW")
  platform=self.ctx.new_page();platform.goto(self.base+"/demo/platform/")
  platform.locator("#adminCapability").fill(P)
  platform.locator("#reviewAdId").fill("new_approved_ad")
  platform.locator("#approveCreative").click()
  expect(platform.locator("#adminStatus")).to_contain_text("APPROVED")
  merchant.locator("#adVersion").fill("3")
  merchant.locator("#approveAdState").click()
  expect(merchant.locator("#adminStatus")).to_contain_text("APPROVED")
  merchant.locator("#adVersion").fill("4")
  merchant.locator("#activateAd").click()
  expect(merchant.locator("#adminStatus")).to_contain_text("ACTIVE")
  consumer=self.ctx.new_page();consumer.goto(self.base+"/demo/")
  consumer.locator("#loadStorefront").click()
  expect(consumer.locator("#storefrontName")).to_have_text("Edited Demo Shop")
  expect(consumer.locator("#storefrontProducts")).to_contain_text("Edited Product")
  expect(consumer.locator("#adAmount")).to_contain_text("New Approved Amount Creative")
  self.assertTrue(consumer.locator("#successAd").is_hidden())
 def test_browser_without_capability_cannot_edit(self):
  page=self.ctx.new_page();page.goto(self.base+"/demo/merchant/")
  page.locator("#saveProfile").click()
  expect(page.locator("#adminStatus")).to_contain_text("操作未完成")
  page.locator("#adminCapability").fill(P)
  page.locator("#saveItem").click()
  expect(page.locator("#adminStatus")).to_contain_text("没有当前操作权限")
if __name__=="__main__":unittest.main()
