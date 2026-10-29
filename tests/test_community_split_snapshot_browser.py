"""Synthetic signed split observation -> original community report -> browser.
No live provider, payment, credential or customer data. Actual original HTTP and
report integrity validation remain in use; synthetic provider transport is confined
to fixture construction and restored before browser reads.
"""
import base64,concurrent.futures,hashlib,http.client,json,os,socket,time,unittest
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
import test_community_platform_host as fixture
from test_community_finance_cards_browser import configure_fixture,SCOPE,COMMUNITY
from scripts.pr122_customer_core import canonical
from scripts.community_order_store import create_order
from scripts.community_provider_reference import provider_order_reference

def seed_snapshot(host,fx):
    c=host.center;directory=host.application.communities;actions=host.application.provider_actions
    web=c.login('one@example.org','FixturePassword123!')
    directory.write(directory.grants['platform'],dict(id=COMMUNITY,tenant='tenant1',owner=fx.fx.uid1,name='合成分账社区',description='仅原报告测试',contact='合成联系人',state='APPROVED',version=1,opinion='',updated_at=c.now()))
    def finance(op,p):return actions.dispatch(web['token'],web['csrf'],dict(workspace='finance',operation=op,params=p))
    directory.dispatch(web['token'],web['csrf'],dict(workspace='platform',operation='community_receiver_bind',params=dict(community_id=COMMUNITY,provider_workspace='finance',receiver_id='community',expected_version=0)))
    create_order(host.persistence.runtime.demo.db,SCOPE,'snapshot_order',101)
    finance('rule_create',dict(rule_id='snapshot_rule',version=1,shares_bps=dict(community=1000),description='synthetic original snapshot',unfreeze_unsplit=True))
    finance('rule_activate',dict(rule_id='snapshot_rule',version=1,expected_revision=0))
    finance('rule_freeze',dict(reference='snapshot_order'))
    signer=serialization.load_pem_private_key(fx.reader_valid_private.encode(),password=None)
    def signed(data):
        raw=canonical(data);stamp=str(c.now());nonce='snapshot-fixture'
        signature=signer.sign((stamp+'\n'+nonce+'\n').encode()+raw+b'\n',padding.PKCS1v15(),hashes.SHA256())
        return {'Wechatpay-Serial':'PUB_KEY_ID_TEST','Wechatpay-Timestamp':stamp,'Wechatpay-Nonce':nonce,'Wechatpay-Signature':base64.b64encode(signature).decode()},raw
    def provider(request):
        if request.method=='GET' and '/v3/pay/partner/transactions/' in request.full_url:
            return signed(dict(sp_mchid=actions.reader._mchid,sub_mchid='1900000001',sp_appid=fx.wechat['appid'],out_trade_no=provider_order_reference(actions.reader._mchid,SCOPE,'snapshot_order'),amount=dict(total=101,currency='CNY'),trade_state='SUCCESS',transaction_id='123456789'))
        if request.method=='POST' and request.full_url.endswith('/v3/profitsharing/orders'):
            payload=json.loads(request.data)
            return signed(dict(sub_mchid=payload['sub_mchid'],out_order_no=payload['out_order_no'],transaction_id=payload['transaction_id'],state='FINISHED',receivers=[dict(type=r['type'],account=r['account'],amount=r['amount'],result='SUCCESS') for r in payload['receivers']]))
        raise AssertionError('UNEXPECTED_SYNTHETIC_TRANSPORT')
    with patch.object(actions.reader,'_fetch',side_effect=provider):finance('split_by_rule',dict(reference='snapshot_order',request_id='snapshot_split'))
    report=directory.dispatch(web['token'],web['csrf'],dict(workspace='platform',operation='community_earnings',params=dict(community_id=COMMUNITY,after_id='')))
    assert len(report['records'])==1 and report['records'][0]['received_minor']==10 and report['page_net_minor']==10
    assert report['totals_scope']=='CURRENT_PAGE_ONLY' and report['finance_status']=='UNCONFIRMED'
    return report

def seed_refund_observations(host,fx):
    # Original encrypted attribution and verified-projection fixture records, not
    # external transactions. This follows the existing backend refund tests.
    from scripts.community_order_provider_projection import project_verified_query,project_verified_refund
    c=host.center;db=host.persistence.runtime.demo.db;commerce=host.application.commerce
    for reference in ('refund_partial_order','refund_without_events'):
        create_order(db,SCOPE,reference,101)
        commerce._save(SCOPE,'project1',fx.fx.uid1,'ORDER',reference,dict(reference=reference,user_id=fx.fx.uid1,scope=dict(SCOPE),community_id=COMMUNITY,referrer_user_id=None,lines=[dict(item_id='synthetic_item',quantity=1,unit_minor=101)],amount_minor=101,currency='CNY'))
        expected=dict(sp_mchid='1900000000',sub_mchid='1900000001',out_trade_no=reference,amount_minor=101)
        observation=dict(source='SIGNED_PROVIDER_ORDER_QUERY',signature_key_id='fixture',out_trade_no=reference,amount_minor=101,currency='CNY',provider_state='SUCCESS',transaction_id='123456790' if reference=='refund_partial_order' else '123456791',body_sha256='a'*64)
        project_verified_query(db,SCOPE,reference,expected,observation,c.now(),'fixture')
    project_verified_refund(db,SCOPE,'refund_partial_order','partial_refund1',11,101,'b'*64,c.now())
    web=c.login('one@example.org','FixturePassword123!')
    result=host.application.communities.dispatch(web['token'],web['csrf'],dict(workspace='platform',operation='community_refunds',params=dict(community_id=COMMUNITY,after_id='')))
    rows={row['reference']:row for row in result['records']}
    assert rows['refund_partial_order']['order_state']=='SUCCESS' and rows['refund_partial_order']['refund_observations'][0]['refund_minor']==11
    assert rows['refund_without_events']['refund_observation_status']=='NO_RECORDED_VERIFIED_REFUND'
    assert result['finance_status']=='UNCONFIRMED'
    return result

class SplitSnapshotFixture(unittest.TestCase):
    def test_original_signed_fixture_report_no_network(self):
        fx=fixture.FormalHost();fx.setUp();self.addCleanup(fx.doCleanups);configure_fixture(fx)
        with patch('urllib.request.urlopen',side_effect=AssertionError('NO_PROVIDER_NETWORK')):
            with fx.open() as host:
                report=seed_snapshot(host,fx);row=report['records'][0];refunds=seed_refund_observations(host,fx);self.assertEqual(len(refunds['records']),2)
                self.assertEqual((row['request_id'],row['receiver_id'],row['rule_id'],row['rule_version']),('snapshot_split','community','snapshot_rule',1))
                self.assertEqual((row['received_minor'],row['returned_minor'],row['net_minor']),(10,0,10))

class SplitSnapshotBrowser(unittest.TestCase):
    @unittest.skipIf(os.geteuid()==0,'Original non-root Unix peer/browser chain runs on Hosted only')
    def test_report20_and_snapshot23_50_real_http(self):
        from playwright.sync_api import sync_playwright,expect
        fx=fixture.FormalHost();fx.setUp();self.addCleanup(fx.doCleanups);configure_fixture(fx)
        evidence=Path('community-admin-browser-evidence');evidence.mkdir(exist_ok=True)
        with patch('urllib.request.urlopen',side_effect=AssertionError('NO_PROVIDER_NETWORK')):
            with fx.open() as host:
                seed_snapshot(host,fx);seed_refund_observations(host,fx)
                server=host.application.listen_proxy(fx.plan['socket_path'],fx.plan['https_origin'],fx.plan['nginx_uid'],fx.plan['nginx_gid']);server.timeout=.1
                received=[];shots=[]
                def flow():
                    def forward(route):
                        req=route.request;path=req.url.removeprefix(fx.plan['https_origin']+'/community-preview')
                        conn=http.client.HTTPConnection('unused',timeout=5);conn.sock=socket.socket(socket.AF_UNIX);conn.sock.settimeout(5);conn.sock.connect(fx.plan['socket_path'])
                        headers={k:v for k,v in req.all_headers().items() if k.lower() not in ('host','content-length')};headers['Host']='uk.wenwenwenyiyiyi.work';headers['X-Xuanjun-Client-IP']='127.0.0.1'
                        try:
                            conn.request(req.method,path,body=req.post_data_buffer,headers=headers);response=conn.getresponse();body=response.read()
                            operation=json.loads(req.post_data).get('operation') if path=='/community/directory' else None
                            received.append(dict(path=path,status=response.status,operation=operation))
                            route.fulfill(status=response.status,headers=dict(response.getheaders()),body=body)
                        finally:conn.close()
                    with sync_playwright() as p:
                        browser=p.chromium.launch(headless=True)
                        try:
                            page=browser.new_page(viewport=dict(width=1440,height=1000));errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.route(fx.plan['https_origin']+'/**',forward)
                            page.goto(fx.plan['https_origin']+'/community-preview/community/portal')
                            session=page.locator('#community-session');session.locator('[name=email]').fill('one@example.org');session.locator('[name=password]').fill('FixturePassword123!');session.get_by_role('button',name='登录',exact=True).click();expect(session.locator('[role=status]')).to_contain_text('已登录')
                            account=page.locator('.admin-account')
                            if account.get_attribute('open') is None:account.locator('summary').click()
                            session.get_by_role('combobox',name='已授权工作区',exact=True).select_option('platform')
                            def shot(name):
                                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(evidence/(name+'.png')),full_page=True);shots.append(name+'.png')
                            expect(page.locator('main h1')).to_have_text('平台管理');expect(page.locator('.admin-home-hero h2')).to_be_visible();expect(page.locator('.admin-home-hero h2')).to_have_text('平台管理')
                            expect(page.locator('.admin-home .admin-card')).to_have_count(14)
                            expect(page.locator('.admin-home-group')).to_have_count(4)
                            for i,count in enumerate((5,3,4,2)):expect(page.locator('.admin-home-group').nth(i).locator('.admin-card')).to_have_count(count)
                            shot('25-platform-home-1440');page.set_viewport_size({'width':390,'height':844});expect(page.locator('.admin-navigation-disclosure')).not_to_have_attribute('open','');expect(page.locator('.admin-home-hero')).to_be_visible();shot('25-platform-home-390')
                            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                            page.set_viewport_size({'width':1440,'height':1100});expect(page.locator('.admin-navigation-disclosure')).to_have_attribute('open','')
                            nav=page.get_by_role('navigation',name='社区功能',exact=True);nav.get_by_role('button',name='社区订单、收益与结算观察',exact=True).click();panel=page.locator('.community-report-panel');page.locator('#reportReference').fill(COMMUNITY)
                            if page.locator('.report-query-controls').get_attribute('open') is None:page.locator('.report-query-controls > summary').click()
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==200):page.locator('#communityEarnings').click()
                            expect(panel.locator('.report-query-controls[open]')).to_have_count(0);overview=panel.locator(':scope > .community-record-card');expect(overview).to_contain_text('¥0.10 CNY');expect(overview).to_contain_text('财务核销未确认');shot('20-nonempty-synthetic-1440')
                            panel.get_by_role('button',name='查看分账快照',exact=True).click();expect(page.locator('main h1')).to_have_text('分账快照');expect(panel.locator('.report-rows')).to_contain_text('snapshot_split');expect(panel.locator('.report-rows')).to_contain_text('仅当前页');shot('23-list-synthetic-1440')
                            panel.get_by_role('button',name='查看分账记录详情',exact=True).click();detail=panel.locator('.community-snapshot-detail');expect(page.locator('main h1')).to_have_text('分账快照 · 详情');expect(detail).to_contain_text('snapshot_rule');expect(detail).to_contain_text('未确认');expect(detail).to_contain_text('¥0.00 CNY');shot('50-detail-synthetic-1440')
                            detail.get_by_role('button',name='返回分账快照列表',exact=True).click();expect(panel.locator('.report-rows')).to_be_visible();shot('23-return-synthetic-1440')
                            panel.get_by_role('button',name='返回观察记录',exact=True).click();expect(overview).to_be_visible();nav.get_by_role('button',name='分账快照',exact=True).click();expect(page.locator('main h1')).to_have_text('分账快照');expect(panel.locator('.report-rows')).to_contain_text('snapshot_split')
                            if page.locator('.report-query-controls').get_attribute('open') is None:page.locator('.report-query-controls > summary').click()
                            page.locator('#reportReference').fill('co_'+'f'*32)
                            if page.locator('.report-query-controls').get_attribute('open') is None:page.locator('.report-query-controls > summary').click()
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status>=400):page.locator('#communityEarnings').click()
                            expect(panel.locator('.report-rows')).to_be_empty();expect(detail).to_be_empty();expect(panel).not_to_contain_text('snapshot_split');shot('23-denied-cleared-1440')
                            if page.locator('.report-query-controls').get_attribute('open') is None:page.locator('.report-query-controls > summary').click()
                            page.locator('#reportReference').fill(COMMUNITY)
                            if page.locator('.report-query-controls').get_attribute('open') is None:page.locator('.report-query-controls > summary').click()
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status==200):panel.get_by_role('button',name='查询原订单退款观察',exact=True).click()
                            expect(page.locator('main h1')).to_have_text('退款观察');expect(panel.locator('.report-rows')).to_contain_text('支付成功，仍可能存在部分退款');expect(panel.locator('.report-rows')).to_contain_text('¥0.11 CNY');expect(panel.locator('.report-rows')).to_contain_text('未记录已签验退款事件，不等于未退款');shot('24-refund-list-synthetic-1440')
                            partial=panel.locator('.report-rows .community-record-card').filter(has_text='refund_partial_order');partial.locator('xpath=following-sibling::button[1]').click();expect(page.locator('main h1')).to_have_text('退款观察 · 详情');expect(detail).to_contain_text('partial_refund1');expect(detail).to_contain_text('¥1.01 CNY');expect(detail).to_contain_text('¥0.11 CNY');expect(detail).to_contain_text('仅查看，不执行退款或分账');expect(detail).to_contain_text('未确认');shot('51-refund-detail-synthetic-1440')
                            detail.get_by_role('button',name='返回退款观察列表',exact=True).click();expect(panel.locator('.report-rows')).to_be_visible();shot('24-refund-return-1440');nav.get_by_role('button',name='退款观察',exact=True).click();expect(page.locator('main h1')).to_have_text('退款观察')
                            if page.locator('.report-query-controls').get_attribute('open') is None:page.locator('.report-query-controls > summary').click()
                            page.locator('#reportReference').fill('co_'+'f'*32)
                            if page.locator('.report-query-controls').get_attribute('open') is None:page.locator('.report-query-controls > summary').click()
                            with page.expect_response(lambda r:r.url.endswith('/community/directory') and r.status>=400):panel.get_by_role('button',name='查询原订单退款观察',exact=True).click()
                            expect(panel.locator('.report-rows')).to_be_empty();expect(detail).to_be_empty();expect(panel).not_to_contain_text('partial_refund1');shot('24-refund-denied-cleared-1440')
                            account=page.locator('.admin-account')
                            if account.get_attribute('open') is None:account.locator('summary').click()
                            session.locator('select').select_option('platform_readonly')
                            expect(page.locator('main h1')).to_have_text('平台管理');expect(page.locator('.admin-home-hero h2')).to_be_visible();expect(page.locator('.admin-home-hero h2')).to_have_text('平台管理');expect(page.locator('.admin-home .admin-card')).to_have_count(14)
                            expect(panel.locator('.report-rows')).to_be_empty();shot('25-role-switch-cleared-1440')
                            if account.get_attribute('open') is None:account.locator('summary').click()
                            session.locator('[data-logout]').click();expect(session.locator('[role=status]')).to_have_text('已退出登录。')
                            expect(page.locator('.admin-home .admin-card')).to_have_count(0);expect(page.locator('main h1')).to_have_text('工作台');shot('25-logout-neutral-1440')
                            self.assertEqual(errors,[]);self.assertTrue(all(r['operation'] in ('community_earnings','community_refunds') for r in received if r['operation']))
                            (evidence/'split-snapshot-receipt.json').write_text(json.dumps(dict(scope='SYNTHETIC_SIGNED_FIXTURE_ORIGINAL_HTTP_NOT_CUSTOMER_ACCEPTANCE',refund_source='SYNTHETIC_SAVED_VERIFIED_PROJECTION_NOT_THIS_RUN_WECHAT_SIGNATURE',shots=shots,received=received,browser_assertions_passed=True),ensure_ascii=False,indent=2)+'\n')
                        finally:browser.close()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(flow);deadline=time.monotonic()+90
                    while not future.done() and time.monotonic()<deadline:server.handle_request()
                    future.result(timeout=2)
