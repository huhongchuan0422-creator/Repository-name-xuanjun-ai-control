"""Chromium navigation using exact original page assets; no fixture identity or business data."""
import unittest
from playwright.sync_api import sync_playwright
from scripts.community_web_entries import asset,PREFIX

class BrowserEntries(unittest.TestCase):
    def test_original_role_navigation_assets_and_ungranted_state(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();errors=[];requests=[];operations=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                def respond(route):
                    path=route.request.url.removeprefix('https://uk.wenwenwenyiyiyi.work')
                    requests.append(path)
                    if route.request.method=='POST':
                        operations.append(route.request.post_data_json.get('operation'))
                    found=asset(path[len(PREFIX):]) if path.startswith(PREFIX+'/') else None
                    if found:
                        raw,mime=found
                        route.fulfill(status=200,body=raw,content_type=mime)
                    else:route.fulfill(status=404,body='not admitted')
                page.route('https://uk.wenwenwenyiyiyi.work/**',respond)
                page.goto('https://uk.wenwenwenyiyiyi.work'+PREFIX+'/merchant/workbench')
                for title,path in [('社区管理','/community/portal'),('平台入驻审核','/merchant/review'),('商家入驻','/merchant/join'),('商家工作台','/merchant/workbench')]:
                    page.get_by_role('navigation',name='角色入口',exact=True).get_by_role('link',name=title,exact=True).click()
                    self.assertEqual(page.url,'https://uk.wenwenwenyiyiyi.work'+PREFIX+path)
                    self.assertTrue(page.locator('h1').is_visible())
                self.assertEqual(errors,[])
                self.assertTrue(all(path.startswith(PREFIX+'/') for path in requests))
                self.assertFalse(any(path.endswith('/operations') for path in requests))
                self.assertTrue(operations)
                self.assertTrue(all(operation=='catalog' for operation in operations))
                self.assertEqual(page.evaluate('typeof window.configureCommunityWorkbench'),'function')
            finally:browser.close()

if __name__=='__main__':unittest.main()
