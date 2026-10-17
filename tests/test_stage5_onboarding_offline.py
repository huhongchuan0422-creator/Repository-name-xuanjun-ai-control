"""Offline-only merchant onboarding regression, no external services."""
import sqlite3
import unittest
from scripts.community_onboarding_offline import initialize,save_draft,transition,get_application,events

FIELDS={"legal_name":"商户甲","store_name":"甲店","address":"测试街","contact":"测试号","license_ref":"demo-document-reference"}
class OnboardingTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        initialize(self.db)
    def tearDown(self):self.db.close()
    def create(self):
        return save_draft(self.db,"tenant-a","app1","merchant-a",FIELDS)
    def test_complete_correction_and_approval(self):
        rev=self.create()
        rev=transition(self.db,"tenant-a","app1","merchant-a","MERCHANT","SUBMIT",rev)
        rev=transition(self.db,"tenant-a","app1","reviewer-a","REVIEWER","CORRECTION",rev,"补充材料")
        self.assertEqual(get_application(self.db,"tenant-a","app1")["status"],"CORRECTION_REQUIRED")
        rev=save_draft(self.db,"tenant-a","app1","merchant-a",FIELDS,rev)
        rev=transition(self.db,"tenant-a","app1","merchant-a","MERCHANT","SUBMIT",rev)
        rev=transition(self.db,"tenant-a","app1","reviewer-a","REVIEWER","APPROVE",rev)
        self.assertEqual(get_application(self.db,"tenant-a","app1")["status"],"APPROVED")
        self.assertEqual(len(events(self.db,"tenant-a","app1")),6)
    def test_tenant_isolation(self):
        self.create()
        with self.assertRaisesRegex(ValueError,"NOT_FOUND"):get_application(self.db,"tenant-b","app1")
    def test_replay_and_roles(self):
        rev=self.create()
        with self.assertRaises(PermissionError):transition(self.db,"tenant-a","app1","merchant-a","MERCHANT","APPROVE",rev)
        with self.assertRaisesRegex(ValueError,"REVISION_CONFLICT"):save_draft(self.db,"tenant-a","app1","merchant-a",FIELDS,0)
    def test_required_fields(self):
        fields=dict(FIELDS,contact="")
        rev=save_draft(self.db,"tenant-a","app1","merchant-a",fields)
        with self.assertRaisesRegex(ValueError,"MISSING_REQUIRED"):transition(self.db,"tenant-a","app1","merchant-a","MERCHANT","SUBMIT",rev)
    def test_reject_final(self):
        rev=self.create()
        rev=transition(self.db,"tenant-a","app1","merchant-a","MERCHANT","SUBMIT",rev)
        rev=transition(self.db,"tenant-a","app1","reviewer-a","REVIEWER","REJECT",rev,"材料不符合")
        with self.assertRaisesRegex(ValueError,"STATE_FORBIDDEN"):save_draft(self.db,"tenant-a","app1","merchant-a",FIELDS,rev)
    def test_event_hash_chain(self):
        rev=self.create();transition(self.db,"tenant-a","app1","merchant-a","MERCHANT","SUBMIT",rev)
        a,b=events(self.db,"tenant-a","app1")
        self.assertEqual(a[2],b[3])
        self.assertNotEqual(a[2],b[2])
if __name__=="__main__":unittest.main()
