"""Actual native source rendered in existing Hosted Chromium, not WeChat/device acceptance.

Uses the original Page controllers and WXML/WXSS through a test-only DOM adapter.
Provider/login/application responses here are synthetic. Real original HTTP/SQLite
and fresh registration are tested separately in test_community_mini_merchant.
"""
import hashlib,json,os,subprocess,unittest
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]

class NativeSourceRender(unittest.TestCase):
    def test_first_visit_admission_four_steps_tabs_back_and_safe_failure(self):
        out=ROOT/'native-evidence';out.mkdir(exist_ok=True)
        html=out/'native-source-interactive.html'
        subprocess.run(['node',str(ROOT/'tests/community_mini_native_render.cjs'),str(html)],check=True)
        records=[];errors=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport=dict(width=390,height=844),device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            # A renderer must not make any remote request, even if a fixture changes.
            page.route('http://**/*',lambda route:route.abort())
            page.route('https://**/*',lambda route:route.abort())
            def click(method,extra=''):
                page.locator('[data-handler="'+method+'"]'+extra).first.click()
                page.wait_for_timeout(80)
            def snapshot(name):
                self.assertEqual(errors,[])
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
                file=out/(name+'.png');page.screenshot(path=str(file),full_page=True)
                evidence=page.evaluate('window.__nativeEvidence')
                records.append(dict(name=name,sha256=hashlib.sha256(file.read_bytes()).hexdigest(),route=evidence['route'],state=evidence['state'],fixture=True))
            page.goto(html.as_uri());expect(page.get_by_text('发现身边好店',exact=True)).to_be_visible()
            snapshot('01-home-public')
            click('openMerchantJoin');snapshot('02-admission-public')
            click('connectApplicant');expect(page.locator('[data-handler="selectDocumentType"]').first).to_be_enabled();snapshot('03-admission-ready')
            page.locator('[data-handler="selectDocumentType"]').first.select_option('1');page.wait_for_timeout(80)
            self.assertEqual(page.evaluate('window.__nativeEvidence.state.options.doc'),'IDENTIFICATION_TYPE_OVERSEA_PASSPORT');snapshot('04-admission-passport')
            page.locator('input[data-key="store_name"]').fill('隔离测试门店');page.wait_for_timeout(80)
            page.locator('input[data-key="address"]').fill('隔离测试地址');page.wait_for_timeout(80)
            click('save');self.assertIsNotNone(page.evaluate('window.__nativeEvidence.state.application'));snapshot('05-admission-draft')
            application=page.evaluate('window.__nativeEvidence.state.application.application')
            for n,title in [(1,'06-admission-operation'),(2,'07-admission-settlement'),(3,'08-admission-progress')]:
                click('next');self.assertEqual(page.evaluate('window.__nativeEvidence.state.step'),n)
                self.assertEqual(page.evaluate('window.__nativeEvidence.state.application.application'),application);snapshot(title)
            # Synthetic submit is strictly visual/handler evidence. Real material and submit guards run in HTTP tests.
            click('submit');self.assertEqual(page.evaluate('window.__nativeEvidence.state.platformState'),'SUBMITTED');snapshot('09-admission-submitted-fixture')
            click('navigateSection','[data-section="orders"]');expect(page.get_by_text('我的订单',exact=True)).to_be_visible();snapshot('10-orders-no-store')
            click('navigateSection','[data-section="recommendations"]');snapshot('11-recommendations-no-store')
            click('openMerchantJoin');expect(page.get_by_text('商家入驻',exact=True)).to_be_visible();click('goBack');snapshot('12-back-recommendations')
            click('navigateSection','[data-section="profile"]');snapshot('13-profile-no-store')
            click('openMerchant');snapshot('14-workbench-no-store');click('goBack');snapshot('15-back-profile')
            click('navigateSection','[data-section="services"]');snapshot('16-more-services-no-store')
            click('openCustomerHome');click('openMerchantJoin');page.evaluate('window.fixtureFailure(true)');click('connectApplicant')
            self.assertFalse(page.evaluate('window.__nativeEvidence.state.ready'));snapshot('17-login-error')
            calls=page.evaluate('window.__nativeEvidence.calls');self.assertFalse(any(x.get('url','').endswith('/mini/api') for x in calls))
            self.assertEqual(errors,[])
            report=dict(kind='ISOLATED_CHROMIUM_ACTUAL_NATIVE_SOURCE_PROJECTION',wechat_device='NOT_EXECUTED',provider='SYNTHETIC_TEST_SUBSTITUTE',http_acceptance='SEPARATE_REAL_ORIGINAL_HTTP_TEST',customer_acceptance=False,source_html_sha256=hashlib.sha256(html.read_bytes()).hexdigest(),records=records,calls=calls)
            (out/'NATIVE_RENDER_RECEIPT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            browser.close()
