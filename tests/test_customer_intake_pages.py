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
if __name__=='__main__':unittest.main()
