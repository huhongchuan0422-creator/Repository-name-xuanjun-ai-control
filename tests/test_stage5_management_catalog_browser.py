"""Actual two management previews consuming seeded merchant and ad SQLite over HTTP."""
import threading
import unittest
from playwright.sync_api import sync_playwright, expect
from scripts.community_demo_api import serve_local
from scripts.community_order_store import create_order, simulated_transition
from scripts.community_refund_preview_store import record_preview

class ManagementCatalogBrowser(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.http=serve_local(port=0)
  create_order(cls.http._owned_connections[0],{"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"},"management_order_1",145)
  create_order(cls.http._owned_connections[0],{"tenant_id":"tenant1","merchant_id":"merchant2","store_id":"store1"},"management_order_2",290)
  identity={"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"}
  simulated_transition(cls.http._owned_connections[0],identity,"management_order_1","management_success_event","SUCCESS",
                       {"simulation_only":True,"scope":identity,"reference":"management_order_1","amount_minor":145,
                        "provider_transaction_id":"management_fake_transaction"})
  record_preview(cls.http._owned_connections[1],cls.http._owned_connections[0],identity,"management_order_1","offline_preview_1",45)
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
 def test_business_overview_scoped_counts_and_ads(self):
  for route in ("/demo/merchant/","/demo/platform/"):
   page=self.ctx.new_page()
   page.goto(self.base+route)
   page.locator("#loadOverview").click()
   expect(page.locator("#overviewOrders")).to_contain_text("SUCCESS 1")
   expect(page.locator("#overviewRevenue")).to_contain_text("145 分")
   expect(page.locator("#overviewRevenue")).to_contain_text("真实收入：未知")
   expect(page.locator("#overviewAds")).to_contain_text("sample_amount")
   expect(page.locator("#overviewAds")).to_contain_text("sample_success")
   page.locator("#merchant").fill("merchant2")
   expect(page.locator("#overviewOrders")).to_have_text("")
   page.locator("#loadOverview").click()
   expect(page.locator("#overviewRevenue")).to_contain_text("290 分")
   expect(page.locator("#overviewAds")).to_have_text("暂无广告活动")
 def test_refund_preview_on_both_management_pages_not_a_payment(self):
  for route in ("/demo/merchant/","/demo/platform/"):
   page=self.ctx.new_page();page.goto(self.base+route)
   page.locator("#reference").fill("management_order_1")
   page.locator("#loadRefundPreview").click()
   expect(page.locator("#refundPreviewAmounts")).to_contain_text("预览退款 45分")
   expect(page.locator("#refundPreviewAmounts")).to_contain_text("余量 100分")
   expect(page.locator("#refundPreviewStatus")).to_contain_text("真实退款未执行")
   page.locator("#merchant").fill("merchant2")
   page.locator("#reference").fill("management_order_2")
   page.locator("#loadRefundPreview").click()
   expect(page.locator("#refundPreviewAmounts")).to_contain_text("预览退款 0分")
   self.assertNotIn("45分",page.locator("#refundPreviewAmounts").inner_text())
 def test_append_only_refund_preview_action_real_browser(self):
  page=self.ctx.new_page();page.goto(self.base+"/demo/merchant/")
  page.locator("#reference").fill("management_order_1")
  page.locator("#refundPreviewValue").fill("10")
  page.locator("#recordRefundPreview").click()
  expect(page.locator("#refundPreviewStatus")).to_contain_text("渠道退款未执行")
  expect(page.locator("#refundPreviewAmounts")).to_contain_text("55分")
  page.locator("#loadRefundPreview").click()
  expect(page.locator("#refundPreviewAmounts")).to_contain_text("预览退款 55分")
  page.locator("#refundPreviewValue").fill("100")
  page.locator("#recordRefundPreview").click()
  expect(page.locator("#refundPreviewStatus")).to_contain_text("预览登记失败")
  page.locator("#loadRefundPreview").click()
  expect(page.locator("#refundPreviewAmounts")).to_contain_text("预览退款 55分")
if __name__=="__main__":unittest.main()
