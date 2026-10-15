"""Stage5 Phase2 actual Chromium test of authenticated offline SaaS experience."""
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from scripts.community_saas_modules import connect
from scripts.community_saas_offer_catalog import install as offer_install,create_offer,approve_offer
from scripts.community_saas_order_preparation import install as order_install,install_lifecycle
from scripts.community_saas_offline_handoff import install_reviews
from scripts.community_saas_phase2 import OfflineSaas,Principal
from scripts.community_saas_phase2_http import serve

CUSTOMER="stage5-phase2-customer-offline-token-123456789"
OWNER="stage5-phase2-owner-offline-token-12345678900"
class SaaSPhase2Browser(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    try:from playwright.sync_api import sync_playwright
    except ImportError:raise unittest.SkipTest("PLAYWRIGHT_NOT_INSTALLED")
    cls.tmp=tempfile.TemporaryDirectory()
    path=str(Path(cls.tmp.name)/"quote.sqlite")
    db=connect(path);offer_install(db)
    create_offer(db,"sku",1,"storefront_catalog","MONTHLY",
     [{"type":"MODULE_FEE","label":"license","cycle":"MONTH","quantity":1,
       "cny_minor":1000,"usd_minor":200,"cost_cny_minor":100,"cost_usd_minor":20}],term_days=30)
    approve_offer(db,"sku",1,"approval","costref",10)
    db.close()
    cls.q=sqlite3.connect(path,check_same_thread=False)
    cls.o=sqlite3.connect(":memory:",check_same_thread=False)
    order_install(cls.o);install_lifecycle(cls.o);install_reviews(cls.o)
    cls.server=serve(OfflineSaas(cls.q,cls.o,cls.q),{
      CUSTOMER:Principal("tenantA","CUSTOMER"),
      OWNER:Principal("tenantA","PLATFORM_OWNER")})
    cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
    cls.thread.start()
    cls.playwright=sync_playwright().start()
    cls.browser=cls.playwright.chromium.launch(headless=True)
 @classmethod
 def tearDownClass(cls):
    cls.browser.close();cls.playwright.stop()
    cls.server.shutdown();cls.thread.join(timeout=4);cls.server.server_close()
    cls.q.close();cls.o.close();cls.tmp.cleanup()
 def page(self,token):
    page=self.browser.new_page()
    page.goto("http://127.0.0.1:"+str(self.server.server_port)+"/offline/saas-panel")
    page.locator("#offlineToken").fill(token)
    return page
 def test_market_and_tenant_prices_visible(self):
    page=self.page(CUSTOMER)
    try:
        page.locator("#loadCatalog").click()
        page.locator("#requestState").get_by_text("仅展示已授权的离线数据",exact=False).wait_for(timeout=6000)
        self.assertIn("sku",page.locator("#moduleCatalog").inner_text())
        self.assertIn("¥10.00",page.locator("#moduleCatalog").inner_text())
        self.assertIn("未授权",page.locator("#moduleCatalog").inner_text())
    finally:page.close()
 def test_quote_and_order_prepare_never_settle(self):
    page=self.page(CUSTOMER)
    try:
        page.locator("#offerId").fill("sku")
        page.locator("#makeQuote").click()
        page.get_by_text("离线报价已冻结",exact=False).wait_for(timeout=6000)
        page.locator("#prepareOrder").click()
        page.get_by_text("订单准备成功",exact=False).wait_for(timeout=6000)
        self.assertIn("未开通权益",page.locator("#requestState").inner_text())
    finally:page.close()
 def test_owner_only_controls_fail_for_customer(self):
    page=self.page(CUSTOMER)
    try:
        page.locator("#ownerOfferId").fill("badsku")
        page.locator("#ownerCreate").click()
        page.get_by_text("未保存",exact=False).wait_for(timeout=6000)
        self.assertEqual(self.q.execute("SELECT COUNT(*) FROM saas_offer_versions WHERE offer_id='badsku'").fetchone()[0],0)
    finally:page.close()
if __name__=="__main__":unittest.main()
