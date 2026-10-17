"""Original Center/merchant SQLite opening, revocation and unknown recovery."""
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as fixture
from scripts.community_center_operations import CenterOperations
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_merchant_opening import open_workbench
from scripts.community_merchant_store import open_store,upsert_profile

class AdmittedMerchantOpening(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.MerchantAdmissionJourney();self.fx.setUp()
        self.db=open_store(self.fx.fx.tmp.name+'/new-merchant.sqlite')
        self.fx.fx.stage.demo.merchant_db=self.db
        self.grants={'merchant':{'user_id':self.fx.fx.uid1,'project':'project1',
            'project_roles':['OWNER'],'principal':self.fx.fx.stage.merchant,'onboarding_required':True}}
        self.configure()
    def tearDown(self):self.db.close();self.fx.tearDown()
    def configure(self):
        self.operations=CenterOperations(self.fx.fx.center,self.fx.fx.stage.api,self.grants,onboarding=self.fx.service)
        self.fx.service.operations=self.operations
    def operate(self):
        return self.operations.dispatch(self.fx.applicant['token'],self.fx.applicant['csrf'],
            {'workspace':'merchant','operation':'community.orders','params':{}})
    def approve(self):return self.fx.review(self.fx.complete(),'APPROVE')
    def open(self,app,workspace='merchant'):
        return self.fx.call('open_workbench',{'application':app['application'],'revision':app['revision'],'workspace':workspace},True)
    def latest(self):return self.fx.call('mine')['applications'][0]
    def test_new_registered_grant_denied_until_approved_and_opened(self):
        with self.assertRaises(PermissionError):self.operate()
        app=self.approve();self.assertEqual(app['opening_state'],'OPENED')
        self.assertEqual(self.operate()['orders'],[])
        self.assertFalse(app['payment_enabled']);self.assertEqual(app['wechat_submerchant_state'],'NOT_VERIFIED')
        self.assertEqual(self.db.execute('SELECT status FROM merchant_profiles').fetchone()[0],'PAUSED')
        self.assertEqual(self.fx.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],2)
    def test_duplicate_opening_keeps_profile_edits_and_does_not_recreate(self):
        app=self.approve()
        self.db.execute("UPDATE merchant_profiles SET name='Edited after opening',version=2");self.db.commit()
        result=open_workbench(self.fx.service,self.operations,self.fx.fx.uid2,app['application'],'merchant',app['revision'])
        self.assertTrue(result['duplicate'])
        self.assertEqual(self.db.execute('SELECT name,version FROM merchant_profiles').fetchone(),('Edited after opening',2))
    def test_profile_write_failure_retains_reservation_and_explicit_retry_finishes(self):
        with patch('scripts.community_merchant_opening.upsert_profile',side_effect=RuntimeError('fixture interruption')):
            with self.assertRaises(RuntimeError):self.approve()
        app=self.latest();self.assertEqual(app['status'],'APPROVED');self.assertEqual(app['opening_state'],'OPENING_PENDING')
        with self.assertRaises(PermissionError):self.operate()
        self.assertEqual(self.db.execute('SELECT count(*) FROM merchant_profiles').fetchone()[0],0)
        result=self.open(app);self.assertEqual(result['opening_state'],'OPENED');self.operate()
    def test_failure_after_profile_commit_recovers_without_second_profile(self):
        original=self.fx.fx.center.audit
        def audit(project,actor,kind,obj):
            if kind=='MERCHANT_OPENING_COMPLETED':raise RuntimeError('fixture audit failure')
            return original(project,actor,kind,obj)
        with patch.object(self.fx.fx.center,'audit',side_effect=audit):
            with self.assertRaises(RuntimeError):self.approve()
        app=self.latest();self.assertEqual(app['opening_state'],'OPENING_PENDING')
        self.assertEqual(self.db.execute('SELECT count(*) FROM merchant_profiles').fetchone()[0],1)
        self.assertEqual(self.open(app)['opening_state'],'OPENED')
        self.assertEqual(self.db.execute('SELECT count(*) FROM merchant_profiles').fetchone()[0],1)
    def test_center_reopen_keeps_pending_reservation_and_original_sessions(self):
        with patch('scripts.community_merchant_opening.upsert_profile',side_effect=RuntimeError('fixture interruption')):
            with self.assertRaises(RuntimeError):self.approve()
        self.fx.fx.reopen()
        self.db.close();self.db=open_store(self.fx.fx.tmp.name+'/new-merchant.sqlite')
        self.fx.fx.stage.demo.merchant_db=self.db
        self.fx.service=MerchantOnboarding(self.fx.fx.center,{self.fx.fx.uid2:'project1'});self.configure()
        self.assertEqual(self.open(self.latest())['opening_state'],'OPENED');self.operate()
    def test_applicant_unknown_target_and_stale_revision_cannot_open(self):
        app=self.approve()
        with self.assertRaises(PermissionError):
            self.fx.call('open_workbench',{'application':app['application'],'revision':app['revision'],'workspace':'merchant'})
        with self.assertRaises(PermissionError):self.open(app,'unknown')
        with self.assertRaises(PermissionError):self.open(dict(app,revision=app['revision']-1))
    def test_existing_profile_without_reservation_is_never_claimed(self):
        identity=self.fx.fx.stage.api.bindings[self.fx.fx.stage.merchant]
        upsert_profile(self.db,identity,dict(identity,authenticated=True,role='MERCHANT_ADMIN'),
            {'name':'Historical merchant','description':'Original data','contact':'Original contact','status':'ACTIVE'})
        with self.assertRaisesRegex(PermissionError,'EXISTING_MERCHANT_CANNOT_BE_CLAIMED'):self.approve()
        with self.assertRaises(PermissionError):self.operate()
        self.assertEqual(self.db.execute('SELECT name FROM merchant_profiles').fetchone()[0],'Historical merchant')
    def test_project_revocation_and_scope_changes_revoke_open_workbench(self):
        self.approve();self.operate()
        self.fx.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid1,))
        with self.assertRaises(PermissionError):self.operate()
        self.assertEqual(self.latest()['opening_state'],'ACCESS_SUSPENDED')
        self.fx.fx.center.db.execute('UPDATE members SET active=1 WHERE user_id=?',(self.fx.fx.uid1,))
        self.fx.fx.stage.api.bindings[self.fx.fx.stage.merchant]['store_id']='another_store'
        with self.assertRaises(PermissionError):self.operate()
    def test_disabled_opening_record_does_not_reactivate_on_retry(self):
        app=self.approve()
        self.fx.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_MERCHANT_OPENING'")
        with self.assertRaises(PermissionError):self.operate()
        with self.assertRaises(PermissionError):self.open(app)
    def test_second_application_cannot_take_over_same_store_reservation(self):
        first=self.approve()
        with self.assertRaisesRegex(PermissionError,'ALREADY_RESERVED'):self.approve()
        self.operate()
        self.assertEqual(self.fx.fx.center.db.execute("SELECT count(*) FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING'").fetchone()[0],1)
        self.assertEqual(self.fx.service._load(first['application'],self.fx.fx.uid1)[2]['status'],'APPROVED')
    def test_required_material_expiry_suspends_previously_opened_workbench(self):
        app=self.fx.draft()
        for kind in app['required_materials']:app=self.fx.upload(app,kind,expires_at=self.fx.fx.stage.now+1)
        app=self.fx.call('submit',{'application':app['application'],'revision':app['revision']})
        app=self.fx.review(app,'APPROVE');self.operate()
        self.fx.fx.stage.now+=2
        with self.assertRaises(PermissionError):self.operate()
        self.assertEqual(self.latest()['opening_state'],'ACCESS_SUSPENDED')
    def test_mismatched_crm_tenant_never_creates_profile_or_opening_record(self):
        from scripts.community_saas_phase2 import Principal
        p=Principal('tenant2','MERCHANT_ADMIN')
        self.fx.fx.stage.api.bindings[p]={'tenant_id':'tenant2','merchant_id':'other_merchant','store_id':'other_store'}
        self.grants['merchant']['principal']=p;self.configure()
        with self.assertRaisesRegex(PermissionError,'PROJECT_TENANT_MISMATCH'):self.approve()
        self.assertEqual(self.db.execute('SELECT count(*) FROM merchant_profiles').fetchone()[0],0)
        self.assertEqual(self.fx.fx.center.db.execute("SELECT count(*) FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING'").fetchone()[0],0)
    def test_reverification_revokes_then_reopens_without_overwriting_merchant_edits(self):
        app=self.approve()
        self.db.execute("UPDATE merchant_profiles SET name='Merchant edited profile',version=7");self.db.commit()
        app=self.fx.review(app,'CORRECTION','证件需要重新核验')
        with self.assertRaises(PermissionError):self.operate()
        app=self.fx.upload(app,'business_license',b'%PDF-reverified license fixture')
        app=self.fx.call('submit',{'application':app['application'],'revision':app['revision']})
        app=self.fx.review(app,'APPROVE');self.assertEqual(app['opening_state'],'OPENED');self.operate()
        self.assertEqual(self.db.execute('SELECT name,version FROM merchant_profiles').fetchone(),('Merchant edited profile',7))
        self.assertEqual(self.fx.fx.center.db.execute("SELECT count(*) FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING'").fetchone()[0],1)
    def test_reopening_unknown_preserves_old_profile_until_explicit_recovery(self):
        app=self.fx.review(self.approve(),'CORRECTION','重新核验经营材料')
        app=self.fx.upload(app,'business_license',b'%PDF-reverified license fixture')
        app=self.fx.call('submit',{'application':app['application'],'revision':app['revision']})
        original=self.fx.fx.center.audit
        def audit(project,actor,kind,obj):
            if kind=='MERCHANT_OPENING_COMPLETED':raise RuntimeError('fixture reopened audit failure')
            return original(project,actor,kind,obj)
        with patch.object(self.fx.fx.center,'audit',side_effect=audit):
            with self.assertRaises(RuntimeError):self.fx.review(app,'APPROVE')
        app=self.latest();self.assertEqual(app['opening_state'],'OPENING_PENDING')
        with self.assertRaises(PermissionError):self.operate()
        self.assertEqual(self.open(app)['opening_state'],'OPENED')
        self.assertEqual(self.db.execute('SELECT count(*) FROM merchant_profiles').fetchone()[0],1)

if __name__=='__main__':unittest.main()
