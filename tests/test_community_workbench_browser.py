"""New merchant workbench against real HTTP and original SQLite fixture stores."""
import queue
import threading
import unittest
from playwright.sync_api import sync_playwright,expect
import test_community_center_operations as fixture
from scripts.community_mini_http import serve
from scripts.community_order_store import create_order

class MerchantWorkbenchBrowser(unittest.TestCase):
    def test_merchant_edits_profile_catalog_and_reads_export(self):
        ready=queue.Queue()
        def host():
            fx=None;server=None
            try:
                fx=fixture.ExistingCenterOperations();fx.setUp()
                rt=fx.fx.stage.api
                create_order(rt.demo.db,rt.bindings[fx.fx.stage.merchant],'browser_order',1250)
                rt.simulate_from_operator(fx.fx.stage.owner,'browser_order','paid_fixture','SUCCESS','browser_fixture_tx')
                server=serve(fx.fx.gateway,operations=fx.operations);ready.put((server,fx.web));server.serve_forever(poll_interval=.05)
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
                    context=browser.new_context(extra_http_headers={'X-Center-Session':web['token']})
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/merchant/workbench')
                    page.evaluate('(csrf)=>configureCommunityWorkbench({csrf,workspace:"merchant"})',web['csrf'])
                    self.assertTrue(page.locator('#billAudit').count()==1)
                    self.assertTrue(page.locator('#billResult').count()==1)
                    self.assertTrue(page.locator('#billSection').is_hidden())
                    page.evaluate('(csrf)=>configureCommunityWorkbench({csrf,workspace:"merchant",providerWorkspace:"finance"})',web['csrf'])
                    self.assertFalse(page.locator('#billSection').is_hidden())
                    calls=[]
                    def fake_bill(route):
                        calls.append(route.request.post_data_json)
                        route.fulfill(status=200,content_type='application/json',
                            body='{"result":{"records":[],"has_more":false,"finance_status":"UNCONFIRMED"}}')
                    page.route('**/community/provider-actions',fake_bill)
                    page.locator('#billDate').fill('2026-10-16')
                    page.locator('#billAudit').click()
                    expect(page.locator('#billResult')).to_contain_text('UNCONFIRMED')
                    self.assertEqual(calls[-1]['operation'],'bill_audit')
                    self.assertEqual(calls[-1]['params']['after_id'],'')
                    page.unroute('**/community/provider-actions')
                    page.evaluate('(csrf)=>configureCommunityWorkbench({csrf,workspace:"merchant"})',web['csrf'])
                    self.assertTrue(page.locator('#billSection').is_hidden())
                    page.locator('#loadSettings').click();expect(page.locator('#notice')).to_have_text('操作完成')
                    page.locator('#name').fill('实际工作台编辑测试');page.locator('#profileStatus').select_option('PAUSED')
                    page.locator('#profileForm button').click();expect(page.locator('#notice')).to_have_text('操作完成')
                    page.locator('#loadSettings').click();expect(page.locator('#name')).to_have_value('实际工作台编辑测试');expect(page.locator('#profileStatus')).to_have_value('PAUSED')
                    page.locator('#itemId').fill('new_item');page.locator('#itemName').fill('商品编辑');page.locator('#itemForm button').click();expect(page.locator('#items')).to_contain_text('商品编辑')
                    page.locator('#items article').filter(has_text='new_item').get_by_role('button').click();page.locator('#itemStatus').select_option('HIDDEN');page.locator('#itemForm button').click();expect(page.locator('#items')).to_contain_text('HIDDEN')
                    page.locator('#loadOrders').click();expect(page.locator('#orders')).to_contain_text('browser_order')
                    page.locator('#orders').get_by_role('button',name='查看详情').click();expect(page.locator('#orderDetail')).to_contain_text('browser_order')
                    page.locator('#refundEvent').fill('browser_refund');page.locator('#refundAmount').fill('250');page.locator('#refundConfirm').check();page.locator('#refundForm button').click();expect(page.locator('#refundResult')).to_contain_text('退款预审已记录')
                    page.locator('#splitShares').fill('merchant,9000\nplatform,1000');page.locator('#splitForm button').click();expect(page.locator('#splitResult')).to_contain_text('merchant：900 分');expect(page.locator('#splitResult')).to_contain_text('platform：100 分')
                    with page.expect_download() as downloaded:page.locator('#exportOrders').click()
                    self.assertEqual(downloaded.value.suggested_filename,'community-orders-page.csv')
                    page.locator('#orderStatus').select_option('FAILED');page.locator('#loadOrders').click();expect(page.locator('#orders')).to_be_empty()
                    for width in (360,768,1440):
                        page.set_viewport_size({'width':width,'height':900});self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                    page.evaluate('configureCommunityWorkbench(null)');expect(page.locator('#name')).to_have_value('');expect(page.locator('#orders')).to_be_empty()
                    self.assertFalse(errors)
                finally:browser.close()
        finally:server.shutdown();thread.join(timeout=10)

if __name__=='__main__':unittest.main()
