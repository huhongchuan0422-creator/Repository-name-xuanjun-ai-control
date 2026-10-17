"""Chromium -> real HTTP -> original encrypted SQLite/private documents.

Accounts, reviewer grant, documents and scanner are explicit synthetic fixtures.
The original Center connection is created and used on the server thread.
"""
import queue
import threading
import unittest
from playwright.sync_api import sync_playwright,expect
import test_community_merchant_onboarding as fixture
from scripts.community_merchant_onboarding import BASE
from scripts.community_mini_http import serve
from scripts.community_center_operations import CenterOperations
from scripts.community_merchant_store import open_store

class OnboardingBrowserJourney(unittest.TestCase):
    def test_apply_upload_correction_resubmit_per_material_review_approve(self):
        self.journey(False)
    def test_bound_crm_mapping_automatically_opens_workbench_after_approval(self):
        self.journey(True)
    def journey(self,with_opening):
        ready=queue.Queue()
        def host():
            server=None;merchant_db=None;fx=None
            try:
                fx=fixture.MerchantAdmissionJourney();fx.setUp()
                center=fx.fx.center;gateway=fx.fx.gateway;service=fx.service
                operations=None
                if with_opening:
                    merchant_db=open_store(fx.fx.tmp.name+'/browser-new-merchant.sqlite')
                    fx.fx.stage.demo.merchant_db=merchant_db
                    operations=CenterOperations(center,fx.fx.stage.api,{'new_merchant':{
                        'user_id':fx.fx.uid1,'project':'project1','project_roles':['OWNER'],
                        'principal':fx.fx.stage.merchant,'onboarding_required':True}},onboarding=service)
                    service.operations=operations
                server=serve(gateway,onboarding=service,operations=operations);ready.put((server,fx));server.serve_forever(poll_interval=.05)
            except BaseException as error:ready.put(error)
            finally:
                if server:server.server_close()
                if merchant_db:merchant_db.close()
                if fx:fx.tearDown()
        thread=threading.Thread(target=host,daemon=True);thread.start();state=ready.get(timeout=10)
        if isinstance(state,BaseException):raise state
        server,fx=state
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                try:
                    applicant=browser.new_context(extra_http_headers={'X-Center-Session':fx.applicant['token']})
                    review=browser.new_context(extra_http_headers={'X-Center-Session':fx.reviewer['token']})
                    page=applicant.new_page();admin=review.new_page();errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)));admin.on('pageerror',lambda error:errors.append(str(error)))
                    base='http://127.0.0.1:'+str(server.server_port)
                    def open_page(target,path,csrf):
                        target.goto(base+path);expect(target.locator('#status')).to_contain_text('请先登录')
                        target.evaluate('csrf=>window.configureCommunityOnboarding({csrf})',csrf)
                    open_page(page,'/merchant/join',fx.applicant['csrf'])
                    for key,value in fx.fields.items():page.locator('#'+key).fill(value)
                    page.locator('#saveDraft').click();expect(page.locator('#status')).to_contain_text('草稿已保存')
                    def upload(kind,content=b'%PDF-synthetic admission document'):
                        row=page.locator('[data-kind="'+kind+'"]')
                        row.locator('input[type=file]').set_input_files({'name':'fixture.pdf','mimeType':'application/pdf','buffer':content})
                        with page.expect_response(lambda response:response.url.endswith('/merchant/onboarding')):
                            row.get_by_role('button',name='上传资料',exact=True).click()
                        expect(row.locator('p')).to_contain_text('已上传')
                    for kind in BASE:upload(kind)
                    page.locator('#submitApplication').click();expect(page.locator('#applicationState')).to_have_text('待审核')
                    open_page(admin,'/merchant/review',fx.reviewer['csrf'])
                    admin.locator('#applications button').first.click();expect(admin.locator('#applicationState')).to_have_text('待审核')
                    admin.locator('#note').fill('请更新清晰的门头照片')
                    admin.locator('[data-kind=storefront_photo]').get_by_role('button',name='资料需补充',exact=True).click()
                    expect(admin.locator('[data-kind=storefront_photo] p')).to_contain_text('需要补件')
                    admin.locator('[data-action=CORRECTION]').click();expect(admin.locator('#applicationState')).to_have_text('待补件')
                    page.locator('#reloadMine').click();expect(page.locator('#applicationState')).to_have_text('待补件')
                    expect(page.locator('#reviewNote')).to_contain_text('请更新清晰的门头照片')
                    upload('storefront_photo',b'%PDF-updated synthetic storefront')
                    page.locator('#submitApplication').click();expect(page.locator('#applicationState')).to_have_text('待审核')
                    admin.locator('#reloadQueue').click();expect(admin.locator('#applications button').first).to_contain_text('待审核')
                    admin.locator('#applications button').first.click();admin.locator('#note').fill('本份资料核对通过')
                    for kind in BASE:
                        row=admin.locator('[data-kind="'+kind+'"]');row.get_by_role('button',name='资料通过',exact=True).click()
                        expect(row.locator('p')).to_contain_text('资料审核通过')
                    admin.locator('[data-action=APPROVE]').click();expect(admin.locator('#applicationState')).to_have_text('入驻审核通过')
                    page.locator('#reloadMine').click();expect(page.locator('#applicationState')).to_have_text('入驻审核通过')
                    expect(page.locator('#opening')).to_contain_text('商家工作台已开通' if with_opening else '工作台权限待绑定')
                    if with_opening:
                        reply=page.evaluate('''async csrf=>{
                          const r=await fetch('/community/operations',{method:'POST',headers:{'Content-Type':'application/json','X-Center-CSRF':csrf},
                            body:JSON.stringify({workspace:'new_merchant',operation:'community.orders',params:{}})});
                          return {status:r.status,body:await r.json()};
                        }''',fx.applicant['csrf'])
                        self.assertEqual(reply['status'],200);self.assertEqual(reply['body']['result']['orders'],[])
                    expect(page.locator('#saveDraft')).to_be_disabled()
                    for width in (360,768,1440):
                        page.set_viewport_size({'width':width,'height':900})
                        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                    self.assertEqual(errors,[])
                finally:browser.close()
        finally:server.shutdown();thread.join(5)

if __name__=='__main__':unittest.main()
