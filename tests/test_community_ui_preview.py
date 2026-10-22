"""Actual browser navigation of isolated original-field projections, no business IO."""
import functools,json,os,threading,unittest
from playwright.sync_api import expect
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from scripts.community_ui_preview_build import build,main,BASE,ROOT
class SourceBoundary(unittest.TestCase):
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
        for width,height in ((1440,1000),(390,844),(320,740)):
            context=self.browser.new_context(viewport={'width':width,'height':height})
            page=context.new_page();page.set_default_timeout(5000);requests=[];errors=[]
            page.on('request',lambda r:requests.append((r.method,r.url)))
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.url)
            for role in self.data['roles']:
                page.get_by_label('查看身份',exact=True).select_option(role)
                expect(page.locator('main h1')).to_have_text(self.data['roles'][role])
                self.assert_layout(page,width,role+'-home')
                pages=[p for p in self.data['pages'] if p['role']==role and p.get('kind')!='admission-field']
                for module in pages:
                    with self.subTest(width=width,page=module['id']):
                        target='#/'+role+'/'+module['id']+('/edit' if role=='admission' else '/list')
                        page.locator('.module-card[href="'+target+'"]').click()
                        expect(page.locator('main h1')).to_have_text(module['title'])
                        if role!='admission':
                            page.get_by_role('link',name='查看详情',exact=True).click()
                            expect(page).to_have_url(__import__('re').compile('/detail$'))
                            page.locator('.edit-preview').click()
                        expect(page).to_have_url(__import__('re').compile('/edit$'))
                        self.assert_layout(page,width,module['id']+'-edit')
                        page.reload();expect(page.locator('main h1')).to_have_text(module['title'])
                        page.locator('#demo-save').click()
                        if role!='admission':
                            expect(page).to_have_url(__import__('re').compile('/list$'))
                            expect(page.locator('.record')).to_be_visible()
                        page.get_by_role('link',name='返回菜单',exact=True).click()
                        expect(page.locator('main h1')).to_have_text(self.data['roles'][role])
            self.assertEqual(errors,[])
            self.assertTrue(all(method=='GET' and url.startswith(self.url.rsplit('/ui-preview/',1)[0]) for method,url in requests),requests)
            context.close()
    def test_admission_conditions_one_shared_draft_history_and_reload(self):
        context=self.browser.new_context(viewport={'width':390,'height':844});page=context.new_page();page.goto(self.url+'#/admission/home')
        page.locator('[data-option="entity"]').select_option('SOLE_PROPRIETOR')
        self.assertEqual(page.get_by_role('link',name='其他受益人资料 ›',exact=True).count(),0)
        page.locator('[data-option="entity"]').select_option('ENTERPRISE')
        page.locator('[data-option="contact"]').select_option('SUPER')
        page.locator('[data-option="scene"]').select_option('both')
        page.locator('[data-option="ubos"]').select_option('2')
        page.locator('.module-card').filter(has_text='主体与门店').click()
        page.locator('.module-card').filter(has_text='其他受益人资料').click()
        page.locator('[data-path$=".ubo_id_doc_name"]').fill('示例甲')
        page.get_by_role('button',name='受益人 2',exact=True).click()
        page.locator('[data-path$=".ubo_id_doc_name"]').fill('示例乙')
        page.reload();self.assertEqual(page.locator('[data-path$=".ubo_id_doc_name"]').input_value(),'示例乙')
        page.get_by_role('button',name='受益人 1',exact=True).click()
        self.assertEqual(page.locator('[data-path$=".ubo_id_doc_name"]').input_value(),'示例甲')
        page.get_by_role('button',name='演示保存并返回',exact=True).click()
        self.assertTrue(page.url.endswith('/admission-start/edit'))
        page.go_back();self.assertIn('admission-beneficiary/edit',page.url)
        page.go_forward();self.assertIn('admission-start/edit',page.url)
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
            expect(page.locator('main h1')).to_have_text(self.data['roles']['merchant'])
            page.get_by_label('查看身份',exact=True).select_option('admission')
            expect(page.locator('main h1')).to_have_text(self.data['roles']['admission'])
            page.locator('.module-card').filter(has_text='主体与门店').click()
            expect(page.locator('main h1')).to_have_text('主体与门店')
            page.reload();expect(page.locator('main h1')).to_have_text('主体与门店')
            self.assertEqual(errors,[]);self.assertFalse(any(url.startswith(('http:','https:')) for url in requests))
            page.screenshot(path=str(self.out/'self-contained-file.png'),full_page=True)
            context.close()
    def test_empty_loading_error_expired_and_no_business_requests(self):
        context=self.browser.new_context(viewport={'width':320,'height':740});page=context.new_page();requests=[]
        page.on('request',lambda r:requests.append((r.method,r.url)))
        page.goto(self.url+'#/merchant/merchant-0-0-0/list')
        # Use a real generated module id rather than relying on fixture numbering.
        first=next(p for p in self.data['pages'] if p['role']=='merchant')
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
if __name__=='__main__':unittest.main()
