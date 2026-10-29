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
from playwright.sync_api import sync_playwright,expect
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
                            expect(panel.locator('[role=status]')).to_contain_text('已登录')
                        base=fx.plan['https_origin']+'/community-preview'
                        page.goto(base+'/merchant/workbench');login('one@example.org')
                        self.assertEqual(page.locator('#community-session select').input_value(),'merchant')
                        with page.expect_response(lambda r:r.url.endswith('/community/operations') and r.status==200):page.locator('#loadOrders').click()
                        page.goto(base+'/community/portal')
                        expect(page.locator('#community-session select')).to_have_value('community')
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='社区资料',exact=True).click()
                        expect(page.locator('#mine')).to_be_visible()
                        with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==200):page.locator('#mine').click()
                        # Frontend workspace selection is not an authorization grant.
                        result=page.evaluate("""async()=>{const r=await fetch('/community-preview/community/operations',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':'wrong'},body:JSON.stringify({workspace:'merchant',operation:'community.summary',params:{}})});return r.status;}""")
                        self.assertEqual(result,403)
                        page.locator('[data-logout]').click();expect(page.locator('#community-session [role=status]')).to_have_text('已退出登录。')
                        page.goto(base+'/merchant/review')
                        with page.expect_response(lambda r:r.url.endswith('/merchant/onboarding') and r.request.post_data_json.get('operation')=='review_list' and r.status==200):
                            login('two@example.org')
                        expect(page.locator('#community-session [role=status]')).to_have_text('已登录原平台审核账户。')
                        # A valid reviewer session/CSRF does not inherit the
                        # other account's original merchant workspace.
                        denied=page.evaluate("""async()=>{const r=await fetch('/community-preview/community/operations',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':sessionStorage.getItem('community-original-csrf')},body:JSON.stringify({workspace:'merchant',operation:'community.summary',params:{}})});return r.status;}""")
                        self.assertEqual(denied,403)
                        for origin in ('https://evil.invalid',None):
                            conn=http.client.HTTPConnection('unused',timeout=5)
                            conn.sock=socket.socket(socket.AF_UNIX);conn.sock.settimeout(5);conn.sock.connect(fx.plan['socket_path'])
                            headers={'Host':'uk.wenwenwenyiyiyi.work','X-Xuanjun-Client-IP':'127.0.0.1','Content-Type':'application/json'}
                            if origin:headers['Origin']=origin
                            try:
                                conn.request('POST','/community/session/login',json.dumps({'email':'one@example.org','password':'FixturePassword123!'}),headers)
                                response=conn.getresponse();response.read();self.assertEqual(response.status,403)
                            finally:conn.close()
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


class SessionMutationRaces(unittest.TestCase):
    @unittest.skipIf(os.geteuid()==0,'Original non-root cookie/HTTP race chain executes on Hosted')
    def test_cookie_csrf_coherence_with_delayed_real_center_responses(self):
        fx=fixture.FormalHost();fx.setUp();self.addCleanup(fx.tearDown)
        with fx.open() as host:
            server=host.application.listen_proxy(fx.plan['socket_path'],fx.plan['https_origin'],fx.plan['nginx_uid'],fx.plan['nginx_gid'])
            server.timeout=.1
            def flow():
                hold_next={};held={};seen=[]
                def forward(route):
                    request=route.request;path=request.url.removeprefix(fx.plan['https_origin']+'/community-preview')
                    conn=http.client.HTTPConnection('unused',timeout=5)
                    conn.sock=socket.socket(socket.AF_UNIX);conn.sock.settimeout(5);conn.sock.connect(fx.plan['socket_path'])
                    headers={k:v for k,v in request.all_headers().items() if k.lower() not in ('host','content-length')}
                    headers.update({'Host':'uk.wenwenwenyiyiyi.work','X-Xuanjun-Client-IP':'127.0.0.1'})
                    try:
                        conn.request(request.method,path,body=request.post_data,headers=headers)
                        response=conn.getresponse();body=response.read();status=response.status;fields=dict(response.getheaders())
                    finally:conn.close()
                    seen.append((path,status))
                    action=path.rsplit('/',1)[-1]
                    def release():route.fulfill(status=status,headers=fields,body=body)
                    if hold_next.pop(action,False):held[action]=release
                    else:release()
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True)
                    try:
                        context=browser.new_context();page=context.new_page();errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        context.route(fx.plan['https_origin']+'/**',forward)
                        base=fx.plan['https_origin']+'/community-preview'
                        panel=page.locator('#community-session')
                        def submit(address):
                            panel.locator('[name=email]').fill(address);panel.locator('[name=password]').fill('FixturePassword123!')
                            panel.locator('form').dispatch_event('submit')
                        def logged():expect(panel.locator('[role=status]')).to_contain_text('已登录')
                        def wait_held(action):
                            deadline=time.monotonic()+5
                            while action not in held and time.monotonic()<deadline:page.wait_for_timeout(20)
                            self.assertIn(action,held)
                        def live():
                            status=page.evaluate("""async()=>{const r=await fetch('/community-preview/community/session/check',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':sessionStorage.getItem('community-original-csrf')},body:'{}'});return r.status;}""")
                            self.assertEqual(status,200)
                            cookie=next(c for c in context.cookies(base) if c['name']=='__Host-xj_customer')
                            self.assertTrue(cookie['httpOnly']);self.assertTrue(cookie['secure'])
                            self.assertEqual(cookie['sameSite'],'Strict')
                            self.assertNotIn('__Host-xj_customer',page.evaluate('document.cookie'))
                            return cookie['value'],page.evaluate("sessionStorage.getItem('community-original-csrf')")
                        page.goto(base+'/merchant/workbench')
                        hold_next['login']=True;submit('one@example.org');wait_held('login')
                        expect(panel.locator('button[type=submit]')).to_be_disabled()
                        submit('two@example.org');page.wait_for_timeout(80)
                        self.assertEqual(sum(path.endswith('/session/login') for path,_ in seen),1)
                        held.pop('login')();logged();first_cookie,_=live()
                        hold_next['logout']=True;panel.locator('[data-logout]').click();wait_held('logout')
                        submit('two@example.org');page.wait_for_timeout(80)
                        self.assertEqual(sum(path.endswith('/session/login') for path,_ in seen),1)
                        held.pop('logout')();expect(panel.locator('[role=status]')).to_have_text('已退出登录。')
                        self.assertFalse(any(c['name']=='__Host-xj_customer' for c in context.cookies(base)))
                        submit('two@example.org');logged();second_cookie,_=live();self.assertNotEqual(first_cookie,second_cookie)
                        for old_status in (200,403):
                            if old_status==403:page.evaluate("sessionStorage.setItem('community-original-csrf','old-invalid-csrf')")
                            hold_next['check']=True;page.reload();wait_held('check')
                            self.assertEqual(seen[-1],('/community/session/check',old_status))
                            submit('one@example.org');logged();pair=live()
                            held.pop('check')();page.wait_for_timeout(80)
                            self.assertEqual(live(),pair)
                            expect(panel.locator('select')).to_have_value('merchant')
                        self.assertEqual(errors,[])
                    finally:browser.close()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(flow);deadline=time.monotonic()+60
                while not future.done() and time.monotonic()<deadline:server.handle_request()
                future.result(timeout=2)

if __name__=='__main__':unittest.main()
