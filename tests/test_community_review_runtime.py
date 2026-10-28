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
 def visible_field(self,page,selector,label,max_steps=24):
  target=page.locator(selector)
  expect(target).to_be_visible()
  return target
 def test_native_saved_application_is_read_by_original_platform_reviewer(self):
  page=self.page();errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
  self.ready(page);page.locator('#apply').click();page.wait_for_function('window.reviewPage?.data.ready === true')
  self.assertEqual(page.evaluate('window.reviewPage.data.applications.length'),0)
  self.assertIsNone(page.evaluate('window.reviewPage.data.application'))
  expect(page.get_by_role('button',name='保存同一份申请草稿，暂不离开',exact=True)).to_be_enabled()
  expect(page.locator('#native [data-path="subject_info.identity_info.id_doc_type"] select')).to_be_enabled()
  merchant_name=self.visible_field(page,'input[data-path="subject_info.business_license_info.merchant_name"]','stage0 merchant_name')
  merchant_name.fill('同版本测试主体')
  mobile=self.visible_field(page,'input[data-path="contact_info.mobile_phone"]','stage0 mobile_phone')
  mobile.fill('13800000000')
  page.locator('#native [data-key="ubos"] select').select_option('1')
  page.get_by_role('button',name='保存草稿并继续下一项',exact=True).click();page.wait_for_function('window.reviewPage.data.step === 1')
  page.locator('#native [data-key="scene"] select').select_option('2')
  page.locator('input[data-path="business_info.merchant_shortname"]').fill('同版本测试门店')
  page.get_by_role('button',name='保存草稿并继续下一项',exact=True).click();page.wait_for_function('window.reviewPage.data.step === 2')
  application=page.evaluate('window.reviewPage.data.application.application')
  page.get_by_role('button',name='‹ 上一阶段',exact=True).click();page.wait_for_function('window.reviewPage.data.step === 1')
  page.get_by_role('button',name='‹ 上一阶段',exact=True).click();page.wait_for_function('window.reviewPage.data.step === 0')
  mobile_after_back=self.visible_field(page,'input[data-path="contact_info.mobile_phone"]','stage2 back to stage0 mobile_phone')
  expect(mobile_after_back).to_have_value('13800000000')
  page.reload();page.get_by_role('button',name='同版本测试门店 · 草稿未提交',exact=True).click();expect(page.locator('input[data-path="subject_info.business_license_info.merchant_name"]')).to_have_value('同版本测试主体')
  self.assertEqual(page.evaluate('window.reviewPage.data.application.application'),application)
  self.assertEqual(page.evaluate('window.reviewPage.data.application.status'),'DRAFT')
  page.screenshot(path=str(self.out/'native-same-application.png'),full_page=True)
  page.locator('#review').click();frame=page.frame_locator('#frame');frame.locator('body[data-review-ready="true"]').wait_for()
  frame.get_by_role('button',name='商家入驻申请',exact=True).click();expect(frame.locator('#applications')).to_contain_text('同版本测试门店')
  page.screenshot(path=str(self.out/'platform-same-application.png'),full_page=True)
  self.assertFalse(errors,errors);self.assertTrue(all(url.startswith(self.url) for url in requests),requests)
 def test_native_home_store_navigation_uses_registered_pages(self):
  page=self.page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  self.ready(page)
  page.get_by_role('button',name='查看当前门店介绍 ›',exact=True).click()
  expect(page).to_have_url(__import__('re').compile(r'view=store-detail&scene=shop1$'))
  page.wait_for_function("window.reviewPage?.data.viewMode === 'store-detail' && window.reviewPage?.scene === 'shop1'")
  self.assertEqual(page.evaluate('window.reviewPage.data.viewMode'),'store-detail')
  self.assertEqual(page.evaluate('window.reviewPage.scene'),'shop1')
  expect(page.locator('#native')).to_contain_text('不代表资质、排名或开通支付')
  page.get_by_role('button',name='返回推荐店铺',exact=True).click()
  expect(page.locator('#native')).to_contain_text('推荐目录尚未开放')
  page.locator('#native [data-section="orders"]').click()
  expect(page.locator('#native')).to_contain_text('订单')
  page.locator('#native [data-section="home"]').click()
  expect(page.locator('#native')).to_contain_text('查看当前门店介绍')
  self.assertEqual(errors,[])
 def test_actual_web_license_inline_saves_and_uploads_same_application(self):
  page=self.page();page.add_init_script("""window.addEventListener('load',async()=>{
    const response=await fetch('/review/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'merchant'})});
    const context=await response.json();if(!response.ok||context.isolated!==true)throw Error('ISOLATED_SESSION_REQUIRED');
    const originalFetch=window.fetch.bind(window),session=context.result;
    window.fetch=(url,options={})=>originalFetch(url,{...options,headers:{...options.headers,'X-Center-Session':session.token,'X-CSRF-Token':session.csrf}});
    await window.configureCommunityOnboarding({csrf:session.csrf});document.body.dataset.reviewReady='true';
  });""")
  page.goto(self.url+'/merchant/join');page.locator('body[data-review-ready="true"]').wait_for()
  page.locator('#newApplication').click();page.locator('#entity_type').select_option('ENTERPRISE')
  license_name=page.locator('[data-path="subject_info.business_license_info.merchant_name"]')
  expect(license_name).to_be_visible();expect(license_name).to_have_count(1)
  license_name.fill('就地执照测试主体');page.locator('#legal_name').fill('就地执照测试主体')
  page.locator('#store_name').fill('就地执照测试店');page.locator('#address').fill('隔离测试地址');page.locator('#contact').fill('13800000000')
  page.locator('#saveDraft').click();expect(page.locator('#status')).to_contain_text('申请草稿已保存')
  expect(license_name).to_have_value('就地执照测试主体')
  application=page.locator('#applicationVersion').inner_text().split(' · ')[0]
  page.locator('#saveLicense').click();expect(page.locator('#wechatState')).to_contain_text('version')
  with page.expect_response(lambda r:r.url.endswith('/merchant/onboarding') and r.request.post_data_json.get('operation')=='wechat_read') as read_reply:
   page.locator('#wechatRead').click()
  self.assertEqual(read_reply.value.status,200)
  self.assertEqual(read_reply.value.json()['result']['profile']['subject_info']['business_license_info']['merchant_name'],'就地执照测试主体')
  expect(page.locator('#wechatRead')).to_be_enabled();expect(license_name).to_have_value('就地执照测试主体')
  row=page.locator('#licenseUpload [data-kind="business_license"]');expect(row).to_be_visible()
  row.locator('input[type="file"]').set_input_files({'name':'license.pdf','mimeType':'application/pdf','buffer':b'%PDF-synthetic license'})
  self.assertEqual(row.locator('input[type="file"]').evaluate('e=>e.files.length'),1)
  with page.expect_response(lambda r:r.url.endswith('/merchant/onboarding') and r.request.post_data_json.get('operation')=='upload') as upload_reply:
   row.get_by_role('button',name='上传资料',exact=True).click()
  self.assertEqual(upload_reply.value.status,200,upload_reply.value.text())
  self.assertIn('business_license',upload_reply.value.json()['result']['materials'])
  expect(row).to_contain_text('已上传')
  self.assertTrue(page.locator('#applicationVersion').inner_text().startswith(application))
  page.screenshot(path=str(self.out/'web-inline-license-same-application.png'),full_page=True)
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
