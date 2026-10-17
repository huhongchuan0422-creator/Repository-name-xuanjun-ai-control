"""Merchant discovery and frozen order lines on original Center/SQLite stores."""
import pathlib
import queue
import shutil
import subprocess
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WorkbenchRefundDom(unittest.TestCase):
    def test_contract(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node unavailable')
        subprocess.run([node, str(ROOT/'tests/community_workbench_refund_dom.cjs'),
            str(ROOT/'demos/community-stage/workbench.js'),
            str(ROOT/'demos/community-stage/workbench.html')], check=True, timeout=30)


class WorkbenchRefundBrowser(unittest.TestCase):
    def test_original_refund_pages_review_and_basket_snapshot(self):
        from playwright.sync_api import sync_playwright, expect
        import test_community_refund_directory as fixture
        from scripts.community_mini_http import serve
        from scripts.community_order_store import create_order
        from scripts.community_demo_bootstrap import DEMO_SCOPE
        ready = queue.Queue()

        def host():
            fx = server = None
            try:
                fx = fixture.RefundDirectory()
                fx.setUp()
                create_order(fx.fx.stage.o, DEMO_SCOPE, 'ordinary_amount_order', 101)
                # Synthetic historical requests belonging to another original user.
                # This does not assert provider payment or execute any funds action.
                for index in range(51):
                    fx.save('browser_request_'+str(index), uid=fx.fx.uid2, pointer=False)
                server = serve(fx.fx.gateway, operations=fx.ops, commerce=fx.commerce)
                ready.put((server, fx.web))
                server.serve_forever(poll_interval=.05)
            except BaseException as error:
                ready.put(error)
            finally:
                if server:
                    server.server_close()
                if fx:
                    fx.tearDown()

        thread = threading.Thread(target=host, daemon=True)
        thread.start()
        state = ready.get(timeout=15)
        if isinstance(state, BaseException):
            raise state
        server, web = state
        try:
            with sync_playwright() as playwright:
                executable = next((shutil.which(name) for name in
                    ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser')
                    if shutil.which(name)), None)
                options = dict(headless=True, chromium_sandbox=True)
                if executable:
                    options['executable_path'] = executable
                browser = playwright.chromium.launch(**options)
                try:
                    context = browser.new_context(extra_http_headers={'X-Center-Session': web['token']})
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/merchant/workbench')
                    page.evaluate('csrf=>configureCommunityWorkbench({csrf,workspace:"merchant"})', web['csrf'])
                    page.locator('#loadRefundApplications').click()
                    expect(page.locator('#refundApplications article')).to_have_count(50)
                    page.locator('#moreRefundApplications').click()
                    expect(page.locator('#refundApplications article')).to_have_count(1)
                    expect(page.locator('#moreRefundApplications')).to_be_hidden()
                    page.locator('#refundApplications button').click()
                    expect(page.locator('#refundApplicationRevision')).to_have_value('1')
                    page.locator('#refundApplicationDecision').select_option('REJECTED')
                    page.locator('#refundApplicationOpinion').fill('Synthetic review only')
                    page.locator('#decideRefundApplication').click()
                    expect(page.locator('#refundApplicationRevision')).to_have_value('2')
                    expect(page.locator('#refundApplicationResult')).to_contain_text('未执行退款')
                    page.locator('#readRefundApplication').click()
                    expect(page.locator('#refundApplicationResult')).to_contain_text('REJECTED')
                    expect(page.locator('#providerActions')).to_be_hidden()
                    page.locator('#detailReference').fill('basket')
                    page.locator('#readOrderLines').click()
                    expect(page.locator('#orderLines')).to_contain_text('sample_item')
                    expect(page.locator('#orderLines')).to_contain_text('冻结单价 101 分')
                    expect(page.locator('#completionRevision')).to_have_value('0')
                    page.locator('#completionNote').fill('No trusted payment exists')
                    page.locator('#completeOrder').click()
                    expect(page.locator('#notice')).to_contain_text('操作未确认')
                    expect(page.locator('#completionRevision')).to_have_value('0')
                    page.locator('#detailReference').fill('ordinary_amount_order')
                    page.locator('#readOrderLines').click()
                    expect(page.locator('#orderLines')).to_contain_text('普通金额订单')
                    expect(page.locator('#completionRevision')).to_have_value('')
                    for width in (360, 768, 1440):
                        page.set_viewport_size(dict(width=width, height=900))
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    page.evaluate('configureCommunityWorkbench(null)')
                    expect(page.locator('#refundApplications')).to_be_empty()
                    expect(page.locator('#orderLines')).to_be_empty()
                    expect(page.locator('#refundApplicationId')).to_have_value('')
                    expect(page.locator('#loadRefundApplications')).to_be_disabled()
                    self.assertFalse(errors)
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=10)


if __name__ == '__main__':
    unittest.main()
