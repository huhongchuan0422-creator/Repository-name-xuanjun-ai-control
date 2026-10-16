import pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class TestIntakePages(unittest.TestCase):
 def test_all_guides(self):
  js=(ROOT/'demos/customer-intake/project-intake.js').read_text()
  for x in ('company_identity','domain_control','wechat_merchant','wechat_miniapp','douyin_oauth','x_oauth'):
   self.assertIn(x,js)
 def test_no_network_or_storage(self):
  js=(ROOT/'demos/customer-intake/project-intake.js').read_text()
  for x in ('fetch(', 'XMLHttpRequest','localStorage','sessionStorage','type="file"'):
   self.assertNotIn(x,js)
 def test_buttons(self):
  html=(ROOT/'demos/customer-intake/project.html').read_text()
  for x in ('id="items"','id="detail"','id="save"','id="submit"','id="correct"','role="status"'):
   self.assertIn(x,html)
  self.assertIn('未接入客户真实登录',html)
 def test_review_actions_explicitly_forbidden_in_customer_demo(self):
  js=(ROOT/'demos/customer-intake/project-intake.js').read_text(encoding='utf-8')
  self.assertIn('kind!=="save"&&kind!=="submit"',js)
  self.assertIn('x.minimum_permissions',js)
  self.assertIn('x.reviewer_role',js)
 def test_authoritative_guide_mirror(self):
  import json,re
  doc=json.loads((ROOT/'docs/customer-intake/project-requirements.v1.json').read_text(encoding='utf-8'))
  js=(ROOT/'demos/customer-intake/project-intake.js').read_text(encoding='utf-8')
  m=re.search(r'const guides=(\[.*?\]);\s*const REQUIREMENTS=',js,re.S)
  self.assertIsNotNone(m)
  mirrored=json.loads(m.group(1))
  self.assertEqual([x['id'] for x in mirrored],[x['id'] for x in doc['items']])
  for source,view in zip(doc['items'],mirrored):
   for original,rendered in [('title','title'),('materials','materials'),('instructions','instructions'),('official_url','url'),('submission_type','method'),('purpose','purpose'),('minimum_permissions','minimum_permissions'),('expiry_policy','expiry_policy'),('reviewer_role','reviewer_role'),('verification_method','verification_method'),('fallback','fallback'),('steps','steps')]:
    self.assertEqual(source[original],view[rendered])
