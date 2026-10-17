"""Real Chromium journey across shared StageRuntime HTTP boundary."""
import tempfile
import threading
import unittest
from playwright.sync_api import sync_playwright, expect
from scripts.community_stage_local import LocalStage
from scripts.community_saas_phase2 import Principal
from scripts.community_demo_bootstrap import fixture_stores, DEMO_SCOPE

class IntegratedBrowser(unittest.TestCase):
    def test_five_views_share_order_and_deny_customer_admin(self):
        with tempfile.TemporaryDirectory() as root:
            customer=Principal('tenant1','CUSTOMER')
            merchant=Principal('tenant1','MERCHANT_ADMIN')
            owner=Principal('tenant1','PLATFORM_OWNER')
            with LocalStage(root,{p:DEMO_SCOPE for p in (customer,merchant,owner)},DEMO_SCOPE) as app:
                m,a,_=fixture_stores()
                try:m.backup(app.demo.merchant_db);a.backup(app.demo.ad_db)
                finally:m.close();a.close()
                server=app.listen({'c'*32:customer,'m'*32:merchant,'p'*32:owner})
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    with sync_playwright() as p:
                        browser=p.chromium.launch(headless=True)
                        try:
                            page=browser.new_page()
                            page.goto('http://127.0.0.1:%s/offline/community-stage'%server.server_port)
                            page.locator('#token').fill('c'*32)
                            for view in ('storefront','mini','h5'):
                                page.locator('[data-view="%s"]'%view).click()
                                expect(page.locator('#merchant')).to_have_text('Demo Merchant A')
                            page.locator('#checkout').click()
                            expect(page.locator('#state')).to_have_text('模拟待支付；未发起微信扣款')
                            page.locator('#receipt').click()
                            expect(page.locator('#state')).to_have_text('MOCK_PENDING（模拟）')
                            expect(page.locator('#after')).to_have_text('')
                            app.runtime.simulate_from_operator(owner,'order1','event1','SUCCESS','tx1')
                            page.locator('#receipt').click()
                            expect(page.locator('#state')).to_have_text('MOCK_PAID_SIMULATED（模拟）')
                            expect(page.locator('#after')).not_to_be_empty()
                            page.locator('#orders').click()
                            expect(page.locator('#state')).to_have_text('请求被拒绝或数据不可用')
                            page.locator('#token').fill('m'*32)
                            expect(page.locator('#after')).to_have_text('')
                            page.locator('[data-view="merchant"]').click()
                            expect(page.locator('#merchant')).to_have_text('Demo Merchant A')
                            page.locator('#orders').click()
                            expect(page.locator('#output')).to_contain_text('order1')
                            page.locator('#token').fill('p'*32)
                            page.locator('[data-view="platform"]').click()
                            page.locator('#reconciliation').click()
                            expect(page.locator('#output')).to_contain_text('"simulated_success_total_minor": 101')
                            expect(page.locator('#output')).to_contain_text('UNKNOWN')
                            page.locator('#catalog').click()
                            expect(page.locator('#output')).to_contain_text('storefront_catalog')
                            self.assertEqual(app.demo.db.execute('SELECT count(*) FROM orders').fetchone()[0],1)
                        finally:browser.close()
                finally:server.shutdown();thread.join(3)

if __name__=='__main__':unittest.main()
