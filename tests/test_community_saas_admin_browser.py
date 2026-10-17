"""SaaS admin DOM contracts plus real browser/Center integration when available."""
import pathlib
import queue
import shutil
import subprocess
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SaasAdminDom(unittest.TestCase):
    def test_admin_dom_contracts(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is required for SaaS admin DOM contracts')
        subprocess.run([node, str(ROOT / 'tests/community_saas_admin_dom.cjs'),
                        str(ROOT / 'demos/community-stage/saas.js'),
                        str(ROOT / 'demos/community-stage/saas.html')],
                       check=True, cwd=ROOT, timeout=30)


class SaasAdminBrowser(unittest.TestCase):
    def test_original_center_admin_review_preflight_and_diagnostics(self):
        try:
            from playwright.sync_api import sync_playwright, expect
        except ImportError:
            self.skipTest('Playwright is not installed')
        import test_community_center_saas as fixture
        from scripts.community_mini_http import serve
        from scripts.community_center_saas import CenterSaas
        ready = queue.Queue()

        def host():
            fx = server = None
            try:
                fx = fixture.CustomerSaas()
                fx.setUp()
                q = fx.quote()
                order = fx.call('order_prepare', dict(quote_id=q['quote_id'], currency='CNY'))
                api = CenterSaas(fx.fx.center, fx.fx.stage.api, dict(fx.grants,
                    owner=dict(user_id=fx.fx.uid1, project='project1', principal=fx.fx.stage.owner)))
                server = serve(fx.fx.gateway, saas=api)
                ready.put((server, fx.one, order['order_id']))
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
        if isinstance(state, PermissionError):
            thread.join(timeout=10)
            self.skipTest('Local HTTP socket unavailable: ' + str(state))
        if isinstance(state, BaseException):
            raise state
        server, web, order_id = state
        try:
            with sync_playwright() as playwright:
                executable = next((shutil.which(name) for name in
                    ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable')
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
                    page.goto('http://127.0.0.1:' + str(server.server_port) + '/customer/saas')
                    page.evaluate('csrf=>configureCommunitySaas({csrf,workspace:"owner"})', web['csrf'])
                    expect(page.locator('#saasAdmin')).to_be_visible()
                    page.locator('#adminReload').click()
                    expect(page.locator('#adminOrders')).to_contain_text(order_id)
                    page.locator('#adminOrders').get_by_role('button', name='选择原订单').click()
                    page.locator('#reviewTaskId').fill('admin_browser_review')
                    page.locator('#reviewKind').select_option('REFUND')
                    page.locator('#reviewReason').fill('<img src=x onerror=alert(1)> review only')
                    page.locator('#reviewOpenForm button').click()
                    expect(page.locator('#adminReviews')).to_contain_text('PENDING')
                    self.assertEqual(page.locator('#adminReviews img').count(), 0)
                    page.locator('#adminReviews').get_by_role('button', name='选择待办').click()
                    page.locator('#closeEventId').fill('admin_browser_close')
                    page.locator('#closeState').select_option('CANCELLED')
                    page.locator('#reviewCloseForm button').click()
                    expect(page.locator('#adminReviews')).to_contain_text('CANCELLED')
                    page.locator('#refundReason').fill('Synthetic review, no refund')
                    page.locator('#refundPlanForm button').click()
                    expect(page.locator('#refundPlan')).to_contain_text('REFUND_REVIEW_ONLY')
                    expect(page.locator('#refundPlan')).to_contain_text('未执行退款')
                    page.locator('#adminDiagnostics').click()
                    expect(page.locator('#diagnosticResult')).to_contain_text('automatic_repair_executed')
                    for width in (360, 768, 1440):
                        page.set_viewport_size(dict(width=width, height=900))
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    page.evaluate('csrf=>configureCommunitySaas({csrf,workspace:"one"})', web['csrf'])
                    expect(page.locator('#saasAdmin')).to_be_hidden()
                    expect(page.locator('#adminOrders')).to_be_empty()
                    expect(page.locator('#refundPlan')).to_be_empty()
                    expect(page.locator('#reviewReason')).to_have_value('')
                    page.evaluate('configureCommunitySaas(null)')
                    expect(page.locator('#adminReload')).to_be_disabled()
                    self.assertFalse(errors)
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=10)


if __name__ == '__main__':
    unittest.main()
