"""Phase2 API contract: 25-node candidate, offline-only."""
import json
import os
import sqlite3
import tempfile
import unittest
from scripts.community_saas_modules import connect,set_price
from scripts.community_saas_offer_catalog import install,create_offer,approve_offer
from scripts.community_saas_order_preparation import install as order_install,install_lifecycle
from scripts.community_saas_offline_handoff import install_reviews
from scripts.community_saas_phase2 import OfflineSaas,Principal,serialize_response,verify_persistent_stores

def line(cost=10):
    return {"type":"MODULE_FEE","label":"license","cycle":"MONTH","quantity":1,
            "cny_minor":100,"usd_minor":20,"cost_cny_minor":cost,"cost_usd_minor":2}
class Phase2Nodes(unittest.TestCase):
 def setUp(self):
    self.q=connect();install(self.q)
    self.o=sqlite3.connect(":memory:")
    order_install(self.o);install_lifecycle(self.o);install_reviews(self.o)
    create_offer(self.q,"sku",1,"storefront_catalog","MONTHLY",[line()],term_days=30)
    approve_offer(self.q,"sku",1,"approval","costref",10)
    self.api=OfflineSaas(self.q,self.o,self.q)
    self.customer=Principal("tenantA","CUSTOMER")
    self.admin=Principal("tenantA","MERCHANT_ADMIN")
 def tearDown(self):self.o.close();self.q.close()
 def call(self,op,data=None,principal=None,now=20):
    return self.api.dispatch(principal or self.customer,op,{} if data is None else data,now)
 def quoted(self):
    return self.call("quote",{"quote_id":"q1","offer_id":"sku","version":1,"expires_at":100})
 def ordered(self):
    self.quoted()
    return self.call("order_prepare",{"order_id":"order1","quote_id":"q1","currency":"CNY"})
 def test_01_catalog(self):
    self.assertTrue(self.call("catalog")["framework_free"])
 def test_02_price_catalog(self):
    self.assertEqual(len(self.call("offers",{"module_id":"storefront_catalog"})["offers"]),1)
 def test_03_quote_issued(self):
    self.assertEqual(self.quoted()["quote_id"],"q1")
 def test_04_quote_tenant(self):
    self.quoted()
    self.assertEqual(self.call("quote_read",{"quote_id":"q1"})["tenant_id"],"tenantA")
 def test_05_prepare_order(self):
    self.assertEqual(self.ordered()["state"],"PREPARED_ONLY")
 def test_06_read_order(self):
    self.ordered()
    self.assertEqual(self.call("order_read",{"order_id":"order1"})["order_id"],"order1")
 def test_07_order_status(self):
    self.ordered()
    self.assertEqual(self.call("order_status",{"order_id":"order1"})["state"],"PREPARED")
 def test_08_ungranted_entitlement(self):
    self.assertFalse(self.call("entitlement",{"module_id":"storefront_catalog"})["active"])
 def test_09_capability_denied(self):
    self.assertFalse(self.call("capability",{"capability":"catalog.read"})["allowed"])
 def test_10_renewal_requires_confirmation(self):
    self.ordered()
    with self.assertRaisesRegex(ValueError,"CONFIRMATION_EVIDENCE_REQUIRED"):
        self.call("renewal_plan",{"order_id":"order1","valid_until":200})
 def test_11_finance_customer_forbidden(self):
    self.ordered()
    with self.assertRaises(PermissionError):
        self.call("finance_requirements",{"order_id":"order1"})
 def test_12_finance_admin_intent(self):
    self.ordered()
    x=self.call("finance_requirements",{"order_id":"order1"},self.admin)
    self.assertFalse(x["settled"])
 def test_13_admin_snapshot_role(self):
    self.ordered()
    self.assertEqual(len(self.call("admin_snapshot",principal=self.admin)["orders"]),1)
 def test_14_admin_customer_forbidden(self):
    with self.assertRaises(PermissionError):self.call("admin_snapshot")
 def test_15_review_create(self):
    self.ordered()
    self.assertEqual(self.call("review_open",{"task_id":"task1","order_id":"order1",
          "kind":"FINANCE_EVIDENCE","reason":"reconcile"},self.admin)["state"],"PENDING")
 def test_16_review_complete(self):
    self.test_15_review_create()
    self.assertEqual(self.call("review_close",{"task_id":"task1","event_id":"ev1","state":"RESOLVED"},
                               self.admin,now=22)["state"],"RESOLVED")
 def test_17_recovery(self):
    self.test_15_review_create()
    self.assertEqual(self.call("recovery",principal=self.admin)["open_tasks"],["task1"])
 def test_18_tenant_isolation(self):
    self.ordered()
    other=Principal("tenantB","MERCHANT_ADMIN")
    self.assertEqual(self.call("admin_snapshot",principal=other)["orders"],[])
 def test_19_body_actor_injection(self):
    with self.assertRaisesRegex(ValueError,"INVALID_REQUEST_FIELDS"):
        self.call("catalog",{"tenant_id":"tenantB"})
 def test_20_body_proof_injection(self):
    with self.assertRaisesRegex(ValueError,"INVALID_REQUEST_FIELDS"):
        self.call("order_status",{"order_id":"order1","payment_confirmed":True})
 def test_21_missing_trusted_principal(self):
    with self.assertRaises(PermissionError):
        self.api.dispatch({"tenant_id":"tenantA"},"catalog",{},20)
 def test_22_customer_cost_redacted(self):
    self.quoted()
    self.assertNotIn("cost_cny_minor",serialize_response(self.call("quote_read",{"quote_id":"q1"})))
 def test_23_customer_order_snapshot_redacted(self):
    self.ordered()
    self.assertNotIn("quote_snapshot",self.call("order_read",{"order_id":"order1"}))
 def test_24_finance_does_not_settle(self):
    self.ordered()
    self.call("finance_requirements",{"order_id":"order1"},self.admin)
    self.assertEqual(self.call("order_status",{"order_id":"order1"})["state"],"PREPARED")
 def test_25_json_rejects_nonfinite(self):
    with self.assertRaises(ValueError):serialize_response({"amount":float("nan")})
 def test_26_reopen_verified_schema(self):
    with tempfile.TemporaryDirectory() as d:
        q=os.path.join(d,"q.db");o=os.path.join(d,"o.db")
        db=connect(q);install(db);db.close()
        odb=sqlite3.connect(o);order_install(odb);install_lifecycle(odb);install_reviews(odb);odb.close()
        self.assertTrue(verify_persistent_stores(q,o)["verified"])
 def test_27_unknown_order_store_rejected(self):
    with tempfile.TemporaryDirectory() as d:
        q=os.path.join(d,"q.db");o=os.path.join(d,"o.db")
        db=connect(q);install(db);db.close()
        x=sqlite3.connect(o);x.execute("CREATE TABLE saas_order_preparations(fake INTEGER)");x.close()
        with self.assertRaises(ValueError):verify_persistent_stores(q,o)
if __name__=="__main__":unittest.main()
