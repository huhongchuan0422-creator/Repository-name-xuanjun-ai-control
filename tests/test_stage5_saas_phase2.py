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
                               Principal("tenantA","PLATFORM_OWNER"),now=22)["state"],"RESOLVED")
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
 def test_28_no_finance_or_grant_writer_health(self):
    state=self.call("health")
    self.assertEqual(state["finance_provider"],"NOT_CONNECTED")
    self.assertEqual(state["grant_writer"],"DISABLED")
 def test_35_health_detail_admin_only(self):
    with self.assertRaises(PermissionError):
        self.call("health_detail")
    healthy=self.call("health_detail",principal=self.admin)
    self.assertEqual(healthy["status"],"OFFLINE_CHECKED")
    self.assertFalse(healthy["production_release_authorized"])
 def test_36_health_detail_pending_task_hold(self):
    self.ordered()
    self.call("review_open",{"task_id":"task1","order_id":"order1",
        "kind":"FINANCE_EVIDENCE","reason":"manual review"},self.admin)
    state=self.call("health_detail",principal=self.admin)
    self.assertEqual(state["status"],"HOLD")
    self.assertEqual(state["report"]["open_tasks"],["task1"])
 def test_37_health_detail_tenant_scoped(self):
    other=Principal("tenantB","MERCHANT_ADMIN")
    self.ordered()
    self.assertEqual(self.call("health_detail",principal=other)["report"]["open_tasks"],[])
 def test_38_health_detail_fails_closed_on_corrupt_schema(self):
    self.o.execute("DROP TABLE saas_review_tasks")
    result=self.call("health_detail",principal=self.admin)
    self.assertEqual(result["status"],"HOLD")
    self.assertEqual(result["reason"],"OFFLINE_STORE_CHECK_FAILED")
 def test_29_refund_plan_admin_only(self):
    self.ordered()
    params={"order_id":"order1","reason":"customer requested reversal"}
    with self.assertRaises(PermissionError):
        self.call("refund_reversal_plan",params)
    result=self.call("refund_reversal_plan",params,self.admin)
    self.assertFalse(result["provider_refund_executed"])
    self.assertFalse(result["entitlement_revoked"])
    self.assertFalse(result["revenue_reversed"])
 def test_30_refund_plan_invalid_reason(self):
    self.ordered()
    with self.assertRaisesRegex(ValueError,"INVALID_REFUND_REASON"):
        self.call("refund_reversal_plan",{"order_id":"order1","reason":""},self.admin)
 def test_31_owner_create_version(self):
    owner=Principal("tenantA","PLATFORM_OWNER")
    record=self.call("owner_create_offer",{"offer_id":"sku2","version":1,
        "module_id":"storefront_catalog","kind":"MONTHLY",
        "lines":[line()],"term_days":30,"tenant_scope":"tenantA",
        "supplier_payment":"NONE"},owner)
    self.assertTrue(record["requires_separate_approval"])
    self.assertFalse(record["payment_authorized"])
 def test_32_owner_approve_creates_immutable_evidence(self):
    self.test_31_owner_create_version()
    owner=Principal("tenantA","PLATFORM_OWNER")
    record=self.call("owner_approve_offer",{"offer_id":"sku2","version":1,
      "approval_ref":"approved","cost_evidence_ref":"evidence"},owner)
    self.assertTrue(record["approved"])
    self.assertFalse(record["production_release_authorized"])
 def test_33_customer_cannot_create_offer(self):
    with self.assertRaises(PermissionError):
        self.call("owner_create_offer",{"offer_id":"bad","version":1,
            "module_id":"storefront_catalog","kind":"MONTHLY",
            "lines":[line()],"term_days":30,"tenant_scope":None,
            "supplier_payment":"NONE"})
 def test_34_merchant_cannot_approve_prices(self):
    with self.assertRaises(PermissionError):
        self.call("owner_approve_offer",{"offer_id":"sku","version":1,
         "approval_ref":"approved","cost_evidence_ref":"evidence"},self.admin)
 def test_39_finance_handoff_rejects_unsafe_integer_amount(self):
    from unittest.mock import patch
    from scripts.community_saas_offline_handoff import plan_finance_claim
    fake={"quote_id":"q1","quote_sha256":"a"*64,"currency":"CNY",
          "amounts_by_cycle_minor":{"MONTH":9007199254740992}}
    with patch("scripts.community_saas_offline_handoff.quote_provenance",return_value={}):
        with patch("scripts.community_saas_offline_handoff.read",return_value=fake):
            with self.assertRaisesRegex(ValueError,"UNSETTLEABLE_AMOUNT"):
                plan_finance_claim(self.o,"order1","tenantA")
 def test_40_finance_handoff_rejects_boolean_amount(self):
    from unittest.mock import patch
    from scripts.community_saas_offline_handoff import plan_finance_claim
    fake={"quote_id":"q1","quote_sha256":"a"*64,"currency":"CNY",
          "amounts_by_cycle_minor":{"MONTH":True}}
    with patch("scripts.community_saas_offline_handoff.quote_provenance",return_value={}):
        with patch("scripts.community_saas_offline_handoff.read",return_value=fake):
            with self.assertRaisesRegex(ValueError,"UNSETTLEABLE_AMOUNT"):
                plan_finance_claim(self.o,"order1","tenantA")
 def test_41_order_prepare_rejects_unsafe_quote_total(self):
    from unittest.mock import patch
    from scripts.community_saas_order_preparation import prepare
    quote={"created_at":10,"expires_at":100,"kind":"MONTHLY",
           "supplier_payment":"NONE","totals_by_cycle":{"MONTH":{"cny_minor":9007199254740992}},
           "offer_governed":True,"approval_ref":"approved","cost_evidence_ref":"evidence",
           "module_id":"storefront_catalog","offer_id":"sku","version":1}
    with patch("scripts.community_saas_order_preparation.read_quote",return_value=quote):
        with self.assertRaisesRegex(ValueError,"INVALID_QUOTE_AMOUNT"):
            prepare(self.o,self.q,"unsafe1","tenantA","qunsafe","CNY",20)
    self.assertEqual(self.o.execute("SELECT COUNT(*) FROM saas_order_preparations").fetchone()[0],0)
 def test_42_refund_review_rejects_unverified_quote_provenance(self):
    from unittest.mock import patch
    self.ordered()
    with patch("scripts.community_saas_order_preparation.quote_provenance",
               side_effect=ValueError("QUOTE_SNAPSHOT_DIGEST_MISMATCH")):
        with self.assertRaisesRegex(ValueError,"QUOTE_SNAPSHOT_DIGEST_MISMATCH"):
            self.call("refund_reversal_plan",
                      {"order_id":"order1","reason":"request"},self.admin)
 def test_43_refund_review_includes_actual_lifecycle_without_refund(self):
    self.ordered()
    view=self.call("refund_reversal_plan",{"order_id":"order1","reason":"request"},self.admin)
    self.assertEqual(view["order_lifecycle_state"],"PREPARED")
    self.assertFalse(view["provider_refund_executed"])
 def test_44_verify_missing_stores_does_not_create_files(self):
    with tempfile.TemporaryDirectory() as d:
        q=os.path.join(d,"never-created-quote.sqlite")
        o=os.path.join(d,"never-created-order.sqlite")
        with self.assertRaisesRegex(ValueError,"STORE_MISSING"):
            verify_persistent_stores(q,o)
        self.assertFalse(os.path.exists(q))
        self.assertFalse(os.path.exists(o))
 def test_45_verify_quote_symlink_rejected_without_mutation(self):
    with tempfile.TemporaryDirectory() as d:
        q=os.path.join(d,"q.sqlite");o=os.path.join(d,"o.sqlite")
        actual=connect(q);install(actual);actual.close()
        odb=sqlite3.connect(o);order_install(odb);install_lifecycle(odb);install_reviews(odb);odb.close()
        link=os.path.join(d,"alias.sqlite");os.symlink(q,link)
        with self.assertRaisesRegex(ValueError,"STORE_NOT_REGULAR"):
            verify_persistent_stores(link,o)
        self.assertTrue(verify_persistent_stores(q,o)["read_only"])
 def test_46_verify_existing_store_does_not_modify_bytes(self):
    with tempfile.TemporaryDirectory() as d:
        q=os.path.join(d,"q.sqlite");o=os.path.join(d,"o.sqlite")
        a=connect(q);install(a);a.close()
        b=sqlite3.connect(o);order_install(b);install_lifecycle(b);install_reviews(b);b.close()
        import hashlib
        def digest(path):
            with open(path,"rb") as fp:return hashlib.sha256(fp.read()).hexdigest()
        previous=(digest(q),digest(o))
        self.assertTrue(verify_persistent_stores(q,o)["verified"])
        self.assertEqual(previous,(digest(q),digest(o)))
 def test_47_trusted_principal_must_be_exact_type(self):
    class Forged(Principal): pass
    forged=Forged("tenantA","PLATFORM_OWNER")
    with self.assertRaisesRegex(PermissionError,"TRUSTED_PRINCIPAL_REQUIRED"):
        self.api.dispatch(forged,"catalog",{},20)
 def test_48_non_string_operation_rejected_without_side_effects(self):
    for operation in ([],{},None,False):
        with self.assertRaisesRegex(ValueError,"INVALID_REQUEST_FIELDS"):
            self.api.dispatch(self.customer,operation,{},20)
    self.assertEqual(self.o.execute("SELECT count(*) FROM saas_order_preparations").fetchone()[0],0)
 def test_49_time_outside_safe_integer_rejected(self):
    with self.assertRaisesRegex(ValueError,"INVALID_TIME"):
        self.api.dispatch(self.customer,"catalog",{},9007199254740992)
 def test_50_customer_cannot_read_internal_health_detail(self):
    with self.assertRaisesRegex(PermissionError,"ADMIN_ROLE_REQUIRED"):
        self.api.dispatch(self.customer,"health_detail",{},20)
 def test_51_merchant_cannot_self_close_finance_review(self):
    self.ordered()
    self.call("review_open",{"task_id":"finance1","order_id":"order1","kind":"FINANCE_EVIDENCE","reason":"pending"},self.admin)
    before=self.o.total_changes
    for state in ("RESOLVED","CANCELLED"):
        with self.assertRaisesRegex(PermissionError,"OWNER_REVIEW_REQUIRED"):
            self.call("review_close",{"task_id":"finance1","event_id":"event"+state,"state":state},self.admin,now=22)
    self.assertEqual(before,self.o.total_changes)
    self.assertEqual(self.call("recovery",principal=self.admin)["open_tasks"],["finance1"])
 def test_52_owner_close_does_not_settle_payment(self):
    self.ordered()
    self.call("review_open",{"task_id":"finance1","order_id":"order1","kind":"FINANCE_EVIDENCE","reason":"pending"},self.admin)
    owner=Principal("tenantA","PLATFORM_OWNER")
    self.assertEqual(self.call("review_close",{"task_id":"finance1","event_id":"eventowner","state":"RESOLVED"},owner,now=22)["state"],"RESOLVED")
    self.assertFalse(self.call("admin_snapshot",principal=owner)["orders"][0]["payment_settled"])
    self.assertEqual(self.call("order_status",{"order_id":"order1"})["state"],"PREPARED")
 def test_53_merchant_can_close_contract_review(self):
    self.ordered()
    self.call("review_open",{"task_id":"contract1","order_id":"order1","kind":"CONTRACT","reason":"checked"},self.admin)
    self.assertEqual(self.call("review_close",{"task_id":"contract1","event_id":"eventcontract","state":"RESOLVED"},self.admin,now=22)["state"],"RESOLVED")
 def test_54_refund_and_deployment_owner_restriction(self):
    self.ordered()
    for kind in ("REFUND","DEPLOYMENT"):
        task_id="review"+kind.lower()
        self.call("review_open",{"task_id":task_id,"order_id":"order1","kind":kind,"reason":"checked"},self.admin)
        with self.assertRaisesRegex(PermissionError,"OWNER_REVIEW_REQUIRED"):
            self.call("review_close",{"task_id":task_id,"event_id":"event"+kind,"state":"CANCELLED"},self.admin,now=22)
        self.assertEqual(self.call("review_close",{"task_id":task_id,"event_id":"owner"+kind,"state":"CANCELLED"},Principal("tenantA","PLATFORM_OWNER"),now=22)["state"],"CANCELLED")
 def test_55_foreign_owner_cannot_close_review(self):
    self.ordered()
    self.call("review_open",{"task_id":"finance1","order_id":"order1","kind":"FINANCE_EVIDENCE","reason":"pending"},self.admin)
    with self.assertRaisesRegex(ValueError,"REVIEW_NOT_FOUND"):
        self.call("review_close",{"task_id":"finance1","event_id":"foreign1","state":"RESOLVED"},Principal("tenantB","PLATFORM_OWNER"),now=22)
    self.assertEqual(self.call("recovery",principal=self.admin)["open_tasks"],["finance1"])
if __name__=="__main__":unittest.main()
