"""Every consumer refund recovery route keeps the original record ownership."""
import unittest
from unittest.mock import patch
import test_community_refund_directory as fixtures
from scripts.community_demo_bootstrap import DEMO_SCOPE


class ConsumerRefundBinding(unittest.TestCase):
    def setUp(self):
        for method in ('socket.socket.connect', 'socket.socket.bind'):
            guard=patch(method,side_effect=AssertionError('NO_NETWORK_OR_LISTENER'))
            guard.start();self.addCleanup(guard.stop)
        self.fx=fixtures.RefundDirectory();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.c,self.commerce=self.fx.c,self.fx.commerce

    def call(self,operation,**params):
        return self.commerce.consumer(self.fx.token,'shop1',operation,
            dict(reference='basket',application_id='request1',**params))

    def test_direct_read_and_idempotent_submit_reject_wrong_scope(self):
        record=self.fx.save()
        with self.c.tx():
            self.commerce._save(DEMO_SCOPE,'project1',self.fx.fx.uid1,'REFUND_APPLICATION','request1',
                dict(record,scope=dict(DEMO_SCOPE,store_id='foreign-store')),True)
        for operation,params in [('refund_application',{}),('refund_apply',dict(amount_minor=50,reason=record['reason']))]:
            with self.subTest(operation=operation),self.assertRaises(PermissionError):
                self.call(operation,**params)

    def test_direct_read_and_idempotent_submit_reject_link_owner_mismatch(self):
        record=self.fx.save()
        key=self.commerce._key(DEMO_SCOPE,'REFUND_APPLICATION','request1')
        with self.c.tx():
            self.c.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=? AND project=?",(self.fx.fx.uid2,key,'project1'))
        for operation,params in [('refund_application',{}),('refund_apply',dict(amount_minor=50,reason=record['reason']))]:
            with self.subTest(operation=operation),self.assertRaises(PermissionError):
                self.call(operation,**params)


    def test_all_recovery_routes_reject_embedded_project_application_or_owner_changes(self):
        record=self.fx.save()
        for field,value in [('project','other-project'),('application_id','other-application'),
                            ('user_id',self.fx.fx.uid2),('reference','other-order')]:
            with self.c.tx():
                self.commerce._save(DEMO_SCOPE,'project1',self.fx.fx.uid1,'REFUND_APPLICATION','request1',dict(record,**{field:value}),True)
            for operation,params in [('refund_application',{}),('refund_apply',dict(amount_minor=50,reason=record['reason']))]:
                with self.subTest(field=field,operation=operation),self.assertRaises(PermissionError):
                    self.call(operation,**params)
            with self.subTest(field=field,operation='refund_current'),self.assertRaises(PermissionError):self.fx.current()

    def test_existing_malformed_application_is_not_absence(self):
        self.fx.save()
        key=self.commerce._key(DEMO_SCOPE,'REFUND_APPLICATION','request1')
        for raw in (b'null',b'[]',b'{}'):
            with self.c.tx():
                self.c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=? AND project=?",(self.c.encrypt(raw,'community-commerce:'+key),key,'project1'))
            with self.subTest(raw=raw),self.assertRaises(PermissionError):self.call('refund_application')

    def test_valid_same_application_remains_idempotent_and_original_records_unchanged(self):
        expected=self.fx.save()
        before=list(self.c.db.execute("SELECT * FROM links WHERE channel='COMMUNITY_COMMERCE_V1' ORDER BY subject_idx"))
        self.assertEqual(self.call('refund_application'),expected)
        self.assertEqual(self.call('refund_apply',amount_minor=50,reason=expected['reason']),expected)
        self.assertEqual(self.fx.current()['application'],expected)
        self.assertEqual(before,list(self.c.db.execute("SELECT * FROM links WHERE channel='COMMUNITY_COMMERCE_V1' ORDER BY subject_idx")))
        with self.assertRaises(ValueError):self.call('refund_apply',amount_minor=51,reason=expected['reason'])


    def test_new_application_rejects_inconsistent_previous_pointer_and_record(self):
        record=self.fx.save(status='CLOSED')
        for changed in [dict(record,reference='another-order'),dict(record,scope=dict(DEMO_SCOPE,store_id='another-store'))]:
            with self.c.tx():
                self.commerce._save(DEMO_SCOPE,'project1',self.fx.fx.uid1,'REFUND_APPLICATION','request1',changed,True)
            with patch('scripts.community_refund_requests.state',return_value={'state':'SUCCESS','amount_minor':101}),patch('scripts.community_refund_requests.provider_evidence',return_value={'verified':'synthetic'}):
                with self.assertRaises(PermissionError):
                    self.commerce.consumer(self.fx.token,'shop1','refund_apply',dict(reference='basket',application_id='request2',amount_minor=50,reason='new request'))
            self.assertIsNone(self.commerce._read(DEMO_SCOPE,'project1','REFUND_APPLICATION','request2'))


if __name__=='__main__':unittest.main()
