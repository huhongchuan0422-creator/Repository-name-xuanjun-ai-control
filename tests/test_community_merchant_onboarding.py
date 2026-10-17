"""Existing encrypted Center and onboarding workflow, synthetic private files."""
import base64
import concurrent.futures
import json
import unittest
import urllib.request
from scripts.community_merchant_onboarding import MerchantOnboarding,BASE
from scripts.community_mini_http import serve
import test_community_mini_center_identity as center_fixture

class MerchantAdmissionJourney(unittest.TestCase):
    def setUp(self):
        self.fx=center_fixture.ExistingCenterComposition();self.fx.setUp()
        self.applicant=self.fx.center.login('one@example.org','FixturePassword123!')
        self.reviewer=self.fx.center.login('two@example.org','FixturePassword123!')
        self.fx.center.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(self.fx.uid2,))
        self.fx.center.scanner=lambda raw:True
        self.service=MerchantOnboarding(self.fx.center,{self.fx.uid2:'project1'})
        self.fields={'legal_name':'Synthetic Merchant','store_name':'Fixture Store','address':'Fixture Address','contact':'Fixture Contact'}
    def tearDown(self):self.fx.tearDown()
    def call(self,op,params=None,review=False):
        web=self.reviewer if review else self.applicant
        return self.service.dispatch(web['token'],web['csrf'],{'operation':op,'params':params or {}})
    def draft(self,previous=None,**changes):
        params={'application':None if previous is None else previous['application'],
                'revision':0 if previous is None else previous['revision'],'fields':dict(self.fields),
                'entity_type':'ENTERPRISE','category':'GENERAL','delegated':False}
        params.update(changes);return self.call('save',params)
    def upload(self,app,kind,raw=b'%PDF-fixture private document',**changes):
        params={'application':app['application'],'revision':app['revision'],'kind':kind,
            'content_base64':base64.b64encode(raw).decode(),'expires_at':None}
        params.update(changes);return self.call('upload',params)
    def complete(self,**changes):
        app=self.draft(**changes)
        for kind in app['required_materials']:app=self.upload(app,kind)
        return self.call('submit',{'application':app['application'],'revision':app['revision']})
    def review(self,app,action,note='Fixture review reason'):
        if action=='APPROVE':
            for kind in app['required_materials']:
                app=self.call('review_material',{'application':app['application'],'revision':app['revision'],
                    'kind':kind,'decision':'ACCEPTED','note':'Fixture material checked'},True)
        return self.call('review',{'application':app['application'],'revision':app['revision'],
            'action':action,'note':note},True)
    def test_complete_application_materials_review_and_approval(self):
        app=self.complete();self.assertEqual(app['status'],'SUBMITTED')
        self.assertEqual(len(self.call('review_list',review=True)['applications']),1)
        approved=self.review(app,'APPROVE')
        self.assertEqual(approved['status'],'APPROVED')
        self.assertEqual(approved['opening_state'],'AWAITING_CRM_BINDING')
        self.assertFalse(approved['payment_enabled'])
        self.assertEqual(approved['wechat_submerchant_state'],'NOT_VERIFIED')
        self.assertEqual(self.fx.center.check_integrity()['integrity'],'PASS')
    def test_correction_edit_resubmit_and_rejection_preserve_versions(self):
        app=self.review(self.complete(),'CORRECTION','请补充清晰门头照片')
        self.assertEqual(app['reviewer_note'],'请补充清晰门头照片')
        app=self.upload(app,'storefront_photo',b'%PDF-new storefront fixture')
        app=self.call('submit',{'application':app['application'],'revision':app['revision']})
        app=self.review(app,'REJECT','资料与门店不一致')
        self.assertEqual(app['status'],'REJECTED')
        with self.assertRaises(ValueError):self.draft(app)
        self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM versions WHERE project=? AND item=?',(app['application'],'storefront_photo')).fetchone()[0],2)
    def test_partial_draft_and_material_requirement_before_submit(self):
        app=self.draft(fields=dict(self.fields,contact=''))
        with self.assertRaisesRegex(ValueError,'MATERIAL_MISSING'):
            self.call('submit',{'application':app['application'],'revision':app['revision']})
        self.assertEqual(self.call('mine')['applications'][0]['status'],'DRAFT')
    def test_delegated_and_food_have_conditional_material_lists(self):
        app=self.draft(entity_type='SOLE_PROPRIETOR',category='FOOD',delegated=True)
        self.assertEqual(set(app['required_materials']),set(BASE)|{'operator_authorization','operator_identity','industry_permit'})
    def test_materials_and_profile_are_encrypted_at_rest(self):
        app=self.upload(self.draft(),'business_license')
        db=self.fx.center.db
        payload=db.execute('SELECT payload FROM onboarding').fetchone()[0]
        self.assertNotIn('Synthetic Merchant',payload)
        link=db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_ONBOARDING'").fetchone()[0]
        self.assertNotIn(b'object_id',bytes(link) if type(link) is bytes else link.encode())
        for path in self.fx.center.objects.iterdir():self.assertNotIn(b'fixture private document',path.read_bytes())
        result=self.call('download',{'application':app['application'],'kind':'business_license'})
        self.assertEqual(base64.b64decode(result['content_base64']),b'%PDF-fixture private document')
    def test_other_account_cannot_edit_read_or_claim_application(self):
        app=self.draft();web=self.reviewer
        body={'operation':'save','params':{'application':app['application'],'revision':app['revision'],
            'fields':self.fields,'entity_type':'ENTERPRISE','category':'GENERAL','delegated':False}}
        with self.assertRaises(PermissionError):self.service.dispatch(web['token'],web['csrf'],body)
        self.assertEqual(self.service.dispatch(web['token'],web['csrf'],{'operation':'mine','params':{}})['applications'],[])
    def test_applicant_cannot_review_self_and_revoked_reviewer_cannot_read(self):
        app=self.complete()
        with self.assertRaises(PermissionError):self.call('review_list')
        self.fx.center.db.execute("UPDATE members SET active=0 WHERE user_id=?",(self.fx.uid2,))
        with self.assertRaises(PermissionError):self.review(app,'APPROVE')
    def test_scan_unknown_bad_format_secret_and_expiry_fail_closed(self):
        app=self.draft()
        for raw in (b'not a document',b'%PDF-----BEGIN PRIVATE KEY-----'):
            with self.assertRaises((ValueError,PermissionError)):self.upload(app,'business_license',raw)
        self.fx.center.scanner=lambda raw:None
        with self.assertRaises(PermissionError):self.upload(app,'business_license')
        self.fx.center.scanner=None
        with self.assertRaises(RuntimeError):self.upload(app,'business_license')
        self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM objects').fetchone()[0],0)
    def test_expired_document_blocks_approval_and_stale_revision_blocks_write(self):
        app=self.draft()
        for kind in app['required_materials']:
            app=self.upload(app,kind,expires_at=self.fx.stage.now+1)
        submitted=self.call('submit',{'application':app['application'],'revision':app['revision']})
        with self.assertRaises(ValueError):self.upload(app,'business_license')
        self.fx.stage.now+=2
        with self.assertRaisesRegex(ValueError,'MATERIAL_MISSING_OR_EXPIRED'):self.review(submitted,'APPROVE')
    def test_session_csrf_and_actor_fields_cannot_be_self_asserted(self):
        with self.assertRaises(PermissionError):self.service.dispatch(self.applicant['token'],'',{'operation':'mine','params':{}})
        with self.assertRaises(ValueError):self.service.dispatch(self.applicant['token'],self.applicant['csrf'],{'operation':'mine','params':{},'role':'REVIEWER'})
    def test_final_approval_requires_every_current_material_review(self):
        app=self.complete()
        with self.assertRaisesRegex(ValueError,'MATERIAL_REVIEW_REQUIRED'):
            self.call('review',{'application':app['application'],'revision':app['revision'],'action':'APPROVE','note':'已核对'},True)
        app=self.call('review',{'application':app['application'],'revision':app['revision'],'action':'BEGIN_REVIEW','note':'开始审核'},True)
        self.assertEqual(app['status'],'IN_REVIEW')
    def test_even_a_configured_reviewer_cannot_approve_own_application(self):
        app=self.complete()
        self.fx.center.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(self.fx.uid1,))
        self.service.reviewers[self.fx.uid1]='project1'
        with self.assertRaises(PermissionError):
            self.call('review_material',{'application':app['application'],'revision':app['revision'],
                'kind':'business_license','decision':'ACCEPTED','note':'self review'})
    def test_replacement_file_invalidates_previous_material_review(self):
        app=self.complete()
        app=self.call('review_material',{'application':app['application'],'revision':app['revision'],
            'kind':'business_license','decision':'ACCEPTED','note':'checked'},True)
        app=self.review(app,'CORRECTION','请更新门头')
        app=self.upload(app,'business_license',b'%PDF-new license fixture')
        self.assertEqual(app['materials']['business_license']['review'],'PENDING')
    def test_original_account_without_project_can_apply_and_original_state_survives_reopen(self):
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        app=self.draft()
        self.fx.reopen();self.service=MerchantOnboarding(self.fx.center,{self.fx.uid2:'project1'})
        restored=self.call('mine')['applications'][0]
        self.assertEqual(restored['application'],app['application']);self.assertEqual(restored['fields'],self.fields)
    def test_real_http_existing_cookie_and_csrf_route(self):
        server=serve(self.fx.gateway,onboarding=self.service)
        try:
            def request():
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/merchant/onboarding',
                    data=json.dumps({'operation':'mine','params':{}}).encode(),headers={'Content-Type':'application/json',
                        'Cookie':'__Host-xj_customer='+self.applicant['token'],'X-CSRF-Token':self.applicant['csrf']})
                with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(request);server.handle_request();result=future.result()
            self.assertEqual(result['result']['applications'],[])
        finally:server.server_close()

if __name__=='__main__':unittest.main()
