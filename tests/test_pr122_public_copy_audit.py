import json,re,unittest
from pathlib import Path
from scripts.pr122_site_hub_public_copy import reviewed_page_copy
from scripts.pr122_site_hub_experience import home
ROOT=Path(__file__).resolve().parents[1]
PAGES=json.loads((ROOT/'tests/fixtures/pr122-public-copy-evidence.json').read_text())['pages']
class ReviewedCopyTests(unittest.TestCase):
    def page(self,path):return reviewed_page_copy(PAGES[path]['html'],path)
    def test_english_grammar_and_about_parity(self):
        self.assertIn('concept demonstrations or internal-validation examples',self.page('en/guides.html'))
        self.assertNotIn('Planned or subject to',self.page('en/terms.html'))
        self.assertIn('Important actions retain confirmation checkpoints',self.page('en/about.html'))
    def test_labs_has_public_rules_and_confirmed_units(self):
        for p in ['labs.html','en/labs.html']:
            result=self.page(p)
            self.assertNotIn('本次官网任务',result);self.assertNotIn('this website task',result)
            self.assertNotIn('2,000万份',result);self.assertNotIn('20 million units',result)
        self.assertIn('2,000万点权益值',self.page('labs.html'))
        self.assertIn('Rights record verified contributions',self.page('en/labs.html'))
        self.assertNotIn('values are non-transferable',self.page('en/labs.html'))
    def test_six_scenario_inputs_and_outputs_preserve_specificity(self):
        for path in PAGES:
            if not path.startswith('en/solutions/'):continue
            page=self.page(path)
            self.assertNotIn('Business rules, authorized data and acceptance criteria.',page)
            self.assertNotIn('A defined workflow, output records and an acceptance result.',page)
        self.assertIn('Inquiry content',self.page('en/solutions/customer-service-sales.html'))
        self.assertIn('Chapter versions, review records and exported content',self.page('en/solutions/creative-digital-content.html'))
    def test_empty_sections_removed_but_real_guides_preserved(self):
        for path in PAGES:
            if '/solutions/' in path or path.startswith('solutions/'):
                result=self.page(path)
                self.assertNotRegex(result,r'<h2>(?:创作流程详情|Creative workflows)</h2><div class="related">\s*</div>')
        for prefix in ('','en/'):
            p=prefix+'solutions/creative-digital-content.html'
            before=PAGES[p]['html'];after=self.page(p)
            self.assertEqual(re.findall('href="([^"]+)"',before),re.findall('href="([^"]+)"',after))
        self.assertNotIn('<h2>审核与编辑指南</h2><div class="related"></div>',self.page('capabilities/content-planning-review.html'))
    def test_chinese_category_title_and_breadcrumb_match_heading(self):
        for path in PAGES:
            if not path.startswith('capabilities/') or path.endswith('content-planning-review.html'):continue
            page=self.page(path);heading=re.search('<h1>(.*?)</h1>',page)[1]
            self.assertIn('<title>'+heading+' | 玄钧AI新</title>',page)
            self.assertIn('<span aria-current="page">'+heading+'</span>',page)
    def test_fee_status_not_permission_status(self):
        page=self.page('capabilities/content-planning-review.html')
        self.assertIn('<dt>费用状态</dt><dd>待核定</dd>',page)
        self.assertIn('平台发布权限按实际获批范围另行确认。</p>',page)
        self.assertEqual(page.count('平台发布权限按实际获批范围另行确认'),1)
        self.assertIn('To be confirmed from scope',self.page('en/capabilities/content-planning-review.html'))
    def test_home_labels_describe_actual_existing_destinations(self):
        for locale in ('','en/'):
            source='<main><section class="hero"><h1>Old</h1><p class="lead">Old</p><div class="actions"></div></section></main>'
            generated=home(source,locale);result=reviewed_page_copy(generated,locale+'index.html')
            self.assertNotIn('成熟项目案例',result);self.assertNotIn('Completed project cases',result)
            self.assertNotIn('产品发展路线',result);self.assertNotIn('Product roadmap',result)
            self.assertIn('href="/'+locale+'visual/catalog/"',result)
            self.assertIn('href="/'+locale+'customer/projects/"',result)
    def test_governance_avoids_absolute_immutability_claim(self):
        self.assertEqual(reviewed_page_copy('<p>留下不可篡改审计</p>','ecosystem/governance/index.html'),'<p>保留可核验、可追溯的审计记录</p>')
        self.assertEqual(reviewed_page_copy('<p>tamper-evident audit records</p>','en/ecosystem/governance/index.html'),'<p>verifiable, traceable audit records</p>')
    def test_aliases_idempotence_and_unrelated_pages(self):
        for path in PAGES:
            first=self.page(path)
            self.assertEqual(reviewed_page_copy(first,path),first)
            self.assertEqual(reviewed_page_copy(PAGES[path]['html'],path[:-5]+'/index.html'),first)
        sample='<p>本次官网任务不调整权益总量、分池、门槛或释放规则；规则设计不等于已发放。</p><script>const x="unchanged";</script>'
        self.assertEqual(reviewed_page_copy(sample,'unrelated/index.html'),sample)
        script='<script>const text="Yunhui Ecosystem Rights records verified contributions";</script>'
        self.assertEqual(reviewed_page_copy(script,'en/labs.html'),script)
if __name__=='__main__':unittest.main()

class BrandProjectionTests(unittest.TestCase):
    def test_exact_owner_brand_and_english_case_aliases(self):
        from scripts.pr122_site_hub_public_copy import brand_text
        self.assertEqual(brand_text('玄钧云汇 / Xuanjun Yunhui / XUANJUN YUNHUI / XuanJun Yunhui'),' / '.join(['玄钧AI新']*4))
    def test_technical_ids_and_separate_business_brand_unchanged(self):
        from scripts.pr122_site_hub_public_copy import brand_text
        value='云汇生态权益 Yunhui Ecosystem Rights /yunhui.css data-yunhui-v1 xuanjun-customer wenwenwenyiyiyi.work 玄钧AI实验室'
        self.assertEqual(brand_text(value),value)
    def test_projection_is_idempotent(self):
        from scripts.pr122_site_hub_public_copy import brand_text
        value=brand_text('玄钧云汇 XUANJUN YUNHUI')
        self.assertEqual(brand_text(value),value)
    def test_old_and_new_chinese_fragments_translate_to_same_brand(self):
        from scripts.pr122_site_hub_english import translate_fragment
        old='<title>客户项目与验收 | 玄钧云汇</title><header>玄钧云汇</header>'
        new=translate_fragment(old.replace('玄钧云汇','玄钧AI新'))
        self.assertEqual(translate_fragment(old),new)
        self.assertIn('玄钧AI新',new)
    def test_unknown_chinese_copy_still_rejected(self):
        from scripts.pr122_site_hub_english import translate_fragment
        with self.assertRaisesRegex(ValueError,'MISSING_ENGLISH_TRANSLATION'):
            translate_fragment('<p>从未审核的未知文案</p>')
    def test_frozen_page_input_remains_old_but_new_projection_is_current(self):
        from scripts.pr122_site_hub_public_copy import reviewed_page_copy
        raw=(ROOT/'tests/fixtures/pr122-public-copy-evidence.json').read_bytes()
        self.assertIn('玄钧云汇'.encode(),raw)
        for name,item in PAGES.items():
            rendered=reviewed_page_copy(item['html'],name)
            self.assertNotRegex(rendered,r'玄钧云汇|(?i:Xuanjun Yunhui)')
        self.assertEqual((ROOT/'tests/fixtures/pr122-public-copy-evidence.json').read_bytes(),raw)
    def test_public_asset_types_and_binary_are_preserved(self):
        import tempfile
        from scripts.pr122_site_hub_public_copy import project_public_brand
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for suffix in ('.html','.js','.json','.xml','.svg','.txt','.css','.mjs','.webmanifest'):
                (root/('public'+suffix)).write_text('玄钧云汇 XUANJUN YUNHUI')
            (root/'image.png').write_bytes(b'\x89PNG\x00historical')
            report=project_public_brand(root)
            self.assertEqual(len(report['changed_public_files']),9)
            self.assertFalse(report['production_approved'])
            for file in root.iterdir():
                if file.suffix!='.png':self.assertEqual(file.read_text(),'玄钧AI新 玄钧AI新')
            self.assertEqual((root/'image.png').read_bytes(),b'\x89PNG\x00historical')
            self.assertEqual(project_public_brand(root)['changed_public_files'],[])
    def test_stage_projection_precedes_csp_and_manifest(self):
        import ast
        tree=ast.parse((ROOT/'scripts/pr122_site_hub_stage.py').read_text())
        calls={}
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):calls.setdefault(node.func.id,[]).append(node.lineno)
        self.assertLess(calls['project_public_brand'][0],calls['write_csp_metadata'][0])
        text=(ROOT/'scripts/pr122_site_hub_stage.py').read_text()
        self.assertLess(text.index('brand_projection=project_public_brand(public)'),text.index('    manifest={'))
    def test_customer_shell_uses_current_brand(self):
        page=(ROOT/'deploy/pr122-customer-center/ui/index.html').read_text()
        self.assertEqual(page.count('玄钧AI新'),3)
        self.assertNotIn('玄钧云汇',page)
    def test_current_demos_and_templates_have_no_old_brand(self):
        for folder in ('demos','showcase','docs/legal/templates'):
            for path in (ROOT/folder).rglob('*'):
                if path.is_file() and path.suffix in ('.html','.md','.json','.js','.mjs'):
                    self.assertNotRegex(path.read_text(),r'玄钧云汇|(?i:Xuanjun Yunhui)',str(path))
    def test_projection_rejects_symlinks(self):
        import tempfile
        from scripts.pr122_site_hub_public_copy import project_public_brand
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'target.html').write_text('玄钧云汇');(root/'alias.html').symlink_to(root/'target.html')
            with self.assertRaisesRegex(ValueError,'PUBLIC_BRAND_SYMLINK'):project_public_brand(root)
    def test_actual_fixture_stage_has_no_legacy_brand_and_exact_final_hashes(self):
        import tempfile,hashlib,html
        from scripts.pr122_site_hub_stage import build
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'stage';build(ROOT,None,out,ROOT/'tests/fixtures/pr122-site-shell',derive_navigation=True)
            manifest=json.loads((out/'MANIFEST.json').read_text())
            self.assertFalse(manifest['production_approved'])
            for name,digest in manifest['files'].items():
                raw=(out/'public'/name).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
                try:text=html.unescape(raw.decode('utf-8'))
                except UnicodeError:continue
                self.assertNotRegex(text,r'玄钧云汇|(?i:Xuanjun Yunhui)',name)
            for row in manifest['navigation_derivation']['files']:
                raw=(out/'public'/row['path']).read_bytes()
                self.assertEqual(len(raw),row['size']);self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
    def test_dynamic_showcase_projects_inherited_brand_without_changing_catalog(self):
        import tempfile,copy
        from scripts.pr122_showcase import render
        from tests.test_pr122_showcase import project,approvals,s
        items=[project()];catalog=s.compile_catalog(items,approvals(items));before=copy.deepcopy(catalog)
        shell={'zh':{'header':'<header>玄钧云汇</header>','footer':'<footer>玄钧云汇</footer>'},'en':{'header':'<header>XUANJUN YUNHUI</header>','footer':'<footer>Xuanjun Yunhui</footer>'}}
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'public';render(catalog,out,shell=shell)
            for page in out.rglob('*.html'):
                text=page.read_text();self.assertIn('玄钧AI新',text);self.assertNotRegex(text,r'玄钧云汇|(?i:Xuanjun Yunhui)')
        self.assertEqual(catalog,before)
