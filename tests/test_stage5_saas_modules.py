"""SaaS module-market tests; pricing/grants are offline fixtures, not billing."""
import sqlite3
import tempfile
import os
import unittest
from scripts.community_saas_modules import connect,catalog,set_price,offers,grant,entitled,capability_allowed,MODULES

class SaasModuleTests(unittest.TestCase):
 def setUp(self):self.db=connect()
 def tearDown(self):self.db.close()
 def prices(self):
  for mid in MODULES:set_price(self.db,mid,1,19900,2900,30)
 def test_module_market_separate_free_shell_and_bilingual_prices(self):
  self.prices()
  data=offers(self.db)
  self.assertEqual(len(data),7)
  for row in data:
   self.assertGreaterEqual(len(row["capabilities"]),1)
   self.assertEqual(row["offer"]["cny_minor"],19900)
   self.assertEqual(row["offer"]["usd_minor"],2900)
  set_price(self.db,"advertising",2,29900,4900,30)
  ad=next(x for x in offers(self.db) if x["id"]=="advertising")
  self.assertEqual(ad["offer"]["version"],2)
  self.assertEqual(ad["offer"]["usd_minor"],4900)
 def test_tenant_expiry_dependency_and_repurchase(self):
  self.prices()
  grant(self.db,"tenantA","advertising",100,200,1)
  self.assertFalse(capability_allowed(self.db,"tenantA","ads.manage",150))
  grant(self.db,"tenantA","storefront_catalog",100,200,1)
  self.assertTrue(capability_allowed(self.db,"tenantA","ads.manage",150))
  self.assertFalse(capability_allowed(self.db,"tenantA","ads.manage",200))
  self.assertFalse(capability_allowed(self.db,"tenantB","ads.manage",150))
  grant(self.db,"tenantA","advertising",200,300,1)
  grant(self.db,"tenantA","storefront_catalog",200,300,1)
  self.assertTrue(capability_allowed(self.db,"tenantA","ads.manage",250))
  with self.assertRaisesRegex(ValueError,"GRANT_MUST_EXTEND"):
   grant(self.db,"tenantA","advertising",200,290,1)
  events=self.db.execute("SELECT COUNT(*) FROM module_events").fetchone()[0]
  self.assertEqual(events,4)
  with self.assertRaises(sqlite3.IntegrityError):
   self.db.execute("UPDATE module_events SET action='FRAUD'")
 def test_no_unauthorized_free_or_unknown_price(self):
  with self.assertRaises(ValueError):grant(self.db,"tenantA","signed_qr",100,200,1)
  with self.assertRaises(ValueError):set_price(self.db,"signed_qr",1,True,100,30)
  with self.assertRaises(ValueError):capability_allowed(self.db,"tenantA","payments.release",100)
  with self.assertRaises(ValueError):grant(self.db,"tenantA","signed_qr",10,10,1)
 def test_sqlite_restart_keeps_versioned_grants(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=os.path.join(tmp,"modules.db")
   a=connect(path)
   set_price(a,"storefront_catalog",1,10000,1000,30)
   grant(a,"tenantR","storefront_catalog",0,900,1,"CUSTOM_DELIVERY")
   a.close()
   b=connect(path)
   try:
    self.assertTrue(capability_allowed(b,"tenantR","storefront.read",20))
    self.assertFalse(capability_allowed(b,"tenantR","storefront.read",900))
   finally:b.close()

if __name__=="__main__":unittest.main()
