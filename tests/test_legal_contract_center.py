import hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('legal_builder',ROOT/'scripts/build_legal_previews.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
class LegalTests(unittest.TestCase):
    def setUp(self):self.registry=json.loads((ROOT/'docs/legal/registry.json').read_text())
    def test_complete_drafts_are_not_signable(self):
        self.assertEqual(len(self.registry['documents']),22);self.assertIs(self.registry['production_enabled'],False)
        for e in self.registry['documents']:
            self.assertFalse(e['signature_enabled']);self.assertEqual(e['status'],'INTERNAL_ONLY' if e['id']=='custom-sow' else 'DRAFT_NOT_FOR_SIGNATURE')
            raw=(ROOT/e['source']).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),e['source_sha256'])
            if e['status']=='DRAFT_NOT_FOR_SIGNATURE':
                self.assertIn('待审核草案',raw.decode());self.assertIn('【',raw.decode())
    def test_community_five_and_business_invariants(self):
        ids={e['id'] for e in self.registry['documents']};self.assertTrue({'merchant-onboarding','community-split','community-service','privacy','refund-responsibility'}<=ids)
        def text(key):return (ROOT/'docs/legal/templates'/f'{key}.md').read_text()
        self.assertIn('不经平台自有账户归集',text('community-split'))
        self.assertIn('不得笼统',text('service-package-rights'))
        self.assertIn('不再派生500元',text('service-package-rights'))
        self.assertIn('允许同人多账号',text('platform-terms'))
        self.assertIn('不复用客户秘密',text('developer-marketplace'))
        self.assertIn('不默认获得国内生产个人信息',text('privacy'))
    def test_build_is_deterministic_and_navigation_complete(self):
        builder.build(ROOT);first={p.name:p.read_bytes() for p in (ROOT/'demos/legal').glob('*.html')};builder.build(ROOT)
        self.assertEqual(first,{p.name:p.read_bytes() for p in (ROOT/'demos/legal').glob('*.html')})
        index=first['index.html'].decode()
        for e in self.registry['documents']:
            if e['status']=='INTERNAL_ONLY':
                self.assertNotIn(e['id']+'.html',index)
                self.assertIn('不供客户签署',first[e['id']+'.html'].decode())
            else:
                self.assertIn(e['id']+'.html',index)
                self.assertIn('不开放真实',first[e['id']+'.html'].decode())
    def test_modified_or_activated_templates_refused(self):
        import shutil
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);shutil.copytree(ROOT/'docs/legal',r/'docs/legal')
            (r/self.registry['documents'][0]['source']).write_text('changed')
            with self.assertRaisesRegex(ValueError,'TEMPLATE_HASH_MISMATCH'):builder.build(r)
            registry=dict(self.registry);registry['production_enabled']=True;(r/'docs/legal/registry.json').write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError,'DRAFT_ONLY_REQUIRED'):builder.build(r)
    def test_html_escapes_untrusted_contract_text(self):
        import shutil
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);shutil.copytree(ROOT/'docs/legal',r/'docs/legal');v=json.loads((r/'docs/legal/registry.json').read_text());e=v['documents'][0]
            payload='<script>alert(1)</script>';p=r/e['source'];p.write_text(payload);e['source_sha256']=hashlib.sha256(payload.encode()).hexdigest();(r/'docs/legal/registry.json').write_text(json.dumps(v))
            builder.build(r);page=(r/e['preview']).read_text();self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)
    def test_role_page_legal_links_resolve_in_candidate_tree(self):
        from html.parser import HTMLParser
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.links=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if tag=='a' and '/legal/' in a.get('href',''):self.links.append(a['href'])
        pages=list((ROOT/'demos/community-local-e2e').glob('*.html'))+[ROOT/'demos/visual/community-payment/index.html']
        self.assertGreaterEqual(len(pages),7)
        for p in pages:
            parser=Links();parser.feed(p.read_text())
            if 'data-legal-drafts=' not in p.read_text():continue
            self.assertTrue(parser.links,p.name)
            for href in parser.links:
                target=(p.parent/href).resolve();self.assertTrue(target.is_relative_to(ROOT/'demos/legal'));self.assertTrue(target.is_file(),href)
if __name__=='__main__':unittest.main()
