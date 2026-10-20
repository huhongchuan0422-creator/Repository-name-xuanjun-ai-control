import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest

from scripts.pr122_site_hub_stage import build, icp_footer, ICP_NUMBER, ICP_URL
from scripts.pr122_site_hub_public_copy import wording
from scripts.pr122_site_hub_preflight import Page
from scripts.pr122_site_hub_test_server import serve

ROOT=Path(__file__).resolve().parents[1]

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.stage=Path(cls.temp.name)/'stage'
        build(ROOT,None,cls.stage,ROOT/'tests/fixtures/pr122-site-shell')
        cls.public=cls.stage/'public'
        cls.server=serve(cls.stage)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.thread.join();cls.server.server_close();cls.temp.cleanup()
    def request(self,path,body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        data=json.dumps(body) if body is not None else None
        values={'Cookie':getattr(self,'cookie','')}
        if body is not None:values.update({'Content-Type':'application/json','Origin':'http://127.0.0.1:'+str(self.server.server_port)})
        values.update(headers or {})
        c.request('POST' if body is not None else 'GET',path,data,values)
        r=c.getresponse()
        if r.getheader('Set-Cookie'):self.cookie=r.getheader('Set-Cookie').split(';',1)[0]
        result=(r.status,r.getheader('Content-Security-Policy'),r.read());c.close();return result
    def test_42_localized_pages_have_original_navigation_and_no_inline_attributes(self):
        pages=list((ROOT/'demos/xuanjun-site-hub').rglob('*.html'))
        pages=[p.relative_to(ROOT/'demos/xuanjun-site-hub') for p in pages if p.parent.name!='xuanjun-site-hub' and p.parent.name!='merchant-dashboard']
        self.assertEqual(len(pages),14)
        for locale in ('','zh-cn/','en/'):
            for p in pages:
                text=(self.public/locale/p).read_text()
                self.assertIn('id="primary-nav"',text)
                self.assertEqual(text.count('class="nav-group"'),4)
                self.assertNotRegex(text,r'\s(?:style|onclick)=')
                self.assertNotIn('<script>',text)
                main=re.search(r'<main\b.*?</main>',text,re.S)[0]
                if locale=='en/':self.assertNotRegex(re.sub(r'<[^>]*>','',main),r'[\u4e00-\u9fff]')
                parser=Page();parser.feed(main)
                for tag,attr,ref in parser.refs:
                    if not ref.startswith('/'):continue
                    path=ref.split('?',1)[0].split('#',1)[0]
                    target=self.public/path.lstrip('/')
                    self.assertTrue(target.is_file() or (target/'index.html').is_file(),ref)
    def test_demo_resources_and_fixed_returns_are_mapped(self):
        for name in ('index.html','merchant.html','platform.html','community.html','beneficiary.html','saas-panel.html'):
            text=(self.public/'visual/community-local-e2e'/name).read_text();p=Page();p.feed(text)
            for tag,attr,ref in p.refs:
                if attr=='src' and ref.startswith('/'):
                    self.assertTrue((self.public/ref.lstrip('/')).is_file(),ref)
                self.assertNotIn('../visual/',ref)
                self.assertNotIn('../legal/',ref)
    def test_official_footer_retains_exact_owner_icp_in_all_locales(self):
        pages=[p for p in self.public.rglob('*.html') if 'id="primary-nav"' in p.read_text()]
        self.assertEqual(len(pages),45)
        for p in pages:
            text=p.read_text();footer=re.search(r'<footer\b.*?</footer>',text,re.S)[0]
            self.assertEqual(footer.count(ICP_NUMBER),1,str(p))
            self.assertIn('href="'+ICP_URL+'"',footer)
            self.assertIn('rel="noopener noreferrer"',footer)
            self.assertEqual(icp_footer(text),text)
        with self.assertRaisesRegex(ValueError,'FOOTER_MISSING'):icp_footer('<html><body></body></html>')
    def test_quote_ui_and_csp_have_no_unsafe_inline(self):
        policy=json.loads((self.stage/'release-metadata/inline-csp.json').read_text())['policy']
        self.assertNotIn('unsafe-inline',policy)
        self.assertTrue((self.public/'assets/ecv-quote-ui.js').is_file())
        self.assertIn('value="ordinary"',(self.public/'marketplace/index.html').read_text())
    def test_existing_home_body_title_and_links_preserved_except_brand(self):
        for locale in ('','en/','zh-cn/'):
            old=(ROOT/'tests/fixtures/pr122-site-shell'/locale/'index.html').read_text()
            new=(self.public/locale/'index.html').read_text()
            a=Page();a.feed(old);b=Page();b.feed(new)
            self.assertLessEqual(set(a.refs),set(b.refs))
            self.assertEqual(re.search(r'<title>.*?</title>',old)[0].replace('玄钧云汇','玄钧AI新').replace('Xuanjun Yunhui','玄钧AI新'),re.search(r'<title>.*?</title>',new)[0])
            # The Owner authorized a new home hierarchy and hero copy. Original
            # business detail sections and links remain available in a disclosure.
            oldmain=re.search(r'<main>.*?</main>',old,re.S)[0]
            oldhero=re.search(r'<section class="hero">.*?</section>',oldmain,re.S)[0]
            self.assertIn(wording(oldmain.split(oldhero,1)[1][:-7],locale=='en/'),new)
            for key in ('products','visual','work','ecosystem','delivery'):
                self.assertIn('id="discover-'+key+'"',new)
            self.assertIn('class="xj-more"',new)

    def test_ecosystem_navigation_is_not_in_the_module_market(self):
        for locale in ('','en/','zh-cn/'):
            text=(self.public/locale/'index.html').read_text()
            market=re.search(r'<div class="nav-group"><a href="/'+locale+r'capabilities">.*?</div></div>',text,re.S)[0]
            ecosystem=re.search(r'<div class="nav-group"><a href="/'+locale+r'labs">.*?</div></div>',text,re.S)[0]
            self.assertNotIn('/ecosystem/',market)
            self.assertIn('/'+locale+'ecosystem/',ecosystem)
            self.assertIn('/'+locale+'ecosystem/governance/',ecosystem)

    def test_public_benefits_tables_and_no_internal_pricing(self):
        for locale in ('','zh-cn/','en/'):
            home=(self.public/locale/'index.html').read_text()
            self.assertIn('id="discover-benefits"',home)
            self.assertNotIn('href="/showcase/',home)
            self.assertIn('90%',home)
            self.assertIn('50%',home)
            for route in ('tiers','profit-sharing'):
                text=(self.public/locale/'ecosystem'/route/'index.html').read_text()
                self.assertEqual(text.count('<tbody>'),2 if route=='tiers' else 1)
                self.assertEqual(len(re.findall(r'<td>',text)),21 if route=='tiers' else 24)
            for page in (self.public/locale/'ecosystem').rglob('*.html'):
                main=re.search(r'<main\b.*?</main>',page.read_text(),re.S)[0]
                self.assertNotRegex(main,r'成本.?[×*].?3|cost.?[×*].?3|\bECV\b|\bEVC\b')
            market=(self.public/locale/'marketplace/index.html').read_text()
            self.assertNotIn('id="directCost"',market)
            self.assertIn('id="ecvUnits"',market)  # stable internal field, public name changes only

    def test_legacy_name_keeps_script_bytes_and_removes_stale_total(self):
        from scripts.pr122_site_hub_public_copy import legacy_public_wording
        source='<p>生态权益值规则设计总量为1000万</p><script>const ECV="ECV";</script>'
        new=legacy_public_wording(source)
        self.assertIn('<script>const ECV="ECV";</script>',new)
        self.assertIn('云汇生态权益',new)
        self.assertEqual(wording('<script src="/assets/ecv-quote.js"></script>',True),'<script src="/assets/ecv-quote.js"></script>')
        for p in self.public.rglob('*.html'):
            if 'id="primary-nav"' in p.read_text():
                self.assertNotIn('生态权益值',p.read_text())

    def test_community_project_belongs_to_delivery(self):
        for locale in ('','zh-cn/','en/'):
            text=(self.public/locale/'index.html').read_text()
            solution=re.search(r'<div class="nav-group"><a href="/'+locale+r'solutions">.*?</div></div>',text,re.S)[0]
            delivery=re.search(r'<div class="nav-group"><a href="/'+locale+r'custom-ai">.*?</div></div>',text,re.S)[0]
            self.assertNotIn('community-payment',solution)
            self.assertIn('/'+locale+'visual/community-payment/',delivery)

    def test_merchant_script_is_preserved_and_externalized(self):
        page=self.public/'visual/community-payment/merchant-dashboard/index.html'
        text=page.read_text()
        self.assertNotIn('ecv-quote-ui.js',text)
        self.assertNotIn('<script>',text)
        self.assertNotRegex(text,r'\sstyle=')
        name=re.search(r'src="(/assets/hub-script-[a-f0-9]+.js)"',text)[1]
        script=(self.public/name.lstrip('/')).read_text()
        self.assertIn('selectMerchant()',script)
        self.assertIn('DEMO-G101',script)
    def test_http_negative_and_real_simulated_order_flow(self):
        self.assertEqual(self.request('/missing-site-hub-page')[0],404)
        self.assertEqual(self.request('/.env')[0],403)
        self.assertEqual(self.request('/',headers={'Host':'external.example'})[0],403)
        self.assertEqual(self.request('/_preview/community-api/session')[0],200)
        scope={'tenant_id':'tenant1','merchant_id':'merchant1','store_id':'store1','reference':'integration_test'}
        status,_,body=self.request('/_preview/community-api/orders',{**scope,'amount_minor':120})
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['state'],'PENDING')
        status,_,body=self.request('/_preview/community-api/orders/simulate',{**scope,'amount_minor':120,'event_id':'sim_1','target':'SUCCESS','transaction_id':'sim_tx_1'})
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['state'],'SUCCESS')
        status,_,body=self.request('/_preview/community-api/admin/profile',{'anything':'invalid'})
        self.assertNotEqual(status,200)
        self.assertEqual(self.request('/_preview/community-api/orders',scope,{'Content-Type':'application/json','Origin':'https://external.example'})[0],403)

if __name__=='__main__':unittest.main()
