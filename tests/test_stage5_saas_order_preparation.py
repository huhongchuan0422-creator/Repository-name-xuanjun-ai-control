"""No collection or entitlement changes: verify prepared-order isolation."""
import sqlite3
import hashlib
import json
import unittest
from scripts.community_saas_modules import connect,entitled
from scripts.community_saas_offer_catalog import install as install_quotes,create_offer,quote
from scripts.community_saas_order_preparation import install,prepare,read,install_lifecycle,advance,status,entitlement_intent

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
if __name__=="__main__":unittest.main()
