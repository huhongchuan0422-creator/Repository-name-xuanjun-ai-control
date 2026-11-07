"""Synthetic values with public-label geometry from a redacted OCR diagnostic.

No document values or image bytes. Coordinate turns test only parser geometry,
not orientation inference; the original four pixel-rotation calls stay intact.
"""
import unittest
from test_community_license_layout import run
from scripts.community_license_layout import normalize_layout, extract_license_fields

class PartialLabelTests(unittest.TestCase):
    def form(self, fragment='☑称', value='合成测试商户甲乙丙丁戊己庚辛'):
        return [(fragment,214,608,95,33),(value,341,611,304,26),
                ('注册资本',880,607,138,33),('合成资本',1056,610,121,30),
                ('法定代表人',180,714,124,31),('合成甲',339,716,73,32),
                ('经营范围',180,768,124,31),('全合成非目标正文',340,767,510,27)]
    def test_redacted_geometry_and_shuffled_coordinate_turns(self):
        for turn in range(4):
            with self.subTest(turn=turn):
                r=run(list(reversed(self.form())),turn)
                f=r['fields']['company_name']
                self.assertEqual(f['value'],'合成测试商户甲乙丙丁戊己庚辛')
                self.assertIn('PARTIAL_LABEL_RECOVERED',f['warnings'])
                self.assertTrue(f['requires_review']);self.assertTrue(r['requires_human_confirmation'])
                self.assertFalse(r['authenticity_verified']);self.assertNotIn('business_scope',r['fields'])
    def test_actual_value_is_never_rewritten_or_completed(self):
        for value in ('甲','合成名称路商店','SYNTHETIC VALUE'):
            self.assertEqual(run(self.form(value=value))['fields']['company_name']['value'],value)
    def test_only_real_fragment_and_value_boxes_are_preserved(self):
        f=run(self.form())['fields']['company_name']
        self.assertEqual(f['source_lines'],[0,1])
        self.assertEqual(len(f['source_boxes']),2)
        self.assertEqual(f['value_boxes'],[[[341.0,611.0],[645.0,611.0],[645.0,637.0],[341.0,637.0]]])
    def test_no_form_or_one_anchor_does_not_guess(self):
        for items in (self.form()[:2],self.form()[:2]+self.form()[4:6]):
            self.assertNotIn('company_name',run(items)['fields'])
    def test_duplicate_anchor_is_not_independent_evidence(self):
        items=self.form()[:2]+self.form()[4:6]+[('法定代表人',180,768,124,31),('合成乙',339,770,73,32)]
        self.assertNotIn('company_name',run(items)['fields'])
    def test_different_column_does_not_support_fragment(self):
        items=self.form()
        items[4]=('法定代表人',880,714,124,31)
        self.assertNotIn('company_name',run(items)['fields'])
    def test_plain_single_character_and_unknown_noise_are_not_promoted(self):
        for fragment in ('称','甲称','公司','☑甲'):
            self.assertNotIn('company_name',run(self.form(fragment=fragment))['fields'])
    def test_without_independent_value_does_not_become_a_field(self):
        items=self.form();del items[1]
        self.assertNotIn('company_name',run(items)['fields'])
    def test_value_across_another_label_is_not_borrowed(self):
        items=self.form();items[0]=('☑称',780,608,95,33)
        items[4]=('法定代表人',746,714,124,31);items[6]=('经营范围',746,768,124,31)
        del items[1]
        self.assertNotIn('company_name',run(items)['fields'])
    def test_existing_complete_name_has_priority(self):
        items=self.form()+[('名称：原有全合成名称',180,540,465,31)]
        f=run(items)['fields']['company_name']
        self.assertEqual(f['value'],'原有全合成名称');self.assertNotIn('PARTIAL_LABEL_RECOVERED',f['warnings'])
    def test_missing_geometry_cannot_recover(self):
        items=self.form();rows=normalize_layout({'txts':[v[0] for v in items],'scores':[.99]*len(items)})
        self.assertNotIn('company_name',extract_license_fields(rows)['fields'])
    def test_existing_decoration_allowlist_not_one_specific_symbol(self):
        from scripts.community_license_layout import LABEL_DECORATIONS
        for symbol in LABEL_DECORATIONS:
            with self.subTest(symbol=symbol):
                self.assertEqual(run(self.form(fragment=symbol+'称'))['fields']['company_name']['value'],
                                 '合成测试商户甲乙丙丁戊己庚辛')
    def test_fragment_with_multiple_possible_field_roles_is_rejected(self):
        # 经 can start a representative label, an address label or a stop label.
        self.assertNotIn('company_name',run(self.form(fragment='☑经'))['fields'])
        self.assertNotIn('registered_address',run(self.form(fragment='☑经'))['fields'])
    def test_rule_is_not_specific_to_name_or_to_a_value_length(self):
        items=self.form(fragment='☑人',value='甲')
        items[4]=('名称',180,714,124,31)
        f=run(items)['fields']['legal_representative']
        self.assertEqual(f['value'],'甲');self.assertIn('PARTIAL_LABEL_RECOVERED',f['warnings'])

    def test_conflicting_supported_fragments_require_manual_resolution(self):
        items=self.form()+[('☑称',214,550,95,33),('另一合成候选',341,553,304,26)]
        f=run(items)['fields']['company_name']
        self.assertEqual(f['value'],'');self.assertIn('CONFLICTING_CANDIDATES',f['warnings'])
        self.assertEqual(len(f['candidates']),2)

if __name__=='__main__':unittest.main()
