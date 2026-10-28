"""Actual browser navigation of isolated original-field projections, no business IO."""
import functools,json,os,threading,unittest
from playwright.sync_api import expect
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from scripts.community_ui_preview_build import build,main,BASE,ROOT
class SourceBoundary(unittest.TestCase):
    def test_scene_photos_do_not_inherit_ocr_prompt(self):
        script=(BASE/'ui-preview/preview.js').read_text()
        stage=script.split('function stage(p)',1)[1].split('function attachBeneficiary',1)[0]
        self.assertIn("x.id==='admission-business_info-'?'':",stage)
        self.assertIn('识别未接通',stage)
        native=(ROOT/'clients/community-mini/pages/merchant-join/index.wxml').read_text()
        photo=native.split('线下实际经营场景照片',1)[1].split('小程序服务截图',1)[0]
        self.assertNotIn('OCR未接通',photo)
        self.assertIn('场景照片无需OCR',photo)
        self.assertNotIn('bindtap="recognizeDocument"',photo)
        self.assertIn('OCR按需调用且默认关闭',native)
        self.assertIn('识别：按需调用；上传本身不自动生成识别结果或自动回填',native)

    def test_generated_inputs_and_scoped_fields(self):
        data=build()
        self.assertEqual((BASE/'ui-preview/sources.js').read_text(),'window.COMMUNITY_UI_PREVIEW='+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+';\n')
        self.assertEqual(len([p for p in data['pages'] if p['role']=='admission' and p['kind']=='stage']),4)
        self.assertEqual(len([p for p in data['pages'] if p['id']=='admission-beneficiary']),1)
        admission=[p for p in data['pages'] if p['role']=='admission']
        self.assertEqual(sum('bank_account_info.account_number' in p['html'] for p in admission),1)
        self.assertEqual(sum('business_license_info.merchant_name' in p['html'] for p in admission),1)
        self.assertEqual(len({p['id'] for p in data['pages']}),len(data['pages']))
        self.assertTrue(all('<script' not in p['html'] and 'onclick=' not in p['html'] for p in data['pages']))
        source=(BASE/'ui-preview/preview.js').read_text()
        self.assertNotIn('fetch(',source);self.assertNotIn('XMLHttpRequest',source)
        self.assertNotIn('requestPayment',source);self.assertNotIn('community-session',source)
        self.assertIn("connect-src 'none'",(BASE/'ui-preview/index.html').read_text())
    def test_isolated_original_host_asset_allowlist(self):
        from scripts.community_web_entries import asset,UI_ASSETS
        for path,(name,mime) in UI_ASSETS.items():
            self.assertEqual(asset(path),((BASE/name).read_bytes(),mime))
        html=asset('/community/ui-preview/')[0].decode()
        self.assertNotIn('web-session.js',html)
        for path in ['/community/ui-preview/../workbench.html','/community/ui-preview/secrets.json','/community/ui-preview/?role=admin']:
            self.assertIsNone(asset(path))
class ClickThrough(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.pw=sync_playwright().start();cls.browser=cls.pw.chromium.launch(headless=True)
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)+'/demos/community-stage/ui-preview/'
        cls.out=Path(os.environ.get('COMMUNITY_UI_EVIDENCE','/tmp/community-ui-evidence'));cls.out.mkdir(parents=True,exist_ok=True)
        cls.data=build();cls.metrics=[]
    @classmethod
    def tearDownClass(cls):
        (cls.out/'browser-metrics.json').write_text(json.dumps(cls.metrics,ensure_ascii=False,indent=2))
        cls.browser.close();cls.pw.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join(2)
    def assert_layout(self,page,width,name):
        m=page.evaluate('''() => ({width:innerWidth,scale:visualViewport.scale,scroll:document.documentElement.scrollWidth,font:getComputedStyle(document.querySelector('h1')).fontSize,visibleHeads:[...document.querySelectorAll('main h1')].filter(e=>e.getClientRects().length).length})''')
        self.assertEqual(m['width'],width);self.assertEqual(m['scale'],1)
        self.assertLessEqual(m['scroll'],width+1);self.assertEqual(m['visibleHeads'],1)
        self.metrics.append(dict(page=name,**m))
        page.screenshot(path=str(self.out/(str(width)+'-'+name+'.png')),full_page=True)
    def test_every_module_three_viewports_click_return_refresh(self):
        for width,height in ((1440,1000),(430,932),(390,844),(320,740)):
            context=self.browser.new_context(viewport={'width':width,'height':height})
            page=context.new_page();page.set_default_timeout(5000);requests=[];errors=[]
            page.on('request',lambda r:requests.append((r.method,r.url)))
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.url)
            for role in self.data['roles']:
                page.get_by_label('查看身份',exact=True).select_option(role)
                expect(page.locator('#view h1').first).to_have_text({'consumer':'发现身边好店','merchant':'邻里生活馆','community':'社区运营总览','platform':'平台管理','admission':self.data['roles']['admission']}[role])
                self.assert_layout(page,width,role+'-home')
                if role=='consumer':
                    page.locator('.mini-hero-card').click()
                    expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-stores/list$'))
                    expect(page.locator('#view')).to_contain_text('邻里生活馆')
                    page.get_by_role('link',name='查看示例门店详情',exact=True).click()
                    expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-stores/detail$'))
                    expect(page.locator('#view')).to_contain_text('社区便民服务')
                    page.get_by_role('link',name='查看展示操作',exact=True).click()
                    expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-stores/edit$'))
                    expect(page.locator('#view')).to_contain_text('社区便民服务')
                    expect(page.locator('#view')).to_contain_text('支付可用')
                    expect(page.locator('#view')).to_contain_text('分账可用')
                    expect(page.locator('#view')).not_to_contain_text('¥20.00')
                    expect(page.locator('#view')).not_to_contain_text('邻里服务套餐')
                    page.get_by_role('button',name='结束查看并返回',exact=True).click()
                    expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-stores/list$'))
                    expect(page.locator('#view')).to_contain_text('社区便民服务')
                    page.reload()
                    expect(page.locator('#view')).to_contain_text('邻里生活馆')
                    page.get_by_role('link',name='我的',exact=True).click()
                    expect(page.locator('#view h1').first).to_have_text('个人中心')
                    community=page.get_by_role('link',name='社区与归属',exact=False).first
                    expect(community).to_be_visible()
                    community.click()
                    expect(page.locator('.mini-tabbar a')).to_have_count(4)
                    expect(page.locator('#view')).to_contain_text('社区与归属')
                    page.get_by_role('link',name='我的',exact=True).click()
                    expect(page.locator('#view h1').first).to_have_text('个人中心')
                    continue
                pages=[p for p in self.data['pages'] if p['role']==role and p.get('kind')!='admission-field' and not p.get('legacyOnly') and not (role=='merchant' and p['id'] in ('merchant-native-catalog','merchant-native-detail'))]
                for module in pages:
                    with self.subTest(width=width,page=module['id']):
                        target='#/'+role+'/'+module['id']+('/edit' if role=='admission' else '/list')
                        if role=='community' and module['id']=='community-4-0-0':
                            # Two cards share this destination; choose the visible order-observation action by its user-facing label.
                            entry=page.locator('#view a[href="'+target+'"]').first
                            expect(entry).to_be_visible()
                            entry.click()
                            expect(page.locator('#view h1').first).to_have_text('社区订单、收益与结算观察')
                        else:
                            menu_entry=page.locator('#menu a[href="'+target+'"]').first
                            view_entry=page.locator('#view a[href="'+target+'"]').first
                            if menu_entry.is_visible():
                                menu_entry.click()
                            elif view_entry.is_visible():
                                view_entry.click()
                            elif role=='admission' and module['id'] not in ('admission-start','admission-result'):
                                next_step=page.get_by_role('link',name='保存草稿并下一步',exact=True)
                                expect(next_step).to_be_visible()
                                next_step.click()
                            else:
                                self.fail('No visible user-facing entry for '+role+'/'+module['id']+' at '+str(width)+'px')
                            expect(page.locator('#view h1').first).to_have_text('申请资料核对' if module['id']=='admission-result' else module['title'])
                        if role=='community' and module['id']=='community-4-0-0':
                            page.get_by_role('button',name='查看查询状态',exact=True).first.click()
                            expect(page.locator('#community-query-status')).to_contain_text('未返回或伪造订单记录')
                            page.goto(self.url+'#/community/home')
                            expect(page.locator('#view h1').first).to_have_text('社区运营总览')
                            continue
                        if role!='admission':
                            page.get_by_role('link',name='查看详情',exact=True).click()
                            expect(page).to_have_url(__import__('re').compile('/detail$'))
                            page.locator('.edit-preview').click()
                        expect(page).to_have_url(__import__('re').compile('/edit$'))
                        self.assert_layout(page,width,module['id']+'-edit')
                        page.reload();expect(page.locator('#view h1').first).to_have_text('申请资料核对' if module['id']=='admission-result' else module['title'])
                        page.locator('#demo-save').click()
                        if role!='admission':
                            expect(page).to_have_url(__import__('re').compile('/list$'))
                            expect(page.locator('.record')).to_be_visible()
                        page.get_by_role('link',name='返回菜单',exact=True).click()
                        expect(page.locator('#view h1').first).to_have_text({'consumer':'发现身边好店','merchant':'邻里生活馆','community':'社区运营总览','platform':'平台管理','admission':self.data['roles']['admission']}[role])
            self.assertEqual(errors,[])
            self.assertTrue(all(method=='GET' and url.startswith(self.url.rsplit('/ui-preview/',1)[0]) for method,url in requests),requests)
            context.close()
    def test_consumer_store_catalog_and_collection_status_are_isolated(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/consumer/consumer-stores/list')
            expect(page.locator('#view')).to_contain_text('邻里生活馆')
            expect(page.locator('#view')).to_contain_text('社区便民服务')
            expect(page.locator('#view')).to_contain_text('演示商家')
            expect(page.locator('#view')).to_contain_text('支付可用')
            expect(page.locator('#view')).to_contain_text('分账可用')
            expect(page.locator('#view')).not_to_contain_text('商品上架')
            expect(page.locator('#view')).to_contain_text('非真实营业信息')
            page.get_by_role('link',name='查看示例门店详情',exact=True).click()
            expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-stores/detail$'))
            expect(page.locator('#view h1').first).to_have_text('商家展示')
            expect(page.locator('#view')).to_contain_text('邻里生活馆（示例门店）')
            expect(page.locator('#view')).to_contain_text('社区便民服务')
            expect(page.locator('#view')).to_contain_text('未经真实商户核验')
            page.get_by_role('link',name='查看展示操作',exact=True).click()
            expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-stores/edit$'))
            expect(page.locator('#view')).to_contain_text('邻里生活馆（示例门店）')
            expect(page.locator('#view')).to_contain_text('社区便民服务')
            expect(page.locator('#view')).to_contain_text('支付可用')
            expect(page.locator('#view')).to_contain_text('merchantID不代表支付已开通')
            expect(page.locator('#view')).to_contain_text('分账可用')
            expect(page.locator('#view')).not_to_contain_text('邻里服务套餐')
            expect(page.locator('#view')).not_to_contain_text('¥20.00')
            page.get_by_role('button',name='结束查看并返回',exact=True).click()
            expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-stores/list$'))
            expect(page.locator('#view')).to_contain_text('邻里生活馆（示例门店）')
            expect(page.locator('#view')).to_contain_text('社区便民服务')
            expect(page.locator('#view')).to_contain_text('支付可用')
            expect(page.locator('#view')).to_contain_text('merchantID不代表支付已开通')
            expect(page.locator('#view')).to_contain_text('分账可用')
            expect(page.locator('#view')).not_to_contain_text('邻里服务套餐')
            expect(page.locator('#view')).not_to_contain_text('¥20.00')
            page.get_by_role('link',name='商家入驻（同一小程序）',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text(self.data['roles']['admission'])
            page.goto(self.url+'#/merchant/merchant-native-collection/list')
            for label,expected in [
                ('查看正式取得条件','本预览从不请求微信'),
                ('查看不可用状态','尚无已核验的正式收款码'),
                ('查看取得失败状态','不生成或回退假二维码'),
                ('查看相册保存失败','无正式图片可保存'),
            ]:
                page.get_by_role('button',name=label,exact=True).click()
                expect(page.locator('#code-review-status')).to_contain_text(expected)
            self.assertEqual(page.locator('main img').count(),0)
            page.get_by_label('示例状态',exact=True).select_option('error')
            expect(page.locator('#view')).to_contain_text('暂时无法加载')
            self.assertEqual(page.locator('[data-code-review]').count(),0)
            self.assertEqual(page.get_by_role('link',name='查看详情',exact=True).count(),0)
        finally:
            page.close()

    def test_admission_conditions_one_shared_draft_history_and_reload(self):
        context=self.browser.new_context(viewport={'width':390,'height':844});page=context.new_page();page.goto(self.url+'#/admission/home')
        page.locator('[data-option="entity"]').select_option('SOLE_PROPRIETOR')
        self.assertEqual(page.locator('[data-option="ubos"]').count(),0)
        page.locator('[data-option="entity"]').select_option('ENTERPRISE')
        page.locator('[data-option="contact"]').select_option('SUPER')
        page.locator('[data-option="scene"]').select_option('both')
        page.locator('[data-option="ubos"]').select_option('2')
        page.locator('.module-card').filter(has_text='主体与门店').click()
        expect(page.locator('.admission-data-card').filter(has_text='最终受益人资料')).to_have_attribute('open','')
        page.locator('[data-path$=".ubo_id_doc_name"]').fill('示例甲')
        page.get_by_role('button',name='受益人 2',exact=True).click()
        page.locator('[data-path$=".ubo_id_doc_name"]').fill('示例乙')
        stored=page.evaluate("JSON.parse(localStorage.getItem('community-ui-preview:v1'))")
        self.assertEqual(stored['options']['uboIndex'],1)
        self.assertEqual(stored['application']['subject_info.ubo_info_list.1.ubo_id_doc_name'],'示例乙')
        page.reload();self.assertEqual(page.locator('[data-path$=".ubo_id_doc_name"]').input_value(),'示例乙')
        page.get_by_role('button',name='受益人 1',exact=True).click()
        self.assertEqual(page.locator('[data-path$=".ubo_id_doc_name"]').input_value(),'示例甲')
        page.get_by_role('button',name='演示保存并返回',exact=True).click()
        self.assertTrue(page.url.endswith('/admission-start/edit'))
        page.go_back();self.assertTrue(page.url.endswith('/admission/home'))
        page.go_forward();self.assertTrue(page.url.endswith('/admission-start/edit'))
        for field in [p for p in self.data['pages'] if p.get('kind')=='admission-field']:
            if field['title']=='其他法人证件':continue
            page.goto(self.url+'#/admission/'+field['id']+'/edit')
            self.assert_layout(page,390,field['id'])
            if field['title']=='管理员':self.assertGreater(page.locator('[data-path="contact_info.contact_id_number"]').count(),0)
        context.close()
    def test_self_contained_review_file_clicks_without_network(self):
        import tempfile
        from scripts.community_ui_preview_build import bundle
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'community-ui-preview.html'
            before={p:p.read_bytes() for p in [ROOT/'docs/development/COMMUNITY_UI_PREVIEW_PAGE_MAP_20261022.md',BASE/'ui-preview/sources.js']}
            bundle(target)
            self.assertTrue(all(p.read_bytes()==raw for p,raw in before.items()))
            context=self.browser.new_context(viewport={'width':390,'height':844});page=context.new_page();requests=[];errors=[]
            page.on('request',lambda r:requests.append(r.url));page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(target.as_uri())
            expect(page.locator('#view h1').first).to_have_text('邻里生活馆')
            page.get_by_label('查看身份',exact=True).select_option('admission')
            expect(page.locator('#view h1').first).to_have_text(self.data['roles']['admission'])
            page.locator('.module-card').filter(has_text='主体与门店').click()
            expect(page.locator('#view h1').first).to_have_text('主体与门店')
            page.locator('[data-stage-card="admission-contact-core"] summary').click()
            page.locator('[data-option="contact"]').select_option('SUPER')
            page.get_by_role('link',name='保存草稿并下一步',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('办理人与经营场景')
            page.locator('[data-option="scene"]').select_option('both')
            page.get_by_role('link',name='保存草稿并下一步',exact=True).click()
            page.get_by_role('link',name='上一步',exact=True).click()
            page.reload();expect(page.locator('[data-fields-for="admission-contact-super"]')).to_have_count(1)
            expect(page.locator('#view h1').first).to_have_text('办理人与经营场景')
            self.assertEqual(errors,[]);self.assertFalse(any(url.startswith(('http:','https:')) for url in requests))
            page.screenshot(path=str(self.out/'self-contained-file.png'),full_page=True)
            context.close()
    def test_same_app_entry_and_dual_terminal_selection(self):
        context=self.browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page()
        page.goto(self.url+'#/consumer/consumer-stores/list')
        page.get_by_role('link',name='商家入驻（同一小程序）',exact=True).click()
        expect(page.locator('#view h1').first).to_have_text(self.data['roles']['admission'])
        page.locator('[data-option="entity"]').select_option('SOLE_PROPRIETOR')
        page.locator('[data-option="contact"]').select_option('SUPER')
        page.locator('[data-option="scene"]').select_option('both')
        page.reload();expect(page.locator('[data-option="contact"]')).to_have_value('SUPER')
        expect(page.get_by_label('查看终端',exact=True)).to_be_disabled()
        self.assertLessEqual(page.locator('.layout').bounding_box()['width'],432)
        for role in ('community','platform'):
            page.get_by_label('查看身份',exact=True).select_option(role)
            for terminal in ('phone','desktop'):
                page.get_by_label('查看终端',exact=True).select_option(terminal)
                self.assertEqual(page.locator('body').get_attribute('data-terminal'),terminal)
                self.assert_layout(page,1440,role+'-'+terminal)
        context.close()

    def test_empty_loading_error_expired_and_no_business_requests(self):
        context=self.browser.new_context(viewport={'width':320,'height':740});page=context.new_page();requests=[]
        page.on('request',lambda r:requests.append((r.method,r.url)))
        page.goto(self.url+'#/merchant/merchant-0-0-0/list')
        # Use a real generated module id rather than relying on fixture numbering.
        first=next(p for p in self.data['pages'] if p['role']=='merchant' and not p.get('legacyOnly'))
        page.goto(self.url+'#/merchant/'+first['id']+'/list')
        for scenario in ['empty','loading','error','expired']:
            page.get_by_label('示例状态',exact=True).select_option(scenario)
            self.assertTrue(page.locator('.state').is_visible())
            self.assertEqual(page.get_by_role('link',name='查看详情',exact=True).count(),0)
            self.assert_layout(page,320,'state-'+scenario)
        page.get_by_role('button',name='查看示例记录',exact=True).click()
        expect(page.get_by_label('示例状态',exact=True)).to_have_value('sample')
        self.assertTrue(all(method=='GET' for method,url in requests))
        context.close()

    def test_four_role_dashboards_and_merchant_fixed_navigation(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/merchant/home')
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            for label in ('工作台','订单','门店','我的'):
                expect(page.locator('.mini-tabbar')).to_contain_text(label)
            expect(page.locator('#view')).not_to_contain_text('商品管理')
            self.assertTrue(any(p['id']=='merchant-native-catalog' for p in self.data['pages']))
            page.screenshot(path=str(self.out/'role-merchant-phone.png'),full_page=True)
            page.goto(self.url+'#/merchant/merchant-native-catalog/list')
            expect(page).to_have_url(__import__('re').compile(r'#/merchant/home$'))
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            page.get_by_role('link',name='订单',exact=True).click()
            expect(page).to_have_url(__import__('re').compile(r'#/merchant/merchant-native-orders/list$'))
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            page.get_by_label('查看身份',exact=True).select_option('community')
            for title in ('社区运营总览','社区商家成员','社区订单','分账明细','退款'):
                expect(page.locator('#view')).to_contain_text(title)
            expect(page.locator('#view')).to_contain_text('隔离合成投影')
            page.screenshot(path=str(self.out/'role-community-phone.png'),full_page=True)
            page.locator('#view a[href="#/community/community-4-0-0/list"]').click()
            expect(page.locator('#view h1').first).to_have_text('社区订单、收益与结算观察')
            page.get_by_role('button',name='查看查询状态',exact=True).first.click()
            expect(page.locator('#community-query-status')).to_contain_text('未返回或伪造订单记录')
            page.goto(self.url+'#/community/home')
            expect(page.locator('#view h1').first).to_have_text('社区运营总览')
            page.get_by_label('查看终端',exact=True).select_option('desktop')
            page.set_viewport_size({'width':1440,'height':1000})
            self.assert_layout(page,1440,'role-community-pc')
            page.screenshot(path=str(self.out/'role-community-pc.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_label('查看终端',exact=True).select_option('phone')
            page.get_by_label('查看身份',exact=True).select_option('platform')
            for title in ('订单与交易','入驻与商家','用户与社区','权限、通知与日志'):
                expect(page.locator('#view')).to_contain_text(title)
            unready=page.locator('.platform-dashboard .dashboard-card.is-unready')
            self.assertEqual({unready.nth(i).locator('b').inner_text() for i in range(unready.count())},{'支付管理','退款管理','分账明细','对账管理'})
            for i in range(unready.count()):
                expect(unready.nth(i).locator('.not-ready')).to_have_text('未就绪')
            ready=page.locator('.platform-dashboard .dashboard-card:not(.is-unready) b')
            self.assertEqual({ready.nth(i).inner_text() for i in range(ready.count())},{'订单管理','商家入驻审核','平台审核','平台商家管理','用户管理','社区管理','社区分账接收关系','平台运营查询','权限配置','通知与日志'})
            for title in ('用户管理','社区管理','商家入驻审核','平台审核','权限配置','通知与日志'):
                expect(page.locator('.platform-dashboard .dashboard-card:not(.is-unready)').filter(has_text=title).first).to_be_visible()
            page.screenshot(path=str(self.out/'role-platform-phone.png'),full_page=True)
            page.get_by_role('link',name='进入订单管理',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('订单管理')
            expect(page.locator('#view')).to_contain_text('UNCONFIRMED')
            page.get_by_label('查看终端',exact=True).select_option('desktop')
            page.set_viewport_size({'width':1440,'height':1000})
            self.assert_layout(page,1440,'role-platform-pc')
            page.goto(self.url+'#/platform/home')
            page.get_by_label('查看终端',exact=True).select_option('desktop')
            self.assertEqual(page.evaluate('innerWidth'),1440)
            page.screenshot(path=str(self.out/'role-platform-pc.png'),full_page=True)
        finally:
            page.close()

    def test_platform_unready_status_labels_remain_readable_on_phone_and_pc(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/platform/home')
            expect(page.locator('#view h1').first).to_have_text('平台管理')
            expect(page.locator('#view')).to_contain_text('订单与交易')
            expect(page.locator('#view')).to_contain_text('入驻与商家')
            expect(page.locator('#view')).to_contain_text('用户与社区')
            expect(page.locator('#view')).to_contain_text('权限、通知与日志')
            for width,height in ((390,844),(320,740)):
                page.set_viewport_size({'width':width,'height':height})
                page.get_by_label('查看终端',exact=True).select_option('phone')
                self.assert_layout(page,width,'role-platform-phone-'+str(width))
                cards=page.locator('.platform-dashboard .dashboard-card.is-unready')
                self.assertEqual({cards.nth(i).locator('b').inner_text() for i in range(cards.count())},{'支付管理','退款管理','分账明细','对账管理'})
                for i in range(cards.count()):
                    card=cards.nth(i)
                    badge=card.locator('.not-ready')
                    expect(badge).to_be_visible()
                    metrics=badge.evaluate("""e=>({text:e.innerText,writing:getComputedStyle(e).writingMode,rect:(()=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}})(),card:(()=>{const r=e.closest('.dashboard-card').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}})(),content:(()=>{const r=e.closest('.dashboard-card').children[1].getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}})()})""")
                    self.assertEqual(metrics['writing'],'horizontal-tb',metrics)
                    self.assertEqual(metrics['text'].strip(),'未就绪',metrics)
                    self.assertTrue(metrics['text'].strip(),metrics)
                    self.assertGreaterEqual(metrics['rect']['width'],35,metrics)
                    self.assertLessEqual(metrics['rect']['right'],metrics['card']['right']+0.5,metrics)
                    self.assertGreaterEqual(metrics['rect']['y'],metrics['content']['bottom']-1,metrics)
                    if width==320:
                        readable=badge.evaluate("""e=>{const box=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};const text=document.createRange();text.selectNodeContents(e);return {text:e.innerText.trim(),whiteSpace:getComputedStyle(e).whiteSpace,fontSize:parseFloat(getComputedStyle(e).fontSize),lineHeight:parseFloat(getComputedStyle(e).lineHeight),badge:box(e),textRect:box(text),card:box(e.closest('.dashboard-card')),title:box(e.closest('.dashboard-card').querySelector('b')),description:box(e.closest('.dashboard-card').querySelector('small')),viewport:{width:innerWidth,scrollWidth:document.documentElement.scrollWidth}}}""")
                        self.assertEqual(readable['whiteSpace'],'nowrap',readable)
                        self.assertEqual(readable['text'],'未就绪',readable)
                        self.assertGreaterEqual(readable['fontSize'],10.5,readable)
                        self.assertLessEqual(readable['textRect']['height'],readable['lineHeight']+1,readable)
                        self.assertLessEqual(readable['badge']['height'],readable['lineHeight']+10,readable)
                        self.assertLessEqual(readable['badge']['right'],readable['card']['right']+0.5,readable)
                        self.assertGreaterEqual(readable['badge']['y'],readable['description']['bottom']-1,readable)
                        self.assertGreaterEqual(readable['card']['width'],readable['badge']['width']+24,readable)
                        self.assertLessEqual(readable['title']['right'],readable['card']['right']+0.5,readable)
                        self.assertLessEqual(readable['description']['right'],readable['card']['right']+0.5,readable)
                        self.assertLessEqual(readable['card']['right'],width+0.5,readable)
                        self.assertLessEqual(readable['viewport']['scrollWidth'],width+1,readable)
                page.screenshot(path=str(self.out/('role-platform-phone-'+str(width)+'.png')),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.get_by_label('查看终端',exact=True).select_option('desktop')
            self.assert_layout(page,1440,'role-platform-pc-1440')
            self.assertEqual(page.evaluate('innerWidth'),1440)
            expect(page.locator('#view')).to_contain_text('订单与交易')
            expect(page.locator('#view')).to_contain_text('权限、通知与日志')
            page.screenshot(path=str(self.out/'role-platform-pc-1440.png'),full_page=True)
        finally:
            page.close()

    def test_admission_conditions_render_matching_fields_and_uploads(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            expect(page.locator('.admission-condition-panel').first).to_be_visible()
            expect(page.locator('.condition-warning').first).to_contain_text('不会默认')
            expect(page.locator('[data-fields-for="admission-subject_info-business_license_info-"] input[data-path="subject_info.business_license_info.license_number"]')).to_have_attribute('aria-required','true')
            expect(page.locator('input[data-material-kind="business_license"]')).to_be_visible()
            identity=page.locator('.admission-data-card').filter(has_text='法人身份证').first
            identity.locator('summary').click()
            expect(page.locator('input[data-material-kind="identity_front"]')).to_be_visible()
            expect(page.locator('input[data-material-kind="identity_back"]')).to_be_visible()
            ubo=page.locator('.admission-data-card').filter(has_text='最终受益人资料').first
            expect(ubo).to_be_visible()
            expect(page.locator('input[data-material-kind="ubo_1_front"]')).to_have_count(0)
            page.locator('[data-option="ubos"]').select_option('2')
            expect(page.locator('input[data-material-kind="ubo_1_front"]')).to_be_visible()
            expect(page.locator('input[data-material-kind="ubo_2_front"]')).to_be_visible()
            expect(page.locator('[data-fields-for="admission-beneficiary"] input[data-path="subject_info.ubo_info_list.0.ubo_id_doc_name"]')).to_have_attribute('aria-required','true')
            page.locator('[data-stage-card="admission-contact-core"] summary').click()
            page.locator('[data-option="contact"]').select_option('SUPER')
            phone=page.locator('input[data-path="contact_info.mobile_phone"]')
            expect(phone).to_have_attribute('type','tel')
            self.assertEqual(page.locator('[data-path="contact_info.mobile_phone"]').count(),1)
            page.get_by_role('link',name='保存草稿并下一步',exact=True).click()
            page.locator('[data-stage-card="admission-contact-super"] summary').click()
            expect(page.locator('input[data-material-kind="operator_identity"]')).to_be_visible()
            operator_doc=page.locator('[data-path="contact_info.contact_id_doc_type"]')
            if operator_doc.count():
                operator_doc.select_option('IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
                expect(page.locator('input[data-material-kind="operator_identity_back"]')).to_have_count(0)
            page.locator('[data-option="scene"]').select_option('both')
            expect(page.locator('input[data-material-kind="storefront_photo"]')).to_be_visible()
            expect(page.locator('input[data-material-kind="interior_photo"]')).to_be_visible()
        finally:
            page.close()

    def test_owner_retail_first_three_screens_and_platform_orders(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/consumer/home')
            page.get_by_label('查看身份',exact=True).select_option('consumer')
            expect(page.locator('#view h1').first).to_have_text('发现身边好店')
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            expect(page.locator('#view')).to_contain_text('发现身边好店')
            expect(page.locator('#view')).to_contain_text('介绍信息未核验')
            expect(page.locator('#view')).not_to_contain_text('邻里服务套餐')
            page.screenshot(path=str(self.out/'owner-consumer-home.png'),full_page=True)
            page.get_by_role('link',name='我的',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('个人中心')
            expect(page.locator('#view')).to_contain_text('商家入驻')
            expect(page.locator('#view')).to_contain_text('当前项目未发现可使用现有入口')
            for retained in ('社区与归属','推荐关系','我的通知','退款申请','支付与订单恢复'):
                expect(page.locator('#view')).to_contain_text(retained)
            community=page.get_by_role('link',name='社区与归属',exact=False).first
            expect(community).to_be_visible()
            community.click()
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            expect(page.locator('#view')).to_contain_text('社区与归属')
            page.get_by_role('link',name='我的',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('个人中心')
            page.reload()
            expect(page.locator('#view h1').first).to_have_text('个人中心')
            page.screenshot(path=str(self.out/'owner-consumer-profile.png'),full_page=True)
            expect(page.locator('#view')).not_to_contain_text('商品篮子')
            self.assertTrue(any(p['id']=='consumer-basket' for p in self.data['pages']))
            page.get_by_label('查看身份',exact=True).select_option('platform')
            page.get_by_role('link',name='进入订单管理',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('订单管理')
            expect(page.locator('#view')).to_contain_text('EXAMPLE-001')
            expect(page.locator('#view')).to_contain_text('UNCONFIRMED')
            expect(page.locator('#view')).to_contain_text('合成只读投影')
            self.assertEqual(page.get_by_role('button',name='退款',exact=True).count(),0)
            page.screenshot(path=str(self.out/'owner-platform-orders.png'),full_page=True)
            page.goto(self.url+'#/admission/admission-start/edit')
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            expect(page.locator('#view')).to_contain_text('同一份申请草稿')
            expect(page.locator('#view')).to_contain_text('当前适用条件下必填')
            page.screenshot(path=str(self.out/'owner-admission.png'),full_page=True)
            page.get_by_role('link',name='我的',exact=True).click()
            expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-profile/list$'))
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            page.get_by_label('查看身份',exact=True).select_option('platform')
            expect(page.locator('#menu')).to_contain_text('订单管理')
            expect(page.locator('#menu')).to_contain_text('入驻与商家')
            expect(page.locator('#menu')).to_contain_text('用户与社区')
            expect(page.locator('#menu')).to_contain_text('权限、通知与日志')
            expect(page.locator('#menu')).to_contain_text('支付管理')
            expect(page.locator('#menu')).to_contain_text('退款管理')
            expect(page.locator('#menu')).to_contain_text('分账明细')
            expect(page.locator('#menu')).to_contain_text('对账管理')
        finally:
            page.close()


    def test_platform_recommendations_are_distinct_from_referral_relations(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/consumer/home')
            expect(page.locator('.mini-tabbar a')).to_have_count(4)
            for label in ('首页','推荐','订单','我的'):
                expect(page.locator('.mini-tabbar')).to_contain_text(label)
            page.get_by_role('link',name='推荐',exact=True).click()
            self.assertTrue(page.url.endswith('/consumer/consumer-recommendations/list'),page.url)
            expect(page.locator('#view')).to_contain_text('平台推荐店铺')
            expect(page.locator('#view')).to_contain_text('尚未接入平台推荐来源')
            page.get_by_role('link',name='查看介绍',exact=False).click()
            self.assertTrue(page.url.endswith('/consumer/consumer-recommendations/detail'),page.url)
            expect(page.locator('#view')).to_contain_text('不代表平台已实际推荐')
            page.get_by_role('link',name='返回平台推荐列表',exact=True).click()
            expect(page.locator('#view')).to_contain_text('平台推荐店铺')
            page.get_by_role('link',name='我的',exact=True).click()
            page.locator('a[href="#/consumer/consumer-referrals/list"]').click()
            expect(page.locator('#view')).to_contain_text('绑定推荐人')
            expect(page.locator('#view')).to_contain_text('推荐人关系')
        finally:
            page.close()

    def test_consumer_profile_edit_local_save_cancel_reload(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/consumer/consumer-profile/list')
            page.get_by_role('link',name='个人资料',exact=False).click()
            self.assertTrue(page.url.endswith('/consumer/consumer-profile/edit'),page.url)
            page.locator('[data-profile-field="nickname"]').fill('演示昵称甲')
            page.locator('[data-profile-field="contact"]').fill('演示联系方式甲')
            page.reload()
            expect(page.locator('[data-profile-field="nickname"]')).to_have_value('演示昵称甲')
            expect(page.locator('[data-profile-field="contact"]')).to_have_value('演示联系方式甲')
            page.get_by_role('button',name='取消修改',exact=True).click()
            page.get_by_role('link',name='个人资料',exact=False).click()
            page.locator('[data-profile-field="nickname"]').fill('演示昵称乙')
            page.get_by_role('button',name='保存本地示例',exact=True).click()
            page.get_by_role('link',name='个人资料',exact=False).click()
            expect(page.locator('[data-profile-field="nickname"]')).to_have_value('演示昵称乙')
        finally:
            page.close()

    def test_platform_order_filter_empty_all_detail_return(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/platform/home')
            page.get_by_role('link',name='进入订单管理',exact=True).click()
            page.get_by_label('订单状态筛选',exact=True).select_option('ALL')
            expect(page.locator('.platform-order-row')).to_contain_text('EXAMPLE-001')
            page.get_by_label('订单状态筛选',exact=True).select_option('FAILED')
            expect(page.locator('.platform-empty')).to_be_visible()
            page.reload()
            expect(page.get_by_label('订单状态筛选',exact=True)).to_have_value('FAILED')
            page.get_by_label('订单状态筛选',exact=True).select_option('ALL')
            page.get_by_role('link',name='查看详情',exact=True).click()
            expect(page.locator('#view')).to_contain_text('支付核验')
            expect(page.locator('#view')).to_contain_text('财务核销')
            page.get_by_role('link',name='返回订单列表（保留筛选）',exact=True).click()
            expect(page.get_by_label('订单状态筛选',exact=True)).to_have_value('ALL')
        finally:
            page.close()



    def test_admission_mobile_phone_has_tel_format_validation_and_draft_remains_allowed(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            page.locator('[data-stage-card="admission-contact-core"] summary').click()
            phone=page.locator('input[data-path="contact_info.mobile_phone"]')
            expect(phone).to_be_visible()
            expect(phone).to_have_attribute('type','tel')
            expect(phone).to_have_attribute('inputmode','tel')
            self.assertEqual(phone.get_attribute('maxlength'),'20')
            expect(phone).to_have_attribute('aria-required','true')
            phone.fill('12 34')
            expect(phone).to_have_attribute('aria-invalid','true')
            expect(phone.locator('xpath=ancestor::label')).to_contain_text('不含空格')
            phone.fill('+12345')
            expect(phone).to_have_attribute('aria-invalid','false')
            page.get_by_role('button',name='演示保存并返回',exact=True).click()
            expect(page.locator('#view')).to_contain_text('主体与门店')
        finally:
            page.close()



    def test_community_four_objects_have_distinct_read_only_routes(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/community/home')
            page.get_by_role('link',name='查看社区商家成员',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('社区商家成员')
            expect(page.locator('#view')).to_contain_text('kind=MERCHANT')
            expect(page.locator('#view')).to_contain_text('这不是微信进件列表')
            page.get_by_role('link',name='查看成员详情',exact=True).click()
            expect(page.locator('#view')).to_contain_text('社区商家成员详情')
            page.get_by_role('link',name='返回社区商家成员列表',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('社区商家成员')
            page.goto(self.url+'#/community/community-orders/list')
            expect(page.locator('#view')).to_contain_text('EXAMPLE-COMM-001')
            page.get_by_role('link',name='查看订单详情',exact=True).click()
            for field in ('merchant_id','store_id','支付核验','PENDING'):
                expect(page.locator('#view')).to_contain_text(field)
            page.get_by_role('link',name='返回社区订单列表',exact=True).click()
            page.goto(self.url+'#/community/community-splits/list')
            expect(page.locator('#view')).to_contain_text('UNCONFIRMED')
            expect(page.locator('#view')).to_contain_text('CURRENT_PAGE_ONLY')
            page.get_by_role('link',name='查看快照详情',exact=True).click()
            expect(page.locator('#view')).to_contain_text('不等于消费者退款')
            page.goto(self.url+'#/community/community-refunds/list')
            expect(page.locator('#view')).to_contain_text('社区角色没有独立退款API。本页只说明可使用现有订单REFUNDED状态/汇总字段；示例不是实际退款记录，不提供退款操作。')
            self.assertEqual(page.get_by_role('button',name='退款',exact=True).count(),0)
            page.get_by_role('link',name='查看退款状态说明',exact=True).click()
            expect(page.locator('#view')).to_contain_text('不存在独立社区退款API；真实退款详情未接入')
            expect(page.locator('#view')).to_contain_text('REFUNDED（仅示例字段投影）')
            expect(page.locator('#view')).to_contain_text('只读投影')
            page.get_by_role('link',name='返回退款观察',exact=True).click()
            expect(page.locator('#view h1').first).to_have_text('退款观察')
            self.assertEqual(page.get_by_role('button',name='退款',exact=True).count(),0)
        finally:
            page.close()



    def test_platform_read_only_assets_are_linked_without_granting_write_actions(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/platform/home')
            page.get_by_role('link',name='用户管理',exact=False).click()
            expect(page.locator('#view h1').first).to_have_text('平台运营查询')
            page.goto(self.url+'#/platform/home')
            page.get_by_role('link',name='社区管理',exact=False).click()
            expect(page.locator('#view h1').first).to_have_text('平台审核')
            page.goto(self.url+'#/platform/home')
            expect(page.locator('#view')).to_contain_text('缺少本角色可验证的数据绑定/权限来源')
            expect(page.locator('#view')).to_contain_text('支付管理')
            expect(page.locator('#view')).to_contain_text('退款管理')
            self.assertEqual(page.get_by_role('button',name='退款',exact=True).count(),0)
        finally:
            page.close()



    def test_owner_responsive_320_390_430_and_real_pc_roles(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            for width,height in ((320,740),(390,844),(430,900)):
                page.set_viewport_size({'width':width,'height':height})
                page.goto(self.url+'#/consumer/home')
                self.assert_layout(page,width,'owner-consumer-home')
                expect(page.locator('.mini-tabbar a')).to_have_count(4)
                for label in ('首页','推荐','订单','我的'):
                    expect(page.locator('.mini-tabbar')).to_contain_text(label)
                page.goto(self.url+'#/platform/home')
                self.assert_layout(page,width,'owner-platform-home')
                expect(page.locator('#view')).to_contain_text('订单与交易')
                expect(page.locator('#view')).to_contain_text('权限、通知与日志')
                grid=page.locator('.platform-dashboard .dashboard-grid').first
                self.assertEqual(page.locator('.platform-dashboard .dashboard-grid').first.evaluate("e=>getComputedStyle(e).gridTemplateColumns.split(' ').length"),1)
                for group in ('订单与交易','入驻与商家','用户与社区','权限、通知与日志'):
                    expect(page.locator('.platform-dashboard')).to_contain_text(group)
                page.screenshot(path=str(self.out / f'role-platform-home-{width}.png'),full_page=True)
                page.goto(self.url+'#/platform/platform-orders/list')
                expect(page.locator('.platform-orders h1')).to_have_text('订单管理')
                expect(page.locator('#platform-order-status')).to_be_visible()
                expect(page.locator('.platform-order-row').first).to_be_visible()
                viewport=page.locator('.platform-orders h1').evaluate("e=>({top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom})")
                self.assertLess(viewport['top'],height)
                page.screenshot(path=str(self.out / f'role-platform-orders-{width}.png'),full_page=True)
                page.goto(self.url+'#/merchant/home')
                self.assert_layout(page,width,'owner-merchant-home')
                expect(page.locator('.mini-tabbar a')).to_have_count(4)
                for label in ('工作台','订单','门店','我的'):
                    expect(page.locator('.mini-tabbar')).to_contain_text(label)
                expect(page.locator('#view')).to_contain_text('收款统计')
                expect(page.locator('#view')).to_contain_text('收款码与保存')
                page.goto(self.url+'#/consumer/consumer-profile/edit')
                page.locator('#profile-cancel').scroll_into_view_if_needed()
                geom=page.locator('#profile-cancel').evaluate("""e=>({buttonBottom:e.getBoundingClientRect().bottom,navTop:document.querySelector('.mini-tabbar').getBoundingClientRect().top,scroll:document.documentElement.scrollWidth,width:innerWidth})""")
                self.assertLessEqual(geom['buttonBottom'],geom['navTop']+1,geom)
                self.assertLessEqual(geom['scroll'],width+1,geom)
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(self.url+'#/community/home')
            self.assert_layout(page,1440,'owner-community-pc')
            page.goto(self.url+'#/platform/home')
            self.assert_layout(page,1440,'owner-platform-pc')
            expect(page.locator('#view')).to_contain_text('订单与交易')
            expect(page.locator('#view')).to_contain_text('权限、通知与日志')
        finally:
            page.close()



    def test_admission_condition_change_preserves_open_group_and_draft(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            subject=page.locator('.admission-data-card').filter(has_text='经营主体').first
            if subject.get_attribute('open') is None:
                subject.locator('summary').click()
            subject.locator('input[data-path="subject_info.business_license_info.license_number"]').fill('DEMO-123')
            identity=page.locator('.admission-data-card').filter(has_text='法人身份证').first
            if identity.get_attribute('open') is None:
                identity.locator('summary').click()
            before_doc_scroll=page.evaluate('window.scrollY')
            page.locator('[data-option="doc"]').select_option('IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
            other_identity=page.locator('.admission-data-card').filter(has_text='其他法人证件').first
            expect(other_identity).to_have_attribute('open','')
            expect(page.locator('[data-option="doc"]')).to_be_focused()
            expect(page.locator('[data-path="subject_info.business_license_info.license_number"]')).to_have_value('DEMO-123')
            self.assertLessEqual(abs(page.evaluate('window.scrollY')-before_doc_scroll),1)
            page.goto(self.url+'#/admission/admission-business/edit')
            scene=page.locator('.admission-data-card').filter(has_text='经营场景').first
            if scene.get_attribute('open') is None:
                scene.locator('summary').click()
            before_scene_scroll=page.evaluate('window.scrollY')
            page.locator('[data-option="scene"]').select_option('both')
            expect(scene).to_have_attribute('open','')
            expect(page.locator('[data-option="scene"]')).to_be_focused()
            self.assertLessEqual(abs(page.evaluate('window.scrollY')-before_scene_scroll),1)
        finally:
            page.close()

    def test_admission_task_continue_review_and_all_status_states(self):
        page=self.browser.new_page(viewport={'width':320,'height':740})
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            page.locator('.admission-data-card').first.locator('[data-stage-continue]').click()
            expect(page.locator('.admission-data-card').nth(1)).to_have_attribute('open','')
            page.locator('.admission-data-card').nth(1).locator('[data-stage-review]').click()
            expect(page.locator('#view h1').first).to_have_text('申请资料核对')
            expect(page.locator('#view')).to_contain_text('返回对应资料组修改')
            for scenario,label in (('loading','正在加载'),('empty','暂无记录'),('error','暂时无法加载'),('expired','会话已失效'),('no_permission','暂无此页面权限'),('unconnected','尚未连接业务数据')):
                page.get_by_label('示例状态',exact=True).select_option(scenario)
                expect(page.locator('#view')).to_contain_text(label)
                expect(page.locator('#view')).not_to_contain_text('EXAMPLE-COMM-001')
            page.get_by_label('示例状态',exact=True).select_option('sample')
        finally:
            page.close()

    def test_material_validation_error_is_local_and_old_record_is_retained(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            upload=page.locator('input[data-material-kind="business_license"]').first
            valid=self.out/'valid-material.png';valid.write_bytes(b'\x89PNG\r\n\x1a\n')
            upload.set_input_files(str(valid))
            expect(upload.locator('xpath=ancestor::label')).to_contain_text('valid-material.png')
            invalid=self.out/'invalid-material.txt';invalid.write_text('not an image')
            upload.set_input_files(str(invalid))
            expect(upload.locator('xpath=ancestor::label')).to_contain_text('仅支持PDF')
            expect(upload.locator('xpath=ancestor::label')).to_contain_text('valid-material.png')
        finally:
            page.close()


    def test_material_removal_failure_retains_saved_record_until_successful_retry(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            upload=page.locator('[data-material-kind="business_license"]')
            upload.set_input_files({'name':'retained-license.png','mimeType':'image/png','buffer':b'\x89PNG\r\n\x1a\n'})
            label=upload.locator('xpath=ancestor::label')
            expect(label).to_contain_text('retained-license.png')
            page.evaluate("() => { Storage.prototype.setItem=function(){throw Error('simulated storage failure')}; }")
            page.locator('[data-material-remove="business_license"]').click()
            expect(page.locator('#feedback')).to_contain_text('无法保存草稿')
            expect(page.locator('#feedback')).not_to_contain_text('已移除')
            expect(label).to_contain_text('retained-license.png')
            page.reload();expect(label).to_contain_text('retained-license.png')
            page.locator('[data-material-remove="business_license"]').click()
            expect(page.locator('#feedback')).to_contain_text('已移除')
            expect(label).not_to_contain_text('retained-license.png')
            page.reload();expect(label).not_to_contain_text('retained-license.png')
            expect(page.locator('[data-material-remove="business_license"]')).to_be_disabled()
        finally:
            page.close()

    def test_contact_review_links_and_failed_save_stay_with_current_draft(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            page.locator('[data-stage-card="admission-contact-core"] summary').click()
            expect(page.locator('[data-option="contact"]')).to_have_value('LEGAL')
            page.locator('[data-option="contact"]').select_option('SUPER')
            page.reload()
            expect(page.locator('[data-option="contact"]')).to_have_value('SUPER')
            expect(page.locator('[data-path="contact_info.mobile_phone"]')).to_have_count(1)
            page.goto(self.url+'#/admission/admission-result/edit')
            expect(page.locator('li').filter(has_text='超级管理员手机').locator('a')).to_have_attribute('href','#/admission/admission-start/edit/admission-contact-core')
            expect(page.locator('li').filter(has_text='法人/经营者身份证人像面').locator('a')).to_have_attribute('href','#/admission/admission-start/edit/admission-subject_info-identity_info-id_card_info-')
            page.locator('li').filter(has_text='法人/经营者身份证人像面').locator('a').click()
            expect(page.locator('[data-stage-card="admission-subject_info-identity_info-id_card_info-"]')).to_have_attribute('open','')
            expect(page.locator('[data-stage-card="admission-subject_info-identity_info-id_card_info-"] [data-path="subject_info.identity_info.id_card_info.id_card_name"]')).to_have_count(1)
            expect(page.locator('[data-stage-card="admission-subject_info-identity_info-id_card_info-"] [data-material-kind="identity_front"]')).to_have_count(1)
            page.goto(self.url+'#/admission/admission-start/edit/admission-contact-core')
            expect(page.locator('[data-stage-card="admission-contact-core"]')).to_have_attribute('open','')
            expect(page.locator('[data-stage-card="admission-contact-core"] [data-path="contact_info.mobile_phone"]')).to_have_count(1)
            page.goto(self.url+'#/admission/admission-business/edit/admission-contact-super')
            expect(page.locator('[data-stage-card="admission-contact-super"]')).to_have_attribute('open','')
            expect(page.locator('[data-stage-card="admission-contact-super"] [data-material-kind="operator_identity"]')).to_have_count(1)
            page.goto(self.url+'#/admission/admission-start/edit')
            page.evaluate("() => { Storage.prototype.setItem=function(){throw Error('simulated storage failure')}; }")
            page.get_by_role('link',name='保存草稿并下一步',exact=True).click()
            self.assertTrue(page.url.endswith('/admission-start/edit'))
            expect(page.locator('#feedback')).to_contain_text('无法保存草稿')
        finally:
            page.close()

    def test_admission_switching_retains_legal_super_and_mixed_document_materials(self):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        def ensure_open(selector):
            card=page.locator(selector)
            expect(card).to_have_count(1)
            if card.get_attribute('open') is None:
                card.locator('summary').click()
            expect(card).to_have_attribute('open','')
        def visible(selector):
            target=page.locator(selector)
            expect(target).to_be_visible()
            return target
        try:
            page.goto(self.url+'#/admission/admission-start/edit')
            core='[data-stage-card="admission-contact-core"]'
            ensure_open(core)
            visible(core+' [data-option="contact"]').select_option('SUPER')
            expect(page.locator(core)).to_contain_text('超级管理员资料')
            ensure_open(core)
            visible(core+' [data-option="contact"]').select_option('LEGAL')
            expect(page.locator(core)).to_contain_text('法人/经营者联系资料')

            id_card='[data-stage-card="admission-subject_info-identity_info-id_card_info-"]'
            id_doc='[data-stage-card="admission-subject_info-identity_info-id_doc_info-"]'
            ensure_open(id_card)
            visible(id_card+' [data-option="doc"]').select_option('IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
            ensure_open(id_doc)
            visible(id_doc+' [data-path="subject_info.identity_info.id_doc_info.id_doc_name"]').fill('LEGAL-PASSPORT-KEEP')
            visible(id_doc+' [data-material-kind="identity_front"]').set_input_files({'name':'legal-front.png','mimeType':'image/png','buffer':b'\x89PNG\r\n\x1a\n'})
            ensure_open(id_doc)
            visible(id_doc+' [data-option="doc"]').select_option('IDENTIFICATION_TYPE_IDCARD')
            ensure_open(id_card)
            visible(id_card+' [data-path="subject_info.identity_info.id_card_info.id_card_name"]')
            visible(id_card+' [data-option="doc"]').select_option('IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
            ensure_open(id_doc)
            expect(visible(id_doc+' [data-path="subject_info.identity_info.id_doc_info.id_doc_name"]')).to_have_value('LEGAL-PASSPORT-KEEP')
            expect(visible(id_doc+' [data-material-kind="identity_front"]').locator('xpath=ancestor::label')).to_contain_text('legal-front.png')

            ensure_open(core)
            visible(core+' [data-option="contact"]').select_option('SUPER')
            page.goto(self.url+'#/admission/admission-business/edit/admission-contact-super')
            operator='[data-stage-card="admission-contact-super"]'
            ensure_open(operator)
            visible(operator+' [data-path="contact_info.contact_id_doc_type"]').select_option('IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
            visible(operator+' [data-path="contact_info.contact_id_number"]').fill('SUPER-PASSPORT-KEEP')
            visible(operator+' [data-material-kind="operator_identity"]').set_input_files({'name':'operator-front.png','mimeType':'image/png','buffer':b'\x89PNG\r\n\x1a\n'})
            ensure_open(operator)
            visible(operator+' [data-path="contact_info.contact_id_doc_type"]').select_option('IDENTIFICATION_TYPE_IDCARD')
            expect(visible(operator+' [data-material-kind="operator_identity_back"]')).to_have_count(1)
            ensure_open(operator)
            visible(operator+' [data-path="contact_info.contact_id_doc_type"]').select_option('IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
            page.goto(self.url+'#/admission/admission-start/edit')
            ensure_open(core)
            visible(core+' [data-option="contact"]').select_option('LEGAL')
            ensure_open(core)
            visible(core+' [data-option="contact"]').select_option('SUPER')
            page.goto(self.url+'#/admission/admission-business/edit/admission-contact-super')
            ensure_open(operator)
            expect(visible(operator+' [data-path="contact_info.contact_id_number"]')).to_have_value('SUPER-PASSPORT-KEEP')
            expect(visible(operator+' [data-material-kind="operator_identity"]').locator('xpath=ancestor::label')).to_contain_text('operator-front.png')
        finally:
            page.close()

    def test_admission_contact_groups_and_customer_copy(self):
        source=(BASE/'ui-preview/preview.js').read_text()
        self.assertIn("admission-contact-core",source)
        self.assertIn("admission-contact-super",source)
        self.assertIn("business_license",source)
        self.assertIn("结算与资料",source)
        self.assertNotIn("复用",source)
        self.assertIn("未提交 / 未核验",source)


    def test_exact_66_design_routes_phone_pc_render_and_entry_mapping(self):
        """New renders, exact URL/mode/conditions and screenshot hashes, not page counts."""
        import re,hashlib,subprocess
        gallery=(BASE/'ui-preview/route-gallery.html').read_text()
        main=json.loads(re.search(r'const mainRoutes=(.*?);',gallery).group(1))
        sub=json.loads(re.search(r'const subRoutes=(.*?);',gallery).group(1))
        routes=[dict(role=r,id=i,mode='edit' if r=='admission' else 'list',kind='main') for r,i,_ in main]
        routes += [dict(role=r,id=i,mode=m,kind='sub') for r,i,m in sub]
        self.assertEqual((len(main),len(sub)),(34,32))
        # Snapshot pre-existing images first; those without route provenance are
        # explicitly unproven, never retroactively relabelled as exact coverage.
        inherited=[dict(file=f.name,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),route_provenance='UNPROVEN_LEGACY_TEST_CONTEXT') for f in sorted(self.out.glob('*.png'))]
        evidence=[]
        try:
            for width,height in ((390,844),(1440,1000)):
                context=self.browser.new_context(viewport={'width':width,'height':height})
                page=context.new_page();page.set_default_timeout(5000)
                errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                page.goto(self.url+'route-gallery.html')
                entries=page.locator('#route-index a')
                self.assertEqual(entries.count(),66)
                urls=[entries.nth(n).get_attribute('href') for n in range(66)]
                for n,r in enumerate(routes):
                    expected='#/'+r['role']+'/'+r['id']+('' if r['id']=='home' else '/'+r['mode'])
                    self.assertEqual(urls[n],'./index.html'+expected)
                    # Conditional passport/UBO routes need their own applicable
                    # UI context; all are explicitly synthetic local drafts.
                    seed=dict(drafts={},saved={},scenario='sample',options=dict(entity='ENTERPRISE',contact='SUPER',doc='IDENTIFICATION_TYPE_OVERSEA_PASSPORT' if 'id_doc_info' in r['id'] else 'IDENTIFICATION_TYPE_IDCARD',scene='both',ubos='1'),application={'subject_info.ubo_info_list.0.ubo_id_doc_type':'IDENTIFICATION_TYPE_OVERSEA_PASSPORT'})
                    page.evaluate('(seed)=>localStorage.setItem("community-ui-preview:v1",JSON.stringify(seed))',seed)
                    # A hash-only goto retains the previous page's JS state;
                    # use a distinct document URL to load this route's conditions.
                    page.goto(self.url+'index.html?route_render='+str(n)+'-'+str(width)+expected)
                    expect(page.locator('main h1').first).to_be_visible()
                    self.assertEqual(page.evaluate('location.hash'),expected)
                    self.assertNotIn('未找到',page.locator('#view').inner_text())
                    name=f'route-{n+1:02d}-{width}.png';path=self.out/name
                    page.screenshot(path=str(path),full_page=True)
                    self.assertGreater(path.stat().st_size,1000)
                    # Return via a real existing role entry, then re-open the
                    # exact route. This asserts navigation, not business writes.
                    page.locator('#role').select_option(r['role'])
                    expect(page.locator('main h1').first).to_be_visible()
                    page.goto(self.url+'index.html'+expected)
                    expect(page.locator('main h1').first).to_be_visible()
                    evidence.append(dict(r,index=n+1,width=width,height=height,route=expected,entry=urls[n],conditions=seed['options'],file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),render='PASS',navigation='PASS',function_acceptance='NOT_CLAIMED'))
                self.assertEqual(errors,[])
                context.close()
        finally:
            (self.out/'route-render-manifest.json').write_text(json.dumps(dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),source_tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),design_routes=66,expected_renders=132,completed_renders=len(evidence),routes=evidence,prior_image_inventory=inherited),ensure_ascii=False,indent=2))
        self.assertEqual(len(evidence),132)

    def test_cashier_local_preview_select_replace_remove_reload_not_server_success(self):
        context=self.browser.new_context(viewport={'width':390,'height':844})
        page=context.new_page();page.goto(self.url)
        page.evaluate('''() => localStorage.setItem('community-ui-preview:v1',JSON.stringify({drafts:{},saved:{},scenario:'sample',options:{entity:'ENTERPRISE',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',scene:'both',ubos:'legal_only'}}))''')
        page.goto(self.url+'index.html#/admission/admission-business/edit')
        field=page.locator('[data-material-kind="cashier_photo"]')
        expect(field).to_be_enabled()
        field.set_input_files(dict(name='cashier-synthetic.png',mimeType='image/png',buffer=b'\x89PNG\r\n\x1a\nsynthetic'))
        expect(field.locator('..').locator('.material-capacity')).to_contain_text('1/1')
        page.reload();expect(page.locator('[data-material-kind="cashier_photo"]').locator('..')).to_contain_text('cashier-synthetic.png')
        page.locator('[data-material-kind="cashier_photo"]').set_input_files(dict(name='replacement.png',mimeType='image/png',buffer=b'\x89PNG\r\n\x1a\nreplacement'))
        page.locator('[data-material-remove="cashier_photo"]').click();page.reload()
        expect(page.locator('[data-material-kind="cashier_photo"]').locator('..').locator('.material-capacity')).to_contain_text('0/1')
        expect(page.locator('[data-material-kind="cashier_photo"]').locator('..')).not_to_contain_text('replacement.png')
        page.screenshot(path=str(self.out/'cashier-local-only-390.png'),full_page=True)
        context.close()

    def test_recommendation_text_cta_stays_horizontal_at_phone_and_pc_widths(self):
        for width in (320,390,1440):
            context=self.browser.new_context(viewport={'width':width,'height':844})
            page=context.new_page();page.goto(self.url+'index.html#/consumer/consumer-recommendations/list')
            button=page.locator('.recommendation-card>b')
            expect(button).to_have_text('查看介绍 ›')
            box=button.bounding_box();self.assertGreaterEqual(box['width'],60);self.assertLess(box['height'],32)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
            page.locator('.recommendation-card').click()
            expect(page).to_have_url(__import__('re').compile(r'#/consumer/consumer-recommendations/detail$'))
            expect(page.locator('main h1').first).to_have_text('店铺介绍')
            page.screenshot(path=str(self.out/('recommendation-cta-'+str(width)+'.png')),full_page=True)
            context.close()

if __name__=='__main__':unittest.main()
