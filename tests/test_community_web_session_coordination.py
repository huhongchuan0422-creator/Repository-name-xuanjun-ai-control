"""Real Chromium negative capability checks; no identity/API responses fabricated."""
import unittest
from playwright.sync_api import sync_playwright,expect
from scripts.community_web_entries import asset,PREFIX

ORIGIN='https://uk.wenwenwenyiyiyi.work'
KEY='community-original-csrf'

class MissingCoordination(unittest.TestCase):
    def test_missing_api_and_channel_construction_failure_close_saved_state(self):
        cases={
            'locks_missing':"Object.defineProperty(navigator,'locks',{value:undefined});",
            'channel_missing':"window.BroadcastChannel=undefined;",
            'channel_constructor':"window.BroadcastChannel=class{constructor(){throw Error('synthetic unavailable');}};",
        }
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                for name,init in cases.items():
                    with self.subTest(case=name):
                        context=browser.new_context();errors=[];posts=[]
                        try:
                            context.add_cookies([{'url':ORIGIN,'name':'__Host-xj_customer','value':'s'*43,'httpOnly':True,'secure':True,'sameSite':'Strict'}])
                            context.add_init_script("sessionStorage.setItem('"+KEY+"','saved-old-csrf');"+init)
                            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                            def serve(route):
                                if route.request.method!='GET':
                                    posts.append(route.request.url);route.fulfill(status=403,body='not allowed');return
                                path=route.request.url.removeprefix(ORIGIN+PREFIX)
                                found=asset(path)
                                if found:
                                    raw,mime=found;route.fulfill(status=200,body=raw,content_type=mime,headers={'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'"})
                                else:route.fulfill(status=404,body='')
                            context.route(ORIGIN+'/**',serve);page.goto(ORIGIN+PREFIX+'/merchant/workbench')
                            expect(page.locator('#community-session [role=status]')).to_contain_text('不支持安全会话协调')
                            self.assertIsNone(page.evaluate("sessionStorage.getItem('"+KEY+"')"))
                            expect(page.locator('#community-session button[type=submit]')).to_be_disabled()
                            expect(page.locator('#loadOrders')).to_be_disabled()
                            page.locator('#community-session form').dispatch_event('submit')
                            page.locator('[data-logout]').dispatch_event('click');page.wait_for_timeout(50)
                            self.assertEqual(posts,[])
                            cookies=context.cookies(ORIGIN)
                            self.assertEqual(next(c['value'] for c in cookies if c['name']=='__Host-xj_customer'),'s'*43)
                            self.assertEqual(errors,[])
                        finally:context.close()
            finally:browser.close()

if __name__=='__main__':unittest.main()
