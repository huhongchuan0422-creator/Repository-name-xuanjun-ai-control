"""Local synthetic native WXML visibility/edit only, no customer acceptance."""
import os,pathlib,subprocess,tempfile,unittest
from playwright.sync_api import sync_playwright,expect
ROOT=pathlib.Path(__file__).resolve().parents[1]
class StepOcrReviewNative(unittest.TestCase):
 def test_all_nine_values_editable_before_one_primary_save_and_no_extra_confirmation(self):
  with tempfile.TemporaryDirectory(prefix='step-review-native-') as temp:
   html=pathlib.Path(temp)/'native.html'
   subprocess.run(['node',str(ROOT/'tests/community_mini_native_render.cjs'),str(html)],check=True)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path=os.environ.get("COMMUNITY_TEST_CHROMIUM_PATH"))
    page=browser.new_page(viewport={'width':390,'height':844});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('http://**/*',lambda r:r.abort());page.route('https://**/*',lambda r:r.abort())
    page.goto(html.as_uri())
    def click(method,extra=''):
     page.locator('[data-handler="'+method+'"]'+extra).first.click();page.wait_for_timeout(100)
    click('navigateSection','[data-section="profile"]');click('openMerchantEntry');click('save')
    page.evaluate('window.fixtureStepOcrReview()');before=page.evaluate('window.__nativeEvidence.calls.length')
    expect(page.locator('[data-handler="reviewAndNext"]')).to_contain_text('保存／下一步（确认本页资料）')
    panel=page.locator('#step-ocr-review');expect(panel).to_be_visible()
    inputs=panel.locator('input[data-handler="editStepOcrReview"]');expect(inputs).to_have_count(9)
    self.assertEqual(inputs.evaluate_all('(xs)=>xs.map(x=>x.value)'),['SYNTHETIC CREDIT','SYNTHETIC COMPANY','SYNTHETIC LEGAL','SYNTHETIC ADDRESS','SYNTHETIC PERSON','SYNTHETIC ID','SYNTHETIC HOME','2020-01-01','长期'])
    inputs.first.fill('SYNTHETIC EDIT');page.wait_for_timeout(100)
    expect(panel.locator('input').first).to_have_value('SYNTHETIC EDIT')
    expect(panel.locator('[data-handler="confirmStepOcrReview"]')).to_have_count(0)
    self.assertEqual(page.evaluate('window.__nativeEvidence.calls.length'),before)
    self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
    self.assertEqual(page.evaluate('window.__nativeEvidence.calls.length'),before)
    self.assertEqual(page.evaluate('window.__nativeEvidence.state.step'),0);self.assertEqual(errors,[])
    browser.close()
if __name__=='__main__':unittest.main()
