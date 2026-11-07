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

if __name__=='__main__':unittest.main()
