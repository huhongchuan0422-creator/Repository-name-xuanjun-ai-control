import ast
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from scripts import pr122_site_hub_public_copy as copy
from scripts.pr122_site_hub_english import translate_fragment
ROOT=Path(__file__).resolve().parents[1]
class TableParser(HTMLParser):
    def __init__(self,text):
        super().__init__();self.tables=[];self.row=None;self.cell=None;self.links=[];self.regions=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='table':self.tables.append([])
        if tag=='tr':self.row=[]
        if tag in ('th','td'):self.cell=''
        if tag=='a':self.links.append(attrs['href'])
        if attrs.get('role')=='region':self.regions.append(attrs)
    def handle_data(self,data):
        if self.cell is not None:self.cell+=data
    def handle_endtag(self,tag):
        if tag in ('th','td'):self.row.append(self.cell);self.cell=None
        if tag=='tr':self.tables[-1].append(self.row);self.row=None
class CopyTests(unittest.TestCase):
    def rendered(self,route,en=False):return copy.public_page('<html><title>old</title><main></main></html>','ecosystem/'+route+'/index.html',en)
    def test_six_exact_thresholds_and_discounts(self):
        page=self.rendered('tiers');p=TableParser(page)
        self.assertEqual(p.tables[0][1:],[[f'≥ {n}点权益值',f'{d}折'] for n,d in ((2,9),(10,8),(20,7),(40,6),(80,5),(150,4))])
        self.assertIn('权益值门槛',page);self.assertNotIn('份',page);self.assertNotIn('玄钧权益',page)
        self.assertIn('最高一档',page);self.assertIn('各档不叠加',page)
    def test_eight_confirmed_dual_thresholds(self):
        page=self.rendered('profit-sharing');p=TableParser(page)
        self.assertEqual(p.tables[0][0],['原始开发定价','持有权益值','可共享净利润比例'])
        self.assertEqual(p.tables[0][1:],[[f'≥ {n*1000:,}元',f'≥ {n*10}点权益值',f'{n*10}%'] for n in range(1,9)])
        self.assertIn('两项条件共同满足的最高档',page)
        self.assertIn('不含第三方成本',page)
        self.assertNotIn('待确认',page)
        self.assertIn('开发折扣与专项抵扣不降低对应的原始开发定价',page)
        self.assertIn('不自动获得收益共享资格',page)
    def test_credit_rules_and_brand_are_preserved(self):
        for route in ('tiers','ledger','activities'):
            page=self.rendered(route)
            self.assertIn('90%',page);self.assertIn('50%',page)
            self.assertIn('第三方成本',page);self.assertIn('不可抵扣',page)
            self.assertIn('不能提现、转让或买卖',page)
        page=self.rendered('ledger')
        self.assertIn('500元',page);self.assertIn('不另附带500元',page)
        self.assertEqual(copy.NAME,'云汇生态权益')
    def test_english_links_and_values(self):
        for route in ('tiers','profit-sharing','ledger','activities'):
            page=self.rendered(route,True);p=TableParser(page)
            self.assertTrue(all(x.startswith('/en/ecosystem/') for x in p.links))
            self.assertNotRegex(page,r'[\u4e00-\u9fff]')
        p=TableParser(self.rendered('tiers',True))
        self.assertEqual(p.tables[0][1:],[['≥ '+str(n)+' rights-value points',str(d*10)+'% of quoted fee'] for n,d in ((2,9),(10,8),(20,7),(40,6),(80,5),(150,4))])
    def test_table_layout_scroll_and_accessible_name(self):
        p=TableParser(self.rendered('tiers'))
        self.assertEqual(len(p.regions),2)
        self.assertTrue(all(r['tabindex']=='0' and r['aria-label'] for r in p.regions))
        tree=ast.parse((ROOT/'scripts/pr122_site_hub_stage.py').read_text())
        css=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CSS' for t in n.targets))
        self.assertIn('.xj-hub .xj-table-scroll{width:100%;max-width:100%;overflow-x:auto}',css)
        self.assertIn('display:table;table-layout:fixed;width:100%;min-width:420px',css)
        self.assertNotIn('.xj-hub table{display:block',css)
    def test_customer_link_and_saas_disclosure_translate(self):
        customer=(ROOT/'demos/xuanjun-site-hub/customer/projects/index.html').read_text()
        self.assertIn('href="/custom-ai">了解定制服务',customer)
        translated=translate_fragment(customer)
        self.assertIn('href="/custom-ai"',translated)
        role=(ROOT/'demos/xuanjun-site-hub/visual/community-payment/index.html').read_text()
        self.assertIn('身份与报价服务未连接，交互暂未开放',role)
        self.assertIn('interaction is not open',translate_fragment(role))
    def test_marketplace_uses_service_neutral_labels_and_decimal_points(self):
        page=(ROOT/'demos/xuanjun-site-hub/marketplace/index.html').read_text()
        self.assertIn('服务费用模拟',page)
        self.assertIn('优惠前自营服务费（元）',page)
        self.assertIn('计算预计实付',page)
        self.assertIn('id="ecvUnits" type="number" min="0" step="any"',page)
        self.assertIn('本页模拟仅以人民币（CNY）计算',page)
        # The stage removes inline quote JS before translation, preserving the existing adapter.
        translated=translate_fragment(re.sub(r'<script>.*?</script>','',page,flags=re.S))
        self.assertIn('Service fee simulator',translated)
        self.assertIn('Current rights-value holdings (points)',translated)
        self.assertIn('calculates in CNY only',translated)
    def test_custom_service_cta_keeps_locale_and_demo_exclusions(self):
        source='<header><a href="/visual/">outside</a></header><main><a href="/custom-ai">custom</a><a href="/visual/community-local-e2e/index.html">demo</a><a href="/visual/community-payment/merchant-dashboard/">merchant</a><a href="/marketplace/">products</a><a href="/en/ecosystem/">already</a></main>'
        for locale in ('en/','zh-cn/'):
            page=copy.localize_hub_links(source,locale)
            self.assertIn('href="/'+locale+'custom-ai"',page)
            self.assertIn('href="/'+locale+'marketplace/"',page)
            self.assertIn('href="/visual/community-local-e2e/index.html"',page)
            self.assertIn('href="/visual/community-payment/merchant-dashboard/"',page)
            self.assertNotIn('/en/en/',page)
            self.assertEqual(copy.localize_hub_links(page,locale),page)
        self.assertEqual(copy.localize_hub_links(source,''),source)
    def test_legal_service_credit_has_two_distinct_caps(self):
        text=(ROOT/'demos/legal/service-package-rights.html').read_text()
        self.assertIn('普通合格自营费用抵扣上限90%',text)
        self.assertIn('先享适用等级折扣，再抵扣折后合格定制开发费的最多50%',text)
        self.assertIn('第三方采购、模型/资源成本及明确排除项不抵扣',text)
        self.assertNotIn('单笔合格费用抵扣上限90%',text)
    def test_legal_stage_threshold_is_valid_transaction_volume(self):
        text=(ROOT/'demos/legal/service-package-rights.html').read_text()
        self.assertIn('对应1亿元累计有效交易额门槛',text)
        self.assertNotIn('1亿元收入门槛',text)
    def test_wording_idempotent_and_never_renames_attributes(self):
        source='<p>云汇生态权益 权益值门槛</p><a href="/ECV/" id="ecvUnits">生态权益</a>'
        one=copy.wording(source)
        self.assertEqual(copy.wording(one),one)
        self.assertIn('href="/ECV/" id="ecvUnits"',one)
        self.assertIn('权益值门槛',one)
if __name__=='__main__':unittest.main()
