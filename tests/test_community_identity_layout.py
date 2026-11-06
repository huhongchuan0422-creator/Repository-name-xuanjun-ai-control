import copy
import json
from pathlib import Path
import unittest
from scripts.community_license_layout import normalize_layout, extract_license_fields
from scripts.community_identity_layout import extract_identity_fields


def rows(items):
    return normalize_layout({'txts':[v[0] for v in items], 'scores':[.99]*len(items),
        'boxes':[[[x,y],[x+w,y],[x+w,y+h],[x,y+h]] for _,x,y,w,h in items]})


class IdentityGeometryTests(unittest.TestCase):
    def test_array_order_cannot_supply_name(self):
        r=extract_identity_fields(rows([('合成甲',140,0,100,20),('姓名',0,0,100,20),('性别 男',0,40,100,20)]))
        self.assertEqual(r['fields']['id_name']['value'],'合成甲')
        self.assertEqual(r['fields']['id_name']['source_lines'],[0,1])

    def test_address_alias_and_multiline(self):
        r=extract_identity_fields(rows([('住址',0,0,100,20),('合成示例路',140,0,160,20),
            ('测试一号',140,30,120,20),('公民身份号码',0,80,100,20),('111111111111111111',140,80,240,20)]))
        self.assertEqual(r['fields']['registered_address']['value'],'合成示例路测试一号')
        self.assertEqual(r['fields']['id_number']['value'],'111111111111111111')

    def test_back_two_dates_and_authority(self):
        r=extract_identity_fields(rows([('签发机关',0,0,100,20),('合成测试公安局',140,0,240,20),
            ('有效期限',0,40,100,20),('2020.01.02-2030.01.02',140,40,300,20)]),'id_back')
        self.assertEqual({k:v['value'] for k,v in r['fields'].items()},
            {'issuing_authority':'合成测试公安局','valid_from':'2020-01-02','valid_to':'2030-01-02'})
        self.assertTrue(r['requires_human_confirmation'])
        self.assertFalse(r['authenticity_verified'])
        self.assertTrue(all(f['requires_review'] for f in r['fields'].values()))

    def test_compact_inline_and_long_term(self):
        r=extract_identity_fields(rows([('签发机关合成公安局',0,0,400,20),('有效期限2020年1月2日至长期',0,40,400,20)]),'id_back')
        self.assertEqual(r['fields']['issuing_authority']['value'],'合成公安局')
        self.assertEqual(r['fields']['valid_from']['value'],'2020-01-02')
        self.assertEqual(r['fields']['valid_to']['value'],'长期')

    def test_no_guess_for_invalid_or_single_date(self):
        for text in ('2020.02.30-2030.01.02','2020.01.02'):
            r=extract_identity_fields(rows([('有效期限 '+text,0,0,400,20)]),'id_back')
            self.assertEqual(r['fields']['valid_from']['value'],'')
            self.assertEqual(r['fields']['valid_to']['value'],'')
            self.assertTrue(r['unresolved_validity_candidates'])

    def test_missing_geometry_does_not_borrow(self):
        r=extract_identity_fields(normalize_layout({'txts':['姓名','合成甲','性别 男'],'scores':[.99]*3}))
        self.assertEqual(r['fields']['id_name']['value'],'')

    def test_conflicting_name_candidates_are_visible(self):
        r=extract_identity_fields(rows([('姓名：合成甲',0,0,200,20),('姓名：合成乙',0,40,200,20)]))
        f=r['fields']['id_name']; self.assertEqual(f['value'],'');self.assertEqual(len(f['candidates']),2)

    def test_source_boxes_retained_without_input_mutation(self):
        raw=rows([('姓名',0,0,100,20),('合成甲',140,0,100,20)]); before=copy.deepcopy(raw)
        r=extract_identity_fields(raw)
        self.assertEqual(raw,before)
        self.assertEqual(r['fields']['id_name']['value_boxes'],[raw[1]['box']])


class SyntheticFailureGeometryTests(unittest.TestCase):
    def test_recognized_label_characters_survive_checkbox_noise(self):
        data=json.loads((Path(__file__).parent/'fixtures/community_license_label_noise_geometry.json').read_text())
        self.assertFalse(data['contains_real_values'])
        result=extract_license_fields(data['rows'],(0,))
        self.assertEqual(result['fields']['company_name']['value'],'合成值8')
        self.assertEqual(result['fields']['company_name']['source_lines'],[6,7,8])
        self.assertEqual(result['fields']['company_name']['value_boxes'],[data['rows'][2]['box']])

    def test_label_symbol_cleanup_does_not_modify_values_or_guess_characters(self):
        result=extract_license_fields(rows([('名',0,0,20,20),('☑称',21,0,60,20),('☑合成商户',100,0,140,20)]),(0,))
        self.assertEqual(result['fields']['company_name']['value'],'☑合成商户')
        missing=extract_license_fields(rows([('名',0,0,20,20),('☑',21,0,20,20),('合成商户',100,0,140,20)]),(0,))
        self.assertNotIn('company_name',missing['fields'])

    def test_excluded_scope_never_scores_or_returns_as_an_ocr_target(self):
        from scripts.community_license_inference import _orientation_evidence, _choose_orientation, EXPECTED_FIELDS
        raw=rows([('经营范围：合成内容',0,0,250,20)])
        result=extract_license_fields(raw,(0,))
        self.assertEqual(result['fields'],{})
        self.assertNotIn('business_scope',EXPECTED_FIELDS['business_license'])
        # Even legacy field dictionaries do not count toward the new target or
        # reappear in new output; this does not mutate stored historical jobs.
        legacy={'fields':{'business_scope':{'value':'合成历史值','confidence':.99,'source_lines':[0,1]}}}
        rank,evidence=_orientation_evidence(raw,legacy,'business_license')
        self.assertEqual(rank,(0,0,0))
        merged=_choose_orientation([{'turn':0,'rank':rank,'evidence':evidence,'result':legacy}],'business_license',300,100)
        self.assertNotIn('business_scope',merged['fields'])
        self.assertIn('business_scope',legacy['fields'])

    def test_private_values_not_in_fixture(self):
        data=json.loads((Path(__file__).parent/'fixtures/community_document_failure_geometry.json').read_text())
        self.assertFalse(data['contains_real_values'])
        first,license_case=data['cases']
        result=extract_identity_fields(normalize_layout(first['raw']))
        for k,v in first['expected'].items():self.assertEqual(result['fields'][k]['value'],v)
        self.assertEqual(result['fields']['id_number']['value'],'')
        result=extract_license_fields(normalize_layout(license_case['raw']))
        for k,v in license_case['expected'].items():self.assertEqual(result['fields'][k]['value'],v)
        self.assertNotIn('business_scope',result['fields'])
        self.assertNotIn('company_name',result['fields'])  # Broken label is not silently guessed.

if __name__=='__main__':unittest.main()
