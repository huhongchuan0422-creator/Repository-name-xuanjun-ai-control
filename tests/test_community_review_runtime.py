"""Real browser/native controllers and original multi-role HTTP, isolated data only."""
import json,os,signal,subprocess,sys,unittest,urllib.request,urllib.error
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]

class IntegratedReview(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.process=subprocess.Popen([sys.executable,'-u','scripts/community_review_runtime.py'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  line=cls.process.stdout.readline()
  if not line:raise RuntimeError(cls.process.stderr.read())
  cls.receipt=json.loads(line);cls.url=cls.receipt['url']
  cls.pw=sync_playwright().start();cls.browser=cls.pw.chromium.launch()
  cls.out=Path(os.environ.get('COMMUNITY_REVIEW_EVIDENCE','/tmp/community-runtime-evidence'));cls.out.mkdir(parents=True,exist_ok=True)
 @classmethod
 def tearDownClass(cls):
  cls.browser.close();cls.pw.stop();cls.process.send_signal(signal.SIGINT)
  try:_,error=cls.process.communicate(timeout=5)
  except subprocess.TimeoutExpired:cls.process.kill();_,error=cls.process.communicate()
  (cls.out/'runner-shutdown.log').write_text(error)
 def page(self,width=390):
  context=self.browser.new_context(viewport={'width':width,'height':900});page=context.new_page();page.set_default_timeout(7000)
  self.addCleanup(context.close);return page
 def ready(self,page):
  page.goto(self.url);page.locator('body[data-review-ready="true"]').wait_for();expect(page.locator('#native')).to_contain_text('客户身份已验证')
 def test_native_saved_application_is_read_by_original_platform_reviewer(self):
  page=self.page();errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
  self.ready(page);page.locator('#apply').click();expect(page.locator('#native')).to_contain_text('选择原申请继续办理')
  page.locator('input[data-key="store_name"]').fill('同版本测试门店')
  page.locator('input[data-key="address"]').fill('隔离演示地址')
  page.locator('input[data-path="subject_info.business_license_info.merchant_name"]').fill('同版本测试主体')
  page.get_by_role('button',name='保存并下一步',exact=True).click();expect(page.locator('#native')).to_contain_text('2 / 4')
  page.locator('input[data-path="contact_info.mobile_phone"]').fill('13800000000')
  page.get_by_role('button',name='保存并下一步',exact=True).click();expect(page.locator('#native')).to_contain_text('3 / 4')
  application=page.evaluate('window.reviewPage.data.application.application')
  page.get_by_role('button',name='上一步',exact=True).click();expect(page.locator('input[data-path="contact_info.mobile_phone"]')).to_have_value('13800000000')
  page.reload();page.get_by_role('button',name='同版本测试门店 · DRAFT',exact=True).click();expect(page.locator('input[data-key="store_name"]')).to_have_value('同版本测试门店')
  self.assertEqual(page.evaluate('window.reviewPage.data.application.application'),application)
  page.screenshot(path=str(self.out/'native-same-application.png'),full_page=True)
  page.locator('#review').click();frame=page.frame_locator('#frame');frame.locator('body[data-review-ready="true"]').wait_for()
  frame.get_by_role('button',name='商家入驻申请',exact=True).click();expect(frame.locator('#applications')).to_contain_text('同版本测试门店')
  page.screenshot(path=str(self.out/'platform-same-application.png'),full_page=True)
  self.assertFalse(errors,errors);self.assertTrue(all(url.startswith(self.url) for url in requests),requests)
 def test_community_and_platform_operate_same_original_directory(self):
  page=self.page(1440);self.ready(page);page.locator('#identity').select_option('community')
  frame=page.frame_locator('#frame');frame.locator('body[data-review-ready="true"]').wait_for()
  frame.get_by_role('button',name='社区资料',exact=True).click()
  frame.locator('#name').fill('同版本测试社区');frame.locator('#contact').fill('隔离联系人');frame.locator('#description').fill('真实原接口与临时测试库')
  frame.get_by_role('button',name='保存资料',exact=True).click();expect(frame.locator('#result')).to_contain_text('同版本测试社区')
  frame.get_by_role('button',name='提交审核',exact=True).click();expect(frame.locator('#result')).to_contain_text('PENDING')
  page.locator('#identity').select_option('platform');frame=page.frame_locator('#frame');frame.locator('body[data-review-ready="true"]').wait_for()
  frame.get_by_role('button',name='平台审核',exact=True).click();frame.locator('#listDirectory').click();expect(frame.locator('#records')).to_contain_text('同版本测试社区')
  page.locator('#terminal').select_option('phone');expect(page.locator('#frame')).to_have_class('phone')
  page.screenshot(path=str(self.out/'community-platform-phone.png'),full_page=True)
  page.locator('#terminal').select_option('desktop');page.screenshot(path=str(self.out/'community-platform-desktop.png'),full_page=True)
 def test_consumer_cannot_gain_existing_merchant_and_external_code_is_not_simulated(self):
  page=self.page();self.ready(page)
  page.evaluate("location.hash='/pages/merchant/index?scene=shop1'")
  expect(page.locator('#native')).to_contain_text('当前账号尚无已开通商家权限')
  page.locator('#identity').select_option('merchant');expect(page.locator('#native')).to_contain_text('请选择日常服务')
  page.get_by_role('button',name='日常订单与收款记录',exact=True).click();expect(page.locator('#native')).to_contain_text('暂无记录')
  page.get_by_role('button',name='返回工作台',exact=True).click();page.get_by_role('button',name='取得正式商家收款码',exact=True).click();expect(page.locator('#native')).to_contain_text('暂未取得可用的正式收款码')
  self.assertEqual(page.locator('#native img').count(),0)
 def test_existing_merchant_catalog_is_not_deleted_and_native_reads_its_edit(self):
  page=self.page();self.ready(page);page.locator('#identity').select_option('merchant');expect(page.locator('#native')).to_contain_text('请选择日常服务')
  page.locator('#portal').click();frame=page.frame_locator('#frame');frame.locator('body[data-review-ready="true"]').wait_for()
  frame.get_by_role('button',name='商品管理',exact=True).click()
  frame.locator('#itemId').fill('review_item');frame.locator('#itemName').fill('同版本手机可见商品');frame.locator('#itemSort').fill('1')
  frame.locator('#itemForm button').click();expect(frame.locator('#items')).to_contain_text('同版本手机可见商品')
  # Return to the same merchant identity, not the consumer identity.
  page.evaluate("location.hash='/pages/merchant/index?scene=shop1'")
  # A management iframe is an auxiliary original backend, not a replacement mini.
  page.locator('#identity').select_option('consumer');page.locator('#identity').select_option('merchant')
  expect(page.locator('#native')).to_contain_text('请选择日常服务');page.get_by_role('button',name='门店与商品资料',exact=True).click();expect(page.locator('#native')).to_contain_text('同版本手机可见商品')

 def test_runner_accepts_no_production_root_and_rejects_cross_origin(self):
  self.assertTrue(self.receipt['isolated']);self.assertFalse(self.receipt['payments']);self.assertTrue(self.receipt['temporary_data'])
  request=urllib.request.Request(self.url+'/review/sources',headers={'Origin':'https://example.invalid'})
  with self.assertRaises(urllib.error.HTTPError) as context:urllib.request.urlopen(request)
  self.assertEqual(context.exception.code,403)
  with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.url+'/review/../../secret')

if __name__=='__main__':unittest.main()
