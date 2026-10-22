"""Browser -> real Unix HTTP -> original Center/business with synthetic accounts.

Only HTTPS/prefix forwarding is a local transport fixture. No API response is
fabricated, no live credentials, account seeds or host changes are performed.
"""
import concurrent.futures
import http.client
import json
import os
import socket
import time
import unittest
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import test_community_platform_host as fixture
from scripts.pr122_customer_source import TrustedNginxSource

class SessionBrowser(unittest.TestCase):
    @unittest.skipIf(os.geteuid()==0,'Full original non-root host/browser chain executes on Hosted')
    def test_original_login_workspaces_role_reads_csrf_and_logout(self):
        fx=fixture.FormalHost();fx.setUp();self.addCleanup(fx.tearDown)
        fx.plan['community_grants']={'community':dict(user_id=fx.fx.uid1,project='project1',tenant='tenant1',role='COMMUNITY_ADMIN')}
        fx.plan['nginx_uid']=os.geteuid() or 65534
        fx.write('host.json',fx.plan)
        with fx.open() as host:
            host.center.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(fx.fx.uid2,))
            server=host.application.listen_proxy(fx.plan['socket_path'],fx.plan['https_origin'],fx.plan['nginx_uid'],fx.plan['nginx_gid'])
            server.timeout=.1;received=[]
            def browser_flow():
                def forward(route):
                    request=route.request;path=request.url.removeprefix(fx.plan['https_origin']+'/community-preview')
                    conn=http.client.HTTPConnection('unused',timeout=5)
                    conn.sock=socket.socket(socket.AF_UNIX);conn.sock.settimeout(5);conn.sock.connect(fx.plan['socket_path'])
                    headers={k:v for k,v in request.all_headers().items() if k.lower() not in ('host','content-length')};headers['Host']='uk.wenwenwenyiyiyi.work';headers['X-Xuanjun-Client-IP']='127.0.0.1'
                    headers.pop('content-length',None)
                    try:
                        conn.request(request.method,path,body=request.post_data,headers=headers)
                        response=conn.getresponse();body=response.read();received.append((path,response.status))
                        route.fulfill(status=response.status,headers=dict(response.getheaders()),body=body)
                    finally:conn.close()
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True)
                    try:
                        page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.route(fx.plan['https_origin']+'/**',forward)
                        def login(address):
                            panel=page.locator('#community-session');panel.locator('[name=email]').fill(address)
                            panel.locator('[name=password]').fill('FixturePassword123!');panel.get_by_role('button',name='登录',exact=True).click()
                            page.wait_for_function("document.querySelector('#community-session [role=status]').textContent.startsWith('已登录')")
                        base=fx.plan['https_origin']+'/community-preview'
                        page.goto(base+'/merchant/workbench');login('one@example.org')
                        self.assertEqual(page.locator('#community-session select').input_value(),'merchant')
                        with page.expect_response(lambda r:r.url.endswith('/community/operations') and r.status==200):page.locator('#loadOrders').click()
                        page.goto(base+'/community/portal')
                        page.wait_for_function("document.querySelector('#community-session select').value==='community'")
                        with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==200):page.locator('#mine').click()
                        # Frontend workspace selection is not an authorization grant.
                        result=page.evaluate("""async()=>{const r=await fetch('/community-preview/community/operations',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':'wrong'},body:JSON.stringify({workspace:'merchant',operation:'community.summary',params:{}})});return r.status;}""")
                        self.assertEqual(result,403)
                        page.locator('[data-logout]').click();page.wait_for_function("document.querySelector('#community-session [role=status]').textContent==='已退出登录。'")
                        page.goto(base+'/merchant/review');login('two@example.org')
                        page.wait_for_function("document.querySelector('#community-session [role=status]').textContent==='已登录原平台审核账户。'")
                        page.wait_for_timeout(150)
                        self.assertIn(('/merchant/onboarding',200),received)
                        self.assertEqual(errors,[])
                    finally:browser.close()
            # Root cannot be an admitted production peer. Only this synthetic
            # local transport substitutes source verification; Hosted uses the
            # actual non-root SO_PEERCRED path without this substitution.
            ctx=patch.object(TrustedNginxSource,'__call__',return_value='127.0.0.1') if os.geteuid()==0 else __import__('contextlib').nullcontext()
            with ctx,concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(browser_flow);deadline=time.monotonic()+45
                while not future.done() and time.monotonic()<deadline:server.handle_request()
                future.result(timeout=2)

if __name__=='__main__':unittest.main()
