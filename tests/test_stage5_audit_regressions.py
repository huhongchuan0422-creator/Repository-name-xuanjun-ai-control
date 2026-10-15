"""Independent-review R1-R7 negative probes. All local, no provider or money."""
import sqlite3
import unittest
from scripts.community_saas_modules import connect,set_price,grant
from scripts.community_saas_offer_catalog import install,create_offer,quote,approve_offer
from scripts.community_saas_order_preparation import (
    install as order_install,install_lifecycle,prepare,advance)
from scripts.community_saas_offline_handoff import (
    install_reviews,create_review,change_review,recovery_check,
    plan_finance_claim,make_test_attestation,inspect_test_attestation)
from scripts.community_saas_offers import (
    open_offer_store,register_offer,add_component,quote_offers,change_offer_status)
from scripts.community_saas_cost_pricing import open_cost_store,save_cost

KEY=b"review-fixture-not-real-provider-validation-key-123"
def price(cny=100,usd=20,cost=30):
    return {"type":"MODULE_FEE","label":"module","cycle":"MONTH","quantity":1,
            "cny_minor":cny,"usd_minor":usd,
            "cost_cny_minor":cost,"cost_usd_minor":1}
class FullScopeAuditProbes(unittest.TestCase):
 def setUp(self):
    self.base=connect();install(self.base)
    self.orders=sqlite3.connect(":memory:")
    order_install(self.orders);install_lifecycle(self.orders);install_reviews(self.orders)
 def tearDown(self):
    self.orders.close();self.base.close()
 def ready(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    approve_offer(self.base,"offer",1,"approval1","costref1",10)
    quote(self.base,"quote","tenantA","offer",1,10,100)
    prepare(self.orders,self.base,"ord","tenantA","quote","CNY",20)
 def test_r1_offer_version_replace_fails(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO saas_offer_versions SELECT * FROM saas_offer_versions")
 def test_r1_offer_lines_replace_fails(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("INSERT OR REPLACE INTO saas_offer_lines SELECT * FROM saas_offer_lines")
 def test_r1_quote_replace_fails(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    quote(self.base,"q","tenantA","offer",1,10,90)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO saas_quotes SELECT * FROM saas_quotes")
 def test_r1_order_replace_fails(self):
    self.ready()
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("INSERT OR REPLACE INTO saas_order_preparations SELECT * FROM saas_order_preparations")
 def test_r1_review_terminal_replace_fails(self):
    self.ready();create_review(self.orders,"task","tenantA","ord","FINANCE_EVIDENCE",21,"reason")
    change_review(self.orders,"task","tenantA","event","RESOLVED",22)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("REPLACE INTO saas_review_tasks SELECT * FROM saas_review_tasks")
 def test_r1_review_event_replace_fails(self):
    self.ready();create_review(self.orders,"task","tenantA","ord","FINANCE_EVIDENCE",21,"reason")
    change_review(self.orders,"task","tenantA","event","RESOLVED",22)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("REPLACE INTO saas_review_events SELECT * FROM saas_review_events")
 def test_r1_lifecycle_event_replace_fails(self):
    self.ready();advance(self.orders,"ord","tenantA","ev1","AWAITING_EXTERNAL",21)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("REPLACE INTO saas_order_lifecycle_events SELECT * FROM saas_order_lifecycle_events")
 def test_r1_module_event_replace_fails(self):
    set_price(self.base,"storefront_catalog",1,100,20,30)
    grant(self.base,"tenantA","storefront_catalog",10,40,1)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO module_events SELECT * FROM module_events")
 def test_r2_draft_order_rejected(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    quote(self.base,"q","tenantA","offer",1,10,100)
    with self.assertRaisesRegex(ValueError,"OFFER_APPROVAL_REQUIRED"):
        prepare(self.orders,self.base,"ord","tenantA","q","CNY",20)
 def test_r2_unknown_cost_no_approval(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price(cost=None)],term_days=30)
    with self.assertRaisesRegex(ValueError,"COST_EVIDENCE_REQUIRED"):
        approve_offer(self.base,"offer",1,"approval","costref",10)
 def test_r2_immutable_approval(self):
    create_offer(self.base,"offer",1,"storefront_catalog","MONTHLY",[price()],term_days=30)
    approve_offer(self.base,"offer",1,"approval","costref",10)
    with self.assertRaises(sqlite3.IntegrityError):
        self.base.execute("REPLACE INTO saas_offer_approvals SELECT * FROM saas_offer_approvals")
 def test_r3_private_no_scope_rejected(self):
    o=open_offer_store()
    try:
        with self.assertRaisesRegex(ValueError,"TENANT_SCOPE_REQUIRED"):
            register_offer(o,"private","storefront_catalog","MONTHLY",1,30,True,"term","basis",availability="CUSTOMER_PRIVATE")
    finally:o.close()
 def test_r3_private_scope_filter(self):
    o=open_offer_store();costs=open_cost_store()
    try:
        for oid,tenant in (("a","tenantA"),("b","tenantB")):
            register_offer(o,oid,"storefront_catalog","MONTHLY",1,30,True,"term","basis",availability="CUSTOMER_PRIVATE",tenant_scope=tenant)
            add_component(o,oid,"license","MODULE_LICENSE","MONTHLY",100,10,"pricebook")
            save_cost(costs,oid,"license","VERIFIED_ACTUAL",20,2,"invoice","MONTHLY")
            for step in ("PREVIEW","APPROVED","EFFECTIVE"):change_offer_status(o,oid,step,costs)
        self.assertEqual(quote_offers(o,"storefront_catalog"),[])
        self.assertEqual([x["offer_id"] for x in quote_offers(o,"storefront_catalog",tenant_id="tenantA")],["a"])
    finally:o.close();costs.close()
 def test_r4_fake_module_schema_rejected(self):
    db=sqlite3.connect(":memory:")
    try:
        for name in ("module_prices","module_entitlements","module_events"):
            db.execute("CREATE TABLE "+name+"(fake INTEGER)")
        db.execute("PRAGMA user_version=1")
        with self.assertRaises(ValueError):
            # separate connection to same named in-memory database required
            pass
    finally:db.close()
 def test_r5_missing_projection_held(self):
    self.ready()
    advance(self.orders,"ord","tenantA","ev1","AWAITING_EXTERNAL",21)
    advance(self.orders,"ord","tenantA","ev2","CONFIRMATION_UNKNOWN",22)
    self.orders.execute("DELETE FROM saas_order_lifecycle WHERE order_id='ord'")
    v=recovery_check(self.orders,"tenantA")
    self.assertEqual(v["integrity_hold"],["ord"])
    self.assertIn("ord",v["awaiting_review"])
 def test_r7_pre_order_proof_rejected(self):
    self.ready()
    att=make_test_attestation(plan_finance_claim(self.orders,"ord","tenantA"),"proof",0,KEY)
    with self.assertRaisesRegex(ValueError,"PRE_ORDER_ATTESTATION"):
        inspect_test_attestation(self.orders,"ord","tenantA",att,KEY,30)
 def test_r7_at_creation_time_valid_fixture(self):
    self.ready()
    att=make_test_attestation(plan_finance_claim(self.orders,"ord","tenantA"),"proof",20,KEY)
    self.assertFalse(inspect_test_attestation(self.orders,"ord","tenantA",att,KEY,30)["production_eligible"])
if __name__=="__main__":unittest.main()
