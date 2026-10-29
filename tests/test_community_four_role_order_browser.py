"""Original-Center same-order browser integration across consumer, merchant, community and platform.

Synthetic identities and loopback HTTP only. No LocalStage shortcut, provider payment,
Finance settlement, production account, server deployment, or new business rule.
"""
import os
import queue
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright, expect
import test_community_reports as fixtures
from scripts.community_mini_http import serve


class OriginalCenterSameOrderBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()

    def test_same_order_visible_in_authorized_existing_views_and_attribution_frozen(self):
        ready=queue.Queue()
        def host():
            fx=None;server=None
            try:
                fx=fixtures.CommunityReportJourney();fx.setUp()
                fx.fx.gateway.commerce=fx.commerce
                server=serve(fx.fx.gateway,operations=fx.ops,communities=fx.communities,commerce=fx.commerce)
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
        reference='four_role_order'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(
                    headless=True,
                    executable_path=(os.environ.get('COMMUNITY_CHROMIUM_EXECUTABLE')
                                     or shutil.which('google-chrome')
                                     or shutil.which('google-chrome-stable')
                                     or shutil.which('chromium')))
                try:
                    base='http://127.0.0.1:'+str(server.server_port)
                    web_context=browser.new_context(extra_http_headers={'X-Center-Session':fx.web['token']})
                    bootstrap=web_context.new_page();bootstrap.goto(base+'/community/portal')

                    price=bootstrap.evaluate("""async arg=>{
                      const r=await fetch('/community/commerce',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':arg.csrf},
                        body:JSON.stringify({workspace:'merchant',operation:'price_set',params:{
                          item_id:'sample_item',expected_revision:0,unit_minor:101,stock:3,enabled:true}})});
                      return {status:r.status,body:await r.json()};
                    }""",{'csrf':fx.web['csrf']})
                    self.assertEqual(price['status'],200,price)

                    consumer=browser.new_page();consumer.goto(base+'/community/portal')
                    def mini(operation,params):
                        return consumer.evaluate("""async arg=>{
                          const r=await fetch('/mini/api',{method:'POST',credentials:'omit',cache:'no-store',redirect:'error',
                            headers:{'Content-Type':'application/json','X-Community-Session':arg.token,'X-Community-Scene':'shop1'},
                            body:JSON.stringify({scene:'shop1',operation:'commerce.'+arg.operation,params:arg.params})});
                          return {status:r.status,body:await r.json()};
                        }""",{'token':fx.token,'operation':operation,'params':params})
                    joined=mini('community_join',{'community_id':fx.cid})
                    self.assertEqual(joined['status'],200,joined)
                    purchased=mini('purchase',{'reference':reference,'lines':[{'item_id':'sample_item','quantity':1,'revision':1}]})
                    self.assertEqual(purchased['status'],200,purchased)
                    order=purchased['body']['result']
                    self.assertEqual(order['reference'],reference)
                    self.assertEqual(order['amount_minor'],101)

                    left=mini('community_leave',{'community_id':fx.cid})
                    self.assertEqual(left['status'],200,left)
                    mine=mini('community_mine',{})
                    self.assertEqual(mine['status'],200,mine)
                    self.assertFalse(mine['body']['result']['active'])

                    merchant=web_context.new_page();merchant.goto(base+'/merchant/workbench')
                    merchant.evaluate("csrf=>window.configureCommunityWorkbench({csrf,workspace:'merchant'})",fx.web['csrf'])
                    merchant.locator('#loadOrders').click();expect(merchant.locator('#notice')).to_have_text('操作完成')
                    expect(merchant.locator('#orders')).to_contain_text(reference)
                    expect(merchant.locator('#orders')).to_contain_text('101')
                    expect(merchant.locator('#orders')).to_contain_text('PENDING')

                    community=web_context.new_page();community.goto(base+'/community/portal')
                    community.evaluate("csrf=>window.configureCommunityPortal({csrf,workspace:'community'})",fx.web['csrf'])
                    community.locator('#reference').fill(fx.cid)
                    community.locator('#read').click();expect(community.locator('#message')).to_have_text('操作完成')
                    community.locator('#communityOrders').click();expect(community.locator('#message')).to_have_text('记录查询完成')
                    expect(community.locator('#records')).to_contain_text(reference)
                    expect(community.locator('#records')).to_contain_text('101分')

                    platform=web_context.new_page();platform.goto(base+'/community/portal')
                    platform.evaluate("csrf=>window.configureCommunityPortal({csrf,workspace:'platform'})",fx.web['csrf'])
                    platform.locator('#platformView').select_option('platform_orders')
                    platform.locator('#platformOrderStatus').select_option('ALL')
                    platform.locator('#readPlatformView').click();expect(platform.locator('#message')).to_have_text('操作完成')
                    expect(platform.locator('#platformViewResult')).to_contain_text(reference)
                    expect(platform.locator('#platformViewResult')).to_contain_text('"amount_minor": 101')
                    expect(platform.locator('#platformViewResult')).to_contain_text('"finance_status": "UNCONFIRMED"')

                    other_context=browser.new_context(extra_http_headers={'X-Center-Session':fx.reviewer['token']})
                    other=other_context.new_page();other.goto(base+'/community/portal')
                    denied_community=other.evaluate("""async arg=>{
                      const r=await fetch('/community/directory',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':arg.csrf},
                        body:JSON.stringify({workspace:'other',operation:'community_orders',params:{community_id:arg.community,after_id:''}})});
                      return {status:r.status,body:await r.json()};
                    }""",{'csrf':fx.reviewer['csrf'],'community':fx.cid})
                    self.assertEqual(denied_community['status'],403)
                    self.assertEqual(denied_community['body']['error'],'ACCESS_DENIED')

                    denied_platform=bootstrap.evaluate("""async arg=>{
                      const r=await fetch('/community/directory',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':arg.csrf},
                        body:JSON.stringify({workspace:'community',operation:'platform_orders',params:{after_id:0,status:'ALL'}})});
                      return {status:r.status,body:await r.json()};
                    }""",{'csrf':fx.web['csrf']})
                    self.assertEqual(denied_platform['status'],403)
                    self.assertEqual(denied_platform['body']['error'],'ACCESS_DENIED')
                finally:
                    browser.close()
        finally:
            server.shutdown();thread.join(5)
            self.assertFalse(thread.is_alive(),'FOUR_ROLE_BROWSER_SERVER_DID_NOT_STOP')


if __name__=='__main__':unittest.main()
