"""Stage5 six-batch isolated handoff acceptance: no production finance calls."""
import json
import sqlite3
import tempfile
import os
import unittest
from scripts.community_saas_modules import connect
from scripts.community_saas_offer_catalog import install as offer_install,create_offer,quote
from scripts.community_saas_order_preparation import install as order_install,install_lifecycle,prepare,advance
from scripts.community_saas_offline_handoff import (
    plan_finance_claim,make_test_attestation,inspect_test_attestation,
    install_reviews,create_review,change_review,admin_snapshot,recovery_check)

KEY=b"offline-test-key-not-a-provider-credential-01234567"
def fee():
    return {"type":"MODULE_FEE","label":"license","cycle":"MONTH","quantity":1,
            "cny_minor":1000,"usd_minor":200}
class OfflineBatch(unittest.TestCase):
 def setUp(self):
    self.quotes=connect();offer_install(self.quotes)
    self.orders=sqlite3.connect(":memory:")
    order_install(self.orders);install_lifecycle(self.orders);install_reviews(self.orders)
    create_offer(self.quotes,"offer1",1,"storefront_catalog","MONTHLY",[fee()],term_days=30)
    quote(self.quotes,"q1","tenantA","offer1",1,10,200)
    prepare(self.orders,self.quotes,"ord1","tenantA","q1","CNY",20)
 def tearDown(self):
    self.quotes.close();self.orders.close()
 def claim(self):return plan_finance_claim(self.orders,"ord1","tenantA")
 def proof(self):return make_test_attestation(self.claim(),"proof1",30,KEY)
 def review(self):return create_review(self.orders,"task1","tenantA","ord1","FINANCE_EVIDENCE",21,"needs audit")
 def test_01_claim_order_bound(self):self.assertEqual(self.claim()["order_id"],"ord1")
 def test_02_claim_tenant_bound(self):self.assertEqual(self.claim()["tenant_id"],"tenantA")
 def test_03_claim_cny(self):self.assertEqual(self.claim()["currency"],"CNY")
 def test_04_claim_amount(self):self.assertEqual(self.claim()["amounts_by_cycle_minor"]["MONTH"],1000)
 def test_05_claim_unsettled(self):self.assertFalse(self.claim()["settled"])
 def test_06_claim_wrong_tenant(self):
    with self.assertRaisesRegex(ValueError,"ORDER_NOT_FOUND"):plan_finance_claim(self.orders,"ord1","tenantB")
 def test_07_proof_fixture_valid(self):
    self.assertTrue(inspect_test_attestation(self.orders,"ord1","tenantA",self.proof(),KEY,30)["verified_test_fixture"])
 def test_08_proof_not_production_authority(self):
    self.assertFalse(inspect_test_attestation(self.orders,"ord1","tenantA",self.proof(),KEY,30)["production_eligible"])
 def test_09_proof_signature_reject(self):
    v=self.proof();v["signature"]="a"*64
    with self.assertRaisesRegex(ValueError,"INVALID_ATTESTATION_SIGNATURE"):
        inspect_test_attestation(self.orders,"ord1","tenantA",v,KEY,30)
 def test_10_proof_bad_key_reject(self):
    with self.assertRaisesRegex(ValueError,"INVALID_TEST_KEY"):
        inspect_test_attestation(self.orders,"ord1","tenantA",self.proof(),b"small",30)
 def test_11_proof_wrong_tenant_reject(self):
    with self.assertRaisesRegex(ValueError,"ORDER_NOT_FOUND"):
        inspect_test_attestation(self.orders,"ord1","tenantB",self.proof(),KEY,30)
 def test_12_proof_future_reject(self):
    with self.assertRaisesRegex(ValueError,"FUTURE_ATTESTATION"):
        inspect_test_attestation(self.orders,"ord1","tenantA",self.proof(),KEY,29)
 def test_13_proof_currency_tamper(self):
    v=self.proof();v["payload"]["currency"]="USD"
    with self.assertRaisesRegex(ValueError,"FINANCE_CLAIM_MISMATCH"):
        inspect_test_attestation(self.orders,"ord1","tenantA",v,KEY,30)
 def test_14_proof_amount_tamper(self):
    v=self.proof();v["payload"]["amounts_by_cycle_minor"]["MONTH"]=0
    with self.assertRaisesRegex(ValueError,"FINANCE_CLAIM_MISMATCH"):
        inspect_test_attestation(self.orders,"ord1","tenantA",v,KEY,30)
 def test_15_proof_quote_digest_tamper(self):
    v=self.proof();v["payload"]["quote_sha256"]="0"*64
    with self.assertRaisesRegex(ValueError,"FINANCE_CLAIM_MISMATCH"):
        inspect_test_attestation(self.orders,"ord1","tenantA",v,KEY,30)
 def test_16_proof_requires_structure(self):
    with self.assertRaisesRegex(ValueError,"INVALID_ATTESTATION"):
        inspect_test_attestation(self.orders,"ord1","tenantA",{},KEY,30)
 def test_17_review_open(self):self.assertEqual(self.review()["state"],"PENDING")
 def test_18_review_idempotent(self):
    self.review();self.assertEqual(self.review()["state"],"PENDING")
 def test_19_review_conflict(self):
    self.review()
    with self.assertRaisesRegex(ValueError,"REVIEW_TASK_CONFLICT"):
        create_review(self.orders,"task1","tenantA","ord1","ENTITLEMENT",21,"needs audit")
 def test_19b_review_replay_after_resolution_returns_truth(self):
    self.review()
    change_review(self.orders,"task1","tenantA","ev1","RESOLVED",22)
    self.assertEqual(self.review()["state"],"RESOLVED")
 def test_20_review_scope(self):
    with self.assertRaisesRegex(ValueError,"ORDER_NOT_FOUND"):
        create_review(self.orders,"task1","tenantB","ord1","FINANCE_EVIDENCE",21,"needs audit")
 def test_21_review_bad_kind(self):
    with self.assertRaisesRegex(ValueError,"INVALID_REVIEW_KIND"):
        create_review(self.orders,"task1","tenantA","ord1","PAY_NOW",21,"bad")
 def test_22_review_resolve(self):
    self.review()
    self.assertEqual(change_review(self.orders,"task1","tenantA","ev1","RESOLVED",22)["state"],"RESOLVED")
 def test_23_review_cancel(self):
    self.review()
    self.assertEqual(change_review(self.orders,"task1","tenantA","ev1","CANCELLED",22)["state"],"CANCELLED")
 def test_24_review_replay(self):
    self.review()
    change_review(self.orders,"task1","tenantA","ev1","RESOLVED",22)
    self.assertEqual(change_review(self.orders,"task1","tenantA","ev1","RESOLVED",22)["state"],"RESOLVED")
 def test_25_review_event_conflict(self):
    self.review();change_review(self.orders,"task1","tenantA","ev1","RESOLVED",22)
    with self.assertRaisesRegex(ValueError,"REVIEW_EVENT_CONFLICT"):
        change_review(self.orders,"task1","tenantA","ev1","CANCELLED",22)
 def test_26_review_wrong_tenant(self):
    self.review()
    with self.assertRaisesRegex(ValueError,"REVIEW_NOT_FOUND"):
        change_review(self.orders,"task1","tenantB","ev1","RESOLVED",22)
 def test_27_review_not_double_complete(self):
    self.review();change_review(self.orders,"task1","tenantA","ev1","RESOLVED",22)
    with self.assertRaisesRegex(ValueError,"INVALID_REVIEW_TRANSITION"):
        change_review(self.orders,"task1","tenantA","ev2","RESOLVED",23)
 def test_28_review_immutable_event(self):
    self.review();change_review(self.orders,"task1","tenantA","ev1","RESOLVED",22)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("DELETE FROM saas_review_events")
 def test_29_admin_tenant_orders(self):
    self.assertEqual(len(admin_snapshot(self.orders,"tenantA",25)["orders"]),1)
 def test_30_admin_no_cross_tenant(self):
    self.assertEqual(admin_snapshot(self.orders,"tenantB",25)["orders"],[])
 def test_31_admin_no_false_settlement(self):
    self.assertFalse(admin_snapshot(self.orders,"tenantA",25)["orders"][0]["payment_settled"])
 def test_32_admin_pending_task(self):
    self.review();self.assertEqual(len(admin_snapshot(self.orders,"tenantA",25)["review_tasks"]),1)
 def test_33_recovery_no_blind_resend(self):
    self.assertFalse(recovery_check(self.orders,"tenantA")["resend_payment_requests"])
 def test_34_recovery_pending_queue(self):
    advance(self.orders,"ord1","tenantA","ev1","AWAITING_EXTERNAL",21)
    advance(self.orders,"ord1","tenantA","ev2","CONFIRMATION_UNKNOWN",22)
    self.assertEqual(recovery_check(self.orders,"tenantA")["awaiting_review"],["ord1"])
 def test_35_recovery_open_review_task(self):
    self.review();self.assertEqual(recovery_check(self.orders,"tenantA")["open_tasks"],["task1"])
 def test_36_recovery_no_mutation(self):
    self.review()
    before=self.orders.total_changes
    recovery_check(self.orders,"tenantA")
    self.assertEqual(before,self.orders.total_changes)
if __name__=="__main__":unittest.main()
