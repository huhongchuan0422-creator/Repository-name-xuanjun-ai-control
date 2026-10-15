"""No collection or entitlement changes: verify prepared-order isolation."""
import sqlite3
import hashlib
import json
import tempfile
import os
import unittest
from scripts.community_saas_modules import connect,entitled
from scripts.community_saas_offer_catalog import install as install_quotes,create_offer,quote
from scripts.community_saas_order_preparation import install,prepare,read,install_lifecycle,advance,status,entitlement_intent,renewal_intent,quote_provenance

def fee(cny=1000,usd=200,cycle="MONTH"):
    return {"type":"MODULE_FEE","label":"license","cycle":cycle,"quantity":1,
            "cny_minor":cny,"usd_minor":usd}
class PrepareOrderTests(unittest.TestCase):
 def setUp(self):
    self.quotes=connect();install_quotes(self.quotes)
    self.orders=sqlite3.connect(":memory:");install(self.orders);install_lifecycle(self.orders)
    create_offer(self.quotes,"monthly",1,"storefront_catalog","MONTHLY",
                 [fee(),fee(5000,800,"ONCE")],term_days=30)
    quote(self.quotes,"q1","tenantA","monthly",1,10,100)
 def tearDown(self):self.quotes.close();self.orders.close()
 def test_snapshot_cycles_no_payment_and_entitlement(self):
    x=prepare(self.orders,self.quotes,"orderA","tenantA","q1","CNY",20)
    self.assertEqual(x["amounts_by_cycle_minor"],{"MONTH":1000,"ONCE":5000})
    self.assertFalse(x["payment_confirmed"])
    self.assertEqual(x["quote_sha256"],hashlib.sha256(json.dumps(x["quote_snapshot"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest())
    self.assertFalse(x["entitlement_granted"])
    self.assertFalse(entitled(self.quotes,"tenantA","storefront_catalog",20))
    self.assertEqual(read(self.orders,"orderA","tenantA"),x)
 def test_duplicate_and_tenant_isolation(self):
    first=prepare(self.orders,self.quotes,"orderA","tenantA","q1","USD",20)
    self.assertEqual(prepare(self.orders,self.quotes,"orderA","tenantA","q1","USD",20),first)
    with self.assertRaisesRegex(ValueError,"ORDER_IDEMPOTENCY_CONFLICT"):
        prepare(self.orders,self.quotes,"orderA","tenantA","q1","USD",21)
    with self.assertRaisesRegex(ValueError,"DUPLICATE_QUOTE_ORDER"):
        prepare(self.orders,self.quotes,"orderB","tenantA","q1","USD",20)
    with self.assertRaisesRegex(ValueError,"ORDER_NOT_FOUND"):
        read(self.orders,"orderA","tenantB")
 def test_expiration_unknown_and_manual_contract(self):
    with self.assertRaisesRegex(ValueError,"QUOTE_EXPIRED"):
        prepare(self.orders,self.quotes,"late","tenantA","q1","CNY",100)
    create_offer(self.quotes,"supplier",1,"storefront_catalog","MONTHLY",
                 [{"type":"SUPPLIER_COST","label":"provider","cycle":"MONTH",
                   "quantity":1,"cny_minor":None,"usd_minor":None}],term_days=30)
    quote(self.quotes,"unknown","tenantA","supplier",1,10,100)
    with self.assertRaisesRegex(ValueError,"UNKNOWN_QUOTE_AMOUNT"):
        prepare(self.orders,self.quotes,"un","tenantA","unknown","CNY",20)
    create_offer(self.quotes,"custom",1,"storefront_catalog","CUSTOM",[fee()])
    quote(self.quotes,"customq","tenantA","custom",1,10,100)
    with self.assertRaisesRegex(ValueError,"MANUAL_CONTRACT"):
        prepare(self.orders,self.quotes,"customorder","tenantA","customq","CNY",20)
 def test_order_rows_immutable(self):
    prepare(self.orders,self.quotes,"orderA","tenantA","q1","CNY",20)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("UPDATE saas_order_preparations SET tenant_id='tenantB'")
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("DELETE FROM saas_order_preparations")
class OfflineLifecycleTests(PrepareOrderTests):
 def test_pending_uncertain_confirmed_requires_trusted_proof(self):
    prepare(self.orders,self.quotes,"orderA","tenantA","q1","CNY",20)
    self.assertEqual(status(self.orders,"orderA","tenantA")["state"],"PREPARED")
    advance(self.orders,"orderA","tenantA","ev1","AWAITING_EXTERNAL",21)
    advance(self.orders,"orderA","tenantA","ev2","CONFIRMATION_UNKNOWN",22)
    with self.assertRaisesRegex(ValueError,"FINANCE_ATTESTATION_REQUIRED"):
        advance(self.orders,"orderA","tenantA","ev3","CONFIRMED_EXTERNAL",23,"proofA")
    result=advance(self.orders,"orderA","tenantA","ev3","CONFIRMED_EXTERNAL",23,"proofA",True)
    self.assertEqual(result["state"],"CONFIRMED_EXTERNAL")
    self.assertFalse(result["entitlement_granted"])
    self.assertFalse(entitled(self.quotes,"tenantA","storefront_catalog",23))
    self.assertEqual(advance(self.orders,"orderA","tenantA","ev3","CONFIRMED_EXTERNAL",23,"proofA",True),result)
    with self.assertRaisesRegex(ValueError,"INVALID_STATE_TRANSITION"):
        advance(self.orders,"orderA","tenantA","ev4","CANCELLED",24)
 def test_entitlement_handoff_is_non_executable(self):
    prepare(self.orders,self.quotes,"orderA","tenantA","q1","CNY",20)
    with self.assertRaisesRegex(ValueError,"CONFIRMATION_EVIDENCE_REQUIRED"):
        entitlement_intent(self.orders,"orderA","tenantA",100)
    advance(self.orders,"orderA","tenantA","ev1","AWAITING_EXTERNAL",21)
    advance(self.orders,"orderA","tenantA","ev2","CONFIRMATION_UNKNOWN",22)
    advance(self.orders,"orderA","tenantA","ev3","CONFIRMED_EXTERNAL",23,"proofA",True)
    intent=entitlement_intent(self.orders,"orderA","tenantA",100)
    self.assertEqual(intent["proposed_valid_until"],100+30*86400)
    self.assertIsNone(intent["legacy_price_version"])
    self.assertFalse(intent["entitlement_granted"])
    self.assertTrue(intent["needs_authoritative_finance_link"])
    with self.assertRaisesRegex(ValueError,"ORDER_NOT_FOUND"):
        entitlement_intent(self.orders,"orderA","tenantB",100)
 def test_cancel_and_wrong_tenant_do_not_mutate(self):
    prepare(self.orders,self.quotes,"orderA","tenantA","q1","CNY",20)
    with self.assertRaisesRegex(ValueError,"ORDER_NOT_FOUND"):
        advance(self.orders,"orderA","tenantB","ev1","CANCELLED",21)
    advance(self.orders,"orderA","tenantA","ev1","CANCELLED",21)
    with self.assertRaisesRegex(ValueError,"INVALID_STATE_TRANSITION"):
        advance(self.orders,"orderA","tenantA","ev2","AWAITING_EXTERNAL",22)
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("DELETE FROM saas_order_lifecycle_events")
 def test_stale_event_and_idempotency_conflict(self):
    prepare(self.orders,self.quotes,"orderA","tenantA","q1","CNY",20)
    with self.assertRaisesRegex(ValueError,"STALE_EVENT_TIME"):
        advance(self.orders,"orderA","tenantA","ev1","AWAITING_EXTERNAL",19)
    advance(self.orders,"orderA","tenantA","ev1","AWAITING_EXTERNAL",21)
    with self.assertRaisesRegex(ValueError,"EVENT_IDEMPOTENCY_CONFLICT"):
        advance(self.orders,"orderA","tenantA","ev1","CANCELLED",21)
    self.assertEqual(self.orders.execute("SELECT count(*) FROM saas_order_lifecycle_events").fetchone()[0],1)
class BatchBusinessGuards(PrepareOrderTests):
 """Twenty-four independently named business acceptance paths."""
 def ready(self,order="ordA"):
    prepare(self.orders,self.quotes,order,"tenantA","q1","CNY",20)
 def confirmed(self,order="ordA"):
    self.ready(order)
    advance(self.orders,order,"tenantA",order+"a","AWAITING_EXTERNAL",21)
    advance(self.orders,order,"tenantA",order+"b","CONFIRMATION_UNKNOWN",22)
    advance(self.orders,order,"tenantA",order+"c","CONFIRMED_EXTERNAL",23,"proofA",True)
 def test_01_cny_prepare(self):
    self.ready();self.assertEqual(read(self.orders,"ordA","tenantA")["currency"],"CNY")
 def test_02_usd_prepare(self):
    v=prepare(self.orders,self.quotes,"ordA","tenantA","q1","USD",20)
    self.assertEqual(v["amounts_by_cycle_minor"]["ONCE"],800)
 def test_03_currency_rejected(self):
    with self.assertRaisesRegex(ValueError,"INVALID_ORDER_CONTEXT"):
        prepare(self.orders,self.quotes,"ordA","tenantA","q1","JPY",20)
 def test_04_boolean_time_rejected(self):
    with self.assertRaisesRegex(ValueError,"INVALID_ORDER_CONTEXT"):
        prepare(self.orders,self.quotes,"ordA","tenantA","q1","CNY",True)
 def test_05_premature_quote_rejected(self):
    with self.assertRaisesRegex(ValueError,"QUOTE_EXPIRED"):
        prepare(self.orders,self.quotes,"ordA","tenantA","q1","CNY",9)
 def test_06_quote_expiry_exclusive(self):
    with self.assertRaisesRegex(ValueError,"QUOTE_EXPIRED"):
        prepare(self.orders,self.quotes,"ordA","tenantA","q1","CNY",100)
 def test_07_wrong_tenant_quote(self):
    with self.assertRaisesRegex(ValueError,"QUOTE_NOT_FOUND"):
        prepare(self.orders,self.quotes,"ordA","tenantB","q1","CNY",20)
 def test_08_immutable_order(self):
    self.ready()
    with self.assertRaises(sqlite3.IntegrityError):
        self.orders.execute("DELETE FROM saas_order_preparations")
 def test_09_digest_consistent(self):
    self.ready();self.assertTrue(quote_provenance(self.orders,"ordA","tenantA")["verified"])
 def test_10_digest_tampering_rejected(self):
    self.ready()
    x=read(self.orders,"ordA","tenantA")
    # A forged row in a second offline database cannot pass provenance.
    evil=dict(x);evil["quote_sha256"]="0"*64
    alt=sqlite3.connect(":memory:")
    try:
        install(alt);install_lifecycle(alt)
        alt.execute("INSERT INTO saas_order_preparations VALUES(?,?,?,?,?,?)",
            ("fake","tenantA","q1","CNY",20,json.dumps(evil)))
        with self.assertRaisesRegex(ValueError,"QUOTE_SNAPSHOT_DIGEST_MISMATCH"):
            quote_provenance(alt,"fake","tenantA")
    finally:alt.close()
 def test_11_initial_state_prepared(self):
    self.ready();self.assertEqual(status(self.orders,"ordA","tenantA")["state"],"PREPARED")
 def test_12_waiting_external(self):
    self.ready()
    self.assertEqual(advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21)["state"],"AWAITING_EXTERNAL")
 def test_13_unknown_confirmation(self):
    self.ready();advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21)
    self.assertEqual(advance(self.orders,"ordA","tenantA","e2","CONFIRMATION_UNKNOWN",22)["state"],"CONFIRMATION_UNKNOWN")
 def test_14_skip_unknown_rejected(self):
    self.ready();advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21)
    with self.assertRaisesRegex(ValueError,"INVALID_STATE_TRANSITION"):
        advance(self.orders,"ordA","tenantA","e2","CONFIRMED_EXTERNAL",22,"proofA",True)
 def test_15_attestation_required(self):
    self.ready();advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21)
    advance(self.orders,"ordA","tenantA","e2","CONFIRMATION_UNKNOWN",22)
    with self.assertRaisesRegex(ValueError,"FINANCE_ATTESTATION_REQUIRED"):
        advance(self.orders,"ordA","tenantA","e3","CONFIRMED_EXTERNAL",23,"proofA")
 def test_16_proof_required(self):
    self.ready()
    with self.assertRaisesRegex(ValueError,"FINANCE_ATTESTATION_REQUIRED"):
        advance(self.orders,"ordA","tenantA","e3","CONFIRMED_EXTERNAL",23,None,True)
 def test_17_non_bool_attestation_rejected(self):
    self.ready()
    with self.assertRaisesRegex(ValueError,"INVALID_TRANSITION_CONTEXT"):
        advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21,None,"true")
 def test_18_event_replay_no_duplicate(self):
    self.ready();advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21)
    advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21)
    self.assertEqual(self.orders.execute("SELECT count(*) FROM saas_order_lifecycle_events").fetchone()[0],1)
 def test_19_event_key_conflict_rejected(self):
    self.ready();advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",21)
    with self.assertRaisesRegex(ValueError,"EVENT_IDEMPOTENCY_CONFLICT"):
        advance(self.orders,"ordA","tenantA","e1","CANCELLED",21)
 def test_20_wrong_tenant_transition(self):
    self.ready()
    with self.assertRaisesRegex(ValueError,"ORDER_NOT_FOUND"):
        advance(self.orders,"ordA","tenantB","e1","AWAITING_EXTERNAL",21)
 def test_21_stale_event_time(self):
    self.ready()
    with self.assertRaisesRegex(ValueError,"STALE_EVENT_TIME"):
        advance(self.orders,"ordA","tenantA","e1","AWAITING_EXTERNAL",19)
 def test_22_cancel_terminal(self):
    self.ready();advance(self.orders,"ordA","tenantA","e1","CANCELLED",21)
    with self.assertRaisesRegex(ValueError,"INVALID_STATE_TRANSITION"):
        advance(self.orders,"ordA","tenantA","e2","AWAITING_EXTERNAL",22)
 def test_23_renewal_continuity(self):
    self.confirmed()
    q=renewal_intent(self.orders,"ordA","tenantA",100,existing_valid_until=200)
    self.assertTrue(q["continuous"]);self.assertEqual(q["proposed_valid_from"],200)
    self.assertFalse(q["entitlement_granted"])
 def test_24_renewal_lapsed(self):
    self.confirmed()
    q=renewal_intent(self.orders,"ordA","tenantA",300,existing_valid_until=200)
    self.assertFalse(q["continuous"]);self.assertEqual(q["proposed_valid_from"],300)
 def test_25_renewal_before_evidence_blocked(self):
    self.ready()
    with self.assertRaisesRegex(ValueError,"CONFIRMATION_EVIDENCE_REQUIRED"):
        renewal_intent(self.orders,"ordA","tenantA",100,200)
 def test_26_renewal_bad_time(self):
    self.confirmed()
    with self.assertRaisesRegex(ValueError,"INVALID_RENEWAL_CONTEXT"):
        renewal_intent(self.orders,"ordA","tenantA",True,200)
 def test_27_no_grant_after_external_proof(self):
    self.confirmed()
    self.assertFalse(entitled(self.quotes,"tenantA","storefront_catalog",25))
 def test_28_unapproved_auto_renewal_false(self):
    self.confirmed()
    self.assertFalse(renewal_intent(self.orders,"ordA","tenantA",100,200)["automatic_renewal_authorized"])
if __name__=="__main__":unittest.main()
