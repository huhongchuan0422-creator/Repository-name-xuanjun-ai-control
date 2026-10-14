"""Offline multioffer tests: no payments, procurements or ledger mutations."""
import sqlite3
import unittest
import tempfile
import os
from scripts.community_saas_modules import connect
from scripts.community_saas_offer_catalog import install,create_offer,list_offers,quote,read_quote,get_offer

def line(kind="MODULE_FEE", cny=1000,usd=200,cycle="MONTH",**kw):
    return {"type":kind,"label":kind,"cycle":cycle,"quantity":1,"cny_minor":cny,"usd_minor":usd,**kw}

class TestMultiOffer(unittest.TestCase):
 def setUp(self):
    self.db=connect()
    install(self.db)
 def tearDown(self):self.db.close()
 def test_parallel_plans_and_itemized_totals(self):
    create_offer(self.db,"monthly",1,"advertising","MONTHLY",[line(),line("DEPLOYMENT",5000,700,"ONCE"),line("MAINTENANCE",300,40)],term_days=30)
    create_offer(self.db,"annual",1,"advertising","YEARLY",[line(cny=10000,usd=1600,cycle="YEAR")],term_days=365)
    create_offer(self.db,"buyout",1,"advertising","BUYOUT",[line(cny=30000,usd=5000,cycle="ONCE")])
    create_offer(self.db,"free",1,"advertising","FREE",[line(cny=0,usd=0)])
    self.assertEqual(len(list_offers(self.db,"advertising")),4)
    q=quote(self.db,"quoteA","tenantA","monthly",1,100,200)
    self.assertEqual(q["totals"],{"cny_minor":6300,"usd_minor":940})
    self.assertFalse(q["payment_authorized"])
    self.assertEqual(read_quote(self.db,"quoteA","tenantA"),q)
    with self.assertRaisesRegex(ValueError,"QUOTE_NOT_FOUND"):read_quote(self.db,"quoteA","tenantB")
 def test_unknown_cost_and_supplier_self_pay(self):
    create_offer(self.db,"selfpay",1,"storefront_catalog","MONTHLY",
         [line("SUPPLIER_COST",None,None,cost_cny_minor=None),line("AGENCY_FEE",900,100)],
         term_days=30,supplier_payment="CUSTOMER")
    q=quote(self.db,"quoteB","tenantA","selfpay",1,0,90)
    self.assertIsNone(q["totals"]["cny_minor"])
    self.assertIsNone(q["lines"][0]["cost_cny_minor"])
    with self.assertRaisesRegex(ValueError,"SUPPLIER_DOUBLE_CHARGE"):
        create_offer(self.db,"bad",1,"storefront_catalog","MONTHLY",
                     [line("SUPPLIER_COST",100,20)],term_days=30,supplier_payment="CUSTOMER")
 def test_contract_scope_and_immutability(self):
    create_offer(self.db,"contract",1,"advertising","CUSTOM",[line()],tenant_scope="tenantA")
    self.assertEqual(len(list_offers(self.db,"advertising","tenantB")),0)
    with self.assertRaisesRegex(ValueError,"OFFER_NOT_AVAILABLE"):
        quote(self.db,"qother","tenantB","contract",1,1,3)
    quote(self.db,"qgood","tenantA","contract",1,1,3)
    with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE saas_quotes SET tenant_id='tenantB'")
    with self.assertRaises(sqlite3.IntegrityError):self.db.execute("DELETE FROM saas_offer_lines")
    with self.assertRaises(sqlite3.IntegrityError):quote(self.db,"qgood","tenantA","contract",1,1,3)
 def test_reject_invalid_and_zero_rules(self):
    with self.assertRaises(ValueError):create_offer(self.db,"free",1,"advertising","FREE",[line()])
    with self.assertRaises(ValueError):create_offer(self.db,"monthly",1,"advertising","MONTHLY",[line()])
    with self.assertRaises(ValueError):create_offer(self.db,"bad",1,"advertising","MONTHLY",[line(cny=True)],term_days=30)
    with self.assertRaises(ValueError):create_offer(self.db,"bad",1,"advertising","MONTHLY",[line(usd=-1)],term_days=30)
    with self.assertRaises(ValueError):create_offer(self.db,"bad",1,"advertising","BUYOUT",[line()],term_days=1)
 def test_file_restart_preserves_offers_and_quotes(self):
    with tempfile.TemporaryDirectory() as folder:
        path=os.path.join(folder,"saas.sqlite")
        first=connect(path)
        try:
            install(first)
            create_offer(first,"restart",1,"advertising","MONTHLY",[line()],term_days=30)
            quote(first,"restartQ","tenantA","restart",1,100,200)
        finally:first.close()
        second=connect(path)
        try:
            self.assertEqual(read_quote(second,"restartQ","tenantA")["totals"]["cny_minor"],1000)
            self.assertEqual(len(list_offers(second,"advertising")),1)
        finally:second.close()
 def test_versioned_offer_quote_snapshot(self):
    create_offer(self.db,"month",1,"advertising","MONTHLY",[line()],term_days=30)
    old=quote(self.db,"oldQ","tenantA","month",1,10,50)
    create_offer(self.db,"month",2,"advertising","MONTHLY",[line(cny=2000,usd=400)],term_days=30)
    self.assertEqual(read_quote(self.db,"oldQ","tenantA"),old)
    self.assertEqual(get_offer(self.db,"month",2)["lines"][0]["cny_minor"],2000)

if __name__=="__main__":unittest.main()
