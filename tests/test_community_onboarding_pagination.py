"""Bounded original-DB admission queues; seeded metadata is synthetic."""
import unittest
import test_community_merchant_onboarding as fixture
from scripts import community_onboarding_offline as workflow

class AdmissionQueuePagination(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.MerchantAdmissionJourney();self.fx.setUp()
        initial=self.fx.draft();uid=self.fx.fx.uid1;service=self.fx.service;c=self.fx.fx.center
        _,meta,data=service._load(initial['application'],uid)
        # Populate fixtures without pretending these are submitted real accounts
        # or uploaded/verified business documents; only listing is under test.
        with c.tx():
            for i in range(60):
                app='ma_'+format(i,'032x')
                workflow.save_draft(c.db,uid,app,uid,data['fields'],
                    encode=lambda value,app=app:service._encode(value,'onboarding-fields:'+app),manage_transaction=False)
                service._meta(app,uid,meta)
            c.db.execute("UPDATE onboarding SET status='REJECTED' WHERE application=?",('ma_'+format(0,'032x'),))
    def tearDown(self):self.fx.tearDown()
    def test_queue_and_mine_page_all_rows_without_duplicates(self):
        for review in (False,True):
            first=self.fx.call('review_list' if review else 'mine',review=review)
            second=self.fx.call('review_list' if review else 'mine',{'cursor':first['next_cursor']},review)
            self.assertEqual(len(first['applications']),50);self.assertEqual(len(second['applications']),11)
            ids=[app['application'] for app in first['applications']+second['applications']]
            self.assertEqual(len(set(ids)),61);self.assertIsNone(second['next_cursor'])
    def test_status_filter_and_original_account_isolation(self):
        rejected=self.fx.call('review_list',{'status':'REJECTED'},True)
        self.assertEqual(len(rejected['applications']),1)
        self.assertEqual(rejected['applications'][0]['status'],'REJECTED')
        web=self.fx.reviewer
        own=self.fx.service.dispatch(web['token'],web['csrf'],{'operation':'mine','params':{'status':'ALL'}})
        self.assertEqual(own['applications'],[]);self.assertIsNone(own['next_cursor'])
        application=rejected['applications'][0]['application']
        self.assertEqual(self.fx.call('read',{'application':application})['status'],'REJECTED')
        with self.assertRaises(PermissionError):
            self.fx.service.dispatch(web['token'],web['csrf'],{'operation':'read','params':{'application':application}})
    def test_invalid_cursor_filter_and_client_owner_are_rejected(self):
        for params in ({'cursor':'../private'},{'cursor':True},{'status':['REJECTED']},
                       {'status':"REJECTED' OR 1=1"},{'user_id':self.fx.fx.uid1}):
            with self.assertRaises(ValueError):self.fx.call('mine',params)

if __name__=='__main__':unittest.main()
