"""Real Chromium portal pagination, using only intercepted offline fixtures.

Authorization/lifecycle semantics remain covered by test_community_platform_merchants.
No server, account, provider or cloud service is contacted by these UI tests.
"""
import json
import os
import shutil
import subprocess
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1] / 'demos' / 'community-stage'


def merchant(workspace, name=None, status='ACTIVE', version=0):
    return dict(workspace=workspace, name=name or workspace, store_status='ACTIVE',
                lifecycle=dict(status=status, version=version, reason='fixture reason'),
                order_counts={}, finance_status='UNCONFIRMED')


def result(records, cursor=None):
    return dict(records=records, has_more=cursor is not None, next_cursor=cursor,
                coverage='ORIGINAL_PROJECT_ADMITTED_MERCHANTS')


class MerchantPortalNodeContracts(unittest.TestCase):
    def test_offline_javascript_contracts(self):
        completed = subprocess.run(
            ['node', '--test', str(Path(__file__).with_name('test_community_portal_pagination.mjs'))],
            cwd=ROOT.parents[1], text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


class MerchantPortalPagination(unittest.TestCase):
    @contextmanager
    def page(self, responses):
        init = '''window.calls=[];window.responses=RESPONSES;window.pending=[];
          window.fetch=(url,options)=>{
            const body=JSON.parse(options.body);
            window.calls.push({url,options,body});
            const fixture=window.responses.shift();
            if(!fixture)throw Error('Unexpected fixture request');
            const reply=()=>new Response(JSON.stringify(fixture.error?{error:fixture.error}:{result:fixture.result}),{status:fixture.status||200});
            if(fixture.delay)return new Promise(resolve=>window.pending.push(()=>resolve(reply())));
            return Promise.resolve(reply());
          };'''.replace('RESPONSES', json.dumps(responses))
        with sync_playwright() as p:
            # CI installs Playwright Chromium; local runs may explicitly select an installed binary.
            browser = p.chromium.launch(
                headless=True, chromium_sandbox=True,
                executable_path=(os.environ.get('COMMUNITY_CHROMIUM_EXECUTABLE')
                                 or shutil.which('google-chrome')
                                 or shutil.which('google-chrome-stable')
                                 or shutil.which('chromium')),
            )
            try:
                page = browser.new_page()
                page.add_init_script(init)
                def serve(route):
                    path = urlsplit(route.request.url).path
                    name = {'/community/portal': 'communities.html',
                            '/community/portal.js': 'communities.js'}.get(path)
                    if name:
                        route.fulfill(status=200, body=(ROOT / name).read_bytes(),
                                      content_type='text/html' if name.endswith('.html') else 'application/javascript')
                    else:
                        route.fulfill(status=404, body='')
                page.route('**/*', serve)
                page.goto('http://127.0.0.1:19876/community/portal')
                page.evaluate("configureCommunityPortal({csrf:'platform-token',workspace:'platform'})")
                yield page
            finally:
                browser.close()

    def complete(self, page):
        expect(page.locator('#message')).to_have_text('操作完成')
        expect(page.locator('#platformMerchants')).to_be_enabled()

    def test_multiple_pages_select_refresh_and_transport_contract(self):
        first = [merchant('merchant-%02d' % i) for i in range(50)]
        last = merchant('merchant-50', '<img src=x onerror=alert(1)>', 'PAUSED', 7)
        with self.page([{'result': result(first, 'merchant-49')},
                        {'result': result([last])}, {'result': result([])}]) as page:
            page.locator('#platformMerchants').click()
            self.complete(page)
            self.assertEqual(page.locator('#merchantRecords article').count(), 50)
            expect(page.locator('#moreMerchants')).to_be_visible()
            page.locator('#moreMerchants').click()
            expect(page.locator('#merchantRecords article')).to_have_count(1)
            expect(page.locator('#moreMerchants')).to_be_hidden()
            expect(page.locator('#merchantRecords')).to_contain_text(last['name'])
            self.assertEqual(page.locator('#merchantRecords img').count(), 0)
            page.locator('#merchantRecords button').click()
            expect(page.locator('#platformMerchantWorkspace')).to_have_value('merchant-50')
            expect(page.locator('#platformMerchantVersion')).to_have_value('7')
            expect(page.locator('#platformMerchantState')).to_have_value('PAUSED')
            expect(page.locator('#platformMerchantReason')).to_have_value('fixture reason')
            page.locator('#platformMerchants').click()
            expect(page.locator('#merchantRecords article')).to_have_count(0)
            expect(page.locator('#merchantResult')).to_have_text('暂无已准入商家')
            calls = page.evaluate('calls')
            self.assertEqual([c['body']['params'] for c in calls],
                             [{'after_workspace': ''}, {'after_workspace': 'merchant-49'}, {'after_workspace': ''}])
            for call in calls:
                self.assertEqual(call['url'], '/community/directory')
                self.assertEqual(call['body']['workspace'], 'platform')
                self.assertEqual(call['body']['operation'], 'platform_merchants')
                self.assertEqual(call['options']['headers']['X-CSRF-Token'], 'platform-token')
                self.assertEqual(call['options']['credentials'], 'same-origin')
                self.assertEqual(call['options']['cache'], 'no-store')
                self.assertEqual(call['options']['redirect'], 'error')

    def test_three_paginators_keep_independent_cursors_and_rows(self):
        community = dict(id='community-one', name='Community', state='ACTIVE')
        with self.page([
            {'result': result([merchant('merchant-a')], 'merchant-a')},
            {'result': dict(records=[community], has_more=True, next_cursor='community-one')},
            {'result': dict(records=[{'id': 4}], has_more=True, next_cursor=4)},
            {'result': result([merchant('merchant-b')])},
            {'result': dict(records=[], has_more=False)},
            {'result': dict(records=[], has_more=False)},
        ]) as page:
            page.locator('#platformMerchants').click()
            page.locator('#mine').click()
            expect(page.locator('#more')).to_be_visible()
            page.locator('#platformView').select_option('platform_orders')
            page.locator('#readPlatformView').click()
            expect(page.locator('#morePlatformView')).to_be_visible()
            page.locator('#moreMerchants').click()
            expect(page.locator('#merchantRecords')).to_contain_text('merchant-b')
            expect(page.locator('#records')).to_contain_text('Community')
            expect(page.locator('#more')).to_be_visible()
            expect(page.locator('#morePlatformView')).to_be_visible()
            page.locator('#more').click()
            page.locator('#morePlatformView').click()
            self.assertEqual(page.evaluate('calls.map(c=>[c.body.operation,c.body.params])'), [
                ['platform_merchants', {'after_workspace': ''}], ['mine', {}],
                ['platform_orders', {'after_id': 0, 'status': 'ALL'}],
                ['platform_merchants', {'after_workspace': 'merchant-a'}],
                ['mine', {'after_id': 'community-one'}],
                ['platform_orders', {'after_id': 4, 'status': 'ALL'}],
            ])

    def test_identity_switch_clears_rows_fields_cursor_and_rejects_late_response(self):
        with self.page([
            {'result': result([merchant('old-private', status='PAUSED', version=3)], 'old-private')},
            {'result': result([merchant('late-private')], 'late-private'), 'delay': True},
            {'result': result([merchant('new-visible')])},
        ]) as page:
            page.locator('#platformMerchants').click()
            page.locator('#merchantRecords button').click()
            page.locator('#moreMerchants').click()
            page.wait_for_function('pending.length === 1')
            expect(page.locator('#moreMerchants')).to_be_disabled()
            page.evaluate("configureCommunityPortal({csrf:'new-token',workspace:'new-platform'})")
            expect(page.locator('#merchantRecords')).to_be_empty()
            expect(page.locator('#merchantResult')).to_be_empty()
            expect(page.locator('#moreMerchants')).to_be_hidden()
            for field in ['platformMerchantWorkspace', 'platformMerchantVersion', 'platformMerchantReason']:
                expect(page.locator('#' + field)).to_have_value('')
            expect(page.locator('#platformMerchantState')).to_have_value('ACTIVE')
            page.locator('#platformMerchants').click()
            expect(page.locator('#merchantRecords')).to_contain_text('new-visible')
            page.evaluate('pending.shift()()')
            page.evaluate('()=>new Promise(resolve=>setTimeout(resolve,0))')
            self.assertNotIn('private', page.locator('body').text_content())
            expect(page.locator('#moreMerchants')).to_be_hidden()
            self.assertEqual(page.evaluate('calls[2].body.params'), {'after_workspace': ''})
            self.assertEqual(page.evaluate('calls[2].body.workspace'), 'new-platform')
            self.assertEqual(page.evaluate("calls[2].options.headers['X-CSRF-Token']"), 'new-token')
            page.evaluate('configureCommunityPortal(null)')
            page.locator('#platformMerchants').click()
            expect(page.locator('#message')).to_have_text('需要客户中心登录')
            self.assertEqual(page.evaluate('calls.length'), 3)

    def test_failed_next_page_preserves_retry_cursor_and_blocks_duplicate_requests(self):
        with self.page([
            {'result': result([merchant('merchant-a')], 'merchant-a')},
            {'error': 'TEMPORARY_UNAVAILABLE', 'status': 503, 'delay': True},
            {'result': result([merchant('merchant-b')])},
        ]) as page:
            page.locator('#platformMerchants').click()
            page.locator('#moreMerchants').click()
            page.wait_for_function('pending.length === 1')
            page.evaluate("document.getElementById('moreMerchants').onclick();document.getElementById('platformMerchants').onclick()")
            self.assertEqual(page.evaluate('calls.length'), 2)
            page.evaluate('pending.shift()()')
            expect(page.locator('#message')).to_have_text('TEMPORARY_UNAVAILABLE')
            expect(page.locator('#merchantRecords')).to_contain_text('merchant-a')
            expect(page.locator('#moreMerchants')).to_be_enabled()
            page.locator('#moreMerchants').click()
            expect(page.locator('#merchantRecords')).to_contain_text('merchant-b')
            self.assertEqual(page.evaluate('calls[2].body.params'), {'after_workspace': 'merchant-a'})

    def test_denied_refresh_clears_previous_list_and_cursor(self):
        with self.page([
            {'result': result([merchant('merchant-a')], 'merchant-a')},
            {'error': 'PLATFORM_MERCHANT_OPERATOR_REQUIRED', 'status': 403},
        ]) as page:
            page.locator('#platformMerchants').click()
            page.locator('#platformMerchants').click()
            expect(page.locator('#message')).to_have_text('PLATFORM_MERCHANT_OPERATOR_REQUIRED')
            expect(page.locator('#merchantRecords')).to_be_empty()
            expect(page.locator('#merchantResult')).to_be_empty()
            expect(page.locator('#moreMerchants')).to_be_hidden()
            expect(page.locator('#platformMerchants')).to_be_enabled()

    def test_invalid_or_repeated_cursor_never_enables_next_page(self):
        with self.page([
            {'result': result([merchant('merchant-a')], '')},
            {'result': result([merchant('merchant-a')], 'merchant-a')},
            {'result': result([merchant('merchant-a')], 'merchant-a')},
        ]) as page:
            page.locator('#platformMerchants').click()
            expect(page.locator('#moreMerchants')).to_be_hidden()
            page.locator('#platformMerchants').click()
            expect(page.locator('#moreMerchants')).to_be_visible()
            page.locator('#moreMerchants').click()
            expect(page.locator('#moreMerchants')).to_be_hidden()


if __name__ == '__main__':
    unittest.main()
