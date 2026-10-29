"""Synthetic financial observations through original non-root Unix/HTTPS host.

No provider network, payment, refund, split, reconciliation execution, or API
response fabrication. Screenshots prove only isolated browser rendering.
"""
from email.message import Message
from scripts.community_web_session import WebSession,COOKIE
import concurrent.futures
import hashlib
import http.client
import json
import os
import socket
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import test_community_platform_host as fixture
from scripts.pr122_customer_core import canonical
from scripts.community_order_store import create_order

SCOPE=dict(tenant_id='tenant1',merchant_id='merchant1',store_id='store1')

COMMUNITY='co_'+'c'*32
REVIEW_COMMUNITY='co_'+'d'*32

def configure_fixture(fx):
    fx.plan['community_grants']={'platform':dict(user_id=fx.fx.uid1,project='project1',tenant='tenant1',role='PLATFORM_OWNER')}
    fx.plan['community_grants']['platform_readonly']=dict(user_id=fx.fx.uid1,project='project1',tenant='tenant1',role='PLATFORM_REVIEWER')
    fx.plan['principals']['finance']=dict(tenant_id='tenant1',role='PLATFORM_OWNER')
    fx.plan['bindings']['finance']=dict(SCOPE)
    fx.plan['operations']['finance']=dict(user_id=fx.fx.uid1,project='project1',project_roles=['OWNER'],principal='finance')
    policy=dict(version=1,applyment_submission_enabled=False,
        provider_bindings=[dict(scope=SCOPE,policy=dict(sp_appid=fx.wechat['appid'],sub_mchid='1900000001',sub_appid=None,
            refund_notify_url=fx.plan['https_origin']+'/wechat/refund/notify',profit_sharing=True,max_total_bps=1000,
            receivers={'community':dict(type='MERCHANT_ID',account='1900000002',name='Synthetic receiver',label='Synthetic receiver')},enabled_operations=['REFUND','SPLIT','RETURN']))],
        payment_admissions={},notifications=None,merchant_bill_grants={})
    fx.plan['commerce_provider_config']=str(fx.write('finance-commerce.json',policy))
    fx.plan['nginx_uid']=os.geteuid() or 65534
    fx.write('host.json',fx.plan)

def seed_observations(host,uid,independent_owner):
    c=host.center
    create_order(host.persistence.runtime.demo.db,SCOPE,'synthetic_platform_order',101)
    directory=host.application.communities
    directory.write(directory.grants['platform'],dict(id=COMMUNITY,tenant='tenant1',owner=uid,name='合成接收关系社区',description='仅Hosted隔离测试',contact='合成联系人',state='APPROVED',version=1,opinion='',updated_at=c.now()))
    directory.write(directory.grants['platform'],dict(id=REVIEW_COMMUNITY,tenant='tenant1',owner=independent_owner,name='合成独立审核社区',description='仅Hosted隔离审核',contact='合成审核联系人',state='PENDING',version=1,opinion='',updated_at=c.now()))
    web=c.login('one@example.org','FixturePassword123!')
    directory.dispatch(web['token'],web['csrf'],dict(workspace='platform',operation='community_receiver_bind',params=dict(community_id=COMMUNITY,provider_workspace='finance',receiver_id='community',expected_version=0)))
    # Unknown immutable observation envelopes, not fabricated signed success.
    for kind in ('REFUND','SPLIT'):
        ref='synthetic_'+kind.lower();key=hashlib.sha256(('finance-card-'+kind).encode()).hexdigest()
        value=dict(scope=SCOPE,scope_hash=hashlib.sha256(canonical(SCOPE)).hexdigest(),kind=kind,
            reference=ref,request_id='req_'+kind.lower(),provider_reference='synthetic_provider_'+kind.lower())
        c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',('COMMUNITY_PROVIDER_ACTION',key,uid,'project1',c.encrypt(canonical(value),'provider-action:'+key)))
    # No RETURN seed: its empty state is intentional, not a fake zero-valued refund.
    value=dict(reference='synthetic_order',scope=SCOPE,original_amount_minor=101,currency='CNY',
        provider_state='NOT_OBSERVED',local_order_state='PENDING',confirmed_local_refunds_minor=0,
        anomalies=['SYNTHETIC_UNVERIFIED_OBSERVATION'],observed_at=c.now(),status='EXCEPTION',
        coverage='ORDER_OBSERVATIONS_ONLY',daily_bill_reconciled=False,finance_status='UNCONFIRMED',funds_retry_authorized=False)
    key=hashlib.sha256(canonical([SCOPE,value['reference']])).hexdigest()
    c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',('COMMUNITY_ORDER_RECONCILIATION',key,uid,'project1',c.encrypt(canonical(value),'community-order-reconciliation:'+key)))

def seed_unknown_return_observation(host,uid):
    # Synthetic persisted PRE-RESPONSE return envelope, shaped exactly like the
    # original SplitReturns reservation. No result/body_sha: NOT verified success.
    from scripts.community_provider_reference import provider_order_reference
    actions=host.application.provider_actions;c=host.center
    web=c.login('one@example.org','FixturePassword123!')
    grant,policy=actions._authorize(web['token'],web['csrf'],'finance')
    p=dict(reference='synthetic_return_order',request_id='req_return',receiver_id='community',amount_minor=7,description='Synthetic saved unknown return')
    return_ref='sr'+hashlib.sha256(canonical([actions.reader._mchid,grant['scope'],p['reference'],p['request_id']])).hexdigest()[:30]
    key=hashlib.sha256(canonical([actions.reader._mchid,'RETURN',return_ref])).hexdigest()
    value=dict(reference=p['reference'],request_id=p['request_id'],receiver_id=p['receiver_id'],scope=grant['scope'],project=grant['project'],user_id=grant['user_id'],policy_hash=actions._policy_hash(policy),payload=dict(sub_mchid=policy['sub_mchid'],out_order_no='synthetic_prior_split',out_return_no=return_ref,return_mchid=policy['receivers']['community']['account'],amount=p['amount_minor'],description=p['description']),request_hash=hashlib.sha256(canonical(p)).hexdigest())
    assert grant['user_id']==uid and grant['scope']==SCOPE
    with c.tx():c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_RETURN',?,?,?,?,1)",(key,uid,grant['project'],c.encrypt(canonical(value),'community-provider-return:'+key)))
    # No original split/budget/return execution is claimed by a saved fixture.
    return value

class FinanceFixtureContract(unittest.TestCase):
    def test_original_dispatch_without_socket_or_provider(self):
        fx=fixture.FormalHost();fx.setUp();self.addCleanup(fx.doCleanups);configure_fixture(fx)
        with patch('urllib.request.urlopen',side_effect=AssertionError('NO_PROVIDER_NETWORK')):
            with fx.open() as host:
                seed_observations(host,fx.fx.uid1,fx.fx.uid2);web=host.center.login('one@example.org','FixturePassword123!')
                # The real Host fixture already grants the exact same scope; no new grant here.
                session=WebSession(host.center,host.application.operations,host.application.communities,host.application.onboarding,provider_actions=host.application.provider_actions,merchant_bills=host.application.merchant_bills)
                headers=Message();headers['Cookie']=COOKIE+'='+web['token'];headers['X-CSRF-Token']=web['csrf']
                checked,_=session.dispatch('/community/session/check',headers,{},'127.0.0.1')
                selected=next(w for w in checked['workspaces'] if w['kind']=='MERCHANT' and w['workspace']=='merchant')
                self.assertEqual(selected['finance_options'],{'provider':[{'workspace':'finance'}],'merchant_bill':[]})
                merchant=host.application.operations.grants['merchant'];finance,_=host.application.provider_actions._authorize(web['token'],web['csrf'],'finance')
                for key in ('user_id','project','tenant','scope'):self.assertEqual(merchant[key],finance[key])
                def call(op,p,workspace='finance'):
                    return host.application.provider_actions.dispatch(web['token'],web['csrf'],dict(workspace=workspace,operation=op,params=p))
                for kind in ('REFUND','SPLIT'):
                    r=call('financial_records',dict(kind=kind,after_id=''));self.assertEqual(len(r['records']),1);self.assertFalse(r['records'][0]['provider_response_verified']);self.assertFalse(r['records'][0]['automatic_retry_allowed'])
                self.assertEqual(call('financial_records',dict(kind='RETURN',after_id=''))['records'],[])
                seed_unknown_return_observation(host,fx.fx.uid1)
                returned=call('financial_records',dict(kind='RETURN',after_id=''))['records'];self.assertEqual(len(returned),1);self.assertEqual(returned[0]['amount_minor'],7);self.assertEqual(returned[0]['receiver_id'],'community');self.assertEqual(returned[0]['status'],'UNKNOWN_QUERY_EXISTING_ONLY');self.assertFalse(returned[0]['provider_response_verified']);self.assertFalse(returned[0]['automatic_retry_allowed']);self.assertNotIn('currency',returned[0])
                self.assertEqual(call('reconciliation_read',dict(reference='synthetic_order'))['finance_status'],'UNCONFIRMED')
                read=host.application.communities.dispatch(web['token'],web['csrf'],dict(workspace='platform',operation='community_receiver_list',params=dict(community_id=COMMUNITY,provider_workspace='finance',after_id='')))
                self.assertEqual(read['records'][0]['version'],1);self.assertFalse(read['funds_operation_executed'])
                orders=host.application.communities.dispatch(web['token'],web['csrf'],dict(workspace='platform',operation='platform_orders',params=dict(after_id=0,status='ALL')))
                self.assertEqual(orders['records'][0]['reference'],'synthetic_platform_order');self.assertEqual(orders['records'][0]['amount_minor'],101);self.assertIsNone(orders['records'][0]['payment_evidence'])
                def review_call(op,params):return host.application.communities.dispatch(web['token'],web['csrf'],dict(workspace='platform',operation=op,params=params))
                before=review_call('status',dict(community_id=REVIEW_COMMUNITY));self.assertEqual(before['state'],'PENDING')
                reviewed=review_call('review',dict(community_id=REVIEW_COMMUNITY,expected_version=before['version'],decision='APPROVED',opinion='合成独立审核'))
                self.assertEqual(reviewed['version'],2);self.assertEqual(review_call('status',dict(community_id=REVIEW_COMMUNITY))['state'],'APPROVED')
                with self.assertRaises(PermissionError):review_call('review',dict(community_id=COMMUNITY,expected_version=1,decision='PAUSED',opinion='self review must fail'))
                for operation,params in [('platform_overview',{}),('platform_customers',dict(after_id='')),('platform_audit',dict(after_id=0))]:
                    value=review_call(operation,params);self.assertIsInstance(value,dict)
                merchants=review_call('platform_merchants',dict(after_workspace=''));target=next(v for v in merchants['records'] if v['workspace']=='merchant');self.assertEqual(target['lifecycle']['version'],0)
                changed=review_call('platform_merchant_state',dict(merchant_workspace='merchant',status='ACTIVE',expected_version=0,reason='合成原状态版本测试'));self.assertEqual(changed['version'],1)
                with self.assertRaises(PermissionError):host.application.communities.dispatch(web['token'],web['csrf'],dict(workspace='platform_readonly',operation='platform_merchant_state',params=dict(merchant_workspace='merchant',status='PAUSED',expected_version=1,reason='只读审核员不得修改')))
                profile=review_call('profile_read',{});self.assertEqual(profile['version'],0)
                saved=review_call('profile_update',dict(nickname='合成个人昵称',contact='合成联系方式',expected_version=0));self.assertEqual(saved['version'],1)
                self.assertEqual(review_call('profile_read',{})['contact'],'合成联系方式')
                with self.assertRaises(ValueError):review_call('profile_update',dict(nickname='不得覆盖',contact='',expected_version=0))
                code=review_call('referral_code',{})['code'];self.assertEqual(len(code),32)
                with self.assertRaises(PermissionError):review_call('referral_bind',dict(code=code)) # original self-referral denial
                with self.assertRaises(PermissionError):call('financial_records',dict(kind='REFUND',after_id=''),workspace='not_admitted')

class FinanceCardsBrowser(unittest.TestCase):
    @unittest.skipIf(os.geteuid()==0,'Original non-root Unix peer/browser chain runs on Hosted only')
    def test_finance_record_cards_real_http(self):
        from playwright.sync_api import sync_playwright,expect
        fx=fixture.FormalHost();fx.setUp();self.addCleanup(fx.doCleanups);configure_fixture(fx)
        evidence=Path('community-admin-browser-evidence');evidence.mkdir(exist_ok=True)
        with patch('urllib.request.urlopen',side_effect=AssertionError('NO_PROVIDER_NETWORK')):
            with fx.open() as host:
                seed_observations(host,fx.fx.uid1,fx.fx.uid2)
                server=host.application.listen_proxy(fx.plan['socket_path'],fx.plan['https_origin'],fx.plan['nginx_uid'],fx.plan['nginx_gid']);server.timeout=.1
                received=[];shots=[];revoke_finance=threading.Event();revoked_finance=threading.Event();seed_return=threading.Event();return_seeded=threading.Event()
                def flow():
                    def forward(route):
                        req=route.request;path=req.url.removeprefix(fx.plan['https_origin']+'/community-preview')
                        conn=http.client.HTTPConnection('unused',timeout=5);conn.sock=socket.socket(socket.AF_UNIX);conn.sock.settimeout(5);conn.sock.connect(fx.plan['socket_path'])
                        headers={k:v for k,v in req.all_headers().items() if k.lower() not in ('host','content-length')};headers['Host']='uk.wenwenwenyiyiyi.work';headers['X-Xuanjun-Client-IP']='127.0.0.1'
                        try:
                            conn.request(req.method,path,body=req.post_data_buffer,headers=headers);response=conn.getresponse();body=response.read()
                            operation=json.loads(req.post_data).get('operation') if path=='/community/provider-actions' else None
                            received.append(dict(path=path,status=response.status,operation=operation))
                            route.fulfill(status=response.status,headers=dict(response.getheaders()),body=body)
                        finally:conn.close()
                    with sync_playwright() as p:
                        browser=p.chromium.launch(headless=True)
                        try:
                            page=browser.new_page(viewport=dict(width=1440,height=1000));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.route(fx.plan['https_origin']+'/**',forward)
                            page.goto(fx.plan['https_origin']+'/community-preview/merchant/workbench')
                            panel=page.locator('#community-session');panel.locator('[name=email]').fill('one@example.org');panel.locator('[name=password]').fill('FixturePassword123!');panel.get_by_role('button',name='登录',exact=True).click();expect(panel.locator('[role=status]')).to_contain_text('已登录')
                            # Normal session/check supplies options; selection enables only an existing grant.
                            panel.get_by_role('combobox',name='已授权工作区',exact=True).select_option('merchant')
                            financeSelector=panel.get_by_role('combobox',name='已授权门店财务工作区',exact=True)
                            expect(financeSelector).to_have_value('');expect(page.locator('#providerActions')).to_be_hidden()
                            expect(financeSelector.locator('option')).to_have_count(2)
                            expect(financeSelector.locator('option[value="finance"]')).to_have_count(1)
                            expect(panel.get_by_role('combobox',name='已授权整商户账单只读工作区',exact=True)).to_be_hidden()
                            financeSelector.select_option('finance');expect(page.locator('#providerActions')).to_be_visible()
                            def shot(name):
                                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(evidence/(name+'.png')),full_page=True);shots.append(name+'.png')
                            def select_finance(button_id):
                                tools=page.locator('.finance-page-tools')
                                if tools.count() and tools.is_visible() and tools.get_attribute('open') is None:tools.locator(':scope > summary').click()
                                page.locator('#'+button_id).click()
                                expect(page.locator('.finance-page-tools[open]')).to_have_count(0)
                                expect(page.locator('.finance-page-return')).to_be_visible()
                            for kind,prefix in [('REFUND','finance-32'),('SPLIT','finance-33')]:
                                select_finance('financeRefund' if kind=='REFUND' else 'financeSplit');expect(page.locator('#financeBrand')).to_have_text('社区服务 · 平台');expect(page.locator('.finance-account[open]')).to_have_count(0);expect(page.locator('#community-session [name=email]')).to_have_count(1);expect(page.locator('#community-session [data-logout]')).to_have_count(1);page.locator('#financialReadControls summary').click()
                                with page.expect_response(lambda r:r.url.endswith('/community/provider-actions') and r.status==200):page.locator('#financialRecords').click()
                                expect(page.locator('#financialObservationList')).to_contain_text('req_'+kind.lower());page.locator('#financialReadControls summary').click();expect(page.locator('#workbenchOriginalSections')).to_be_hidden();shot(prefix+'-list-1440')
                                page.locator('#financialObservationList').get_by_role('button',name='查看详情',exact=True).click();expect(page.locator('#financialObservationDetail')).to_contain_text('摘要未提供金额');shot(prefix+'-detail-1440')
                                page.locator('#financialObservationBack').click();expect(page.locator('#financialKind')).to_have_value(kind);expect(page.locator('#financialObservationList')).to_be_visible();shot(prefix+'-return-1440')
                            select_finance('financeReturn');page.locator('#financialReadControls summary').click();page.locator('#financialRecords').click();expect(page.locator('#financialObservationList')).to_contain_text('当前范围没有可见记录');page.locator('#financialReadControls summary').click();shot('finance-33-return-empty-1440')
                            seed_return.set()
                            if not return_seeded.wait(5):raise AssertionError('synthetic return fixture seed not acknowledged')
                            page.locator('#financialReadControls summary').click()
                            with page.expect_response(lambda r:r.url.endswith('/community/provider-actions') and r.status==200):page.locator('#financialRecords').click()
                            expect(page.locator('#financialObservationList')).to_contain_text('req_return');page.locator('#financialReadControls summary').click();shot('finance-33-return-nonempty-1440')
                            page.locator('#financialObservationList').get_by_role('button',name='查看详情',exact=True).click()
                            expect(page.locator('#workbenchTitle')).to_have_text('分账回退详情');expect(page.locator('#financialObservationDetail')).to_contain_text('community');expect(page.locator('#financialObservationDetail')).to_contain_text('7 最小货币单位（原记录未返回币种）');expect(page.locator('#financialObservationDetail')).to_contain_text('UNKNOWN_QUERY_EXISTING_ONLY');expect(page.locator('#financialObservationDetail')).to_contain_text('未验证');expect(page.locator('#financialObservationDetail')).to_contain_text('未确认');shot('finance-65-return-detail-1440')
                            page.locator('#financialObservationBack').click();expect(page.locator('#financialObservationList')).to_contain_text('req_return');expect(page.locator('#financialKind')).to_have_value('RETURN');shot('finance-65-return-back-1440')
                            select_finance('financeReconciliation');page.locator('#financialReadControls summary').click();page.locator('#providerOrder').fill('synthetic_order');page.locator('#readReconciliation').click();expect(page.locator('#financialObservationList')).to_contain_text('synthetic_order');page.locator('#financialReadControls summary').click();shot('finance-34-list-1440')
                            page.locator('#financialObservationList').get_by_role('button',name='查看详情',exact=True).click();expect(page.locator('#financialObservationDetail')).to_contain_text('不是全量日账单');shot('finance-34-detail-1440')
                            # Original page27 reads the same real fixture receiver binding; no second system.
                            page.goto(fx.plan['https_origin']+'/community-preview/community/portal')
                            expect(page.locator('#community-session [role=status]')).to_contain_text('已登录')
                            page.evaluate("configureCommunityPortal({csrf:sessionStorage.getItem('community-original-csrf'),workspace:'platform'})")
                            page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='平台配置社区分账接收关系',exact=True).click()
                            panel27=page.locator('#receiverRelations');panel27.locator('#receiverCommunityReference').fill(COMMUNITY);panel27.locator('#receiverWorkspace').fill('finance');panel27.locator('#listReceiverRelations').click()
                            expect(panel27.locator('.community-record-card')).to_contain_text('community')
                            def receiver_shot(name):
                                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(evidence/(name+'.png')),full_page=True);shots.append(name+'.png')
                            receiver_shot('finance-27-list-1440')
                            panel27.get_by_role('button',name='查看接收关系详情',exact=True).click();expect(panel27.locator('.community-receiver-detail')).to_contain_text('finance');receiver_shot('finance-54-detail-1440')
                            panel27.get_by_role('button',name='返回接收关系列表',exact=True).click();expect(panel27.locator('.community-record-card')).to_be_visible();receiver_shot('finance-27-return-1440')
                            panel27.locator('.open-actions:not(.receiver-query-controls) > summary').click();panel27.locator('#receiverId').fill('community');panel27.locator('#readReceiverRelation').click();expect(panel27.locator('#receiverVersion')).to_have_value('1');receiver_shot('finance-55-readback-1440')
                            panel27.locator('.receiver-query-controls > summary').click();panel27.locator('#receiverWorkspace').fill('not_admitted')
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==403):panel27.locator('#listReceiverRelations').click()
                            expect(panel27.locator('.community-receiver-detail')).to_be_hidden();expect(panel27.locator('#receiverVersion')).to_have_value('');receiver_shot('finance-27-denied-1440')
                            # Original26/52/53: independent synthetic reviewer, exact original CAS and status reread.
                            page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='平台审核',exact=True).click()
                            reviewPanel=page.locator('.platform-review-panel');reviewPanel.locator('summary').click();reviewPanel.locator('#directoryStatus').select_option('PENDING');reviewPanel.locator('#listDirectory').click()
                            expect(reviewPanel.locator('.platform-review-rows')).to_contain_text('尚未形成审核决定');reviewPanel.locator('summary').click();expect(page.locator('main h1')).to_have_text('平台审核');receiver_shot('finance-26-list-1440')
                            reviewPanel.get_by_role('button',name='查看审核详情',exact=True).click();expect(reviewPanel.locator('.platform-review-detail')).to_contain_text('合成审核联系人');expect(page.locator('main h1')).to_have_text('平台审核 · 详情');receiver_shot('finance-52-detail-1440')
                            reviewPanel.get_by_role('button',name='打开原审核界面',exact=True).click();reviewPanel.locator('#decision').select_option('APPROVED');reviewPanel.locator('#opinion').fill('合成独立审核');receiver_shot('finance-53-edit-1440')
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==200):reviewPanel.locator('#review').click()
                            expect(reviewPanel.locator('.platform-review-detail')).to_contain_text('已通过');reviewPanel.get_by_role('button',name='回读当前社区版本',exact=True).click();expect(reviewPanel.locator('.platform-review-detail')).to_contain_text('合成独立审核');receiver_shot('finance-53-readback-1440')
                            reviewPanel.get_by_role('button',name='返回审核列表',exact=True).click();expect(reviewPanel.locator('.platform-review-rows')).to_be_visible();expect(reviewPanel.locator('#directoryStatus')).to_have_value('PENDING');receiver_shot('finance-26-return-1440')
                            # Original platform_orders authority, not provider-actions or mocked responses.
                            page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='平台运营查询',exact=True).click()
                            orderPanel=page.locator('.platform-orders-panel');orderPanel.locator('summary').click();orderPanel.locator('#platformView').select_option('platform_orders');orderPanel.locator('#platformOrderStatus').select_option('ALL');orderPanel.locator('#readPlatformView').click()
                            expect(orderPanel.locator('.platform-order-rows')).to_contain_text('synthetic_platform_order');orderPanel.locator('summary').click();expect(page.locator('main h1')).to_have_text('支付证据')
                            receiver_shot('finance-31-list-1440')
                            orderPanel.get_by_role('button',name='查看支付证据详情',exact=True).click();expect(orderPanel.locator('.platform-order-detail')).to_contain_text('不据此断言未支付');expect(page.locator('main h1')).to_have_text('支付证据详情');receiver_shot('finance-62-detail-1440')
                            orderPanel.get_by_role('button',name='返回原列表',exact=True).click();expect(orderPanel.locator('.platform-order-rows')).to_be_visible();expect(page.locator('main h1')).to_have_text('支付证据');receiver_shot('finance-31-return-1440')
                            # Original28/56/57 three non-order schemas, same read scope and current filter.
                            for operation in ['platform_overview','platform_customers','platform_audit']:
                                orderPanel.get_by_role('button',name='打开原运营查询条件',exact=True).click() if operation!='platform_overview' else orderPanel.locator('summary').click()
                                orderPanel.locator('#platformView').select_option(operation);orderPanel.locator('#readPlatformView').click();expect(orderPanel.locator('.platform-operation-rows .community-record-card').first).to_be_visible();orderPanel.locator('summary').click();expect(page.locator('main h1')).to_have_text('平台运营查询');receiver_shot('finance-28-'+operation+'-list-1440')
                                orderPanel.get_by_role('button',name='查看运营记录详情',exact=True).first.click();expect(orderPanel.locator('.platform-operation-detail')).to_be_visible();expect(page.locator('main h1')).to_have_text('平台运营查询 · 详情');receiver_shot('finance-56-'+operation+'-detail-1440');orderPanel.get_by_role('button',name='返回运营查询列表',exact=True).click()
                            orderPanel.get_by_role('button',name='打开原运营查询条件',exact=True).click();expect(page.locator('main h1')).to_have_text('平台运营查询 · 原查询条件');receiver_shot('finance-57-query-1440')
                            # Original29/58/59 merchant lifecycle. Synthetic ACTIVE->ACTIVE version change only, not WeChat signing.
                            page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='平台商家管理',exact=True).click();merchantPanel=page.locator('.platform-merchant-panel');expect(page.locator('.admin-brand')).to_contain_text('社区服务 · 平台');merchantPanel.locator('summary').click();merchantPanel.locator('#platformMerchants').click();expect(merchantPanel.locator('.platform-merchant-rows')).to_contain_text('merchant');merchantPanel.locator('summary').click();expect(merchantPanel.get_by_role('button',name='查看商家详情',exact=True)).to_have_css('background-color','rgb(36, 109, 79)');receiver_shot('finance-29-list-1440')
                            merchantPanel.get_by_role('button',name='查看商家详情',exact=True).click();expect(merchantPanel.locator('.platform-merchant-detail')).to_contain_text('merchant');receiver_shot('finance-58-detail-1440');merchantPanel.get_by_role('button',name='回读所选商家当前版本',exact=True).click();expect(merchantPanel.locator('#platformMerchantVersion')).to_have_value('0')
                            merchantPanel.get_by_role('button',name='打开原商家状态操作',exact=True).click();merchantPanel.locator('#platformMerchantState').select_option('ACTIVE');merchantPanel.locator('#platformMerchantReason').fill('合成原状态版本测试');receiver_shot('finance-59-edit-1440')
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==200):merchantPanel.locator('#saveMerchantState').click()
                            merchantPanel.get_by_role('button',name='回读所选商家当前版本',exact=True).click();expect(merchantPanel.locator('#platformMerchantVersion')).to_have_value('1');expect(merchantPanel.locator('.platform-merchant-detail')).to_contain_text('合成原状态版本测试');receiver_shot('finance-59-readback-1440');merchantPanel.get_by_role('button',name='返回商家列表',exact=True).click();expect(merchantPanel.locator('.platform-merchant-rows')).to_be_visible()
                            # Original17/41/42: current user's existing profile store and version CAS, synthetic only.
                            page.get_by_role('navigation',name='社区功能',exact=True).get_by_role('button',name='个人资料与推荐关系',exact=True).click();customerPanel=page.locator('.customer-profile-panel');expect(page.locator('.admin-brand')).to_contain_text('社区服务 · 社区');customerPanel.locator('#readProfile').click();expect(customerPanel.locator('.customer-profile-rows')).to_contain_text('原资料未填写')
                            customerPanel.get_by_role('button',name='查看个人资料详情',exact=True).click();customerPanel.get_by_role('button',name='编辑个人资料',exact=True).click();customerPanel.locator('#nickname').fill('合成个人昵称');customerPanel.locator('#customerContact').fill('合成联系方式');expect(page.locator('main h1')).to_have_text('个人资料与推荐关系 · 编辑');receiver_shot('finance-42-profile-edit-1440')
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==200):customerPanel.get_by_role('button',name='保存个人资料',exact=True).click()
                            expect(customerPanel.locator('.customer-profile-detail')).to_contain_text('合成联系方式');receiver_shot('finance-41-profile-detail-1440');customerPanel.get_by_role('button',name='返回个人资料列表',exact=True).click();expect(customerPanel.locator('.customer-profile-rows')).to_contain_text('合成个人昵称');receiver_shot('finance-17-profile-list-1440');customerPanel.locator('#readProfile').click();expect(customerPanel.locator('.customer-profile-rows')).to_contain_text('合成联系方式')
                            customerPanel.locator('summary').click();customerPanel.locator('#referralCode').click();expect(customerPanel.locator('.customer-referral-result')).to_contain_text('我的推荐码');expect(customerPanel.locator('.customer-profile-rows')).to_be_empty()
                            page.evaluate("configureCommunityPortal({csrf:sessionStorage.getItem('community-original-csrf'),workspace:'not_admitted'})")
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==403):customerPanel.locator('#readProfile').click()
                            expect(customerPanel.locator('#nickname')).to_have_value('');expect(customerPanel.locator('#customerContact')).to_have_value('');expect(customerPanel.locator('.customer-profile-detail')).to_be_empty();expect(customerPanel.locator('.customer-referral-result')).to_be_empty();receiver_shot('finance-17-profile-denied-1440')
                            # Real finance grant revoked on host owner thread, retaining the same browser identity.
                            page.goto(fx.plan['https_origin']+'/community-preview/merchant/workbench');expect(page.locator('#community-session [role=status]')).to_contain_text('已登录')
                            page.evaluate("configureCommunityWorkbench({csrf:sessionStorage.getItem('community-original-csrf'),workspace:'merchant',providerWorkspace:'finance'})")
                            select_finance('financeRefund');page.locator('#financialReadControls summary').click();page.locator('#financialRecords').click();expect(page.locator('#financialObservationList')).to_contain_text('req_refund')
                            revoke_finance.set()
                            if not revoked_finance.wait(5):raise AssertionError('fixture grant revocation not acknowledged')
                            with page.expect_response(lambda r:r.url.endswith('/community/provider-actions') and r.status==403):page.locator('#financialRecords').click()
                            expect(page.locator('#financialObservation')).to_be_hidden();expect(page.locator('#financialObservationDetail')).to_be_empty();expect(page.locator('#providerActionResult')).to_be_empty();page.locator('#financialReadControls summary').click();page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(evidence/'finance-denied-1440.png'),full_page=True);shots.append('finance-denied-1440.png')
                            self.assertEqual(errors,[])
                            self.assertTrue(all(r['operation'] in ('financial_records','reconciliation_read') for r in received if r['operation']))
                            (evidence/'finance-receipt.json').write_text(json.dumps(dict(scope='SYNTHETIC_ORIGINAL_HOST_HTTP_NOT_CUSTOMER_ACCEPTANCE',return_fixture='SYNTHETIC_PERSISTED_UNKNOWN_NO_PROVIDER_RESULT_NO_FUNDS_EXECUTION',shots=shots,received=received,browser_assertions_passed=True),ensure_ascii=False,indent=2)+'\n')
                        finally:browser.close()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(flow);deadline=time.monotonic()+90
                    while not future.done() and time.monotonic()<deadline:
                        if seed_return.is_set() and not return_seeded.is_set():
                            seed_unknown_return_observation(host,fx.fx.uid1);return_seeded.set()
                        if revoke_finance.is_set() and not revoked_finance.is_set():
                            host.application.provider_actions.operations.grants.pop('finance');revoked_finance.set()
                        server.handle_request()
                    future.result(timeout=2)

if __name__=='__main__':unittest.main()
