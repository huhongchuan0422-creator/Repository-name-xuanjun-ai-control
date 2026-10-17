"""Original SQLite refund-history discovery; synthetic records, no money calls."""
import unittest
import test_community_mini_center_identity as fixtures
from scripts.community_center_operations import CenterOperations
from scripts.community_commerce import Commerce
from scripts.community_demo_bootstrap import DEMO_SCOPE


class RefundDirectory(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.ExistingCenterComposition();self.fx.setUp();self.c=self.fx.center
        self.web=self.c.login('one@example.org','FixturePassword123!');self.token=self.fx.token()
        self.grants={'merchant':dict(user_id=self.fx.uid1,project='project1',project_roles=['OWNER'],principal=self.fx.stage.merchant)}
        self.compose()
        self.merchant('price_set',dict(item_id='sample_item',expected_revision=0,unit_minor=101,stock=20,enabled=True))
        self.commerce.consumer(self.token,'shop1','purchase',dict(reference='basket',lines=[dict(item_id='sample_item',quantity=1,revision=1)]))
    def compose(self):
        self.ops=CenterOperations(self.c,self.fx.stage.api,self.grants);self.commerce=Commerce(self.ops,self.fx.identity)
    def tearDown(self):self.fx.tearDown()
    def merchant(self,op,p):return self.commerce.dispatch(self.web['token'],self.web['csrf'],dict(workspace='merchant',operation=op,params=p))
    def current(self,token=None):return self.commerce.consumer(token or self.token,'shop1','refund_current',dict(reference='basket'))
    def save(self,application='request1',status='SUBMITTED',identity=None,project='project1',uid=None,pointer=True):
        identity=identity or DEMO_SCOPE;uid=uid or self.fx.uid1
        record=dict(application_id=application,reference='basket',scope=identity,project=project,user_id=uid,status=status,revision=1,amount_minor=50,reason='Synthetic historical request',opinion='',created_at=self.c.now())
        with self.c.tx():
            self.commerce._save(identity,project,uid,'REFUND_APPLICATION',application,record)
            if pointer:self.commerce._save(identity,project,uid,'REFUND_CURRENT','basket',dict(application_id=application),True)
        return record
    def test_61_records_paginate_exactly_and_preserve_unknown_state(self):
        for n in range(61):self.save('request'+str(n),status='LEGACY_UNKNOWN' if n==60 else 'SUBMITTED')
        with self.c.tx():
            for n in range(210):self.commerce._save(DEMO_SCOPE,'project1',self.fx.uid1,'PRODUCT','noise'+str(n),dict(item_id='noise'+str(n)))
        first=self.merchant('refund_applications',dict(after_id=''))
        self.assertEqual(len(first['records']),50);self.assertTrue(first['has_more'])
        second=self.merchant('refund_applications',dict(after_id=first['next_cursor']))
        self.assertEqual(len(second['records']),11);self.assertFalse(second['has_more']);self.assertIsNone(second['next_cursor'])
        records=first['records']+second['records'];self.assertEqual(len({r['application_id'] for r in records}),61)
        self.assertIn('LEGACY_UNKNOWN',[r['status'] for r in records])
    def test_scan_budget_sparse_empty_page_keeps_later_refund_reachable(self):
        # Original encrypted channel also holds unrelated record kinds. Synthetic
        # low keys deterministically place over one request's budget before refund.
        with self.c.tx():
            for n in range(1100):
                key=format(n,'064x')
                self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_COMMERCE_V1',?,?,?,?,1)",(key,self.fx.uid1,'project1',self.c.encrypt(b'{"item_id":"noise"}','community-commerce:'+key)))
        expected=self.save()
        first=self.merchant('refund_applications',dict(after_id=''))
        self.assertEqual(first['records'],[]);self.assertTrue(first['has_more']);self.assertEqual(first['next_cursor'],format(999,'064x'))
        second=self.merchant('refund_applications',dict(after_id=first['next_cursor']))
        self.assertEqual(second['records'],[expected]);self.assertFalse(second['has_more']);self.assertIsNone(second['next_cursor'])
    def test_other_store_and_project_filtered_and_original_read_still_used(self):
        expected=self.save();self.save('foreign_store',identity=dict(DEMO_SCOPE,store_id='other'))
        self.save('foreign_project',project='other_project')
        result=self.merchant('refund_applications',dict(after_id=''));self.assertEqual(result['records'],[expected])
        self.assertEqual(self.merchant('refund_application_read',dict(application_id='request1')),expected)
    def test_current_restores_original_pointer_and_null_is_distinct(self):
        self.assertEqual(self.current(),dict(reference='basket',application=None))
        record=self.save(status='EXECUTION_RESERVED');self.assertEqual(self.current()['application'],record)
        self.fx.reopen();self.c=self.fx.center;self.compose()
        self.assertEqual(self.current()['application'],record)
    def test_missing_current_record_and_wrong_owner_fail_closed(self):
        with self.c.tx():self.commerce._save(DEMO_SCOPE,'project1',self.fx.uid1,'REFUND_CURRENT','basket',dict(application_id='missing'),True)
        with self.assertRaises(PermissionError):self.current()
        self.save(uid=self.fx.uid2)
        with self.assertRaises(PermissionError):self.current()
    def test_existing_null_or_malformed_pointer_is_not_absence(self):
        self.save()
        key=self.commerce._key(DEMO_SCOPE,'REFUND_CURRENT','basket')
        for raw in (b'null',b'[]',b'{}'):
            with self.c.tx():self.c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=?",(self.c.encrypt(raw,'community-commerce:'+key),key))
            with self.assertRaises(ValueError):self.current()
    def test_pointer_and_application_link_owner_must_match_authenticated_owner(self):
        self.save()
        for kind,ref in (('REFUND_CURRENT','basket'),('REFUND_APPLICATION','request1')):
            key=self.commerce._key(DEMO_SCOPE,kind,ref)
            with self.c.tx():self.c.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=?",(self.fx.uid2,key))
            with self.assertRaises(PermissionError):self.current()
            with self.c.tx():self.c.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=?",(self.fx.uid1,key))
    def test_other_customer_cannot_recover_current_application(self):
        self.save();second=self.fx.token('second','openid2')
        with self.assertRaises(PermissionError):self.current(second)
    def test_revoked_membership_denies_each_page_and_current(self):
        self.save();self.merchant('refund_applications',dict(after_id=''))
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,));self.c.db.commit()
        with self.assertRaises(PermissionError):self.merchant('refund_applications',dict(after_id=''))
        with self.assertRaises(PermissionError):self.current()
    def test_csrf_and_registered_role_binding_required(self):
        with self.assertRaises(PermissionError):
            self.commerce.dispatch(self.web['token'],'wrong',dict(workspace='merchant',operation='refund_applications',params=dict(after_id='')))
        self.ops.grants['merchant']['role']='STORE_STAFF'
        with self.assertRaises(PermissionError):self.merchant('refund_applications',dict(after_id=''))
    def test_strict_cursor_and_client_scope_fields_rejected(self):
        for after in (None,1,True,'request1','A'*64,"' OR 1=1"):
            with self.assertRaises(ValueError):self.merchant('refund_applications',dict(after_id=after))
        with self.assertRaises(ValueError):self.merchant('refund_applications',dict(after_id='',store_id='other'))
        with self.assertRaises(ValueError):self.commerce.consumer(self.token,'shop1','refund_current',dict(reference='basket',user_id=self.fx.uid1))
    def test_directory_binding_tamper_denied_and_no_refund_decision_effect(self):
        record=self.save(status='APPROVED')
        before=list(self.c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_COMMERCE_V1' ORDER BY subject_idx"))
        events=list(self.fx.stage.o.execute('SELECT * FROM order_events'))
        self.merchant('refund_applications',dict(after_id=''));self.current()
        self.assertEqual(before,list(self.c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_COMMERCE_V1' ORDER BY subject_idx")))
        self.assertEqual(events,list(self.fx.stage.o.execute('SELECT * FROM order_events')))
        with self.c.tx():self.commerce._save(DEMO_SCOPE,'project1',self.fx.uid1,'REFUND_APPLICATION','request1',dict(record,scope=dict(DEMO_SCOPE,store_id='other')),True)
        with self.assertRaises(PermissionError):self.merchant('refund_applications',dict(after_id=''))
        with self.assertRaises(PermissionError):self.current()

if __name__=='__main__':unittest.main()
