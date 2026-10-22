"""Real same-context Chromium tabs and document lifecycle against original HTTP.

Transport forwards every request to the real serial Unix handler. Only complete
original responses may be held; no identity/business response is invented.
"""
import concurrent.futures
import http.client
import json
import os
import socket
import time
import unittest
from playwright.sync_api import sync_playwright,expect,Error as BrowserError
import test_community_platform_host as fixture

ORIGIN='https://uk.wenwenwenyiyiyi.work'
BASE=ORIGIN+'/community-preview'
KEY='community-original-csrf'

class RealTransport:
    def __init__(self,case,context,sock):
        self.case,self.context,self.sock=case,context,sock
        self.hold_next={};self.held={};self.seen=[]
        context.route(ORIGIN+'/**',self.forward)
    def forward(self,route):
        request=route.request;path=request.url.removeprefix(BASE)
        conn=http.client.HTTPConnection('unused',timeout=5)
        conn.sock=socket.socket(socket.AF_UNIX);conn.sock.settimeout(5);conn.sock.connect(self.sock)
        headers={k:v for k,v in request.all_headers().items() if k.lower() not in ('host','content-length')}
        headers.update({'Host':'uk.wenwenwenyiyiyi.work','X-Xuanjun-Client-IP':'127.0.0.1'})
        try:
            conn.request(request.method,path,body=request.post_data,headers=headers)
            response=conn.getresponse();body=response.read();status=response.status;fields=dict(response.getheaders())
        finally:conn.close()
        self.seen.append((path,status))
        def release():
            try:route.fulfill(status=status,headers=fields,body=body);return 'RELEASED'
            except BrowserError:
                # A destroyed document's original fetch may already be aborted.
                failure=request.failure or ''
                if 'ABORTED' not in failure and 'CANCEL' not in failure.upper():raise
                return 'ORIGINAL_REQUEST_ABORTED'
        action=path.rsplit('/',1)[-1]
        if self.hold_next.pop(action,False):self.held[action]=release
        else:release()
    def wait_held(self,page,action):
        deadline=time.monotonic()+5
        while action not in self.held and time.monotonic()<deadline:page.wait_for_timeout(20)
        self.case.assertIn(action,self.held)
    def count(self,action):return sum(path=='/community/session/'+action for path,_ in self.seen)
    def submit(self,page,address):
        panel=page.locator('#community-session')
        panel.locator('[name=email]').fill(address);panel.locator('[name=password]').fill('FixturePassword123!')
        panel.locator('form').dispatch_event('submit')
    def login(self,page,address):
        expect(page.locator('#community-session button[type=submit]')).to_be_enabled()
        self.submit(page,address)
        expect(page.locator('#community-session [role=status]')).to_contain_text('已登录')
        expect(page.locator('#community-session button[type=submit]')).to_be_enabled()
    def csrf(self,page):return page.evaluate("sessionStorage.getItem('"+KEY+"')")
    def check(self,page,csrf=None):
        return page.evaluate("""async supplied=>{const csrf=supplied===null?sessionStorage.getItem('community-original-csrf'):supplied;const r=await fetch('/community-preview/community/session/check',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf||''},body:'{}'});return {status:r.status,body:await r.json()};}""",csrf)
    def live(self,page,uid=None):
        csrf=self.csrf(page);self.case.assertTrue(csrf)
        result=self.check(page);self.case.assertEqual(result['status'],200)
        if uid:self.case.assertEqual(result['body']['result']['user_id'],uid)
        cookie=next(c for c in self.context.cookies(ORIGIN) if c['name']=='__Host-xj_customer')
        self.case.assertTrue(cookie['httpOnly']);self.case.assertTrue(cookie['secure']);self.case.assertEqual(cookie['sameSite'],'Strict')
        self.case.assertNotIn('__Host-xj_customer',page.evaluate('document.cookie'))
        return cookie['value'],csrf
    def closed(self,page):
        self.case.assertIsNone(self.csrf(page))
        expect(page.locator('#loadOrders')).to_be_disabled()
        expect(page.locator('#summary')).to_be_empty()
        self.case.assertEqual(self.check(page,'')['status'],403)
    def consistent(self,page):
        if self.csrf(page):self.live(page)
        else:self.closed(page)

@unittest.skipIf(os.geteuid()==0,'Actual non-root multi-page/Unix peer executes on Hosted')
class OriginalSessionTabs(unittest.TestCase):
    def original(self,flow):
        fx=fixture.FormalHost();fx.setUp();self.addCleanup(fx.tearDown)
        with fx.open() as host:
            server=host.application.listen_proxy(fx.plan['socket_path'],ORIGIN,fx.plan['nginx_uid'],fx.plan['nginx_gid'])
            server.timeout=.1
            def browser_flow():
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True)
                    try:
                        context=browser.new_context();context.set_default_timeout(5000)
                        transport=RealTransport(self,context,fx.plan['socket_path'])
                        flow(context,transport,fx)
                    finally:browser.close()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(browser_flow);deadline=time.monotonic()+80
                while not future.done() and time.monotonic()<deadline:server.handle_request()
                future.result(timeout=2)
    def test_same_context_tabs_serialize_cookie_mutations_and_clear_old_authority(self):
        def flow(context,t,fx):
            one=context.new_page();two=context.new_page();errors=[]
            for page in (one,two):page.on('pageerror',lambda error:errors.append(str(error)));page.goto(BASE+'/merchant/workbench')
            t.hold_next['login']=True;t.submit(one,'one@example.org');t.wait_held(one,'login')
            t.submit(two,'two@example.org');two.wait_for_timeout(100)
            self.assertEqual(t.count('login'),1,'second tab issued a cookie mutation before original response settled')
            t.held.pop('login')();one.wait_for_timeout(200)
            for page in (one,two):expect(page.locator('#community-session button[type=submit]')).to_be_enabled()
            t.consistent(one);t.consistent(two)
            # Stabilize a real merchant view before another tab changes identity.
            t.login(one,'one@example.org');t.live(one,fx.fx.uid1)
            with one.expect_response(lambda r:r.url.endswith('/community/operations') and r.status==200):one.locator('#loadOrders').click()
            expect(one.locator('#summary')).not_to_be_empty()
            old_pair=t.live(one)
            t.login(two,'two@example.org');new_pair=t.live(two,fx.fx.uid2)
            self.assertNotEqual(new_pair[0],old_pair[0]);one.wait_for_timeout(100);t.closed(one)
            self.assertEqual(t.check(one,old_pair[1])['status'],403)
            # An old logout response cannot clear a newer tab's login cookie.
            t.hold_next['logout']=True;two.locator('[data-logout]').click();t.wait_held(two,'logout')
            before=t.count('login');t.submit(one,'one@example.org');one.wait_for_timeout(100)
            self.assertEqual(t.count('login'),before)
            t.held.pop('logout')();two.wait_for_timeout(200)
            for page in (one,two):expect(page.locator('#community-session button[type=submit]')).to_be_enabled();t.consistent(page)
            t.login(one,'one@example.org');t.live(one,fx.fx.uid1);two.wait_for_timeout(100);t.closed(two)
            one.locator('[data-logout]').click();expect(one.locator('#community-session [role=status]')).to_have_text('已退出登录。')
            two.wait_for_timeout(100)
            self.assertFalse(any(c['name']=='__Host-xj_customer' for c in context.cookies(ORIGIN)))
            for page in (one,two):t.closed(page)
            self.assertEqual(errors,[])
        self.original(flow)
    def lifecycle(self,mode):
        def flow(context,t,fx):
            page=context.new_page();page.goto(BASE+'/merchant/workbench');t.login(page,'one@example.org');t.live(page,fx.fx.uid1)
            t.hold_next['login']=True;t.submit(page,'one@example.org');t.wait_held(page,'login');before=t.count('login')
            if mode=='refresh':page.reload()
            else:
                page.goto(BASE+'/community/entrypoints');page.go_back()
            expect(page.locator('#community-session button[type=submit]')).to_be_enabled()
            self.assertEqual(t.count('login'),before,'document restoration automatically replayed UNKNOWN login')
            self.assertIsNone(t.csrf(page));expect(page.locator('#loadOrders')).to_be_disabled()
            t.login(page,'two@example.org');pair=t.live(page,fx.fx.uid2)
            t.held.pop('login')();page.wait_for_timeout(100)
            self.assertEqual(t.live(page,fx.fx.uid2),pair,'old document Set-Cookie overwrote current cookie/CSRF')
            self.assertEqual(t.count('login'),before+1)
        self.original(flow)
    def test_refresh_during_real_login_does_not_replay_or_corrupt_new_session(self):self.lifecycle('refresh')
    def test_leave_and_back_during_real_login_does_not_replay_or_corrupt_new_session(self):self.lifecycle('back')

if __name__=='__main__':unittest.main()
