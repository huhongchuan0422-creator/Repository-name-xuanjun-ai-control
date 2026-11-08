import copy
import unittest
from scripts.community_license_layout import normalize_layout
from scripts.community_bank_card_layout import extract_bank_card_fields


def extract(texts, scores=None, boxes=None):
    return extract_bank_card_fields(normalize_layout(dict(txts=texts, scores=scores or [.99]*len(texts), boxes=boxes)), (0,))


class BankCardLayoutTests(unittest.TestCase):
    def test_printed_and_grouped(self):
        r = extract(['合成测试银行', '1111 2222 3333 4444'])
        self.assertEqual(r['fields']['account_number']['value'], '1111222233334444')
        self.assertEqual(r['fields']['account_bank']['value'], '合成测试银行')
        self.assertTrue(r['requires_human_confirmation'])
        self.assertFalse(r['authenticity_verified'])
        self.assertFalse(r['account_validity_verified'])
        self.assertFalse(r['bank_identity_verified'])
        self.assertTrue(all(f['requires_review'] for f in r['fields'].values()))

    def test_no_rejection_on_length_checksum_or_confidence(self):
        r = extract(['卡号：１２３'], [.01])['fields']['account_number']
        self.assertEqual(r['value'], '123')
        self.assertEqual(r['confidence'], .01)
        self.assertIn('UNUSUAL_NUMBER_LENGTH', r['warnings'])
        self.assertIn('LUHN_CHECK_MISMATCH', r['warnings'])

    def test_masked_digits_not_completed(self):
        f = extract(['卡号 1111 **** **** 1234'])['fields']['account_number']
        self.assertEqual(f['value'], '1111********1234')
        self.assertIn('MASKED_OR_INCOMPLETE_NUMBER', f['warnings'])

    def test_conflicts_not_selected(self):
        r = extract(['卡号1111', '卡号2222', '合成甲银行', '合成乙银行'])
        for f in r['fields'].values():
            self.assertEqual(f['value'], '')
            self.assertEqual(len(f['candidates']), 2)
            self.assertIn('CONFLICTING_CANDIDATES', f['warnings'])

    def test_no_name_branch_or_bin_inference(self):
        r = extract(['持卡人：某某', '开户支行：合成银行测试支行', '客服电话：95555', 'VALID 12/30', 'VISA'])
        self.assertEqual(set(r['fields']), {'account_number', 'account_bank'})
        self.assertTrue(all(not f['value'] for f in r['fields'].values()))
        self.assertEqual(len(r['unresolved_rows']), 4)

    def test_neighbour_geometry_and_source_retention(self):
        b = lambda x,y,w: [[x,y],[x+w,y],[x+w,y+20],[x,y+20]]
        rows = normalize_layout(dict(txts=['卡号', '1111 2222'], scores=[.9,.8], boxes=[b(0,0,60),b(90,0,160)]))
        before = copy.deepcopy(rows)
        r = extract_bank_card_fields(rows, (0,))
        self.assertEqual(r['fields']['account_number']['value'], '11112222')
        self.assertEqual(rows, before)
        self.assertTrue(r['fields']['account_number']['source_boxes'])

    def test_no_array_order_concatenation(self):
        r = extract(['1111', '2222'])['fields']['account_number']
        self.assertEqual(r['value'], '')
        self.assertEqual({c['value'] for c in r['candidates']}, {'1111','2222'})

    def test_security_and_contact_semantic_labels_not_numbers(self):
        for label in ('安全码', 'CVV', 'cvc2', 'PIN', '有效期', '客服电话', 'VALID THRU'):
            r = extract([label + '：123', '卡号：456'])
            self.assertEqual(r['fields']['account_number']['value'], '456', label)
            self.assertNotIn('123', str(r['fields']))
            self.assertNotIn('123', str(r['unresolved_rows']))

    def test_separate_security_value_box_reserved_by_geometry(self):
        b = lambda x,y,w: [[x,y],[x+w,y],[x+w,y+20],[x,y+20]]
        r = extract(['CVV', '123', '卡号', '456'], boxes=[b(0,0,60),b(90,0,60),b(0,100,60),b(90,100,60)])
        self.assertEqual(r['fields']['account_number']['value'], '456')
        self.assertNotIn('123', str(r['fields']))
        self.assertNotIn('123', str(r['unresolved_rows']))

    def test_empty_and_turn_validation(self):
        self.assertEqual(extract([])['fields']['account_number']['value'], '')
        for turns in ((), (4,), (True,)):
            with self.assertRaises(ValueError): extract_bank_card_fields([], turns)

    def test_four_coordinate_rotations_preserve_candidates(self):
        original = normalize_layout(dict(txts=['卡号', '1111 2222', '合成测试银行'], scores=[.9]*3,
            boxes=[[[0,0],[60,0],[60,20],[0,20]], [[90,0],[250,0],[250,20],[90,20]],
                   [[0,40],[200,40],[200,60],[0,60]]]))
        for turn in range(4):
            rows = copy.deepcopy(original)
            for row in rows:
                for unused in range(turn):
                    row['box'] = [[-y,x] for x,y in row['box']]
            r = extract_bank_card_fields(rows)
            self.assertEqual(r['fields']['account_number']['value'], '11112222')
            self.assertEqual(r['fields']['account_bank']['value'], '合成测试银行')

    def test_normalize_alignment_errors_remain(self):
        with self.assertRaises(ValueError):
            normalize_layout(dict(txts=['123'], scores=[]))


if __name__ == '__main__':
    unittest.main()
