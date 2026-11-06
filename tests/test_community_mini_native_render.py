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
                if name=='17-login-error':
                    for group in ('license','legal'):
                        expect(page.locator('#material-'+group).get_by_text('登录后读取材料清单',exact=True)).to_be_visible()
                    expect(page.get_by_text('正在读取材料清单',exact=False)).to_have_count(0)
                    self.assertFalse(page.evaluate('window.__nativeEvidence.state.pending'))
                # Native picker child labels and selection must show the same Page state.
                # HTML select does not apply a value attribute after options are inserted.
                for picker in page.locator('select[value]:not([data-column])').all():
                    expect(picker).to_have_value('' if picker.get_attribute('aria-label').strip().startswith('请选择') else picker.get_attribute('value'))
                for raw_code in ('BANK_ACCOUNT_TYPE_CORPORATE','BANK_ACCOUNT_TYPE_PERSONAL','NOT_VERIFIED','NOT_APPROVED','operator_identity','ubo_1_front'):
                    expect(page.get_by_text(raw_code,exact=False)).to_have_count(0)
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),page.evaluate("""()=>[...document.querySelectorAll('*')].map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,scroll:e.scrollWidth})).sort((a,b)=>b.right-a.right).slice(0,5)"""))
                spacing=page.locator('.page:visible').first.evaluate('(element)=>({left:parseFloat(getComputedStyle(element).paddingLeft),bottom:parseFloat(getComputedStyle(element).paddingBottom)})')
                self.assertGreaterEqual(spacing['left'],10,'native .page padding must survive DOM projection')
                self.assertGreaterEqual(spacing['bottom'],90,'native bottom safe-area reservation must survive rpx conversion')
                file=out/(name+'.png');page.screenshot(path=str(file),full_page=True)
                viewport=out/(name+'-viewport.png');page.screenshot(path=str(viewport),full_page=False)
                evidence=page.evaluate('window.__nativeEvidence')
                records.append(dict(name=name,viewport_sha256=hashlib.sha256(viewport.read_bytes()).hexdigest(),viewport=dict(width=390,height=844),sha256=hashlib.sha256(file.read_bytes()).hexdigest(),route=evidence['route'],state=evidence['state'],fixture=True))
            page.goto(html.as_uri());expect(page.get_by_text('好生活，就在身边。',exact=True)).to_be_visible()
            from scripts.community_merchant_onboarding import MATERIALS
            self.assertEqual({x['id']:x['title'] for x in page.evaluate('window.__nativeCatalog')},MATERIALS)
            snapshot('01-home-public')
            click('navigateSection','[data-section="profile"]');snapshot('13-profile-no-store')
            self.assertEqual(page.locator('[data-handler="openMerchantEntry"]').count(),1)
            # Original onLoad verifies the shared identity and reads catalog/mine automatically.
            before_join=page.evaluate('window.__nativeEvidence.calls')
            click('openMerchantEntry')
            evidence=page.evaluate('window.__nativeEvidence')
            self.assertTrue(evidence['state']['authenticated'])
            self.assertTrue(evidence['state']['ready'])
            self.assertFalse(evidence['state']['pending'])
            self.assertIsNone(evidence['state']['application'])
            self.assertEqual(evidence['state']['applications'],[])
            self.assertEqual(evidence['state']['catalog'],page.evaluate('window.__nativeCatalog'))
            self.assertEqual(sum(x.get('operation')=='wx.login' for x in evidence['calls']),1)
            self.assertEqual([x.get('suboperation') for x in evidence['calls'][len(before_join):]],['catalog','mine'])
            expect(page.locator('[data-handler="connectApplicant"]')).to_have_count(0)
            expect(page.get_by_text('登录后读取材料清单',exact=True)).to_have_count(0)
            for group in ('license','legal'):
                expect(page.locator('#material-'+group+' [data-handler="upload"]').first).to_be_enabled()
            snapshot('02-admission-auto-authenticated')
            expect(page.locator('[data-handler="selectDocumentType"]').first).to_be_enabled();snapshot('03-admission-ready')
            page.locator('[data-handler="selectDocumentType"]').first.select_option('1');page.wait_for_timeout(80)
            self.assertEqual(page.evaluate('window.__nativeEvidence.state.options.doc'),'IDENTIFICATION_TYPE_OVERSEA_PASSPORT');snapshot('04-admission-passport')
            expect(page.locator('[data-handler="toggleMaterialEdit"]')).to_have_count(0)
            expect(page.locator('input[data-path="subject_info.business_license_info.merchant_name"]')).to_be_visible()
            # Inject only synthetic suggestion state into original source renderer.
            page.evaluate('window.fixtureOcrSuggestions()')
            for path in ('subject_info.business_license_info.period_begin','subject_info.business_license_info.period_end','subject_info.business_license_info.license_number'):
                expect(page.locator('input[data-path="'+path+'"]')).to_be_visible()
            expect(page.locator('input[data-path="subject_info.business_license_info.merchant_name"]')).to_have_count(0)
            # Every existing material-group edit entrance is a real, sized button.
            for edit in page.locator('[data-handler="toggleMaterialEdit"]').all():
                self.assertEqual(edit.evaluate('(e)=>e.tagName'),'BUTTON')
                metrics=edit.evaluate('(e)=>({height:e.getBoundingClientRect().height,size:parseFloat(getComputedStyle(e).fontSize),weight:parseFloat(getComputedStyle(e).fontWeight),border:parseFloat(getComputedStyle(e).borderTopWidth)})')
                self.assertGreaterEqual(metrics['height'],44)
                self.assertGreaterEqual(metrics['size'],15)
                self.assertGreaterEqual(metrics['weight'],600)
                self.assertGreater(metrics['border'],0)
            snapshot('24-all-material-edit-buttons')
            click('toggleMaterialEdit','[data-group="license"]')
            page.locator('input[data-path="subject_info.business_license_info.merchant_name"]').fill('隔离测试主体');page.wait_for_timeout(80)
            page.locator('input[data-path="contact_info.mobile_phone"]').fill('+44-123456789');page.wait_for_timeout(80)
            expect(page.locator('input[data-path="contact_info.mobile_phone"]')).to_have_attribute('aria-label','法人/经营者联系电话')
            expect(page.locator('input[data-path="contact_info.mobile_phone"]')).to_have_attribute('inputmode','tel')
            snapshot('25-contact-edit-open')
            expect(page.locator('#material-contact [data-handler="toggleMaterialEdit"]')).to_have_count(0)
            expect(page.locator('input[data-path="contact_info.mobile_phone"]')).to_have_value('+44-123456789')
            self.assertTrue(page.evaluate('window.__nativeEvidence.state.dirty'))
            snapshot('26-contact-direct-input-unsaved')
            # Same Page conditions, not DOM-only artwork or a second draft.
            page.locator('[data-handler="condition"][data-key="contact"]').select_option('1');page.wait_for_timeout(80)
            self.assertTrue(page.locator('#material-legal').is_visible());self.assertTrue(page.locator('#material-operator').is_visible());snapshot('18-super-both-identities')
            page.locator('[data-handler="condition"][data-key="ubos"]').select_option('3');page.wait_for_timeout(80)
            self.assertTrue(page.locator('#material-ubo0').is_visible());self.assertTrue(page.locator('#material-ubo1').is_visible());snapshot('19-two-beneficiaries')
            click('save');self.assertIsNotNone(page.evaluate('window.__nativeEvidence.state.application'));snapshot('05-admission-draft')
            application=page.evaluate('window.__nativeEvidence.state.application.application')
            for n,title in [(1,'06-admission-operation'),(2,'07-admission-settlement'),(3,'08-admission-progress')]:
                click('next');self.assertEqual(page.evaluate('window.__nativeEvidence.state.step'),n)
                expect(page.locator('[data-handler="back"]')).to_be_visible()
                expect(page.locator('[data-handler="back"]')).to_contain_text('上一步')
                before_back=page.evaluate('({materials:window.__nativeEvidence.state.application.materials,application:window.__nativeEvidence.state.application.application,calls:window.__nativeEvidence.calls.length})')
                click('back');self.assertEqual(page.evaluate('window.__nativeEvidence.state.step'),n-1)
                self.assertEqual(page.evaluate('window.__nativeEvidence.calls.length'),before_back['calls'])
                self.assertEqual(page.evaluate('window.__nativeEvidence.state.application.materials'),before_back['materials'])
                self.assertEqual(page.evaluate('window.__nativeEvidence.state.application.application'),before_back['application'])
                snapshot('27-back-from-step-'+str(n+1))
                click('next');self.assertEqual(page.evaluate('window.__nativeEvidence.state.step'),n)

                if n==1:
                    self.assertEqual(page.evaluate('window.__nativeEvidence.state.options.scene'),'unknown');snapshot('20-unknown-actual-scene')
                    redemption=page.locator('[data-handler="chooseRedemption"]')
                    expect(redemption).to_have_value('1')
                    redemption.select_option('0');page.wait_for_timeout(80)
                    self.assertEqual(page.evaluate('window.__nativeEvidence.state.pendingRedemptionPercent'),0)
                    snapshot('31-redemption-compact-explicit-zero')
                    click('save')
                    self.assertEqual(page.evaluate('window.__nativeEvidence.state.application.redemption_percent'),0)
                    expect(page.locator('[data-handler="chooseRedemption"]')).to_have_value('0')
                    page.locator('[data-handler="condition"][data-key="scene"]').select_option('3');page.wait_for_timeout(80)
                    self.assertEqual(page.locator('#material-store .upload-slot').count(),2);snapshot('21-both-scene-photographs')
                    picker=page.locator('[data-native-picker="multiSelector"]');expect(picker).to_be_visible()
                    picker.locator('[data-picker-open="multiSelector"]').click()
                    picker.locator('select[data-column="0"]').select_option('0');page.wait_for_timeout(80)
                    self.assertEqual(page.evaluate('window.__nativeEvidence.state.regionIndices[0]'),0)
                    page.locator('[data-picker-open="multiSelector"]').click()
                    click('chooseRegion','[data-picker-confirm="multiSelector"]')
                    self.assertNotEqual(page.evaluate('window.__nativeEvidence.state.regionLabel'),'请选择实际经营地区');snapshot('23-region-picker-fixture')
                self.assertEqual(page.evaluate('window.__nativeEvidence.state.application.application'),application);snapshot(title)
                if n==3:
                    link=page.locator('[data-handler="returnMaterial"][data-group="contact"]')
                    expect(link).to_be_visible();expect(link).to_contain_text('修改本组资料')
                    snapshot('28-final-explicit-edit-links')
                    click('returnMaterial','[data-group="contact"]')
                    expect(page.locator('input[data-path="contact_info.mobile_phone"]')).to_have_value('+44-123456789')
                    self.assertEqual(page.evaluate('window.__nativeEvidence.state.application.application'),application)
                    snapshot('29-final-return-contact')
                    for expected_step in (1,2,3):
                        click('next');self.assertEqual(page.evaluate('window.__nativeEvidence.state.step'),expected_step)

            # Synthetic submit is strictly visual/handler evidence. Real material and submit guards run in HTTP tests.
            click('returnMaterial','[data-group="legal"]');self.assertEqual(page.evaluate('window.__nativeEvidence.state.step'),0);self.assertGreaterEqual(page.locator('#material-legal').evaluate('(e)=>e.getBoundingClientRect().top'),-2);self.assertLess(page.locator('#material-legal').evaluate('(e)=>e.getBoundingClientRect().top'),100);snapshot('22-return-legal-group')
            for _ in range(3):click('next')
            click('submitAllReview');self.assertEqual(page.evaluate('window.__nativeEvidence.state.platformState'),'SUBMITTED')
            self.assertEqual(page.evaluate('window.__nativeEvidence.state.wechatReviewState'),'PENDING_INTERNAL_REVIEW');snapshot('09-admission-submitted-fixture')
            click('submitAllReview')
            review_calls=page.evaluate('window.__nativeEvidence.calls')
            self.assertEqual(sum(x.get('suboperation')=='submit' for x in review_calls),1)
            self.assertEqual(sum(x.get('suboperation')=='wechat_submit_review' for x in review_calls),1)
            for state,opening,visible in [('DRAFT','NOT_APPROVED',False),('REJECTED','NOT_APPROVED',False),('CORRECTION_REQUIRED','NOT_APPROVED',False),('APPROVED','AWAITING_CRM_BINDING',False),('APPROVED','OPENED',True)]:
                # Render-only state fixture, not a grant of original server permission.
                page.evaluate('([state,opening])=>window.fixtureApprovalView(state,opening)',[state,opening])
                expect(page.locator('[data-handler="workbench"]')).to_have_count(1 if visible else 0)
                expect(page.locator('[data-handler="back"]')).to_have_text('返回上一步')
                snapshot('30-final-state-'+state+'-'+opening)
            click('workbench');snapshot('14-workbench-no-store');self.assertEqual(page.evaluate('window.__nativeEvidence.state.workspace'),'')
            expect(page.locator('[data-handler="showCollection"]')).to_have_count(0)
            expect(page.locator('.merchant-hero')).to_have_count(0)
            click('goProfile');snapshot('15-back-profile')
            click('navigateSection','[data-section="orders"]');expect(page.get_by_text('我的订单',exact=True)).to_be_visible();snapshot('10-orders-no-store')
            click('navigateSection','[data-section="recommendations"]');snapshot('11-recommendations-no-store')
            self.assertEqual(page.locator('[data-handler="openMerchantJoin"]').count(),0)
            click('navigateSection','[data-section="profile"]');click('openMerchantEntry')
            expect(page.get_by_text('开启您的邻里生意',exact=True)).to_be_visible();click('goBack');snapshot('12-back-profile')
            click('navigateSection','[data-section="services"]');snapshot('16-more-services-no-store')
            click('openCustomerHome');click('navigateSection','[data-section="profile"]')
            # Fail automatic entry first; its visible retry must remain safe too.
            before_failure=page.evaluate('window.__nativeEvidence.calls')
            page.evaluate('window.fixtureFailure(true)');click('openMerchantEntry')
            self.assertFalse(page.evaluate('window.__nativeEvidence.state.ready'))
            expect(page.locator('[data-handler="retryApplicantRead"]')).to_be_visible()
            expect(page.locator('[data-handler="connectApplicant"]')).to_have_count(0)
            click('retryApplicantRead')
            failure=page.evaluate('window.__nativeEvidence')
            self.assertTrue(failure['state']['authenticated'])
            self.assertEqual(failure['state']['readState'],'FAILED')
            self.assertEqual(sum(x.get('operation')=='wx.login' for x in failure['calls']),1)
            self.assertFalse(failure['state']['pending'])
            self.assertIsNone(failure['state']['application'])
            self.assertEqual(failure['state']['catalog'],[])
            self.assertEqual([x.get('suboperation') for x in failure['calls'][len(before_failure):]],['catalog','catalog'])
            for group in ('license','legal'):
                expect(page.locator('#material-'+group+' [data-handler="upload"]').first).to_be_disabled()
            expect(page.locator('[data-handler="selectDocumentType"]').first).to_be_disabled()
            self.assertFalse(page.evaluate('window.__nativeEvidence.state.ready'));snapshot('17-login-error')
            calls=page.evaluate('window.__nativeEvidence.calls')
            # Original no-store navigation makes these scoped read attempts, not business writes.
            customer_reads=[x for x in calls if x.get('url','').endswith('/mini/api')]
            customer_operations=[x.get('operation') for x in customer_reads]
            self.assertIn('customer.directory',customer_operations)
            self.assertGreaterEqual(customer_operations.count('customer.contexts'),2)
            self.assertTrue(set(customer_operations)<= {'customer.contexts','customer.directory'})
            self.assertTrue(all(x.get('url')=='https://fixture.invalid/mini/api' and x.get('scene')=='' for x in customer_reads))
            # Failed admission and its retry cannot spill into any customer API or write action.
            self.assertFalse(any(x.get('url','').endswith('/mini/api') for x in failure['calls'][len(before_failure):]))
            self.assertFalse(any(x.get('suboperation') in ('wechat_execute','wechat_query','refund_execute') for x in calls))
            self.assertEqual(errors,[])
            report=dict(kind='ISOLATED_CHROMIUM_ACTUAL_NATIVE_SOURCE_PROJECTION',wechat_device='NOT_EXECUTED',provider='SYNTHETIC_TEST_SUBSTITUTE',platform_identity='SYNTHETIC_ACCOUNT_INFO_MATCH_NOT_REAL_WECHAT',picker='TEST_ONLY_COMPOSITE_MULTISELECTOR_NOT_WECHAT',http_acceptance='SEPARATE_REAL_ORIGINAL_HTTP_TEST',customer_acceptance=False,source_html_sha256=hashlib.sha256(html.read_bytes()).hexdigest(),records=records,calls=calls)
            (out/'NATIVE_RENDER_RECEIPT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            browser.close()
