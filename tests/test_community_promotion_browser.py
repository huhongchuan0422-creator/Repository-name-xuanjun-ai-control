"""Cross-role Chromium + real loopback HTTP for existing community promotions.

Uses synthetic existing Center identities/scenes only. No provider, payment, upload,
production host, or new business rule is introduced.
"""
import datetime
import os
import shutil
import queue
import re
import threading
import unittest

from playwright.sync_api import sync_playwright, expect
import test_community_reports as fixtures
from scripts.community_mini_http import serve


class CommunityPromotionBrowserJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()
    def test_admin_promotion_consumer_redeem_metrics_and_pause(self):
        ready=queue.Queue()
        def host():
            server=None;fx=None
            try:
                fx=fixtures.CommunityReportJourney();fx.setUp()
                fx.fx.gateway.commerce=fx.commerce
                server=serve(fx.fx.gateway,communities=fx.communities,commerce=fx.commerce)
                ready.put((server,fx));server.serve_forever(poll_interval=.05)
            except BaseException as error:
                ready.put(error)
            finally:
                if server:server.server_close()
                if fx:fx.tearDown()
        thread=threading.Thread(target=host,daemon=True);thread.start()
        state=ready.get(timeout=10)
        if isinstance(state,BaseException):raise state
        server,fx=state
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=(os.environ.get('COMMUNITY_CHROMIUM_EXECUTABLE') or shutil.which('google-chrome') or shutil.which('google-chrome-stable') or shutil.which('chromium')))
                try:
                    base='http://127.0.0.1:'+str(server.server_port)
                    admin_context=browser.new_context(extra_http_headers={'X-Center-Session':fx.web['token']})
                    admin=admin_context.new_page()
                    admin.goto(base+'/community/portal')
                    admin.evaluate("csrf=>window.configureCommunityPortal({csrf,workspace:'community'})",fx.web['csrf'])
                    expect(admin.locator('#message')).to_have_text('已连接原客户中心身份。')
                    admin.locator('#reference').fill(fx.cid)
                    admin.locator('#read').click();expect(admin.locator('#message')).to_have_text('操作完成')
                    expect(admin.locator('#reference')).to_have_value(fx.cid)

                    expires=fx.c.now()+86400
                    admin.locator('#promotionScene').fill('shop1')
                    admin.locator('#promotionTitle').fill('Synthetic browser promotion')
                    admin.locator('#promotionExpiry').fill(datetime.datetime.fromtimestamp(expires,datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M'))
                    admin.locator('#createPromotion').click()
                    expect(admin.locator('#promotionCode')).to_have_value(re.compile(r'^cp_[0-9a-f]{32}$'))
                    expect(admin.locator('#promotionVersion')).to_have_value('1')
                    code=admin.locator('#promotionCode').input_value()

                    consumer_context=browser.new_context()
                    consumer=consumer_context.new_page();consumer.goto(base+'/community/portal')
                    token=fx.token
                    def redeem():
                        return consumer.evaluate("""async arg=>{
                          const r=await fetch('/mini/api',{method:'POST',credentials:'omit',cache:'no-store',redirect:'error',
                            headers:{'Content-Type':'application/json','X-Community-Session':arg.token,'X-Community-Scene':'shop1'},
                            body:JSON.stringify({scene:'shop1',operation:'commerce.promotion_redeem',params:{code:arg.code}})});
                          return {status:r.status,body:await r.json()};
                        }""",{'token':token,'code':code})
                    first=redeem();second=redeem()
                    self.assertEqual((first['status'],second['status']),(200,200))
                    self.assertTrue(first['body']['result']['active']);self.assertTrue(second['body']['result']['active'])

                    admin.locator('#listPromotions').click();expect(admin.locator('#message')).to_have_text('操作完成')
                    expect(admin.locator('#records')).to_contain_text('Synthetic browser promotion')
                    expect(admin.locator('#records')).to_contain_text('新成员 1')
                    record=admin.evaluate("""async arg=>{
                      const r=await fetch('/community/directory',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':arg.csrf},
                        body:JSON.stringify({workspace:'community',operation:'promotions',params:{community_id:arg.community,after_id:''}})});
                      return {status:r.status,body:await r.json()};
                    }""",{'csrf':fx.web['csrf'],'community':fx.cid})
                    self.assertEqual(record['status'],200)
                    record=record['body']['result']['records'][0]
                    self.assertEqual((record['authenticated_redemptions'],record['new_members']),(1,1))
                    self.assertEqual(record['metrics'],'DISTINCT_AUTHENTICATED_REDEMPTIONS_ONLY')

                    admin.locator('#promotionState').select_option('PAUSED')
                    admin.locator('#savePromotionState').click()
                    expect(admin.locator('#promotionVersion')).to_have_value('2')
                    denied=redeem()
                    self.assertEqual(denied['status'],403)
                    self.assertEqual(denied['body']['error'],'ACCESS_DENIED')

                    admin.locator('#listPromotions').click();expect(admin.locator('#records')).to_contain_text('PAUSED')
                    final=admin.evaluate("""async arg=>{
                      const r=await fetch('/community/directory',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':arg.csrf},
                        body:JSON.stringify({workspace:'community',operation:'promotions',params:{community_id:arg.community,after_id:''}})});
                      return {status:r.status,body:await r.json()};
                    }""",{'csrf':fx.web['csrf'],'community':fx.cid})
                    self.assertEqual(final['status'],200)
                    final=final['body']['result']['records'][0]
                    self.assertEqual((final['authenticated_redemptions'],final['new_members']),(1,1))
                finally:
                    browser.close()
        finally:
            server.shutdown();thread.join(5)
            self.assertFalse(thread.is_alive(),'PROMOTION_BROWSER_SERVER_DID_NOT_STOP')


if __name__=='__main__':unittest.main()
