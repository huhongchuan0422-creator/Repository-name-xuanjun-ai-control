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
from pathlib import Path
from contextlib import contextmanager
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
            # Synthetic private record belonging to the other existing fixture account.
            foreign_id='co_'+'f'*32
            host.application.communities.write(fx.plan['community_grants']['community'],
                dict(id=foreign_id,tenant='tenant1',owner=fx.fx.uid2,name='他人测试社区',
                     description='隔离测试资料',contact='不得显示的测试联系人',state='DRAFT',
                     version=1,opinion='',updated_at=host.center.now()))
            # Page21 synthetic approved record and promotion, confined to this
            # disposable host. Subsequent list/state requests use real HTTP/roles.
            promotion_community='co_'+'a'*32
            promotion_code='cp_'+'b'*32
            host.application.communities.write(fx.plan['community_grants']['community'],
                dict(id=promotion_community,tenant='tenant1',owner=fx.fx.uid1,name='推广隔离测试社区',
                     description='仅页面21测试',contact='合成联系人',state='APPROVED',
                     version=1,opinion='',updated_at=host.center.now()))
            from scripts.community_consumer_communities import PROMOTIONS
            from scripts.pr122_customer_core import canonical
            promotion_record=dict(id=promotion_code,community_id=promotion_community,tenant='tenant1',
                scene='shop1',title='原场景推广测试',expires_at=host.center.now()+86400,
                status='ACTIVE',version=1,created_at=host.center.now())
            host.center.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',
                (PROMOTIONS,promotion_code,fx.fx.uid1,'project1',
                 host.center.encrypt(canonical(promotion_record),'community-promotion:'+promotion_code)))
            # Page22 uses the same admitted fixture merchant, not a mocked API.
            from scripts.community_center_communities import MEMBERS
            relation_key=host.application.communities.key('tenant1','MERCHANT:'+fx.fx.uid1)
            relation=dict(community_id=promotion_community,tenant='tenant1',user_id=fx.fx.uid1,kind='MERCHANT',updated_at=host.center.now())
            host.center.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',
                (MEMBERS,relation_key,fx.fx.uid1,'project1',host.center.encrypt(canonical(relation),'community-relation:'+relation_key)))
            merchant_db=host.persistence.runtime.demo.merchant_db
            merchant_db.execute("INSERT OR REPLACE INTO merchant_profiles VALUES(?,?,?,?,?,?,?,1)",
                ('tenant1','merchant1','store1','原商家表合成门店','仅 Hosted 测试','不得输出的商家联系方式','ACTIVE'))
            merchant_db.commit()
            server.timeout=.1;received=[]
            def browser_flow():
                def forward(route):
                    request=route.request;path=request.url.removeprefix(fx.plan['https_origin']+'/community-preview')
                    conn=http.client.HTTPConnection('unused',timeout=5)
                    conn.sock=socket.socket(socket.AF_UNIX);conn.sock.settimeout(5);conn.sock.connect(fx.plan['socket_path'])
                    headers={k:v for k,v in request.all_headers().items() if k.lower() not in ('host','content-length')};headers['Host']='uk.wenwenwenyiyiyi.work';headers['X-Xuanjun-Client-IP']='127.0.0.1'
                    headers.pop('content-length',None)
                    try:
                        conn.request(request.method,path,body=request.post_data_buffer,headers=headers)
                        response=conn.getresponse();body=response.read();received.append((path,response.status))
                        route.fulfill(status=response.status,headers=dict(response.getheaders()),body=body)
                    finally:conn.close()
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True)
                    try:
                        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
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
                        evidence=Path('community-admin-browser-evidence');evidence.mkdir(exist_ok=True)
                        shots=[]
                        def shot(name):
                            page.evaluate('window.scrollTo(0,0)')
                            page.screenshot(path=str(evidence/(name+'.png')),full_page=True)
                            shots.append(name+'.png')
                        @contextmanager
                        def directory(op,status=200):
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.request.post_data_json.get('operation')==op) as event:
                                yield
                            response=event.value
                            self.assertEqual(response.status,status,{'operation':op,'status':response.status,'body':response.json()})
                        page.get_by_role('button',name='登记新社区',exact=True).click()
                        page.locator('#name').fill('逐页验收测试社区')
                        page.locator('#description').fill('仅 Hosted 隔离合成数据，不代表生产记录。')
                        page.locator('#contact').fill('测试联系人 · 00000000000')
                        shot('18-register-before-submit-1440')
                        with directory('register'):page.locator('#profile button').click()
                        expect(page.locator('.community-profile-panel .community-profile-detail')).to_be_visible()
                        with directory('mine'):page.locator('#mine').click()
                        card=page.locator('.community-profile-panel .community-record-card').filter(has_text='逐页验收测试社区')
                        expect(card).to_have_count(1)
                        expect(card.locator('dt')).to_have_text(['社区名称','社区介绍','联系人及联系方式','状态'])
                        expect(card.locator('dd')).to_have_text(['逐页验收测试社区','仅 Hosted 隔离合成数据，不代表生产记录。','测试联系人 · 00000000000','草稿'])
                        shot('18-list-1440')
                        with directory('status'):card.get_by_role('button',name='查看详情',exact=True).click()
                        expect(page.locator('.community-profile-panel .community-profile-detail')).to_be_visible()
                        expect(page.locator('#profile')).to_be_hidden()
                        shot('18-detail-1440')
                        page.get_by_role('button',name='返回记录列表',exact=True).click()
                        expect(card).to_be_visible();shot('18-return-1440')
                        with directory('status'):card.get_by_role('button',name='查看详情',exact=True).click()
                        page.get_by_role('button',name='编辑资料',exact=True).click()
                        expect(page.locator('#profile')).to_be_visible();shot('18-edit-1440')
                        page.locator('#description').fill('已编辑的 Hosted 隔离测试介绍')
                        with directory('update'):page.locator('#profile button').click()
                        with directory('status'):page.get_by_role('button',name='回读当前记录',exact=True).click()
                        expect(page.locator('.community-profile-panel .community-profile-detail dl')).to_contain_text('已编辑的 Hosted 隔离测试介绍')
                        shot('18-readback-1440')
                        own_community_id=page.locator('#reference').input_value()
                        with directory('mine'):page.locator('#mine').click()
                        expect(card).to_contain_text('测试联系人 · 00000000000')
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='打开社区',exact=True).click()
                        page.locator('#reference').fill(foreign_id)
                        with directory('status',403):page.locator('#read').click()
                        expect(page.locator('#records')).to_be_empty()
                        expect(page.locator('#contact')).to_have_value('')
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='社区资料',exact=True).click()
                        expect(page.locator('.community-profile-panel .community-profile-detail')).to_be_hidden()
                        expect(page.locator('main')).not_to_contain_text('测试联系人 · 00000000000')
                        expect(page.locator('main')).not_to_contain_text('不得显示的测试联系人')
                        shot('18-denied-cleared-1440')
                        # Page19: original status HTTP, not a simulated membership lookup.
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='打开社区',exact=True).click()
                        page.locator('#reference').fill(own_community_id)
                        with directory('status'):page.locator('#read').click()
                        open_card=page.locator('.community-open-panel .community-record-card')
                        expect(open_card).to_be_visible()
                        expect(open_card.locator('dt')).to_have_text(['社区编号','关系类型','列表说明'])
                        expect(open_card.locator('dd')).to_have_text([own_community_id,'当前关系未确认','点击下方按钮查看完整社区资料。'])
                        expect(page.locator('#members')).to_be_hidden()
                        self.assertLess(page.locator('.community-open-panel .open-query').bounding_box()['y'],open_card.bounding_box()['y'])
                        self.assertLess(open_card.bounding_box()['y'],page.locator('.community-open-panel .open-actions').bounding_box()['y'])
                        shot('19-list-1440')
                        page.get_by_role('button',name='查看社区详情',exact=True).click()
                        expect(page.locator('.community-open-panel .community-profile-detail')).to_be_visible()
                        expect(page.locator('.community-open-panel .community-profile-detail')).to_contain_text('已编辑的 Hosted 隔离测试介绍')
                        shot('19-detail-1440')
                        page.get_by_role('button',name='返回社区记录',exact=True).click()
                        expect(open_card).to_be_visible();shot('19-return-1440')
                        page.locator('.community-open-panel .open-actions > summary').click()
                        with directory('members'):page.locator('#members').click()
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='社区资料',exact=True).click()
                        with directory('mine'):page.locator('#mine').click()
                        expect(card).to_be_visible()
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='打开社区',exact=True).click()
                        expect(page.locator('#records')).to_be_empty()
                        expect(page.locator('.community-open-panel')).not_to_contain_text('测试联系人 · 00000000000')
                        page.locator('#reference').fill(foreign_id)
                        with directory('status',403):page.locator('#read').click()
                        expect(open_card).to_be_hidden()
                        expect(page.locator('.community-open-panel .community-profile-detail')).to_be_hidden()
                        expect(page.locator('.community-open-panel')).not_to_contain_text('测试联系人 · 00000000000')
                        expect(page.locator('.community-open-panel')).not_to_contain_text('不得显示的测试联系人')
                        shot('19-denied-cleared-1440')
                        # Page20 uses real original reports over the same HTTP fixture.
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='社区订单、收益与结算观察',exact=True).click()
                        report_panel=page.locator('.community-report-panel')
                        page.locator('#reportReference').fill(own_community_id)
                        expect(page.locator('#bindReceiver')).to_be_hidden()
                        shot('20-before-query-1440')
                        with directory('community_earnings'):page.locator('#communityEarnings').click()
                        report_card=report_panel.locator(':scope > .community-record-card')
                        expect(report_card.locator('dt')).to_have_text(['社区收益观察','分账快照','退款观察','查询状态'])
                        expect(report_card).to_contain_text('仅当前页 · 财务核销未确认')
                        expect(report_panel).to_contain_text('已读取当前页 0 条记录')
                        shot('20-list-empty-1440')
                        report_panel.get_by_role('button',name='查看分账快照',exact=True).click()
                        expect(report_panel.locator('.community-report-detail')).to_be_visible()
                        expect(report_panel.locator('.community-report-detail')).to_contain_text('当前页没有记录')
                        shot('20-detail-empty-1440')
                        report_panel.get_by_role('button',name='返回观察记录',exact=True).click()
                        expect(report_card).to_be_visible();shot('20-return-1440')
                        with directory('community_orders'):page.locator('#communityOrders').click()
                        expect(report_panel).to_contain_text('当前社区归属订单；未读取分账快照')
                        page.locator('#reportReference').fill(foreign_id)
                        with directory('community_earnings',403):page.locator('#communityEarnings').click()
                        expect(report_panel.locator('.report-rows')).to_be_empty()
                        expect(page.locator('#records')).to_be_empty()
                        expect(page.locator('#more')).to_be_hidden()
                        expect(report_panel).to_contain_text('读取失败或无权查看，旧记录已清除')
                        expect(report_card).not_to_contain_text('¥0.00')
                        shot('20-denied-cleared-1440')
                        # Page21 original response fields, detail/return and update.
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='社区推广',exact=True).click()
                        promotion_panel=page.locator('.community-promotion-panel')
                        page.locator('#promotionReference').fill(promotion_community)
                        expect(page.locator('#createPromotion')).to_be_hidden()
                        with directory('promotions'):page.locator('#listPromotions').click()
                        promotion_card=promotion_panel.locator('.community-record-card')
                        expect(promotion_card).to_have_count(1)
                        expect(promotion_card.locator('dt')).to_have_text(['原小程序门店场景','推广标题','到期时间','列表说明'])
                        expect(promotion_card).to_contain_text('shop1');expect(promotion_card).to_contain_text('原场景推广测试')
                        shot('21-list-1440')
                        promotion_panel.get_by_role('button',name='查看推广详情',exact=True).click()
                        expect(promotion_panel.locator('.community-promotion-detail')).to_contain_text(promotion_code)
                        shot('21-detail-1440')
                        promotion_panel.get_by_role('button',name='返回推广记录',exact=True).click()
                        expect(promotion_card).to_be_visible();shot('21-return-1440')
                        promotion_panel.locator('.open-actions > summary').click()
                        page.locator('#promotionState').select_option('PAUSED')
                        with directory('promotion_state'):page.locator('#savePromotionState').click()
                        expect(promotion_panel.locator('.community-promotion-detail')).to_contain_text('已暂停')
                        with directory('promotions'):page.locator('#listPromotions').click()
                        promotion_panel.get_by_role('button',name='查看推广详情',exact=True).click()
                        expect(page.locator('#promotionVersion')).to_have_value('2')
                        expect(promotion_panel.locator('.community-promotion-detail')).to_contain_text('已暂停')
                        shot('21-state-readback-1440')
                        page.locator('#promotionReference').fill(foreign_id)
                        with directory('promotions',403):page.locator('#listPromotions').click()
                        expect(promotion_panel.locator('.promotion-records')).to_be_empty()
                        expect(promotion_panel.locator('.community-promotion-detail')).to_be_hidden()
                        expect(page.locator('#promotionCode')).to_have_value('')
                        expect(page.locator('#more')).to_be_hidden()
                        expect(promotion_panel).not_to_contain_text('原场景推广测试')
                        shot('21-denied-cleared-1440')
                        # Pages22/49 query the actual original members permission path.
                        page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='社区商家成员',exact=True).click()
                        page.locator('#memberCommunityReference').fill(promotion_community)
                        with directory('members'):page.locator('#queryMerchantMembers').click()
                        member_panel=page.locator('.community-members-panel')
                        member_card=member_panel.locator('.community-record-card')
                        expect(member_card).to_have_count(1)
                        expect(member_card.locator('dt')).to_have_text(['成员名称','成员类型','所属范围','列表说明'])
                        expect(member_card).to_contain_text('原商家表合成门店')
                        expect(member_panel).not_to_contain_text('不得输出的商家联系方式')
                        shot('22-list-1440')
                        member_panel.get_by_role('button',name='查看商家成员详情',exact=True).click()
                        member_detail=member_panel.locator('.community-member-detail')
                        expect(member_detail).to_be_visible();expect(member_detail).to_contain_text('原商家表合成门店')
                        expect(member_detail).to_contain_text('未核验，不能从成员关系推断')
                        shot('49-detail-1440')
                        member_panel.get_by_role('button',name='返回成员列表',exact=True).click()
                        expect(member_card).to_be_visible();shot('22-return-1440')
                        member_panel.get_by_role('button',name='查看商家成员详情',exact=True).click()
                        with directory('members'):member_panel.get_by_role('button',name='重新查询当前社区',exact=True).click()
                        expect(member_card).to_contain_text('原商家表合成门店');shot('22-readback-1440')
                        page.locator('#memberCommunityReference').fill(foreign_id)
                        with directory('members',403):page.locator('#queryMerchantMembers').click()
                        expect(member_panel.locator('.member-records')).to_be_empty()
                        expect(member_detail).to_be_hidden();expect(page.locator('#more')).to_be_hidden()
                        expect(member_panel).not_to_contain_text('原商家表合成门店')
                        shot('22-denied-cleared-1440')
                        # Frontend workspace selection is not an authorization grant.
                        result=page.evaluate("""async()=>{const r=await fetch('/community-preview/community/operations',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':'wrong'},body:JSON.stringify({workspace:'merchant',operation:'community.summary',params:{}})});return r.status;}""")
                        self.assertEqual(result,403)
                        page.locator('.admin-account summary').click()
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
                        (evidence/'receipt.json').write_text(json.dumps(dict(source=os.environ.get('GITHUB_SHA','LOCAL'),
                            scope='REAL_BROWSER_ORIGINAL_UNIX_HTTP_SYNTHETIC_FIXTURE_ONLY',page='18',pages=['18','19','20','21','22','49'],screenshots=shots,
                            production=False,customer_accepted=False),ensure_ascii=False,indent=2)+'\n')
                    except Exception:
                        evidence=Path('community-admin-browser-evidence');evidence.mkdir(exist_ok=True)
                        diagnostic=dict(received=received,errors=errors,production=False,passed=False)
                        (evidence/'failure.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2)+'\n')
                        try:page.screenshot(path=str(evidence/'18-failure-1440.png'),full_page=True,timeout=5000)
                        except Exception:pass
                        try:diagnostic['message']=page.locator('#message').inner_text(timeout=1000)
                        except Exception:pass
                        try:diagnostic['input_validity']=page.locator('#profile').evaluate('(form)=>Array.from(form.elements).map(e=>({id:e.id,valid:e.checkValidity(),message:e.validationMessage}))')
                        except Exception:pass
                        (evidence/'failure.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2)+'\n')
                        raise
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
