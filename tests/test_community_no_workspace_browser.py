import json
import re
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

from scripts.community_web_entries import asset


ORIGIN = 'https://uk.wenwenwenyiyiyi.work'
BASE = ORIGIN + '/community-preview'


class NoWorkspaceBrowser(unittest.TestCase):
    def test_authenticated_account_without_workspace_sees_no_business_shell(self):
        evidence = Path('evidence/no-workspace-browser')
        evidence.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={'width': 1200, 'height': 720})
                page.add_init_script("sessionStorage.setItem('community-original-csrf','synthetic-no-workspace-csrf')")

                def route(request):
                    path = request.request.url.removeprefix(BASE)
                    if path == '/community/session/check':
                        request.fulfill(status=200, content_type='application/json', body=json.dumps({
                            'result': {'workspaces': [], 'reviewer': False, 'community_admin': None}
                        }))
                        return
                    result = asset(path)
                    if result is None:
                        request.fulfill(status=404, body='')
                        return
                    body, mime = result
                    request.fulfill(status=200, content_type=mime.split(';')[0], body=body)

                page.route(ORIGIN + '/**', route)
                page.goto(BASE + '/community/portal#merchant-workbench=catalog-management')
                expect(page.locator('body')).to_have_class(re.compile(r'\badmin-no-workspace\b'))
                expect(page.locator('.admin-brand')).to_be_hidden()
                expect(page.locator('.admin-sidebar')).to_be_hidden()
                expect(page.locator('body > main')).to_be_hidden()
                expect(page.locator('#community-session')).to_be_visible()
                expect(page.locator('#community-session form')).to_be_hidden()
                expect(page.locator('#community-session [role=status]')).to_have_text('已登录；当前账户没有此角色的工作区。')
                expect(page.locator('#community-session [data-logout]')).to_be_visible()
                expect(page.locator('iframe:visible')).to_have_count(0)
                page.screenshot(path=str(evidence / 'no-workspace-1200.png'), full_page=True)
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
