import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TestGuideContract(unittest.TestCase):
 def test_contract(self):
  data=json.loads((ROOT/'docs/customer-intake/project-requirements.v1.json').read_text(encoding='utf-8'))
  self.assertEqual(data['status'],'OFFLINE_CANDIDATE_NOT_ACCEPTING_FILES')
  ids=[x['id'] for x in data['items']]
  self.assertEqual(len(ids),len(set(ids)))
  self.assertGreaterEqual(len(ids),6)
  for item in data['items']:
   self.assertIn(item['submission_type'],('PRIVATE_DOCUMENT','SERVER_CHALLENGE','PUBLIC_ID_PLUS_SECRETREF','OAUTH'))
   self.assertTrue(item['instructions'] and item['materials'])
   self.assertEqual(item['submission_status'],'WAITING_VERIFIED_CUSTOMER_LOGIN')
 def test_preview_no_real_submit(self):
  s=(ROOT/'demos/customer-intake/index.html').read_text(encoding='utf-8')
  self.assertIn('UPLOAD=DISABLED',s)
  self.assertNotIn('<form',s)
  self.assertNotIn('type="file"',s)
  self.assertNotIn('type="password"',s)
if __name__=='__main__':unittest.main()

 def test_full_tutorial_fields_in_static_pages(self):
  data=json.loads((ROOT/'docs/customer-intake/project-requirements.v1.json').read_text(encoding='utf-8'))
  page=(ROOT/'demos/customer-intake/index.html').read_text(encoding='utf-8')
  js=(ROOT/'demos/customer-intake/project-intake.js').read_text(encoding='utf-8')
  for item in data['items']:
   for key in ('purpose','minimum_permissions','expiry_policy','reviewer_role','verification_method','fallback'):
    self.assertTrue(item[key])
    self.assertIn(item[key].replace('&','&amp;'),page)
   self.assertTrue(item['steps'])
   self.assertIn(item['id'],js)
