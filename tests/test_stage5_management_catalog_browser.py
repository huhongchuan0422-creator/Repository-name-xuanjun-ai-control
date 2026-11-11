"""Actual two management previews consuming seeded merchant and ad SQLite over HTTP."""
import threading
import unittest
from playwright.sync_api import sync_playwright, expect
from scripts.community_demo_api import serve_local
from scripts.community_order_store import create_order, simulated_transition
from scripts.community_refund_preview_store import record_preview
from scripts.community_demo_api import DemoService

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
  create_order(cls.http._owned_connections[0],identity,"management_preview_action",145)
  simulated_transition(cls.http._owned_connections[0],identity,"management_preview_action","management_action_success","SUCCESS",
                       {"simulation_only":True,"scope":identity,"reference":"management_preview_action",
                        "amount_minor":145,"provider_transaction_id":"management_action_tx"})
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
   expect(page.locator("#overviewOrders")).to_contain_text("SUCCESS 2")
   expect(page.locator("#overviewRevenue")).to_contain_text("290 分")
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
  page.locator("#reference").fill("management_preview_action")
  page.locator("#refundPreviewValue").fill("10")
  page.locator("#recordRefundPreview").click()
  expect(page.locator("#refundPreviewStatus")).to_contain_text("渠道退款未执行")
  expect(page.locator("#refundPreviewAmounts")).to_contain_text("10分")
  page.locator("#loadRefundPreview").click()
  expect(page.locator("#refundPreviewAmounts")).to_contain_text("预览退款 10分")
  page.locator("#refundPreviewValue").fill("140")
  page.locator("#recordRefundPreview").click()
  expect(page.locator("#refundPreviewStatus")).to_contain_text("预览登记失败")
  page.locator("#loadRefundPreview").click()
  expect(page.locator("#refundPreviewAmounts")).to_contain_text("预览退款 10分")
 def test_both_executable_channel_shells_issue_verify_signed_demo_qr(self):
  for route in ("/demo/mini/","/demo/official-h5/"):
   page=self.ctx.new_page()
   page.goto(self.base+route)
   page.locator("#issueQR").click()
   expect(page.locator("#result")).to_contain_text("已创建本地模拟签名凭证")
   expect(page.locator("#token")).to_contain_text("signature")
   page.locator("#verifyQR").click()
   expect(page.locator("#result")).to_contain_text("签名验证通过")
   page.locator("#merchant").fill("merchant2")
   expect(page.locator("#token")).to_have_text("")
   self.assertNotIn("真实支付",page.locator("#result").inner_text())
 def test_offline_split_preview_conserves_net_of_refunds_without_provider(self):
  identity={"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"}
  service=DemoService(self.http._owned_connections[0],refund_db=self.http._owned_connections[1])
  out=service.dispatch("POST","/demo/splits/preview",{
   **identity,"reference":"management_order_1","shares_bps":{"merchant":7000,"platform":3000}})
  self.assertEqual(sum(out["allocations_minor"].values()),100)
  self.assertEqual(out["allocatable_minor"],100)
  self.assertEqual(out["refund_preview_minor"],45)
  self.assertFalse(out["provider_settlement_verified"])
  self.assertFalse(out["provider_split_executed"])
  self.assertFalse(out["financial_receipt_issued"])
  self.assertFalse(out["cross_database_atomic_snapshot"])
 def test_platform_split_preview_real_chromium_no_settlement(self):
  page=self.ctx.new_page();page.goto(self.base+"/demo/platform/")
  page.locator("#reference").fill("management_order_1")
  page.locator("#loadSplitPreview").click()
  expect(page.locator("#splitStatus")).to_contain_text("真实结算未执行")
  expect(page.locator("#splitAmounts")).to_contain_text("商家：70分")
  expect(page.locator("#splitAmounts")).to_contain_text("平台：30分")
  self.assertNotIn("真实已结算",page.locator("#splitAmounts").inner_text())
  page.locator("#merchant").fill("merchant2")
  page.locator("#reference").fill("management_order_2")
  page.locator("#loadSplitPreview").click()
  expect(page.locator("#splitStatus")).to_contain_text("计算失败")
 def test_signed_channel_qr_checkout_creates_real_pending_sqlite_order(self):
  for route,reference in (("/demo/mini/","channel_mini_order"),("/demo/official-h5/","channel_h5_order")):
   page=self.ctx.new_page()
   page.goto(self.base+route)
   page.locator("#reference").fill(reference)
   page.locator("#issueQR").click()
   expect(page.locator("#result")).to_contain_text("已创建本地模拟签名凭证")
   page.locator("#verifyQR").click()
   expect(page.locator("#result")).to_contain_text("签名验证通过")
   page.locator("#checkoutQR").click()
   expect(page.locator("#result")).to_contain_text("已创建模拟待支付订单")
   order=self.http._owned_connections[0].execute(
      "SELECT state,amount_minor FROM orders WHERE reference=?",(reference,)).fetchone()
   self.assertEqual(order,("PENDING",120))
 def test_real_browser_reconciliation_preview_maintains_unknown_provider(self):
  for route in ("/demo/merchant/","/demo/platform/"):
   page=self.ctx.new_page()
   page.goto(self.base+route)
   page.locator("#loadReconciliation").click()
   expect(page.locator("#reconciliationStatus")).to_contain_text("真实渠道对账UNKNOWN")
   expect(page.locator("#reconciliationAmounts")).to_contain_text("渠道实收：UNKNOWN")
   expect(page.locator("#reconciliationAmounts")).to_contain_text("模拟SUCCESS订单：2")
   page.locator("#merchant").fill("merchant2")
   page.locator("#loadReconciliation").click()
   expect(page.locator("#reconciliationAmounts")).to_contain_text("模拟SUCCESS订单：0")
   expect(page.locator("#reconciliationAmounts")).to_contain_text("渠道实收：UNKNOWN")
 def test_qr_to_storefront_order_and_two_management_views_browser_journey(self):
  consumer=self.ctx.new_page()
  consumer.goto(self.base+"/demo/")
  consumer.locator("#loadStorefront").click()
  expect(consumer.locator("#storefrontName")).to_have_text("Demo Merchant A")
  expect(consumer.locator("#adAmount")).to_contain_text("DEMO APPROVED AMOUNT AD")
  self.assertTrue(consumer.locator("#successAd").is_hidden())
  mini=self.ctx.new_page()
  mini.goto(self.base+"/demo/mini/")
  mini.locator("#reference").fill("journey_scan_order")
  mini.locator("#issueQR").click()
  expect(mini.locator("#result")).to_contain_text("已创建本地模拟签名凭证")
  mini.locator("#verifyQR").click()
  expect(mini.locator("#result")).to_contain_text("签名验证通过")
  mini.locator("#checkoutQR").click()
  expect(mini.locator("#result")).to_contain_text("已创建模拟待支付订单")
  for route,query in (("/demo/merchant/","#load"),("/demo/platform/","#inspect")):
   page=self.ctx.new_page()
   page.goto(self.base+route)
   page.locator("#reference").fill("journey_scan_order")
   page.locator(query).click()
   expect(page.locator("#state")).to_contain_text("PENDING")
   expect(page.locator("#verified")).to_have_text("否")
   page.locator("#listOrders").click()
   expect(page.locator("#orderList")).to_contain_text("journey_scan_order")
   page.locator("#merchant").fill("merchant2")
   page.locator("#listOrders").click()
   self.assertNotIn("journey_scan_order",page.locator("#orderList").inner_text())
if __name__=="__main__":unittest.main()
