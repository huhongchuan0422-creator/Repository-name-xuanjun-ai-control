"""Customer SaaS page -> original Center session -> original SQLite SaaS stores."""
import queue
import threading
import unittest
from playwright.sync_api import sync_playwright,expect
import test_community_center_saas as fixture
from scripts.community_mini_http import serve
from scripts.community_center_saas import CenterSaas

class SaasCustomerBrowser(unittest.TestCase):
    def test_prices_quote_order_restore_and_session_clear(self):
        ready=queue.Queue()
        def host():
            fx=None;server=None
            try:
                fx=fixture.CustomerSaas();fx.setUp();fx.api=CenterSaas(fx.fx.center,fx.fx.stage.api,dict(fx.grants,owner=dict(user_id=fx.fx.uid1,project='project1',principal=fx.fx.stage.owner)));server=serve(fx.fx.gateway,saas=fx.api);ready.put((server,fx.one));server.serve_forever(poll_interval=.05)
            except BaseException as e:ready.put(e)
            finally:
                if server:server.server_close()
                if fx:fx.tearDown()
        thread=threading.Thread(target=host,daemon=True);thread.start();state=ready.get(timeout=10)
        if isinstance(state,BaseException):raise state
        server,web=state
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                try:
                    context=browser.new_context(extra_http_headers={'X-Center-Session':web['token']});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/customer/saas')
                    page.evaluate('csrf=>configureCommunitySaas({csrf,workspace:"one"})',web['csrf'])
                    page.locator('#catalog').click();expect(page.locator('#modules')).to_contain_text('storefront_catalog')
                    page.locator('#modules article').filter(has_text='商家商品展示').get_by_role('button',name='查看方案').click()
                    expect(page.locator('#offers')).to_contain_text('¥10.00');expect(page.locator('#offers')).to_contain_text('$2.00')
                    page.get_by_role('button',name='生成报价').click();expect(page.locator('#quote')).to_contain_text('MONTH')
                    page.locator('#prepare').click();expect(page.locator('#order')).to_contain_text('PREPARED_ONLY')
                    self.assertNotIn('cost_cny_minor',page.locator('#order').inner_text())
                    page.locator('#myOrders').click();expect(page.locator('#records')).to_contain_text('so_')
                    page.locator('#records').get_by_role('button',name='打开').click();page.locator('#readOrder').click();expect(page.locator('#order')).to_contain_text('PREPARED')
                    page.locator('#renewal').click();expect(page.locator('#renewalResult')).to_contain_text('payment_confirmed_by_adapter')
                    owner=context.new_page();owner.goto('http://127.0.0.1:'+str(server.server_port)+'/customer/saas')
                    owner.evaluate('csrf=>configureCommunitySaas({csrf,workspace:"owner"})',web['csrf']);expect(owner.locator('#pricing')).to_be_visible()
                    owner.locator('#offerId').fill('owner_browser_sku');owner.locator('#offerKind').select_option('BUYOUT');owner.locator('#addPriceLine').click()
                    owner.locator('[data-field=cny_minor]').fill('2000');owner.locator('[data-field=usd_minor]').fill('400');owner.locator('#pricingForm').get_by_role('button',name='保存新版本').click();expect(owner.locator('#pricingResult')).to_contain_text('新版本已保存')
                    owner.locator('#approvalRef').fill('owner_browser_approval');owner.locator('#costEvidenceRef').fill('owner_browser_cost');owner.locator('#approveForm button').click();expect(owner.locator('#pricingResult')).to_contain_text('方案批准结果')
                    owner.evaluate('configureCommunitySaas(null)');expect(owner.locator('#offerId')).to_have_value('');expect(owner.locator('#priceLines')).to_be_empty();owner.close()
                    for width in (360,768,1440):
                        page.set_viewport_size({'width':width,'height':900});self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                    page.evaluate('configureCommunitySaas(null)');expect(page.locator('#order')).to_be_empty();expect(page.locator('#records')).to_be_empty();self.assertFalse(errors)
                finally:browser.close()
        finally:server.shutdown();thread.join(timeout=10)

if __name__=='__main__':unittest.main()
