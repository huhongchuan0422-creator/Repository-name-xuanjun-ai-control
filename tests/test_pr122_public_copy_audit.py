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
            self.assertIn('<title>'+heading+' | 玄钧云汇</title>',page)
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
