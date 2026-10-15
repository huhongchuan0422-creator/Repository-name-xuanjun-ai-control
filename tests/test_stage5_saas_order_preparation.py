"""No collection or entitlement changes: verify prepared-order isolation."""
import sqlite3
import unittest
from scripts.community_saas_modules import connect,entitled
from scripts.community_saas_offer_catalog import install as install_quotes,create_offer,quote
from scripts.community_saas_order_preparation import install,prepare,read

def fee(cny=1000,usd=200,cycle="MONTH"):
    return {"type":"MODULE_FEE","label":"license","cycle":cycle,"quantity":1,
            "cny_minor":cny,"usd_minor":usd}
class PrepareOrderTests(unittest.TestCase):
 def setUp(self):
    self.quotes=connect();install_quotes(self.quotes)
    self.orders=sqlite3.connect(":memory:");install(self.orders)
    create_offer(self.quotes,"monthly",1,"storefront_catalog","MONTHLY",
                 [fee(),fee(5000,800,"ONCE")],term_days=30)
    quote(self.quotes,"q1","tenantA","monthly",1,10,100)
 def tearDown(self):self.quotes.close();self.orders.close()
 def test_snapshot_cycles_no_payment_and_entitlement(self):
    x=prepare(self.orders,self.quotes,"orderA","tenantA","q1","CNY",20)
    self.assertEqual(x["amounts_by_cycle_minor"],{"MONTH":1000,"ONCE":5000})
    self.assertFalse(x["payment_confirmed"])
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
if __name__=="__main__":unittest.main()
