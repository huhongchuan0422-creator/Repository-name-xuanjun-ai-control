"""Replay actual unchanged model output from eight explicitly synthetic images.

This tests mapping, not a new inference run or real-document accuracy.
"""
import json
from pathlib import Path
import unittest
from scripts.community_license_layout import normalize_layout,extract_license_fields

class RawReplay(unittest.TestCase):
    def test_independent_heldout_cases(self):
        cases=json.loads((Path(__file__).parent/'fixtures/community_license_layout_heldout.json').read_text())
        for case in cases:
            with self.subTest(case=case['case']):
                result=extract_license_fields(normalize_layout(case['raw']))
                self.assertNotIn('business_scope',result['fields'])
                # Retain original fixtures as historical input, not current scope requirements.
                expected={k:v for k,v in case['expected'].items() if k!='business_scope'}
                self.assertEqual({k:v['value'] for k,v in result['fields'].items()},expected)

    def test_eight_real_model_synthetic_outputs(self):
        files=sorted((Path(__file__).parent/'fixtures/community_license_layout').glob('*.json'))
        self.assertEqual(len(files),8)
        for path in files:
            with self.subTest(path=path.name):
                data=json.loads(path.read_text());self.assertTrue(data['synthetic_only'])
                result=extract_license_fields(normalize_layout(data['raw_capture']))
                self.assertNotIn('business_scope',result['fields'])
                for key,value in data['expected'].items():
                    if key=='business_scope':continue
                    self.assertEqual(result['fields'][key]['value'],value)
                    self.assertTrue(result['fields'][key]['requires_review'])
                # Deliberately invalid synthetic credit code must not be invented.
                self.assertEqual(result['fields']['credit_code']['value'],'')
                self.assertTrue(result['requires_human_confirmation'])
                self.assertFalse(result['authenticity_verified'])

if __name__=='__main__':unittest.main()
