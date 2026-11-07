import json
import unittest
from pathlib import Path
from test_community_license_layout import run
from scripts.community_license_layout import normalize_layout, extract_license_fields

class StopBoundaryTests(unittest.TestCase):
    def address(self, items, expected, turn=0):
        result=run(items,turn)
        self.assertEqual(result['fields']['registered_address']['value'], expected)
        self.assertNotIn('business_scope',result['fields'])
        self.assertTrue(result['requires_human_confirmation'])
    def test_actual_model_rows(self):
        rows=json.loads((Path(__file__).parent/'fixtures/license_address_stop_rows.json').read_text())
        self.assertEqual(extract_license_fields(rows,(0,))['fields']['registered_address']['value'],'上海市浦东新区合成路一号')
    def test_unspaced_stops_all_coordinate_rotations_and_order(self):
        rows=[('住所：合成市甲路',0,0,250,20),('经营范围软件开发',0,35,250,20),('成立日期2020年01月01日',0,70,300,20),('营业期限长期',0,105,220,20),('测试水印',0,140,100,20)]
        for turn in range(4):self.address(list(reversed(rows)), '合成市甲路',turn)
    def test_multiline_preserved(self):
        self.address([('住所',0,0,70,20),('合成市经营范围路',100,0,200,20),('一号楼成立日期街二层',100,30,220,20),('经营范围软件开发',0,65,200,20),('营业期限长期',0,100,200,20)],'合成市经营范围路一号楼成立日期街二层')
    def test_single_keyword_prefix_is_not_a_barrier(self):
        self.address([('住所：合成市',0,0,180,20),('经营范围路一号',0,30,200,20)],'合成市经营范围路一号')
    def test_two_keyword_prefix_address_lines_are_preserved(self):
        self.address([('住所：合成市',0,0,180,20),('经营范围路一号',0,30,200,20),('成立日期街二层',0,60,220,20)],'合成市经营范围路一号成立日期街二层')
    def test_inline_keyword_is_not_a_barrier(self):
        self.address([('住所：经营范围路成立日期街一号',0,0,400,20)],'经营范围路成立日期街一号')
    def test_other_column_does_not_corroborate(self):
        self.address([('住所',0,0,60,20),('甲市',80,0,80,20),('经营范围路一号',80,30,200,20),('营业期限长期',400,65,150,20)],'甲市经营范围路一号')
    def test_split_stop_label_and_same_line(self):
        self.address([('住所',0,0,60,20),('甲市',80,0,80,20),('经营',0,35,40,20),('范围',42,35,40,20),('软件开发',100,35,100,20)],'甲市')
        self.address([('住所：甲市 经营范围：软件开发',0,0,400,20)],'甲市')
    def test_missing_geometry_keeps_inline(self):
        r=extract_license_fields(normalize_layout({'txts':['住所：合成市','经营范围软件开发','营业期限长期'],'scores':[.99]*3}))
        self.assertEqual(r['fields']['registered_address']['value'],'合成市')
    def test_noise_is_not_a_prefix_match(self):
        self.address([('住所：甲市',0,0,180,20),('合成经营范围路',0,30,180,20),('合成成立日期街一号',0,60,200,20)],'甲市合成经营范围路合成成立日期街一号')


class TargetBoundaryTests(unittest.TestCase):
    def form(self):
        return [('名称合成科技有限公司',0,0,300,20),
                ('法定代表人测试甲',0,35,240,20),
                ('统一社会信用代码91310115MA12345678',0,70,500,20),
                ('住所合成市甲路一号',0,105,300,20),
                ('经营范围软件开发',0,140,300,20),
                ('成立日期2020年01月01日',0,175,300,20)]
    def test_actual_model_rows_no_separator(self):
        frames=json.loads((Path(__file__).parent/'fixtures/license_target_no_separator_rows.json').read_text())
        for name, rows in frames.items():
            if name not in ('png','scanned'):continue
            fields=extract_license_fields(rows,(0,))['fields']
            self.assertEqual(fields['company_name']['value'],'测试合成科技有限公司',name)
            self.assertEqual(fields['registered_address']['value'],'上海市浦东新区合成路一号',name)
            self.assertEqual(fields['legal_representative']['value'],'测试甲',name)
    def test_all_four_targets_no_separator(self):
        for turn in range(4):
            r=run(list(reversed(self.form())),turn)
            self.assertEqual({k:f['value'] for k,f in r['fields'].items()},
                dict(company_name='合成科技有限公司',legal_representative='测试甲',
                     credit_code='91310115MA12345678',registered_address='合成市甲路一号'))
            self.assertTrue(r['requires_human_confirmation'])
            self.assertFalse(r['authenticity_verified'])
    def test_aliases_and_two_strict_fields(self):
        for label in ('名称','企业名称','个体工商户名称'):
            items=[(label+'合成店',0,0,300,20),('法定代表人：甲',0,35,240,20),('住所：乙市一号',0,70,300,20)]
            self.assertEqual(run(items)['fields']['company_name']['value'],'合成店')
    def test_two_prefixes_without_independent_structure_do_not_enable(self):
        items=[('名称设计有限公司',0,0,300,20),('住所路一号',0,35,300,20)]
        self.assertEqual(run(items)['fields'],{})
    def test_explicit_address_prefix_protection_all_turns(self):
        items=self.form();items[0]=('名称：正式名称',0,0,300,20)
        items[3]=('住所：合成市',0,105,300,20)
        items[4]=('名称路一号',0,140,300,20)
        items[5]=('住所街二层',0,175,300,20)
        items.extend([('成立日期：2020年01月01日',0,210,300,20),('营业期限长期',0,245,200,20)])
        for turn in range(4):
            fields=run(list(reversed(items)),turn)['fields']
            self.assertEqual(fields['company_name']['value'],'正式名称')
            self.assertEqual(fields['registered_address']['value'],'合成市名称路一号住所街二层')
    def test_single_prefix_not_a_form(self):
        for text in ('名称设计有限公司','住所路一号','地址科技公司','负责人路二号'):
            self.assertEqual(run([(text,0,0,300,20)])['fields'],{})
    def test_no_geometry_not_relaxed(self):
        rows=normalize_layout({'txts':[x[0] for x in self.form()],'scores':[.99]*6})
        self.assertNotIn('company_name',extract_license_fields(rows)['fields'])
    def test_invalid_code_not_form_evidence(self):
        items=self.form();items[2]=('统一社会信用代码INVALID',0,70,500,20)
        self.assertNotIn('company_name',run(items)['fields'])
    def test_other_column_not_form_evidence(self):
        items=self.form();items[2]=(items[2][0],800,70,500,20)
        self.assertNotIn('company_name',run(items)['fields'])
    def test_internal_target_words_preserved(self):
        items=self.form();items[0]=('名称住所经营者名称科技有限公司',0,0,500,20)
        self.assertEqual(run(items)['fields']['company_name']['value'],'住所经营者名称科技有限公司')
    def test_explicit_name_value_prefix_not_stripped(self):
        items=self.form();items[0]=('名称',0,-30,80,20)
        items.append(('名称设计有限公司',0,0,300,20))
        self.assertEqual(run(items)['fields']['company_name']['value'],'名称设计有限公司')
    def test_explicit_multiline_address_prefix_not_stripped(self):
        items=self.form();items[3]=('住所：合成市',0,105,300,20)
        items[4]=('名称路一号',0,140,300,20)
        items[5]=('住所街二层',0,175,300,20)
        items.extend([('成立日期：2020年01月01日',0,210,300,20),('营业期限长期',0,245,200,20)])
        self.assertEqual(run(items)['fields']['registered_address']['value'],'合成市名称路一号住所街二层')
    def test_recovered_address_owns_keyword_continuations(self):
        items=self.form();items[0]=('名称：正式公司',0,0,300,20)
        items[3]=('住所合成市',0,105,300,20)
        items[4]=('名称路一号',0,140,300,20)
        items[5]=('住所街二层',0,175,300,20)
        items.append(('成立日期：2020年01月01日',0,210,300,20))
        for turn in range(4):
            fields=run(list(reversed(items)),turn)['fields']
            self.assertEqual(fields['company_name']['value'],'正式公司')
            self.assertEqual(fields['registered_address']['value'],'合成市名称路一号住所街二层')
    def test_established_name_wins_over_unspaced_keyword_rows(self):
        for y in (20,140):
            items=self.form();items[0]=('名称：正式公司',0,-15,300,20)
            items.append(('名称设计有限公司',0,y,300,20))
            for turn in range(4):
                fields=run(list(reversed(items)),turn)['fields']
                self.assertEqual(fields['company_name']['value'],'正式公司')
    def test_explicit_name_value_before_address_keeps_prefix(self):
        items=[('名称',0,0,80,20),('名称设计有限公司',0,30,300,20),
               ('法定代表人：甲',0,65,240,20),('统一社会信用代码91310115MA12345678',0,100,500,20),
               ('住所合成市',0,135,300,20),('成立日期：2020年01月01日',0,170,300,20)]
        for turn in range(4):
            fields=run(list(reversed(items)),turn)['fields']
            self.assertEqual(fields['company_name']['value'],'名称设计有限公司')
            self.assertEqual(fields['registered_address']['value'],'合成市')
    def test_actual_target_prefix_model_frames(self):
        frames=json.loads((Path(__file__).parent/'fixtures/license_target_no_separator_rows.json').read_text())['target_prefix_scanned_frames']
        rows=frames[0]
        exact=extract_license_fields(rows,(0,))['fields']
        self.assertEqual(exact['registered_address']['value'],'合成市名称路一号住所街二层')
        self.assertEqual(exact['company_name']['value'],'测试合成科技有限公司')
        for turn in range(4):
            items=[]
            for n in rows:
                xs=[p[0] for p in n['box']];ys=[p[1] for p in n['box']]
                items.append((n['text'],min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)))
            fields=run(list(reversed(items)),turn)['fields']
            self.assertEqual(fields['company_name']['value'],'测试合成科技有限公司')
            self.assertEqual(fields['registered_address']['value'],'合成市名称路一号住所街二层')
            self.assertEqual(fields['credit_code']['value'],'91310115MA12345678')
    def test_dash_credit_label_is_contextual_and_does_not_edit_value(self):
        for dash in ('—','–','－','-'):
            items=self.form();items[2]=('统'+dash+'社会信用代码91310115MA12345678',0,70,500,20)
            fields=run(items)['fields']
            self.assertEqual(fields['company_name']['value'],'合成科技有限公司')
            self.assertEqual(fields['credit_code']['value'],'91310115MA12345678')
            self.assertNotIn('credit_code',run([items[2]])['fields'])
    def test_unrelated_or_invalid_credit_prefix_not_used(self):
        for text in ('旧社会信用代码91310115MA12345678','原社会信用代码91310115MA12345678','备注统—社会信用代码91310115MA12345678','统—社会信用代码INVALID'):
            items=self.form();items[2]=(text,0,70,500,20)
            self.assertNotIn('company_name',run(items)['fields'])
            self.assertNotIn('credit_code',run(items)['fields'])
    def test_noisy_leading_text_not_label(self):
        items=self.form();items[0]=('合成名称科技有限公司',0,0,400,20)
        self.assertNotIn('company_name',run(items)['fields'])

if __name__=='__main__':unittest.main()

