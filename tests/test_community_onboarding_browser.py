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
    def test_reject_reopen_same_application_resubmit_and_fresh_material_reviews(self):
        ready=queue.Queue()
        def host():
            server=None;fx=None
            try:
                fx=fixture.MerchantAdmissionJourney();fx.setUp()
                server=serve(fx.fx.gateway,onboarding=fx.service);ready.put((server,fx));server.serve_forever(poll_interval=.05)
            except BaseException as error:ready.put(error)
            finally:
                if server:server.server_close()
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
                    def revision(target):
                        text=target.locator('#applicationVersion').inner_text()
                        return int(text.rsplit(' ',1)[-1])
                    def application(target):
                        text=target.locator('#applicationVersion').inner_text()
                        return text.split(' · ',1)[0].replace('申请编号 ','')
                    def upload(kind,content):
                        row=page.locator('[data-kind="'+kind+'"]')
                        row.locator('input[type=file]').set_input_files({'name':'fixture.pdf','mimeType':'application/pdf','buffer':content})
                        with page.expect_response(lambda response:response.url.endswith('/merchant/onboarding')):
                            row.get_by_role('button',name='上传资料',exact=True).click()
                        expect(row.locator('p')).to_contain_text('已上传')

                    open_page(page,'/merchant/join',fx.applicant['csrf'])
                    for key,value in fx.fields.items():page.locator('#'+key).fill(value)
                    page.locator('#saveDraft').click();expect(page.locator('#status')).to_contain_text('草稿已保存')
                    for kind in BASE:upload(kind,b'%PDF-synthetic '+kind.encode())
                    original_id=application(page);submitted_from=revision(page)
                    page.locator('#submitApplication').click();expect(page.locator('#applicationState')).to_have_text('待审核')
                    submitted_revision=revision(page);self.assertGreater(submitted_revision,submitted_from)

                    open_page(admin,'/merchant/review',fx.reviewer['csrf'])
                    admin.locator('#applications button').first.click();expect(admin.locator('#applicationState')).to_have_text('待审核')
                    self.assertEqual(application(admin),original_id)
                    reject_before=revision(admin)
                    admin.locator('#note').fill('资料整体不符合当前入驻要求，请补充后重新提交')
                    admin.locator('[data-action=REJECT]').click();expect(admin.locator('#applicationState')).to_have_text('已驳回')
                    rejected_revision=revision(admin);self.assertGreater(rejected_revision,reject_before)

                    page.locator('#reloadMine').click();expect(page.locator('#applicationState')).to_have_text('已驳回')
                    self.assertEqual(application(page),original_id)
                    expect(page.locator('#reviewNote')).to_contain_text('资料整体不符合当前入驻要求')
                    page.locator('#loadHistory').click();expect(page.locator('#historyStatus')).to_contain_text('历史已读取至末页')
                    expect(page.locator('#historyRows')).to_contain_text('REJECT')
                    expect(page.locator('#historyRows')).to_contain_text('资料整体不符合当前入驻要求')
                    page.locator('#loadAdmissionNotices').click();expect(page.locator('#admissionNoticeStatus')).to_contain_text('已读取本申请通知')
                    expect(page.locator('#admissionNotices')).to_contain_text('申请已驳回')

                    admin.locator('#note').fill('允许原申请号重新开启补件')
                    admin.locator('[data-action=REOPEN]').click();expect(admin.locator('#applicationState')).to_have_text('待补件')
                    reopened_revision=revision(admin);self.assertGreater(reopened_revision,rejected_revision)
                    self.assertEqual(application(admin),original_id)

                    page.locator('#reloadMine').click();expect(page.locator('#applicationState')).to_have_text('待补件')
                    self.assertEqual(application(page),original_id)
                    page.locator('#loadHistory').click();expect(page.locator('#historyRows')).to_contain_text('REOPEN')
                    expect(page.locator('#historyRows')).to_contain_text('允许原申请号重新开启补件')
                    page.locator('#loadAdmissionNotices').click();expect(page.locator('#admissionNotices')).to_contain_text('已重新开启补件')
                    upload('storefront_photo',b'%PDF-reopened replacement storefront')
                    changed_revision=revision(page);self.assertGreater(changed_revision,reopened_revision)
                    page.locator('#submitApplication').click();expect(page.locator('#applicationState')).to_have_text('待审核')
                    resubmitted_revision=revision(page);self.assertGreater(resubmitted_revision,changed_revision)
                    self.assertEqual(application(page),original_id)

                    admin.locator('#reloadQueue').click();admin.locator('#applications button').first.click()
                    expect(admin.locator('#applicationState')).to_have_text('待审核');self.assertEqual(application(admin),original_id)
                    before_unreviewed=revision(admin)
                    admin.locator('#note').fill('不得跳过逐份复审')
                    def is_unreviewed_approve(response):
                        if not response.url.endswith('/merchant/onboarding') or response.request.method!='POST':
                            return False
                        try: body=response.request.post_data_json
                        except BaseException: return False
                        return body.get('operation')=='review' and body.get('params',{}).get('action')=='APPROVE' and \
                            body.get('params',{}).get('application')==original_id and body.get('params',{}).get('revision')==before_unreviewed
                    with admin.expect_response(is_unreviewed_approve) as rejected:
                        admin.locator('[data-action=APPROVE]').click()
                    response=rejected.value
                    self.assertEqual(response.status,400)
                    reply=response.json()
                    self.assertEqual(reply.get('error'),'INVALID_REQUEST')
                    expect(admin.locator('#status')).to_contain_text('资料、状态或版本不符合要求')
                    expect(admin.locator('[data-action=APPROVE]')).to_be_enabled()
                    admin.locator('#reloadQueue').click()
                    admin.locator('#applications button').first.click()
                    expect(admin.locator('#applicationState')).to_have_text('待审核')
                    self.assertEqual(application(admin),original_id)
                    self.assertEqual(revision(admin),before_unreviewed)
                    self.assertNotIn('入驻审核通过',admin.locator('#applicationState').inner_text())

                    for kind in BASE:
                        row=admin.locator('[data-kind="'+kind+'"]')
                        admin.locator('#note').fill('重开后逐份复审通过 '+kind)
                        row.get_by_role('button',name='资料通过',exact=True).click()
                        expect(row.locator('p')).to_contain_text('资料审核通过')
                    reviewed_revision=revision(admin);self.assertGreater(reviewed_revision,resubmitted_revision)
                    admin.locator('#note').fill('重开申请逐份复审完成')
                    admin.locator('[data-action=APPROVE]').click();expect(admin.locator('#applicationState')).to_have_text('入驻审核通过')
                    approved_revision=revision(admin);self.assertGreater(approved_revision,reviewed_revision)

                    page.locator('#reloadMine').click();expect(page.locator('#applicationState')).to_have_text('入驻审核通过')
                    self.assertEqual(application(page),original_id)
                    page.locator('#loadHistory').click()
                    expect(page.locator('#historyStatus')).to_contain_text('历史已读取至末页')
                    history=page.locator('#historyRows').inner_text()
                    self.assertIn('REJECT',history);self.assertIn('REOPEN',history)
                    self.assertIn('资料整体不符合当前入驻要求',history)
                    self.assertIn('允许原申请号重新开启补件',history)
                    self.assertEqual(errors,[])
                finally:browser.close()
        finally:server.shutdown();thread.join(5)

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
