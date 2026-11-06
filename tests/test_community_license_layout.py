import copy
import unittest
from scripts.community_license_layout import normalize_layout,extract_license_fields


def run(items, turn=0):
    texts=[];boxes=[]
    for text,x,y,w,h in items:
        texts.append(text); box=[]
        for px,py in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]:
            for unused in range(turn):px,py=-py,px
            box.append([px,py])
        boxes.append(box)
    return extract_license_fields(normalize_layout({'txts':texts,'scores':[.99]*len(texts),'boxes':boxes}))

class LayoutTests(unittest.TestCase):
    def test_labels_never_become_values(self):
        r=run([('经营范围',0,0,100,20),('住所',0,50,100,20),('合成测试地址',150,50,150,20)])
        self.assertNotIn('business_scope',r['fields'])
        self.assertEqual(r['fields']['registered_address']['value'],'合成测试地址')
    def test_split_name_same_row(self):
        r=run([('法定代表人',0,0,100,20),('张',140,0,20,20),('三',162,0,20,20)])
        self.assertEqual(r['fields']['legal_representative']['value'],'张三')
    def test_name_conflict_has_no_first_wins(self):
        r=run([('法定代表人 张',0,0,150,20),('法定代表人 张三',0,50,150,20)])
        f=r['fields']['legal_representative'];self.assertEqual(f['value'],'');self.assertEqual({x['value'] for x in f['candidates']},{'张','张三'})
    def test_same_line_multiple_labels(self):
        r=run([('法定代表人 张三 经营范围 技术服务',0,0,400,20)])
        self.assertEqual(r['fields']['legal_representative']['value'],'张三');self.assertNotIn('business_scope',r['fields'])
    def test_excluded_scope_does_not_change_address(self):
        r=run([('经营范围',0,0,100,20),('技术服务；',140,0,120,20),('软件开发。',140,30,120,20),('住所',0,60,100,20),('合成测试地址',140,60,150,20)])
        self.assertNotIn('business_scope',r['fields'])
        self.assertEqual(r['fields']['registered_address']['value'],'合成测试地址')
    def test_split_latin_name_preserves_word_boundary(self):
        r=run([('法定代表人',0,0,100,20),('SYNTHETIC',140,0,100,20),('USER',245,0,60,20)])
        self.assertEqual(r['fields']['legal_representative']['value'],'SYNTHETIC USER')
    def test_single_character_name_is_accepted(self):
        self.assertEqual(run([('法定代表人',0,0,100,20),('王',140,0,20,20)])['fields']['legal_representative']['value'],'王')
    def test_repeated_identical_labels_deduplicate(self):
        f=run([('法定代表人 王',0,0,150,20),('法定代表人 王',0,40,150,20)])['fields']['legal_representative']
        self.assertEqual(f['value'],'王');self.assertEqual(len(f['candidates']),1)
    def test_scrambled_array_and_four_coordinate_rotations(self):
        items=[('合成甲',160,60,100,20),('名称',0,0,100,20),('合成商店',160,0,100,20),('法定代表人',0,60,100,20),('经营范围',0,120,100,20),('合成技术服务',160,120,140,20)]
        for t in range(4):
            r=run(items,t)['fields'];self.assertEqual(r['legal_representative']['value'],'合成甲');self.assertNotIn('business_scope',r);self.assertEqual(r['company_name']['value'],'合成商店')
    def test_cannot_borrow_across_another_column_label(self):
        r=run([('法定代表人',0,0,100,20),('经营范围',200,0,100,20),('合成技术服务',350,0,150,20)])
        self.assertEqual(r['fields']['legal_representative']['value'],'');self.assertNotIn('business_scope',r['fields'])
    def test_high_confidence_still_requires_review(self):
        r=run([('法定代表人 合成甲',0,0,200,20)]);self.assertTrue(r['requires_human_confirmation']);self.assertTrue(r['fields']['legal_representative']['requires_review']);self.assertFalse(r['authenticity_verified'])
    def test_missing_geometry_never_takes_next_line(self):
        r=extract_license_fields(normalize_layout({'txts':['经营范围','住所','测试地址'],'scores':[.99]*3}))
        self.assertNotIn('business_scope',r['fields'])
    def test_missing_geometry_inline_still_works(self):
        r=extract_license_fields(normalize_layout({'txts':['法定代表人 王'],'scores':[.4]}))
        self.assertEqual(r['fields']['legal_representative']['value'],'王')
    def test_label_characters_with_spaces(self):
        self.assertEqual(run([('法 定 代 表 人：王',0,0,200,20)])['fields']['legal_representative']['value'],'王')
    def test_embedded_label_word_not_standalone_label(self):
        r=run([('名称',0,0,100,20),('合成经营范围咨询公司',140,0,200,20)])
        self.assertEqual(r['fields']['company_name']['value'],'合成经营范围咨询公司')
    def test_unaligned_arrays_rejected(self):
        with self.assertRaises(ValueError):normalize_layout({'txts':['x'],'scores':[]})
    def test_unusable_geometry_is_local_not_document_failure(self):
        for box in (None, 123, [], [[0,0]]*4, [[0,0],[1,0],[1,float('nan')],[0,1]]):
            rows=normalize_layout({'txts':['法定代表人 合成甲','住所：合成地址'],'scores':[.99,.98],
                'boxes':[box,[[0,40],[200,40],[200,60],[0,60]]]})
            result=extract_license_fields(rows)
            self.assertEqual(result['fields']['legal_representative']['value'],'合成甲')
            self.assertIn('LAYOUT_GEOMETRY_UNAVAILABLE',result['fields']['legal_representative']['warnings'])
            self.assertEqual(result['fields']['registered_address']['value'],'合成地址')
    def test_invalid_standalone_label_geometry_never_borrows_next_text(self):
        rows=normalize_layout({'txts':['法定代表人','合成甲','住所：合成地址'],'scores':[.99]*3,
             'boxes':[None,[[100,0],[200,0],[200,20],[100,20]],[[0,40],[200,40],[200,60],[0,60]]]})
        result=extract_license_fields(rows)
        self.assertEqual(result['fields']['legal_representative']['value'],'')
        self.assertEqual(result['fields']['registered_address']['value'],'合成地址')
    def test_box_array_misalignment_still_rejected(self):
        with self.assertRaises(ValueError):normalize_layout({'txts':['x'],'scores':[.99],'boxes':[]})
    def test_empty_result(self):self.assertEqual(extract_license_fields(normalize_layout({'txts':None,'scores':None}))['fields'],{})
    def test_no_mutation(self):
        raw={'txts':['法定代表人 王'],'scores':[.9],'boxes':[[[0,0],[100,0],[100,20],[0,20]]]};before=copy.deepcopy(raw)
        extract_license_fields(normalize_layout(raw));self.assertEqual(raw,before)

if __name__=='__main__':unittest.main()
